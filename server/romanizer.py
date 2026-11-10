"""
把歌詞轉成：
  日文 → 假名注音 + 羅馬音（用 fugashi 斷詞、pykakasi 轉羅馬音）
  中文 → 拼音 + 注音符號（用 pypinyin）
  韓文 → 羅馬字（自己寫的簡易版）
  英文 → 不用轉

每一句歌詞會被切成很多「詞」(token)，每個詞長這樣：
  {
    "text": "歩く",                              # 原文
    "parts": [{"text": "歩", "ruby": "ある"},     # 原文拆開，漢字上面放假名
              {"text": "く", "ruby": ""}],
    "roma": "aruku",                             # 羅馬音（中文是拼音）
    "zhuyin": "",                                # 注音符號（只有中文才有）
    "space": False,                              # 原文這個詞前面有沒有空格
    "join": False,                               # 羅馬音要不要黏在前一個詞後面（不加空格）
    "syl": 3,                                    # 大約有幾個音節（用來分配每個字的時間）
  }
"""
import re
import unicodedata

_tagger = None
_tagger_failed = False
_kakasi = None

# 日文的小寫假名（不算一拍）
SMALL_KANA = "ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ"

# 標點符號在羅馬音那一行要顯示成什麼
PUNCT_ROMA = {"、": ",", "。": ".", "，": ",", "！": "!", "？": "?", "!": "!", "?": "?",
              ",": ",", "～": "~", "~": "~"}

# 日文詞性（unidic 字典給的名稱，是日文，不能改成中文）
POS_PARTICLE = "助詞"      # 助詞：は、を、へ…
POS_AUXILIARY = "助動詞"   # 助動詞：た、ます…
POS_SUFFIX = "接尾辞"      # 接尾詞：さん、たち…

# 讀音修正：歌詞裡在字後面加 {讀音}，就用你寫的讀音（字典猜錯時用）
#   日文：私{わたし}、明日{あした}（平假名、片假名都可以）
#   中文：還{ㄏㄨㄢˊ}（寫注音就改注音）、還{huán}（寫拼音就改拼音）
READING_MARK = re.compile(r"\{([^{}]*)\}")

# 中文漢字的範圍（拆句子用）
HANZI_PATTERN = "[一-鿿㐀-䶿]+|[^一-鿿㐀-䶿]+"


# ---------- 字元判斷 ----------

def is_hiragana(ch):
    return "ぁ" <= ch <= "ゟ"


def is_katakana(ch):
    return "゠" <= ch <= "ヿ"


def is_kana(ch):
    return is_hiragana(ch) or is_katakana(ch)


def is_kanji(ch):
    return ("一" <= ch <= "鿿") or ("㐀" <= ch <= "䶿") or ch == "々"


def is_hangul(ch):
    return "가" <= ch <= "힣"


def is_punctuation(ch):
    category = unicodedata.category(ch)
    return category[0] in ("P", "S", "Z")


def has_kanji(text):
    for ch in text:
        if is_kanji(ch):
            return True
    return False


def all_kana(text):
    if text == "":
        return False
    for ch in text:
        if not is_kana(ch):
            return False
    return True


def all_punctuation(text):
    for ch in text:
        if not is_punctuation(ch):
            return False
    return True


def to_hiragana(text):
    """片假名 → 平假名"""
    result = ""
    for ch in text:
        if "ァ" <= ch <= "ヶ":
            result += chr(ord(ch) - 0x60)
        else:
            result += ch
    return result


def to_katakana(text):
    """平假名 → 片假名"""
    result = ""
    for ch in text:
        if "ぁ" <= ch <= "ゖ":
            result += chr(ord(ch) + 0x60)
        else:
            result += ch
    return result


# ---------- 語言判斷 ----------

def detect_song_language(all_text):
    """用整首歌詞判斷主要語言：ja / zh / ko / other"""
    kana = 0
    hangul = 0
    cjk = 0
    for ch in all_text:
        if is_kana(ch):
            kana += 1
        elif is_hangul(ch):
            hangul += 1
        elif is_kanji(ch):
            cjk += 1
    if kana > 0 and kana >= hangul:
        return "ja"
    if hangul > 0 and hangul >= cjk:
        return "ko"
    if cjk > 0:
        return "zh"
    return "other"


def detect_line_language(text, song_language):
    """判斷單一句的語言（日文歌裡也常有英文句子）"""
    has_kana_char = False
    has_hangul_char = False
    has_cjk_char = False
    for ch in text:
        if is_kana(ch):
            has_kana_char = True
        elif is_hangul(ch):
            has_hangul_char = True
        elif is_kanji(ch):
            has_cjk_char = True
    if has_hangul_char:
        return "ko"
    if has_kana_char:
        return "ja"
    if has_cjk_char:
        # 只有漢字的句子：日文歌就當日文，不然當中文
        if song_language == "ja":
            return "ja"
        return "zh"
    return "other"


# ---------- 音節數（分配時間用） ----------

def count_mora(kana):
    """日文的拍數：小寫的ゃゅょ不算一拍"""
    count = 0
    for ch in kana:
        if is_kana(ch) and ch not in SMALL_KANA:
            count += 1
    return count


def count_latin_syllables(word):
    """英文大約的音節數：數母音的組數"""
    groups = re.findall(r"[aeiouy]+", word.lower())
    if len(groups) > 0:
        return len(groups)
    if re.search(r"[0-9a-zA-Z]", word):
        return 1
    return 0


# ---------- 做出一個 token ----------

def make_token(text, parts, roma, space, join, syl):
    return {
        "text": text,
        "parts": parts,
        "roma": roma,
        "zhuyin": "",
        "space": space,
        "join": join,
        "syl": syl,
    }


def plain_parts(text):
    return [{"text": text, "ruby": ""}]


def punctuation_token(text, space):
    roma = ""
    for ch in text:
        if ch in PUNCT_ROMA:
            roma += PUNCT_ROMA[ch]
    return make_token(text, plain_parts(text), roma, space, True, 0)


def word_tokens(text, keep_roma):
    """
    用空格切詞（英文、韓文用）。
    keep_roma=True 時，羅馬音那一行就放原文（日文/中文句子裡夾的英文）
    """
    tokens = []
    pending_space = False
    for chunk in re.findall(r"\s+|\S+", text):
        if chunk.strip() == "":
            pending_space = True
            continue
        if all_punctuation(chunk):
            tokens.append(punctuation_token(chunk, pending_space))
        else:
            roma = ""
            if keep_roma:
                roma = chunk
            tokens.append(make_token(chunk, plain_parts(chunk), roma, pending_space, False,
                                     count_latin_syllables(chunk)))
        pending_space = False
    return tokens


# ---------- 日文 ----------

def get_tagger():
    """fugashi 是日文斷詞工具（使用 unidic-lite 字典）"""
    global _tagger, _tagger_failed
    if _tagger is None and not _tagger_failed:
        try:
            import fugashi
            _tagger = fugashi.Tagger()
        except Exception as error:
            print("fugashi 無法使用，改用 pykakasi：", error)
            _tagger_failed = True
    return _tagger


def get_kakasi():
    global _kakasi
    if _kakasi is None:
        import pykakasi
        _kakasi = pykakasi.kakasi()
    return _kakasi


def kana_to_romaji(kana):
    result = ""
    for item in get_kakasi().convert(kana):
        result += item["hepburn"]
    return result


def split_okurigana(surface, hiragana):
    """
    把假名注音只放在漢字上面。
    例：「歩く」讀「あるく」→ [歩(ある)] [く]
    """
    word = surface
    reading = hiragana

    # 拿掉後面相同的假名
    tail = ""
    while word != "" and reading != "" and is_kana(word[-1]) and to_hiragana(word[-1]) == reading[-1]:
        tail = word[-1] + tail
        word = word[:-1]
        reading = reading[:-1]

    # 拿掉前面相同的假名
    head = ""
    while word != "" and reading != "" and is_kana(word[0]) and to_hiragana(word[0]) == reading[0]:
        head = head + word[0]
        word = word[1:]
        reading = reading[1:]

    parts = []
    if head != "":
        parts.append({"text": head, "ruby": ""})
    if word != "":
        if has_kanji(word):
            parts.append({"text": word, "ruby": reading})
        else:
            parts.append({"text": word, "ruby": ""})
    if tail != "":
        parts.append({"text": tail, "ruby": ""})
    return parts


def feature_value(word, name):
    """從 fugashi 的斷詞結果拿資料，沒有就回傳 None"""
    value = getattr(word.feature, name, None)
    if value is None or value == "*" or value == "":
        return None
    return value


def japanese_word_token(surface, kana, pos, space):
    if all_punctuation(surface):
        return punctuation_token(surface, space)

    if kana is None and all_kana(surface):
        kana = to_katakana(surface)

    # 字典裡查不到讀音的漢字：改用 pykakasi 猜讀音
    if kana is None and has_kanji(surface):
        guess = ""
        for item in get_kakasi().convert(surface):
            guess += item["hira"]
        if guess != "":
            kana = to_katakana(guess)

    if kana is None:
        # 英文字母、數字等
        return make_token(surface, plain_parts(surface), surface, space, False,
                          count_latin_syllables(surface))

    roma = kana_to_romaji(kana)
    # 助詞的特別讀法：は→wa、へ→e、を→o
    if pos == POS_PARTICLE:
        if surface == "は":
            roma = "wa"
        elif surface == "へ":
            roma = "e"
        elif surface == "を":
            roma = "o"

    if has_kanji(surface):
        parts = split_okurigana(surface, to_hiragana(kana))
    else:
        parts = plain_parts(surface)

    # 助動詞、接尾詞黏在前面（例：「見た」→ mita，不是 mi ta）
    join = (pos == POS_AUXILIARY or pos == POS_SUFFIX) and not space
    return make_token(surface, parts, roma, space, join, count_mora(kana))


def japanese_tokens(text):
    tagger = get_tagger()
    if tagger is None:
        return japanese_tokens_simple(text)

    tokens = []
    for word in tagger(text):
        surface = word.surface
        kana = feature_value(word, "kana")
        pos = feature_value(word, "pos1")
        space = word.white_space != ""
        tokens.append(japanese_word_token(surface, kana, pos, space))
    return tokens


def japanese_tokens_simple(text):
    """沒有 fugashi 時的備用方案：只用 pykakasi"""
    tokens = []
    for item in get_kakasi().convert(text):
        original = item["orig"]
        space = original.startswith(" ")
        original = original.strip()
        if original == "":
            continue
        tokens.append(japanese_word_token(original, to_katakana(item["hira"]), "", space))
    return tokens


# ---------- 中文 ----------

def chinese_readings(piece, style):
    """一串漢字的讀音（拼音或注音），保證每個字一個讀音"""
    from pypinyin import lazy_pinyin

    readings = lazy_pinyin(piece, style=style)
    if len(readings) != len(piece):
        readings = []
        for ch in piece:
            readings.append(lazy_pinyin(ch, style=style)[0])
    return readings


def chinese_tokens(text):
    from pypinyin import Style

    tokens = []
    pending_space = False
    # 把句子切成「一串漢字」和「其他文字」
    for piece in re.findall(HANZI_PATTERN, text):
        if is_kanji(piece[0]):
            pinyin_list = chinese_readings(piece, Style.TONE)
            zhuyin_list = chinese_readings(piece, Style.BOPOMOFO)
            for index in range(len(piece)):
                token = make_token(piece[index], plain_parts(piece[index]), pinyin_list[index],
                                   pending_space, False, 1)
                token["zhuyin"] = zhuyin_list[index]
                tokens.append(token)
                pending_space = False
        else:
            more = word_tokens(piece, True)
            if len(more) > 0 and piece.startswith(" "):
                more[0]["space"] = True
            tokens.extend(more)
            if piece.endswith(" "):
                pending_space = True
    return tokens


# ---------- 韓文（簡易版羅馬字，不處理連音變化） ----------

KO_INITIAL = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
KO_VOWEL = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
            "yu", "eu", "ui", "i"]
KO_FINAL = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t",
            "t", "ng", "t", "t", "k", "t", "p", "t"]


def korean_to_roman(text):
    result = ""
    for ch in text:
        if is_hangul(ch):
            # 韓文一個字 = 初聲 + 中聲 + 終聲，用編號算出來
            code = ord(ch) - 0xAC00
            initial = code // 588
            vowel = (code % 588) // 28
            final = code % 28
            result += KO_INITIAL[initial] + KO_VOWEL[vowel] + KO_FINAL[final]
        else:
            result += ch
    return result


def korean_tokens(text):
    tokens = word_tokens(text, True)
    for token in tokens:
        if token["syl"] == 0 and token["join"]:
            continue  # 標點符號
        hangul_count = 0
        for ch in token["text"]:
            if is_hangul(ch):
                hangul_count += 1
        token["roma"] = korean_to_roman(token["text"])
        if hangul_count > 0:
            token["syl"] = hangul_count
    return tokens


# ---------- 讀音修正 {讀音} ----------

def strip_reading_marks(text):
    """去掉 {讀音} 標記，只留下歌詞文字（顯示、判斷語言用）"""
    return READING_MARK.sub("", text)


def split_reading_marks(text, language):
    """
    把一句歌詞切成好幾段：
      {"text": 一般的文字, "reading": None}
      {"text": 要改讀音的字, "reading": 你寫的讀音}
    要改讀音的字：
      日文 = {…} 前面連在一起的漢字（例：明日{あした}）
      中文 = {…} 前面的字，一個讀音一個字（例：還{ㄏㄨㄢˊ}、還是{ㄏㄞˊ ㄕˋ}）
      前面不是漢字的話，就是前面那一個字
    """
    pieces = []
    position = 0
    for match in READING_MARK.finditer(text):
        target_end = match.start()
        target_start = target_end
        most = len(text)   # 最多往前拿幾個字
        if language == "zh":
            most = len(match.group(1).split())
        while target_start > position and is_kanji(text[target_start - 1]) and target_end - target_start < most:
            target_start -= 1
        if target_start == target_end and target_end > position and text[target_end - 1].strip() != "":
            target_start = target_end - 1
        if target_start > position:
            pieces.append({"text": text[position:target_start], "reading": None})
        reading = match.group(1).strip()
        if target_start < target_end and reading != "":
            pieces.append({"text": text[target_start:target_end], "reading": reading})
        elif target_start < target_end:
            pieces.append({"text": text[target_start:target_end], "reading": None})
        position = match.end()
    if position < len(text):
        pieces.append({"text": text[position:], "reading": None})
    return pieces


def has_bopomofo(text):
    """有注音符號（ㄅㄆㄇ…）"""
    for ch in text:
        if "㄀" <= ch <= "ㄯ":
            return True
    return False


def fixed_reading_tokens(surface, reading, language):
    """用你寫的讀音做出 token"""
    if language == "ja":
        return [japanese_word_token(surface, to_katakana(reading), None, False)]
    if language == "zh":
        # 中文每個字一個 token；好幾個字的話，讀音用空格隔開，例如 還是{ㄏㄞˊ ㄕˋ}
        tokens = chinese_tokens(surface)
        readings = reading.split()
        if len(readings) != len(tokens):
            return tokens   # 讀音的數量跟字數對不起來，就不改
        for index in range(len(readings)):
            if has_bopomofo(readings[index]):
                tokens[index]["zhuyin"] = readings[index]
            else:
                tokens[index]["roma"] = readings[index]
        return tokens
    return plain_tokens(surface, language)


def plain_tokens(text, language):
    if language == "ja":
        return japanese_tokens(text)
    if language == "zh":
        return chinese_tokens(text)
    if language == "ko":
        return korean_tokens(text)
    return word_tokens(text, False)


# ---------- 對外使用的函式 ----------

def tokenize_line(text, language):
    tokens = []
    for piece in split_reading_marks(text, language):
        if piece["reading"] is None:
            more = plain_tokens(piece["text"], language)
        else:
            more = fixed_reading_tokens(piece["text"], piece["reading"], language)
        # 這一段前面有空格：第一個字要記得有空格
        if len(more) > 0 and len(tokens) > 0 and piece["text"][:1] == " ":
            more[0]["space"] = True
        tokens.extend(more)
    return tokens
