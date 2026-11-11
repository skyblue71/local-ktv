// 歌曲庫（首頁）：顯示所有歌曲、搜尋、排序、篩選、加入新歌。
//   排序、篩選的選擇記在這台電腦的瀏覽器裡（下次打開還是一樣）
//   在頁面上按「/」可以直接打字搜尋

import * as api from '../api.js';
import { t, tServer } from '../i18n.js';
import { icon } from '../icons.js';
import { escapeHtml, formatTime, showToast } from '../ui.js';
import { openAddSongDialog } from './addSongDialog.js';

const VIEW_KEY = 'karaoke-library-view';   // 排序、篩選記在瀏覽器的哪個名字底下

// 排序：value → 名字
const SORTS = [
  ['new', t('最近加入')],
  ['title', t('歌名')],
  ['artist', t('歌手')],
  ['score', t('最高分')],
  ['length', t('長度')],
];

// 篩選：value → 名字
const FILTERS = [
  ['all', t('全部')],
  ['unsung', t('還沒唱過')],
  ['sung', t('唱過的')],
  ['nolyrics', t('缺字幕')],
  ['mv', t('有 MV')],
];

let refreshTimer = null;
let allSongs = [];
let systemInfo = null;

function optionsHtml(list, selected) {
  let html = '';
  for (const option of list) {
    html += '<option value="' + option[0] + '"' + (option[0] === selected ? ' selected' : '') + '>' + option[1] + '</option>';
  }
  return html;
}

// 讀、存排序和篩選（瀏覽器不給存也沒關係，用預設的）
function loadView() {
  const view = { sort: 'new', filter: 'all' };
  try {
    const saved = JSON.parse(localStorage.getItem(VIEW_KEY) || '{}');
    if (saved.sort) {
      view.sort = saved.sort;
    }
    if (saved.filter) {
      view.filter = saved.filter;
    }
  } catch (error) {
    // 讀不到就用預設
  }
  return view;
}

function saveView() {
  try {
    localStorage.setItem(VIEW_KEY, JSON.stringify({
      sort: document.getElementById('sort-select').value,
      filter: document.getElementById('filter-select').value,
    }));
  } catch (error) {
    // 存不了也沒關係
  }
}

export async function enter(app) {
  const view = loadView();
  app.innerHTML =
    '<div class="page">' +
    '  <div class="page-header">' +
    '    <div class="title-line">' +
    '      <h1>' + t('歌曲庫') + '</h1>' +
    '      <span class="muted" id="song-count"></span>' +
    '    </div>' +
    '    <button id="add-button" class="btn btn-primary">' + icon('plus') + ' ' + t('加入歌曲') + '</button>' +
    '  </div>' +
    '  <div class="library-toolbar">' +
    '    <label class="search-box">' + icon('search') +
    '      <input id="search-box" class="input" type="search" placeholder="' + t('搜尋歌名、歌手') + '" title="' + t('按 / 也可以直接打字搜尋') + '">' +
    '    </label>' +
    '    <label class="select-box" title="' + t('篩選') + '">' + icon('filter') +
    '      <select id="filter-select" class="input" aria-label="' + t('篩選') + '">' + optionsHtml(FILTERS, view.filter) + '</select>' +
    '    </label>' +
    '    <label class="select-box" title="' + t('排序') + '">' + icon('sort') +
    '      <select id="sort-select" class="input" aria-label="' + t('排序') + '">' + optionsHtml(SORTS, view.sort) + '</select>' +
    '    </label>' +
    '  </div>' +
    '  <div id="song-grid" class="song-grid"></div>' +
    '  <p class="page-footer muted small" id="system-line"></p>' +
    '</div>';

  document.getElementById('add-button').addEventListener('click', function () {
    openAddSongDialog(systemInfo, function () {
      loadSongs();
    });
  });
  document.getElementById('search-box').addEventListener('input', renderSongs);
  for (const id of ['sort-select', 'filter-select']) {
    document.getElementById(id).addEventListener('change', function () {
      saveView();
      renderSongs();
    });
  }
  document.addEventListener('keydown', onKeyDown);

  loadSystemInfo();
  await loadSongs();
}

export function leave() {
  document.removeEventListener('keydown', onKeyDown);
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

// 按「/」：直接跳到搜尋欄（正在打字的時候不算）
function onKeyDown(event) {
  if (event.key !== '/' || event.ctrlKey || event.altKey || event.metaKey) {
    return;
  }
  const target = event.target;
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) {
    return;
  }
  if (document.querySelector('.dialog-backdrop')) {
    return;   // 有對話方塊開著
  }
  event.preventDefault();
  document.getElementById('search-box').focus();
}

async function loadSystemInfo() {
  const line = document.getElementById('system-line');
  try {
    systemInfo = await api.getSystemInfo();
    if (!line) {
      return;
    }
    if (systemInfo.separator && systemInfo.gpu) {
      line.textContent = t('AI 去人聲用：{device}', { device: systemInfo.gpu });
    } else if (systemInfo.separator) {
      line.textContent = t('AI 去人聲用：CPU（比較慢）');
    } else {
      line.textContent = t('AI 去人聲：未安裝（會直接用原曲當伴奏）');
    }
  } catch (error) {
    if (line) {
      line.textContent = '';
    }
    showToast(t('連不到伺服器：{message}', { message: error.message }), 'error');
  }
}

async function loadSongs() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  try {
    allSongs = await api.getSongs();
  } catch (error) {
    showToast(t('讀取歌曲失敗：{message}', { message: error.message }), 'error');
    return;
  }
  if (!document.getElementById('song-grid')) {
    return;  // 已經換頁了
  }
  renderSongs();

  // 有歌還在處理中的話，2 秒後再更新一次
  let busy = false;
  for (const song of allSongs) {
    if (song.status === 'waiting' || song.status === 'processing') {
      busy = true;
    }
  }
  if (busy) {
    refreshTimer = setTimeout(loadSongs, 2000);
  }
}

// 這首歌符不符合篩選
function passFilter(song, filter) {
  const sung = song.best_score !== null && song.best_score !== undefined;
  if (filter === 'unsung') {
    return !sung;
  }
  if (filter === 'sung') {
    return sung;
  }
  if (filter === 'nolyrics') {
    return song.status === 'ready' && !(song.has_lyrics && song.lyrics_synced);
  }
  if (filter === 'mv') {
    return song.has_video === true;
  }
  return true;
}

// 照選的方式排（新的陣列，不改 allSongs）
function sortSongs(songs, sort) {
  const list = songs.slice();
  list.sort(function (a, b) {
    if (sort === 'title') {
      return (a.title || '').localeCompare(b.title || '', 'zh-Hant', { numeric: true });
    }
    if (sort === 'artist') {
      return (a.artist || '').localeCompare(b.artist || '', 'zh-Hant', { numeric: true }) ||
        (a.title || '').localeCompare(b.title || '', 'zh-Hant', { numeric: true });
    }
    if (sort === 'score') {
      // 沒唱過的放最後
      const scoreA = a.best_score === null || a.best_score === undefined ? -1 : Number(a.best_score);
      const scoreB = b.best_score === null || b.best_score === undefined ? -1 : Number(b.best_score);
      return scoreB - scoreA;
    }
    if (sort === 'length') {
      return (a.duration || 0) - (b.duration || 0);
    }
    // 最近加入：歌曲 ID 開頭就是加入的時間，大的比較新
    return b.id < a.id ? -1 : 1;
  });
  return list;
}

function renderSongs() {
  const grid = document.getElementById('song-grid');
  if (!grid) {
    return;
  }
  const keyword = document.getElementById('search-box').value.trim().toLowerCase();
  const filter = document.getElementById('filter-select').value;
  const sort = document.getElementById('sort-select').value;

  const shown = [];
  for (const song of allSongs) {
    const text = (song.title + ' ' + (song.artist || '')).toLowerCase();
    if (keyword !== '' && text.indexOf(keyword) < 0) {
      continue;
    }
    if (!passFilter(song, filter)) {
      continue;
    }
    shown.push(song);
  }

  let html = '';
  for (const song of sortSongs(shown, sort)) {
    html += songCardHtml(song);
  }
  if (allSongs.length === 0) {
    html =
      '<div class="empty-state">' +
      '  <div class="empty-icon">' + icon('music') + '</div>' +
      '  <p>' + t('還沒有歌曲，按「加入歌曲」開始') + '</p>' +
      '</div>';
  } else if (shown.length === 0) {
    html = '<div class="empty-state"><p>' + t('沒有符合的歌曲') + '</p></div>';
  }
  grid.innerHTML = html;

  let count = t('{count} 首', { count: allSongs.length });
  if (shown.length !== allSongs.length) {
    count = t('{shown} / {count} 首', { shown: shown.length, count: allSongs.length });
  }
  document.getElementById('song-count').textContent = count;
}

function songCardHtml(song) {
  let cover = '<div class="cover cover-placeholder">' + escapeHtml((song.title || '?').charAt(0)) + '</div>';
  if (song.has_cover) {
    cover = '<div class="cover"><img src="' + api.coverUrl(song.id, song.cover_version) + '" alt="" loading="lazy"></div>';
  }

  // 下面一排：有的功能用小圖示（滑鼠移上去看是什麼），缺的才用字提醒
  let status = '';
  if (song.status === 'ready') {
    const parts = [];
    if (song.has_lyrics && song.lyrics_synced) {
      parts.push('<span class="feature" title="' + t('有字幕') + '">' + icon('lyrics') + '</span>');
    } else if (song.has_lyrics) {
      parts.push('<span class="tag tag-warn" title="' + t('歌詞沒有時間，到「編輯歌詞」用點按同步') + '">' + t('歌詞沒時間') + '</span>');
    } else {
      parts.push('<span class="tag tag-warn">' + t('沒歌詞') + '</span>');
    }
    if (song.has_vocals) {
      parts.push('<span class="feature" title="' + t('已去人聲（可以開導唱）') + '">' + icon('vocals') + '</span>');
    }
    if (song.has_video) {
      parts.push('<span class="feature" title="' + t('有 MV') + '">' + icon('video') + '</span>');
    }
    status = '<div class="card-features">' + parts.join('') + '</div>';
  } else if (song.status === 'error') {
    status = '<div class="card-features"><span class="tag tag-error">' + t('處理失敗') + '</span></div>';
  } else {
    status =
      '<div class="progress-text">' + escapeHtml(tServer(song.stage)) + '</div>' +
      '<div class="progress"><div class="progress-fill" style="width:' + song.progress + '%"></div></div>';
  }

  let best = '';
  if (song.best_score !== null && song.best_score !== undefined) {
    best = '<div class="best-score" title="' + t('最高分') + '">' + Number(song.best_score).toFixed(1) + '</div>';
  }

  let meta = escapeHtml(song.artist || t('未知歌手'));
  if (song.duration) {
    meta += ' · ' + formatTime(song.duration);
  }

  return (
    '<a class="song-card" href="#/song/' + encodeURIComponent(song.id) + '" title="' + escapeHtml(song.title) + '">' +
    cover + best +
    '  <div class="song-info">' +
    '    <div class="song-title">' + escapeHtml(song.title) + '</div>' +
    '    <div class="song-artist">' + meta + '</div>' +
    status +
    '  </div>' +
    '</a>'
  );
}
