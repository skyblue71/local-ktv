// 歌曲詳情頁：開始唱歌、編輯歌詞、看分數紀錄。

import * as api from '../api.js';
import { lineHtml } from '../game/lyricsView.js';
import { t, tServer } from '../i18n.js';
import { icon, iconButton } from '../icons.js';
import { loadSettings } from '../settings.js';
import { confirmAction, escapeHtml, formatTime, helpTip, openDialog, showToast } from '../ui.js';
import { openEditSongDialog } from './editSongDialog.js';
import { renderTrimPanel } from './trimPanel.js';

let refreshTimer = null;
let songId = '';

// 歌名下面的小標籤：長度、去人聲、字幕、MV、來源、裁切（詳細的放在滑鼠移上去的提示）
function songTags(song) {
  const tags = [];
  tags.push('<span class="tag">' + icon('clock') + ' ' + formatTime(song.duration) + '</span>');
  let source = '';
  if (song.lyrics_source) {
    source = t('來源：{source}', { source: tServer(song.lyrics_source) });
  }
  if (song.has_lyrics && song.lyrics_synced) {
    tags.push('<span class="tag tag-ok" title="' + escapeHtml(source) + '">' + icon('lyrics') + ' ' + t('字幕') + '</span>');
  } else if (song.has_lyrics) {
    tags.push('<span class="tag tag-warn" title="' + t('歌詞沒有時間，到「編輯歌詞」用點按同步') + '">' + t('歌詞沒時間') + '</span>');
  } else {
    tags.push('<span class="tag tag-warn">' + t('沒歌詞') + '</span>');
  }
  if (song.has_vocals) {
    tags.push('<span class="tag tag-ok" title="' + t('可以開導唱') + '">' + icon('vocals') + ' ' + t('已去人聲') + '</span>');
  }
  if (song.has_video) {
    tags.push('<span class="tag tag-ok">' + icon('video') + ' MV</span>');
  }
  if (song.has_chart) {
    tags.push('<span class="tag tag-ok" title="' + t('唱歌時用你修的評分條') + '">' + icon('bars') + ' ' + t('修過譜') + '</span>');
  }
  if (song.source === 'YouTube') {
    tags.push('<span class="tag">YouTube</span>');
  }
  const trimStart = Number(song.trim_start) || 0;
  const trimEnd = Number(song.trim_end) || 0;
  if (trimStart > 0 || trimEnd > 0) {
    let endText = formatTime(song.duration);
    if (trimEnd > 0) {
      endText = formatTime(trimEnd);
    }
    tags.push('<span class="tag" title="' + t('只唱這一段') + '">' + icon('scissors') + ' ' + formatTime(trimStart) + '～' + endText + '</span>');
  }
  return tags.join('');
}

export async function enter(app, id) {
  songId = id;
  app.innerHTML = '<div class="page"><p class="muted">' + t('載入中…') + '</p></div>';
  await render(app);
}

export function leave() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

async function render(app) {
  let song;
  try {
    song = await api.getSong(songId);
  } catch (error) {
    app.innerHTML = '<div class="page"><p>' + t('找不到這首歌。') + '</p><a href="#/" class="btn">' + t('回歌曲庫') + '</a></div>';
    return;
  }

  // 封面（點一下可以編輯）
  let cover = '<div class="cover cover-big cover-placeholder cover-editable" id="hero-cover" title="' + t('點一下換封面') + '">' +
    escapeHtml((song.title || '?').charAt(0)) + '</div>';
  if (song.has_cover) {
    cover = '<div class="cover cover-big cover-editable" id="hero-cover" title="' + t('點一下換封面') + '"><img src="' +
      api.coverUrl(song.id, song.cover_version) + '" alt=""></div>';
  }

  // 最上面那一大塊的背景：有封面的話，把封面的顏色暈開鋪在後面（只是好看）
  let glow = '';
  if (song.has_cover) {
    glow = '<div class="hero-glow" style="background-image:url(' + api.coverUrl(song.id, song.cover_version) + ')"></div>';
  }

  const ready = song.status === 'ready';
  let statusHtml = '';
  if (song.status === 'error') {
    statusHtml = '<div class="notice notice-error">' + t('處理失敗：{error}', { error: escapeHtml(tServer(song.error)) }) + '</div>';
  } else if (!ready) {
    statusHtml =
      '<div class="notice">' +
      '  <div>' + escapeHtml(tServer(song.stage)) + '…</div>' +
      '  <div class="progress"><div class="progress-fill" style="width:' + song.progress + '%"></div></div>' +
      '</div>';
  } else if (song.has_vocals && song.pitch_source === 'original') {
    statusHtml = '<div class="notice">' + t('人聲沒分離成功，評分可能不準') +
      helpTip(t('評分用的旋律是從原曲分析的')) + '</div>';
  }

  const songPath = '#/song/' + encodeURIComponent(song.id);
  app.innerHTML =
    '<div class="page">' +
    '  <a href="#/" class="back-link">' + icon('back') + t('歌曲庫') + '</a>' +
    '  <div class="song-hero">' + glow + cover +
    '    <div class="song-hero-info">' +
    '      <div class="hero-title-row">' +
    '        <h1>' + escapeHtml(song.title) + '</h1>' +
    '        <div class="hero-tools">' +
    iconButton('edit', t('編輯歌名、歌手、封面'), 'rename-button', 'btn-ghost') +
    iconButton('refresh', t('重新處理'), 'reprocess-button', 'btn-ghost') +
    iconButton('trash', t('刪除這首歌'), 'delete-button', 'btn-ghost btn-danger') +
    '        </div>' +
    '      </div>' +
    '      <p class="song-artist-big">' + escapeHtml(song.artist || t('未知歌手')) + '</p>' +
    '      <div class="tags">' + songTags(song) + '</div>' +
    statusHtml +
    '      <div class="button-row">' +
    '        <a class="btn btn-primary btn-big' + (ready ? '' : ' disabled') + '" href="#/sing/' + encodeURIComponent(song.id) + '">' + icon('mic') + ' ' + t('開始唱歌') + '</a>' +
    '        <a class="btn' + (ready && song.has_vocals ? '' : ' disabled') + '" href="#/sing/' + encodeURIComponent(song.id) + '?test=1" title="' + t('不用麥克風，讓原唱自己唱，確認評分正常（分數不會存）') + '">' + icon('flask') + ' ' + t('測試') + '</a>' +
    '        <a class="btn" href="' + songPath + '/lyrics">' + icon('lyrics') + ' ' + t('編輯歌詞') + '</a>' +
    '        <a class="btn' + (ready ? '' : ' disabled') + '" href="' + songPath + '/chart" title="' + t('自己修評分條、調每個字的時間') + '">' + icon('bars') + ' ' + t('修譜') + '</a>' +
    '      </div>' +
    '    </div>' +
    '  </div>' +
    '  <section class="panel" id="trim-panel"></section>' +
    '  <div class="two-columns">' +
    '    <section class="panel"><h2>' + t('分數排行') + '</h2><div id="score-list" class="muted">' + t('載入中…') + '</div></section>' +
    '    <section class="panel"><h2>' + t('歌詞') + '</h2><div id="lyrics-preview" class="lyrics-preview muted">' + t('載入中…') + '</div></section>' +
    '  </div>' +
    '</div>';

  // 裁切（處理完成的歌才能裁）
  const trimBox = document.getElementById('trim-panel');
  if (ready) {
    renderTrimPanel(trimBox, song, function () {
      render(app);
    });
  } else {
    trimBox.classList.add('hidden');
  }

  // 編輯歌名、歌手、封面（按鈕或點封面）
  function editSong() {
    openEditSongDialog(song, function () {
      render(app);
    });
  }
  document.getElementById('rename-button').addEventListener('click', editSong);
  document.getElementById('hero-cover').addEventListener('click', editSong);

  document.getElementById('reprocess-button').addEventListener('click', function () {
    const dialog = openDialog(t('重新處理'),
      '<p>' + t('重新分析音高、產生字幕') + helpTip(t('會重做：轉檔、分人聲、評分條（AI 的）、字幕。\n') +
        t('會留著：歌詞、你修過的譜、你調過的字、裁切、分數、封面。\n\n') +
        t('選「不去人聲」：沒有導唱、不能用「測試」，AI 也聽不到字（字幕照評分條分，比較不準）')) + '</p>' +
      '<div class="dialog-actions">' +
      '  <button class="btn" id="no-separate">' + t('不去人聲') + '</button>' +
      '  <button class="btn btn-primary" id="yes-separate">' + t('AI 去人聲') + '</button>' +
      '</div>');
    async function start(separate) {
      dialog.close();
      await api.reprocessSong(song.id, separate);
      showToast(t('已重新排隊處理'), 'ok');
      render(app);
    }
    dialog.box.querySelector('#no-separate').addEventListener('click', function () {
      start(false);
    });
    dialog.box.querySelector('#yes-separate').addEventListener('click', function () {
      start(true);
    });
  });

  document.getElementById('delete-button').addEventListener('click', async function () {
    if (!confirmAction(t('確定要刪除「{title}」嗎？\n影片、歌詞、你修過的譜、調過的字、分數紀錄都會一起刪掉，不能還原。', { title: song.title }))) {
      return;
    }
    await api.deleteSong(song.id);
    showToast(t('已刪除'), 'ok');
    location.hash = '#/';
  });

  loadScores(song.id);
  loadLyricsPreview(song.id);

  // 還在處理中：2 秒後重新整理
  if (song.status === 'waiting' || song.status === 'processing') {
    refreshTimer = setTimeout(function () {
      if (location.hash === '#/song/' + encodeURIComponent(song.id)) {
        render(app);
      }
    }, 2000);
  }
}

async function loadScores(id) {
  const box = document.getElementById('score-list');
  let scores = [];
  try {
    scores = await api.getScores(id);
  } catch (error) {
    box.textContent = t('讀取失敗');
    return;
  }
  if (scores.length === 0) {
    box.textContent = t('還沒有人唱過，來當第一個吧！');
    return;
  }
  scores.sort(function (a, b) {
    return b.total - a.total;
  });
  let html = '<table class="score-table"><tr><th>#</th><th>' + t('名字') + '</th><th>' + t('分數') + '</th><th>' + t('日期') + '</th></tr>';
  for (let i = 0; i < scores.length && i < 10; i++) {
    const score = scores[i];
    html += '<tr><td>' + (i + 1) + '</td><td>' + escapeHtml(score.player) + '</td>' +
      '<td class="score-number">' + Number(score.total).toFixed(3) + '</td>' +
      '<td class="muted">' + escapeHtml(score.date || '') + '</td></tr>';
  }
  html += '</table>';
  box.classList.remove('muted');
  box.innerHTML = html;
}

async function loadLyricsPreview(id) {
  const box = document.getElementById('lyrics-preview');
  const settings = loadSettings();
  let data;
  try {
    data = await api.getLyrics(id);
  } catch (error) {
    box.textContent = t('讀取失敗');
    return;
  }
  if (!data.lyrics || data.lyrics.lines.length === 0) {
    box.textContent = t('還沒有歌詞。');
    return;
  }
  let html = '';
  for (const line of data.lyrics.lines) {
    let time = '';
    if (line.start !== undefined) {
      time = '<span class="line-time">' + formatTime(line.start) + '</span>';
    }
    html += '<div class="preview-line">' + time + '<div class="preview-text">' +
      lineHtml(line, settings) + '</div></div>';
  }
  box.classList.remove('muted');
  box.innerHTML = html;
}
