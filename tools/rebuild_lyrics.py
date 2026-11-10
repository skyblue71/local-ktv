"""
只重新產生字幕（每首歌的 lyrics.json），很快（全部幾秒）。

什麼時候用：
  改了字幕的時間算法（server\\lyrics_builder.py）或假名讀音（server\\romanizer.py）之後，
  讓以前加的歌也用新的算法重做一次。歌詞文字（lyrics.lrc）、音符、分數都不會變。

執行方式（在專案資料夾底下，start.bat 開著也沒關係）：
  .venv\\Scripts\\python tools\\rebuild_lyrics.py
"""
import os
import sys

# 讓這個程式找得到 server 資料夾
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import song_store  # noqa: E402
from server.song_processor import rebuild_lyrics  # noqa: E402


def main():
    for meta in song_store.list_songs():
        if meta.get("status") != "ready":
            continue
        print(meta["title"])
        lyrics = rebuild_lyrics(meta["id"])
        if lyrics is None:
            print("  沒有歌詞，跳過")
        elif not lyrics["synced"]:
            print("  歌詞沒有時間軸（要用點按同步），只更新了讀音")
        else:
            text = "  完成：" + str(len(lyrics["lines"])) + " 句"
            mms_lines = 0
            for line in lyrics["lines"]:
                if line.get("mms"):
                    mms_lines += 1
            if lyrics.get("syllables") == "mms":
                text += "，" + str(mms_lines) + " 句用認音節（MMS）算填色"
            shift = lyrics.get("auto_shift", 0)
            if abs(shift) >= 0.1:
                text += "（歌詞整首自動移了 %+.2f 秒）" % shift
            print(text)
    print("全部完成。")


main()
