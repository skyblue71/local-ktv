"""
網頁伺服器（後端）的入口。

啟動方式（在專案資料夾底下）：
  .venv\\Scripts\\python -m uvicorn server.main:app --port 8000

這裡只負責「網址 → 要做什麼事」，真正的工作都交給其他檔案。
"""
import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import (audio_tools, chart_store, cover_tools, job_queue, lyrics_consensus, lyrics_match, lyrics_search,
                    recording_export, separator, singing_check, song_store, syllable_model, trim, word_store,
                    youtube_import)
from server.config import WEB_DIR
from server.song_processor import make_lyrics, rebuild_lyrics

# 沒裝 yt-dlp 時的說明
YTDLP_MISSING = '虛擬環境裡沒有 yt-dlp，請執行 setup.bat（會用 pip 安裝 yt-dlp）'

# 影片檔的格式（給瀏覽器播 MV 用）
VIDEO_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm"}

ALLOWED_EXTENSIONS = [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma",
                      ".mp4", ".mkv", ".webm", ".mov"]


# 伺服器啟動時，先啟動背景處理佇列
@asynccontextmanager
async def lifespan(app):
    job_queue.start()
    yield


app = FastAPI(title="本機KTV", lifespan=lifespan)


# 叫瀏覽器每次都確認檔案有沒有新版本（更新程式後不會看到舊畫面）
@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


def check_song(song_id):
    if not song_store.song_exists(song_id):
        raise HTTPException(status_code=404, detail="找不到這首歌")


def lyrics_source_name(source):
    """加歌時一起送來的歌詞是從哪來的：在「加入歌曲」的歌詞選單選的 = LRCLIB，其他都算手動輸入"""
    if source == "LRCLIB":
        return "LRCLIB"
    return "手動輸入"


# ---------- 資料格式 ----------

class SongUpdate(BaseModel):
    title: str | None = None
    artist: str | None = None
    lyrics_offset: int | None = None
    lyrics_auto_align: bool | None = None
    lyrics_syllable_ai: bool | None = None   # 每個字的填色用 AI 認音節（MMS）；False = 照音符平均分
    lyrics_show_absent: bool | None = None   # 這支影片沒唱的句子照樣顯示；False = 不顯示


class LyricsUpdate(BaseModel):
    lrc: str
    source: str = "手動輸入"
    reset_offset: bool = False   # 換成搜尋到的另一份歌詞：整體偏移歸零（舊的偏移是給舊歌詞用的）


class ReprocessRequest(BaseModel):
    separate: bool = True


class TrimRequest(BaseModel):
    start: float = 0          # 從第幾秒開始唱
    end: float = 0            # 唱到第幾秒（0 = 唱到最後）


class YoutubeSongRequest(BaseModel):
    url: str
    title: str = ""
    artist: str = ""
    separate: bool = True
    auto_lyrics: bool = True
    lrc: str = ""
    lyrics_source: str = ""


class LyricsMatchRequest(BaseModel):
    versions: list[str] = []   # 要比對的幾份歌詞（LRC 文字）


class LyricsPreviewRequest(BaseModel):
    lrc: str   # 要試聽的那份歌詞（LRC 文字）
    fresh: bool = False   # 搜尋結果的試聽：不加你設的整體偏移（按「使用」也會歸零，看到的才一樣）


class ChartRequest(BaseModel):
    notes: list[dict] = []   # 你修過的譜：[{s, e, p, u}]


class WordsRequest(BaseModel):
    words: list[dict] = []   # 你調過的字：[{line, nth, index, text, start, end}]（word_store.py）


class ScoreRecord(BaseModel):
    player: str = "我"
    total: float
    details: dict = {}


# ---------- 系統資訊 ----------

@app.get("/api/system")
def system_info():
    """
    separator：分人聲的套件裝了沒；separatorModel、syllableModel：分人聲、認音節的模型檔在不在
    （不在的話，網頁在加歌的地方說「按 update.bat 下載」）
    """
    available = separator.is_available()
    gpu = ""
    if available:
        gpu = separator.get_gpu_name()
    return {
        "separator": available,
        "separatorModel": separator.has_model(),
        "syllableModel": syllable_model.is_available(),
        "gpu": gpu,
        "youtube": youtube_import.is_available(),
    }


# ---------- 歌曲 ----------

@app.get("/api/songs")
def get_songs():
    return song_store.list_songs()


@app.post("/api/songs")
def upload_song(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(""),
    separate: bool = Form(True),
    auto_lyrics: bool = Form(True),
    lrc: str = Form(""),
    lyrics_source: str = Form(""),
):
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支援的檔案格式：" + extension)

    filename_title = os.path.splitext(os.path.basename(file.filename or "未命名"))[0]
    song_id = song_store.create_song(title.strip(), artist.strip(), "original" + extension,
                                     separate, auto_lyrics)

    # 把上傳的檔案存起來
    original_path = song_store.song_file(song_id, "original" + extension)
    with open(original_path, "wb") as output:
        shutil.copyfileobj(file.file, output)

    # 沒填標題/歌手的話，從檔案標籤讀，再不行就用檔名
    tag_title, tag_artist = audio_tools.read_tags(original_path)
    changes = {}
    if title.strip() == "":
        changes["title"] = tag_title or filename_title
    if artist.strip() == "":
        changes["artist"] = tag_artist
    if lrc.strip() != "":
        song_store.write_text(song_store.song_file(song_id, "lyrics.lrc"), lrc)
        changes["lyrics_source"] = lyrics_source_name(lyrics_source)
    song_store.update_meta(song_id, changes)

    job_queue.add_job(song_id)
    return song_store.get_meta(song_id)


# ---------- 從 YouTube 加歌 ----------

@app.get("/api/youtube/info")
def youtube_info(url: str):
    """讀取影片的標題、歌手（不下載影片）"""
    if not youtube_import.is_available():
        raise HTTPException(status_code=400, detail=YTDLP_MISSING)
    try:
        return youtube_import.get_info(url)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/api/songs/youtube")
def add_youtube_song(request: YoutubeSongRequest):
    """建立歌曲，影片交給背景處理時再下載"""
    if not youtube_import.is_available():
        raise HTTPException(status_code=400, detail=YTDLP_MISSING)
    try:
        url = youtube_import.check_url(request.url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    title = request.title.strip() or "YouTube 影片"
    song_id = song_store.create_song(title, request.artist.strip(), "",
                                     request.separate, request.auto_lyrics)
    changes = {"youtube_url": url, "source": "YouTube"}
    if request.lrc.strip() != "":
        song_store.write_text(song_store.song_file(song_id, "lyrics.lrc"), request.lrc)
        changes["lyrics_source"] = lyrics_source_name(request.lyrics_source)
    song_store.update_meta(song_id, changes)

    job_queue.add_job(song_id)
    return song_store.get_meta(song_id)


@app.get("/api/songs/{song_id}")
def get_song(song_id: str):
    check_song(song_id)
    return song_store.get_meta(song_id)


@app.patch("/api/songs/{song_id}")
def update_song(song_id: str, update: SongUpdate):
    check_song(song_id)
    changes = {}
    if update.title is not None:
        if update.title.strip() == "":
            raise HTTPException(status_code=400, detail="歌名不能空白")
        changes["title"] = update.title.strip()
    if update.artist is not None:
        changes["artist"] = update.artist.strip()
    if update.lyrics_offset is not None:
        changes["lyrics_offset"] = update.lyrics_offset
    if update.lyrics_auto_align is not None:
        changes["lyrics_auto_align"] = update.lyrics_auto_align
    if update.lyrics_syllable_ai is not None:
        changes["lyrics_syllable_ai"] = update.lyrics_syllable_ai
    if update.lyrics_show_absent is not None:
        changes["lyrics_show_absent"] = update.lyrics_show_absent
    meta = song_store.update_meta(song_id, changes)
    # 偏移、自動對齊、AI 認音節、沒唱的句子要不要顯示改了，字幕要重新產生
    if (update.lyrics_offset is not None or update.lyrics_auto_align is not None
            or update.lyrics_syllable_ai is not None or update.lyrics_show_absent is not None):
        rebuild_lyrics(song_id)
    return song_store.get_meta(song_id)


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
    check_song(song_id)
    song_store.delete_song(song_id)
    return {"ok": True}


@app.post("/api/songs/{song_id}/trim")
def trim_song(song_id: str, request: TrimRequest):
    """裁切（只記住範圍，不剪檔案）。裁切只決定播哪一段，歌詞的時間不變（trim.py）"""
    check_song(song_id)
    meta = song_store.get_meta(song_id)
    try:
        start, end = trim.check_range(request.start, request.end, meta.get("duration", 0))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    # 存裁切的範圍
    song_store.update_meta(song_id, {"trim_start": start, "trim_end": end})
    result = song_store.get_meta(song_id)
    result["message"] = "已儲存"
    return result


@app.get("/api/songs/{song_id}/trim/suggest")
def suggest_trim(song_id: str):
    """自動找 MV 前後的劇情（有人說話）：回傳建議的裁切範圍（沒有劇情就回傳 suggestion: null）"""
    check_song(song_id)
    meta = song_store.get_meta(song_id)
    lyrics = song_store.read_json(song_store.song_file(song_id, "lyrics.json"))
    if lyrics is None or not lyrics.get("phrases"):
        return {"suggestion": None, "reason": "沒有時間軸歌詞，沒辦法判斷"}
    song_zero = trim.lyrics_start_in_video(meta, lyrics)
    suggestion = singing_check.suggest_story_trim(lyrics["phrases"], meta.get("duration", 0), song_zero)
    if suggestion is None:
        return {"suggestion": None, "reason": "沒有找到劇情"}
    return {"suggestion": suggestion, "reason": ""}


@app.post("/api/songs/{song_id}/reprocess")
def reprocess_song(song_id: str, request: ReprocessRequest):
    check_song(song_id)
    song_store.update_meta(song_id, {"separate": request.separate})
    job_queue.add_job(song_id)
    return song_store.get_meta(song_id)


# ---------- 檔案（音訊、封面、音高） ----------

@app.get("/api/songs/{song_id}/audio/{kind}")
def get_audio(song_id: str, kind: str):
    check_song(song_id)
    if kind not in ("instrumental", "vocals"):
        raise HTTPException(status_code=400, detail="只有 instrumental 或 vocals")
    path = song_store.song_file(song_id, kind + ".flac")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="還沒有這個音軌")
    return FileResponse(path, media_type="audio/flac")


@app.get("/api/songs/{song_id}/video")
def get_video(song_id: str):
    """MV 影片（瀏覽器會一段一段要，所以可以跳到中間播）"""
    check_song(song_id)
    meta = song_store.get_meta(song_id)
    if not meta.get("has_video"):
        raise HTTPException(status_code=404, detail="這首歌沒有 MV")
    path = song_store.song_file(song_id, meta["original_file"])
    extension = os.path.splitext(path)[1].lower()
    if not os.path.exists(path) or extension not in VIDEO_TYPES:
        raise HTTPException(status_code=404, detail="找不到 MV 檔案")
    return FileResponse(path, media_type=VIDEO_TYPES[extension])


@app.post("/api/songs/{song_id}/cover")
def upload_cover(song_id: str, file: UploadFile = File(...)):
    """換封面：上傳一張圖片（原本的封面會先備份，可以還原）"""
    check_song(song_id)
    folder = song_store.song_dir(song_id)
    upload_path = os.path.join(folder, "cover_upload.tmp")
    try:
        with open(upload_path, "wb") as output:
            shutil.copyfileobj(file.file, output)
        cover_tools.save_custom_cover(folder, upload_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    finally:
        if os.path.isfile(upload_path):
            os.remove(upload_path)
    song_store.update_meta(song_id, {"has_cover": True, "cover_custom": True,
                                     "cover_version": cover_tools.new_version()})
    return song_store.get_meta(song_id)


@app.delete("/api/songs/{song_id}/cover")
def restore_cover(song_id: str):
    """還原原本的封面"""
    check_song(song_id)
    has_cover = cover_tools.restore_original_cover(song_store.song_dir(song_id))
    song_store.update_meta(song_id, {"has_cover": has_cover, "cover_custom": False,
                                     "cover_version": cover_tools.new_version()})
    return song_store.get_meta(song_id)


@app.get("/api/songs/{song_id}/cover")
def get_cover(song_id: str):
    check_song(song_id)
    path = song_store.song_file(song_id, "cover.jpg")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="沒有封面")
    return FileResponse(path)


@app.get("/api/songs/{song_id}/pitch")
def get_pitch(song_id: str):
    check_song(song_id)
    pitch = song_store.read_json(song_store.song_file(song_id, "pitch.json"))
    if pitch is None:
        raise HTTPException(status_code=404, detail="還沒有音高資料")
    return pitch


# ---------- 你修過的譜（chart_store.py） ----------

@app.get("/api/songs/{song_id}/chart")
def get_chart(song_id: str):
    """回傳 { notes: [...] }；沒修過的歌 notes 是 null（唱歌時照舊用 AI 的譜）"""
    check_song(song_id)
    return {"notes": chart_store.get_chart(song_id)}


@app.put("/api/songs/{song_id}/chart")
def save_chart(song_id: str, request: ChartRequest):
    check_song(song_id)
    try:
        notes = chart_store.save_chart(song_id, request.notes)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=400, detail="譜的資料不對：" + str(error))
    return {"notes": notes}


@app.delete("/api/songs/{song_id}/chart")
def delete_chart(song_id: str):
    """還原 AI 的譜"""
    check_song(song_id)
    chart_store.delete_chart(song_id)
    return {"notes": None}


# ---------- 你調過的字的時間（word_store.py） ----------

@app.get("/api/songs/{song_id}/words")
def get_words(song_id: str):
    """回傳 { words: [...] }：你在修譜頁調過的字（沒調過是空的）"""
    check_song(song_id)
    return {"words": word_store.get_words(song_id)}


@app.put("/api/songs/{song_id}/words")
def save_words(song_id: str, request: WordsRequest):
    """存你調過的字（整份換掉），重做字幕。回傳 { words, lyrics }"""
    check_song(song_id)
    try:
        words = word_store.save_words(song_id, request.words)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=400, detail="字的時間不對：" + str(error))
    return {"words": words, "lyrics": rebuild_lyrics(song_id)}


@app.delete("/api/songs/{song_id}/words")
def delete_words(song_id: str):
    """還原字的時間（全部照程式算的），重做字幕"""
    check_song(song_id)
    word_store.delete_words(song_id)
    return {"words": [], "lyrics": rebuild_lyrics(song_id)}


# ---------- 歌詞 ----------

@app.get("/api/songs/{song_id}/lyrics")
def get_lyrics(song_id: str):
    check_song(song_id)
    meta = song_store.get_meta(song_id)
    return {
        "lrc": song_store.read_text(song_store.song_file(song_id, "lyrics.lrc"), ""),
        "lyrics": song_store.read_json(song_store.song_file(song_id, "lyrics.json")),
        "offset": meta.get("lyrics_offset", 0),
        "source": meta.get("lyrics_source", ""),
    }


@app.put("/api/songs/{song_id}/lyrics")
def save_lyrics(song_id: str, update: LyricsUpdate):
    check_song(song_id)
    song_store.write_text(song_store.song_file(song_id, "lyrics.lrc"), update.lrc)
    changes = {"lyrics_source": update.source}
    if update.reset_offset:
        changes["lyrics_offset"] = 0
    song_store.update_meta(song_id, changes)
    lyrics = rebuild_lyrics(song_id)
    return {"lyrics": lyrics}


@app.get("/api/lyrics/search")
def search_lyrics(title: str = "", artist: str = ""):
    return lyrics_search.search(title, artist)


@app.post("/api/songs/{song_id}/lyrics/match")
def match_lyrics(song_id: str, request: LyricsMatchRequest):
    """幾份歌詞各自跟這首歌的歌聲對不對得上（編輯歌詞的搜尋結果用）。沒有時間軸的那份回傳 null。
    另外多份歌詞互相比對（lyrics_consensus.py）：每一份多一個 check，現在用的字幕放在 current"""
    check_song(song_id)
    meta = song_store.get_meta(song_id)
    pitch = song_store.read_json(song_store.song_file(song_id, "pitch.json"), {})
    # 不加你設的整體偏移：那是給現在這份歌詞用的。加了的話每一份都會被帶到同一個錯的地方，
    # 互相比對就比不出來。按「使用」換歌詞時偏移也會歸零
    offset = 0.0
    results = []
    version_lines = []
    for lrc_text in request.versions[:30]:
        result = lyrics_match.evaluate(lrc_text, pitch.get("notes", []), meta.get("duration", 0), offset)
        results.append(result)
        if result is None:
            version_lines.append([])
        else:
            version_lines.append(lyrics_match.video_lines(lrc_text, offset, result["shift"]))

    current_lines = []
    lyrics = song_store.read_json(song_store.song_file(song_id, "lyrics.json"))
    if lyrics is not None and lyrics.get("synced"):
        for line in lyrics["lines"]:
            current_lines.append((line["start"], line["text"]))
    checks, current = lyrics_consensus.check_all(version_lines, current_lines)
    for index in range(len(results)):
        if results[index] is not None:
            results[index]["check"] = checks[index]
    return {"results": results, "current": current}


@app.post("/api/songs/{song_id}/lyrics/preview")
def preview_lyrics(song_id: str, request: LyricsPreviewRequest):
    """試聽用：把一份歌詞做成字幕，但不存檔（跟真的唱歌時的字幕一樣）"""
    check_song(song_id)
    return {"lyrics": make_lyrics(song_id, request.lrc, not request.fresh)}


# ---------- 分數 ----------

@app.get("/api/songs/{song_id}/scores")
def get_scores(song_id: str):
    check_song(song_id)
    return song_store.get_scores(song_id)


@app.post("/api/songs/{song_id}/scores")
def add_score(song_id: str, record: ScoreRecord):
    check_song(song_id)
    score = {"player": record.player, "total": record.total, "details": record.details}
    return song_store.add_score(song_id, score)


# ---------- 下載錄音 ----------

@app.get("/api/recording/formats")
def get_recording_formats():
    """錄音可以下載成哪些格式（結果畫面的下載按鈕照這個排）"""
    return recording_export.list_formats()


@app.post("/api/recording/export")
def export_recording(file: UploadFile = File(...), format: str = Form(...)):
    """把唱完的錄音轉成指定格式再傳回去（會補上總長度；錄音轉完就刪掉，不會留在硬碟）"""
    export_format = recording_export.find_format(format)
    if export_format is None:
        raise HTTPException(status_code=400, detail="沒有這種格式：" + format)
    try:
        data = recording_export.export_recording(file.file, export_format)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error))
    return Response(content=data, media_type=export_format["media_type"])


# ---------- 網頁 ----------
# 一定要放最後：其他網址都不是的話，就去 web 資料夾找檔案
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
