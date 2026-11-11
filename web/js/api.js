// 跟後端（Python 伺服器）溝通的函式都放在這裡。
// 其他檔案要拿資料時，只要呼叫這裡的函式就好。

import { t, tServer } from './i18n.js';

async function request(method, url, data) {
  const options = { method: method, headers: {} };
  if (data !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(data);
  }

  const response = await fetch(url, options);
  if (!response.ok) {
    let message = t('伺服器錯誤 {status}', { status: response.status });
    try {
      const body = await response.json();
      if (body.detail) {
        message = tServer(body.detail);
      }
    } catch (error) {
      // 回應不是 JSON，就用預設訊息
    }
    throw new Error(message);
  }
  return response.json();
}

function songUrl(songId) {
  return '/api/songs/' + encodeURIComponent(songId);
}

// ---------- 系統 ----------
export function getSystemInfo() {
  return request('GET', '/api/system');
}

// ---------- 歌曲 ----------
export function getSongs() {
  return request('GET', '/api/songs');
}

export function getSong(songId) {
  return request('GET', songUrl(songId));
}

export function updateSong(songId, changes) {
  return request('PATCH', songUrl(songId), changes);
}

export function deleteSong(songId) {
  return request('DELETE', songUrl(songId));
}

// 裁切：data = { start: 秒, end: 秒（0 = 到最後） }（只決定播哪一段，歌詞時間不變）
export function saveTrim(songId, data) {
  return request('POST', songUrl(songId) + '/trim', data);
}

// 自動找 MV 前後的劇情：回傳 { suggestion: { start, end, talk_before, talk_after } 或 null, reason }
export function suggestTrim(songId) {
  return request('GET', songUrl(songId) + '/trim/suggest');
}

export function reprocessSong(songId, separate) {
  return request('POST', songUrl(songId) + '/reprocess', { separate: separate });
}

export function getPitch(songId) {
  return request('GET', songUrl(songId) + '/pitch');
}

// 你修過的譜：回傳 { notes: [...] }，沒修過 notes 是 null
export function getChart(songId) {
  return request('GET', songUrl(songId) + '/chart');
}

export function saveChart(songId, notes) {
  return request('PUT', songUrl(songId) + '/chart', { notes: notes });
}

// 還原 AI 的譜
export function deleteChart(songId) {
  return request('DELETE', songUrl(songId) + '/chart');
}

// 你在修譜頁調過的字的時間：{ words: [{ line, nth, index, text, start, end }] }
export function getWords(songId) {
  return request('GET', songUrl(songId) + '/words');
}

// 存你調過的字（整份換掉）。回傳 { words, lyrics（重做好的字幕）}
export function saveWords(songId, words) {
  return request('PUT', songUrl(songId) + '/words', { words: words });
}

// 還原字的時間（全部照程式算的）。回傳 { words: [], lyrics }
export function deleteWords(songId) {
  return request('DELETE', songUrl(songId) + '/words');
}

export function audioUrl(songId, kind) {
  return songUrl(songId) + '/audio/' + kind;
}

// 換封面：上傳一張圖片
export async function uploadCover(songId, file) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(songUrl(songId) + '/cover', { method: 'POST', body: form });
  const body = await response.json().catch(function () {
    return {};
  });
  if (!response.ok) {
    throw new Error(tServer(body.detail) || t('上傳失敗 {status}', { status: response.status }));
  }
  return body;
}

// 還原原本的封面
export function restoreCover(songId) {
  return request('DELETE', songUrl(songId) + '/cover');
}

// version：封面換過的話給新號碼，瀏覽器才不會用舊的圖（歌曲資料裡的 cover_version）
export function coverUrl(songId, version) {
  if (version) {
    return songUrl(songId) + '/cover?v=' + encodeURIComponent(version);
  }
  return songUrl(songId) + '/cover';
}

export function videoUrl(songId) {
  return songUrl(songId) + '/video';
}

// ---------- 從 YouTube 加歌 ----------
export function getYoutubeInfo(url) {
  return request('GET', '/api/youtube/info?url=' + encodeURIComponent(url));
}

export function addYoutubeSong(data) {
  return request('POST', '/api/songs/youtube', data);
}

// 上傳歌曲（用 XMLHttpRequest 才能知道上傳進度）
export function uploadSong(formData, onProgress) {
  return new Promise(function (resolve, reject) {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/songs');
    xhr.upload.onprogress = function (event) {
      if (event.lengthComputable && onProgress) {
        onProgress(event.loaded / event.total);
      }
    };
    xhr.onload = function () {
      let body = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch (error) {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body);
      } else {
        let message = t('上傳失敗 {status}', { status: xhr.status });
        if (body && body.detail) {
          message = tServer(body.detail);
        }
        reject(new Error(message));
      }
    };
    xhr.onerror = function () {
      reject(new Error(t('上傳失敗：連不到伺服器')));
    };
    xhr.send(formData);
  });
}

// ---------- 歌詞 ----------
export function getLyrics(songId) {
  return request('GET', songUrl(songId) + '/lyrics');
}

// resetOffset：換成搜尋到的另一份歌詞時傳 true，整體偏移歸零（舊的偏移是給舊歌詞用的）
export function saveLyrics(songId, lrcText, source, resetOffset) {
  return request('PUT', songUrl(songId) + '/lyrics',
    { lrc: lrcText, source: source, reset_offset: resetOffset === true });
}

// 幾份歌詞各自跟這首歌的歌聲對不對得上：回傳 { results: [{ shift, silent, silent_at, lines } 或 null, ...] }
export function matchLyrics(songId, versions) {
  return request('POST', songUrl(songId) + '/lyrics/match', { versions: versions });
}

// 試聽用：把一份歌詞做成字幕，但不存檔。回傳 { lyrics }
// fresh：搜尋結果的試聽，不加你設的整體偏移（按「使用」時偏移會歸零，試聽看到的才會一樣）
export function previewLyrics(songId, lrc, fresh) {
  return request('POST', songUrl(songId) + '/lyrics/preview', { lrc: lrc, fresh: fresh === true });
}

export function searchLyrics(title, artist) {
  const url = '/api/lyrics/search?title=' + encodeURIComponent(title) + '&artist=' + encodeURIComponent(artist);
  return request('GET', url);
}

// ---------- 分數 ----------
export function getScores(songId) {
  return request('GET', songUrl(songId) + '/scores');
}

export function addScore(songId, record) {
  return request('POST', songUrl(songId) + '/scores', record);
}

// ---------- 下載錄音 ----------
// 錄音可以下載成哪些格式：[{ id, label }]（id 也是副檔名）
export function getRecordingFormats() {
  return request('GET', '/api/recording/formats');
}

// 把錄音交給伺服器轉檔，回傳轉好的檔案（Blob）
export async function exportRecording(blob, formatId) {
  const form = new FormData();
  form.append('file', blob, 'recording');
  form.append('format', formatId);
  const response = await fetch('/api/recording/export', { method: 'POST', body: form });
  if (!response.ok) {
    const body = await response.json().catch(function () {
      return {};
    });
    throw new Error(tServer(body.detail) || t('轉檔失敗 {status}', { status: response.status }));
  }
  return response.blob();
}
