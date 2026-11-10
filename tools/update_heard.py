"""
只重新產生「瀏覽器的耳朵」（pitch.json 裡的 heard），很快（一首幾秒）。

什麼時候用：
  改了網頁的音高偵測（web\\js\\audio\\pitch-worklet.js）和 server\\browser_ear.py 之後，
  讓以前加的歌也用新的偵測方法重新聽一次。音符、字幕都不會變。

執行方式（在專案資料夾底下，start.bat 開著也沒關係）：
  .venv\\Scripts\\python tools\\update_heard.py
"""
import os
import sys

# 讓這個程式找得到 server 資料夾
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import browser_ear, song_store  # noqa: E402


def update(meta):
    folder = song_store.song_dir(meta["id"])
    pitch_path = os.path.join(folder, "pitch.json")
    if not os.path.isfile(pitch_path):
        print("  沒有 pitch.json，跳過")
        return
    # 聽的檔案要跟寫音符時一樣（人聲，或是人聲分離失敗時的原曲）
    audio_path = os.path.join(folder, "vocals.flac")
    if meta.get("pitch_source") == "original":
        audio_path = os.path.join(folder, meta.get("original_file", ""))
    if not os.path.isfile(audio_path):
        print("  找不到音檔，跳過")
        return

    pitch = song_store.read_json(pitch_path)
    frame_count = len(pitch["contour"])
    pitch["heard"] = browser_ear.listen(audio_path, folder, pitch["tuning"], frame_count)
    song_store.write_json(pitch_path, pitch)
    heard_frames = 0
    for value in pitch["heard"]:
        if value != 0:
            heard_frames += 1
    print("  完成：聽得到 " + str(heard_frames) + " 格（共 " + str(frame_count) + " 格）")


def main():
    for meta in song_store.list_songs():
        if meta.get("status") != "ready":
            continue
        print(meta["title"])
        update(meta)
    print("全部完成。")


main()
