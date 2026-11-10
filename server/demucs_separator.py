"""
AI 分人聲（Demucs；config.py 的 SEPARATOR = "demucs" 才會用）。

使用 Meta 開源的 demucs 模型，有 NVIDIA 顯示卡會自動用顯示卡加速。
模型（約 80MB）下載在電腦裡，現在設定成不連網（見 config.py 的 ALLOW_MODEL_DOWNLOAD）：
  下載網址：https://huggingface.co/adefossez/HTDemucs （demucs 原作者本人帳號）
  存放位置：C:\\Users\\<你的名字>\\.cache\\huggingface\\hub\\models--adefossez--HTDemucs
這是 demucs 4.1.0 官方的做法（GitHub README：pretrained models hosted on Hugging Face）。
"""
import soundfile as sf

from server.audio_tools import save_flac
from server.config import ALLOW_MODEL_DOWNLOAD, DEMUCS_MODEL

# 模型載入一次就好，之後重複使用
_model = None


def is_available():
    """檢查電腦有沒有安裝 demucs 和 torch"""
    try:
        import torch      # noqa: F401
        import demucs     # noqa: F401
        return True
    except Exception:
        return False


def get_device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_model():
    """載入去人聲模型（用電腦裡已經下載好的）"""
    global _model
    if _model is None:
        from demucs.pretrained import get_model
        print("載入人聲分離模型…")
        # 名字前面加 "hf://"：只准從 Hugging Face 拿模型。
        # 不加的話，Hugging Face 拿不到時 demucs 會自動改去 Meta 的舊伺服器下載，
        # 那條路不受「不連網」開關控制，所以要擋掉。
        model_name = "hf://" + DEMUCS_MODEL
        try:
            _model = get_model(model_name)
        except Exception as error:
            if not ALLOW_MODEL_DOWNLOAD:
                raise RuntimeError(
                    "電腦裡找不到去人聲模型，而且目前設定成不連網。"
                    "請執行一次 setup.bat（會下載模型一次），再處理一次這首歌。"
                    "（原始錯誤：" + str(error) + "）"
                )
            raise
        _model.eval()
    return _model


def separate_vocals(wav_path, vocals_path, instrumental_path):
    """
    wav_path：44100Hz 雙聲道的 WAV
    會產生 vocals_path（人聲）和 instrumental_path（伴奏）兩個 FLAC 檔
    """
    import torch
    from demucs.apply import apply_model

    model = load_model()

    # 讀取音訊，形狀變成 (聲道, 取樣點)
    audio, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
    wav = torch.from_numpy(audio.T.copy())

    # demucs 要求先把音量標準化，分離完再還原
    mono = wav.mean(0)
    mean = mono.mean()
    std = mono.std() + 1e-8
    wav = (wav - mean) / std

    with torch.no_grad():
        result = apply_model(
            model,
            wav[None],             # 加一個批次維度
            device=get_device(),
            shifts=1,
            split=True,            # 長歌曲分段處理，避免顯示卡記憶體不夠
            overlap=0.25,
            progress=False,
        )[0]

    result = result * std + mean

    # result 裡有 drums（鼓）、bass（貝斯）、other（其他）、vocals（人聲）
    source_names = list(model.sources)
    vocals = result[source_names.index("vocals")]

    # 伴奏 = 人聲以外的全部加起來
    instrumental = torch.zeros_like(vocals)
    for index in range(len(source_names)):
        if source_names[index] != "vocals":
            instrumental = instrumental + result[index]

    save_flac(vocals_path, vocals.cpu().numpy(), sample_rate)
    save_flac(instrumental_path, instrumental.cpu().numpy(), sample_rate)

    # 釋放顯示卡記憶體
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
