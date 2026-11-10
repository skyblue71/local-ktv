"""
歌詞時間跟人聲有多吻合（0～1，越大越吻合）。
字幕（lyrics_builder.py：整首歌詞是不是早／晚了一大段）和搜尋歌詞時的比對（lyrics_match.py）共用。

算法：把時間切成一格一格（FIT_STEP 秒），
  「有人唱」的格子：有音符的地方
  「有歌詞」的格子：每一句從它的時間，到下一行的時間為止（最長 LINE_MAX 秒）
  吻合度 = 「有歌詞而且有人唱」佔「有歌詞」和「有人唱」的比例（兩個比例的調和平均）
用前綴和算，試幾百種位移也很快。
"""

FIT_STEP = 0.1     # 每格幾秒
LINE_MAX = 8.0     # 一句歌詞最長算幾秒（避免最後一句或間奏前那句拉太長）


def voiced_prefix(notes, duration):
    """每一格有沒有人唱，做成前綴和：prefix[k] = 前 k 格裡有幾格有人唱"""
    length = int(duration / FIT_STEP) + 1
    voiced = [0] * length
    for note in notes:
        first = max(0, int(note["s"] / FIT_STEP))
        last = min(length, int(note["e"] / FIT_STEP) + 1)
        for k in range(first, last):
            voiced[k] = 1
    prefix = [0] * (length + 1)
    for k in range(length):
        prefix[k + 1] = prefix[k] + voiced[k]
    return prefix


def lyric_cells(raw_lines, shift, length):
    """每一句歌詞往後移 shift 秒之後，佔哪幾格：[(開始格, 結束格), ...]"""
    cells = []
    for index in range(len(raw_lines)):
        line = raw_lines[index]
        if line["text"] == "":
            continue
        start = line["time"] + shift
        end = start + LINE_MAX
        if index + 1 < len(raw_lines):
            end = min(end, raw_lines[index + 1]["time"] + shift)
        first = max(0, int(start / FIT_STEP))
        last = min(length, int(end / FIT_STEP))
        if last > first:
            cells.append((first, last))
    return cells


def fit(raw_lines, prefix, shift):
    """歌詞往後移 shift 秒時的吻合度（prefix 是 voiced_prefix 做的）"""
    length = len(prefix) - 1
    voiced_total = prefix[length]
    lyric_total = 0
    both = 0
    for first, last in lyric_cells(raw_lines, shift, length):
        lyric_total += last - first
        both += prefix[last] - prefix[first]
    if both == 0 or voiced_total == 0:
        return 0.0
    precision = both / lyric_total
    recall = both / voiced_total
    return 2 * precision * recall / (precision + recall)


def best_offsets(raw_lines, notes, duration, low, high, count, separation):
    """
    在 low～high 秒之間，吻合度最高的幾個位移（彼此至少差 separation 秒），由高到低。
    raw_lines 的時間要已經加好整體偏移。
    """
    if not duration or len(notes) == 0:
        return []
    prefix = voiced_prefix(notes, duration)
    scores = []
    steps = int(round((high - low) / FIT_STEP))
    for k in range(steps + 1):
        shift = round(low + k * FIT_STEP, 2)
        scores.append((fit(raw_lines, prefix, shift), shift))
    scores.sort(reverse=True)
    picked = []
    for score, shift in scores:
        far_enough = True
        for other in picked:
            if abs(shift - other) <= separation:
                far_enough = False
        if far_enough:
            picked.append(shift)
        if len(picked) >= count:
            break
    return picked
