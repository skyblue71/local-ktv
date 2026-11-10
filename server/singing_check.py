"""
判斷原唱每一段是「歌詞」「像唱歌」還是「說話」，用來自動找出 MV 前後的劇情（要不要裁掉）。
（評分不用這份：評分只看歌詞，見 web\\js\\game\\lyricNotes.js）

把音符分成一段一段（停 PHRASE_GAP 秒以上算新的一段，只看原唱聽得到的音），每一段標成：
  lyrics   這一段裡有音落在歌詞範圍內
  singing  沒有歌詞，但音高穩：至少 SING_MIN_LENGTH 秒、音高穩穩停在音上的時間 ≥ SING_STABLE
           （注意：引擎聲這種很穩的聲音也會被標成這個，所以自動裁切不靠它）
  talking  沒有歌詞，而且音高一直滑（MV 劇情說話、零星的聲音）
實測：劇情對白 39～68%；沒歌詞但在唱的段落 75～86%；引擎聲 72%。

自動裁切：以「有歌詞的段落」當成歌：
  第一段歌詞之前有說話 → 開頭裁到最後一段說話結束；最後一段歌詞之後有說話 → 結尾裁到第一段說話開始。
  另外看歌詞：網路上的歌詞大多是「沒有劇情的版本」，歌詞的 0:00 如果落在影片的第 X 秒，
  影片前面那 X 秒就不是這首歌。那裡有人聲（說話、或音高很穩的聲音都算）就當成劇情，
  開頭裁到那裡面最後一段人聲結束（最晚 X 秒），前奏留著，唱歌前有時間準備。
  （例：某支 MV 前 19 秒是劇情，但大多是音效，說話只有 2 秒，只看說話會找不到）
"""

LYRIC_MARGIN = 0.3     # 歌詞每一句前後多留幾秒
PHRASE_GAP = 1.5       # 停這麼久以上算新的一段
SING_MIN_LENGTH = 1.0  # 沒歌詞的段落至少要這麼長才可能是唱歌（太短的零星聲音不算）
SING_STABLE = 0.72     # 沒歌詞的段落：音高穩在音上的時間要這麼多以上才算在唱歌
ON_PITCH = 0.5         # 原唱音高跟音符差 0.5 半音以內，算「穩在音上」
HEARD_MIN = 0.3        # 原唱聽得到的時間不到 30% 的音不看（評分器本來就會拿掉）

STORY_MIN = 3.0        # 說話加起來至少要這麼多秒，才算「劇情」（零星一兩聲不裁）
TRIM_AFTER_TALK = 0.5  # 開頭裁在最後一段說話結束後幾秒
TRIM_BEFORE_SING = 1.0 # 但至少要留第一段唱歌前這麼多秒（不要裁到歌）


def is_heard(note, heard, hop):
    if not heard or not hop:
        return True
    first = int(note["s"] / hop)
    last = max(first + 1, int(note["e"] / hop))
    voiced = 0
    for value in heard[first:last]:
        if value:
            voiced += 1
    return voiced / (last - first) >= HEARD_MIN


def in_lyrics(note, lines):
    """這個音符有沒有一半以上在歌詞某一句的範圍內"""
    inside = 0.0
    for line in lines:
        start = max(note["s"], line["start"] - LYRIC_MARGIN)
        end = min(note["e"], line["end"] + LYRIC_MARGIN)
        if end > start:
            inside += end - start
    return inside >= (note["e"] - note["s"]) * 0.5


def stability(phrase, contour, hop):
    """一段音符裡，原唱音高穩在音上的時間比例（0～1）"""
    voiced = 0
    on = 0
    for note in phrase:
        for k in range(int(note["s"] / hop), int(note["e"] / hop)):
            if k < len(contour) and contour[k]:
                voiced += 1
                if abs(contour[k] / 10.0 - note["p"]) <= ON_PITCH:
                    on += 1
    if voiced == 0:
        return 0.0
    return on / voiced


def classify_phrases(notes, lines, contour, heard, hop):
    """回傳每一段：[{"s": 開始, "e": 結束, "kind": "lyrics" | "singing" | "talking", "stable": 穩定度}, ...]"""
    groups = []
    for note in notes:
        if not is_heard(note, heard, hop):
            continue
        if len(groups) > 0 and note["s"] - groups[-1][-1]["e"] < PHRASE_GAP:
            groups[-1].append(note)
        else:
            groups.append([note])

    phrases = []
    for group in groups:
        start = group[0]["s"]
        end = group[-1]["e"]
        stable = stability(group, contour, hop)
        kind = "talking"
        has_lyrics = False
        for note in group:
            if in_lyrics(note, lines):
                has_lyrics = True
                break
        if has_lyrics:
            kind = "lyrics"
        elif end - start >= SING_MIN_LENGTH and stable >= SING_STABLE:
            kind = "singing"
        phrases.append({"s": round(start, 3), "e": round(end, 3), "kind": kind, "stable": round(stable, 3)})
    return phrases


def voice_before(phrases, time):
    """time 秒之前，沒有歌詞的人聲（說話、像唱歌的聲音）：
    回傳 (加起來幾秒, 最後一段在幾秒結束)；沒有人聲的話結束時間是 None"""
    total = 0.0
    last_end = None
    for phrase in phrases:
        if phrase["kind"] == "lyrics":
            continue
        end = min(phrase["e"], time)
        if end > phrase["s"]:
            total += end - phrase["s"]
            last_end = end
    return total, last_end


def suggest_story_trim(phrases, duration, song_zero=0.0):
    """
    自動找 MV 前後的劇情，回傳建議：
      {"start": 開頭裁到幾秒（0 = 不裁）, "end": 結尾裁到幾秒（0 = 不裁）,
       "talk_before": 開頭說話幾秒, "talk_after": 結尾說話幾秒,
       "song_zero": 用歌詞判斷時，歌從影片第幾秒開始（沒用到 = 0）, "voice_before": 那之前的人聲幾秒}
    song_zero：歌詞版本的 0:00 在影片的第幾秒（trim.lyrics_start_in_video）
    沒有劇情就回傳 None
    """
    sung = []
    for phrase in phrases:
        if phrase["kind"] == "lyrics":
            sung.append(phrase)
    if len(sung) == 0:
        return None
    first_sung = sung[0]
    last_sung = sung[-1]

    start = 0.0
    talk_before = 0.0
    last_talk_end = None
    for phrase in phrases:
        if phrase["kind"] == "talking" and phrase["e"] <= first_sung["s"]:
            talk_before += phrase["e"] - phrase["s"]
            last_talk_end = phrase["e"]
    if last_talk_end is not None and talk_before >= STORY_MIN:
        start = min(last_talk_end + TRIM_AFTER_TALK, first_sung["s"] - TRIM_BEFORE_SING)
        start = max(0.0, start)

    # 看歌詞：歌從影片第 song_zero 秒才開始，前面又有人聲 → 前面是劇情
    used_zero = 0.0
    voice = 0.0
    if song_zero > 0:
        voice, last_voice_end = voice_before(phrases, song_zero)
        if voice >= STORY_MIN:
            # 裁在最後一段人聲結束後一點點；最晚到歌的開頭，也不能裁到第一段唱歌
            zero_start = min(last_voice_end + TRIM_AFTER_TALK, song_zero, first_sung["s"] - TRIM_BEFORE_SING)
            if zero_start > start:
                start = zero_start
                used_zero = song_zero

    end = 0.0
    talk_after = 0.0
    first_talk_start = None
    for phrase in phrases:
        if phrase["kind"] == "talking" and phrase["s"] >= last_sung["e"]:
            talk_after += phrase["e"] - phrase["s"]
            if first_talk_start is None:
                first_talk_start = phrase["s"]
    if first_talk_start is not None and talk_after >= STORY_MIN:
        end = max(first_talk_start - TRIM_AFTER_TALK, last_sung["e"] + TRIM_BEFORE_SING)
        if duration and end >= duration:
            end = 0.0

    if start <= 0 and end <= 0:
        return None
    return {"start": round(start, 2), "end": round(end, 2),
            "talk_before": round(talk_before, 1), "talk_after": round(talk_after, 1),
            "song_zero": round(used_zero, 2), "voice_before": round(voice, 1)}
