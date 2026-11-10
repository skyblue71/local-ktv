"""
「瀏覽器的耳朵」：用跟網頁一模一樣的方法（YIN 演算法）聽原唱。

為什麼需要：
  評分條是 AI（CREPE）寫的，唱歌時卻是瀏覽器裡的 YIN 在聽，
  兩隻「耳朵」不一樣，原唱自己唱（測試模式）也會被判 MISS。
  加歌時先用 YIN 把原唱聽一遍、記下來，評分時拿你的聲音也跟它比，
  兩邊就統一了。

這裡的每個數字都要跟 web\\js\\audio\\pitch-worklet.js 一樣，改一邊就要改另一邊。
"""
import math
import os

import numpy as np
import soundfile as sf

from server.audio_tools import convert_audio

# ---- 跟 pitch-worklet.js 一樣的設定 ----
BROWSER_RATE = 48000             # 瀏覽器播放的取樣率
RATE = BROWSER_RATE // 2         # 降取樣一半：24000
WINDOW = 1024                    # 每次分析多少點（約 0.04 秒）
STEP = 256                       # 每隔多少點分析一次（約 0.01 秒）
THRESHOLD = 0.15                 # YIN 門檻
FALLBACK = 0.5                   # 找不到時改用最低點（低於這個才算）
SUBHARMONIC_MARGIN = 0.2         # 次諧波修正
GATE = 0.006                     # 音量門檻（設定裡「靈敏度」的預設值）
MIN_LAG = RATE // 1100           # 最高音 1100Hz
MAX_LAG = RATE // 60             # 最低音 60Hz

# 倍頻加總（和聲修正）：兩個音疊在一起（例如主唱 D4 + 和聲 G4），
# 波形要很久才重複一次，YIN 會抓到一個「根本沒有聲音」的低音（G2）。
# 這時候基音幾乎沒聲音，就改看「誰的倍頻加起來最強」。
WEAK_BASE = 0.1                  # 基音不到最強倍頻的 1/10（-20dB）= 基音不見了
MAX_K = 6                        # 候選音：YIN 的頻率 ×1 ~ ×6
HARMONICS = 5                    # 每個候選音看 5 個倍頻
HARMONIC_WEIGHT = 0.8            # 越高的倍頻越不重要（第 h 個 × 0.8^(h-1)）
CONTINUITY = 0.8                 # 跟上一格差 1 個半音以內的候選音，分數有最高分的 0.8 倍就選它（線比較連續）
INDEX = np.arange(WINDOW)
HANN = 0.5 - 0.5 * np.cos(2 * math.pi * INDEX / (WINDOW - 1))   # Hann 窗

# 結果的格子：每 0.01 秒一格（跟 pitch.json 的 contour 一樣）
HOP_SECONDS = 0.01


def load_like_browser(path, work_dir):
    """
    讀音檔，變成跟瀏覽器聽到的一樣：
      轉成 48000Hz（瀏覽器播放的取樣率）→ 只拿第一個聲道（網頁只聽第一個）→ 每兩點平均成一點
    """
    temp_path = os.path.join(work_dir, "browser_ear_48k.wav")
    convert_audio(path, temp_path, BROWSER_RATE, 2)
    audio, _ = sf.read(temp_path, dtype="float32", always_2d=True)
    os.remove(temp_path)
    left = audio[:, 0]
    if len(left) % 2 == 1:
        left = left[:-1]
    return (left[0::2] + left[1::2]) * 0.5


def difference_function(frame):
    """
    YIN 第 2、3 步：波形跟「往後移 lag 格的自己」差多少，再做正規化。
    用 FFT 一次算出所有 lag（結果跟網頁的兩層迴圈一樣，只是快很多）。
    """
    length = WINDOW - MAX_LAG
    head = frame[:length]
    lags = np.arange(MAX_LAG + 1)
    # 差的平方和 = 前段能量 + 後段能量 - 2 × 兩段相乘
    energy_head = float(np.sum(head * head))
    squares = np.concatenate([[0.0], np.cumsum(frame * frame)])
    energy_shift = squares[lags + length] - squares[lags]
    spectrum = np.fft.rfft(frame, 2048) * np.conj(np.fft.rfft(head, 2048))
    cross = np.fft.irfft(spectrum, 2048)[:MAX_LAG + 1]
    d = energy_head + energy_shift - 2 * cross
    # 正規化（YIN 的關鍵步驟）：d[lag] × lag ÷ (d[1] 加到 d[lag] 的總和)
    normalized = np.ones(MAX_LAG + 1)
    running = np.cumsum(d[1:])
    safe = np.where(running > 0, running, 1.0)
    normalized[1:] = np.where(running > 0, d[1:] * lags[1:] / safe, 1.0)
    return normalized


def fix_subharmonic(d, best):
    """次諧波修正：週期 ÷6 到 ÷2 附近，只要沒有比原本差超過 SUBHARMONIC_MARGIN，就改用比較短的週期"""
    for k in range(6, 1, -1):
        candidate = int(round(best / k))
        if candidate < MIN_LAG:
            continue
        radius = max(1, int(round(candidate * 0.03)))
        low = max(MIN_LAG, candidate - radius)
        high = min(MAX_LAG, candidate + radius)
        lag = low + int(np.argmin(d[low:high + 1]))
        if d[lag] <= d[best] + SUBHARMONIC_MARGIN:
            return lag
    return best


def strength_at(weighted, hz):
    """某個頻率有多強（振幅）。weighted = 已經乘上 Hann 窗的聲音（網頁用 Goertzel 算，結果一樣）"""
    if hz >= RATE / 2:
        return 0.0
    angle = 2 * math.pi * hz / RATE * INDEX
    real = float(np.dot(weighted, np.cos(angle)))
    imag = float(np.dot(weighted, np.sin(angle)))
    return math.sqrt(real * real + imag * imag)


def choose_harmonic(frame, lag, previous_hz):
    """
    倍頻加總：回傳 k，真正的音高 = YIN 的頻率 × k（大部分時候 k = 1，不改）。
    只有「基音幾乎沒聲音」時才比：每個候選音把自己的倍頻強度加起來，最強的就是主唱。
    previous_hz = 上一格的結果（0 = 上一格沒聲音），分數差不多時選跟它連續的
    """
    weighted = frame * HANN
    base_hz = RATE / lag
    strengths = [0.0]                       # strengths[m] = 頻率 × m 有多強
    for m in range(1, MAX_K + 1):
        strengths.append(strength_at(weighted, base_hz * m))
    strongest = max(strengths[2:])
    if strongest <= 0 or strengths[1] >= strongest * WEAK_BASE:
        return 1                            # 基音有聲音：YIN 是對的
    for m in range(MAX_K + 1, MAX_K * HARMONICS + 1):
        strengths.append(strength_at(weighted, base_hz * m))
    scores = [0.0]                          # scores[k] = 候選音 × k 的倍頻加總
    best_k = 1
    for k in range(1, MAX_K + 1):
        if lag / k < MIN_LAG:
            break
        score = 0.0
        for h in range(1, HARMONICS + 1):
            score += strengths[k * h] * HARMONIC_WEIGHT ** (h - 1)
        scores.append(score)
        if score > scores[best_k]:
            best_k = k
    # 連續性：跟上一格接近（1 個半音以內）的候選音，分數夠高就選它
    if previous_hz > 0:
        for k in range(1, len(scores)):
            close = abs(12 * math.log2(base_hz * k / previous_hz)) <= 1
            if close and scores[k] >= scores[best_k] * CONTINUITY:
                return k
    return best_k


def find_pitch(frame, previous_hz=0.0):
    """一小段聲音的音高（Hz），聽不到就回傳 0。previous_hz = 上一格的結果"""
    rms = math.sqrt(float(np.mean(frame * frame)))
    if rms < GATE:
        return 0.0
    d = difference_function(frame)

    # 找第一個低於門檻的谷底
    best = -1
    for lag in range(MIN_LAG, MAX_LAG + 1):
        if d[lag] < THRESHOLD:
            while lag + 1 <= MAX_LAG and d[lag + 1] < d[lag]:
                lag += 1
            best = lag
            break
    # 找不到的話，改用最低的那一點
    if best == -1:
        lowest = MIN_LAG + int(np.argmin(d[MIN_LAG:MAX_LAG + 1]))
        if d[lowest] < FALLBACK:
            best = lowest
    if best == -1:
        return 0.0
    best = fix_subharmonic(d, best)

    # 拋物線內插，更精確
    better = float(best)
    if 1 < best < MAX_LAG:
        a, b, c = d[best - 1], d[best], d[best + 1]
        bottom = a + c - 2 * b
        if bottom != 0:
            better = best + (a - c) / (2 * bottom)
    # 和聲修正：基音不見了的話，改用倍頻加總最強的那個音
    k = choose_harmonic(frame, best, previous_hz)
    return RATE / better * k


def listen(path, work_dir, tuning, frame_count):
    """
    用瀏覽器的耳朵聽整首歌，回傳每 0.01 秒一格的音高（單位 0.1 半音，0 = 聽不到），
    格式跟 pitch.json 的 contour 一樣（已經扣掉調音偏差 tuning）。
    """
    samples = load_like_browser(path, work_dir).astype(np.float64)
    heard = [0] * frame_count
    analysis_count = (len(samples) - WINDOW) // STEP
    previous_hz = 0.0
    for n in range(analysis_count):
        frame = samples[n * STEP: n * STEP + WINDOW]
        hz = find_pitch(frame, previous_hz)
        previous_hz = hz
        if hz <= 0:
            continue
        # 這一段聲音「中間」的時間 → 對應到哪一格
        center = (n * STEP + WINDOW / 2) / RATE
        index = int(round(center / HOP_SECONDS))
        if 0 <= index < frame_count:
            midi = 69 + 12 * math.log2(hz / 440.0) - tuning
            heard[index] = int(round(midi * 10))
    return heard
