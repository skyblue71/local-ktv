// 修譜頁：自己修評分條（AI 漏掉的補上、做錯的改掉）    網址：#/song/<ID>/chart
//
// 分工：畫面 chartCanvas.js、資料和復原 chartModel.js、評分條的音 noteTone.js、這個檔案管滑鼠鍵盤和存檔
// 改了會自動存檔（伺服器 chart_store.py 存成 chart.json）。AI 的譜（pitch.json）不會被改到，可以隨時還原。
// 存過之後，唱歌時就用你修的譜：你畫的就算（不再只算有歌詞的部分）。

import * as api from '../api.js';
import { getAudioContext, getOutputLatency } from '../audio/audioContext.js';
import { NoteTone } from '../audio/noteTone.js';
import { SongPlayer } from '../audio/songPlayer.js';
import { ChartCanvas, timeText } from '../game/chartCanvas.js';
import { ChartModel, MIN_LENGTH } from '../game/chartModel.js';
import { notesInLyrics } from '../game/lyricNotes.js';
import { applyQuietSetting } from '../game/quietParts.js';
import { splitAtSyllables } from '../game/syllableBars.js';
import { fillMissed } from '../game/twoEars.js';
import { isUnheardNote } from '../game/scorer.js';
import { icon } from '../icons.js';
import { loadSettings } from '../settings.js';
import { confirmAction, escapeHtml, helpTip, showToast } from '../ui.js';

// 小問號裡的說明
const HELP =
  '拖評分條：移動（左右＝時間，上下＝音高）\n' +
  '拉評分條的頭尾：變長、變短\n' +
  '在空白的地方拖一下：新增\n' +
  '虛線框：AI 有聽到、但沒評分的音，點一下加進來\n' +
  '淡淡的線：AI 聽到的原唱音高\n' +
  '點最上面的時間尺：從那裡播放\n\n' +
  '下面那一排字：字幕每個字的時間\n' +
  '拖一個字：移動；拉頭尾：改開始、結束\n' +
  '評分條會跟著字走（你修過譜的話不會動）\n' +
  '選一個粉紅色的字按 Delete：這個字還原\n\n' +
  '空白鍵：播放／暫停\n' +
  'Delete：刪除\n' +
  '↑ ↓：改音高\n' +
  'Ctrl+Z：復原\n\n' +
  '藍色是 AI 的，粉紅色是你畫的或改過的。改了會自動存檔\n\n' +
  '改過評分條之後，唱歌就用你修的譜：\n' +
  '之後換歌詞、調字、改「清掉小聲雜音」，評分條都不會再動。\n' +
  '「還原 AI 的譜」：評分條回到跟著字走。\n' +
  '「還原字的時間」：你調過的字回到程式算的';
const TONE_HELP = '播放時，播到評分條就發出那個音。\n跟原唱一起聽，就知道評分條對不對';

const SAVE_DELAY = 800;     // 改完幾毫秒後存檔（連續改的時候不要一直存）
const ZOOM_STEP = 1.5;      // 放大、縮小一次差幾倍
const MIN_VISIBLE = 3;      // 最多放大到畫面寬度放 3 秒
const MAX_VISIBLE = 60;     // 最多縮小到畫面寬度放 60 秒
const DRAG_START = 4;       // 滑鼠移動超過幾像素才算「拖」（只是點一下不算）
const FOLLOW_RIGHT = 0.85;  // 播放時，播放線跑到畫面寬度的這裡，畫面就往後捲
const FOLLOW_LEFT = 0.15;   // 捲完之後，播放線在畫面的這裡
const MIN_WORD = 0.05;      // 一個字最短幾秒（跟伺服器 word_store.py 的 MIN_LENGTH 一樣）
const TOUCHING = 0.011;     // 兩個字的交界差不到這麼多秒，算「連著」（拉交界時兩個字一起動）

let page = null;

export async function enter(app, id) {
  page = { songId: id, loop: 0, saveTimer: null, saving: false, dirty: false, drag: null,
    player: null, tone: null, lastTime: '', lastPlaying: null };
  const myPage = page;
  app.innerHTML = '<div class="page"><p class="muted">載入中…</p></div>';

  let results;
  try {
    // 你調過的字（讀不到的話，當作沒調過）
    const wordsRequest = api.getWords(id).catch(function () {
      return { words: [] };
    });
    results = await Promise.all([api.getSong(id), api.getPitch(id), api.getLyrics(id), api.getChart(id), wordsRequest]);
  } catch (error) {
    if (page === myPage) {
      app.innerHTML = '<div class="page"><p>沒辦法修譜：' + escapeHtml(error.message) + '</p>' +
        '<a class="btn" href="#/song/' + encodeURIComponent(id) + '">返回</a></div>';
    }
    return;
  }
  if (page !== myPage) {
    return;   // 載入途中離開了
  }
  page.song = results[0];
  page.pitch = results[1];
  page.settings = loadSettings();
  page.hasChart = results[3].notes !== null;
  page.words = results[4].words || [];   // 你調過的字的時間（word_store.py）
  page.selectedWord = null;              // 現在選的字：{ line, index, token }
  // 字幕、和「唱歌時會評分的 AI 音符」（字的時間改了就要重算）
  setLyrics(results[2].lyrics);

  // 一開始的譜：修過就用你修的；沒修過就用 AI 的
  let startNotes = page.aiNotes;
  if (page.hasChart) {
    startNotes = results[3].notes;
  }
  page.model = new ChartModel(startNotes);

  render(app);
  loadAudio(myPage);
  page.loop = requestAnimationFrame(loop);
}

export function leave() {
  if (page === null) {
    return;
  }
  cancelAnimationFrame(page.loop);
  // 還沒存的，離開前馬上存
  if (page.saveTimer) {
    clearTimeout(page.saveTimer);
  }
  if (page.dirty) {
    api.saveChart(page.songId, page.model.plainNotes()).catch(function () {
      showToast('修譜沒存到，請再改一次', 'error');
    });
  }
  if (page.player) {
    page.player.destroy();
  }
  if (page.tone) {
    page.tone.destroy();
  }
  document.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('resize', onResize);
  page = null;
}

// 換一份字幕（剛載入、或字的時間改了）：跟唱歌頁一樣照設定清掉小聲雜音，再算出唱歌時會評分的 AI 音符
function setLyrics(lyrics) {
  page.lyrics = applyQuietSetting(lyrics, page.settings.quietDb, page.pitch);
  page.aiNotes = aiNotesInUse(page.pitch, page.lyrics);
}

// 沒修過譜時，唱歌會評分的音（跟唱歌頁一樣：只有歌詞的部分、照字切開、原唱聽得到的）
function aiNotesInUse(pitch, lyrics) {
  const result = [];
  const filled = fillMissed(pitch.notes, pitch, lyrics, page.settings.quietDb);
  for (const note of splitAtSyllables(notesInLyrics(filled, lyrics), lyrics)) {
    if (!isUnheardNote(pitch.heard, note.s, note.e)) {
      result.push(note);
    }
  }
  return result;
}

function render(app) {
  app.innerHTML =
    '<div class="page chart-page">' +
    '  <a href="#/song/' + encodeURIComponent(page.songId) + '" class="back-link">' + icon('back') + escapeHtml(page.song.title) + '</a>' +
    '  <div class="chart-head">' +
    '    <h1>修譜' + helpTip(HELP) + '</h1>' +
    '    <span class="muted small" id="chart-status"></span>' +
    '  </div>' +
    '  <div class="chart-toolbar">' +
    '    <button class="btn btn-primary" id="chart-play" disabled>載入中…</button>' +
    '    <span class="chart-time" id="chart-time">0:00.0</span>' +
    '    <label class="check"><input type="checkbox" id="chart-tone" checked> 評分條的音' + helpTip(TONE_HELP) + '</label>' +
    '    <span class="toolbar-space"></span>' +
    '    <button class="btn btn-small" id="chart-zoom-out" title="縮小">－</button>' +
    '    <button class="btn btn-small" id="chart-zoom-in" title="放大">＋</button>' +
    '    <button class="btn btn-small" id="chart-undo" title="Ctrl+Z">' + icon('undo') + ' 復原</button>' +
    '    <button class="btn btn-small" id="chart-delete" title="Delete">刪除</button>' +
    '    <button class="btn btn-small btn-ghost" id="chart-reset">還原 AI 的譜</button>' +
    '    <button class="btn btn-small btn-ghost" id="words-reset">還原字的時間</button>' +
    '  </div>' +
    '  <div class="chart-box"><canvas id="chart-canvas"></canvas></div>' +
    '  <input type="range" class="chart-scroll" id="chart-scroll" min="0" max="1" step="0.1" value="0" title="左右捲動">' +
    '</div>';

  if (page.hasChart) {
    setStatus('用的是你修的譜');
  } else {
    setStatus('用的是 AI 的譜');
  }

  const canvas = document.getElementById('chart-canvas');
  page.canvas = canvas;
  page.view = new ChartCanvas(canvas);
  page.view.fitPitchRange(page.pitch.notes.concat(page.model.notes), page.pitch.low || 60, page.pitch.high || 72);
  // 一開始從第一個評分條前 1 秒開始看
  if (page.model.notes.length > 0) {
    setViewStart(page.model.notes[0].s - 1);
  }
  page.ghosts = findGhosts();

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  document.addEventListener('keydown', onKeyDown);
  window.addEventListener('resize', onResize);

  document.getElementById('chart-play').addEventListener('click', function () {
    this.blur();   // 不然之後按空白鍵會變成又按一次這個按鈕
    togglePlay();
  });
  document.getElementById('chart-zoom-in').addEventListener('click', function () {
    this.blur();
    zoomAround(1 / ZOOM_STEP, zoomAnchor());
  });
  document.getElementById('chart-zoom-out').addEventListener('click', function () {
    this.blur();
    zoomAround(ZOOM_STEP, zoomAnchor());
  });
  document.getElementById('chart-undo').addEventListener('click', function () {
    this.blur();
    undo();
  });
  document.getElementById('chart-delete').addEventListener('click', function () {
    this.blur();
    deleteSelected();
  });
  document.getElementById('chart-reset').addEventListener('click', function () {
    this.blur();
    resetToAi();
  });
  document.getElementById('words-reset').addEventListener('click', function () {
    this.blur();
    resetWords();
  });
  document.getElementById('chart-scroll').addEventListener('input', function () {
    setViewStart(Number(this.value));
  });
  updateButtons();
}

function setStatus(text) {
  const status = document.getElementById('chart-status');
  if (status) {
    status.textContent = text;
  }
}

// ---------- 播放 ----------

async function loadAudio(myPage) {
  const player = new SongPlayer(getAudioContext());
  let vocalsUrl = null;
  if (page.song.has_vocals) {
    vocalsUrl = api.audioUrl(page.songId, 'vocals');
  }
  try {
    await player.load(api.audioUrl(page.songId, 'instrumental'), vocalsUrl);
  } catch (error) {
    player.destroy();
    if (page === myPage) {
      document.getElementById('chart-play').textContent = '音樂載入失敗';
    }
    return;
  }
  if (page !== myPage) {
    player.destroy();   // 載入途中離開了
    return;
  }
  player.setGuideVolume(100);   // 聽得到原唱，才知道評分條對不對
  player.setMasterVolume(page.settings.masterVolume);
  page.player = player;
  page.tone = new NoteTone(getAudioContext());
  page.tone.setMasterVolume(page.settings.masterVolume);
  const button = document.getElementById('chart-play');
  button.disabled = false;
  updatePlayButton();
}

async function togglePlay() {
  if (page.player === null) {
    return;
  }
  if (page.player.playing) {
    page.player.pause();
  } else {
    await getAudioContext().resume();   // 瀏覽器規定：要按了按鈕才能出聲
    page.player.play();
  }
  updatePlayButton();
}

function updatePlayButton() {
  const button = document.getElementById('chart-play');
  if (!button || page.player === null) {
    return;
  }
  page.lastPlaying = page.player.playing;
  if (page.player.playing) {
    button.innerHTML = icon('pause') + ' 暫停';
  } else {
    button.innerHTML = icon('play') + ' 播放';
  }
}

function seekTo(time) {
  if (page.player === null) {
    return;
  }
  page.player.seek(Math.max(0, time));
}

function songDuration() {
  if (page.player !== null) {
    return page.player.getDuration();
  }
  return Number(page.song.duration) || 0;
}

// 每個畫面：播放的話畫面跟著捲、發出評分條的音，然後重畫
function loop() {
  if (page === null) {
    return;
  }
  page.loop = requestAnimationFrame(loop);

  let now = 0;
  if (page.player !== null) {
    const playTime = page.player.getTime();
    now = playTime;
    if (page.player.playing) {
      now -= getOutputLatency();   // 畫面配合「你聽到的」時間
      follow(now);
    }
    // 評分條的音跟音樂同時送出去，喇叭的延遲一樣，所以用播放的時間（不扣延遲）
    const toneOn = document.getElementById('chart-tone').checked && page.player.playing;
    page.tone.update(playTime, page.model.notes, toneOn);
    if (page.player.playing !== page.lastPlaying) {
      updatePlayButton();   // 播完了
    }
  }

  page.view.draw({
    notes: page.model.notes,
    selected: page.model.selected,
    ghosts: page.ghosts,
    contour: page.pitch.contour,
    hop: page.pitch.hop || 0.01,
    lines: lyricLines(),
    selectedWord: page.selectedWord ? page.selectedWord.token : null,
    now: now,
  });

  const text = timeText(now);
  if (text !== page.lastTime) {
    page.lastTime = text;
    document.getElementById('chart-time').textContent = text;
  }
  updateScrollBar();
}

function lyricLines() {
  if (page.lyrics && page.lyrics.synced) {
    return page.lyrics.lines;
  }
  return null;
}

// ---------- 捲動、放大縮小 ----------

function setViewStart(time) {
  const view = page.view;
  const last = Math.max(0, songDuration() - view.secondsVisible);
  view.viewStart = Math.max(0, Math.min(last, time));
}

// 播放時：播放線快跑出畫面右邊（或在左邊外面），畫面就捲過去
function follow(now) {
  if (page.drag !== null) {
    return;   // 正在拖，不要動畫面
  }
  const view = page.view;
  if (now > view.viewStart + view.secondsVisible * FOLLOW_RIGHT || now < view.viewStart) {
    setViewStart(now - view.secondsVisible * FOLLOW_LEFT);
  }
}

// 放大縮小：anchor 這個時間點留在畫面上同一個位置
function zoomAround(factor, anchor) {
  const view = page.view;
  const before = view.secondsVisible;
  const after = Math.max(MIN_VISIBLE, Math.min(MAX_VISIBLE, before * factor));
  const ratio = (anchor - view.viewStart) / before;
  view.secondsVisible = after;
  setViewStart(anchor - ratio * after);
}

// 按鈕放大縮小時，以播放線為準（播放線不在畫面上就用畫面中間）
function zoomAnchor() {
  const view = page.view;
  let now = 0;
  if (page.player !== null) {
    now = page.player.getTime();
  }
  if (now >= view.viewStart && now <= view.viewStart + view.secondsVisible) {
    return now;
  }
  return view.viewStart + view.secondsVisible / 2;
}

function updateScrollBar() {
  const bar = document.getElementById('chart-scroll');
  const view = page.view;
  const last = Math.max(0, songDuration() - view.secondsVisible);
  const maxText = last.toFixed(1);
  if (bar.max !== maxText) {
    bar.max = maxText;
  }
  const valueText = view.viewStart.toFixed(1);
  if (bar.value !== valueText) {
    bar.value = valueText;
  }
}

function onWheel(event) {
  event.preventDefault();
  const view = page.view;
  if (event.ctrlKey) {
    // Ctrl + 滾輪：以滑鼠的位置放大縮小
    const point = canvasPoint(event);
    let factor = ZOOM_STEP;
    if (event.deltaY < 0) {
      factor = 1 / ZOOM_STEP;
    }
    zoomAround(factor, view.xToTime(point.x));
    return;
  }
  // 滾輪：左右捲動
  let delta = event.deltaX;
  if (Math.abs(event.deltaY) > Math.abs(delta)) {
    delta = event.deltaY;
  }
  setViewStart(view.viewStart + delta / 500 * view.secondsVisible);
}

function onResize() {
  page.view.resize();
}

// ---------- 滑鼠（手指也可以）----------

function canvasPoint(event) {
  const rect = page.canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

// 拖的時候滑鼠跑出畫面外也繼續收到移動（有些裝置不支援，就算了）
function capturePointer(event) {
  try {
    page.canvas.setPointerCapture(event.pointerId);
  } catch (error) {
    // 不支援也沒關係，只是拖出畫面外會停
  }
}

function onPointerDown(event) {
  const point = canvasPoint(event);
  const view = page.view;
  const model = page.model;
  const area = view.areaAt(point.x, point.y);

  // 時間尺、歌詞那一條：從那裡播放（可以按著拖）
  if (area === 'ruler' || area === 'lyrics') {
    capturePointer(event);
    page.drag = { mode: 'seek' };
    seekTo(view.xToTime(point.x));
    return;
  }
  // 每個字那一排：點到字就選起來、準備拖；點空白的地方 = 從那裡播放
  if (area === 'words') {
    capturePointer(event);
    const word = view.hitWord(point.x, lyricLines());
    if (word === null) {
      page.selectedWord = null;
      page.drag = { mode: 'seek' };
      seekTo(view.xToTime(point.x));
    } else {
      model.selected = null;
      page.selectedWord = word;
      page.drag = startWordDrag(word, point.x);
    }
    updateButtons();
    return;
  }
  if (area !== 'grid') {
    return;
  }
  capturePointer(event);
  page.selectedWord = null;

  // 點到評分條：選起來，準備拖（移動、拉頭、拉尾）
  const hit = view.hitNote(point.x, point.y, model.notes);
  if (hit !== null) {
    model.selected = hit.note;
    model.remember();
    page.drag = { mode: hit.part, note: hit.note, x: point.x, y: point.y,
      s: hit.note.s, e: hit.note.e, p: hit.note.p, moved: false };
    updateButtons();
    return;
  }

  // 點到虛線框（AI 有聽到、沒評分的音）：加進來
  const ghost = view.hitNote(point.x, point.y, page.ghosts);
  if (ghost !== null) {
    model.remember();
    model.add(ghost.note.s, ghost.note.e, ghost.note.p);
    page.drag = null;
    changed();
    return;
  }

  // 空白的地方：拖一下就畫一個新的；只是點一下 = 取消選取
  model.selected = null;
  page.drag = { mode: 'draw', x: point.x, y: point.y, time: view.xToTime(point.x),
    pitch: view.yToPitch(point.y), note: null, moved: false };
  updateButtons();
}

function onPointerMove(event) {
  const point = canvasPoint(event);
  const drag = page.drag;
  if (drag === null) {
    updateCursor(point);
    return;
  }
  const view = page.view;
  const model = page.model;
  if (drag.mode === 'seek') {
    seekTo(view.xToTime(point.x));
    return;
  }
  if (drag.mode === 'word') {
    if (!drag.moved && Math.abs(point.x - drag.x) < DRAG_START) {
      return;
    }
    drag.moved = true;
    moveWord(drag, view.xToTime(point.x) - view.xToTime(drag.x));
    return;
  }

  // 移動超過幾像素才算開始拖（只是點一下不會動到）
  if (!drag.moved) {
    if (Math.abs(point.x - drag.x) < DRAG_START && Math.abs(point.y - drag.y) < DRAG_START) {
      return;
    }
    drag.moved = true;
    if (drag.mode === 'draw') {
      model.remember();
      drag.note = model.add(drag.time, drag.time + MIN_LENGTH, drag.pitch);
    }
  }

  const time = view.xToTime(point.x);
  const shift = time - view.xToTime(drag.x);   // 左右拖了幾秒
  if (drag.mode === 'draw') {
    model.setTimes(drag.note, Math.min(drag.time, time), Math.max(drag.time, time));
  } else if (drag.mode === 'body') {
    const length = drag.e - drag.s;
    const start = Math.max(0, drag.s + shift);
    model.setTimes(drag.note, start, start + length);
    const pitchShift = view.yToPitch(point.y) - view.yToPitch(drag.y);   // 上下拖了幾個半音
    model.setPitch(drag.note, clampPitch(drag.p + pitchShift));
  } else if (drag.mode === 'start') {
    model.setTimes(drag.note, Math.min(drag.s + shift, drag.e - MIN_LENGTH), drag.e);
  } else if (drag.mode === 'end') {
    model.setTimes(drag.note, drag.s, Math.max(drag.e + shift, drag.s + MIN_LENGTH));
  }
}

function onPointerUp() {
  const drag = page.drag;
  page.drag = null;
  if (drag === null || drag.mode === 'seek') {
    return;
  }
  if (drag.mode === 'word') {
    if (drag.moved) {
      saveWordDrag(drag);
    }
    return;
  }
  if (drag.moved) {
    changed();
  } else if (drag.mode !== 'draw') {
    page.model.forget();   // 只是點一下選起來，沒有改
  }
}

// 滑鼠移到哪裡，游標就換成能做的事
function updateCursor(point) {
  const view = page.view;
  const area = view.areaAt(point.x, point.y);
  let cursor = 'default';
  if (area === 'ruler' || area === 'lyrics') {
    cursor = 'pointer';
  } else if (area === 'words') {
    const word = view.hitWord(point.x, lyricLines());
    cursor = 'pointer';
    if (word !== null && word.part === 'body') {
      cursor = 'grab';
    } else if (word !== null) {
      cursor = 'ew-resize';
    }
  } else if (area === 'grid') {
    const hit = view.hitNote(point.x, point.y, page.model.notes);
    if (hit !== null && hit.part === 'body') {
      cursor = 'grab';
    } else if (hit !== null) {
      cursor = 'ew-resize';
    } else if (view.hitNote(point.x, point.y, page.ghosts) !== null) {
      cursor = 'copy';
    } else {
      cursor = 'crosshair';
    }
  }
  page.canvas.style.cursor = cursor;
}

function clampPitch(pitch) {
  return Math.max(page.view.low, Math.min(page.view.high, pitch));
}

// ---------- 鍵盤 ----------

function onKeyDown(event) {
  if (document.querySelector('.dialog-backdrop')) {
    return;   // 對話方塊開著
  }
  const target = event.target;
  if (target.tagName === 'TEXTAREA' || (target.tagName === 'INPUT' && target.type === 'text')) {
    return;   // 正在打字
  }
  const model = page.model;
  if (event.code === 'Space') {
    event.preventDefault();
    togglePlay();
  } else if ((event.ctrlKey || event.metaKey) && event.code === 'KeyZ') {
    event.preventDefault();
    undo();
  } else if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault();
    if (page.selectedWord !== null) {
      restoreSelectedWord();   // 選的是字：這個字還原成程式算的
    } else {
      deleteSelected();
    }
  } else if ((event.key === 'ArrowUp' || event.key === 'ArrowDown') && model.selected !== null) {
    event.preventDefault();
    let step = 1;
    if (event.key === 'ArrowDown') {
      step = -1;
    }
    model.remember();
    model.setPitch(model.selected, clampPitch(model.selected.p + step));
    changed();
  }
}

// ---------- 調字的時間（下面那一排字；伺服器 word_store.py 存成 word_times.json）----------

// 這一句會唱的字（標點不算）
function sungTokens(line) {
  const result = [];
  for (const token of line.tokens || []) {
    if (token.syl > 0) {
      result.push(token);
    }
  }
  return result;
}

// 開始拖一個字。拉頭（尾）的時候，前（後）一個字如果跟它連著，交界一起動
function startWordDrag(word, x) {
  const sung = sungTokens(lyricLines()[word.line]);
  const token = word.token;
  const drag = { mode: 'word', part: word.part, word: word, x: x, s: token.start, e: token.end,
    partner: null, partnerIndex: -1, moved: false,
    before: word.index > 0 ? sung[word.index - 1] : null,                  // 同一句的前一個字
    after: word.index + 1 < sung.length ? sung[word.index + 1] : null };   // 同一句的後一個字
  if (word.part === 'start' && word.index > 0 && Math.abs(sung[word.index - 1].end - token.start) < TOUCHING) {
    drag.partner = sung[word.index - 1];
    drag.partnerIndex = word.index - 1;
  } else if (word.part === 'end' && word.index + 1 < sung.length &&
             Math.abs(sung[word.index + 1].start - token.end) < TOUCHING) {
    drag.partner = sung[word.index + 1];
    drag.partnerIndex = word.index + 1;
  }
  return drag;
}

// 拖的時候：先直接改畫面上的字（放開才存檔）。shift = 往右拖了幾秒
function moveWord(drag, shift) {
  const token = drag.word.token;
  if (drag.part === 'body') {
    // 整個字移動：不能把前、後一個字整個蓋掉（各留最短的長度）
    const length = drag.e - drag.s;
    let start = Math.max(0, drag.s + shift);
    if (drag.after !== null) {
      start = Math.min(start, drag.after.end - MIN_WORD - length);
    }
    if (drag.before !== null) {
      start = Math.max(start, drag.before.start + MIN_WORD);
    }
    token.start = start;
    token.end = start + length;
  } else if (drag.part === 'start') {
    let start = Math.max(0, Math.min(drag.s + shift, drag.e - MIN_WORD));
    if (drag.partner !== null) {
      start = Math.max(start, drag.partner.start + MIN_WORD);
      drag.partner.end = start;
    }
    token.start = start;
  } else {
    let end = Math.max(drag.e + shift, drag.s + MIN_WORD);
    if (drag.partner !== null) {
      end = Math.min(end, drag.partner.end - MIN_WORD);
      drag.partner.start = end;
    }
    token.end = end;
  }
}

// 這個字在存檔裡怎麼認：句子的文字、同樣文字的第幾句、這一句第幾個字
function wordEntry(lineIndex, tokenIndex, token) {
  const lines = lyricLines();
  let nth = 0;
  for (let i = 0; i < lineIndex; i++) {
    if (lines[i].text === lines[lineIndex].text) {
      nth++;
    }
  }
  return { line: lines[lineIndex].text, nth: nth, index: tokenIndex, text: token.text,
    start: Math.round(token.start * 1000) / 1000, end: Math.round(token.end * 1000) / 1000 };
}

function sameWord(a, b) {
  return a.line === b.line && a.nth === b.nth && a.index === b.index;
}

// 放開滑鼠：把拖過的字（和一起動的那個字）記下來，存檔
function saveWordDrag(drag) {
  const token = drag.word.token;
  const changedWords = [wordEntry(drag.word.line, drag.word.index, token)];
  if (drag.partner !== null) {
    changedWords.push(wordEntry(drag.word.line, drag.partnerIndex, drag.partner));
  }
  // 蓋到前、後一個字：那個字讓開。它是你調過的字的話，它的記錄也要跟著改
  //（沒調過的字伺服器會自己讓開，word_store.py）
  if (drag.before !== null && drag.before !== drag.partner && drag.before.end > token.start) {
    drag.before.end = token.start;
    if (drag.before.manual) {
      changedWords.push(wordEntry(drag.word.line, drag.word.index - 1, drag.before));
    }
  }
  if (drag.after !== null && drag.after !== drag.partner && drag.after.start < token.end) {
    drag.after.start = token.end;
    if (drag.after.manual) {
      changedWords.push(wordEntry(drag.word.line, drag.word.index + 1, drag.after));
    }
  }
  const words = page.words.filter(function (old) {
    return !changedWords.some(function (entry) {
      return sameWord(old, entry);
    });
  });
  sendWords(words.concat(changedWords));
}

// 選的那個字還原成程式算的（只對你調過的字有用）
function restoreSelectedWord() {
  const word = page.selectedWord;
  const entry = wordEntry(word.line, word.index, word.token);
  const words = page.words.filter(function (old) {
    return !sameWord(old, entry);
  });
  if (words.length === page.words.length) {
    return;   // 這個字沒調過
  }
  sendWords(words);
}

// 把整份「你調過的字」存到伺服器，換成重做好的字幕；沒修過譜的話，評分條跟著字重排
async function sendWords(words) {
  const myPage = page;
  setStatus('儲存中…');
  let result;
  try {
    if (words.length === 0) {
      result = await api.deleteWords(page.songId);
    } else {
      result = await api.saveWords(page.songId, words);
    }
  } catch (error) {
    if (page !== myPage) {
      return;
    }
    setStatus('字的時間沒存到：' + error.message);
    // 畫面上拖過的字放回伺服器現在的樣子
    try {
      const data = await api.getLyrics(page.songId);
      if (page === myPage) {
        showLyrics(data.lyrics);
      }
    } catch (again) {
      // 連不上：先留著畫面上的樣子
    }
    return;
  }
  if (page !== myPage) {
    return;
  }
  page.words = result.words;
  showLyrics(result.lyrics);
  setStatus('字的時間已儲存 ✓');
}

function showLyrics(lyrics) {
  page.selectedWord = null;
  setLyrics(lyrics);
  if (!page.hasChart && !page.dirty) {
    page.model.load(page.aiNotes);   // 用 AI 的譜：評分條跟著字的時間重排
  }
  page.ghosts = findGhosts();
  updateButtons();
}

async function resetWords() {
  if (page.words.length === 0) {
    return;
  }
  if (!confirmAction('還原字的時間？你調過的 ' + page.words.length + ' 個字會回到程式算的時間。')) {
    return;
  }
  sendWords([]);
}

// ---------- 改譜 ----------

function deleteSelected() {
  const model = page.model;
  if (model.selected === null) {
    return;
  }
  model.remember();
  model.removeSelected();
  changed();
}

function undo() {
  if (page.model.undo()) {
    changed();
  }
}

// 改過了：排好順序、更新虛線框、等一下存檔
function changed() {
  page.model.sort();
  page.ghosts = findGhosts();
  updateButtons();
  page.dirty = true;
  setStatus('儲存中…');
  if (page.saveTimer) {
    clearTimeout(page.saveTimer);
  }
  page.saveTimer = setTimeout(saveNow, SAVE_DELAY);
}

async function saveNow() {
  page.saveTimer = null;
  if (page.saving || !page.dirty) {
    return;   // 正在存的話，存完會再檢查一次
  }
  const myPage = page;
  page.saving = true;
  page.dirty = false;
  try {
    await api.saveChart(page.songId, page.model.plainNotes());
    if (page !== myPage) {
      return;
    }
    page.hasChart = true;
    setStatus('已儲存 ✓');
  } catch (error) {
    if (page !== myPage) {
      return;
    }
    page.dirty = true;
    setStatus('儲存失敗：' + error.message);
  }
  page.saving = false;
  updateButtons();
  if (page.dirty && page.saveTimer === null) {
    page.saveTimer = setTimeout(saveNow, SAVE_DELAY);   // 存的時候又改了
  }
}

async function resetToAi() {
  if (!page.hasChart && !page.dirty) {
    showToast('現在用的就是 AI 的譜');
    return;
  }
  if (!confirmAction('還原成 AI 的譜？你修的地方會全部不見。')) {
    return;
  }
  if (page.saveTimer) {
    clearTimeout(page.saveTimer);
    page.saveTimer = null;
  }
  page.dirty = false;
  try {
    await api.deleteChart(page.songId);
  } catch (error) {
    showToast('還原失敗：' + error.message, 'error');
    return;
  }
  page.hasChart = false;
  page.model.load(page.aiNotes);
  page.ghosts = findGhosts();
  setStatus('用的是 AI 的譜');
  updateButtons();
}

// AI 有聽到、但不在現在的譜裡的音（畫成虛線框）
function findGhosts() {
  const used = {};
  for (const note of page.model.notes) {
    used[noteKey(note)] = true;
  }
  const ghosts = [];
  for (const note of page.pitch.notes) {
    if (!used[noteKey(note)]) {
      ghosts.push(note);
    }
  }
  return ghosts;
}

function noteKey(note) {
  return note.s.toFixed(2) + '|' + note.e.toFixed(2) + '|' + note.p;
}

function updateButtons() {
  const model = page.model;
  document.getElementById('chart-undo').disabled = !model.canUndo();
  document.getElementById('chart-delete').disabled = model.selected === null;
  document.getElementById('chart-reset').classList.toggle('hidden', !page.hasChart && !page.dirty);
  document.getElementById('words-reset').classList.toggle('hidden', page.words.length === 0);
}
