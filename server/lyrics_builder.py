"""
把「LRC 歌詞」+「旋律音符」+「AI 認音節」做成卡拉 OK 字幕資料（lyrics.json）。

LRC 只告訴我們每一句「大概什麼時候開始」，
但卡拉 OK 字幕要知道「每一個字什麼時候唱」，才能做出逐字變色的效果。

做法：
  1. 這份歌詞大概在哪裡：整首固定早／晚（estimate_shift）、MV 插了劇情要整段搬（song_alignment.py）
  2. 每個字從幾秒唱到幾秒：word_timeline.py（整首一次對齊 + 照歌聲修正）
  3. 句子的時間 = 第一個字開始 ～ 最後一個字唱完；評分條也只放在字的時間裡（web\\js\\game\\lyricNotes.js）
  所以字幕、句子、評分條都照同一個時間，不會各算各的。
"""
import re

from server import lyrics_fit, song_alignment, word_timeline
from server.lrc_parser import parse_lrc
from server.romanizer import detect_line_language, detect_song_language, strip_reading_marks, tokenize_line
from server.word_timeline import sung_tokens, total_syllables

# 對唱標記：句子前面寫「男：」「女：」「合：」（或 M: F: D:、(男)、【女】），字幕會換顏色
#   1 = 男（第一位歌手）、2 = 女（第二位歌手）、3 = 合唱
SINGER_MARKS = {"男": 1, "M": 1, "女": 2, "F": 2, "合": 3, "D": 3}
SINGER_PATTERN = re.compile(r"^\s*(?:[(（【\[]\s*(男|女|合|M|F|D)\s*[)）】\]]|(男|女|合|M|F|D)\s*[:：])\s*")


def split_singer(text):
    """把句子前面的對唱標記拿掉，回傳 (歌手編號, 剩下的歌詞)；沒有標記回傳 (None, 原本的歌詞)"""
    match = SINGER_PATTERN.match(text)
    if match is None:
        return None, text
    mark = match.group(1) or match.group(2)
    return SINGER_MARKS[mark], text[match.end():]


TOGETHER_RATIO = 0.25    # 歌詞檔給一句的時間（到下一句開始）平均每個音節的秒數，不到「這首歌平常」的這麼多倍，就是唱不完：
                         # 這句跟下一句是一起唱的（和聲、翻譯放在同一個時間），兩句一起出現、一起填色
                         # 「平常」= 這首歌每一句的中位數，所以整首都很快的歌（rap、講話一秒 12 個音節）不會被當成一起唱
                         #（28 首實測：分開唱的句子，最快的是那首歌平常的 0.36 倍；
                         #   兩句只差 0.4 秒那種真的一起唱的，大約是平常的 0.1 倍）
# 整首歌詞固定早／晚：網站上的歌詞常常整首都早 1～2 秒（例如翻唱版用了原版的時間）
SHIFT_LOW = -1.5       # 最多往前移幾秒
SHIFT_HIGH = 3.5       # 最多往後移幾秒
SHIFT_STEP = 0.05      # 每次試幾秒
SHIFT_ONSET_GAP = 0.3  # 前面停這麼久才算「開口」
SHIFT_HIT = 0.25       # 歌詞時間 ± 這麼多秒內有人開口，算這句「對上」
SHIFT_MIN_RATE = 0.3   # 移完至少要有三成的句子對上
SHIFT_MIN_GAIN = 0.15  # 而且要比不移多對上一成五的句子（至少 3 句），不然就不移
# 差一大段（例如 MV 的前奏比歌詞網站的版本長 9 秒）：先粗對、再細對
FAR_LOW = -30.0        # 粗對最多往前找幾秒
FAR_HIGH = 60.0        # 粗對最多往後找幾秒
FAR_PEAKS = 3          # 粗對挑幾個候選位置（吻合度最高的幾個，彼此差 3 秒以上）
FAR_MIN = 4.0          # 候選位置離 0 超過這麼多秒才算「差一大段」（近的交給上面的細對）
FAR_FINE = 1.5         # 每個候選位置前後各細對幾秒
# 句子連著唱、開口很少的歌，上面的「開口對上幾句」證據不夠：改看
#「每一句離最近的開口差幾秒」的中位數（大部分句子都差多少）
MEDIAN_MIN_LINES = 8   # 至少要有這麼多句找得到附近的開口
MEDIAN_MIN = 0.5       # 中位數至少差這麼多秒才移（太小的交給整首一次對齊）
MEDIAN_FIT_DROP = 0.01 # 移了之後「有歌詞的地方剛好有人唱」的吻合度（lyrics_fit.py）不能比不移差超過這麼多


def find_onsets(notes, gap):
    """人聲「開口」的時間：前面停頓 gap 秒以上之後，第一個音符開始的時間"""
    starts = []
    previous_end = None
    for note in notes:
        if previous_end is None or note["s"] - previous_end >= gap:
            starts.append(note["s"])
        previous_end = note["e"]
    return starts


def count_hits(line_times, onsets, shift):
    """歌詞每一句往後移 shift 秒時，有幾句的開頭剛好有人開口"""
    hits = 0
    for time in line_times:
        for onset in onsets:
            if abs(onset - (time + shift)) <= SHIFT_HIT:
                hits += 1
                break
    return hits


def best_hits_between(line_times, onsets, low, high):
    """在 low～high 秒之間（每 SHIFT_STEP 秒）試位移，回傳 (最多對上幾句, 那時的位移)；一樣多選移比較少的"""
    best_hits = -1
    best_shift = 0.0
    steps = int(round((high - low) / SHIFT_STEP))
    for k in range(steps + 1):
        shift = round(low + k * SHIFT_STEP, 2)
        hits = count_hits(line_times, onsets, shift)
        if hits > best_hits or (hits == best_hits and abs(shift) < abs(best_shift)):
            best_hits = hits
            best_shift = shift
    return best_hits, best_shift


def median_shift(line_times, onsets):
    """
    每一句找離它最近的開口（SHIFT_LOW～SHIFT_HIGH 秒內），看大部分句子差幾秒（中位數）。
    句數夠、差得夠多（MEDIAN_MIN）才回傳中位數，不然回傳 None（吻合度的檢查在 estimate_shift 裡）
    """
    diffs = []
    for time in line_times:
        best = None
        for onset in onsets:
            diff = onset - time
            if SHIFT_LOW <= diff <= SHIFT_HIGH and (best is None or abs(diff) < abs(best)):
                best = diff
        if best is not None:
            diffs.append(best)
    if len(diffs) < MEDIAN_MIN_LINES:
        return None
    diffs.sort()
    middle = diffs[len(diffs) // 2]
    if len(diffs) % 2 == 0:
        middle = (diffs[len(diffs) // 2 - 1] + diffs[len(diffs) // 2]) / 2
    if abs(middle) < MEDIAN_MIN:
        return None
    return round(middle, 2)


def estimate_shift(raw_lines, notes, offset, duration=0):
    """
    整首歌詞是不是固定早（或晚）了幾秒，回傳要往後移的秒數（不移 = 0）。
    1. 近的（SHIFT_LOW～SHIFT_HIGH）：看哪一種位移讓最多句子的開頭剛好碰到人聲開口
    2. 遠的（FAR_LOW～FAR_HIGH，例如 MV 前奏比歌詞的版本長一大段）：
       先用「有歌詞的地方剛好有人唱」的吻合度（lyrics_fit.py）挑幾個候選位置，
       每個候選位置附近再用開口對上的句數細對
    都要明顯比不移好（多 SHIFT_MIN_GAIN 的句子、至少 3 句，而且至少 SHIFT_MIN_RATE 的句子對上）才移
    """
    line_times = []
    for line in raw_lines:
        if line["text"] != "":
            line_times.append(line["time"] + offset)
    onsets = find_onsets(notes, SHIFT_ONSET_GAP)
    if len(line_times) == 0 or len(onsets) == 0:
        return 0.0
    needed_gain = max(3, SHIFT_MIN_GAIN * len(line_times))
    needed_rate = SHIFT_MIN_RATE * len(line_times)

    stay_hits = count_hits(line_times, onsets, 0.0)
    near_hits, near_shift = best_hits_between(line_times, onsets, SHIFT_LOW, SHIFT_HIGH)
    chosen_shift = 0.0
    if near_hits >= needed_rate and near_hits - stay_hits >= needed_gain:
        chosen_shift = near_shift
    else:
        # 開口對上的證據不夠（句子連著唱）：改看中位數；移了之後吻合度不能變差
        middle = median_shift(line_times, onsets)
        if middle is not None and duration:
            shifted = []
            for line in raw_lines:
                shifted.append({"time": line["time"] + offset, "text": line["text"]})
            prefix = lyrics_fit.voiced_prefix(notes, duration)
            if lyrics_fit.fit(shifted, prefix, middle) >= lyrics_fit.fit(shifted, prefix, 0.0) - MEDIAN_FIT_DROP:
                chosen_shift = middle

    # 遠的候選：要比「近的最好」再多對上很多句才採用
    shifted_lines = []
    for line in raw_lines:
        shifted_lines.append({"time": line["time"] + offset, "text": line["text"]})
    best_far_hits = max(near_hits, stay_hits)
    for peak in lyrics_fit.best_offsets(shifted_lines, notes, duration, FAR_LOW, FAR_HIGH, FAR_PEAKS, 3.0):
        if abs(peak) <= FAR_MIN:
            continue
        hits, shift = best_hits_between(line_times, onsets, peak - FAR_FINE, peak + FAR_FINE)
        if hits >= needed_rate and hits - best_far_hits >= needed_gain:
            best_far_hits = hits
            chosen_shift = shift
    return chosen_shift


def can_pair(raw_lines, syllable_counts, index):
    """第 index 行跟下一行能不能比「時間夠不夠唱」：兩句都有字、都沒有逐字時間（有的話它自己的時間就是準的）"""
    if index + 1 >= len(raw_lines):
        return False
    line = raw_lines[index]
    after = raw_lines[index + 1]
    both_text = line["text"] != "" and after["text"] != ""
    no_words = not line["words"] and not after["words"]
    return both_text and no_words and syllable_counts[index] > 0


def fastest_syllable(raw_lines, syllable_counts):
    """
    這首歌一個音節最快唱幾秒：比這個還快就是唱不完。
    = 這首歌平常的速度（每一句「到下一句開始的時間 ÷ 音節數」的中位數）× TOGETHER_RATIO。
    沒有句子可以算就回傳 0
    """
    speeds = []
    for index in range(len(raw_lines)):
        if can_pair(raw_lines, syllable_counts, index):
            gap = raw_lines[index + 1]["time"] - raw_lines[index]["time"]
            speeds.append(gap / syllable_counts[index])
    if len(speeds) == 0:
        return 0
    speeds.sort()
    return speeds[len(speeds) // 2] * TOGETHER_RATIO


def find_together(raw_lines, syllable_counts, seconds_per_syllable):
    """
    歌詞檔給一句的時間（到下一句開始）太短、根本唱不完（平均每個音節不到 seconds_per_syllable 秒），
    例如兩句只差 0.4 秒：「[00:21.46] 主唱的句子」「[00:21.89] （和聲）」：
    這句跟下一句是一起唱的（和聲、兩個人一起唱、原文和翻譯放在同一個時間），
    兩句要一起出現、一起填色，不要一句快速閃過去再換下一句。
    畫面上一次只放得下兩句，所以最多兩句一組。
    syllable_counts：每一行有幾個音節；seconds_per_syllable：fastest_syllable 算出來的
    回傳 {第一句是第幾行: 第二句是第幾行, ...}
    """
    together = {}
    index = 0
    while index + 1 < len(raw_lines):
        if can_pair(raw_lines, syllable_counts, index):
            gap = raw_lines[index + 1]["time"] - raw_lines[index]["time"]
            if gap < syllable_counts[index] * seconds_per_syllable:
                together[index] = index + 1
                index += 2
                continue
        index += 1
    return together


def second_to_first(together):
    """把 {第一句: 第二句} 反過來，變成 {第二句: 第一句}"""
    result = {}
    for first in together:
        result[together[first]] = first
    return result


# 句尾斷開的小聲聲音（回音、換氣、子音的尾巴）：
#   這裡只「量」它比歌聲小幾 dB，記在 lyrics.json 的 "quiet"（每段 {s, e, db, line, cut}），不在這裡刪
#   要不要清掉，由你在「設定 → 清掉小聲雜音」決定（web\js\game\quietParts.js；預設在 web\js\settings.js）
#   所以改數字不用重新處理歌曲
#   （句首的不用量：評分條只放在字的時間裡，第一個字開始前的聲音本來就不會有評分條）

def median_loudness(loudness, hop, pieces):
    """這幾段時間（[[開始, 結束], ...]）的音量：每一格 dB 的中位數；沒有資料回傳 None"""
    if not loudness or hop <= 0:
        return None
    values = []
    for start, end in pieces:
        first = max(0, int(round(start / hop)))
        last = min(len(loudness), int(round(end / hop)))
        values.extend(loudness[first:last])
    if len(values) == 0:
        return None
    values.sort()
    return values[len(values) // 2]


def note_runs(notes, start, end):
    """start～end 之間的音符，連著的算一段：[[開始, 結束], ...]（超出範圍的部分切掉）"""
    runs = []
    for note in notes:
        if note["e"] <= start or note["s"] >= end:
            continue
        piece_start = max(note["s"], start)
        piece_end = min(note["e"], end)
        if len(runs) > 0 and piece_start - runs[-1][1] <= 0.005:
            runs[-1][1] = max(runs[-1][1], piece_end)
        else:
            runs.append([piece_start, piece_end])
    return runs


def quiet_tail_parts(tokens, line_end, notes, loudness, hop):
    """
    一句的最後：最後一個字開始之後的音符，照「斷開」分成一段一段，從最後一段往前量：
    這一段比前面唱這個字的聲音小幾 dB。
    要清掉前面那一段，後面的也一定要清掉，所以每一段記的是「它和它後面每一段裡最小的那個」，
    唱歌畫面只要比一個數字就好（設定的數字 ≤ db 就清掉）。
    回傳 [{"s", "e", "db", "cut"}, ...]；cut = 清掉這一段的話，這一句（和最後一個字）結束在哪裡
    （比歌聲還大聲的不記；沒有音量資料就回傳空的）
    """
    sung = sung_tokens(tokens)
    if not loudness or hop <= 0 or len(sung) == 0:
        return []
    runs = note_runs(notes, sung[-1]["start"], line_end)

    parts = []
    smallest = None
    while len(runs) >= 2:
        body = median_loudness(loudness, hop, runs[:-1])
        tail = median_loudness(loudness, hop, runs[-1:])
        if body is None or tail is None:
            break
        if smallest is None or body - tail < smallest:
            smallest = body - tail
        if smallest <= 0:
            break   # 沒有比較小聲：真的在唱，前面的也不用再看
        run = runs.pop()
        parts.append({"s": round(run[0], 3), "e": round(run[1], 3),
                      "db": round(smallest, 1), "cut": round(runs[-1][1], 3)})
    return parts


def assign_times_by_words(tokens, text, words, next_start):
    """加強版 LRC 有逐字時間時，直接用它的時間"""
    # 先算出原文每個字元的時間
    char_times = []
    for index in range(len(words)):
        word_start, word_text = words[index]
        if index + 1 < len(words):
            word_end = words[index + 1][0]
        else:
            word_end = min(next_start, word_start + 2.0)
        length = len(word_text)
        for k in range(length):
            a = word_start + (word_end - word_start) * k / length
            b = word_start + (word_end - word_start) * (k + 1) / length
            char_times.append((a, b))

    position = 0
    for token in tokens:
        found = text.find(token["text"], position)
        if found < 0 or found >= len(char_times):
            found = min(position, len(char_times) - 1)
        last = min(found + len(token["text"]) - 1, len(char_times) - 1)
        token["start"] = round(char_times[found][0], 3)
        token["end"] = round(char_times[last][1], 3)
        position = found + len(token["text"])


def times_from_word_lrc(raw_lines, all_tokens, times, offset, notes, heard, end_time):
    """加強版 LRC（自己就有每個字的時間）：有逐字時間的句子照它；沒有的照音符分（不用 AI 認音節）"""
    rows = []
    for row in range(len(raw_lines)):
        if raw_lines[row]["text"] != "" and len(sung_tokens(all_tokens[row])) > 0:
            rows.append(row)
    pieces = word_timeline.heard_notes(notes, heard)
    for order in range(len(rows)):
        row = rows[order]
        next_start = end_time
        if row + 1 < len(times):
            next_start = times[row + 1]
        line = raw_lines[row]
        if line["words"]:
            words = []
            joined_text = ""
            for word_time, word_text in line["words"]:
                words.append((word_time + offset, word_text))
                joined_text += word_text
            assign_times_by_words(all_tokens[row], joined_text, words, next_start)
        else:
            word_timeline.spread_by_runs(sung_tokens(all_tokens[row]), pieces, times[row],
                                         max(next_start, times[row] + word_timeline.TINY))
    return {}


def build_lyrics(lrc_text, notes, duration, offset_ms=0, auto_align=True, heard=None, hop=0.0, emission=None,
                 loudness=None, show_absent=False):
    """
    auto_align：整首歌詞自動對到歌手真的唱的地方（整首早晚、整段搬家、每一句的位置）；關掉 = 照歌詞檔的時間
    heard：pitch.json 的「瀏覽器的耳朵」資料（哪些音聽得到；沒有也可以）
    emission：認音節的結果（syllable_model.load_emission）；有的話每個字的時間用 MMS 聽，沒有就照音符分
    loudness、hop：pitch.json 的人聲音量（每一格 dB）；句尾斷開的小聲聲音量出小幾 dB，記在 "quiet"（沒有也可以）
    show_absent：這支影片沒唱的句子要不要照樣顯示（預設不顯示；「編輯歌詞」頁可以切換）
    回傳：
      {
        "synced": True/False,
        "lang": 主要語言,
        "lines": [{"start", "end", "text", "lang", "singer", "tokens": [...], "mms"（AI 聽的）, "mms_score"}, ...],
        "song_zero": 歌詞版本的 0:00 在影片第幾秒, "moved_sections": 整段搬家的段落,
        "absent_lines": 影片沒唱的句子 [{"time": 歌詞檔給它的時間, "text": 歌詞}, ...],
        "absent_shown": 那幾句有沒有照樣顯示（show_absent）
      }
    """
    parsed = parse_lrc(lrc_text)
    raw_lines = parsed["lines"]

    all_text = ""
    for line in raw_lines:
        all_text += strip_reading_marks(line["text"]) + "\n"
    song_language = detect_song_language(all_text)

    # 對唱標記：每一行是誰唱的（標記會一直延續到下一個標記出現）
    singer = 0   # 0 = 沒有標記（用預設顏色）
    for line in raw_lines:
        mark, rest = split_singer(line["text"])
        if mark is not None:
            singer = mark
            line["text"] = rest.strip()
        line["singer"] = singer

    # 沒有時間軸：只做羅馬音，時間留給使用者去「點按同步」
    if not parsed["synced"]:
        lines = []
        for line in raw_lines:
            if line["text"] == "":
                continue
            language = detect_line_language(strip_reading_marks(line["text"]), song_language)
            lines.append({"text": strip_reading_marks(line["text"]), "lang": language, "singer": line["singer"],
                          "tokens": tokenize_line(line["text"], language)})
        return {"synced": False, "lang": song_language, "lines": lines}

    offset = offset_ms / 1000.0

    # 每一行的語言、拆好的字（先算好，才知道每一句有幾個音節）
    languages = []
    all_tokens = []
    syllable_counts = []
    for line in raw_lines:
        if line["text"] == "":
            languages.append(song_language)
            all_tokens.append([])
            syllable_counts.append(0)
            continue
        language = detect_line_language(strip_reading_marks(line["text"]), song_language)
        tokens = tokenize_line(line["text"], language)   # text 裡的 {讀音} 標記在這裡處理
        languages.append(language)
        all_tokens.append(tokens)
        syllable_counts.append(total_syllables(tokens))

    # 時間近到唱不完的兩句：一起唱（一起出現、一起填色）
    seconds_per_syllable = fastest_syllable(raw_lines, syllable_counts)
    together = find_together(raw_lines, syllable_counts, seconds_per_syllable)
    first_of = second_to_first(together)

    # 1. 這份歌詞大概在哪裡：歌詞檔的時間＋整體偏移，再自動修正整首早晚、整段搬家
    has_word_times = False
    for line in raw_lines:
        if line["words"]:
            has_word_times = True
    times = []
    for index in range(len(raw_lines)):
        if index in first_of:
            times.append(times[first_of[index]])   # 跟上一句一起唱：同一個時間
        else:
            times.append(raw_lines[index]["time"] + offset)
    auto_shift = 0.0      # 自動判斷的「整首歌詞固定早／晚」（秒）
    moved_sections = []   # 整段搬家的段落
    absent_lines = []     # 這支影片沒唱、拿掉的句子
    song_zero = offset    # 歌詞那個版本的 0:00 落在影片的第幾秒（自動找劇情用）
    if auto_align and not has_word_times and len(notes) > 0:
        auto_shift = estimate_shift(raw_lines, notes, offset, duration)
        for index in range(len(times)):
            times[index] += auto_shift
        song_zero = offset + auto_shift
        # MV 中間插了劇情、影片是剪短的版本 → 整段搬到歌手真的唱的地方；影片沒唱的句子拿掉（song_alignment.py）
        if emission is not None:
            moved_sections, absent_rows = song_alignment.fix_sections(
                raw_lines, all_tokens, times, first_of, syllable_counts, seconds_per_syllable,
                emission, notes, heard, hop, duration)
            first_row = None
            for index in range(len(raw_lines)):
                if raw_lines[index]["text"] != "":
                    first_row = index
                    break
            for section in moved_sections:
                if section["first_row"] == first_row:
                    song_zero += section["move"]   # 第一句整段搬了：歌的開頭也跟著搬
            for row in sorted(absent_rows):
                absent_lines.append({"time": round(times[row], 2), "text": strip_reading_marks(raw_lines[row]["text"])})
                if not show_absent:
                    raw_lines[row]["text"] = ""   # 當成空白行：只標示上一句在這裡結束
                    all_tokens[row] = []

    # 2. 每個字從幾秒唱到幾秒（word_timeline.py）
    end_time = duration
    if not end_time and len(notes) > 0:
        end_time = notes[-1]["e"]
    if has_word_times:
        info = times_from_word_lrc(raw_lines, all_tokens, times, offset, notes, heard, end_time)
    else:
        info = word_timeline.time_lines(raw_lines, all_tokens, times, together, first_of, notes, heard,
                                        emission, end_time, auto_align, loudness, hop)

    # 3. 句子 = 第一個字開始 ～ 最後一個字唱完
    lines = []
    for index in range(len(raw_lines)):
        line = raw_lines[index]
        if line["text"] == "":
            continue   # 空白行只是用來標示「這句結束了」
        tokens = all_tokens[index]
        sung = sung_tokens(tokens)
        if len(sung) == 0:
            continue
        # 標點符號：跟著前一個字（第一個字之前的跟著第一個字）
        previous_end = sung[0]["start"]
        for token in tokens:
            if token["syl"] > 0:
                previous_end = token["end"]
            else:
                token["start"] = previous_end
                token["end"] = previous_end
        line_start = sung[0]["start"]
        line_end = max(sung[-1]["end"], line_start + 0.5)   # 一句至少出現 0.5 秒（太快看不到）
        new_line = {
            "start": round(line_start, 3),
            "end": round(line_end, 3),
            "text": strip_reading_marks(line["text"]),
            "lang": languages[index],
            "singer": line["singer"],
            "tokens": tokens,
        }
        row_info = info.get(index, {})
        if row_info.get("mms"):
            new_line["mms"] = True
        if row_info.get("score") is not None:
            new_line["mms_score"] = row_info["score"]
        lines.append(new_line)

    syllables = "notes"
    for line in lines:
        if line.get("mms"):
            syllables = "mms"

    # 句尾斷開的小聲聲音（回音、換氣、子音）：量它小幾 dB；記下是第幾句（line），清掉時這一句也提早結束
    quiet = []
    for index in range(len(lines)):
        line = lines[index]
        last_end = sung_tokens(line["tokens"])[-1]["end"]
        for part in quiet_tail_parts(line["tokens"], last_end, notes, loudness, hop):
            part["line"] = index
            quiet.append(part)

    return {"synced": True, "lang": song_language, "lines": lines, "auto_shift": auto_shift,
            "syllables": syllables, "quiet": quiet, "song_zero": round(song_zero, 3),
            "moved_sections": moved_sections, "absent_lines": absent_lines, "absent_shown": show_absent}
