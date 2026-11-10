"""
LRC 歌詞解析。

LRC 是最常見的「有時間軸」歌詞格式，長這樣：
  [00:12.34]春が来た
  [00:18.00]花が咲いた

也支援「逐字時間」的加強版 LRC：
  [00:12.34]<00:12.34>は<00:12.80>る<00:13.20>が
"""
import re

LINE_TIME = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
WORD_TIME = re.compile(r"<(\d+):(\d+(?:\.\d+)?)>")
META_TAG = re.compile(r"^\[([a-zA-Z]+):(.*)\]$")


def to_seconds(minutes, seconds):
    return int(minutes) * 60 + float(seconds)


def parse_word_times(content):
    """
    解析逐字時間，回傳 [(秒數, 文字), ...]；沒有逐字時間就回傳 None
    """
    matches = list(WORD_TIME.finditer(content))
    if len(matches) == 0:
        return None
    words = []
    for index in range(len(matches)):
        match = matches[index]
        time = to_seconds(match.group(1), match.group(2))
        text_start = match.end()
        if index + 1 < len(matches):
            text_end = matches[index + 1].start()
        else:
            text_end = len(content)
        text = content[text_start:text_end]
        if text != "":
            words.append((time, text))
    return words


def parse_lrc(text):
    """
    回傳：
      {
        "synced": True/False（有沒有時間軸）,
        "lines": [{"time": 秒數或 None, "text": 歌詞, "words": 逐字時間或 None}, ...]
      }
    """
    lines = []
    offset_ms = 0
    has_time = False

    # 用記事本存的檔案，開頭可能有一個看不見的字元（BOM），不拿掉的話會跑進第一句的字幕
    text = text.lstrip("﻿")

    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if raw_line == "":
            continue

        # [ti:標題] [ar:歌手] [offset:500] 這類資訊標籤
        meta = META_TAG.match(raw_line)
        if meta and not LINE_TIME.match(raw_line):
            if meta.group(1).lower() == "offset":
                try:
                    offset_ms = int(float(meta.group(2).strip()))
                except ValueError:
                    offset_ms = 0
            continue

        times = LINE_TIME.findall(raw_line)
        content = LINE_TIME.sub("", raw_line)

        if len(times) == 0:
            # 沒有時間的純文字歌詞
            lines.append({"time": None, "text": content.strip(), "words": None})
            continue

        has_time = True
        words = parse_word_times(content)
        clean_text = WORD_TIME.sub("", content).strip()

        # 一行可能有好幾個時間（副歌重複），每個時間各放一行
        for minutes, seconds in times:
            lines.append({
                "time": to_seconds(minutes, seconds) - offset_ms / 1000.0,
                "text": clean_text,
                "words": words,
            })

    if has_time:
        timed_lines = []
        for line in lines:
            if line["time"] is not None:
                timed_lines.append(line)
        timed_lines.sort(key=lambda line: line["time"])
        lines = timed_lines

    return {"synced": has_time, "lines": lines}
