"""
AI 人聲分離：把一首歌拆成「人聲」和「伴奏」。
用 Mel-Band RoFormer（melband_separator.py）。其他程式只要叫這個檔案的函式。
"""
import numpy as np
import soundfile as sf

from server import melband_separator
from server.audio_tools import save_flac


def is_available():
    """檢查電腦有沒有安裝分人聲需要的套件"""
    return melband_separator.is_available()


def has_model():
    """電腦裡有沒有分人聲的模型檔（大小對）"""
    return melband_separator.has_model()


def get_gpu_name():
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return ""


def load_model():
    """載入分人聲模型（用電腦裡已經下載好的）"""
    return melband_separator.load_model()


def separate_vocals(wav_path, vocals_path, instrumental_path):
    """
    wav_path：44100Hz 雙聲道的 WAV
    會產生 vocals_path（人聲）和 instrumental_path（伴奏）兩個 FLAC 檔
    """
    melband_separator.separate_vocals(wav_path, vocals_path, instrumental_path)


def copy_as_instrumental(wav_path, instrumental_path):
    """不做分離時：直接把原曲當作伴奏"""
    audio, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
    save_flac(instrumental_path, np.asarray(audio.T), sample_rate)
