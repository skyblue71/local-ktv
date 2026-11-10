// 歌曲頁的「✂ 裁切」：MV 前面有劇情、後面有片尾的話，可以只唱中間那一段。
//   不會刪掉檔案，只記住「從幾秒唱到幾秒」，隨時可以改，或按「不裁切」還原。
//   上面有播放器（有 MV 就放 MV），播到想要的地方，按「用現在的位置」就好。
//
//   裁切只決定播哪一段，跟歌詞的時間無關：歌詞永遠放在歌手真的唱的地方（server\trim.py）。

import * as api from '../api.js';
import { icon } from '../icons.js';
import { escapeHtml, formatTime, helpTip, showToast } from '../ui.js';

// 小問號裡的說明
const TRIM_HELP = '只唱其中一段，例如跳過 MV 前面的劇情、後面的片尾。\n' +
  '不會刪掉檔案，隨時可以按「不裁切」還原。\n' +
  '用下面的播放器找到要開始（結束）的地方，按「目前位置」，再按「儲存」\n\n' +
  '會影響：只播、只評分這一段，分數也只算這一段。\n' +
  '不會影響：歌詞的時間、評分條的位置（裁完字幕一樣對得齊）';
const SUGGEST_HELP = '找出歌開始前、結束後的劇情（說話、人聲），幫你填好時間。按「儲存」才會套用。\n' +
  '只找頭和尾。歌中間的劇情裁不掉，但那裡沒有歌詞，本來就沒有評分條、不扣分';

// 現在的裁切狀態，例如「目前：0:54 ～ 4:45」；沒有裁切就不寫
function stateText(song) {
  const start = Number(song.trim_start) || 0;
  const end = Number(song.trim_end) || 0;
  if (start <= 0 && end <= 0) {
    return '';
  }
  let endText = '最後';
  if (end > 0) {
    endText = formatTime(end);
  }
  return '目前：' + formatTime(start) + ' ～ ' + endText;
}

// 自動找到的劇情，例如「從 0:51.6 開始」「到 4:30.2 結束」
function suggestionText(suggestion) {
  const parts = [];
  if (suggestion.start > 0) {
    parts.push('從 ' + preciseTime(suggestion.start) + ' 開始');
  }
  if (suggestion.end > 0) {
    parts.push('到 ' + preciseTime(suggestion.end) + ' 結束');
  }
  return parts.join('、');
}

// 滑鼠移上去看的詳細內容：劇情有幾秒
function suggestionDetail(suggestion) {
  const parts = [];
  if (suggestion.start > 0 && suggestion.song_zero > 0) {
    parts.push('歌詞的版本從 ' + preciseTime(suggestion.song_zero) + ' 才開始，前面有 ' +
      suggestion.voice_before + ' 秒的人聲，不是歌');
  } else if (suggestion.start > 0) {
    parts.push('開頭有 ' + suggestion.talk_before + ' 秒的人在說話');
  }
  if (suggestion.end > 0) {
    parts.push('結尾有 ' + suggestion.talk_after + ' 秒的人在說話');
  }
  return parts.join('\n');
}

// 秒數 → 「分:秒.十分之一秒」，例如 54.3 → 0:54.3
function preciseTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  let rest = (seconds - minutes * 60).toFixed(1);
  if (seconds - minutes * 60 < 10) {
    rest = '0' + rest;
  }
  return minutes + ':' + rest;
}

export function renderTrimPanel(box, song, onSaved) {
  const start = Number(song.trim_start) || 0;
  const end = Number(song.trim_end) || 0;
  let openAttribute = '';   // 有裁切的話，一進來就展開
  if (start > 0 || end > 0) {
    openAttribute = ' open';
  }

  box.innerHTML =
    '<details class="trim-details"' + openAttribute + '>' +
    '  <summary>' + icon('scissors') + ' 裁切' + helpTip(TRIM_HELP) + '</summary>' +
    '  <div class="trim-row">' +
    '    <button class="btn btn-small" id="trim-suggest">' + icon('wand') + ' 自動找劇情</button>' + helpTip(SUGGEST_HELP) +
    '    <span class="small" id="trim-suggest-text"></span>' +
    '  </div>' +
    '  <div class="trim-media-box" id="trim-media-box"></div>' +
    '  <div class="trim-grid">' +
    '    <span class="trim-label">開始</span>' +
    '    <label class="offset-value"><input class="input" type="number" id="trim-start" min="0" step="0.1"> 秒</label>' +
    '    <span class="muted small trim-time" id="trim-start-text"></span>' +
    '    <div class="trim-buttons">' +
    '      <button class="btn btn-small" id="trim-start-now" title="用播放器現在的位置">' + icon('target') + ' 目前位置</button>' +
    '      <button class="btn btn-small" id="trim-start-listen" title="從這裡開始聽">' + icon('play') + ' 試聽</button>' +
    '    </div>' +
    '    <span class="trim-label">結束</span>' +
    '    <label class="offset-value"><input class="input" type="number" id="trim-end" min="0" step="0.1" placeholder="最後"> 秒</label>' +
    '    <span class="muted small trim-time" id="trim-end-text"></span>' +
    '    <div class="trim-buttons">' +
    '      <button class="btn btn-small" id="trim-end-now" title="用播放器現在的位置">' + icon('target') + ' 目前位置</button>' +
    '      <button class="btn btn-small" id="trim-end-listen" title="聽結尾前 5 秒">' + icon('play') + ' 試聽</button>' +
    '    </div>' +
    '  </div>' +
    '  <p class="muted small" id="trim-state"></p>' +
    '  <div class="button-row">' +
    '    <button class="btn btn-primary" id="trim-save">' + icon('save') + ' 儲存</button>' +
    '    <button class="btn" id="trim-reset">不裁切</button>' +
    '  </div>' +
    '</details>';

  const startInput = box.querySelector('#trim-start');
  const endInput = box.querySelector('#trim-end');
  startInput.value = start;
  endInput.value = '';   // 空白 = 到最後
  if (end > 0) {
    endInput.value = end;
  }
  const state = box.querySelector('#trim-state');
  state.textContent = stateText(song);
  state.classList.toggle('hidden', state.textContent === '');

  function showTimes() {
    box.querySelector('#trim-start-text').textContent = preciseTime(Number(startInput.value) || 0);
    if (endInput.value === '' || Number(endInput.value) <= 0) {
      box.querySelector('#trim-end-text').textContent = '到最後 ' + formatTime(song.duration);
    } else {
      box.querySelector('#trim-end-text').textContent = preciseTime(Number(endInput.value));
    }
  }
  showTimes();
  startInput.addEventListener('input', showTimes);
  endInput.addEventListener('input', showTimes);

  // 播放器：打開「裁切」時才載入（不打開就不會去讀影片）
  let media = null;
  function getMedia() {
    if (media) {
      return media;
    }
    const mediaBox = box.querySelector('#trim-media-box');
    if (song.has_video) {
      mediaBox.innerHTML = '<video class="trim-media" controls preload="metadata"></video>';
      media = mediaBox.querySelector('video');
      media.src = api.videoUrl(song.id);
    } else {
      mediaBox.innerHTML = '<audio class="trim-media" controls preload="metadata"></audio>';
      media = mediaBox.querySelector('audio');
      media.src = api.audioUrl(song.id, 'instrumental');
    }
    return media;
  }
  const details = box.querySelector('details');
  if (details.open) {
    getMedia();
  }
  details.addEventListener('toggle', function () {
    if (details.open) {
      getMedia();
    } else if (media) {
      media.pause();
    }
  });

  box.querySelector('#trim-start-now').addEventListener('click', function () {
    startInput.value = getMedia().currentTime.toFixed(1);
    showTimes();
  });
  box.querySelector('#trim-end-now').addEventListener('click', function () {
    endInput.value = getMedia().currentTime.toFixed(1);
    showTimes();
  });
  box.querySelector('#trim-start-listen').addEventListener('click', function () {
    const player = getMedia();
    player.currentTime = Number(startInput.value) || 0;
    player.play();
  });
  box.querySelector('#trim-end-listen').addEventListener('click', function () {
    const player = getMedia();
    let endTime = Number(endInput.value) || 0;
    if (endTime <= 0) {
      endTime = song.duration;
    }
    player.currentTime = Math.max(0, endTime - 5);
    player.play();
  });

  // 自動找劇情：找到的話把建議的時間填進去（按「儲存」才會套用）
  box.querySelector('#trim-suggest').addEventListener('click', async function () {
    const text = box.querySelector('#trim-suggest-text');
    text.textContent = '尋找中…';
    try {
      const result = await api.suggestTrim(song.id);
      if (result.suggestion === null) {
        text.innerHTML = escapeHtml(result.reason);
        return;
      }
      startInput.value = result.suggestion.start;
      endInput.value = '';
      if (result.suggestion.end > 0) {
        endInput.value = result.suggestion.end;
      }
      showTimes();
      text.innerHTML = '已填好：' + escapeHtml(suggestionText(result.suggestion)) +
        helpTip(suggestionDetail(result.suggestion) + '\n可以先按「試聽」確認，再按「儲存」');
    } catch (error) {
      text.textContent = '找不到：' + error.message;
    }
  });

  async function save(data) {
    try {
      const result = await api.saveTrim(song.id, data);
      if (media) {
        media.pause();
      }
      showToast(result.message || '已儲存', 'ok');
      if (onSaved) {
        onSaved();
      }
    } catch (error) {
      showToast('儲存失敗：' + error.message, 'error');
    }
  }

  box.querySelector('#trim-save').addEventListener('click', function () {
    save({
      start: Number(startInput.value) || 0,
      end: Number(endInput.value) || 0,
    });
  });
  box.querySelector('#trim-reset').addEventListener('click', function () {
    save({ start: 0, end: 0 });
  });
}
