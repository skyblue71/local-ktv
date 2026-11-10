"""
設定檔：所有路徑和常數都放在這裡，要改的時候只改這一個地方。
"""
import os

# 專案根目錄（server 資料夾的上一層）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 資料存放位置
DATA_DIR = os.path.join(BASE_DIR, "data")
SONGS_DIR = os.path.join(DATA_DIR, "songs")

# 網頁檔案（前端）位置
WEB_DIR = os.path.join(BASE_DIR, "web")

# 歌詞搜尋網站（LRCLIB 是免費、公開的歌詞資料庫）
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
USER_AGENT = "LocalKaraoke/1.0"

# AI 分人聲用哪一個（Mel-Band RoFormer 分得比 Demucs 乾淨）
#   "mel_band_roformer"：Kim 的 Mel-Band RoFormer（預設）
#   "demucs"           ：比較輕的 Demucs（想換就改這裡，再執行一次 setup.bat 下載它的模型）
SEPARATOR = "mel_band_roformer"

# Mel-Band RoFormer 的模型檔：作者 Kimberley Jensen 本人放在 Hugging Face 的
#   作者的 GitHub（https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model）說明也是叫大家從這裡下載
#   大小、SHA256 是 Hugging Face 網頁公布的；安裝時（setup.bat → tools\download_model.py）下載一次並比對
MELBAND_MODEL_URL = "https://huggingface.co/KimberleyJSN/melbandroformer/resolve/main/MelBandRoformer.ckpt"
MELBAND_MODEL_DIR = os.path.join(os.path.expanduser("~"), ".cache", "mel_band_roformer")
MELBAND_MODEL_NAME = "MelBandRoformer.ckpt"
MELBAND_MODEL_SIZE = 913106900
MELBAND_MODEL_SHA256 = "87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e"

# Demucs 的模型名稱（SEPARATOR = "demucs" 才會用到）
# 模型來源：https://huggingface.co/adefossez/HTDemucs （demucs 原作者本人帳號）
DEMUCS_MODEL = "htdemucs"

# 去人聲模型要不要上網？
#   False：完全不連網，只用電腦裡已經下載好的模型（預設）
#   True ：允許上網檢查新版；電腦裡沒有模型時會自動下載
# 模型在安裝時（setup.bat → tools\download_model.py）下載一次；如果哪天被刪掉，再執行一次 setup.bat 就好
ALLOW_MODEL_DOWNLOAD = False

if not ALLOW_MODEL_DOWNLOAD:
    # 這是 Hugging Face 官方的「離線模式」開關，打開後它就不會連網
    os.environ["HF_HUB_OFFLINE"] = "1"

# 音高分析：每 0.01 秒取一個音高
PITCH_HOP_SECONDS = 0.01

# 認音節（字幕每個字的填色時間、評分條照音節切開）：Meta 官方的 MMS 強制對齊模型
#   torchaudio 內建的 MMS_FA 用的就是這個檔案。安裝時（setup.bat → tools\download_model.py）下載一次，
#   之後卡拉OK只讀電腦裡的檔案、不連網。檔案不在的話，字幕照音符分
MMS_MODEL_URL = "https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt"
MMS_MODEL_DIR = os.path.join(os.path.expanduser("~"), ".cache", "torch", "hub", "checkpoints")
MMS_MODEL_NAME = "mms_fa_ctc_alignment_mling_uroman.pt"
MMS_MODEL_SIZE = 1262047414
# Meta 伺服器公布的指紋（ETag，Amazon S3 分段格式：每 8 MiB 一段）和我們下載後算的 SHA256
MMS_MODEL_ETAG = "97a1af3bb69ad1fcade02350fe0453d0-151"
MMS_MODEL_SHA256 = "20ef12963ab4924bef49ac4fc7f58ad5da2ee43b2c11bc8c853c9b90ecdbc680"

# 從 YouTube 加歌：用 pip 裝的 yt-dlp（官方推薦組合，但不裝會被 Windows 擋的 pycryptodomex；來源 https://pypi.org/project/yt-dlp ）
# MV 畫質最高到 1080p（當背景夠清楚，檔案也不會太大）
YOUTUBE_MAX_HEIGHT = 1080
# 借用電腦裡的 Node.js 通過 YouTube 驗證，最低要幾版（yt-dlp 官方要求 22 以上）
NODE_MIN_VERSION = 22

# 程式啟動時，確保資料夾存在
os.makedirs(SONGS_DIR, exist_ok=True)
