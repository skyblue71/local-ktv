"""
每個字從幾秒唱到幾秒（字幕、句子、評分條都照這裡算的時間）

字、句子、評分條如果各算各的，會對不上（例如有評分條、卻沒有字在填色）。
所以只算一件事：**每個字從幾秒唱到幾秒**，其他全部照它：
  - 字的填色 = 這個字的時間
  - 句子的時間 = 第一個字開始 ～ 最後一個字唱完（lyrics_builder.py）
  - 評分條 = 每個字的時間裡的音符（web\\js\\game\\lyricNotes.js），換字的地方切開（syllableBars.js）

做法（整首歌一起算）：
1. 整首一次對齊（AI 認音節 MMS，syllable_model 存好的 mms_emission.npy）：
   整份歌詞的字母照順序，放到整首歌最像的位置；每一句前後放一個 *（萬用字元：吸收間奏、劇情、和聲）。
   每一句只能落在「前一句 ～ 後兩句」的歌詞時間之間，副歌唱好幾次時不會跑到別次去
   （「歌詞時間」選「照歌詞檔」的話：每一句只能落在歌詞檔給它的時間裡）
   → 每個字母從幾秒開始、AI 有多少把握
2. 一句的平均把握度低於 MIN_SCORE（AI 聽不出這些字）：這句用猜的（spread_by_runs）
   從歌詞檔的時間（上一句唱完之後）到歌詞檔的下一行（下一句開始之前），照音符分給每個字
3. 照歌聲修正（每個字都用同一套規則，fit_to_runs）：
   「一段歌聲」= 瀏覽器的耳朵聽得到、連在一起沒停的音符（音高分析已經把很短的停頓接起來了，pitch_analyzer 的 BRIDGE_GAP）
   - 開始：AI 有把握的字，照 AI 聽到的時間（子音開始的地方）
           一句的第一個字例外：落在一個「歌手換氣後才開口」的音的中間 → 從歌手出聲的地方開始（opening_start）
           沒把握的（或猜的）：落在一個音的中間 → 從這個音開始的地方開始；落在沒聲音的地方 → 從下一段歌聲開始
           一句的第一個字落在一個音的中間：這個音如果是從上一句連著唱過來的（可能是上一句拉長的尾音），不往前搶，
           從歌手重新開口的地方或歌詞檔的時間開始（first_word_start）
           沒把握的字對到一個音的開頭之後：歌手是停下來之後才出聲、音符之前就有聲音的話（開口那一小段音高不穩，
           寫音符的 AI 沒寫音符），提早到出聲的地方（voice_start）
   - 結束：唱到下一個字開始前，最後一個音唱完的時候
           這個字一個音都沒有（寫音符的 AI 沒寫，例如唱得很輕、音高不穩）但聽字的 AI 有聽到它：
           唱到下一個字開始前，瀏覽器的耳朵最後還聽得到聲音的地方（last_voice）
           一句最後一個字：唱到它那一段歌聲（和 AI 有把握的最後一個字母那一段）唱完；
           後面斷開的歌聲不算這個字（一個字拉長是連著唱的；斷開又沒歌詞的是哼唱、即興）
           歌詞檔在這句後面有空白行（結束記號：歌手唱到這裡停）：沒把握的部分（猜的結束、拉長）只算到空白行，
           但只有切掉的是「小聲雜音」才切（比整首的歌聲小「清掉小聲雜音」的預設 dB 以上，
           例如一句最後一個字後面間奏的殘音）。跟歌聲一樣大的是真的人聲，照舊算這個字；自己連著唱的那一段不受影響
   時間都是 AI 聽到的、音符本身的開始結束、或歌詞檔給的。
"""
import numpy as np

from server import game_bars
from server.syllable_aligner import FRAME_SECONDS, MIN_SCORE, align_line, spell, token_beats

NO_PATH = -1e30   # 對齊時「不能走」的分數
TINY = 1e-6       # 比較時間用：兩個音「連在一起」= 前一個結束的時間就是後一個開始的時間
# 找到的音符，唱歌時間平均每個音節不到這麼多秒（一秒唱不了 10 個音節）：音符不可信，改照時間平均分
#   （全部歌實測）
MIN_SING_SYLLABLE = 0.1


def total_syllables(tokens):
    total = 0
    for token in tokens:
        total += token["syl"]
    return total


def sung_tokens(tokens):
    """有音節的字（標點符號不算）"""
    result = []
    for token in tokens:
        if token["syl"] > 0:
            result.append(token)
    return result


# ---------- 1. 整首一次對齊 ----------

def forced_align(emission, labels, lowest, highest):
    """
    強制對齊（CTC）：每個字母一定照順序出現，找出整首最像的放法。
    跟 torchaudio 的 forced_align 一樣，只是多了一個限制：第 k 個字母只能放在第 lowest[k] ～ highest[k] 格之間。
    labels：每個字母的編號（MMS 的字典）；回傳每一格放的是第幾個 state（偶數 = 空白、奇數 = 第 (state-1)/2 個字母），
    放不下回傳 None
    """
    emission = np.asarray(emission, dtype=np.float32)
    frames = len(emission)
    count = len(labels)
    states = 2 * count + 1
    labels = np.asarray(labels)
    lowest = np.asarray(lowest)
    highest = np.asarray(highest)

    state_label = np.zeros(states, dtype=int)   # 空白是 0 號
    state_label[1::2] = labels
    state_low = np.zeros(states, dtype=int)
    state_high = np.zeros(states, dtype=int)
    state_low[1::2] = lowest
    state_high[1::2] = highest
    # 字母前後的空白：前後兩個字母可以放的地方都可以
    state_low[0] = lowest[0]
    state_high[0] = highest[0]
    state_low[2:-1:2] = np.minimum(lowest[:-1], lowest[1:])
    state_high[2:-1:2] = np.maximum(highest[:-1], highest[1:])
    state_low[-1] = lowest[-1]
    state_high[-1] = highest[-1]
    # 可以跳過中間的空白、直接到下一個字母（兩個字母不一樣才行，一樣的話中間一定要有空白）
    can_skip = np.zeros(states, dtype=bool)
    can_skip[3::2] = labels[1:] != labels[:-1]

    score = np.full(states, NO_PATH)
    if state_low[0] <= 0:
        score[0] = emission[0, 0]
    if state_low[1] <= 0:
        score[1] = emission[0, state_label[1]]
    came_from = np.zeros((frames, states), dtype=np.int8)   # 0 = 留在原地、1 = 從前一個來、2 = 跳過空白來
    every_state = np.arange(states)
    for frame in range(1, frames):
        from_previous = np.full(states, NO_PATH)
        from_previous[1:] = score[:-1]
        from_skip = np.full(states, NO_PATH)
        from_skip[2:] = score[:-2]
        from_skip[~can_skip] = NO_PATH
        choices = np.stack([score, from_previous, from_skip])
        best_choice = np.argmax(choices, axis=0)
        best = choices[best_choice, every_state]
        new_score = best + emission[frame, state_label]
        allowed = (state_low <= frame) & (frame <= state_high)
        new_score[~allowed] = NO_PATH
        new_score[best <= NO_PATH / 2] = NO_PATH
        came_from[frame] = best_choice
        score = new_score

    last = states - 1
    if score[states - 2] > score[states - 1]:
        last = states - 2
    if score[last] <= NO_PATH / 2:
        return None
    path = np.zeros(frames, dtype=int)
    state = last
    for frame in range(frames - 1, -1, -1):
        path[frame] = state
        state -= int(came_from[frame, state])
    return path


def align_whole_song(entries, emission):
    """
    entries：要對齊的每一句 [{"row": 第幾行, "tokens": [有拼音的字], "low": 最早幾秒, "high": 最晚幾秒}]
    回傳 {第幾行: {"score": 這句的平均把握度, "letters": {字的位置: [(字母開始秒數, 把握度), ...]}}}；
    對不了回傳 None
    """
    from torchaudio.pipelines import MMS_FA
    dictionary = MMS_FA.get_dict()   # 字母 → 編號（含 *）
    frames = len(emission)
    star = dictionary["*"]

    labels = []
    lowest = []
    highest = []
    owners = []   # 每個字母是哪一句、第幾個字（* 是 None）
    for entry in entries:
        low = max(0, int(entry["low"] / FRAME_SECONDS))
        high = min(frames - 1, int(entry["high"] / FRAME_SECONDS))
        labels.append(star)
        lowest.append(0)
        highest.append(frames - 1)
        owners.append(None)
        first_letter = True
        for position in range(len(entry["tokens"])):
            for letter in spell(entry["tokens"][position]):
                labels.append(dictionary[letter])
                if first_letter and "first_low" in entry:
                    # 這一句的第一個字母另外限制在歌詞檔的時間附近（time_lines 的 near_lyric_file）
                    lowest.append(max(low, int(entry["first_low"] / FRAME_SECONDS)))
                    highest.append(min(high, int(entry["first_high"] / FRAME_SECONDS)))
                else:
                    lowest.append(low)
                    highest.append(high)
                first_letter = False
                owners.append((entry["row"], position))
    labels.append(star)
    lowest.append(0)
    highest.append(frames - 1)
    owners.append(None)

    path = forced_align(emission, labels, lowest, highest)
    if path is None:
        return None

    # 每個字母佔哪幾格
    spans = {}
    for frame in range(len(path)):
        if path[frame] % 2 == 1:
            index = (path[frame] - 1) // 2
            if index not in spans:
                spans[index] = [frame, frame]
            spans[index][1] = frame

    emission = np.asarray(emission, dtype=np.float32)
    result = {}
    for index in range(len(labels)):
        owner = owners[index]
        if owner is None:
            continue
        row, position = owner
        first, last = spans[index]
        # 把握度 = 這個字母那幾格的機率平均（跟 torchaudio 一樣）
        letter_score = float(np.mean(np.exp(emission[first:last + 1, labels[index]])))
        line = result.setdefault(row, {"scores": [], "letters": {}})
        line["letters"].setdefault(position, []).append((round(first * FRAME_SECONDS, 3), letter_score))
        line["scores"].append(letter_score)
    for row in result:
        result[row]["score"] = float(np.mean(result[row]["scores"]))
    return result


# ---------- 2. 歌聲：一段一段 ----------

def singing_runs(notes, heard):
    """瀏覽器的耳朵聽得到的音符（跟評分條同一條規則：scorer.js 的 isUnheardNote），連在一起的接成一段"""
    runs = []
    for note in notes:
        if game_bars.is_unheard(heard, note["s"], note["e"]):
            continue
        if len(runs) > 0 and note["s"] - runs[-1][1] <= TINY:
            runs[-1][1] = max(runs[-1][1], note["e"])
        else:
            runs.append([note["s"], note["e"]])
    return runs


def heard_notes(notes, heard):
    """瀏覽器的耳朵聽得到的每一個音 [[開始, 結束], ...]"""
    result = []
    for note in notes:
        if not game_bars.is_unheard(heard, note["s"], note["e"]):
            result.append([note["s"], note["e"]])
    return result


def piece_at(pieces, time):
    """time 落在哪一段裡（沒有回傳 None）"""
    for piece in pieces:
        if piece[0] - TINY <= time < piece[1]:
            return piece
        if piece[0] > time:
            break
    return None


def last_piece_before(pieces, time):
    """time 之前（已經結束的）最後一段"""
    found = None
    for piece in pieces:
        if piece[1] > time:
            break
        found = piece
    return found


def next_piece_after(pieces, time):
    """time 之後第一段"""
    for piece in pieces:
        if piece[0] >= time:
            return piece
    return None


# ---------- 3. 照歌聲修正 ----------

def last_word_end(item, start, next_start, runs, unsure_limit):
    """
    一句最後一個字唱到哪裡：唱到「開始的地方」和「AI 有把握的最後一個字母」（猜的字：猜的結束）所在的那一段唱完
    （落在沒聲音的地方：算後面那一段），之後還有歌聲就照 tail_end 在停最久的地方切開。
    unsure_limit：沒把握的部分（猜的結束、拉長）最多到哪裡；確定是這個字的部分可以到 next_start
    沒有聽得到的音就回傳 None
    """
    last_limit = next_start
    if not item["heard"]:
        last_limit = unsure_limit
    end = None
    for point, limit in [(start, next_start), (item["last_point"], last_limit)]:
        run = piece_at(runs, point)
        if run is None:
            run = next_piece_after(runs, point)
        if run is not None and run[0] < limit and run[1] > start:
            end = max(end if end is not None else start, min(run[1], limit))
    return end


def first_word_start(notes, runs, note, time, previous, next_time, voice_onset=None, line_time=None):
    """
    一句的第一個字（AI 沒把握的）落在 note 這個音的中間：要從哪裡開始？
    time：歌詞檔的時間（或 AI 沒把握的位置）；previous：上一個字開始的時間；next_time：下一個字的時間
    1. 這段歌聲是歌手換氣之後才開口的（上一個字不在這一段裡）：這個音就是這個字的，從歌手出聲的地方開始
       （opening_start；歌詞檔的時間晚了一點而已）
    2. 這段歌聲是從上一句連著唱過來的（中間沒停）：這個音可能是上一句拉長的尾音，不往前搶。
       - 後面（下一個字之前）歌手停下來又重新開口，而且那裡離歌詞檔的時間比這個音的開頭近：從重新開口的地方開始
       - 不然照歌詞檔的時間
    （拿 AI 很有把握的 755 句當答案，假裝 AI 聽不出來再猜一次，會用到這條規則的 323 句：
      以前一律從音的開頭開始 → 差 0.25 秒內 63%、提早超過 0.25 秒（上一句還在唱就先填滿）26%；
      現在 → 75%、8%。其他試過的：一律照歌詞檔 67%、一律用比較近的音 64%、一律用下一個音 58%）
    """
    run = piece_at(runs, time)
    from_previous_line = run is not None and run[0] <= previous
    if not from_previous_line:
        opening = opening_start(notes, runs, time, previous, voice_onset, line_time)
        if opening is not None:
            return opening
        return note[0]
    reopen = next_piece_after(runs, time)
    if reopen is not None and reopen[0] < next_time and reopen[0] - time < time - note[0]:
        return reopen[0]
    return time


def opening_start(notes, runs, time, previous, voice_onset, line_time):
    """
    一句的第一個字在 time 開始。如果 time 落在一個音的中間，而這段歌聲是歌手換氣之後才開口的
    （上一個字不在這一段裡）：這段聲音只可能是這個字，從歌手出聲的地方開始。
    回傳開始的秒數（不符合就回傳 None）
      出聲的地方 = 這個音的開頭，再往前到人聲開始變大聲的地方（voice_onset），
      但最多只往前到歌詞檔給這一句的時間 line_time：歌詞檔說這句還沒開始的話，前面的聲音是和聲、哼唱，不是這個字
      （不設這個界線，有和聲的歌會一路往前找，實測有句子被提早 1～3 秒）
      沒有音量資料、或歌詞檔的時間比這個音的開頭還晚：就是音的開頭
    （AI 聽拉長的母音常常標得比開口晚：一句開頭的「I——」0:34.8 開口、拉到 0:36，AI 標在 0:35.68，
      寫音符的 AI 從 0:35.05 才有把握，歌詞檔寫 0:34.70。前面那一段有歌聲、沒有字，也就沒有評分條。
      這條沒辦法拿 AI 有把握的字當答案來量（要改的就是 AI 標的時間），是照道理訂的）
    """
    run = piece_at(runs, time)
    note = piece_at(notes, time)
    if run is None or note is None:
        return None
    if run[0] <= previous + TINY or note[0] <= previous + TINY:
        return None   # 上一個字也在這段歌聲裡：不是換氣後才開口的
    if voice_onset is None or line_time is None or line_time >= note[0]:
        return note[0]
    return voice_onset(note[0], max(previous, line_time))


def make_voice_onset(loudness, hop, pieces):
    """
    回傳 voice_onset(音的開頭, 最早可以到哪裡, need_pause)：
    從這個音的開頭往前，人聲一直不是小聲雜音的那一段，是從幾秒開始的。
    小聲雜音 = 比整首的歌聲小「清掉小聲雜音」的預設 dB 以上（跟 make_quiet_check 同一條線）。
    need_pause=True：一路找到「最早可以到哪裡」人聲都沒停過，就不算「停下來之後才出聲」，回傳音的開頭
    沒有音量資料就回傳 None
    """
    if not loudness or not hop or len(pieces) == 0:
        return None
    singing = median_db(loudness, hop, pieces)
    if singing is None:
        return None
    limit = singing - game_bars.DEFAULT_QUIET_DB

    def voice_onset(note_start, earliest, need_pause=False):
        index = min(len(loudness), int(round(note_start / hop)))
        first = max(0, int(round(earliest / hop)) + 1)
        while index - 1 >= first and loudness[index - 1] >= limit:
            index -= 1
        if need_pause and index - 1 < first:
            return note_start
        return min(note_start, index * hop)
    return voice_onset


def voice_start(notes, note_start, earliest, voice_onset):
    """
    一個（AI 沒把握的）字對到 note_start 這個音的開頭。歌手其實是從幾秒開始出聲的？回傳那個秒數
    寫音符的 AI 只在音高穩定的地方寫音符，歌手剛開口的那一小段（子音、滑上去、抖一下）常常沒有音符；
    字從音符才開始的話，前面那一小段有歌聲、沒有字，也就沒有評分條。
    出聲的地方 = 從這個音的開頭往前，人聲一直不是小聲雜音的那一段的開頭（voice_onset）。
    往前找只找到 earliest（前一個字還在唱的時候）和「前面最後一個音唱完」為止，那之前是別的字的；
    找到那裡人聲都沒停過，就分不出這個字從哪裡開始，照舊用音的開頭。
    沒有音量資料也是音的開頭
    （拿 AI 很有把握、落在沒聲音的地方、後面接著一段歌聲的 801 個字當答案：
      音符的開頭 → 差 0.1 秒內 31%、0.25 秒內 84%，晚超過 0.1 秒的 69%；
      出聲的地方 → 67%、97%，晚的 23%、早的 11%。
      其他試過的找法：瀏覽器的耳朵聽到的開頭 42%、AI 音高線的開頭 51%。
      整套一起量：假裝 AI 對每個字都沒把握再算一次，跟它真的有把握的 7696 個字比，
      有變的 651 個字差 0.1 秒內 28% → 70%、0.25 秒內 84% → 96%，變準 587 個、變不準 61 個（最多差 0.30 秒））
    """
    if voice_onset is None:
        return note_start
    before = last_piece_before(notes, note_start)
    if before is not None:
        earliest = max(earliest, before[1])
    return voice_onset(note_start, earliest, True)


def keep_after_previous(start, item, previous_item):
    """
    沒把握的字照歌聲往前對了之後（start），不能比前一個字「AI 有把握的最後一個字母」還早開始：
    那時候前一個字還在唱。會的話就不往前對，留在 AI 聽到的位置（至少在那個字母之後）。回傳開始的秒數
    （例如「comes」拉長音，AI 聽到「the」在長音快結束的地方才開始、但對第一個字母沒把握；
      往前對到長音的開頭，就把「comes」的長音整個搶走了）
    前一個字是猜的（AI 沒聽到字母）就不管
    """
    if not previous_item["heard"] or start >= previous_item["last_point"]:
        return start
    return max(item["start"], previous_item["last_point"])


def make_last_voice(heard, hop):
    """
    回傳 last_voice(開始, 最晚)：這段時間裡，瀏覽器的耳朵最後還聽得到原唱的地方是幾秒（那一格的結尾，不超過「最晚」）；
    完全聽不到回傳 None。沒有 heard 資料就回傳 None
    """
    if not heard or not hop:
        return None

    def last_voice(start, latest):
        first = max(0, int(round(start / hop)))
        last = min(len(heard), int(round(latest / hop)))
        for index in range(last - 1, first - 1, -1):
            if heard[index] != 0:
                return min(latest, (index + 1) * hop)
        return None
    return last_voice


def fit_to_runs(items, runs, notes, limit_end, is_quiet=None, voice_onset=None, last_voice=None):
    """
    照歌聲修正每個字的開始、結束（規則見最上面第 3 點）。
    items：照順序的字 [{"token", "start", "sure"（AI 對開始的地方有把握）, "last_point"（AI 有把握的最後一個字母／猜的結束）,
                       "end_hint"（沒聲音時用的結束）, "last"（一句最後一個字）, "mark"（後面空白行的時間）,
                       "first"（一句第一個字）, "line_time"（歌詞檔給這一句的時間，第一個字才有）}]
    notes：聽得到的每一個音（heard_notes）；limit_end：最後一個字最多到哪裡
    is_quiet(開始, 結束)：這段聲音是不是小聲雜音（沒有音量資料就是 None，空白行不切）
    voice_onset(音的開頭, 最早到哪裡)：歌手從幾秒開始出聲（make_voice_onset；沒有音量資料就是 None）
    last_voice(開始, 最晚)：這段時間裡瀏覽器的耳朵最後還聽得到原唱的地方（make_last_voice；沒有資料就是 None）
    """
    # 第 1 輪：開始
    previous = -1e9
    for index in range(len(items)):
        item = items[index]
        start = item["start"]
        if index + 1 < len(items):
            next_candidate = items[index + 1]["start"]
        else:
            next_candidate = limit_end
        note_start = None   # 這個字對到哪一個音的開頭（沒有就是 None）
        if not item["sure"]:
            if piece_at(runs, start) is not None:
                # 落在一個音的中間：從這個音開始的地方開始（前一個字不在這個音裡開始的話）
                # 一句的第一個字要先看這個音是不是上一句拉長的尾音（first_word_start）
                note = piece_at(notes, start)
                if note is not None and note[0] > previous + TINY:
                    if item.get("first"):
                        start = first_word_start(notes, runs, note, start, previous, next_candidate, voice_onset,
                                                 item.get("line_time"))
                    else:
                        start = note[0]
                        note_start = start
            else:
                # 落在沒聲音的地方：從下一段歌聲開始（下一個字開始前的話）；
                # 後面沒有歌聲了：AI 沒把握的位置不能信，回到前面最後一個音開始的地方
                # （前一個字不在這個音裡開始的話。例如一首歌最後一個字，AI 把握度 0，被放在歌唱完 11 秒後）
                later = next_piece_after(runs, start)
                if later is not None and later[0] < next_candidate:
                    start = later[0]
                    note_start = start
                elif not item.get("first"):
                    # 只在同一句裡往前找：一句的第一個字是另外開口唱的，不能搶上一句的音
                    earlier = last_piece_before(notes, start)
                    if earlier is not None and earlier[0] > previous + TINY:
                        start = earlier[0]
                        note_start = start
            if index > 0:
                start = keep_after_previous(start, item, items[index - 1])
        elif item.get("first"):
            # AI 有把握的第一個字：換氣後才開口的那段聲音都是它的，從歌手出聲的地方開始
            opening = opening_start(notes, runs, start, previous, voice_onset, item.get("line_time"))
            if opening is not None:
                start = min(start, opening)
        start = max(start, previous)
        item["final_start"] = start
        item["at_note_start"] = note_start is not None and start == note_start
        previous = start

    # 第 1 輪之後：對到一個音開頭的字，歌手是停下來之後才出聲的話，提早到出聲的地方（voice_start）
    # （上面全部算完才做：上面的規則要看「前一個字是不是從這個音開始的」，先提早的話會看錯）
    for index in range(len(items)):
        item = items[index]
        if not item["at_note_start"]:
            continue
        earliest = -1e9
        if index > 0:
            # 前一個字開始、和它 AI 有把握的最後一個字母之前，前一個字還在唱
            earliest = items[index - 1]["final_start"]
            if items[index - 1]["heard"]:
                earliest = max(earliest, items[index - 1]["last_point"])
        item["final_start"] = voice_start(notes, item["final_start"], earliest, voice_onset)

    # 第 2 輪：結束
    for index in range(len(items)):
        item = items[index]
        start = item["final_start"]
        if index + 1 < len(items):
            next_start = items[index + 1]["final_start"]
        else:
            next_start = limit_end
        end = None
        if item["last"]:
            end = last_word_end(item, start, next_start, runs, next_start)
            # 歌詞檔在這句後面有空白行（結束記號：歌手唱到這裡停）：
            # 沒把握的部分（猜的結束、換一口氣再唱的拉長）只算到空白行——但只有切掉的是「小聲雜音」才切
            # （比歌聲小「清掉小聲雜音」的預設 dB 以上；跟歌聲一樣大的是真的人聲，照舊算這個字）
            mark = item.get("mark")
            if end is not None and mark is not None and start < mark < next_start and is_quiet is not None:
                cut_end = last_word_end(item, start, next_start, runs, mark)
                if cut_end is not None and cut_end < end and is_quiet(cut_end, end):
                    end = cut_end
        else:
            # 唱到下一個字開始前，最後一個音唱完
            for run in runs:
                if run[1] <= start:
                    continue
                if run[0] >= next_start:
                    break
                end = min(run[1], next_start)
        if end is None:
            end = min(max(item["end_hint"], start), next_start)   # 沒有聽得到的音
            # 寫音符的 AI 在這個字這裡一個音都沒寫（音高不穩，例如唱得很輕），但聽字的 AI 有聽到這個字：
            # 瀏覽器的耳朵在下一個字開始之前還聽得到聲音的話，這個字就唱到那裡
            # （不然這個字只有一瞬間，那段時間不算有字，也就補不了評分條）
            if not item["last"] and item["heard"] and last_voice is not None:
                voice_end = last_voice(start, next_start)
                if voice_end is not None:
                    end = max(end, voice_end)
        item["token"]["start"] = round(start, 3)
        item["token"]["end"] = round(max(end, start), 3)


# ---------- 把握度低的句子：用猜的 ----------

def piece_weights(pieces, syllables):
    """
    每一段歌聲的份量（分音節用）：照秒數，但**長音最多算「平均一個音節」那麼長**。
    拉長的音只是一個音節拉長，不會因為長就分到好幾個音節。
    「平均一個音節」= 這段唱歌時間 ÷ 音節數（每一句自己算）
    """
    total = 0.0
    for piece in pieces:
        total += piece[1] - piece[0]
    share = total / max(1, syllables)
    weights = []
    for piece in pieces:
        weights.append(min(piece[1] - piece[0], share))
    return weights


def time_at(pieces, weights, fraction, is_start=False):
    """
    份量（piece_weights）走到 fraction（0~1）的時候，對應到真正的秒數。
    is_start=True（算一個字的開始）：剛好落在兩段中間的地方時，用「下一段開始」的時間
    """
    total = 0.0
    for weight in weights:
        total += weight
    target = total * fraction
    passed = 0.0
    for index in range(len(pieces)):
        piece = pieces[index]
        weight = weights[index]
        reached = passed + weight >= target - TINY
        if is_start:
            reached = passed + weight > target + TINY
        if reached:
            inside = 0.0
            if weight > 0:
                inside = max(0.0, target - passed) / weight
            return piece[0] + inside * (piece[1] - piece[0])
        passed += weight
    return pieces[-1][1]


def spread_by_runs(tokens, notes, window_start, window_end):
    """
    AI 聽不出來的句子：window_start～window_end 之間聽得到的音，照音節數分給每個字（長音最多算一個音節，piece_weights）。
    音符少到唱不完這一句（MIN_SING_SYLLABLE）：整段時間平均分。
    （拿 AI 很有把握的 506 句當答案測：句尾差 0.25 秒內 95%，字開始差 0.25 秒內 41%）
    """
    syllables = max(1, total_syllables(tokens))
    pieces = []
    for note in notes:
        start = max(note[0], window_start)
        end = min(note[1], window_end)
        if end > start:
            pieces.append([start, end])
    length = 0.0
    for piece in pieces:
        length += piece[1] - piece[0]
    if length < syllables * MIN_SING_SYLLABLE:
        pieces = [[window_start, max(window_end, window_start + TINY)]]
    weights = piece_weights(pieces, syllables)
    count = 0
    for token in tokens:
        token["start"] = time_at(pieces, weights, count / syllables, True)
        count += token["syl"]
        token["end"] = time_at(pieces, weights, count / syllables)


# ---------- 全部一起 ----------

def make_item(token, letters, last):
    """fit_to_runs 要的資料：letters = AI 聽到的字母 [(開始秒數, 把握度)]（猜的字是 None）"""
    item = {"token": token, "start": token["start"], "end_hint": token["end"], "last": last,
            "sure": False, "last_point": token["end"], "heard": bool(letters)}
    if letters:
        item["sure"] = letters[0][1] >= MIN_SCORE
        item["last_point"] = token["start"]
        for letter_time, letter_score in letters:
            if letter_score >= MIN_SCORE:
                item["last_point"] = letter_time   # AI 有把握的最後一個字母
    return item


def near_lyric_file(entries, found, times, emission):
    """
    這首歌的歌詞檔準不準，程式自己量（不用使用者一首一首決定要不要自動對齊）：
    AI 比較有把握的那一半句子（把握度在這首歌的中位數以上）當答案，看它們開始的時間離歌詞檔最遠差幾秒。
    比較沒把握的那一半句子，離歌詞檔不能比這個更遠：超過的話，把那些句子的第一個字母限制在這個距離裡，整首重新對一次。
    歌詞檔準的歌會自動守著歌詞檔，不準的歌（或中間有整段搬家的歌）自動放寬。
    回傳要用的對齊結果（不用重對、或重對不了，就是原本的 found）
    """
    scores = []
    for entry in entries:
        line = found.get(entry["row"])
        if line is not None:
            scores.append(line["score"])
    if len(scores) < 2:
        return found
    scores.sort()
    middle = scores[len(scores) // 2]

    def distance(entry):
        return abs(found[entry["row"]]["letters"][0][0][0] - times[entry["row"]])

    limit = 0.0
    for entry in entries:
        line = found.get(entry["row"])
        if line is not None and line["score"] >= middle:
            limit = max(limit, distance(entry))
    changed = False
    for entry in entries:
        line = found.get(entry["row"])
        if line is not None and line["score"] < middle and distance(entry) > limit:
            entry["first_low"] = times[entry["row"]] - limit
            entry["first_high"] = times[entry["row"]] + limit
            changed = True
    if not changed:
        return found
    again = align_whole_song(entries, emission)
    if again is None:
        return found
    return again


def median_db(loudness, hop, pieces):
    """這幾段時間裡每一格音量（dB）的中位數；沒有資料回傳 None"""
    values = []
    for start, end in pieces:
        first = max(0, int(round(start / hop)))
        last = min(len(loudness), int(round(end / hop)))
        values.extend(loudness[first:last])
    if len(values) == 0:
        return None
    values.sort()
    return values[len(values) // 2]


def make_quiet_check(loudness, hop, pieces):
    """
    回傳 is_quiet(開始, 結束)：這段時間裡聽得到的聲音，是不是比整首的歌聲小「清掉小聲雜音」的預設 dB 以上
    （跟設定的「清掉小聲雜音」同一個數字，game_bars.DEFAULT_QUIET_DB，從 web\\js\\settings.js 讀）
    沒有音量資料就回傳 None
    """
    if not loudness or not hop or len(pieces) == 0:
        return None
    singing = median_db(loudness, hop, pieces)
    if singing is None:
        return None

    def is_quiet(start, end):
        inside = []
        for piece in pieces:
            if piece[1] > start and piece[0] < end:
                inside.append([max(piece[0], start), min(piece[1], end)])
        level = median_db(loudness, hop, inside)
        if level is None:
            return True   # 這段根本聽不到聲音
        return singing - level >= game_bars.DEFAULT_QUIET_DB

    return is_quiet


def time_lines(raw_lines, all_tokens, times, together, first_of, notes, heard, emission, duration, auto_align,
               loudness=None, hop=0.0):
    """
    算出每一行每個字的 start、end（一個字有好幾拍的再加 beats），直接改在 all_tokens 裡。
    times：每一行的歌詞時間（已經整首移、整段搬過）
    loudness、hop：人聲每一格的音量（dB，pitch.json）；用來分辨空白行後面的聲音是不是小聲雜音（沒有也可以）
    回傳 {第幾行: {"mms": 這句用 AI 聽的, "score": 把握度（沒對就是 None）}}
    """
    rows = []
    for row in range(len(raw_lines)):
        if raw_lines[row]["text"] != "" and len(sung_tokens(all_tokens[row])) > 0:
            rows.append(row)
    main_rows = []   # 不是「跟上一句一起唱」的第二句
    for row in rows:
        if row not in first_of:
            main_rows.append(row)
    end_time = duration
    if not end_time and len(notes) > 0:
        end_time = notes[-1]["e"]
    if not end_time and len(times) > 0:
        end_time = max(times) + 10

    def lyric_next(row):
        """歌詞檔的下一行（一起唱的兩句算一行）的時間"""
        follow = row + 1
        if row in together:
            follow = together[row] + 1
        if follow < len(times):
            return times[follow]
        return end_time

    # 1. 整首一次對齊
    entries = []
    for order in range(len(main_rows)):
        row = main_rows[order]
        usable = []
        for token in sung_tokens(all_tokens[row]):
            if spell(token) != "":
                usable.append(token)
        if len(usable) == 0:
            continue
        if auto_align:
            low = 0.0
            if order > 0:
                low = times[main_rows[order - 1]]
            high = end_time
            if order + 2 < len(main_rows):
                high = times[main_rows[order + 2]]
        else:
            low = times[row]
            high = lyric_next(row)
        entries.append({"row": row, "tokens": usable, "low": low, "high": max(high, low + FRAME_SECONDS)})
    found = {}
    if emission is not None and len(entries) > 0:
        found = align_whole_song(entries, emission) or {}
        if auto_align:
            found = near_lyric_file(entries, found, times, emission)

    info = {}
    letters_of = {}   # id(字) → AI 聽到的字母
    for entry in entries:
        line = found.get(entry["row"])
        if line is None:
            continue
        info[entry["row"]] = {"mms": line["score"] >= MIN_SCORE, "score": round(line["score"], 3)}
        if line["score"] < MIN_SCORE:
            continue
        for position in range(len(entry["tokens"])):
            token = entry["tokens"][position]
            letters = line["letters"][position]
            letters_of[id(token)] = letters
            token["start"] = letters[0][0]
            token["end"] = letters[-1][0] + FRAME_SECONDS
        # 沒有拼音的字（例如數字）：跟著前一個字（第一個就跟著後一個字）
        sung = sung_tokens(all_tokens[entry["row"]])
        for index in range(len(sung)):
            if "start" in sung[index]:
                continue
            if index > 0:
                sung[index]["start"] = sung[index - 1]["end"]
            else:
                for later in sung:
                    if "start" in later:
                        sung[index]["start"] = later["start"]
                        break
            sung[index]["end"] = sung[index]["start"]

    # 2. AI 聽不出來的句子：用猜的
    pieces = heard_notes(notes, heard)
    runs = singing_runs(notes, heard)
    for order in range(len(main_rows)):
        row = main_rows[order]
        if info.get(row, {}).get("mms"):
            continue
        info.setdefault(row, {"mms": False, "score": None})
        previous_end = 0.0
        if order > 0:
            previous = sung_tokens(all_tokens[main_rows[order - 1]])
            if len(previous) > 0 and "end" in previous[-1]:
                previous_end = previous[-1]["end"]
        window_end = end_time
        if order + 1 < len(main_rows):
            next_row = main_rows[order + 1]
            next_sung = sung_tokens(all_tokens[next_row])
            if info.get(next_row, {}).get("mms") and "start" in next_sung[0]:
                window_end = next_sung[0]["start"]
            else:
                window_end = times[next_row]
        window_start = max(previous_end, times[row])
        if window_start < lyric_next(row) < window_end:
            window_end = lyric_next(row)   # 歌詞檔說這句在這裡結束（或下一句在這裡開始）
        spread_by_runs(sung_tokens(all_tokens[row]), pieces, window_start, max(window_end, window_start + TINY))

    def end_mark(row):
        """歌詞檔在這一行後面緊接著空白行（結束記號：歌手唱到這裡停）→ 空白行的時間；沒有就是 None"""
        follow = row + 1
        if row in together:
            follow = together[row] + 1
        if follow < len(raw_lines) and raw_lines[follow]["text"] == "":
            return times[follow]
        return None

    # 3. 照歌聲修正：整首一起
    items = []
    for row in main_rows:
        sung = sung_tokens(all_tokens[row])
        for index in range(len(sung)):
            item = make_item(sung[index], letters_of.get(id(sung[index])), index == len(sung) - 1)
            if item["last"]:
                item["mark"] = end_mark(row)
            item["first"] = index == 0
            if index == 0:
                item["line_time"] = times[row]   # 歌詞檔給這一句的時間（整首移過、整段搬過）
            items.append(item)
    fit_to_runs(items, runs, pieces, end_time, make_quiet_check(loudness, hop, pieces),
                make_voice_onset(loudness, hop, pieces), make_last_voice(heard, hop))

    # 跟上一句一起唱的第二句：在第一句的時間裡自己對
    for second in first_of:
        if second not in rows:
            continue
        first_sung = sung_tokens(all_tokens[first_of[second]])
        sung = sung_tokens(all_tokens[second])
        if len(first_sung) == 0:
            continue
        window_start = first_sung[0]["start"]
        window_end = max(first_sung[-1]["end"], window_start + TINY)
        usable = []
        for token in sung:
            if spell(token) != "":
                usable.append(token)
        result = None
        if emission is not None and len(usable) > 0:
            result = align_line(emission, [spell(token) for token in usable], window_start, window_end)
        if result is not None and result[2] >= MIN_SCORE and len(usable) == len(sung):
            for index in range(len(usable)):
                usable[index]["start"] = result[0][index]
                usable[index]["end"] = result[0][index]
                letters_of[id(usable[index])] = result[1][index]
            info[second] = {"mms": True, "score": round(result[2], 3)}
        else:
            spread_by_runs(sung, pieces, window_start, window_end)
            info[second] = {"mms": False, "score": None if result is None else round(result[2], 3)}
        second_items = []
        for index in range(len(sung)):
            second_items.append(make_item(sung[index], letters_of.get(id(sung[index])), index == len(sung) - 1))
            second_items[-1]["first"] = index == 0
        fit_to_runs(second_items, runs, pieces, window_end)

    # 一個字有好幾拍（例如「光」hi・ka・ri）：每一拍照 AI 聽到的時間（syllable_aligner.token_beats）
    for row in rows:
        for token in sung_tokens(all_tokens[row]):
            letters = letters_of.get(id(token))
            if not letters:
                continue
            beat_info = token_beats(token, spell(token), letters, notes)
            if beat_info is not None:
                token["beats"] = beat_info[0]
                token["beat_x"] = beat_info[1]
                token["beat_roma_x"] = beat_info[2]
    return info
