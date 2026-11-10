"""
背景工作排隊：新歌一首一首處理（顯示卡一次只做一件事比較穩）。
"""
import queue
import threading

from server import song_store
from server.song_processor import process_song

_jobs = queue.Queue()
_started = False


def add_job(song_id):
    song_store.update_meta(song_id, {"status": "waiting", "stage": "排隊中", "progress": 0, "error": ""})
    _jobs.put(song_id)


def _worker():
    while True:
        song_id = _jobs.get()
        try:
            process_song(song_id)
        except Exception as error:
            print("處理失敗：", error)
        _jobs.task_done()


def start():
    """伺服器啟動時呼叫：開一個背景執行緒，並把上次沒做完的歌重新排隊"""
    global _started
    if _started:
        return
    _started = True

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    for meta in song_store.list_songs():
        if meta.get("status") in ("waiting", "processing"):
            add_job(meta["id"])
