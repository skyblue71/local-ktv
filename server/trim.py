"""
裁切：只唱歌曲的一部分（例如 MV 前面的劇情、後面的片尾不要）。

不會真的剪檔案，只在 meta.json 記住：
  trim_start  從第幾秒開始唱（0 = 從頭）
  trim_end    唱到第幾秒（0 = 唱到最後）
隨時可以改回來。

裁切只決定「播哪一段」，跟歌詞的時間無關：
歌詞永遠照整支影片的時間，放在歌手真的唱的地方（lyrics_builder 的自動對齊、song_alignment 的一段一段對齊）。
"""

MIN_LENGTH = 10.0       # 裁切後至少要留幾秒


def lyrics_start_in_video(meta, lyrics):
    """歌詞檔的 0:00（歌詞那個版本的開頭）落在影片的第幾秒
    = 字幕程式算好的 song_zero（整體偏移 + 整首自動移的秒數 + 第一段整段搬家的秒數）"""
    if lyrics.get("song_zero") is not None:
        return float(lyrics["song_zero"])
    # 舊的字幕（還沒重新產生過）
    seconds = (meta.get("lyrics_offset", 0) or 0) / 1000.0
    seconds += float(lyrics.get("auto_shift", 0) or 0)
    return seconds


def check_range(start, end, duration):
    """檢查裁切範圍，回傳整理好的 (開始, 結束)；不合理就丟出 ValueError（訊息會顯示給使用者）"""
    start = max(0.0, float(start or 0))
    end = float(end or 0)
    if end <= 0 or end >= duration:
        end = 0.0   # 0 = 唱到最後
    real_end = duration
    if end > 0:
        real_end = end
    if start >= duration:
        raise ValueError("開始的時間超過歌曲長度了")
    if real_end - start < MIN_LENGTH:
        raise ValueError("裁切後至少要留 " + str(int(MIN_LENGTH)) + " 秒")
    return round(start, 2), round(end, 2)
