"""
只重新整理音符、補人聲音量，再重做字幕，很快（一首一兩秒），不用重新分析音高。

什麼時候用：
  改了 server\\pitch_analyzer.py 最後的音符整理規則（例如 drop_stray_notes：拿掉孤零零的小點），
  或以前的歌還沒有「人聲音量」（pitch.json 的 loudness，字幕判斷句尾小聲的尾巴用）之後，
  讓以前加的歌也用新規則。音高曲線、瀏覽器的耳朵（heard）、你修過的譜（chart.json）、分數都不會變。

執行方式（在專案資料夾底下，start.bat 開著也沒關係）：
  .venv\\Scripts\\python tools\\update_notes.py
"""
import os
import sys

# 讓這個程式找得到 server 資料夾
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import pitch_analyzer, song_store  # noqa: E402
from server.song_processor import rebuild_lyrics  # noqa: E402


def update(meta):
    folder = song_store.song_dir(meta["id"])
    pitch_path = os.path.join(folder, "pitch.json")
    if not os.path.isfile(pitch_path):
        print("  沒有 pitch.json，跳過")
        return
    pitch = song_store.read_json(pitch_path)
    changes = []

    before = len(pitch["notes"])
    pitch["notes"] = pitch_analyzer.drop_stray_notes(pitch["notes"])
    removed = before - len(pitch["notes"])
    if removed > 0:
        changes.append("拿掉 " + str(removed) + " 個小點")

    if not pitch.get("loudness"):
        # 量的檔案要跟寫音符時一樣（人聲，或是人聲分離失敗時的原曲）
        audio_path = os.path.join(folder, "vocals.flac")
        if meta.get("pitch_source") == "original":
            audio_path = os.path.join(folder, meta.get("original_file", ""))
        if os.path.isfile(audio_path):
            pitch["loudness"] = pitch_analyzer.measure_loudness(audio_path, folder, len(pitch["contour"]))
            changes.append("補上人聲音量")
        else:
            print("  找不到音檔，沒辦法量音量")

    if len(changes) == 0:
        print("  不用改")
        return
    song_store.write_json(pitch_path, pitch)
    rebuild_lyrics(meta["id"])   # 字幕的時間是照音符、音量算的，跟著重做
    print("  " + "、".join(changes) + "，字幕已重做")


def main():
    for meta in song_store.list_songs():
        if meta.get("status") != "ready":
            continue
        print(meta["title"])
        update(meta)
    print("全部完成。")


main()
