"""
認音節（做字幕時）用的小工具：把拼音對到 syllable_model 存好的 mms_emission.npy 上。

每個字的時間由 word_timeline.py 整首一次算。這裡是大家共用的：
  - spell：每個字的拼音（token 的 roma，日文是羅馬拼音、中文是拼音、英文就是原文），只留 a～z 和 '
  - align_line：一小段時間裡對一句（拼音前後各加一個「*」萬用字元，吸收不屬於這一句的聲音）
    整段搬家（song_alignment.py）、一起唱的第二句（word_timeline.py）用
  - token_beats：一個字有好幾拍（例如「光」hi・ka・ri）：每一拍從 MMS 聽到那一拍第一個字母的時間開始，
    字幕一拍一拍填色、評分條一拍一條；拍數對不上（beats.py）就整個字一起填
  - MIN_SCORE：AI 有沒有把握的界線（一句的平均、一個字母都用這條）
"""
import re

import numpy as np

from server import beats

FRAME_SECONDS = 0.02   # syllable_model 的每一格
MARGIN = 0.6           # 每一句前後多給幾秒
                       #   整段搬家（song_alignment.py）時：每個位置前後多聽這麼多秒、兩個位置差不到這麼多就不用換
# 一句的平均把握度（每個字母的機率平均）低於這個，這句不用 MMS、用猜的（word_timeline.spread_by_runs）
# 一個字第一個字母的把握度低於這個：AI 對這個字從哪裡開始沒把握，照音符（word_timeline.fit_to_runs）
#   17 首、673 句實測（「沒有換字痕跡的長音被切給好幾個字」舊→新、字移動超過 1 秒的比例）：
#     0.4 以上 68→14、12%｜0.2～0.4 41→15、17%｜0.1～0.2 30→19、19%｜0.05～0.1 10→7、19%｜0.05 以下 9→5、33%
#   低於 0.1 的句子長音幾乎沒改善、字卻常亂跳（多半是和聲很多的英文副歌），所以不用
MIN_SCORE = 0.1
# 一個字裡的某一拍，開始的地方落在長音（AI 抓到的一個音 HOLD_NOTE 秒以上）中間，
# 而且 MMS 對這一拍第一個字母的把握度低於 MIN_SCORE（跟整句的界線同一條：機率 10%）→ 不相信這一拍，
# 併回前一拍（beats 裡放 None：填色在那一段平均分、評分條不在那裡切）
#   全部歌實測（每一拍第一個字母的把握度中位數、低於 0.1 的比例）：
#     有明顯子音痕跡的拍子（一定是真換拍）1,112 拍：0.52、23%
#     落在「聲音沒有先變小再變大」的長音中間 46 拍：0.06、63% → 多半是 MMS 硬塞進去的
#   只看長音中間：其他地方就算把握度低也照用（真換拍也有 23% 偏低，切錯的影響也小）
HOLD_NOTE = 0.8
HOLD_EDGE = 0.12       # 離長音的開頭、結尾這麼近的不算「中間」（跟評分條 MIN_PIECE 一樣）

NOT_LETTER = re.compile(r"[^a-z']")


def spell(token):
    """這個字的拼音（只留 a～z 和 '），沒有就回傳空字串"""
    roma = token.get("roma") or token.get("text") or ""
    return NOT_LETTER.sub("", roma.lower())


def align_line(emission, spellings, window_start, window_end):
    """回傳 (每個字開始的秒數, 每個字裡每個字母的 (開始秒數, 把握度), 平均把握度)；對不了回傳 None"""
    import torch
    from torchaudio.pipelines import MMS_FA

    first = max(0, int(window_start / FRAME_SECONDS))
    last = min(len(emission), int(window_end / FRAME_SECONDS))
    if last - first < 5:
        return None
    piece = torch.from_numpy(np.asarray(emission[first:last], dtype=np.float32))
    tokenizer = MMS_FA.get_tokenizer()
    aligner = MMS_FA.get_aligner()
    try:
        spans = aligner(piece, tokenizer(["*"] + spellings + ["*"]))
    except Exception:
        return None   # 例如這一句太短，放不下這麼多字母
    starts = []
    letters = []
    scores = []
    for word_index in range(1, len(spellings) + 1):
        word_spans = spans[word_index]
        starts.append(round((first + word_spans[0].start) * FRAME_SECONDS, 3))
        letter_info = []
        for span in word_spans:
            scores.append(span.score)
            letter_info.append((round((first + span.start) * FRAME_SECONDS, 3), float(span.score)))
        letters.append(letter_info)
    return starts, letters, float(np.mean(scores))


def inside_hold(notes, time):
    """time 是不是落在一個長音（HOLD_NOTE 秒以上）的中間"""
    for note in notes:
        if note["s"] > time:
            break
        if note["e"] - note["s"] >= HOLD_NOTE and note["s"] + HOLD_EDGE < time < note["e"] - HOLD_EDGE:
            return True
    return False


def token_beats(token, spelling, letter_info, notes):
    """這個字每一拍開始的秒數（第一拍＝這個字開始；不相信的拍子放 None，見 HOLD_NOTE）。
    回傳 (beats, 每一拍在畫面上從這個字的幾 % 開始, 在下面那行羅馬拼音從幾 % 開始)；
    切不出來回傳 None（整個字一起填）"""
    positions = beats.beat_starts(token["text"], spelling, token["syl"])
    if positions is None or len(letter_info) != len(spelling):
        return None
    result = []
    previous = token["start"]
    for index in range(len(positions)):
        if index == 0:
            result.append(round(token["start"], 3))
            continue
        time, score = letter_info[positions[index]]
        time = max(previous, time)
        if time >= token["end"]:
            return None   # 拍子跑到這個字結束之後：不可信，整個字一起填
        if score < MIN_SCORE and inside_hold(notes, time):
            result.append(None)   # 長音中間又沒把握：併回前一拍
            continue
        result.append(round(time, 3))
        previous = time
    return result, beats.beat_widths(token, positions, spelling), beats.letter_widths(positions, spelling)


