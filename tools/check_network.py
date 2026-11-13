"""
測試：整個程式跑一遍，會不會連到外面的網路？

做法：擋住所有對外網路（只允許連自己這台電腦），然後依序做：
  1. 載入去人聲模型
  2. 開伺服器，讀網頁和每首歌的資料（只讀，不改）
  3. 處理一首歌：轉檔 → AI 去人聲 → 分析音高（用程式自己產生的幾秒測試聲音，結果放暫存資料夾）
  4. 日文、中文、韓文的羅馬音和注音，做字幕
最後印出「想連到外面幾次」。

不會動到你的歌曲，也不會發出聲音。
不測「搜尋歌詞」：那個功能本來就會連到 lrclib.net。
執行方法：雙擊專案資料夾裡的「檢查連網.bat」
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request

# 讓這個程式找得到 tools 和 server 資料夾
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.dirname(TOOLS_DIR))

import network_guard  # noqa: E402

# 擋住網路（要在載入其他程式之前）
network_guard.start()

import uvicorn  # noqa: E402

from server import audio_tools, pitch_analyzer, separator  # noqa: E402
from server.lyrics_builder import build_lyrics  # noqa: E402
from server.main import app  # noqa: E402
from server.romanizer import tokenize_line  # noqa: E402

TEST_PORT = 8765   # 跟平常的 8000 不一樣，開著卡拉OK也可以測


def make_test_sound(path):
    """產生幾秒的測試聲音（幾個連著的音），存成 WAV。只是讓「處理一首歌」有東西可以處理"""
    import numpy as np
    import soundfile as sf

    sample_rate = 44100
    pieces = []
    for pitch in [60, 62, 64, 65, 67, 65, 64, 62]:        # Do Re Mi Fa Sol Fa Mi Re，每個音 1 秒
        hz = 440.0 * 2 ** ((pitch - 69) / 12)
        time = np.arange(sample_rate) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * hz * time) + 0.1 * np.sin(2 * np.pi * hz * 2 * time)
        pieces.append(tone)
    sound = np.concatenate(pieces).astype("float32")
    sf.write(path, np.stack([sound, sound], axis=1), sample_rate)


def test_load_model():
    print()
    print("【1】載入去人聲模型…")
    separator.load_model()
    print("    成功（Mel-Band RoFormer）")


def read_page(path):
    """跟自己的伺服器要一個網頁，回傳內容"""
    url = "http://127.0.0.1:" + str(TEST_PORT) + path
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def test_server():
    print()
    print("【2】開伺服器，讀網頁和歌曲資料…")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 等伺服器準備好（最多 10 秒）
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)

    read_page("/")
    print("    首頁 OK")
    songs = json.loads(read_page("/api/songs"))
    for song in songs:
        song_url = "/api/songs/" + song["id"]
        for part in ["", "/pitch", "/lyrics", "/scores", "/audio/instrumental"]:
            try:
                read_page(song_url + part)
            except Exception:
                pass   # 有些歌沒有歌詞，讀不到是正常的
        print("    讀完：" + song["title"])

    server.should_exit = True
    thread.join(timeout=10)


def test_process_song(work_folder):
    print()
    print("【3】處理一首歌（轉檔 → AI 去人聲 → 分析音高）…")
    test_sound = os.path.join(work_folder, "test_sound.wav")
    make_test_sound(test_sound)

    wav_path = os.path.join(work_folder, "work.wav")
    audio_tools.convert_audio(test_sound, wav_path, 44100, 2)
    print("    轉檔 OK")

    vocals_path = os.path.join(work_folder, "vocals.flac")
    instrumental_path = os.path.join(work_folder, "instrumental.flac")
    separator.separate_vocals(wav_path, vocals_path, instrumental_path)
    print("    AI 去人聲 OK")

    pitch = pitch_analyzer.analyze(wav_path, work_folder)
    print("    分析音高 OK，找到 " + str(len(pitch["notes"])) + " 個音符")
    return pitch["notes"]


def test_lyrics(notes):
    print()
    print("【4】羅馬音、注音、字幕…")
    samples = [
        ("桜の花が咲いている", "ja"),
        ("今天天氣很好", "zh"),
        ("사랑해요", "ko"),
    ]
    for text, language in samples:
        tokens = tokenize_line(text, language)
        roma_list = []
        for token in tokens:
            roma_list.append(token.get("roma", ""))
        print("    " + text + " → " + " ".join(roma_list))

    lrc_text = "[00:01.00]春が来た\n[00:05.00]花が咲いた\n"
    lyrics = build_lyrics(lrc_text, notes, 20, 0)
    print("    字幕 OK，共 " + str(len(lyrics["lines"])) + " 句")


def main():
    work_folder = tempfile.mkdtemp(prefix="karaoke_test_")
    try:
        test_load_model()
        test_server()
        notes = test_process_song(work_folder)
        test_lyrics(notes)
    finally:
        shutil.rmtree(work_folder, ignore_errors=True)   # 刪掉暫存檔

    no_network = network_guard.print_report()
    print()
    if no_network:
        print("【通過】整個流程跑完，完全沒有連到外面。")
    else:
        print("【沒通過】上面列出的就是想連到外面的地方。")


main()
