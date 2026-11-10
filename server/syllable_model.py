"""
認音節（第 1 步，加歌時做一次）：用 Meta 官方的 MMS 模型「聽」整首人聲，
算出每 0.02 秒「聽起來像哪個字母」的機率，存成 mms_emission.npy（每首約 1MB）。

之後做字幕（syllable_aligner.py）只要讀這個檔案，把每一句的拼音對上去就好，
不用再跑 AI，所以改偏移、改歌詞重算字幕都很快。

為什麼要它：只把「一句唱的時間平均分給每個音節」的話，
拉長音那個字會被切給好幾個字。MMS 聽得出每個音（ka、yo、wa…）在哪裡。
（實測一首歌：沒有換字痕跡的長音被切開 24 個 → 7 個）

模型：torchaudio 內建的 MMS_FA，檔案在 config.MMS_MODEL_DIR（安裝時下載，見 tools\\download_model.py）。
讀檔用 weights_only=True（只讀數字，不執行檔案裡的程式碼），而且只讀電腦裡的檔案、不連網。
"""
import gc
import os

import numpy as np
import soundfile as sf

from server.audio_tools import convert_audio
from server.config import MMS_MODEL_DIR, MMS_MODEL_NAME

RATE = 16000                 # MMS 只吃 16000Hz 的聲音
FRAME_SECONDS = 320 / RATE   # 每一格 0.02 秒（模型每 320 個取樣點輸出一格）
CHUNK_SECONDS = 30.0         # 一次聽 30 秒（整首一次聽，顯示卡記憶體不夠）
OVERLAP_SECONDS = 1.0        # 每段前後多聽 1 秒，接起來的地方才不會怪
EMISSION_FILE = "mms_emission.npy"


def is_available():
    """電腦裡有沒有 MMS 模型檔"""
    return os.path.isfile(os.path.join(MMS_MODEL_DIR, MMS_MODEL_NAME))


def load_model(device):
    import torch  # noqa: F401（放在這裡：沒用到就不載入）
    from torchaudio.pipelines import MMS_FA
    model = MMS_FA.get_model(with_star=True, dl_kwargs={
        "model_dir": MMS_MODEL_DIR,
        "file_name": MMS_MODEL_NAME,
        "weights_only": True,   # 只讀數字，不執行檔案裡的程式碼
        "progress": False,
    })
    return model.to(device)


def compute_emission(vocals_path, work_dir):
    """聽整首人聲，回傳 (格數, 29) 的 float16 陣列：每 0.02 秒每個字母的機率（取 log）"""
    import torch

    temp_path = os.path.join(work_dir, "mms_16k.wav")
    convert_audio(vocals_path, temp_path, RATE, 1)
    audio, _ = sf.read(temp_path, dtype="float32")
    os.remove(temp_path)

    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    model = load_model(device)

    chunk = int(CHUNK_SECONDS * RATE)
    overlap = int(OVERLAP_SECONDS * RATE)
    total_frames = int(len(audio) / (FRAME_SECONDS * RATE))
    parts = []
    with torch.inference_mode():
        for begin in range(0, len(audio), chunk):
            # 這一段多聽前後各 1 秒，只留中間屬於這一段的格子
            first = max(0, begin - overlap)
            last = min(len(audio), begin + chunk + overlap)
            piece = torch.from_numpy(audio[first:last]).unsqueeze(0).to(device)
            if piece.shape[1] < 400:
                break   # 剩下不到一格的聲音
            emission, _ = model(piece)
            emission = emission[0].float().cpu().numpy()
            frame_seconds = (last - first) / RATE / emission.shape[0]
            keep_from = int(round((begin - first) / RATE / frame_seconds))
            keep_count = int(round((min(begin + chunk, len(audio)) - begin) / RATE / frame_seconds))
            parts.append(emission[keep_from:keep_from + keep_count])

    # 用完就放掉顯示卡記憶體（去人聲、音高辨識也要用）
    del model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    result = np.concatenate(parts, axis=0)[:max(1, total_frames)]
    return result.astype(np.float16)


def save_emission(song_folder, vocals_path):
    """算好存起來；回傳存好的路徑"""
    emission = compute_emission(vocals_path, song_folder)
    path = os.path.join(song_folder, EMISSION_FILE)
    temp_path = path + ".tmp.npy"
    np.save(temp_path, emission)
    os.replace(temp_path, path)
    return path


def load_emission(song_folder):
    """讀存好的結果；沒有就回傳 None"""
    path = os.path.join(song_folder, EMISSION_FILE)
    if not os.path.isfile(path):
        return None
    return np.load(path)
