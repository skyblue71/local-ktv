"""
從 LRCLIB（免費公開的歌詞資料庫）搜尋歌詞。
網址：https://lrclib.net
"""
import re

import requests

from server.config import LRCLIB_SEARCH_URL, USER_AGENT

# 時間標記，例如 [01:23.45]
TIME_TAG = re.compile(r"\[\d+:\d+")
# 至少要有幾個時間標記，才算真的「有時間軸」
MIN_TIME_TAGS = 3


def has_time_tags(text):
    """
    LRCLIB 上有些人上傳的「有時間軸歌詞」其實一個時間都沒有（只是純文字），
    不檢查的話會被標成「有時間軸」，用了才發現沒有。
    """
    return len(TIME_TAG.findall(text)) >= MIN_TIME_TAGS


def _request(params):
    try:
        response = requests.get(
            LRCLIB_SEARCH_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        if response.status_code != 200:
            return []
        return response.json()
    except Exception as error:
        print("歌詞搜尋失敗：", error)
        return []


def search(title, artist=""):
    """回傳搜尋結果清單（最多 20 筆）"""
    title = (title or "").strip()
    artist = (artist or "").strip()

    items = []
    if title != "":
        params = {"track_name": title}
        if artist != "":
            params["artist_name"] = artist
        items = _request(params)

    # 找不到的話，改用關鍵字搜尋
    if len(items) == 0:
        keyword = (title + " " + artist).strip()
        if keyword != "":
            items = _request({"q": keyword})

    # 還是找不到、而且有填歌手：只用歌名再找一次（歌手名稱常常跟資料庫寫的不一樣，例如 YouTube 頻道名）
    if len(items) == 0 and title != "" and artist != "":
        items = _request({"track_name": title})

    results = []
    for item in items[:20]:
        synced = item.get("syncedLyrics") or ""
        plain = item.get("plainLyrics") or ""
        # 標了有時間軸、其實沒有時間：當成「只有文字」
        if synced != "" and not has_time_tags(synced):
            if plain == "":
                plain = synced
            synced = ""
        # 專輯名稱是空值（LRCLIB 上有人填 "null"、"-"）就當成沒有，畫面不要顯示怪字
        album = (item.get("albumName") or "").strip()
        if album.lower() in ("null", "none", "-", "?"):
            album = ""
        results.append({
            "id": item.get("id"),
            "title": item.get("trackName") or "",
            "artist": item.get("artistName") or "",
            "album": album,
            "duration": item.get("duration") or 0,
            "synced": synced,
            "plain": plain,
        })
    return results


def find_best(title, artist, duration):
    """
    自動挑一個最適合的「有時間軸」歌詞：
    歌曲長度越接近越好（差太多代表可能是不同版本）。
    """
    results = search(title, artist)
    best = None
    best_difference = 9999
    for result in results:
        if result["synced"] == "":
            continue
        if duration and result["duration"]:
            difference = abs(result["duration"] - duration)
        else:
            difference = 30
        if difference < best_difference:
            best = result
            best_difference = difference

    if best is not None and best_difference <= 15:
        return best
    return None
