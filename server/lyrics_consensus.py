"""
多份歌詞互相比對（「編輯歌詞」搜尋結果用）：抓出「整首早／晚一句」和「某幾句時間寫錯」。

為什麼要：有些歌每一句隔得差不多一樣久（例如每 6 秒一句），
歌詞檔只要有一兩句時間寫錯，自動對齊就可能整首對到「早一句」的位置，
而且每一句看起來都剛好有人在唱，只聽人聲發現不了。
（例：某支 MV，有兩句時間寫錯的那份歌詞，整首早了 6.65 秒）

做法：網路上同一首歌有很多份歌詞，大多是不同人各自對時間做的。
  1. 每一份先各自對齊這首歌（lyrics_builder.estimate_shift），算出每一句在影片的第幾秒
  2. 同一句歌詞（字一樣），很多份都放在差不多的時間（CLUSTER_GAP 秒內），取中間值當「大家說的時間」
     （副歌會出現好幾次，每一次各算一個）
  3. 某一份跟大家比，每一句跟「最近的那一次」比：
     大部分句子都差很多 → 整首早／晚了；只有幾句差很多 → 那幾句時間寫錯了
  一模一樣的複製版只算一票（不然 10 份抄來的錯誤版本會贏）。
"""
import re

# 整首跟大家差這麼多秒以上，算「整首早／晚了」（差這麼多的話，逐句對齊修不回來）
WHOLE_LIMIT = 2.0
# 某一句跟這份歌詞其他句子差這麼多秒以上，算「這句時間寫錯了」
ODD_LINE = 3.0
# 同一句歌詞，不同版本放的時間（從最早的那份算起）這麼多秒以內，算同一個地方
CLUSTER_GAP = 3.0
# 離「大家說的時間」超過這麼多秒就不比（副歌第二次出現，網路版本的字不一樣、沒有大家的時間，
# 不要拿去跟一分鐘前的第一次比）。寫錯的句子實測差 8～19 秒，所以抓得到
MATCH_RANGE = 25.0
# 同一個地方至少要有這麼多份（不同的）歌詞，才算得出「大家說的時間」
MIN_VOTES = 3
# 至少要有這麼多句比得到，才判斷這份歌詞
MIN_LINES = 5
# 判斷「是不是複製版」看前幾句的時間
SAME_COPY_LINES = 15

# 括號裡全是假名的讀音（例：拙(つたな)い）、{讀音}。英文括號裡的和聲（例：(symphony...)）要留著，那是不同句
READING_MARK = re.compile(r"[（(][぀-ヿ]+[）)]|\{[^}]*\}")
NOT_LETTER = re.compile(r"[\W_]+")                          # 空白、標點、♪


def normalize(text):
    """比對用的字：去掉讀音、空白、標點，英文變小寫"""
    text = READING_MARK.sub("", text)
    return NOT_LETTER.sub("", text.lower())


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def word_times(lines):
    """[(影片裡的時間, 字), ...] → [(比對用的字, 時間), ...]（空的、只有符號的不要）"""
    result = []
    for time, text in lines:
        word = normalize(text)
        if word != "":
            result.append((word, time))
    return result


def copy_identity(words):
    """前幾句的時間（四捨五入到 0.1 秒）：一樣的話就是複製版"""
    times = []
    for word, time in words[:SAME_COPY_LINES]:
        times.append(round(time, 1))
    return tuple(times)


def build_consensus(all_words):
    """all_words：每一份歌詞的 word_times。
    回傳 {字: [大家說的時間, ...]}（同一句出現好幾次就有好幾個時間）"""
    votes = {}
    used = set()
    for words in all_words:
        identity = copy_identity(words)
        if len(words) == 0 or identity in used:
            continue   # 複製版只算一票
        used.add(identity)
        for word, time in words:
            votes.setdefault(word, []).append(time)

    consensus = {}
    for word in votes:
        times = sorted(votes[word])
        group = [times[0]]
        places = []
        for time in times[1:]:
            # 從這個地方的第一份算起 CLUSTER_GAP 秒內才算同一個地方（不要一份接一份串成一大串）
            if time - group[0] <= CLUSTER_GAP:
                group.append(time)
            else:
                places.append(group)
                group = [time]
        places.append(group)
        for group in places:
            if len(group) >= MIN_VOTES:
                consensus.setdefault(word, []).append(median(group))
    return consensus


def nearest(times, time):
    best = times[0]
    for other in times:
        if abs(other - time) < abs(best - time):
            best = other
    return best


def compare(lines, consensus):
    """一份歌詞跟大家比。lines：[(影片裡的時間, 字), ...]
    回傳 {"diff": 整首比大家早（負）／晚（正）幾秒, "off": 整首差太多（WHOLE_LIMIT 以上）,
          "odd": [{"text": 字, "time": 這份放在影片第幾秒, "others": 大部分版本放在第幾秒}, ...]}
    比得到的句子太少就回傳 None"""
    diffs = []
    matched = []
    for time, text in lines:
        word = normalize(text)
        if word in consensus:
            target = nearest(consensus[word], time)
            if abs(time - target) > MATCH_RANGE:
                continue
            diffs.append(time - target)
            matched.append((time, text, target))
    if len(diffs) < MIN_LINES:
        return None
    whole = median(diffs)
    odd = []
    for index in range(len(matched)):
        if abs(diffs[index] - whole) > ODD_LINE:
            time, text, target = matched[index]
            odd.append({"text": text, "time": round(time, 2), "others": round(target, 2)})
    return {"diff": round(whole, 2), "off": abs(whole) >= WHOLE_LIMIT, "odd": odd}


def check_all(version_lines, current_lines):
    """version_lines：搜尋到的每一份歌詞 [(影片裡的時間, 字), ...]（沒有時間軸的給 []）
    current_lines：現在用的字幕 [(開始時間, 字), ...]
    回傳 (每一份的比對結果, 現在的字幕的比對結果)；比不了的是 None"""
    all_words = []
    for lines in version_lines:
        all_words.append(word_times(lines))
    consensus = build_consensus(all_words)
    checks = []
    for lines in version_lines:
        if len(lines) == 0:
            checks.append(None)
        else:
            checks.append(compare(lines, consensus))
    current = None
    if len(current_lines) > 0:
        current = compare(current_lines, consensus)
    return checks, current
