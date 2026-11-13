"""
旋律音高分析：從「人聲」裡找出每個時間點的音高，再整理成一個一個的「音符」。

評分時就是拿你唱的音高跟這些音符比較。

流程：
  1. 把人聲轉成 16000Hz 單聲道
  2. 用 CREPE（AI 音高辨識）找出每 0.01 秒的音高
  3. 太小聲、不確定的地方當作「沒在唱」
  4. 平滑 → 對齊到半音 → 連續相同的音高合成一個音符
  5. 整理成像 KTV 的譜：小空隙接起來、碎音併起來
  6. 用「瀏覽器的耳朵」（browser_ear.py）也聽一遍，評分時拿來比對
"""
import math
import os

import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter, uniform_filter1d

from server import browser_ear
from server.audio_tools import convert_audio
from server.config import PITCH_HOP_SECONDS

SAMPLE_RATE = 16000
HOP = int(SAMPLE_RATE * PITCH_HOP_SECONDS)   # 160 個取樣點 = 0.01 秒
LOWEST_HZ = 60.0       # 最低音（大約 B1）
HIGHEST_HZ = 1100.0    # 最高音（大約 C#6）

# AI 的「信心度」高於這個值，才算「有在唱」
#   太高：小聲、有氣音的地方會被漏掉（有唱歌詞卻沒有評分條）
#   太低：AI 不確定的雜音也會被寫成音符
#   實測：0.45 → 有聲音的地方 69% 有音符；0.25 → 80%，間奏裡的假音符只多 0.2 秒
CONFIDENCE_LIMIT = 0.25
# 比整首最大聲小這麼多 dB 以上，就當作沒聲音
LOUDNESS_RANGE_DB = 35.0

# 整理音符，讓譜像 KTV 一樣（不要一截一截、不要碎音）
#   實測：一句裡斷開的地方 170 → 41 個，短於 0.15 秒的碎音 177 → 6 個
BRIDGE_GAP = 0.25      # 音符之間的空隙（子音、短換氣）短於這個就接起來
MIN_NOTE = 0.15        # 短於這個的碎音，併到相連而且音高比較接近的音符；
                       # 前後都沒有相連的（孤零零一小點）不是在唱，拿掉（drop_stray_notes）
                       #（例如一首歌的一個字唱完停 0.57 秒後的 0.08 秒雜音，
                       #  會變成評分條後面多一個小圓點、字幕填色拖 0.65 秒。全部 21 首有 64 個這種小點）


# ---------- 第 2 步：音高辨識 ----------

def detect_pitch_crepe(audio):
    """用 CREPE 找音高。回傳 (頻率陣列, 信心度陣列)
    用自己的 crepe_runner 跑（跟 torchcrepe 算法一樣），
    不載入 torchcrepe 套件本身，因為它會載入被 Windows 擋的 numba。"""
    from server import crepe_runner
    return crepe_runner.detect(audio, HOP, LOWEST_HZ, HIGHEST_HZ)


def detect_pitch(audio):
    """回傳 (頻率陣列, 信心度陣列, 用的是哪一個 AI)。CREPE 跑不起來就停下來（沒有備用方案）"""
    try:
        frequency, confidence = detect_pitch_crepe(audio)
    except Exception as error:
        raise RuntimeError("音高辨識失敗：" + str(error))
    return frequency, confidence, "crepe"


# ---------- 第 3 步：判斷哪裡有在唱 ----------

def frame_loudness_db(audio, frame_count):
    """計算每一格（0.01 秒）的音量，單位 dB"""
    window = 1024
    padded = np.pad(audio, (window // 2, window // 2 + HOP))
    loudness = np.zeros(frame_count)
    for i in range(frame_count):
        piece = padded[i * HOP: i * HOP + window]
        rms = math.sqrt(float(np.mean(piece * piece)) + 1e-12)
        loudness[i] = 20 * math.log10(rms)
    return loudness


def hz_to_midi(hz):
    """頻率轉成 MIDI 音高編號（69 = A4 = 440Hz，每加 1 就是高半音）"""
    return 69 + 12 * math.log2(hz / 440.0)


def fill_small_gaps(midi, voiced, max_gap=3):
    """很短的空隙（例如換氣、子音）補起來，讓同一句不會斷得太碎"""
    count = len(voiced)
    i = 0
    while i < count:
        if voiced[i]:
            i += 1
            continue
        gap_start = i
        while i < count and not voiced[i]:
            i += 1
        gap_end = i
        gap_length = gap_end - gap_start
        if gap_start > 0 and gap_end < count and gap_length <= max_gap:
            left = midi[gap_start - 1]
            right = midi[gap_end]
            for k in range(gap_start, gap_end):
                ratio = (k - gap_start + 1) / (gap_length + 1)
                midi[k] = left + (right - left) * ratio
                voiced[k] = True


def find_runs(voiced):
    """找出連續「有在唱」的區段，回傳 [(開始格, 結束格), ...]"""
    runs = []
    count = len(voiced)
    i = 0
    while i < count:
        if not voiced[i]:
            i += 1
            continue
        start = i
        while i < count and voiced[i]:
            i += 1
        runs.append((start, i))
    return runs


def estimate_tuning(midi_values):
    """
    估計整首歌的「調音偏差」。
    有些歌不是標準的 A=440Hz，例如整體偏高 0.2 個半音，這裡把它找出來。
    """
    if len(midi_values) == 0:
        return 0.0
    fraction = midi_values - np.round(midi_values)
    angle = fraction * 2 * math.pi
    mean_sin = float(np.mean(np.sin(angle)))
    mean_cos = float(np.mean(np.cos(angle)))
    return math.atan2(mean_sin, mean_cos) / (2 * math.pi)


# ---------- 第 4 步：整理成音符 ----------

def make_notes(midi, voiced, tuning):
    """
    把每 0.01 秒的音高，整理成音符清單：
      [{"s": 開始秒數, "e": 結束秒數, "p": 音高(半音編號)}, ...]
    """
    count = len(midi)
    semitone = np.full(count, -1, dtype=int)

    for start, end in find_runs(voiced):
        piece = midi[start:end] - tuning
        # 平滑：0.11 秒的移動平均（把顫音抹平）
        smooth = uniform_filter1d(piece, size=11, mode="nearest")
        rounded = np.round(smooth)
        # 中值濾波：去掉一閃而過的跳音
        rounded = median_filter(rounded, size=7, mode="nearest")
        semitone[start:end] = rounded.astype(int)

    # 連續相同音高 → 一個音符
    raw_notes = []
    i = 0
    while i < count:
        if semitone[i] < 0:
            i += 1
            continue
        j = i
        while j < count and semitone[j] == semitone[i]:
            j += 1
        raw_notes.append({
            "s": i * PITCH_HOP_SECONDS,
            "e": j * PITCH_HOP_SECONDS,
            "p": int(semitone[i]),
        })
        i = j

    # 清理：太短的音符併到前一個，或刪掉；同音高又靠很近的合併
    notes = []
    for note in raw_notes:
        duration = note["e"] - note["s"]
        if len(notes) > 0:
            last = notes[-1]
            gap = note["s"] - last["e"]
            if note["p"] == last["p"] and gap < 0.06:
                last["e"] = note["e"]
                continue
            if duration < 0.07 and gap < 0.02:
                last["e"] = note["e"]
                continue
        if duration < 0.07:
            continue
        notes.append(note)

    notes = connect_notes(notes)
    notes = merge_short_notes(notes)
    notes = merge_same_pitch(notes)
    notes = drop_stray_notes(notes)

    for note in notes:
        note["s"] = round(note["s"], 3)
        note["e"] = round(note["e"], 3)
    return notes


def connect_notes(notes):
    """音符之間很短的空隙（子音、短換氣）接起來：同一句的評分條才不會一截一截"""
    for index in range(len(notes) - 1):
        current = notes[index]
        following = notes[index + 1]
        if following["s"] - current["e"] < BRIDGE_GAP:
            current["e"] = following["s"]
    return notes


def touching(a, b):
    """兩個音符是不是連在一起（中間沒有空隙）"""
    return abs(b["s"] - a["e"]) < 0.005


def merge_short_notes(notes):
    """
    太短的碎音（短於 MIN_NOTE），併到相連、而且音高比較接近的那一個音符。
    前後都沒有相連的先留著，最後由 drop_stray_notes 拿掉。
    """
    index = 0
    while index < len(notes):
        note = notes[index]
        if note["e"] - note["s"] >= MIN_NOTE:
            index += 1
            continue

        left = None
        right = None
        if index > 0 and touching(notes[index - 1], note):
            left = notes[index - 1]
        if index + 1 < len(notes) and touching(note, notes[index + 1]):
            right = notes[index + 1]

        if left is None and right is None:
            index += 1
            continue

        # 選音高比較接近的那一邊
        target = left
        if left is None:
            target = right
        elif right is not None and abs(right["p"] - note["p"]) < abs(left["p"] - note["p"]):
            target = right

        target["s"] = min(target["s"], note["s"])
        target["e"] = max(target["e"], note["e"])
        notes.pop(index)
        index = max(0, index - 1)   # 合併後重新檢查前一個
    return notes


def merge_same_pitch(notes):
    """相連而且音高一樣的音符，合成一個"""
    result = []
    for note in notes:
        if len(result) > 0 and result[-1]["p"] == note["p"] and touching(result[-1], note):
            result[-1]["e"] = note["e"]
        else:
            result.append(note)
    return result


def drop_stray_notes(notes):
    """
    孤零零的一小點：短於 MIN_NOTE、前後都沒有相連的音符 → 拿掉。
    前後空隙都超過 BRIDGE_GAP 還這麼短，多半是唱完後的雜音、換氣、殘響，不是在唱；
    留著的話畫面上是一個唱不到的小圓點，字幕填色也會被拖長。
    （tools\\update_notes.py 用這個整理以前加的歌，不用重新分析音高）
    """
    result = []
    for index in range(len(notes)):
        note = notes[index]
        if note["e"] - note["s"] < MIN_NOTE:
            left = index > 0 and touching(notes[index - 1], note)
            right = index + 1 < len(notes) and touching(note, notes[index + 1])
            if not left and not right:
                continue
        result.append(note)
    return result


# ---------- 主程式 ----------

def analyze(audio_path, work_dir):
    """分析一個音訊檔，回傳可以存成 pitch.json 的資料"""
    temp_path = os.path.join(work_dir, "pitch_16k.wav")
    convert_audio(audio_path, temp_path, SAMPLE_RATE, 1)
    audio, _ = sf.read(temp_path, dtype="float32")
    os.remove(temp_path)

    frequency, confidence, engine = detect_pitch(audio)
    frame_count = len(frequency)
    loudness = frame_loudness_db(audio, frame_count)

    # 音量門檻：比最大聲小 LOUDNESS_RANGE_DB 以上就當作沒聲音
    loud_limit = max(-50.0, float(np.percentile(loudness, 99)) - LOUDNESS_RANGE_DB)

    midi = np.zeros(frame_count)
    voiced = np.zeros(frame_count, dtype=bool)
    for i in range(frame_count):
        is_singing = (
            confidence[i] > CONFIDENCE_LIMIT
            and loudness[i] > loud_limit
            and LOWEST_HZ <= frequency[i] <= HIGHEST_HZ
        )
        if is_singing:
            voiced[i] = True
            midi[i] = hz_to_midi(float(frequency[i]))

    fill_small_gaps(midi, voiced)
    tuning = estimate_tuning(midi[voiced])
    notes = make_notes(midi, voiced, tuning)

    # 旋律曲線（畫面上淡淡的參考線用），單位是 0.1 半音，0 代表沒聲音
    contour = []
    for i in range(frame_count):
        if voiced[i]:
            contour.append(int(round((midi[i] - tuning) * 10)))
        else:
            contour.append(0)

    # 用「瀏覽器的耳朵」（跟唱歌時一樣的 YIN）也聽一遍原唱，評分時拿來比對，兩邊才統一
    heard = browser_ear.listen(audio_path, work_dir, tuning, frame_count)

    low = 60
    high = 72
    if len(notes) > 0:
        low = min(n["p"] for n in notes)
        high = max(n["p"] for n in notes)

    return {
        "hop": PITCH_HOP_SECONDS,
        "engine": engine,
        "tuning": round(tuning, 3),
        "low": low,
        "high": high,
        "notes": notes,
        "contour": contour,   # AI（CREPE）聽到的原唱
        "heard": heard,       # 瀏覽器的耳朵（YIN）聽到的原唱
        "loudness": loudness_list(loudness),   # 人聲每一格多大聲（dB），字幕判斷句尾小聲的尾巴用
    }


def loudness_list(loudness):
    """每一格的音量（dB）存成整數清單（最小 -99，存檔小一點）"""
    result = []
    for value in loudness:
        result.append(int(round(max(-99.0, float(value)))))
    return result


def measure_loudness(audio_path, work_dir, frame_count):
    """只量人聲音量（不重新分析音高），給以前加的歌補資料用（tools\\update_notes.py）"""
    temp_path = os.path.join(work_dir, "loudness_16k.wav")
    convert_audio(audio_path, temp_path, SAMPLE_RATE, 1)
    audio, _ = sf.read(temp_path, dtype="float32")
    os.remove(temp_path)
    return loudness_list(frame_loudness_db(audio, frame_count))
