"""
唱完的錄音，下載前重新包裝一次。

瀏覽器錄出來的檔案裡沒有寫「總共多長」，有些播放軟體會看不到長度、也不能拖。
這裡用 ffmpeg 轉成 mp3，檔案就會有長度，手機和其他軟體也都打得開。

轉成什麼格式，寫在 config.py 的 RECORDING_FORMATS。
錄音只會暫時放在暫存資料夾，轉完就刪掉，不會留在硬碟。
"""
import os
import shutil
import tempfile

from server import audio_tools
from server.config import RECORDING_FORMATS


def list_formats():
    """給網頁用的格式清單（只給按鈕需要的東西）"""
    formats = []
    for item in RECORDING_FORMATS:
        formats.append({"id": item["id"], "label": item["label"]})
    return formats


def find_format(format_id):
    """用代號找格式，找不到回傳 None"""
    for item in RECORDING_FORMATS:
        if item["id"] == format_id:
            return item
    return None


def export_recording(source_file, export_format):
    """
    把錄音轉成指定的格式，回傳轉好的檔案內容（bytes）。
    source_file：上傳來的錄音（可以讀的檔案物件）
    export_format：RECORDING_FORMATS 裡的其中一列
    """
    with tempfile.TemporaryDirectory() as folder:
        # ffmpeg 是看檔案內容認格式的，所以來源檔名不用管副檔名
        source_path = os.path.join(folder, "source")
        target_path = os.path.join(folder, "target." + export_format["id"])
        with open(source_path, "wb") as output:
            shutil.copyfileobj(source_file, output)

        arguments = ["-i", source_path, "-vn"] + export_format["ffmpeg"] + [target_path]
        audio_tools.run_ffmpeg(arguments)

        with open(target_path, "rb") as result:
            return result.read()
    # 離開 with 的時候，暫存資料夾和裡面的檔案會自動刪掉
