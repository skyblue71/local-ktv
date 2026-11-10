"""
你自己調過的「字的時間」：存在每首歌資料夾的 word_times.json（修譜頁下面那一排字，拖一下就改）。

AI 聽不出來的字（例如拉長的「Wow」）沒有算法救得了，所以讓你自己拖到對的時間。
  有 word_times.json → 做字幕時，你調過的字照你的時間，其他字照舊由程式算
  沒有              → 全部由程式算
評分條只放在字的時間裡，所以字調對了，評分條也會跟著對（你修過譜的歌照你的譜，不會變）。
程式算的結果不會被改到，可以隨時「還原字的時間」（刪掉 word_times.json 就好）。

每一筆：{"line": 這一句的文字, "nth": 同樣文字的第幾句（從 0 開始）, "index": 這一句裡第幾個字（標點不算，從 0 開始）,
         "text": 這個字, "start": 開始秒數, "end": 結束秒數}
用「文字＋第幾句」認句子：歌詞重新對齊、句子時間變了也認得出來；歌詞文字改了，對不上的那幾筆就不會用。
"""
import os

from server import song_store

WORDS_FILE = "word_times.json"
MAX_WORDS = 5000          # 一首歌最多幾筆（擋掉奇怪的資料）
MIN_LENGTH = 0.05         # 一個字最短幾秒
MIN_LINE_SECONDS = 0.5    # 一句至少出現幾秒（跟 lyrics_builder 一樣：太快看不到）


def words_path(song_id):
    return song_store.song_file(song_id, WORDS_FILE)


def get_words(song_id):
    """回傳你調過的字（清單）；沒調過回傳空清單"""
    data = song_store.read_json(words_path(song_id))
    if data is None:
        return []
    return data.get("words", [])


def clean_words(words, duration):
    """檢查、整理送來的資料。不合理就丟出 ValueError（訊息會給使用者看）"""
    if len(words) > MAX_WORDS:
        raise ValueError("調過的字太多了（最多 %d 個）" % MAX_WORDS)
    result = []
    seen = {}
    for word in words:
        start = round(float(word["start"]), 3)
        end = round(float(word["end"]), 3)
        if start < 0 or end - start < MIN_LENGTH:
            raise ValueError("有字的時間不對")
        if duration and start > duration:
            raise ValueError("有字超過歌曲長度")
        cleaned = {"line": str(word["line"]), "nth": int(word["nth"]), "index": int(word["index"]),
                   "text": str(word["text"]), "start": start, "end": end}
        key = (cleaned["line"], cleaned["nth"], cleaned["index"])
        if key in seen:
            result[seen[key]] = cleaned   # 同一個字送了兩次：用後面那一次
        else:
            seen[key] = len(result)
            result.append(cleaned)
    return result


def save_words(song_id, words):
    meta = song_store.get_meta(song_id)
    cleaned = clean_words(words, meta.get("duration", 0))
    if len(cleaned) == 0:
        delete_words(song_id)
        return cleaned
    song_store.write_json(words_path(song_id), {"words": cleaned})
    return cleaned


def delete_words(song_id):
    path = words_path(song_id)
    if os.path.exists(path):
        os.remove(path)


def sung_tokens(line):
    """這一句會唱的字（標點不算）"""
    return [token for token in line.get("tokens", []) if token.get("syl", 0) > 0]


def apply_words(lyrics, words):
    """
    把你調過的字套到字幕上（直接改 lyrics）。回傳套用了幾個字。
      1. 你調過的字：照你的開始、結束，記上 "manual": True；它的拍子（beats）是照舊時間算的，拿掉
      2. 同一句裡其他的字不能跟它疊在一起：前面的字最晚到它開始、後面的字最早從它結束開始
      3. 句子 = 第一個字開始～最後一個字唱完
      4. 有調過字的句子，句尾「小聲雜音」的記錄拿掉（你調的就算，不要再被自動剪短）
    """
    if not words or not lyrics or not lyrics.get("synced"):
        return 0
    lines = lyrics.get("lines", [])
    # 每一句是「同樣文字的第幾句」
    counts = {}
    where = {}
    for index in range(len(lines)):
        text = lines[index].get("text", "")
        nth = counts.get(text, 0)
        counts[text] = nth + 1
        where[(text, nth)] = index

    applied = 0
    touched = set()
    for word in words:
        line_index = where.get((word["line"], word["nth"]))
        if line_index is None:
            continue
        sung = sung_tokens(lines[line_index])
        if word["index"] < 0 or word["index"] >= len(sung) or sung[word["index"]].get("text") != word["text"]:
            continue
        token = sung[word["index"]]
        token["start"] = word["start"]
        token["end"] = word["end"]
        token["manual"] = True
        for name in ("beats", "beat_x", "beat_roma_x"):
            token.pop(name, None)
        touched.add(line_index)
        applied += 1

    for line_index in touched:
        line = lines[line_index]
        sung = sung_tokens(line)
        for position in range(len(sung)):
            if not sung[position].get("manual"):
                continue
            # 前面沒調過的字：最晚到這個字開始
            for earlier in reversed(sung[:position]):
                if earlier.get("manual"):
                    break
                earlier["end"] = min(earlier["end"], sung[position]["start"])
                earlier["start"] = min(earlier["start"], earlier["end"])
            # 後面沒調過的字：最早從這個字結束開始
            for later in sung[position + 1:]:
                if later.get("manual"):
                    break
                later["start"] = max(later["start"], sung[position]["end"])
                later["end"] = max(later["end"], later["start"])
        # 標點跟著前一個字
        previous_end = None
        for token in line.get("tokens", []):
            if token.get("syl", 0) > 0:
                previous_end = token["end"]
            elif previous_end is not None:
                token["start"] = previous_end
                token["end"] = previous_end
        line["start"] = round(sung[0]["start"], 3)
        line["end"] = round(max(sung[-1]["end"], line["start"] + MIN_LINE_SECONDS), 3)

    if touched and lyrics.get("quiet"):
        kept = []
        for part in lyrics["quiet"]:
            if isinstance(part, dict) and part.get("line") in touched:
                continue
            kept.append(part)
        lyrics["quiet"] = kept
    return applied
