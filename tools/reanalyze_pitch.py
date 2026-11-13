"""
重新分析音高：已經加進來的歌，用新的設定重新寫音符（不用重新去人聲，很快）。

什麼時候用：
  程式更新了音高分析的設定（例如 pitch_analyzer.py 的 CONFIDENCE_LIMIT），
  想讓以前加的歌也套用新設定的時候。

做的事（每一首歌）：
  1. 用 AI 分離出來的人聲（vocals.flac）重新分析音高 → 寫成新的 pitch.json
     （人聲找不到旋律的話，跟加歌時一樣改用原曲）
  2. 重新產生字幕（lyrics.json），因為字幕的時間是照音符分配的

執行方式（在專案資料夾底下，先把 start.bat 關掉）：
  .venv\\Scripts\\python tools\\reanalyze_pitch.py
"""
import os
import sys

# 讓這個程式找得到 server 資料夾
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import pitch_analyzer, song_store  # noqa: E402
from server.song_processor import rebuild_lyrics  # noqa: E402

# 人聲音軌少於這麼多個音符，就當作分離失敗，改用原曲（跟 song_processor.py 一樣）
MIN_NOTES = 10


def reanalyze(meta):
    song_id = meta["id"]
    folder = song_store.song_dir(song_id)
    vocals_path = os.path.join(folder, "vocals.flac")
    original_path = os.path.join(folder, meta.get("original_file", ""))

    pitch = None
    source = "vocals"
    if meta.get("has_vocals") and os.path.exists(vocals_path):
        pitch = pitch_analyzer.analyze(vocals_path, folder)
        if len(pitch["notes"]) < MIN_NOTES:
            pitch = None
    if pitch is None:
        if not os.path.isfile(original_path):
            print("  找不到人聲也找不到原曲，跳過")
            return
        pitch = pitch_analyzer.analyze(original_path, folder)
        source = "original"

    song_store.write_json(os.path.join(folder, "pitch.json"), pitch)
    song_store.update_meta(song_id, {"pitch_source": source})
    rebuild_lyrics(song_id)
    print("  完成：" + str(len(pitch["notes"])) + " 個音符（來源：" + source + "）")


def main():
    for meta in song_store.list_songs():
        if meta.get("status") != "ready":
            continue
        print(meta["title"])
        reanalyze(meta)
    print("全部完成。")


main()
