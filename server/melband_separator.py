"""
AI 分人聲（Mel-Band RoFormer）：把一首歌拆成「人聲」和「伴奏」。

模型：Kim（Kimberley Jensen）的 Mel-Band RoFormer 人聲模型
  模型檔：作者本人的 Hugging Face https://huggingface.co/KimberleyJSN/melbandroformer
  程式：作者本人的 GitHub https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model
  網路結構在 mel_band_roformer.py；這個檔案負責：讀模型檔、把整首歌切成 8 秒一段給 AI、再接起來。
  切段、接起來的方法照抄作者 GitHub 的 utils.py（demix_track），設定照作者的 configs/config_vocals_mel_band_roformer.yaml。
  伴奏 = 原曲 − 人聲（作者 inference.py 的做法）。
  切段的程式原本來自 ZFTurbo 的 Music-Source-Separation-Training（MIT 授權）；
  授權聲明全文見專案最上層的「第三方授權.md」。

安全：模型檔是 PyTorch 格式，這種格式裡面可以藏程式（木馬），
  所以只用 weights_only=True 讀：只准讀數字（權重），裡面要是有程式就直接拒絕，不會執行。
  （下載時也比對過大小、SHA256，檢查過裡面只有權重：tools\\download_model.py）
"""
import os

import numpy as np
import soundfile as sf

from server import config
from server.audio_tools import save_flac

# 作者的設定檔（configs/config_vocals_mel_band_roformer.yaml）裡跟網路結構有關的部分
MODEL_SETTINGS = dict(
    dim=384, depth=6, stereo=True, num_stems=1, time_transformer_depth=1, freq_transformer_depth=1,
    num_bands=60, dim_head=64, heads=8, attn_dropout=0, ff_dropout=0, dim_freqs_in=1025,
    sample_rate=44100, stft_n_fft=2048, stft_hop_length=441, stft_win_length=2048,
    stft_normalized=False, mask_estimator_depth=2,
)
CHUNK_SIZE = 352800    # 作者設定：一次給 AI 8 秒（44100 × 8，訓練時也是 8 秒）
NUM_OVERLAP = 2        # 作者設定：每段跟下一段重疊一半，接起來比較自然

# 模型載入一次就好，之後重複使用
_model = None


def model_path():
    return os.path.join(config.MELBAND_MODEL_DIR, config.MELBAND_MODEL_NAME)


def is_available():
    """電腦有沒有裝需要的套件"""
    try:
        import torch                   # noqa: F401
        import einops                  # noqa: F401
        import rotary_embedding_torch  # noqa: F401
        return True
    except Exception:
        return False


def get_device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_model():
    """載入分人聲模型（用電腦裡已經下載好的）"""
    global _model
    if _model is None:
        import torch
        from server.mel_band_roformer import MelBandRoformer

        path = model_path()
        if not os.path.isfile(path) or os.path.getsize(path) != config.MELBAND_MODEL_SIZE:
            raise RuntimeError(
                "電腦裡找不到去人聲模型（或檔案不完整）。"
                "請執行一次 setup.bat（會下載模型一次），再處理一次這首歌。"
                "（應該在：" + path + "）"
            )
        print("載入人聲分離模型…")
        model = MelBandRoformer(**MODEL_SETTINGS)
        weights = torch.load(path, map_location="cpu", weights_only=True)
        model.load_state_dict(weights, strict=True)
        _model = model.to(get_device()).eval()
    return _model


def make_window(fade_size, device):
    """一段的權重：頭尾淡入淡出，中間是 1"""
    import torch
    window = torch.ones(CHUNK_SIZE)
    window[-fade_size:] *= torch.linspace(1, 0, fade_size)
    window[:fade_size] *= torch.linspace(0, 1, fade_size)
    return window.to(device)


def demix(model, mix, device):
    """
    照抄作者 utils.py 的 demix_track。mix：(聲道, 取樣點) 的 torch 張量；回傳人聲 (聲道, 取樣點) 的 numpy。
    1. 前後各補一段（反射），讓開頭結尾也有重疊
    2. 每次往後走半段，每段給 AI 分一次，用淡入淡出的權重加起來
    3. 最後除以權重的總和，再把前後補的去掉
    """
    import torch
    import torch.nn.functional as F

    step = CHUNK_SIZE // NUM_OVERLAP
    fade_size = CHUNK_SIZE // 10
    border = CHUNK_SIZE - step
    padded = False
    if mix.shape[1] > 2 * border and border > 0:
        mix = F.pad(mix, (border, border), mode="reflect")
        padded = True
    window_base = make_window(fade_size, device)

    # 有顯示卡時用半精度算（作者也是這樣），比較快、比較省記憶體
    use_half = device == "cuda"
    with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_half):
        with torch.no_grad():
            mix = mix.to(device)
            result = torch.zeros(tuple(mix.shape), dtype=torch.float32, device=device)
            counter = torch.zeros(tuple(mix.shape), dtype=torch.float32, device=device)
            total_length = mix.shape[1]
            i = 0
            while i < total_length:
                part = mix[:, i:i + CHUNK_SIZE]
                length = part.shape[-1]
                # 最後一段不夠長：補到 8 秒（夠長就反射補，太短就補 0）
                if length < CHUNK_SIZE:
                    if length > CHUNK_SIZE // 2 + 1:
                        part = F.pad(part, (0, CHUNK_SIZE - length), mode="reflect")
                    else:
                        part = F.pad(part, (0, CHUNK_SIZE - length, 0, 0), mode="constant", value=0)
                vocals = model(part.unsqueeze(0))[0]
                window = window_base.clone()
                if i == 0:
                    window[:fade_size] = 1          # 第一段開頭不用淡入
                elif i + CHUNK_SIZE >= total_length:
                    window[-fade_size:] = 1         # 最後一段結尾不用淡出
                result[:, i:i + length] += vocals[:, :length] * window[:length]
                counter[:, i:i + length] += window[:length]
                i += step
            estimated = (result / counter).cpu().numpy()
    np.nan_to_num(estimated, copy=False, nan=0.0)
    if padded:
        estimated = estimated[:, border:-border]
    return estimated


def separate_vocals(wav_path, vocals_path, instrumental_path):
    """
    wav_path：44100Hz 雙聲道的 WAV
    會產生 vocals_path（人聲）和 instrumental_path（伴奏）兩個 FLAC 檔
    """
    import torch

    model = load_model()
    audio, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
    mix = torch.from_numpy(audio.T.copy())
    vocals = demix(model, mix, get_device())
    instrumental = audio.T - vocals      # 伴奏 = 原曲 − 人聲

    save_flac(vocals_path, vocals, sample_rate)
    save_flac(instrumental_path, instrumental, sample_rate)

    # 釋放顯示卡記憶體
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
