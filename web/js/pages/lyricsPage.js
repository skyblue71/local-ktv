// 編輯歌詞頁（左邊工具、右邊預覽）：
//   網路上的歌詞：上網搜尋（LRCLIB；清單跟「加入歌曲」的是同一個：lyricsPicker.js），點一列就換
//   歌詞文字：直接編輯 LRC 文字
//   字幕時間：整首字幕提早／延後（存檔還是叫 lyrics_offset，單位毫秒）、自動對齊、AI 認音節
//   點按同步：沒有時間的歌詞，邊聽邊按空白鍵標記每一句開始的時間

import * as api from '../api.js';
import { getAudioContext } from '../audio/audioContext.js';
import { SongPlayer } from '../audio/songPlayer.js';
import { lineHtml } from '../game/lyricsView.js';
import { icon } from '../icons.js';
import { loadSettings, saveSettings } from '../settings.js';
import { confirmAction, escapeHtml, formatTime, helpTip, showToast } from '../ui.js';
import { trimStart } from '../game/trimRange.js';
import { LyricsPicker } from './lyricsPicker.js';

// 小問號裡的說明（畫面上只放標題，要看的人再點）
const FORMAT_HELP =
  '每一行前面的 [分:秒.百分秒] 是這句開始唱的時間。沒有時間的純文字也可以，之後用「點按同步」補上。\n\n' +
  '對唱：句子前面加「男：」「女：」「合：」（或 M: F: D:），字幕會換顏色，一直延續到下一個標記。' +
  '例如 [00:12.00]女：第一句\n\n' +
  '讀音標錯了：在字後面加 {正確讀音}。日文例如 私{わたし}；中文寫注音或拼音都可以，例如 還{ㄏㄨㄢˊ}，' +
  '兩個字以上用空格隔開：還是{ㄏㄞˊ ㄕˋ}。讀音的拍數也會影響填色的速度\n\n' +
  '按「儲存」會影響：字幕和評分條重做。\n' +
  '不會影響：你修過的譜、裁切。\n' +
  '句子的文字改了，你在「修譜」調過的那幾個字會回到程式算的';
const OFFSET_HELP = '整首字幕一起移。\n字幕比歌聲早出來 → 按右邊（延後）\n字幕比歌聲晚 → 按左邊（提早）\n' +
  '也可以直接打秒數，負的是提早\n\n' +
  '會影響：字幕，和跟著字走的評分條。\n不會影響：你修過的譜、裁切';
const ALIGN_HELP = '自動：程式自己把歌詞放到歌手唱的地方。歌詞檔準就照歌詞檔，不準就照 AI 聽到的。\n' +
  '照歌詞檔：完全照歌詞檔的時間，可以自己整首提早、延後。\n自動放錯的歌，改選「照歌詞檔」\n\n' +
  '換了會影響：這首歌的字幕和評分條重做。\n不會影響：你修過的譜、你調過的字、裁切。\n' +
  '「回到預設」：自動、整首移動歸零、AI 認音節打開';
const SYLLABLE_HELP = 'AI 聽出每個字、每一拍什麼時候唱，填色和評分條都照著走。\n' +
  '關掉：每一句照歌詞檔的時間，句子裡照評分條把時間分給每個字。\n\n' +
  '會影響：字幕每個字的時間、評分條在哪裡切開。\n不會影響：你修過的譜、你調過的字';
const TAP_HELP = '會播放原曲。每一句開始唱的瞬間，按一下空白鍵（或大按鈕）。\n按錯了按 Backspace 退回上一句\n\n' +
  '全部按完會存進歌詞檔（原本的時間會被換掉），字幕和評分條重做。\n' +
  '要完全照你按的時間：「歌詞時間」選「照歌詞檔」。選「自動」的話程式還會再對一次';

let song = null;
let savedLrc = '';    // 現在存著的歌詞（清單上標「✓ 已選」用）
let tapSync = null;   // 點按同步進行中的資料
let picker = null;    // 上網搜尋歌詞的清單（跟「加入歌曲」同一個）

export async function enter(app, id) {
  app.innerHTML = '<div class="page"><p class="muted">載入中…</p></div>';
  try {
    song = await api.getSong(id);
  } catch (error) {
    app.innerHTML = '<div class="page"><p>找不到這首歌。</p></div>';
    return;
  }
  const data = await api.getLyrics(id);

  app.innerHTML =
    '<div class="page">' +
    '  <a href="#/song/' + encodeURIComponent(song.id) + '" class="back-link">' + icon('back') + escapeHtml(song.title) + '</a>' +
    '  <h1>編輯歌詞</h1>' +
    '  <div class="two-columns editor-columns">' +
    '    <div>' +
    '      <section class="panel">' +
    '        <h2>' + icon('search') + ' 網路上的歌詞</h2>' +
    '        <div id="lyrics-picker"></div>' +
    '      </section>' +
    '      <section class="panel">' +
    '        <h2>' + icon('text') + ' 歌詞文字' + helpTip(FORMAT_HELP) + '</h2>' +
    '        <textarea class="input lrc-editor" id="lrc-text" spellcheck="false"></textarea>' +
    '        <div class="button-row">' +
    '          <button class="btn btn-primary" id="save-button">' + icon('save') + ' 儲存</button>' +
    '          <span class="muted small" id="save-status"></span>' +
    '        </div>' +
    '      </section>' +
    '      <section class="panel">' +
    '        <h2>' + icon('clock') + ' 字幕時間</h2>' +
    '        <div class="form-grid">' +
    '          <span>歌詞時間' + helpTip(ALIGN_HELP) + '</span>' +
    '          <div class="button-row">' +
    '            <label><input type="radio" name="align-mode" id="align-auto" value="auto"> 自動</label>' +
    '            <label><input type="radio" name="align-mode" id="align-file" value="file"> 照歌詞檔</label>' +
    '            <button class="btn btn-small btn-ghost" id="timing-reset">回到預設</button>' +
    '          </div>' +
    '          <span id="offset-label">整首移動' + helpTip(OFFSET_HELP) + '</span>' +
    '          <div class="offset-control" id="offset-row">' +
    '            <span class="offset-end">提早</span>' +
    '            <button class="btn btn-small" data-offset="-1000">1</button>' +
    '            <button class="btn btn-small" data-offset="-500">0.5</button>' +
    '            <button class="btn btn-small" data-offset="-100">0.1</button>' +
    '            <label class="offset-value"><input class="input" id="offset-input" type="number" step="0.1"' +
    ' aria-label="移動幾秒（負的是提早）"> 秒</label>' +
    '            <button class="btn btn-small" data-offset="100">0.1</button>' +
    '            <button class="btn btn-small" data-offset="500">0.5</button>' +
    '            <button class="btn btn-small" data-offset="1000">1</button>' +
    '            <span class="offset-end">延後</span>' +
    '            <button class="btn btn-small btn-ghost hidden" id="offset-zero">歸零</button>' +
    '          </div>' +
    '          <label for="syllable-ai">AI 認音節' + helpTip(SYLLABLE_HELP) + '</label>' +
    '          <div><input type="checkbox" class="switch" id="syllable-ai"></div>' +
    '        </div>' +
    '      </section>' +
    '      <section class="panel">' +
    '        <h2>' + icon('target') + ' 點按同步' + helpTip(TAP_HELP) + '</h2>' +
    '        <div id="tap-area">' +
    '          <button class="btn" id="tap-start">' + icon('play') + ' 開始</button>' +
    '        </div>' +
    '      </section>' +
    '    </div>' +
    '    <section class="panel preview-panel">' +
    '      <h2>' + icon('lyrics') + ' 預覽</h2>' +
    '      <div id="lyrics-preview" class="lyrics-preview"></div>' +
    '    </section>' +
    '  </div>' +
    '</div>';

  document.getElementById('lrc-text').value = data.lrc || '';
  savedLrc = data.lrc || '';
  showOffset(data.offset || 0);

  // 上網搜尋歌詞：按「選這個」= 馬上換成那一份（整體偏移歸零），歌手空白的話用那份歌詞上的補上
  picker = new LyricsPicker(document.getElementById('lyrics-picker'), {
    getQuery: function () {
      return { title: song.title, artist: song.artist || '', duration: song.duration };
    },
    currentLrc: function () {
      return savedLrc;
    },
    onChoose: async function (item) {
      document.getElementById('lrc-text').value = item.synced || item.plain;
      return await saveLrc('LRCLIB', true);
    },
    // 點一下就換掉：現在的歌詞不在清單裡（可能是你自己改過的）、或字幕時間有移過，先問一下
    confirmChoose: function (inList) {
      const notes = [];
      if (!inList && savedLrc.trim() !== '') {
        notes.push('現在的歌詞會被換掉（你自己改過的地方會不見）');
      }
      if ((Number(song.lyrics_offset) || 0) !== 0) {
        notes.push('字幕時間的移動會歸零');
      }
      if (notes.length === 0) {
        return true;
      }
      return confirmAction('換成這一份歌詞？\n' + notes.join('\n'));
    },
    onSongChange: function (newSong) {
      song = newSong;
    },
    beforeListen: stopTapSync,   // 兩個不要同時播
    allowNone: false,
  });
  picker.followSong(song.title, song.artist || '');
  picker.setSong(song);
  showAlignMode();
  document.getElementById('align-auto').addEventListener('change', applyAutoAlign);
  document.getElementById('align-file').addEventListener('change', applyAutoAlign);
  document.getElementById('timing-reset').addEventListener('click', resetTiming);
  const syllableAi = document.getElementById('syllable-ai');
  syllableAi.checked = song.lyrics_syllable_ai !== false;   // 沒設定過 = 打開
  syllableAi.addEventListener('change', applySyllableAi);
  renderPreview(data.lyrics);

  document.getElementById('save-button').addEventListener('click', function () {
    saveLrc('手動輸入');
  });

  const offsetButtons = document.querySelectorAll('[data-offset]');
  for (const button of offsetButtons) {
    button.title = offsetButtonTitle(Number(button.dataset.offset));
    button.addEventListener('click', function () {
      // 用毫秒整數加減，才不會出現 0.30000000000000004 這種數字
      showOffset(readOffset() + Number(button.dataset.offset));
      applyOffset();
    });
  }
  // 自己打數字：按 Enter 或離開格子就套用（不用另外按鈕）
  document.getElementById('offset-input').addEventListener('change', function () {
    showOffset(readOffset());
    applyOffset();
  });
  document.getElementById('offset-zero').addEventListener('click', function () {
    showOffset(0);
    applyOffset();
  });
  document.getElementById('tap-start').addEventListener('click', startTapSync);
  document.addEventListener('keydown', onKeyDown);
}

export function leave() {
  document.removeEventListener('keydown', onKeyDown);
  stopTapSync();
  if (picker) {
    picker.destroy();
    picker = null;
  }
  song = null;
}

// ---------- 儲存 ----------

// resetOffset：換成搜尋到的另一份歌詞時傳 true，整體偏移歸零（舊的偏移是給舊歌詞用的）
// 存好回傳 true，失敗回傳 false
async function saveLrc(source, resetOffset) {
  const status = document.getElementById('save-status');
  status.textContent = '儲存中…';
  try {
    const text = document.getElementById('lrc-text').value;
    const result = await api.saveLyrics(song.id, text, source, resetOffset);
    status.textContent = '已儲存 ✓';
    // 歌詞換了：搜尋清單上的「✓ 已選」、「你現在的歌詞」那一行跟著換
    savedLrc = text;
    if (picker) {
      picker.updateChosen();
    }
    if (resetOffset === true && (Number(song.lyrics_offset) || 0) !== 0) {
      song.lyrics_offset = 0;
      showOffset(0);
      status.textContent = '已儲存 ✓（字幕時間的移動歸零）';
    }
    renderPreview(result.lyrics);
    return true;
  } catch (error) {
    status.textContent = '儲存失敗：' + error.message;
    return false;
  }
}

// 整體時間偏移：畫面上用「秒」，存檔用「毫秒」（lyrics_offset）
function readOffset() {
  return Math.round(Number(document.getElementById('offset-input').value || 0) * 1000);
}

function showOffset(milliseconds) {
  document.getElementById('offset-input').value = milliseconds / 1000;
  document.getElementById('offset-zero').classList.toggle('hidden', milliseconds === 0);
}

// 例如「延後 17.5 秒」「提早 0.3 秒」「不移動」
function offsetText(milliseconds) {
  if (milliseconds > 0) {
    return '字幕延後 ' + (milliseconds / 1000) + ' 秒';
  }
  if (milliseconds < 0) {
    return '字幕提早 ' + (-milliseconds / 1000) + ' 秒';
  }
  return '字幕不移動';
}

// 移動按鈕滑鼠移上去的說明，例如「提早 0.5 秒」
function offsetButtonTitle(milliseconds) {
  if (milliseconds < 0) {
    return '提早 ' + (-milliseconds / 1000) + ' 秒';
  }
  return '延後 ' + (milliseconds / 1000) + ' 秒';
}

// 連按好幾下時，一次存完再存下一次（同時送出的話，最後存到的可能不是最後按的數字）
let offsetSaving = Promise.resolve();

function applyOffset() {
  offsetSaving = offsetSaving.then(saveOffset);
  return offsetSaving;
}

async function saveOffset() {
  const value = readOffset();   // 輪到這次存的時候才讀，所以一定是最新的數字
  if (value === (Number(song.lyrics_offset) || 0)) {
    return;   // 跟已經存的一樣：不用再存
  }
  try {
    // 記住新的偏移：點按同步換算時間要用
    song = await api.updateSong(song.id, { lyrics_offset: value });
    const data = await api.getLyrics(song.id);
    renderPreview(data.lyrics);
    showToast(offsetText(value), 'ok');
  } catch (error) {
    showToast('設定失敗：' + error.message, 'error');
  }
}

// 歌詞時間用哪一種：自動（沒設定過 = 自動）還是照歌詞檔
function isAutoAlign() {
  return song.lyrics_auto_align !== false;
}

// 照現在的設定顯示：選項打勾；「整首移動」只有「照歌詞檔」才看得到（自動的時候移了也沒用）
function showAlignMode() {
  const auto = isAutoAlign();
  document.getElementById('align-auto').checked = auto;
  document.getElementById('align-file').checked = !auto;
  document.getElementById('offset-label').classList.toggle('hidden', auto);
  document.getElementById('offset-row').classList.toggle('hidden', auto);
}

async function applyAutoAlign() {
  const auto = document.getElementById('align-auto').checked;
  try {
    song = await api.updateSong(song.id, { lyrics_auto_align: auto });
    showAlignMode();
    const data = await api.getLyrics(song.id);
    renderPreview(data.lyrics);
    showToast(auto ? '歌詞時間：自動' : '歌詞時間：照歌詞檔', 'ok');
  } catch (error) {
    showToast('設定失敗：' + error.message, 'error');
  }
}

// 回到預設：自動、整首移動歸零、AI 認音節打開
async function resetTiming() {
  try {
    song = await api.updateSong(song.id, { lyrics_auto_align: true, lyrics_offset: 0, lyrics_syllable_ai: true });
    showAlignMode();
    showOffset(0);
    document.getElementById('syllable-ai').checked = true;
    const data = await api.getLyrics(song.id);
    renderPreview(data.lyrics);
    showToast('字幕時間回到預設', 'ok');
  } catch (error) {
    showToast('設定失敗：' + error.message, 'error');
  }
}

// AI 認音節（每個字、每一拍的填色時間用 MMS）：關掉 = 照音符平均分
async function applySyllableAi() {
  const checked = document.getElementById('syllable-ai').checked;
  try {
    song = await api.updateSong(song.id, { lyrics_syllable_ai: checked });
    const data = await api.getLyrics(song.id);
    renderPreview(data.lyrics);
    let message = '已關掉 AI 認音節（照音符平均分）';
    if (checked) {
      message = '已打開 AI 認音節';
    }
    showToast(message, 'ok');
  } catch (error) {
    showToast('設定失敗：' + error.message, 'error');
  }
}

function renderPreview(lyrics) {
  const box = document.getElementById('lyrics-preview');
  if (!box) {
    return;
  }
  if (!lyrics || lyrics.lines.length === 0) {
    box.innerHTML = '<p class="muted">還沒有歌詞。</p>';
    return;
  }
  const settings = loadSettings();
  let html = '';
  if (!lyrics.synced) {
    html += '<div class="notice">沒有時間軸' + helpTip('唱歌時不會有字幕，請用「點按同步」') + '</div>';
  }
  // 自動對齊發現整首歌詞固定早／晚，已經自動移過
  const shift = Number(lyrics.auto_shift) || 0;
  if (Math.abs(shift) >= 0.1) {
    let direction = '延後';
    let reason = '偏早';
    if (shift < 0) {
      direction = '提早';
      reason = '偏晚';
    }
    html += '<div class="notice small">程式已自動把字幕' + direction + ' ' + Math.abs(shift).toFixed(2) + ' 秒' +
      helpTip('這份歌詞的時間整首' + reason + '，程式照歌聲自動移過了。\n不對的話，把「歌詞時間」改成「照歌詞檔」，再用「整首移動」調整') +
      '</div>';
  }
  // 一段一段對齊：中間插了劇情、影片剪短 → 整段搬到歌手唱的地方（server\song_alignment.py）
  const moved = lyrics.moved_sections || [];
  if (moved.length > 0) {
    const parts = [];
    for (const section of moved) {
      parts.push(formatTime(section.from) + ' 起的 ' + section.lines + ' 句 → ' + formatTime(section.to));
    }
    html += '<div class="notice small">有 ' + moved.length + ' 段歌詞搬到歌手唱的地方' +
      helpTip('這支影片跟歌詞的版本不一樣（中間有劇情、或剪短了），程式照歌聲搬過去：\n' + parts.join('\n')) +
      '</div>';
  }
  const absent = lyrics.absent_lines || [];
  if (absent.length > 0) {
    html += '<div class="notice small">影片沒唱的 ' + absent.length + ' 句不顯示' +
      helpTip('這幾句在這支影片裡找不到有人唱：\n' + absent.join('\n')) +
      '</div>';
  }
  for (const line of lyrics.lines) {
    let time = '';
    if (line.start !== undefined) {
      time = '<span class="line-time">' + formatTime(line.start) + '</span>';
    }
    html += '<div class="preview-line">' + time + '<div class="preview-text">' +
      lineHtml(line, settings) + '</div></div>';
  }
  box.innerHTML = html;
}

// ---------- 點按同步 ----------

// 從 LRC 文字裡拿出每一句（去掉原本的時間）
function getPlainLines() {
  const text = document.getElementById('lrc-text').value;
  const lines = [];
  for (let line of text.split('\n')) {
    line = line.replace(/\[\d+:\d+(\.\d+)?\]/g, '').replace(/<\d+:\d+(\.\d+)?>/g, '').trim();
    if (line === '' || /^\[[a-zA-Z]+:.*\]$/.test(line)) {
      continue;
    }
    lines.push(line);
  }
  return lines;
}

function secondsToLrcTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  let minuteText = String(minutes);
  if (minutes < 10) {
    minuteText = '0' + minuteText;
  }
  let secondText = rest.toFixed(2);
  if (rest < 10) {
    secondText = '0' + secondText;
  }
  return '[' + minuteText + ':' + secondText + ']';
}

async function startTapSync() {
  const lines = getPlainLines();
  if (lines.length === 0) {
    showToast('請先在上面貼上歌詞（每句一行）', 'error');
    return;
  }
  const area = document.getElementById('tap-area');
  area.innerHTML = '<p class="muted">載入音樂中…</p>';
  picker.stopListen();   // 兩個不要同時播

  const context = getAudioContext();
  await context.resume();
  const player = new SongPlayer(context);
  let vocalsUrl = null;
  if (song.has_vocals) {
    vocalsUrl = api.audioUrl(song.id, 'vocals');
  }
  await player.load(api.audioUrl(song.id, 'instrumental'), vocalsUrl);
  player.setGuideVolume(100);  // 要聽得到原唱才知道什麼時候開始唱
  const settings = loadSettings();
  player.setMasterVolume(settings.masterVolume);

  // 歌詞檔裡的時間 = 播放的時間 - 整體偏移
  //（這樣按出來的時間存進歌詞檔後，字幕才會剛好在你按的地方；裁切跟歌詞時間無關）
  //「自動」的時候整體偏移沒有在用，當 0
  let shift = 0;
  if (!isAutoAlign()) {
    shift = (Number(song.lyrics_offset) || 0) / 1000;
  }
  player.seek(trimStart(song));   // 有裁切的話，從裁切的開頭開始播

  tapSync = { player: player, lines: lines, times: [], shift: shift };
  area.innerHTML =
    '<div class="tap-box">' +
    '  <div class="tap-time" id="tap-time">0:00</div>' +
    '  <div class="tap-next muted small">下一句：</div>' +
    '  <div class="tap-line" id="tap-line"></div>' +
    '  <div class="tap-after muted" id="tap-after"></div>' +
    '  <button class="btn btn-primary btn-big" id="tap-button">這一句開始 <kbd>空白鍵</kbd></button>' +
    '  <div class="button-row tap-tools">' +
    '    <button class="btn btn-small" id="tap-undo" title="退回上一句（Backspace）">' + icon('undo') + ' 退回</button>' +
    '    <button class="btn btn-small" id="tap-stop">' + icon('stop') + ' 停止</button>' +
    '    <label class="control-slider" title="音量">' + icon('volume') +
    '<input type="range" min="0" max="100" id="tap-volume" aria-label="音量"></label>' +
    '  </div>' +
    '</div>';
  const volume = document.getElementById('tap-volume');
  volume.value = settings.masterVolume;
  volume.addEventListener('input', function () {
    player.setMasterVolume(Number(volume.value));
    settings.masterVolume = Number(volume.value);
    saveSettings(settings);
  });
  document.getElementById('tap-button').addEventListener('click', tapNow);
  document.getElementById('tap-undo').addEventListener('click', tapUndo);
  document.getElementById('tap-stop').addEventListener('click', function () {
    finishTapSync(false);
  });

  player.play();
  updateTapDisplay();
  tapSync.timer = setInterval(function () {
    const label = document.getElementById('tap-time');
    if (label && tapSync) {
      label.textContent = formatTime(tapSync.player.getTime());
    }
  }, 200);
}

function updateTapDisplay() {
  if (!tapSync) {
    return;
  }
  const index = tapSync.times.length;
  document.getElementById('tap-line').textContent = tapSync.lines[index] || '（全部完成）';
  document.getElementById('tap-after').textContent = tapSync.lines[index + 1] || '';
}

function tapNow() {
  if (!tapSync) {
    return;
  }
  tapSync.times.push(tapSync.player.getTime());
  if (tapSync.times.length >= tapSync.lines.length) {
    finishTapSync(true);
    return;
  }
  updateTapDisplay();
}

function tapUndo() {
  if (!tapSync || tapSync.times.length === 0) {
    return;
  }
  tapSync.times.pop();
  // 退回到「再上一句」開始前 1 秒，重新聽一次
  let back = trimStart(song);
  if (tapSync.times.length > 0) {
    back = tapSync.times[tapSync.times.length - 1];
  }
  tapSync.player.seek(Math.max(trimStart(song), back - 1));
  updateTapDisplay();
}

function finishTapSync(completed) {
  if (!tapSync) {
    return;
  }
  const lrcLines = [];
  for (let i = 0; i < tapSync.lines.length; i++) {
    if (i < tapSync.times.length) {
      lrcLines.push(secondsToLrcTime(Math.max(0, tapSync.times[i] - tapSync.shift)) + tapSync.lines[i]);
    } else {
      lrcLines.push(tapSync.lines[i]);
    }
  }
  const tappedCount = tapSync.times.length;
  stopTapSync();

  const area = document.getElementById('tap-area');
  area.innerHTML = '<button class="btn" id="tap-start">' + icon('refresh') + ' 重新來一次</button>';
  document.getElementById('tap-start').addEventListener('click', startTapSync);

  if (tappedCount > 0) {
    document.getElementById('lrc-text').value = lrcLines.join('\n');
    if (completed) {
      saveLrc('點按同步');
      showToast('同步完成，已儲存！', 'ok');
    } else {
      showToast('已標記 ' + tappedCount + ' 句（還沒儲存，確認後按「儲存」）');
    }
  }
}

function stopTapSync() {
  if (tapSync) {
    clearInterval(tapSync.timer);
    tapSync.player.destroy();
    tapSync = null;
  }
}

function onKeyDown(event) {
  if (!tapSync) {
    return;
  }
  if (event.code === 'Space') {
    event.preventDefault();
    tapNow();
  } else if (event.code === 'Backspace') {
    event.preventDefault();
    tapUndo();
  }
}
