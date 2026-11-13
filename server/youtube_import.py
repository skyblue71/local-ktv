"""
從 YouTube 網址加歌：讀取影片資訊、下載影片（含 MV 畫面）、下載縮圖當封面。

使用 pip 裝在虛擬環境裡的 yt-dlp（官方推薦組合 yt-dlp[default]，但不裝 pycryptodomex，
因為 Windows 會擋它；來源 https://pypi.org/project/yt-dlp ，官方 GitHub：https://github.com/yt-dlp/yt-dlp ）。
合併畫面和聲音用的是本來就有的 ffmpeg（imageio-ffmpeg 附的，audio_tools 那一份）。

YouTube 會要求先跑一段 JavaScript 算「通行碼」才給高畫質網址，
電腦裡有 Node.js 的話就借用它來跑（沒有也能下載，只是畫質可能比較低）。

⚠️ YouTube 的使用規定不允許下載影片，請只用在你有權利下載的影片。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys

from server.audio_tools import get_ffmpeg_path
from server.config import DATA_DIR, NODE_MIN_VERSION, YOUTUBE_MAX_HEIGHT

YTDLP_CACHE_DIR = os.path.join(DATA_DIR, "yt-dlp-cache")

# 執行 yt-dlp 的方式：用虛擬環境的 python 跑 python -m yt_dlp
YTDLP_COMMAND = [sys.executable, "-m", "yt_dlp"]

# 執行外部程式時不要跳出黑色視窗
NO_WINDOW = 0x08000000

# 進度的輸出格式：
#   PROGRESS|畫面格式|百分比|第幾段|總共幾段
PROGRESS_TEMPLATE = (
    "download:PROGRESS|%(info.vcodec)s|%(progress._percent_str)s"
    "|%(progress.fragment_index)s|%(progress.fragment_count)s"
)


# ---------- 工具 ----------

def is_available():
    """虛擬環境裡有沒有裝 yt-dlp"""
    return importlib.util.find_spec("yt_dlp") is not None


def find_node():
    """找電腦裡符合版本的 Node.js，找到回傳路徑，找不到回傳 None"""
    path = shutil.which("node")
    if path is None:
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True,
                                timeout=10, creationflags=NO_WINDOW)
        major = int(result.stdout.strip().lstrip("v").split(".")[0])
    except Exception:
        return None
    if major < NODE_MIN_VERSION:
        return None
    return path


def make_environment():
    """讓 yt-dlp 用 UTF-8 輸出，中文、日文標題才不會變亂碼"""
    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def check_url(url):
    """網址要是 http 或 https 開頭"""
    url = (url or "").strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("請貼上影片網址（https:// 開頭）")
    return url


def common_arguments():
    """每次執行 yt-dlp 都要加的參數"""
    # --cache-dir：yt-dlp 的小暫存放在 data\ 裡（不放到資料夾外面的使用者資料夾）
    arguments = ["--no-playlist", "--encoding", "utf-8", "--no-colors", "--cache-dir", YTDLP_CACHE_DIR]
    node = find_node()
    if node is not None:
        arguments += ["--js-runtimes", "node:" + node]
    return arguments


# ---------- 讀取影片資訊 ----------

def clean_artist(name):
    """YouTube Music 的「歌手名 - Topic」頻道，把後面的 - Topic 拿掉"""
    name = (name or "").strip()
    if name.endswith(" - Topic"):
        name = name[:-len(" - Topic")]
    return name


def get_info(url):
    """
    讀取影片資訊（不下載影片），回傳：
      {"title", "artist", "duration", "video_id", "url"}
    """
    url = check_url(url)
    command = YTDLP_COMMAND + ["-J"] + common_arguments() + ["--", url]
    result = subprocess.run(command, capture_output=True, timeout=120,
                            env=make_environment(), creationflags=NO_WINDOW)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError("讀不到影片資訊：" + message[-300:])

    info = json.loads(result.stdout.decode("utf-8", errors="replace"))

    # 有些音樂影片（例如 YouTube Music 的 Topic 頻道）會附上正式的歌名和歌手
    title = info.get("track") or info.get("title") or ""
    artist = info.get("artist") or info.get("creator") or info.get("uploader") or ""
    # artist 有時是好幾個人用逗號隔開，只取第一個
    artist = clean_artist(artist.split(",")[0])

    return {
        "title": title,
        "artist": artist,
        "duration": info.get("duration") or 0,
        "video_id": info.get("id") or "",
        "url": info.get("webpage_url") or url,
    }


# ---------- 下載 ----------

def fragment_percent(index_text, count_text):
    """分段傳送時，用「第幾段／總共幾段」算百分比"""
    try:
        index = int(index_text)
        count = int(count_text)
    except ValueError:
        return None
    if count <= 0:
        return None
    return index * 100.0 / count


def parse_progress(line):
    """把進度那一行翻成 (畫面或聲音, 百分比)；不是進度就回傳 None"""
    if not line.startswith("PROGRESS|"):
        return None
    parts = line.split("|")
    if len(parts) < 5:
        return None
    if parts[1] == "none":
        part = "聲音"
    else:
        part = "畫面"
    percent = fragment_percent(parts[3], parts[4])
    if percent is None:
        try:
            percent = float(parts[2].strip().replace("%", ""))
        except ValueError:
            percent = 0.0
    return part, percent


def cover_arguments():
    """順便下載影片縮圖，轉成 jpg，存成 cover.jpg（當歌曲封面）"""
    return ["--write-thumbnail", "--convert-thumbnails", "jpg", "-o", "thumbnail:cover.%(ext)s"]


def download_cover(url, folder):
    """
    只下載影片縮圖當封面（不下載影片）。
    給「以前加的歌」或「下載時縮圖失敗」補封面用，成功回傳 True。
    """
    url = check_url(url)
    command = YTDLP_COMMAND + common_arguments() + ["--skip-download"] + cover_arguments() + [
        "--ffmpeg-location", get_ffmpeg_path(),
        "-P", folder,
        "--", url,
    ]
    result = subprocess.run(command, capture_output=True, timeout=120,
                            env=make_environment(), creationflags=NO_WINDOW)
    if result.returncode != 0:
        print("[yt-dlp] 下載封面失敗：" + result.stderr.decode("utf-8", errors="replace")[-200:])
    return os.path.exists(os.path.join(folder, "cover.jpg"))


def download(url, folder, on_progress=None):
    """
    下載影片到 folder，存成 original.mp4（畫面最高 1080p＋最好的聲音）。
    on_progress(畫面或聲音, 百分比) 用來回報進度。
    回傳存好的檔名（例如 "original.mp4"）。
    """
    url = check_url(url)
    format_arguments = [
        "-f", "bv*+ba/b",                                  # 最好的畫面＋最好的聲音
        "-S", "res:" + str(YOUTUBE_MAX_HEIGHT),            # 畫面最高 1080p
        "--merge-output-format", "mp4",                    # 合成 mp4（瀏覽器可以播 MV）
    ]
    command = YTDLP_COMMAND + common_arguments() + format_arguments + cover_arguments() + [
        "--ffmpeg-location", get_ffmpeg_path(),
        "-P", folder,
        "-o", "original.%(ext)s",
        "--newline", "--progress", "--progress-template", PROGRESS_TEMPLATE,
        "--", url,
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env=make_environment(), creationflags=NO_WINDOW)
    last_lines = []
    for raw_line in process.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip()
        progress = parse_progress(line)
        if progress is not None:
            if on_progress is not None:
                on_progress(progress[0], progress[1])
        elif line != "":
            print("[yt-dlp] " + line)
            last_lines.append(line)
            last_lines = last_lines[-5:]
    process.wait()

    if process.returncode != 0:
        raise RuntimeError("YouTube 下載失敗：" + " / ".join(last_lines)[-300:])

    if not os.path.exists(os.path.join(folder, "original.mp4")):
        raise RuntimeError("YouTube 下載完了，但找不到 original.mp4")
    return "original.mp4"
