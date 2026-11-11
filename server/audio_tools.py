"""
音訊小工具：轉檔、讀取長度、讀取歌曲標籤和封面。

轉檔使用 ffmpeg（由 imageio-ffmpeg 套件附帶，不用另外安裝）。
"""
import os
import subprocess

import imageio_ffmpeg
import numpy as np
import soundfile as sf


def get_ffmpeg_path():
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(arguments):
    """叫 ffmpeg 做事。arguments 是要給它的參數（不用寫 ffmpeg 自己）；失敗會丟出錯誤"""
    command = [
        get_ffmpeg_path(),
        "-y",                      # 覆蓋舊檔
        "-loglevel", "error",      # 只顯示錯誤
    ] + arguments
    # Windows 上不要跳出黑色視窗
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW

    result = subprocess.run(command, capture_output=True, creationflags=flags)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError("音訊轉換失敗：" + message[-400:])


def convert_audio(source_path, target_path, sample_rate=44100, channels=2):
    """把任何音訊/影片檔轉成 WAV（例如 mp3、m4a、mp4 都可以）"""
    run_ffmpeg([
        "-i", source_path,
        "-vn",                     # 不要影像
        "-ac", str(channels),      # 聲道數
        "-ar", str(sample_rate),   # 取樣率
        "-c:a", "pcm_s16le",
        target_path,
    ])


def has_video_stream(file_path):
    """
    檔案裡有沒有「真的影片畫面」（MV）。
    mp3 裡的專輯封面也算一種畫面（attached pic），那個不算。
    """
    command = [get_ffmpeg_path(), "-hide_banner", "-i", file_path]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
    # 只給 -i 不給輸出檔，ffmpeg 會印出檔案資訊後結束（會回報錯誤，這是正常的）
    result = subprocess.run(command, capture_output=True, creationflags=flags)
    info = result.stderr.decode("utf-8", errors="replace")
    for line in info.splitlines():
        if "Video:" in line and "attached pic" not in line:
            return True
    return False


def get_duration(audio_path):
    """取得音訊長度（秒）"""
    info = sf.info(audio_path)
    return info.frames / info.samplerate


def save_flac(path, audio, sample_rate):
    """
    存成 FLAC（無失真壓縮，比 WAV 小一半，瀏覽器也能播放）。
    audio 的形狀是 (聲道, 取樣點)
    """
    audio = np.clip(audio, -1.0, 1.0)
    sf.write(path, audio.T, sample_rate, subtype="PCM_16", format="FLAC")


def read_tags(file_path):
    """讀取歌曲檔案裡的標題和歌手（沒有就回傳空字串）"""
    title = ""
    artist = ""
    try:
        from mutagen import File
        audio = File(file_path, easy=True)
        if audio is not None and audio.tags is not None:
            if "title" in audio.tags:
                title = audio.tags["title"][0]
            if "artist" in audio.tags:
                artist = audio.tags["artist"][0]
    except Exception as error:
        print("讀取標籤失敗：", error)
    return title, artist


def extract_cover(file_path, output_path):
    """把歌曲檔案裡內嵌的封面圖片存出來，成功回傳 True"""
    try:
        from mutagen import File
        audio = File(file_path)
        if audio is None:
            return False

        image_data = None

        # MP3 的封面放在 APIC 標籤
        if audio.tags is not None:
            for key in audio.tags.keys():
                if str(key).startswith("APIC"):
                    image_data = audio.tags[key].data
                    break

        # FLAC 的封面
        if image_data is None and hasattr(audio, "pictures") and audio.pictures:
            image_data = audio.pictures[0].data

        # M4A 的封面
        if image_data is None and audio.tags is not None and "covr" in audio.tags:
            image_data = bytes(audio.tags["covr"][0])

        if image_data is None:
            return False

        with open(output_path, "wb") as f:
            f.write(image_data)
        return True
    except Exception as error:
        print("讀取封面失敗：", error)
        return False
