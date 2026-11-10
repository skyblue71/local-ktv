"""
歌曲資料的讀寫。

每首歌是 data/songs/<歌曲ID>/ 一個資料夾，裡面會有：
  meta.json          歌曲基本資料（標題、歌手、處理狀態…）
  original.xxx       上傳的原始檔案
  instrumental.flac  伴奏
  vocals.flac        人聲（導唱用、評分參考）
  pitch.json         旋律音高資料（評分用，AI 做的譜）
  chart.json         你自己修過的譜（有的話唱歌時用這份，chart_store.py）
  lyrics.lrc         歌詞原文（LRC 格式）
  lyrics.json        處理好的字幕（含假名、羅馬音、每個字的時間）
  scores.json        分數紀錄
  cover.jpg          封面圖片
"""
import json
import os
import re
import shutil
import threading
import time
import uuid

from server.config import SONGS_DIR

# 背景處理和網頁請求可能同時讀寫檔案，用一把「鎖」避免互相打架
_file_lock = threading.Lock()


# ---------- 路徑 ----------

def is_valid_id(song_id):
    """檢查歌曲 ID 只包含英文、數字、減號（避免有人傳奇怪的路徑進來）"""
    if not song_id:
        return False
    return re.fullmatch(r"[0-9A-Za-z\-]+", song_id) is not None


def song_dir(song_id):
    return os.path.join(SONGS_DIR, song_id)


def song_file(song_id, filename):
    return os.path.join(song_dir(song_id), filename)


def song_exists(song_id):
    if not is_valid_id(song_id):
        return False
    return os.path.exists(song_file(song_id, "meta.json"))


# ---------- JSON 讀寫 ----------

def read_json(path, default=None):
    with _file_lock:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_json(path, data):
    with _file_lock:
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        # 先寫到暫存檔，再一次換過去，這樣檔案不會寫到一半壞掉
        os.replace(temp_path, path)


def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    # 換行先一律變成 \n 再寫：上傳表單送來的換行是 \r\n，Windows 寫檔又會再加一個 \r，
    # 讀回來每一行後面就多一行空行（「編輯歌詞」也就認不出用的是哪一份）
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------- 歌曲 ----------

def create_song(title, artist, original_filename, separate, auto_lyrics):
    """建立一首新歌的資料夾和 meta.json，回傳歌曲 ID"""
    song_id = time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    os.makedirs(song_dir(song_id), exist_ok=True)

    meta = {
        "id": song_id,
        "title": title,
        "artist": artist,
        "duration": 0,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "original_file": original_filename,
        "separate": separate,          # 要不要用 AI 去人聲
        "auto_lyrics": auto_lyrics,    # 要不要自動搜尋歌詞
        "status": "waiting",           # waiting / processing / ready / error
        "stage": "排隊中",
        "progress": 0,
        "error": "",
        "has_vocals": False,
        "has_cover": False,
        "has_lyrics": False,
        "lyrics_synced": False,
        "lyrics_source": "",
        "lyrics_offset": 0,            # 歌詞整體偏移（毫秒）
        "best_score": None,
    }
    write_json(song_file(song_id, "meta.json"), meta)
    return song_id


def get_meta(song_id):
    return read_json(song_file(song_id, "meta.json"))


def update_meta(song_id, changes):
    """更新 meta.json 裡的部分欄位，例如 update_meta(id, {"progress": 50})"""
    meta = get_meta(song_id)
    if meta is None:
        return None
    for key in changes:
        meta[key] = changes[key]
    write_json(song_file(song_id, "meta.json"), meta)
    return meta


def list_songs():
    songs = []
    if not os.path.exists(SONGS_DIR):
        return songs
    for name in os.listdir(SONGS_DIR):
        meta = read_json(os.path.join(SONGS_DIR, name, "meta.json"))
        if meta is not None:
            songs.append(meta)
    # 新的歌排前面
    songs.sort(key=lambda m: m.get("created", ""), reverse=True)
    return songs


def delete_song(song_id):
    if song_exists(song_id):
        shutil.rmtree(song_dir(song_id), ignore_errors=True)


# ---------- 分數 ----------

def get_scores(song_id):
    return read_json(song_file(song_id, "scores.json"), [])


def add_score(song_id, score):
    scores = get_scores(song_id)
    score["date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    scores.append(score)
    write_json(song_file(song_id, "scores.json"), scores)

    # 順便更新最高分
    best = None
    for s in scores:
        if best is None or s.get("total", 0) > best:
            best = s.get("total", 0)
    update_meta(song_id, {"best_score": best})
    return scores
