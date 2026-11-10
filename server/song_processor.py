"""
處理一首新歌的完整流程（在背景執行）：

  0. 下載        從 YouTube 加的歌，先把影片下載下來（電腦裡的檔案就跳過）
  1. 轉檔        原始檔 → WAV
  2. 去人聲      AI 分離出「人聲」和「伴奏」
  3. 分析音高    從人聲找出旋律音符（評分用）
  3之一. 認音節  用 MMS 聽整首人聲，存成 mms_emission.npy（字幕每個字的時間用；沒有模型就跳過）
  4. 找歌詞      自動去 LRCLIB 搜尋
  5. 做字幕      產生假名、羅馬音、逐字時間
"""
import os
import time
import traceback

from server import (audio_tools, lyrics_search, pitch_analyzer, separator, singing_check, song_store,
                    syllable_model, word_store, youtube_import)
from server.lyrics_builder import build_lyrics

# 瀏覽器能直接播放的影片格式（這些才能當 MV 背景）
BROWSER_VIDEO_EXTENSIONS = [".mp4", ".webm", ".m4v"]


def set_progress(song_id, stage, progress):
    print("[" + song_id + "] " + stage + " " + str(progress) + "%")
    song_store.update_meta(song_id, {"status": "processing", "stage": stage, "progress": progress})


def make_lyrics(song_id, lrc_text, use_offset=True):
    """用這首歌的設定（偏移、自動對齊、裁切），把 LRC 文字做成字幕資料（不存檔）。
    「編輯歌詞」的試聽也用這個，所以試聽看到的字幕跟真的唱歌時一模一樣
    use_offset=False：不加整體偏移（搜尋結果的試聽：按「使用」換歌詞時偏移會歸零）"""
    meta = song_store.get_meta(song_id)
    pitch = song_store.read_json(song_store.song_file(song_id, "pitch.json"), {})
    notes = pitch.get("notes", [])
    # 整體偏移（毫秒）。裁切跟歌詞時間無關（trim.py），不用加
    # 只有「照歌詞檔」（lyrics_auto_align = False）才用你手動移的秒數；
    # 「自動」時程式自己會整首移、每句對，再加手動移的只會互相打架（存著的數字不會刪，切回「照歌詞檔」就又有用）
    offset_ms = 0
    if use_offset and not meta.get("lyrics_auto_align", True):
        offset_ms = meta.get("lyrics_offset", 0)
    # 認音節的結果（沒有、或你在「編輯歌詞」取消勾選「AI 認音節」，就是 None，字幕照音符分）
    emission = None
    if meta.get("lyrics_syllable_ai", True):
        emission = syllable_model.load_emission(song_store.song_dir(song_id))
    lyrics = build_lyrics(lrc_text, notes, meta.get("duration", 0), offset_ms,
                          meta.get("lyrics_auto_align", True), pitch.get("heard"), pitch.get("hop", 0.0),
                          emission, pitch.get("loudness"))
    # 你在修譜頁自己調過的字：照你的時間（word_store.py）
    word_store.apply_words(lyrics, word_store.get_words(song_id))
    # 每一段原唱是唱歌還是說話（「自動找劇情」用這份）
    if lyrics["synced"] and pitch.get("contour"):
        lyrics["phrases"] = singing_check.classify_phrases(notes, lyrics["lines"], pitch["contour"],
                                                           pitch.get("heard"), pitch.get("hop", 0.01))
    return lyrics


def rebuild_lyrics(song_id):
    """重新產生 lyrics.json（歌詞或偏移改了之後呼叫）"""
    lrc_path = song_store.song_file(song_id, "lyrics.lrc")
    json_path = song_store.song_file(song_id, "lyrics.json")

    lrc_text = song_store.read_text(lrc_path, "")
    if lrc_text.strip() == "":
        if os.path.exists(json_path):
            os.remove(json_path)
        song_store.update_meta(song_id, {"has_lyrics": False, "lyrics_synced": False})
        return None

    lyrics = make_lyrics(song_id, lrc_text)
    song_store.write_json(json_path, lyrics)
    song_store.update_meta(song_id, {"has_lyrics": True, "lyrics_synced": lyrics["synced"]})
    return lyrics


def download_from_youtube(song_id, url, folder):
    """0. 從 YouTube 下載影片，回傳存好的檔名"""
    last_time = [0.0]     # 上次更新進度的時間（太常寫檔沒必要，一秒一次就好）
    last_text = [""]      # 上次寫的進度文字（一樣就不用再寫）

    def report(part, percent):
        percent = min(100, percent)
        text = part + str(round(percent))
        now = time.time()
        if text == last_text[0]:
            return
        if now - last_time[0] < 1.0 and percent < 100:
            return
        last_time[0] = now
        last_text[0] = text
        # 下載佔整體進度的 0～4%，詳細百分比寫在文字裡
        set_progress(song_id, "從 YouTube 下載" + part + " " + str(round(percent)) + "%",
                     round(percent / 25))

    set_progress(song_id, "讀取 YouTube 影片", 0)
    filename = youtube_import.download(url, folder, report)
    song_store.update_meta(song_id, {"original_file": filename})
    return filename


def process_song(song_id):
    meta = song_store.get_meta(song_id)
    if meta is None:
        return

    folder = song_store.song_dir(song_id)
    work_wav = os.path.join(folder, "work.wav")
    vocals_path = os.path.join(folder, "vocals.flac")
    instrumental_path = os.path.join(folder, "instrumental.flac")

    try:
        # 0. 從 YouTube 加的歌：還沒下載過才下載（重新處理時不會再下載一次）
        original_file = meta.get("original_file", "")
        if meta.get("youtube_url"):
            if original_file == "" or not os.path.exists(os.path.join(folder, original_file)):
                original_file = download_from_youtube(song_id, meta["youtube_url"], folder)
        original_path = os.path.join(folder, original_file)

        # 有沒有 MV 畫面（瀏覽器能播的影片格式才算）
        extension = os.path.splitext(original_file)[1].lower()
        has_video = False
        if extension in BROWSER_VIDEO_EXTENSIONS:
            has_video = audio_tools.has_video_stream(original_path)
        song_store.update_meta(song_id, {"has_video": has_video})

        # 1. 轉檔
        set_progress(song_id, "轉換音訊格式", 5)
        audio_tools.convert_audio(original_path, work_wav, 44100, 2)
        duration = audio_tools.get_duration(work_wav)
        song_store.update_meta(song_id, {"duration": round(duration, 2)})

        # 封面：從 YouTube 加的歌用影片縮圖；電腦裡的檔案用檔案內附的封面
        cover_path = os.path.join(folder, "cover.jpg")
        if meta.get("cover_custom"):
            pass   # 你自己換過封面：重新處理也不要蓋掉
        elif meta.get("youtube_url"):
            if not os.path.exists(cover_path):
                try:
                    youtube_import.download_cover(meta["youtube_url"], folder)
                except Exception as error:
                    print("[" + song_id + "] 下載封面失敗（不影響唱歌）：", error)
        else:
            audio_tools.extract_cover(original_path, cover_path)
        song_store.update_meta(song_id, {"has_cover": os.path.exists(cover_path)})

        # 2. 去人聲
        has_vocals = False
        if meta.get("separate") and separator.is_available():
            set_progress(song_id, "AI 分離人聲與伴奏", 15)
            separator.separate_vocals(work_wav, vocals_path, instrumental_path)
            has_vocals = True
        else:
            set_progress(song_id, "準備伴奏", 15)
            separator.copy_as_instrumental(work_wav, instrumental_path)
            if os.path.exists(vocals_path):
                os.remove(vocals_path)
        song_store.update_meta(song_id, {"has_vocals": has_vocals})

        # 3. 分析音高（有分離就用人聲，比較準；沒有就只能用原曲）
        set_progress(song_id, "分析旋律音高", 65)
        pitch = None
        pitch_source = "vocals"
        if has_vocals:
            pitch = pitch_analyzer.analyze(vocals_path, folder)
            # 保護機制：分離出來的人聲找不到旋律（例如 AI 把人聲當成樂器），就改用原曲
            if len(pitch["notes"]) < 10:
                print("[" + song_id + "] 人聲音軌幾乎沒有旋律，改用原曲分析")
                pitch = None
        if pitch is None:
            pitch = pitch_analyzer.analyze(work_wav, folder)
            pitch_source = "original"
        song_store.write_json(os.path.join(folder, "pitch.json"), pitch)
        song_store.update_meta(song_id, {"pitch_source": pitch_source})

        # 3之一. 認音節（有分出人聲、電腦裡有 MMS 模型才做；失敗也不影響唱歌，字幕照音符分）
        emission_path = os.path.join(folder, syllable_model.EMISSION_FILE)
        if os.path.exists(emission_path):
            os.remove(emission_path)   # 重新處理：舊的人聲結果不能用了
        if has_vocals and pitch_source == "vocals" and syllable_model.is_available():
            set_progress(song_id, "AI 認音節", 82)
            try:
                syllable_model.save_emission(folder, vocals_path)
            except Exception as error:
                print("[" + song_id + "] 認音節失敗（字幕照音符分）：", error)

        # 4. 找歌詞（已經有歌詞就不重找）
        lrc_path = os.path.join(folder, "lyrics.lrc")
        if meta.get("auto_lyrics") and not os.path.exists(lrc_path):
            set_progress(song_id, "搜尋歌詞", 88)
            best = lyrics_search.find_best(meta["title"], meta["artist"], duration)
            if best is not None:
                song_store.write_text(lrc_path, best["synced"])
                song_store.update_meta(song_id, {"lyrics_source": "LRCLIB"})

        # 5. 做字幕
        set_progress(song_id, "生成字幕與羅馬音", 95)
        rebuild_lyrics(song_id)
        # 不會自動裁切：要不要裁掉劇情由你在歌曲頁的「✂ 裁切」自己決定（有「🔍 自動找劇情」可以用）

        song_store.update_meta(song_id, {"status": "ready", "stage": "完成", "progress": 100, "error": ""})
        print("[" + song_id + "] 處理完成")

    except Exception as error:
        traceback.print_exc()
        song_store.update_meta(song_id, {"status": "error", "stage": "處理失敗", "error": str(error)})

    finally:
        if os.path.exists(work_wav):
            os.remove(work_wav)
