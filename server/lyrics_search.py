"""
從 LRCLIB（免費公開的歌詞資料庫）搜尋歌詞。
網址：https://lrclib.net
"""
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from server.config import LRCLIB_SEARCH_URL, USER_AGENT
from server.lrc_parser import LINE_TIME, WORD_TIME, to_seconds

# 時間標記，例如 [01:23.45]
TIME_TAG = re.compile(r"\[\d+:\d+")
# 至少要有幾個時間標記，才算真的「有時間軸」
MIN_TIME_TAGS = 3
# 自動挑歌詞時，長度差幾秒以內才算同一個版本
SAME_VERSION_SECONDS = 15


def has_time_tags(text):
    """
    LRCLIB 上有些人上傳的「有時間軸歌詞」其實一個時間都沒有（只是純文字），
    不檢查的話會被標成「有時間軸」，用了才發現沒有。
    """
    return len(TIME_TAG.findall(text)) >= MIN_TIME_TAGS


def last_time(synced):
    """歌詞裡最晚的一個時間（秒）；沒有時間回傳 0"""
    latest = 0
    for minutes, seconds in LINE_TIME.findall(synced) + WORD_TIME.findall(synced):
        latest = max(latest, to_seconds(minutes, seconds))
    return latest


def real_length(result):
    """
    這份歌詞是給多長的歌用的（秒）。兩個都看，取比較長的：
      1. 資料庫上標的長度
      2. 歌詞最後一句的時間
    有些歌詞標的長度是錯的（例如標 1:59，最後一句卻在 4:41）。兩個都不知道回傳 0
    """
    return max(result["duration"], result["lyrics_end"])


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


def _queries(title, artist):
    """
    要問資料庫的幾種問法，越前面的越貼近你打的字。
    資料庫每一種問法最多回 20 份，幾種合起來才列得完整：
      歌名＋歌手 → 只用歌名（歌手名稱常常跟資料庫寫的不一樣，例如 YouTube 頻道名）→ 關鍵字
    """
    queries = []
    if title != "" and artist != "":
        queries.append({"track_name": title, "artist_name": artist})
    if title != "":
        queries.append({"track_name": title})
    keyword = (title + " " + artist).strip()
    if keyword != "":
        queries.append({"q": keyword})
    return queries


def search(title, artist=""):
    """
    回傳搜尋結果清單：幾種問法找到的全部列出來，同一份只留一次。
    每一份的 found_by 是「第幾種問法先找到的」（0 = 最貼近你打的字）
    """
    title = (title or "").strip()
    artist = (artist or "").strip()

    queries = _queries(title, artist)
    if len(queries) == 0:
        return []
    # 幾種問法同時問，不用一個一個等
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        answers = list(pool.map(_request, queries))

    results = []
    seen_ids = set()
    for found_by in range(len(answers)):
        for item in answers[found_by]:
            if item.get("id") in seen_ids:
                continue
            seen_ids.add(item.get("id"))

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
                "lyrics_end": last_time(synced),
                "found_by": found_by,
                "synced": synced,
                "plain": plain,
            })
    return results


def find_best(title, artist, duration):
    """
    自動挑一個最適合的「有時間軸」歌詞：
    歌曲長度越接近越好（差太多代表可能是不同版本）。
    只從最貼近歌名、歌手的那一種問法找到的裡面挑（其他的可能是同名的別首歌）。
    """
    results = search(title, artist)
    if len(results) == 0:
        return None
    closest_query = results[0]["found_by"]

    best = None
    best_difference = 9999
    for result in results:
        if result["found_by"] != closest_query or result["synced"] == "":
            continue
        length = real_length(result)
        if duration and length:
            difference = abs(length - duration)
        else:
            difference = 30
        if difference < best_difference:
            best = result
            best_difference = difference

    if best is not None and best_difference <= SAME_VERSION_SECONDS:
        return best
    return None
