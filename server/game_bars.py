"""
照唱歌畫面的算法算出評分條（Python 版，健檢工具用：tools\\check_songs.py）。

唱歌畫面的做法（web\\js\\game 資料夾）：
  1. quietParts.js 的 applyQuietSetting：照你的設定（清掉小聲雜音 quietDb）挑出要清的段落，句尾清掉的那一句提早結束
  2. lyricNotes.js 的 notesInLyrics：只留字在唱的時間（每個字開始～結束）裡的部分，落在要清的段落裡的部分剪掉
  3. scorer.js 的 isUnheardNote：瀏覽器的耳朵連原唱都聽不太到的音，不顯示
  4. trimRange.js 的 notesInRange：只留裁切範圍裡的
  （syllableBars.js 照字切開評分條，只是把一條切成幾條，健檢不用）
  你修過譜（chart.json）的話，遊戲直接用你的譜。

用到的數字**直接從那幾個 JS 檔讀**，不在這裡另外寫一份，改了 JS 這裡也會跟著變。
"""
import os
import re

WEB_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")


def read_js_number(relative_path, name):
    """從 JS 檔讀「const 名字 = 數字;」或設定預設值「名字: 數字,」"""
    with open(os.path.join(WEB_JS, relative_path), encoding="utf8") as file:
        text = file.read()
    found = re.search(r"const\s+" + name + r"\s*=\s*([0-9.]+)", text)
    if found is None:
        found = re.search(r"\b" + name + r"\s*:\s*([0-9.]+)", text)
    if found is None:
        raise ValueError(relative_path + " 裡找不到 " + name)
    return float(found.group(1))


SHORTEST = read_js_number(os.path.join("game", "lyricNotes.js"), "SHORTEST")
OLD_FORMAT_DB = read_js_number(os.path.join("game", "quietParts.js"), "OLD_FORMAT_DB")
UNHEARD_LIMIT = read_js_number(os.path.join("game", "scorer.js"), "UNHEARD_LIMIT")
CONTOUR_HOP = read_js_number(os.path.join("game", "scorer.js"), "CONTOUR_HOP")
DEFAULT_QUIET_DB = read_js_number("settings.js", "quietDb")


def read_part(part):
    """quiet 的一段整理成同一種樣子（舊的歌存的是 [開始, 結束]）"""
    if isinstance(part, list):
        return {"s": part[0], "e": part[1], "db": OLD_FORMAT_DB}
    return part


def end_line_at(line, time):
    """這一句提早在 time 結束（跟 quietParts.js 的 endLineAt 一樣）"""
    tokens = []
    for token in line.get("tokens", []):
        copy = dict(token)
        if copy["end"] > time:
            copy["end"] = max(copy["start"], time)
        if copy["start"] > time:
            copy["start"] = copy["end"]
        tokens.append(copy)
    new_line = dict(line)
    new_line["end"] = min(line["end"], max(line["start"] + 0.5, time))
    new_line["tokens"] = tokens
    return new_line


def apply_quiet_setting(lyrics, quiet_db):
    """跟 quietParts.js 的 applyQuietSetting 一樣：回傳 (整理好的句子, 要清掉的段落)"""
    ranges = []
    cut_at = {}
    if quiet_db > 0:
        for raw in lyrics.get("quiet", []):
            part = read_part(raw)
            if part["db"] < quiet_db:
                continue
            ranges.append((part["s"], part["e"]))
            if "line" in part and "cut" in part:
                if part["line"] not in cut_at or part["cut"] < cut_at[part["line"]]:
                    cut_at[part["line"]] = part["cut"]
    lines = []
    for index in range(len(lyrics["lines"])):
        line = lyrics["lines"][index]
        if index in cut_at:
            lines.append(end_line_at(line, cut_at[index]))
        else:
            lines.append(line)
    return lines, ranges


def median_of(values):
    """中位數（跟 quietParts.js 的 medianOf 一樣：排好後取中間那個）"""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def quiet_stretches(lines, notes, loudness, quiet_db):
    """
    跟 quietParts.js 的 quietStretches 一樣：句子裡面「小聲的那一段時間」（字和字中間的回音、換氣）。
    每一句：這一句的歌聲 = 句子裡的音符每一格音量的中位數；
    連續比它小 quiet_db 以上、而且長到 SHORTEST（最短的評分條）以上的一段 → 要清掉。
    只剪那一段時間，不是整條評分條：真的在唱的長音只會少掉變小聲的尾巴。
    """
    ranges = []
    if quiet_db <= 0 or not loudness:
        return ranges
    for line in lines:
        first = max(0, round(line["start"] / CONTOUR_HOP))
        last = min(len(loudness), round(line["end"] / CONTOUR_HOP))
        sung = []
        for note in notes:
            if note["e"] <= line["start"] or note["s"] >= line["end"]:
                continue
            note_first = max(first, round(note["s"] / CONTOUR_HOP))
            note_last = min(last, round(note["e"] / CONTOUR_HOP))
            sung.extend(loudness[note_first:note_last])
        if len(sung) == 0:
            continue
        limit = median_of(sung) - quiet_db
        start = None
        for index in range(first, last + 1):
            quiet = index < last and loudness[index] <= limit
            if quiet and start is None:
                start = index
            if not quiet and start is not None:
                if (index - start) * CONTOUR_HOP >= SHORTEST:
                    ranges.append((start * CONTOUR_HOP, index * CONTOUR_HOP))
                start = None
    return ranges


def fill_missed(notes, pitch, lines, quiet_db):
    """
    跟 twoEars.js 的 fillMissed 一樣：字正在唱的時間裡，AI 沒寫音符、聲音不是小聲雜音、
    瀏覽器的耳朵一半以上聽得到、長到 SHORTEST 以上、緊接著 AI 寫的音符 → 補一個音符。
    回傳補好的音符清單（不改原本的）
    """
    heard = pitch.get("heard")
    loudness = pitch.get("loudness")
    if not notes or not heard or not loudness:
        return notes
    size = min(len(heard), len(loudness))
    noted = [False] * size
    sung = []
    starts_at = {}
    ends_at = {}
    for note in notes:
        first = max(0, js_round(note["s"] / CONTOUR_HOP))
        last = min(size, js_round(note["e"] / CONTOUR_HOP))
        for index in range(first, last):
            noted[index] = True
            sung.append(loudness[index])
        starts_at[first] = note
        ends_at[last] = note
    if len(sung) == 0:
        return notes
    sung.sort()
    limit = float("-inf")
    if quiet_db > 0:
        limit = sung[len(sung) // 2] - quiet_db

    inside = [False] * size
    for line in lines:
        for token in line.get("tokens", []):
            if token["syl"] > 0 and token["end"] > token["start"]:
                first = max(0, js_round(token["start"] / CONTOUR_HOP))
                last = min(size, js_round(token["end"] / CONTOUR_HOP))
                for index in range(first, last):
                    inside[index] = True

    added = []
    begin = None
    for index in range(size + 1):
        is_open = index < size and inside[index] and not noted[index] and loudness[index] >= limit
        if is_open and begin is None:
            begin = index
        if not is_open and begin is not None:
            start, end = begin, index
            begin = None
            if (end - start) * CONTOUR_HOP < SHORTEST:
                continue
            values = [heard[k] for k in range(start, end) if heard[k] != 0]
            if len(values) < (end - start) * 0.5:
                continue
            neighbor = ends_at.get(start) or starts_at.get(end)
            if neighbor is None:
                continue
            values.sort()
            pitch_value = js_round(values[len(values) // 2] / 10)
            pitch_value -= 12 * js_round((pitch_value - neighbor["p"]) / 12)
            added.append({"s": start * CONTOUR_HOP, "e": end * CONTOUR_HOP, "p": pitch_value})
    if len(added) == 0:
        return notes
    # 補的那段跟旁邊連著、音高又一樣：接成同一條
    result = []
    for note in sorted(list(notes) + added, key=lambda note: note["s"]):
        if result and result[-1]["p"] == note["p"] and abs(note["s"] - result[-1]["e"]) < 0.005:
            result[-1] = dict(result[-1], e=note["e"])
        else:
            result.append(note)
    return result


def js_round(value):
    """跟 JavaScript 的 Math.round 一樣（.5 往上；Python 的 round 是四捨六入五成雙，會差一格）"""
    import math
    return math.floor(value + 0.5)


def word_ranges(lines):
    """每個字的時間 [開始, 結束]（標點不算），重疊、連在一起的合成一段（跟 lyricNotes.js 的 wordRanges 一樣）"""
    ranges = []
    for line in lines:
        for token in line.get("tokens", []):
            if token["syl"] > 0 and token["end"] > token["start"]:
                ranges.append([token["start"], token["end"]])
    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def cut_out_quiet(start, end, quiet):
    """跟 lyricNotes.js 的 cutOutQuiet 一樣：落在要清的段落裡的部分剪掉"""
    pieces = [(start, end)]
    for range_start, range_end in quiet:
        kept = []
        for piece_start, piece_end in pieces:
            if piece_end <= range_start or piece_start >= range_end:
                kept.append((piece_start, piece_end))
                continue
            if piece_start < range_start:
                kept.append((piece_start, range_start))
            if piece_end > range_end:
                kept.append((range_end, piece_end))
        pieces = kept
    return pieces


def is_unheard(heard, start, end):
    """跟 scorer.js 的 isUnheardNote 一樣"""
    if not heard:
        return False
    first = max(0, round(start / CONTOUR_HOP))
    last = min(len(heard), round(end / CONTOUR_HOP))
    voiced = 0
    for index in range(first, last):
        if heard[index] != 0:
            voiced += 1
    total = max(1, round((end - start) / CONTOUR_HOP))
    return voiced / total < UNHEARD_LIMIT


def trim_range(meta):
    """裁切範圍（跟 trimRange.js 一樣）"""
    start = float(meta.get("trim_start") or 0)
    duration = float(meta.get("duration") or 0)
    end = float(meta.get("trim_end") or 0)
    if not (0 < end < duration):
        end = duration if duration > 0 else 1e9
    return start, end


def game_bars(lyrics, pitch, meta, chart_notes=None, quiet_db=None):
    """
    回傳 (評分條 [{"s", "e", "p"}, ...], 整理好的句子)：跟唱歌畫面上看到的一樣（照字切開那一步不做）
    """
    if quiet_db is None:
        quiet_db = DEFAULT_QUIET_DB
    lines, quiet = apply_quiet_setting(lyrics, quiet_db)
    quiet = list(quiet) + quiet_stretches(lines, pitch.get("notes", []), pitch.get("loudness"), quiet_db)
    trim_start, trim_end = trim_range(meta)

    if chart_notes:
        candidates = [dict(note) for note in chart_notes]
    else:
        candidates = []
        ranges = word_ranges(lines)
        for note in fill_missed(pitch.get("notes", []), pitch, lines, quiet_db):
            for start, end in cut_out_quiet(note["s"], note["e"], quiet):
                for range_start, range_end in ranges:
                    kept_start = max(start, range_start)
                    kept_end = min(end, range_end)
                    if kept_end <= kept_start:
                        continue
                    was_cut = kept_start != note["s"] or kept_end != note["e"]
                    if was_cut and kept_end - kept_start < SHORTEST:
                        continue   # 剪剩很短的碎片不要
                    candidates.append({"s": kept_start, "e": kept_end, "p": note["p"]})
        heard = pitch.get("heard")
        candidates = [bar for bar in candidates if not is_unheard(heard, bar["s"], bar["e"])]

    bars = []
    for bar in candidates:
        inside = min(bar["e"], trim_end) - max(bar["s"], trim_start)
        if inside >= (bar["e"] - bar["s"]) * 0.5:
            bars.append(bar)
    return bars, lines
