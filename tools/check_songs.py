"""
全部歌健檢：照唱歌畫面放評分條的算法（server\\game_bars.py）看每首歌，列出可疑的地方和時間點，可以拿去用耳朵確認。
改了字幕、評分條的算法之後跑一次，可以跟上一次的結果比。

檢查的項目（都用程式裡本來就有的數字）：
  1. 沒有字在填色的評分條：這條評分條的時間裡，沒有任何一個字正在填色
     （在一句的第一個字之前＝句首前，在最後一個字之後＝字填完了還有評分條，或兩個字中間）
     評分條照句子的時間放、字的填色照字的時間，所以字的時間算錯的地方會有幾條（填色可能不準的地方）
  2. 猜的字從長音中間開始：AI 沒把握、照音符猜的句子裡，字的開始落在一個長音
     （syllable_aligner 的 HOLD_NOTE）中間（離頭尾 HOLD_EDGE 以上）→ 填色多半猜錯了
     （AI 算的句子不看：同一個音高連唱兩個字，AI 聽得到換字，是正常的）
  3. AI 聽不懂的句子：MMS 沒把握（< MIN_SCORE），字的時間是照音符猜的
  4. 有歌詞、沒評分條：整句一條評分條都沒有（字幕可能放錯地方、或原唱那裡真的沒聲音）
  5. 沒歌詞、有人唱：句子外面（沒有句子在唱的地方），原唱有聲音（瀏覽器的耳朵聽得到、而且比歌聲小不到你設的「清掉小聲雜音」dB）
     → 可能是歌詞檔漏了句子、和聲、MV 劇情，或分人聲沒分乾淨
  6. 字擠太快：一句平均每個音節不到 MIN_SING_SYLLABLE 秒（一秒唱不了那麼多字）
  7. 句子裡有人唱、沒評分條：句子的時間裡，原唱有聲音（瀏覽器的耳朵聽得到、比歌聲小不到「清掉小聲雜音」dB），
     卻沒有評分條的地方（連續 SHORTEST 以上才算）
  另外列每首歌填色最久的 3 個字（只是參考，不算問題）

執行方式（在專案資料夾底下，start.bat 開著也沒關係；只讀資料，不改任何歌）：
  .venv\\Scripts\\python -X utf8 tools\\check_songs.py
結果：
  畫面上是每首歌的數量，和上一次比的差別
  健檢報告.md：每一個可疑地方的時間點
  data\\health_check.json：這次的數量（下次比較用；上一次的改名成 health_check_previous.json）
"""
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from server import game_bars, song_store  # noqa: E402
from server.word_timeline import MIN_SING_SYLLABLE, TINY  # noqa: E402
from server.syllable_aligner import HOLD_EDGE, HOLD_NOTE  # noqa: E402

REPORT_PATH = os.path.join(ROOT, "健檢報告.md")
SNAPSHOT_PATH = os.path.join(ROOT, "data", "health_check.json")
PREVIOUS_PATH = os.path.join(ROOT, "data", "health_check_previous.json")

ITEMS = [
    ("after_fill", "沒有字在填色的評分條", "條"),
    ("mid_hold", "猜的字從長音中間開始", "個字"),
    ("ai_unsure", "AI 聽不懂的句子", "句"),
    ("no_bars", "有歌詞、沒評分條", "句"),
    ("no_lyrics", "沒歌詞、有人唱", "秒"),
    ("crammed", "字擠太快", "句"),
    ("unbarred", "句子裡有人唱、沒評分條", "秒"),
]


def clock(seconds):
    """秒數 → 分:秒（例如 2:03.24）"""
    minutes = int(seconds // 60)
    return "%d:%05.2f" % (minutes, seconds - minutes * 60)


def sung(tokens):
    result = []
    for token in tokens:
        if token.get("syl", 0) > 0:
            result.append(token)
    return result


def owner_line(bar, lines):
    """這條評分條算哪一句：跟句子時間重疊最多的；都沒重疊就算離最近的那一句"""
    best = None
    best_score = None
    for line in lines:
        overlap = min(bar["e"], line["end"]) - max(bar["s"], line["start"])
        if overlap <= 0:
            overlap = -min(abs(bar["s"] - line["end"]), abs(line["start"] - bar["e"]))
        if best_score is None or overlap > best_score:
            best = line
            best_score = overlap
    return best


def frames_median(values, hop, pieces):
    """這幾段時間裡，每一格數值的中位數（沒有資料回傳 None）"""
    if not values or hop <= 0:
        return None
    picked = []
    for start, end in pieces:
        picked.extend(v for v in values[int(start / hop):int(end / hop)] if v is not None)
    if not picked:
        return None
    return statistics.median(picked)


def heard_part(heard, hop, start, end):
    if not heard or hop <= 0:
        return None
    part = heard[int(start / hop):max(int(start / hop) + 1, int(end / hop))]
    if not part:
        return None
    return sum(1 for v in part if v) / len(part)


def check_song(meta):
    folder = song_store.song_dir(meta["id"])
    lyrics = song_store.read_json(os.path.join(folder, "lyrics.json"), None)
    pitch = song_store.read_json(os.path.join(folder, "pitch.json"), None)
    if not lyrics or not lyrics.get("synced") or not pitch:
        return None
    chart = song_store.read_json(os.path.join(folder, "chart.json"), None)
    chart_notes = None
    if isinstance(chart, dict):
        chart_notes = chart.get("notes")
    elif isinstance(chart, list):
        chart_notes = chart
    bars, lines = game_bars.game_bars(lyrics, pitch, meta, chart_notes)
    notes = pitch.get("notes", [])
    hop = pitch.get("hop", 0.01)
    found = {key: [] for key, _, _ in ITEMS}

    # 1. 沒有字在填色的評分條
    for bar in bars:
        filling = False
        for line in lines:
            for token in sung(line["tokens"]):
                if token["start"] < bar["e"] and token["end"] > bar["s"]:
                    filling = True
                    break
            if filling:
                break
        if filling:
            continue
        line = owner_line(bar, lines)
        if line is None or not sung(line["tokens"]):
            continue
        words = sung(line["tokens"])
        if bar["e"] <= words[0]["start"]:
            where = "句首前，第一個字 %s 才開始" % clock(words[0]["start"])
        elif bar["s"] >= words[-1]["end"]:
            where = "字填完之後，最後一個字 %s 填完" % clock(words[-1]["end"])
        else:
            where = "兩個字中間，那時候沒有字在填"
        found["after_fill"].append((bar["s"], "%s～%s（%s）｜%s" % (
            clock(bar["s"]), clock(bar["e"]), where, line["text"])))

    # 2. 猜的字從長音中間開始（AI 算的句子不看）
    for line in lines:
        if line.get("mms"):
            continue
        for token in sung(line["tokens"]):
            for note in notes:
                if note["s"] > token["start"]:
                    break
                long_enough = note["e"] - note["s"] >= HOLD_NOTE
                if long_enough and note["s"] + HOLD_EDGE < token["start"] < note["e"] - HOLD_EDGE:
                    found["mid_hold"].append((token["start"], "%s「%s」在長音 %s～%s 中間開始｜%s" % (
                        clock(token["start"]), token["text"], clock(note["s"]), clock(note["e"]), line["text"])))
                    break

    # 3. AI 聽不懂的句子（這首有用 MMS 才看）
    if lyrics.get("syllables") == "mms":
        for line in lines:
            if not line.get("mms"):
                found["ai_unsure"].append((line["start"], "%s 把握度 %s｜%s" % (
                    clock(line["start"]), line.get("mms_score", "沒有"), line["text"])))

    # 4. 有歌詞、沒評分條
    trim_start, trim_end = game_bars.trim_range(meta)
    for line in lines:
        if line["end"] <= trim_start or line["start"] >= trim_end or not sung(line["tokens"]):
            continue
        has_bar = False
        for bar in bars:
            if bar["e"] > line["start"] and bar["s"] < line["end"]:
                has_bar = True
                break
        if not has_bar:
            found["no_bars"].append((line["start"], "%s～%s｜%s" % (
                clock(line["start"]), clock(line["end"]), line["text"])))

    # 5. 沒歌詞、有人唱：連在一起（中間沒停）的音算一段
    singing = frames_median(pitch.get("loudness"), hop, [(bar["s"], bar["e"]) for bar in bars])
    ranges = game_bars.line_ranges(lines)
    runs = []
    for note in notes:
        if note["e"] <= trim_start or note["s"] >= trim_end:
            continue
        outside = True
        for range_start, range_end in ranges:
            if note["e"] > range_start and note["s"] < range_end:
                outside = False
                break
        if not outside:
            continue
        if runs and note["s"] - runs[-1][1] <= TINY:
            runs[-1][1] = note["e"]
        else:
            runs.append([note["s"], note["e"]])
    for start, end in runs:
        ratio = heard_part(pitch.get("heard"), hop, start, end)
        if ratio is not None and ratio < game_bars.UNHEARD_LIMIT:
            continue
        level = frames_median(pitch.get("loudness"), hop, [(start, end)])
        quieter = None
        if singing is not None and level is not None:
            quieter = singing - level
            if quieter >= game_bars.DEFAULT_QUIET_DB:
                continue   # 很小聲：本來就會被當成雜音
        text = "%s～%s（%.1f 秒" % (clock(start), clock(end), end - start)
        if quieter is not None:
            text += "，比歌聲小 %.0f dB" % quieter
        found["no_lyrics"].append((start, text + "）", end - start))

    # 6. 字擠太快
    for line in lines:
        words = sung(line["tokens"])
        if not words:
            continue
        syllables = sum(token["syl"] for token in words)
        length = words[-1]["end"] - words[0]["start"]
        if syllables > 0 and length / syllables < MIN_SING_SYLLABLE:
            found["crammed"].append((line["start"], "%s %d 個音節擠在 %.2f 秒｜%s" % (
                clock(line["start"]), syllables, length, line["text"])))

    # 7. 句子裡有人唱、沒評分條（歌聲多大聲照 AI 寫的音符算，跟評分條怎麼放無關，改前改後可以比）
    heard = pitch.get("heard")
    loudness = pitch.get("loudness")
    voice = frames_median(loudness, hop, [(note["s"], note["e"]) for note in notes])
    if heard and loudness and voice is not None:
        size = min(len(heard), len(loudness))
        inside = [False] * size
        for line in lyrics["lines"]:
            if sung(line.get("tokens", [])):
                first = max(0, int(max(line["start"], trim_start) / hop))
                last = min(size, int(min(line["end"], trim_end) / hop))
                for index in range(first, last):
                    inside[index] = True
        for bar in bars:
            for index in range(max(0, int(bar["s"] / hop)), min(size, int(bar["e"] / hop))):
                inside[index] = False
        begin = None
        for index in range(size + 1):
            loud_here = index < size and inside[index] and loudness[index] >= voice - game_bars.DEFAULT_QUIET_DB
            if loud_here and begin is None:
                begin = index
            if not loud_here and begin is not None:
                start, end = begin * hop, index * hop
                heard_frames = sum(1 for k in range(begin, index) if heard[k] != 0)
                frames = index - begin
                begin = None
                # 瀏覽器的耳朵一半以上的時間聽得到音高（跟補評分條 fill_missed 同一個標準）
                if end - start >= game_bars.SHORTEST and heard_frames >= frames * 0.5:
                    line = owner_line({"s": start, "e": end}, lyrics["lines"])
                    found["unbarred"].append((start, "%s～%s（%.2f 秒）｜%s" % (
                        clock(start), clock(end), end - start, line["text"] if line else ""), end - start))

    # 參考：填色最久的 3 個字
    longest = []
    for line in lines:
        for token in sung(line["tokens"]):
            longest.append((token["end"] - token["start"], token, line))
    longest.sort(key=lambda item: -item[0])
    top = ["%s「%s」%.1f 秒｜%s" % (clock(t["start"]), t["text"], length, ln["text"]) for length, t, ln in longest[:3]]

    counts = {}
    for key, _, unit in ITEMS:
        if unit == "秒":
            counts[key] = round(sum(item[2] for item in found[key]), 1)
        else:
            counts[key] = len(found[key])
    return {"title": meta["title"], "counts": counts, "found": found, "longest": top}


def write_report(results):
    out = ["# 健檢報告", "", "照唱歌畫面放評分條的算法看每首歌（清掉小聲雜音用預設 %g dB）。時間點可以拿去聽，確認是不是真的有問題。" %
           game_bars.DEFAULT_QUIET_DB, ""]
    out.append("| 歌 | " + " | ".join(label for _, label, _ in ITEMS) + " |")
    out.append("|---|" + "---|" * len(ITEMS))
    for result in results:
        out.append("| %s | " % result["title"][:30] + " | ".join(str(result["counts"][key]) for key, _, _ in ITEMS) + " |")
    out.append("")
    for result in results:
        out.append("## " + result["title"])
        for key, label, unit in ITEMS:
            items = sorted(result["found"][key], key=lambda item: item[0])
            if not items:
                continue
            out.append("**%s**（%s %s）" % (label, result["counts"][key], unit))
            for item in items:
                out.append("- " + item[1])
        out.append("**填色最久的字**（參考）")
        for text in result["longest"]:
            out.append("- " + text)
        out.append("")
    with open(REPORT_PATH, "w", encoding="utf8") as file:
        file.write("\n".join(out))


def main():
    results = []
    for meta in song_store.list_songs():
        if meta.get("status") != "ready":
            continue
        result = check_song(meta)
        if result is not None:
            results.append(result)
    results.sort(key=lambda result: result["title"])

    previous = {}
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH, encoding="utf8") as file:
            previous = json.load(file)

    totals = {key: 0 for key, _, _ in ITEMS}
    old_totals = {key: 0 for key, _, _ in ITEMS}
    snapshot = {}
    for result in results:
        snapshot[result["title"]] = result["counts"]
        old = previous.get(result["title"], {})
        changes = []
        for key, label, unit in ITEMS:
            totals[key] += result["counts"][key]
            old_totals[key] += old.get(key, 0)
            if key in old and old[key] != result["counts"][key]:
                changes.append("%s %s→%s" % (label, old[key], result["counts"][key]))
        line = result["title"][:32] + "：" + "、".join(
            "%s %s" % (label, result["counts"][key]) for key, label, _ in ITEMS if result["counts"][key])
        print(line if line.endswith("：") is False else result["title"][:32] + "：沒有可疑的地方")
        if changes:
            print("    跟上次比：" + "、".join(changes))
    print("\n全部：" + "、".join("%s %s %s" % (label, round(totals[key], 1), unit) for key, label, unit in ITEMS))
    if previous:
        print("上次：" + "、".join("%s %s %s" % (label, round(old_totals[key], 1), unit) for key, label, unit in ITEMS))

    write_report(results)
    if os.path.exists(SNAPSHOT_PATH):
        os.replace(SNAPSHOT_PATH, PREVIOUS_PATH)
    with open(SNAPSHOT_PATH, "w", encoding="utf8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=1)
    print("\n詳細的時間點在 健檢報告.md")


main()
