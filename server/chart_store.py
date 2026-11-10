"""
你自己修過的譜（評分條）：存在每首歌資料夾的 chart.json。

  有 chart.json → 唱歌時用你修的譜（你畫的就算，不再自動過濾）
  沒有          → 照舊用 AI 做的譜（pitch.json 的 notes，只算有歌詞的部分）

AI 的譜（pitch.json）不會被改到，所以隨時可以「還原 AI 的譜」（刪掉 chart.json 就好）。
重新處理歌曲也不會蓋掉你修的譜。

每個音符：{"s": 開始秒數, "e": 結束秒數, "p": 音高(半音編號), "u": 1}
  u = 1 代表「你畫的或改過的」：評分時只照你畫的音高比、不管 AI 有沒有聽到（不會被拿掉）
  沒有 u 的是 AI 原本的音，跟以前一樣評分
"""
import os

from server import song_store

CHART_FILE = "chart.json"
MAX_NOTES = 5000          # 一首歌最多幾個音符（擋掉奇怪的資料）
MIN_LENGTH = 0.05         # 一個音最短幾秒
LOWEST_PITCH = 24         # 音高範圍（C1 ～ C8）
HIGHEST_PITCH = 108


def chart_path(song_id):
    return song_store.song_file(song_id, CHART_FILE)


def get_chart(song_id):
    """回傳你修過的音符清單；沒修過回傳 None"""
    data = song_store.read_json(chart_path(song_id))
    if data is None:
        return None
    return data.get("notes", [])


def clean_notes(notes, duration):
    """檢查、整理送來的音符：數字要合理、照時間排好。不合理就丟出 ValueError（訊息會給使用者看）"""
    if len(notes) > MAX_NOTES:
        raise ValueError("音符太多了（最多 %d 個）" % MAX_NOTES)
    result = []
    for note in notes:
        start = round(float(note["s"]), 3)
        end = round(float(note["e"]), 3)
        pitch = int(round(float(note["p"])))
        if start < 0 or end - start < MIN_LENGTH:
            raise ValueError("有音符的時間不對")
        if duration and start > duration:
            raise ValueError("有音符超過歌曲長度")
        if pitch < LOWEST_PITCH or pitch > HIGHEST_PITCH:
            raise ValueError("有音符的音高不對")
        cleaned = {"s": start, "e": end, "p": pitch}
        if note.get("u"):
            cleaned["u"] = 1
        result.append(cleaned)
    result.sort(key=lambda n: n["s"])
    return result


def save_chart(song_id, notes):
    meta = song_store.get_meta(song_id)
    cleaned = clean_notes(notes, meta.get("duration", 0))
    song_store.write_json(chart_path(song_id), {"notes": cleaned})
    song_store.update_meta(song_id, {"has_chart": True})
    return cleaned


def delete_chart(song_id):
    path = chart_path(song_id)
    if os.path.exists(path):
        os.remove(path)
    song_store.update_meta(song_id, {"has_chart": False})
