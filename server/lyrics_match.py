"""
一份歌詞跟這首歌（這支影片）的歌聲對不對得上。「編輯歌詞」搜尋時，在每個版本旁邊標出來，讓你知道該選哪一個。

回傳：
  shift      程式會自動把整首移幾秒（跟字幕用的同一套：lyrics_builder.estimate_shift）
  silent     移完之後，有幾句放在「沒人在唱」的地方（那一句的時間內，原唱幾乎沒聲音）
  silent_at  第一句沒人唱的時間（秒）
  lines      有時間的句數
例如：專輯版的歌詞拿來配 MV，前奏常常會有幾句「歌詞跳出來了卻沒人唱」。
"""
from server import lyrics_fit
from server.lrc_parser import parse_lrc
from server.lyrics_builder import estimate_shift

SILENT_RATIO = 0.2   # 一句的時間內，有人唱的時間不到兩成 → 算放在沒人唱的地方
LINE_WINDOW = 4.0    # 每一句只看開頭之後幾秒（不超過下一句）
MIN_WINDOW = 0.3     # 兩句擠在一起時，至少看這麼久


def video_lines(lrc_text, offset_seconds, shift):
    """這份歌詞每一句放在影片的第幾秒：[(時間, 字), ...]（多份歌詞互相比對用）"""
    lines = []
    for line in parse_lrc(lrc_text)["lines"]:
        if line["text"] != "":
            lines.append((line["time"] + offset_seconds + shift, line["text"]))
    return lines


def evaluate(lrc_text, notes, duration, offset_seconds):
    """回傳這份歌詞的比對結果；沒有時間軸、或這首歌還沒有音符，回傳 None"""
    parsed = parse_lrc(lrc_text)
    if not parsed["synced"] or len(notes) == 0 or not duration:
        return None
    raw = parsed["lines"]
    shift = estimate_shift(raw, notes, offset_seconds, duration)
    prefix = lyrics_fit.voiced_prefix(notes, duration)
    cells = len(prefix) - 1

    silent_times = []
    count = 0
    for index in range(len(raw)):
        line = raw[index]
        if line["text"] == "":
            continue
        count += 1
        start = line["time"] + offset_seconds + shift
        end = start + LINE_WINDOW
        if index + 1 < len(raw):
            end = min(end, raw[index + 1]["time"] + offset_seconds + shift)
        end = max(end, start + MIN_WINDOW)
        first = max(0, int(start / lyrics_fit.FIT_STEP))
        last = min(cells, int(end / lyrics_fit.FIT_STEP))
        if last <= first:
            continue
        voiced = (prefix[last] - prefix[first]) / (last - first)
        if voiced < SILENT_RATIO:
            silent_times.append(round(start, 2))

    silent_at = None
    if len(silent_times) > 0:
        silent_at = silent_times[0]
    return {"shift": shift, "silent": len(silent_times), "silent_at": silent_at, "lines": count}
