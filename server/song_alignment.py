"""
一段一段對齊：歌詞一定要放在歌手真的唱的地方，網路上的歌詞只是參考。

網路上的歌詞大多是給 CD 版的。MV 中間插了劇情、或影片是剪短的版本，那一段歌詞的時間就會錯開，
只整首一起移（lyrics_builder.estimate_shift）修不好。不管有沒有裁切，都在這裡修好：

1. 整首一次對齊：整份歌詞每句前後放一個 *（萬用字元：吸收劇情、音效、和聲），
   用 MMS（syllable_model 存好的 mms_emission.npy）把每個字母照順序放到整首歌最像的位置
   → 每一句有兩個候選位置：「網路歌詞的位置」（已經整首移過）、「整首對齊找到的位置」
2. 每個位置用同樣的方法、同樣長的時間（整首對齊聽到這句唱多久）聽一次：MMS 有多少把握聽到這一句的字（把握度）
   要搬幾秒、一句唱多久，都是 AI 聽出來的
3. 每一句選一個位置，整首加起來的把握度最高，而且：
   - 網路歌詞的位置優先：整首對齊的位置，把握度要先除以 BETTER_RATIO 再比（要明顯比較像才換）
   - 順序不能亂：有搬的句子，前一句要有時間唱完（每個音節至少 seconds_per_syllable 秒）
   - 前後句盡量一起搬：跟前一句選的不一樣，扣 SWITCH_COST（單獨一句亂跳的不換）
   （只看整首對齊會出錯：副歌唱好幾次時，英文歌常對到錯的那一次。這時兩邊都不太像、或換了會打亂順序，就不會換）
4. 這支影片沒唱的句子：兩個位置完全沒有人在唱、整首對齊也沒把握 → 拿掉（不顯示、不放評分條）

每一句裡每個字的時間，之後照樣由 syllable_aligner 細對（這裡只搬整句）。
"""
import numpy as np

from server import singing_check
from server.syllable_aligner import MARGIN, MIN_SCORE, align_line, spell

FRAME_SECONDS = 0.02    # syllable_model 的每一格
# 22 首歌實測：
BETTER_RATIO = 2.0      # 整首對齊的位置要比網路歌詞的位置像幾倍才換：
                        #   一首錯開的歌，整首對齊的位置大多像 2～50 倍以上（例：0.000 → 0.508）
                        #   副歌唱兩次的歌 0.8 倍、另外兩首 1.2 倍和 1.5 倍 → 不換
SWITCH_COST = MIN_SCORE # 跟前一句選的位置不一樣，扣這麼多分（= 一句「MMS 聽得到」的最低把握度，syllable_aligner 的）
                        #   沒有這條時，英文歌會有單獨幾句亂跳（一首 11 句、另一首 4 句）；有了只剩真的整段錯開的歌會搬
# 兩個位置差不到 MARGIN（syllable_aligner 細對齊時每句前後多看的秒數）就不用換：細對齊自己會找到


def voiced_share(notes, heard, hop, start, end):
    """start～end 之間，瀏覽器的耳朵也聽得到的音符，蓋住多少比例（0～1）"""
    if end <= start:
        return 0.0
    covered = 0.0
    for note in notes:
        if note["e"] <= start or note["s"] >= end:
            continue
        if not singing_check.is_heard(note, heard, hop):
            continue
        covered += min(note["e"], end) - max(note["s"], start)
    return min(1.0, covered / (end - start))


def spellings_of(tokens):
    """這一句每個字的拼音（沒有拼音的字、標點不算）"""
    result = []
    for token in tokens:
        if token["syl"] > 0 and spell(token) != "":
            result.append(spell(token))
    return result


def make_entries(raw_lines, all_tokens, times, first_of, duration):
    """要檢查的句子：有字、有拼音、不是「跟上一句一起唱」的第二句。
    每一句記：第幾行（index）、拼音、網路歌詞的位置（start）、到下一句有幾秒（span，最後一句到影片結束）"""
    entries = []
    for index in range(len(raw_lines)):
        if raw_lines[index]["text"] == "" or index in first_of:
            continue
        spellings = spellings_of(all_tokens[index])
        if len(spellings) == 0:
            continue
        entries.append({"index": index, "spellings": spellings, "start": times[index]})
    for position in range(len(entries)):
        entry = entries[position]
        if position + 1 < len(entries):
            entry["span"] = entries[position + 1]["start"] - entry["start"]
        else:
            entry["span"] = (duration or entry["start"]) - entry["start"]
    return entries


def whole_song(entries, emission):
    """整首一次對齊：每一句加上 "found": (開始, 結束, 把握度)；對不了回傳 False"""
    import torch
    from torchaudio.pipelines import MMS_FA

    words = []
    owners = []   # 每個字是第幾句的（* 是 None）
    for position in range(len(entries)):
        words.append("*")
        owners.append(None)
        for spelling in entries[position]["spellings"]:
            words.append(spelling)
            owners.append(position)
    words.append("*")
    owners.append(None)

    tokenizer = MMS_FA.get_tokenizer()
    aligner = MMS_FA.get_aligner()
    try:
        spans = aligner(torch.from_numpy(np.asarray(emission, dtype=np.float32)), tokenizer(words))
    except Exception:
        return False   # 例如歌太短、放不下這麼多字母

    pieces = {}
    for word_index in range(len(words)):
        position = owners[word_index]
        if position is None:
            continue
        word = spans[word_index]
        if position not in pieces:
            pieces[position] = {"start": word[0].start * FRAME_SECONDS, "scores": []}
        pieces[position]["end"] = word[-1].end * FRAME_SECONDS
        for letter in word:
            pieces[position]["scores"].append(float(letter.score))
    for position in pieces:
        piece = pieces[position]
        entries[position]["found"] = (round(piece["start"], 3), round(piece["end"], 3),
                                      float(np.mean(piece["scores"])))
    return True


def confidence(emission, entry, start, length):
    """這一句放在 start 開始、唱 length 秒的話，MMS 有多少把握聽到這些字（0～1）"""
    result = align_line(emission, entry["spellings"], start - MARGIN, start + length + MARGIN)
    if result is None:
        return 0.0
    return result[2]


def score_both(entries, emission):
    """每一句兩個位置各聽一次（同樣長：整首對齊聽到這句唱多久，前後各多看 MARGIN 秒）"""
    for entry in entries:
        entry["here"] = 0.0
        entry["there"] = None   # None = 沒有第二個位置可以選
        if "found" not in entry:
            entry["here"] = confidence(emission, entry, entry["start"], entry["span"])
            continue
        start, end, score = entry["found"]
        length = end - start
        entry["here"] = confidence(emission, entry, entry["start"], length)
        if abs(start - entry["start"]) > MARGIN:
            entry["there"] = confidence(emission, entry, start, length)


def choose_places(entries, seconds_per_syllable):
    """每一句選「網路歌詞的位置」(0) 或「整首對齊的位置」(1)，整首把握度加起來最高（規則見最上面第 3 點）。
    回傳每一句選了哪個"""
    count = len(entries)
    best = []    # best[i][choice] = 到第 i 句為止、第 i 句選 choice 時，最高的總分（None = 不行）
    back = []    # 那個最高分，前一句選了什麼
    for i in range(count):
        entry = entries[i]
        places = [entry["start"], None]
        values = [entry["here"], None]
        if entry["there"] is not None:
            places[1] = entry["found"][0]
            values[1] = entry["there"] / BETTER_RATIO
        best.append([None, None])
        back.append([None, None])
        for choice in (0, 1):
            if places[choice] is None:
                continue
            if i == 0:
                best[i][choice] = values[choice]
                continue
            previous = entries[i - 1]
            previous_places = [previous["start"], None]
            if previous["there"] is not None:
                previous_places[1] = previous["found"][0]
            for before in (0, 1):
                if best[i - 1][before] is None:
                    continue
                # 一句有搬、一句沒搬：前一句要有時間唱完。
                # 兩句都沒搬：照網路歌詞，不檢查。兩句都搬：都是整首對齊找到的位置，順序本來就對，不檢查
                # （影片沒唱的句子會被整首對齊擠在很短的時間裡；兩句都搬還檢查的話，後面整段都會搬不過去）
                if choice != before:
                    if places[choice] - previous_places[before] < previous["syllables"] * seconds_per_syllable:
                        continue
                total = best[i - 1][before] + values[choice]
                if before != choice:
                    total -= SWITCH_COST
                # 一樣高分時選網路歌詞的位置（先比 0，只有更高才換成 1）
                if best[i][choice] is None or total > best[i][choice]:
                    best[i][choice] = total
                    back[i][choice] = before

    # 從最後一句往回找
    choices = [0] * count
    if count == 0:
        return choices
    last = 0
    if best[count - 1][0] is None or (best[count - 1][1] is not None and best[count - 1][1] > best[count - 1][0]):
        last = 1
    if best[count - 1][last] is None:
        return [0] * count   # 怎麼選都會亂（不應該發生）：全部維持網路歌詞的位置
    choices[count - 1] = last
    for i in range(count - 1, 0, -1):
        choices[i - 1] = back[i][choices[i]]
    return choices


def is_absent(entry, notes, heard, hop):
    """這支影片沒唱這句：兩個位置完全沒人唱（瀏覽器的耳朵也聽不到任何音），整首對齊也沒把握"""
    if voiced_share(notes, heard, hop, entry["start"], entry["start"] + entry["span"]) > 0:
        return False
    if "found" not in entry:
        return False
    start, end, score = entry["found"]
    return score < MIN_SCORE and voiced_share(notes, heard, hop, start, end) == 0


def fix_sections(raw_lines, all_tokens, times, first_of, syllable_counts, seconds_per_syllable,
                 emission, notes, heard, hop, duration):
    """
    每一句放到歌手真的唱的地方、找出影片沒唱的句子。會直接改 times（每一行的開始時間）。
    syllable_counts：每一行有幾個音節；seconds_per_syllable：一個音節最快唱幾秒（lyrics_builder.TOGETHER_SYLLABLE）
    回傳 (搬了哪幾段, 拿掉哪幾行)：
      搬了：[{"first_row": 第一行, "lines": 幾句, "from": 原本的時間, "to": 搬過去的時間, "move": 秒}]
            （連著一起搬的句子算一段，給畫面上的提示用）
      拿掉：[第幾行, ...]（raw_lines 的位置）
    """
    entries = make_entries(raw_lines, all_tokens, times, first_of, duration)
    if len(entries) == 0 or not whole_song(entries, emission):
        return [], []
    for entry in entries:
        entry["syllables"] = syllable_counts[entry["index"]]
    score_both(entries, emission)
    choices = choose_places(entries, seconds_per_syllable)

    moved = []
    for position in range(len(entries)):
        entry = entries[position]
        if choices[position] != 1:
            continue
        move = entry["found"][0] - entry["start"]
        # 這一句到下一句前的每一行（中間的空白行、一起唱的第二句）都一起搬
        first_row = entry["index"]
        last_row = len(raw_lines) - 1
        if position + 1 < len(entries):
            last_row = entries[position + 1]["index"] - 1
        for row in range(first_row, last_row + 1):
            times[row] = times[row] + move
        if len(moved) > 0 and choices[position - 1] == 1:
            moved[-1]["lines"] += 1   # 跟上一句連著搬：算同一段
        else:
            moved.append({"first_row": first_row, "lines": 1, "from": round(entry["start"], 2),
                          "to": round(entry["found"][0], 2), "move": round(move, 2)})
        entry["start"] = entry["found"][0]

    absent = []
    for entry in entries:
        if is_absent(entry, notes, heard, hop):
            absent.append(entry["index"])
    # 跟上一句一起唱的第二句：第一句沒唱，它也沒唱
    for second in first_of:
        if first_of[second] in absent:
            absent.append(second)
    return moved, absent
