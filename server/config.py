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

# ---------- AI 模型 ----------
# 模型檔只在安裝時（setup.bat → tools\download_model.py）下載一次，之後卡拉OK只讀電腦裡的檔案、不連網。
# 被刪掉的話，按 update.bat 會問要不要再下載

# 分人聲：Kim（Kimberley Jensen）的 Mel-Band RoFormer，作者本人放在 Hugging Face 的
#   作者的 GitHub（https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model）說明也是叫大家從這裡下載
#   大小、SHA256 是 Hugging Face 網頁公布的；下載時比對
MELBAND_MODEL_URL = "https://huggingface.co/KimberleyJSN/melbandroformer/resolve/main/MelBandRoformer.ckpt"
MELBAND_MODEL_NAME = "MelBandRoformer.ckpt"
MELBAND_MODEL_SIZE = 913106900
MELBAND_MODEL_SHA256 = "87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e"

# 認音節（字幕每個字的填色時間、評分條照音節切開）：Meta 官方的 MMS 強制對齊模型
#   torchaudio 內建的 MMS_FA 用的就是這個檔案。檔案不在的話，字幕照音符分
MMS_MODEL_URL = "https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt"
MMS_MODEL_NAME = "mms_fa_ctc_alignment_mling_uroman.pt"
MMS_MODEL_SIZE = 1262047414
# Meta 伺服器公布的指紋（ETag，Amazon S3 分段格式：每 8 MiB 一段）和我們下載後算的 SHA256
MMS_MODEL_ETAG = "97a1af3bb69ad1fcade02350fe0453d0-151"
MMS_MODEL_SHA256 = "20ef12963ab4924bef49ac4fc7f58ad5da2ee43b2c11bc8c853c9b90ecdbc680"

# 模型放在專案資料夾的 models\，每個模型一個資料夾（models\資料夾\檔名）：
#   這個程式的東西都在它自己的資料夾裡，刪掉資料夾就乾淨；整理的時候也只動程式認得的資料夾
#   不放 .venv：setup.bat 遇到 Python 太舊會把 .venv 整個清掉重建，模型會被一起清掉
MODELS_DIR = os.path.join(BASE_DIR, "models")
MODEL_FOLDERS = {
    MELBAND_MODEL_NAME: "mel_band_roformer",
    MMS_MODEL_NAME: "mms",
}
# 以前用過、現在不用的模型資料夾（models\ 底下的名字）：按 update.bat 時，還在的話問要不要丟到資源回收筒
#   （tools\clean_models.py）。換掉一個模型的時候，把它的資料夾名字從 MODEL_FOLDERS 搬到這裡
OLD_MODEL_FOLDERS = []
# 舊版把模型放在使用者資料夾的 .cache 裡。models\ 沒有、那裡有的話照樣用，
#   不用重新下載，也不會搬動它（README 有寫這兩個位置，不要的人可以自己刪）
OLD_MODEL_DIRS = {
    MELBAND_MODEL_NAME: os.path.join(os.path.expanduser("~"), ".cache", "mel_band_roformer"),
    MMS_MODEL_NAME: os.path.join(os.path.expanduser("~"), ".cache", "torch", "hub", "checkpoints"),
}


def download_path(name):
    """模型檔 name 下載要放的地方：models\\ 裡它自己的資料夾"""
    return os.path.join(MODELS_DIR, MODEL_FOLDERS[name], name)


def model_path(name):
    """
    模型檔 name 的位置：models\\ 裡它的資料夾有就用它；沒有、舊的位置有，用舊的；
    都沒有回傳 models\\ 裡的（download_path）
    """
    new = download_path(name)
    old_dir = OLD_MODEL_DIRS.get(name)
    if os.path.isfile(new) or old_dir is None or not os.path.isfile(os.path.join(old_dir, name)):
        return new
    return os.path.join(old_dir, name)


# 音高分析：每 0.01 秒取一個音高
PITCH_HOP_SECONDS = 0.01

# 從 YouTube 加歌：用 pip 裝的 yt-dlp（官方推薦組合，但不裝會被 Windows 擋的 pycryptodomex；來源 https://pypi.org/project/yt-dlp ）
# MV 畫質最高到 1080p（當背景夠清楚，檔案也不會太大）
YOUTUBE_MAX_HEIGHT = 1080
# 借用電腦裡的 Node.js 通過 YouTube 驗證，最低要幾版（yt-dlp 官方要求 22 以上）
NODE_MIN_VERSION = 22

# 唱完下載錄音的格式（結果畫面的下載按鈕就是照這張表排的，一列一顆按鈕）
#   id        ：格式的代號，也是下載檔案的副檔名
#   label     ：按鈕上的字（前面會自動加「下載」）
#   media_type：告訴瀏覽器這是什麼檔案
#   ffmpeg    ：轉檔時給 ffmpeg 的參數
#               mp3 的 "-q:a" 是音質，0 最好、9 最差，數字越小檔案越大
RECORDING_FORMATS = [
    {"id": "mp3", "label": "MP3", "media_type": "audio/mpeg", "ffmpeg": ["-c:a", "libmp3lame", "-q:a", "2"]},
]

# 程式啟動時，確保資料夾存在
os.makedirs(SONGS_DIR, exist_ok=True)
