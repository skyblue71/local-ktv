"""
用 CREPE（AI 音高辨識）找出人聲每一幀的音高。

做法跟 torchcrepe 0.0.24 的 predict(...) 一樣（MIT 授權，https://github.com/maxrmorrison/torchcrepe ）：
  1. 每 hop 個取樣點切一段 1024 點的聲音（一幀），減掉平均、除以標準差
  2. 丟進 AI 模型 → 每一幀 360 格音高的機率
  3. 太低、太高的格子不要
  4. Viterbi 找一條不亂跳的路線（一次 1024 幀，一段一段算）
  5. 格子換成頻率（加一點點雜訊，消掉每格 20 音分的鋸齒）

為什麼不直接用 torchcrepe：它一載入就連帶載入 numba，
Windows「智慧型應用程式控制」會擋 numba 的檔案。
模型權重還是用 torchcrepe 套件附的 full.pth（沒有另外下載）。
授權聲明全文見專案最上層的「第三方授權.md」。
"""
import importlib.util
import os

import numpy as np
import torch

from server.crepe_model import CrepeModel
from server.crepe_viterbi import viterbi_bins

CREPE_RATE = 16000        # CREPE 只吃 16000Hz 的聲音
WINDOW = 1024             # 一幀 1024 個取樣點
BATCH_FRAMES = 1024       # 一次算 1024 幀（跟原本的設定一樣）
CENTS_PER_BIN = 20        # 每一格 20 音分
FIRST_BIN_CENTS = 1997.3794084376191   # 第 0 格的音分（10Hz 當作 0 音分）
DITHER_SEED = 0           # 雜訊的亂數種子固定：同一首歌每次分析結果都一樣

# 模型只載入一次，之後重複用
loaded_model = None
loaded_device = None


def weights_path():
    """torchcrepe 套件附的模型權重檔（只找檔案位置，不載入 torchcrepe）"""
    spec = importlib.util.find_spec("torchcrepe")
    if spec is None or spec.origin is None:
        raise RuntimeError("找不到 torchcrepe 套件（CREPE 的模型檔在裡面），請執行 setup.bat")
    folder = os.path.dirname(spec.origin)
    return os.path.join(folder, "assets", "full.pth")


def get_model(device):
    global loaded_model, loaded_device
    if loaded_model is None or loaded_device != device:
        model = CrepeModel()
        weights = torch.load(weights_path(), map_location=device, weights_only=True)
        model.load_state_dict(weights)
        model = model.to(device)
        model.eval()
        loaded_model = model
        loaded_device = device
    return loaded_model


def frequency_to_bin(frequency, round_up):
    """頻率 → 第幾格"""
    cents = 1200 * np.log2(frequency / 10.0)
    position = (cents - FIRST_BIN_CENTS) / CENTS_PER_BIN
    if round_up:
        return int(np.ceil(position))
    return int(np.floor(position))


def median_of_3(values):
    """每一點跟左右鄰居取中間的值，讓信心度不要一直跳。
    頭尾只有 2 個值，取比較小的那個（跟 torchcrepe.filter.median 一樣）"""
    if len(values) < 2:
        return values.copy()
    result = np.empty_like(values)
    stacked = np.stack([values[:-2], values[1:-1], values[2:]])
    result[1:-1] = np.median(stacked, axis=0)
    result[0] = min(values[0], values[1])
    result[-1] = min(values[-2], values[-1])
    return result


def find_bins(audio, hop, lowest_hz, highest_hz):
    """audio：16000Hz 單聲道 numpy 陣列。
    回傳 (每一幀選第幾格, 每一幀的信心度)，每 hop 個取樣點一幀"""
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    model = get_model(device)
    low_bin = frequency_to_bin(lowest_hz, False)
    high_bin = frequency_to_bin(highest_hz, True)

    signal = torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0)
    total_frames = 1 + int(signal.size(1) // hop)
    # 前後各補半幀的 0，讓每一幀的中心對準時間點
    signal = torch.nn.functional.pad(signal, (WINDOW // 2, WINDOW // 2))

    bin_parts = []
    confidence_parts = []
    with torch.no_grad():
        for first in range(0, total_frames, BATCH_FRAMES):
            # 1. 切出這一段的每一幀
            start = first * hop
            end = min(signal.size(1), (first + BATCH_FRAMES - 1) * hop + WINDOW)
            frames = torch.nn.functional.unfold(signal[:, None, None, start:end],
                                                kernel_size=(1, WINDOW),
                                                stride=(1, hop))
            frames = frames.transpose(1, 2).reshape(-1, WINDOW).to(device)
            frames = frames - frames.mean(dim=1, keepdim=True)
            frames = frames / torch.clamp(frames.std(dim=1, keepdim=True), min=1e-10)

            # 2. AI 模型：每一幀 360 格的機率，轉成 (360, 幀數)
            probabilities = model(frames).T.contiguous()

            # 3. 太低、太高的格子不要
            probabilities[:low_bin, :] = -float("inf")
            probabilities[high_bin:, :] = -float("inf")

            # 4. Viterbi 找路線；信心度 = 選到的那一格的機率
            chances = torch.softmax(probabilities, dim=0)
            bins = viterbi_bins(chances)
            bins_tensor = torch.from_numpy(bins).to(device)
            confidence = probabilities.gather(0, bins_tensor[None, :])[0]

            bin_parts.append(bins)
            confidence_parts.append(confidence.cpu().numpy())

    return np.concatenate(bin_parts), np.concatenate(confidence_parts)


def detect(audio, hop, lowest_hz, highest_hz):
    """回傳 (頻率陣列 Hz, 信心度陣列)，每 hop 個取樣點一個"""
    bins, confidence = find_bins(audio, hop, lowest_hz, highest_hz)

    # 5. 格子 → 頻率，加一點點三角形分布的雜訊（-20～+20 音分），跟 torchcrepe 一樣
    random = np.random.default_rng(DITHER_SEED)
    noise = random.triangular(-CENTS_PER_BIN, 0, CENTS_PER_BIN, size=len(bins))
    cents = CENTS_PER_BIN * bins + FIRST_BIN_CENTS + noise
    frequency = 10.0 * 2.0 ** (cents / 1200.0)

    confidence = median_of_3(confidence)
    return frequency.astype(np.float32), confidence.astype(np.float32)
