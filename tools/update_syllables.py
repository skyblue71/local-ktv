"""
讓以前加的歌也「認音節」：用 MMS 聽每一首的人聲（存成 mms_emission.npy），再重新做字幕。
字幕每個字的填色時間會改用 MMS 算；歌詞、偏移、裁切、評分範圍都不會變。

什麼時候用：
  第一次裝好 MMS 模型之後，或以後換了認音節的方法，讓舊的歌也套用。
  一首大約幾秒（要用顯示卡）。最好先關掉 start.bat（避免同時有新歌在處理，顯示卡記憶體不夠）。

執行方式（在專案資料夾底下）：
  .venv\\Scripts\\python tools\\update_syllables.py
"""
import os
import sys
import time

# 讓這個程式找得到 server 資料夾
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import song_store, syllable_model  # noqa: E402
from server.song_processor import rebuild_lyrics  # noqa: E402


def update(meta):
    folder = song_store.song_dir(meta["id"])
    vocals_path = os.path.join(folder, "vocals.flac")
    if meta.get("pitch_source") != "vocals" or not os.path.isfile(vocals_path):
        print("  沒有分出人聲，跳過（字幕照音符分）")
        return
    began = time.time()
    syllable_model.save_emission(folder, vocals_path)
    lyrics = rebuild_lyrics(meta["id"])
    used = 0
    total = 0
    if lyrics is not None and lyrics.get("synced"):
        for line in lyrics["lines"]:
            total += 1
            if line.get("mms"):
                used += 1
    print("  完成（%.1f 秒）：%d/%d 句用 MMS 算填色" % (time.time() - began, used, total))


def main():
    if not syllable_model.is_available():
        print("電腦裡沒有 MMS 模型，請先按 update.bat（會問你要不要下載）")
        sys.exit(1)
    for meta in song_store.list_songs():
        if meta.get("status") != "ready":
            continue
        print(meta["title"])
        update(meta)
    print("全部完成。")


main()
