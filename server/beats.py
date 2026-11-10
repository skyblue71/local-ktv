"""
把一個字的拼音切成「一拍一拍」，回傳每一拍從第幾個字母開始。
認音節（syllable_aligner.py）用：MMS 知道每個字母在幾秒，所以就知道每一拍在幾秒，
字幕可以一拍一拍填色、評分條可以一拍一條，不用把一個字的時間平均分給每一拍。

切法要跟 romanizer.py 算拍數（token 的 syl）的方法一樣，拍數對得上才用：
  日文（有假名或漢字的字）：照羅馬拼音切「拍」
    ka・yo・wa・i（か弱い 4 拍）、hi・ka・ri（光 3 拍）、shi・n・ji・tsu（ん自己一拍）、
    ki・t・te（っ：重複的子音自己一拍）、ma・t・cha（っ 在 ch 前面寫成 t）
  其他（英文等）：照「母音組」切，跟 count_latin_syllables 一樣（fi・gu・re）；
    母音組前面的子音，最後一個算下一拍的開頭
"""
import re

VOWELS = "aeiou"
JAPANESE_CHAR = re.compile(r"[぀-ヿ一-鿿]")


def japanese_beats(spelling):
    """日文羅馬拼音 → 每一拍第一個字母的位置"""
    starts = []
    i = 0
    length = len(spelling)
    while i < length:
        letter = spelling[i]
        if letter == "'":
            i += 1                       # n' 的分隔號
        elif letter in VOWELS:
            starts.append(i)             # 只有母音的一拍（あいうえお）
            i += 1
        elif letter == "n" and (i + 1 == length or spelling[i + 1] not in VOWELS + "y"):
            starts.append(i)             # ん
            i += 1
        elif i + 1 < length and spelling[i + 1] == letter:
            starts.append(i)             # っ（重複的子音，例如 kitte 的第一個 t）
            i += 1
        elif letter == "t" and spelling[i + 1:i + 3] == "ch":
            starts.append(i)             # っ 在 ch 前面（matcha）
            i += 1
        else:
            j = i
            while j < length and spelling[j] not in VOWELS:
                j += 1
            if j >= length:
                break                    # 最後只剩子音，沒有母音：不算一拍
            starts.append(i)             # 子音＋母音（ka、shi、kya…）
            i = j + 1
    return starts


def vowel_group_beats(spelling):
    """英文等：每一個母音組一拍；兩個母音組中間的子音，最後一個算下一拍的開頭"""
    groups = []
    for match in re.finditer(r"[aeiouy]+", spelling):
        groups.append((match.start(), match.end()))
    starts = []
    for index in range(len(groups)):
        if index == 0:
            starts.append(0)
        else:
            previous_end = groups[index - 1][1]
            starts.append(max(previous_end, groups[index][0] - 1))
    return starts


def letter_widths(positions, spelling):
    """照拼音字母算：每一拍從拼音的幾 %（0～1）開始（字幕下面那行羅馬拼音用；ka・yo・wa・i → 0、2/7、4/7、6/7）"""
    result = []
    for position in positions:
        result.append(round(position / max(1, len(spelling)), 4))
    return result


def beat_widths(token, positions, spelling):
    """畫面上每一拍從這個字的幾 %（0～1）開始，讓填色走到哪一拍、畫面就塗到哪一個字
    日文：每個字（parts 的每一段）的寬度照字數，這個字的讀音有幾拍就平均分給那幾拍
          例「か弱い」：か（1 拍）0、弱（よわ 2 拍）1/3 和 1/2、い（1 拍）2/3
    其他：照這一拍第一個字母在拼音裡的位置（fi・gu・re → 0、1/3、2/3）
    算不出來就每一拍一樣寬"""
    count = len(positions)
    equal = []
    for index in range(count):
        equal.append(round(index / count, 4))

    if not JAPANESE_CHAR.search(token["text"]):
        if len(spelling) == 0:
            return equal
        return letter_widths(positions, spelling)

    from server.romanizer import count_mora   # 放在這裡：跟算拍數用同一個方法
    parts = token.get("parts") or []
    total_chars = 0
    for part in parts:
        total_chars += len(part["text"])
    if total_chars == 0:
        return equal
    result = []
    passed_chars = 0
    for part in parts:
        reading = part.get("ruby") or part["text"]
        morae = count_mora(reading)
        for k in range(morae):
            result.append(round((passed_chars + len(part["text"]) * k / morae) / total_chars, 4))
        passed_chars += len(part["text"])
    if len(result) != count:
        return equal
    return result


def beat_starts(token_text, spelling, syllables):
    """這個字每一拍從第幾個字母開始；拍數跟 syllables 對不上就回傳 None（這個字整個一起填）"""
    if syllables <= 1 or spelling == "":
        return None
    if JAPANESE_CHAR.search(token_text):
        starts = japanese_beats(spelling)
    else:
        starts = vowel_group_beats(spelling)
    if len(starts) != syllables:
        return None
    return starts
