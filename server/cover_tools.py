"""
封面：換成你自己選的圖片、或還原成原本的封面。

  cover.jpg           現在用的封面
  cover_original.jpg  第一次換封面前，原本的封面（YouTube 縮圖、檔案內附的封面）先備份在這裡，
                      按「還原原本的封面」就搬回來
圖片用 ffmpeg（imageio-ffmpeg 附的）轉成 jpg，太大的縮小到 COVER_MAX_WIDTH 寬。
"""
import os
import shutil
import subprocess
import time

from server.audio_tools import get_ffmpeg_path

COVER_MAX_WIDTH = 1280            # 封面最寬幾像素（太大的縮小，載入比較快）
COVER_MAX_BYTES = 20 * 1024 * 1024  # 圖片檔最大 20MB

COVER_NAME = "cover.jpg"
BACKUP_NAME = "cover_original.jpg"


def convert_image(source_path, target_path):
    """任何 ffmpeg 看得懂的圖片（jpg、png、webp、gif、bmp…）→ jpg。失敗丟出 ValueError"""
    command = [
        get_ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", source_path,
        "-frames:v", "1",
        "-vf", "scale='min(" + str(COVER_MAX_WIDTH) + ",iw)':-2",
        "-q:v", "3",
        target_path,
    ]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(command, capture_output=True, creationflags=flags)
    if result.returncode != 0 or not os.path.isfile(target_path) or os.path.getsize(target_path) == 0:
        raise ValueError("看不懂這個圖片檔，請換一張（jpg、png、webp 都可以）")


def save_custom_cover(folder, upload_path):
    """把上傳的圖片存成封面；第一次換的時候先備份原本的封面"""
    if os.path.getsize(upload_path) > COVER_MAX_BYTES:
        raise ValueError("圖片太大了（最大 20MB）")
    temp_path = os.path.join(folder, "cover_new.jpg")
    try:
        convert_image(upload_path, temp_path)
        cover_path = os.path.join(folder, COVER_NAME)
        backup_path = os.path.join(folder, BACKUP_NAME)
        if os.path.isfile(cover_path) and not os.path.isfile(backup_path):
            shutil.copyfile(cover_path, backup_path)
        os.replace(temp_path, cover_path)
    finally:
        if os.path.isfile(temp_path):
            os.remove(temp_path)


def restore_original_cover(folder):
    """還原原本的封面（沒有備份 = 原本就沒有封面，就把封面拿掉）。回傳還原後有沒有封面"""
    cover_path = os.path.join(folder, COVER_NAME)
    backup_path = os.path.join(folder, BACKUP_NAME)
    if os.path.isfile(backup_path):
        os.replace(backup_path, cover_path)
        return True
    if os.path.isfile(cover_path):
        os.remove(cover_path)
    return False


def new_version():
    """封面換了之後給一個新號碼，網頁才會重新抓圖（不然瀏覽器會用舊的）"""
    return str(int(time.time() * 1000))
