// 唱歌畫面（最重要的一頁）
//
// 流程：
//   載入歌曲資料和音訊 → 按「開始」→ 開啟麥克風 → 倒數 → 播放
//   → 每 10 毫秒收到你的音高，交給評分器 → 每個畫面更新音高圖和字幕
//   → 歌曲結束 → 算總分 → 顯示結果
//
// 「測試模式」(?test=1)：不用麥克風，把原唱人聲送進音高偵測，用來確認評分系統正常。
//
// 未來共唱：page.singers 是一個陣列，現在只有一位歌手。
//          多一個人就多放一個 { microphone, scorer, color } 進去。

import * as api from '../api.js';
import { getAudioContext, getOutputLatency } from '../audio/audioContext.js';
import { Microphone } from '../audio/microphone.js';
import { MusicSpectrum } from '../audio/musicSpectrum.js';
import { Recorder } from '../audio/recorder.js';
import { SongPlayer } from '../audio/songPlayer.js';
import { calculateFinalScore } from '../game/finalScore.js';
import { LyricsView } from '../game/lyricsView.js';
import { MvBackground } from '../game/mvBackground.js';
import { frequencyToMidi } from '../game/noteNames.js';
import { PitchView } from '../game/pitchView.js';
import { Scorer } from '../game/scorer.js';
import { endLinesAtLastBar } from '../game/lineEnds.js';
import { notesInLyrics } from '../game/lyricNotes.js';
import { applyQuietSetting } from '../game/quietParts.js';
import { splitAtSyllables } from '../game/syllableBars.js';
import { addTalkBars } from '../game/talkBars.js';
import { fillMissed } from '../game/twoEars.js';
import { lyricsInRange, notesInRange, trimEnd, trimStart } from '../game/trimRange.js';
import { t } from '../i18n.js';
import { icon } from '../icons.js';
import { loadSettings, saveSettings } from '../settings.js';
import { escapeHtml, formatTime, helpTip } from '../ui.js';
import { showResult } from './resultView.js';
import { openSettingsDialog } from './settingsDialog.js';

const SINGER_COLORS = ['#4ff0ff', '#ff7ad9'];  // 第一位、第二位歌手的顏色
const PLAY_LABEL = icon('play') + ' ' + t('繼續');     // 暫停中，按了會繼續
const PAUSE_LABEL = icon('pause') + ' ' + t('暫停');   // 播放中，按了會暫停

let page = null;  // 這一頁用到的東西都放這裡，離開時一起清掉

export async function enter(app, songId, query) {
  document.body.classList.add('singing');
  page = {
    songId: songId,
    testMode: query.test === '1',
    settings: loadSettings(),
    song: null,
    pitch: null,
    player: null,
    singers: [],
    pitchView: null,
    spectrum: null,
    lyricsView: null,
    recorder: null,
    recordingUrl: null,
    mv: null,
    animation: 0,
    started: false,
    finished: false,
    seeked: false,
  };
  const myPage = page;

  app.innerHTML = pageHtml(songId);
  setOverlay('<div class="loading-text" id="loading-text">' + t('載入歌曲中…') + '</div>');

  try {
    // 你修過的譜（讀不到的話，當作沒修過）
    const chartRequest = api.getChart(songId).catch(function () {
      return { notes: null };
    });
    const results = await Promise.all([api.getSong(songId), api.getPitch(songId), api.getLyrics(songId), chartRequest]);
    if (page !== myPage) {
      return;  // 載入途中已經離開這一頁
    }
    page.song = results[0];
    page.pitch = results[1];
    const lyricsData = results[2];
    const chart = results[3];
    // 照設定清掉小聲雜音：句尾的（評分條、字幕填色都用清過的）、句子裡面小聲的那一段（只影響評分條）
    lyricsData.lyrics = applyQuietSetting(lyricsData.lyrics, page.settings.quietDb, page.pitch);

    if (page.testMode && !page.song.has_vocals) {
      throw new Error(t('這首歌沒有分離出人聲，不能用測試模式。'));
    }

    document.getElementById('sing-title').textContent = page.song.title;
    document.getElementById('sing-artist').textContent = page.song.artist || '';
    if (page.song.has_cover) {
      document.getElementById('sing-bg').style.backgroundImage = 'url(' + api.coverUrl(songId, page.song.cover_version) + ')';
    }
    // 有影片的歌：背景播 MV
    if (page.song.has_video && page.settings.showMV) {
      page.mv = new MvBackground(document.getElementById('sing-video'), api.videoUrl(songId),
        page.settings.mvBrightness);
    }
    if (page.testMode) {
      document.getElementById('test-badge').classList.remove('hidden');
    }

    // 下載音訊
    const context = getAudioContext();
    page.player = new SongPlayer(context);
    let vocalsUrl = null;
    if (page.song.has_vocals) {
      vocalsUrl = api.audioUrl(songId, 'vocals');
    }
    await page.player.load(api.audioUrl(songId, 'instrumental'), vocalsUrl, function (ratio) {
      const text = document.getElementById('loading-text');
      if (text) {
        text.textContent = t('載入音樂中… {percent}%', { percent: Math.round(ratio * 100) });
      }
    });
    if (page !== myPage) {
      myPage.player.destroy();  // 載入途中離開了：把這次載入的播放器關掉
      return;
    }
    page.player.setMasterVolume(page.settings.masterVolume);
    page.player.setMusicVolume(page.settings.musicVolume);
    // 測試模式預設聽得到原唱，比較好確認線有沒有跟上（下面的導唱按鈕、滑桿一樣可以調）
    page.player.setGuideVolume(page.testMode ? 100 : page.settings.guideVolume);
    page.player.onEnded = finish;

    // 裁切：只唱 trimStart ～ trimEnd 這一段（MV 前面的劇情、後面的片尾不唱）
    page.trimStart = trimStart(page.song);
    page.trimEnd = trimEnd(page.song, page.player.getDuration());
    page.player.seek(page.trimStart);

    // 要唱的音符：
    //   你修過譜（修譜頁）→ 用你修的譜，你畫的就算
    //   沒修過 → AI 的譜：
    //     1. 只有字在唱的時候（前奏、間奏、MV 劇情都不算），跟字幕同一個時間 → lyricNotes.js
    //     2. 原唱自己都聽不太到的音（殘留的和聲）評分器會拿掉 → scorer.js 的 UNHEARD_LIMIT
    //     3. 評分條照字切開，一個字（一拍）一條 → syllableBars.js
    //   都只算裁切範圍內的
    //     0. AI 唱到一半漏掉、瀏覽器的耳朵聽得到的地方先補上 → twoEars.js
    const filled = fillMissed(page.pitch.notes, page.pitch, lyricsData.lyrics, page.settings.quietDb);
    let sung = splitAtSyllables(notesInLyrics(filled, lyricsData.lyrics), lyricsData.lyrics);
    //     4. 講話、rap 的地方（有字、有人聲、量不到音高）補上只看有沒有出聲的評分條 → talkBars.js
    if (page.settings.talkBars) {
      sung = addTalkBars(sung, page.pitch, lyricsData.lyrics);
    }
    //     5. 一句最後一條評分條結束了，這一句就算唱完，字幕不再繼續填 → lineEnds.js
    let shownLyrics = endLinesAtLastBar(lyricsData.lyrics, sung, page.pitch.heard);
    if (chart.notes) {
      sung = chart.notes;
      shownLyrics = lyricsData.lyrics;
    }
    page.notes = notesInRange(sung, page.trimStart, page.trimEnd);

    // 畫面
    page.pitchView = new PitchView(document.getElementById('pitch-canvas'), page.pitch);
    // 音高圖最下面那排跟著音樂跳的柱子（只是好看：在旁邊聽音樂，不會改到聲音）
    page.spectrum = new MusicSpectrum(context, page.player.master);
    const lyrics = lyricsInRange(shownLyrics, page.trimStart, page.trimEnd);
    page.lyricsView = new LyricsView(document.getElementById('lyrics-area'), lyrics, page.settings);
    page.singers = [{
      name: page.settings.playerName,
      microphone: null,
      scorer: new Scorer(page.notes, page.settings, page.pitch.contour, page.pitch.heard),
      color: SINGER_COLORS[0],
    }];

    setupControls();
    showStartScreen();
    loop();
  } catch (error) {
    setOverlay(
      '<div class="overlay-message">' +
      '  <h2>' + t('無法開始') + '</h2><p>' + escapeHtml(error.message) + '</p>' +
      '  <a class="btn" href="#/song/' + encodeURIComponent(songId) + '">' + t('返回') + '</a>' +
      '</div>');
  }
}

export function leave() {
  document.body.classList.remove('singing');
  if (!page) {
    return;
  }
  cancelAnimationFrame(page.animation);
  document.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('resize', onResize);
  if (page.spectrum) {
    page.spectrum.destroy();
  }
  if (page.player) {
    page.player.destroy();
  }
  if (page.mv) {
    page.mv.destroy();
  }
  for (const singer of page.singers) {
    if (singer.microphone) {
      singer.microphone.stop();
    }
  }
  if (page.recorder) {
    page.recorder.stop();
  }
  if (page.recordingUrl) {
    URL.revokeObjectURL(page.recordingUrl);
  }
  page = null;
}

// ---------- 畫面 ----------

function pageHtml(songId) {
  return (
    '<div class="sing-page">' +
    '  <div class="sing-background" id="sing-bg"></div>' +
    '  <video class="sing-video hidden" id="sing-video" muted playsinline preload="auto"></video>' +
    '  <div class="sing-top">' +
    '    <a class="btn btn-ghost" href="#/song/' + encodeURIComponent(songId) + '">' + icon('close') + ' ' + t('離開') + '</a>' +
    '    <div class="sing-title">' +
    '      <div class="sing-song-title" id="sing-title"></div>' +
    '      <div class="sing-song-artist" id="sing-artist"></div>' +
    '    </div>' +
    '    <div class="sing-hud">' +
    '      <div class="hud-item"><div class="hud-label">COMBO</div><div class="hud-value" id="combo-value">0</div></div>' +
    '      <div class="hud-item"><div class="hud-label">' + t('得分') + '</div><div class="hud-value hud-score" id="score-value">0.0</div></div>' +
    '    </div>' +
    '    <button class="btn btn-ghost" id="sing-settings" title="' + t('設定（會先暫停）') + '">' + icon('settings') + ' ' + t('設定') + '</button>' +
    '  </div>' +
    '  <div class="pitch-area">' +
    '    <canvas id="pitch-canvas"></canvas>' +
    '    <div class="test-badge hidden" id="test-badge" title="' + t('原唱人聲自動唱') + '">' + icon('flask') + ' ' + t('測試模式') + '</div>' +
    '  </div>' +
    '  <div class="lyrics-area" id="lyrics-area"></div>' +
    '  <div class="sing-controls">' +
    '    <button class="btn" id="play-button">' + PAUSE_LABEL + '</button>' +
    '    <button class="btn btn-ghost" id="restart-button">' + icon('refresh') + ' ' + t('重來') + '</button>' +
    '    <button class="btn btn-primary hidden" id="skip-intro">' + icon('skip') + ' ' + t('跳過前奏') + '</button>' +
    '    <span class="time-label" id="time-label">0:00 / 0:00</span>' +
    '    <div class="seek-bar" id="seek-bar"><div class="seek-fill" id="seek-fill"></div></div>' +
    '    <div class="control-slider" id="guide-control">' +
    '      <button class="btn btn-small guide-toggle" id="guide-toggle" title="' + t('快速鍵：G') + '">' + t('導唱：關') + '</button>' +
    '      <input type="range" min="0" max="100" id="guide-slider" title="' + t('導唱音量') + '">' +
    '    </div>' +
    '    <label class="control-slider">' + t('伴奏') + ' <input type="range" min="0" max="100" id="music-slider"></label>' +
    '    <label class="control-slider" title="' + t('總音量') + '">' + icon('volume') + ' <input type="range" min="0" max="100" id="master-slider" aria-label="' + t('總音量') + '"></label>' +
    '    <div class="mic-meter" title="' + t('麥克風音量') + '"><div class="mic-meter-fill" id="mic-meter"></div></div>' +
    '    <button class="btn btn-primary" id="finish-button">' + t('結束評分') + '</button>' +
    '  </div>' +
    '  <div class="sing-overlay" id="sing-overlay"><div class="overlay-box" id="overlay-box"></div></div>' +
    '</div>'
  );
}

function setOverlay(html) {
  const overlay = document.getElementById('sing-overlay');
  if (!overlay) {
    return;
  }
  overlay.classList.remove('hidden');
  document.getElementById('overlay-box').innerHTML = html;
}

function hideOverlay() {
  const overlay = document.getElementById('sing-overlay');
  if (overlay) {
    overlay.classList.add('hidden');
  }
}

// 有裁切的話，開始畫面寫出唱哪一段，例如「 · 只唱 0:54 ～ 4:45」
function trimText() {
  if (page.trimStart <= 0 && page.trimEnd >= page.player.getDuration()) {
    return '';
  }
  return t(' · 只唱 {start} ～ {end}', { start: formatTime(page.trimStart), end: formatTime(page.trimEnd) });
}

// 開始畫面：只放歌名、按鍵提示，詳細說明收在小問號裡
function showStartScreen() {
  let hint = '<kbd>' + t('空白鍵') + '</kbd> ' + t('暫停');
  if (page.player.hasVocals()) {
    hint += '<kbd>G</kbd> ' + t('導唱');
  }
  let help = t('建議戴耳機唱，伴奏才不會被麥克風收進去，評分比較準。\n') +
    t('男生唱女生的歌（或相反）也沒關係，高八度、低八度都算對。\n') +
    t('← → 鍵：倒退、快轉 5 秒');
  if (page.testMode) {
    hint = icon('flask') + ' ' + t('測試模式');
    help = t('不開麥克風，讓原唱人聲自己唱。\n分數應該很高（90 分以上），用來確認評分系統正常。');
  }
  let artist = '';
  if (page.song.artist) {
    artist = escapeHtml(page.song.artist) + ' · ';
  }
  // 封面做成一張慢慢轉的唱片（沒有封面就放一個音符；只是好看）
  let disc = '<div class="start-disc">' + icon('music') + '</div>';
  if (page.song.has_cover) {
    disc = '<div class="start-disc" style="background-image:url(' +
      api.coverUrl(page.songId, page.song.cover_version) + ')"></div>';
  }
  setOverlay(
    '<div class="overlay-message start-screen">' + disc +
    '  <h2>' + escapeHtml(page.song.title) + '</h2>' +
    '  <p class="muted">' + artist + formatTime(page.trimEnd - page.trimStart) + trimText() + '</p>' +
    '  <p class="muted small start-hint">' + hint + helpTip(help) + '</p>' +
    '  <div class="button-row">' +
    '    <button class="btn btn-primary btn-big start-button" id="start-button">' + icon('mic') + ' ' + t('開始') + '</button>' +
    '    <button class="btn btn-ghost" id="start-settings">' + icon('settings') + ' ' + t('設定') + '</button>' +
    '    <a class="btn btn-ghost" id="start-back" href="#/song/' + encodeURIComponent(page.songId) + '">' +
    icon('back') + ' ' + t('返回') + '</a>' +
    '  </div>' +
    '</div>');
  document.getElementById('start-button').addEventListener('click', startSinging);
  document.getElementById('start-settings').addEventListener('click', openSingSettings);
}

// ---------- 開始唱 ----------

async function startSinging() {
  const myPage = page;
  const context = getAudioContext();
  await context.resume();
  setOverlay('<div class="loading-text">' + t('開啟麥克風中…') + '</div>');

  const singer = page.singers[0];
  const microphone = new Microphone(context);
  try {
    if (page.testMode) {
      await microphone.startSimulation(page.player.vocalTap);
    } else {
      await microphone.start(page.settings.micId, page.settings.echoCancel);
    }
  } catch (error) {
    let extra = '';
    if (page.song.has_vocals) {
      extra = '<a class="btn" href="#/sing/' + encodeURIComponent(page.songId) + '?test=1">' + t('改用測試模式') + '</a>';
    }
    setOverlay(
      '<div class="overlay-message">' +
      '  <h2>' + t('無法使用麥克風') + '</h2>' +
      '  <p>' + escapeHtml(error.message) + '</p>' +
      '  <p class="muted">' + t('請確認有接麥克風') +
      helpTip(t('瀏覽器擋住的話：按網址列左邊的圖示，允許使用麥克風')) + '</p>' +
      '  <div class="button-row"><button class="btn btn-primary" id="retry-mic">' + t('再試一次') + '</button>' + extra + '</div>' +
      '</div>');
    document.getElementById('retry-mic').addEventListener('click', startSinging);
    return;
  }
  if (page !== myPage) {
    microphone.stop();
    return;
  }

  microphone.setGate(page.settings.micGate);
  microphone.setMonitor(page.settings.monitor, page.settings.monitorVolume, page.settings.reverb);
  microphone.onPitch = function (frame) {
    onPitchFrame(singer, frame);
  };
  singer.microphone = microphone;

  createRecorder();

  await countdown();
  if (page !== myPage) {
    return;
  }
  hideOverlay();
  page.started = true;
  page.player.play();
  if (page.recorder) {
    page.recorder.start();
  }
}

// 錄音：伴奏 + 你的聲音（測試模式不錄）
function createRecorder() {
  page.recorder = null;
  if (!page.settings.record || page.testMode) {
    return;
  }
  const microphone = page.singers[0].microphone;
  page.recorder = new Recorder(getAudioContext());
  page.recorder.addInput(page.player.master);
  page.recorder.addInput(microphone.getVoiceOutput());
}

// 開始前的 3、2、1 倒數（設定裡可以關掉）
// 倒數時可以按大大的「跳過」，或按空白鍵、Enter
// 畫面只畫一次、每秒只換數字（每一秒整個重畫的話，按鈕也會跟著換掉，剛好在換的時候按會按不到）
function countdown() {
  return new Promise(function (resolve) {
    if (!page.settings.countdown) {
      resolve();
      return;
    }
    let number = 3;
    let finished = false;
    let timer = 0;

    function done() {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timer);
      document.removeEventListener('keydown', onCountdownKey);
      resolve();
    }

    function onCountdownKey(event) {
      if (event.code === 'Space' || event.code === 'Enter') {
        event.preventDefault();
        done();
      }
    }

    function tick() {
      const element = document.getElementById('countdown-number');
      if (!page || number === 0 || !element) {
        done();
        return;
      }
      element.textContent = number;
      element.classList.remove('pop');
      void element.offsetWidth;   // 讓跳出來的動畫重新播放
      element.classList.add('pop');
      number--;
      timer = setTimeout(tick, 700);
    }

    setOverlay(
      '<div class="countdown-area">' +
      '  <div class="countdown-number" id="countdown-number"></div>' +
      '  <button class="btn btn-big skip-countdown" id="skip-countdown">' + t('跳過') + ' ' + icon('skip') + '<kbd>' + t('空白鍵') + '</kbd></button>' +
      '</div>');
    document.getElementById('skip-countdown').addEventListener('click', done);
    document.addEventListener('keydown', onCountdownKey);
    tick();
  });
}

// ---------- 收到音高 ----------

function onPitchFrame(singer, frame) {
  if (!page || !page.player.playing) {
    return;
  }
  // 延遲補償：你聽到的聲音比實際晚（喇叭延遲），你的聲音進電腦也會晚（麥克風延遲）
  let latency = 0;
  if (!page.testMode) {
    latency = getOutputLatency() + singer.microphone.inputLatency + page.settings.latencyMs / 1000;
  }
  const songTime = page.player.contextTimeToSongTime(frame.time) - latency;

  let midi = null;
  if (frame.freq > 0) {
    midi = frequencyToMidi(frame.freq) - page.pitch.tuning;
  }
  singer.scorer.addPitch(songTime, midi, frame.rms);
}

// ---------- 每個畫面 ----------

function loop() {
  if (!page) {
    return;
  }
  page.animation = requestAnimationFrame(loop);

  let now = page.player.getTime();
  if (page.player.playing && !page.testMode) {
    now -= getOutputLatency();  // 畫面配合「你聽到的」時間
  }

  const judgeDelay = 0.15 + Math.max(0, page.settings.latencyMs / 1000);
  for (const singer of page.singers) {
    singer.scorer.update(now - judgeDelay);
  }

  // 音樂跳動柱：設定關掉就不給資料（不給就不畫）
  if (page.settings.showSpectrum) {
    page.pitchView.setSpectrum(page.spectrum.read());
  } else {
    page.pitchView.setSpectrum(null);
  }
  page.pitchView.draw(now, page.singers);
  page.lyricsView.update(now);
  if (page.mv) {
    page.mv.sync(now, page.player.playing);
  }
  updateHud(now);
  updateSkipButton(now);

  // 裁切的結尾到了：結束評分（沒裁結尾的話，歌曲播完時 onEnded 會結束）
  if (page.started && !page.finished && page.player.playing && page.player.getTime() >= page.trimEnd) {
    finish();
  }
}

function updateHud(now) {
  const scorer = page.singers[0].scorer;
  document.getElementById('score-value').textContent = scorer.liveScore().toFixed(1);
  const combo = document.getElementById('combo-value');
  combo.textContent = scorer.combo;
  combo.classList.toggle('combo-hot', scorer.combo >= 10);

  // 時間：一律顯示原影片的時間（跟歌詞檔、編輯歌詞、YouTube 上的時間一樣，有裁切也不會對不起來）
  //（從裁切點算 0:00 的話，畫面上的時間會比歌詞的時間少一截，看起來像字幕提早跑）
  // 進度條：只顯示要唱的那一段（裁切範圍）
  const length = page.trimEnd - page.trimStart;
  const passed = Math.max(0, Math.min(length, now - page.trimStart));
  document.getElementById('time-label').textContent = formatTime(Math.max(0, now)) + ' / ' +
    formatTime(page.player.getDuration());
  document.getElementById('seek-fill').style.width = (passed / length * 100) + '%';

  const microphone = page.singers[0].microphone;
  let percent = 0;
  if (microphone && microphone.level > 0) {
    const db = 20 * Math.log10(microphone.level);
    percent = Math.max(0, Math.min(100, (db + 60) / 60 * 100));
  }
  document.getElementById('mic-meter').style.width = percent + '%';
}

// ---------- 控制按鈕 ----------

function setupControls() {
  document.getElementById('play-button').addEventListener('click', togglePause);
  document.getElementById('restart-button').addEventListener('click', restart);
  document.getElementById('skip-intro').addEventListener('click', skipToNextNote);
  document.getElementById('finish-button').addEventListener('click', finish);
  document.getElementById('sing-settings').addEventListener('click', openSingSettings);

  // 導唱：按鈕（或 G 鍵）隨時開關，滑桿調音量（測試模式也可以調）
  if (page.player.hasVocals()) {
    const guideSlider = document.getElementById('guide-slider');
    guideSlider.addEventListener('input', function () {
      setGuideVolume(Number(guideSlider.value));
    });
    document.getElementById('guide-toggle').addEventListener('click', toggleGuide);
    if (page.testMode) {
      setGuideVolume(100);
    } else {
      setGuideVolume(page.settings.guideVolume);
    }
  } else {
    document.getElementById('guide-control').classList.add('hidden');
  }

  // 總音量
  const masterSlider = document.getElementById('master-slider');
  masterSlider.value = page.settings.masterVolume;
  masterSlider.addEventListener('input', function () {
    page.player.setMasterVolume(Number(masterSlider.value));
    page.settings.masterVolume = Number(masterSlider.value);
    saveSettings(page.settings);
  });

  const musicSlider = document.getElementById('music-slider');
  musicSlider.value = page.settings.musicVolume;
  musicSlider.addEventListener('input', function () {
    page.player.setMusicVolume(Number(musicSlider.value));
    page.settings.musicVolume = Number(musicSlider.value);
    saveSettings(page.settings);
  });

  document.getElementById('seek-bar').addEventListener('click', function (event) {
    if (!page.started || page.finished) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    seekTo(page.trimStart + ratio * (page.trimEnd - page.trimStart));
  });

  document.addEventListener('keydown', onKeyDown);
  window.addEventListener('resize', onResize);
}

// 設定導唱音量（0 = 關掉），按鈕和滑桿一起更新，並記住設定
// （測試模式的導唱音量只在這次有效，不會改到平常唱歌的設定）
function setGuideVolume(volume) {
  page.player.setGuideVolume(volume);
  if (!page.testMode) {
    page.settings.guideVolume = volume;
    if (volume > 0) {
      page.settings.guideLastVolume = volume;  // 記住音量，下次打開用這個
    }
    saveSettings(page.settings);
  }
  page.guideVolume = volume;

  document.getElementById('guide-slider').value = volume;
  const button = document.getElementById('guide-toggle');
  if (volume > 0) {
    button.textContent = t('導唱：開');
    button.classList.add('on');
  } else {
    button.textContent = t('導唱：關');
    button.classList.remove('on');
  }
}

// 導唱開 ↔ 關
function toggleGuide() {
  if (!page || !page.player || !page.player.hasVocals()) {
    return;
  }
  if (page.guideVolume > 0) {
    setGuideVolume(0);
  } else if (page.testMode) {
    setGuideVolume(100);
  } else {
    setGuideVolume(page.settings.guideLastVolume || 70);
  }
}

function onKeyDown(event) {
  if (!page) {
    return;
  }
  // 設定開著的時候（可能正在打名字），按鍵不要變成暫停、導唱
  if (document.querySelector('.dialog-backdrop')) {
    return;
  }
  // G 鍵：開關導唱（還沒開始、暫停中也可以按）
  if (event.code === 'KeyG') {
    toggleGuide();
    return;
  }
  if (!page.started || page.finished) {
    return;
  }
  if (event.code === 'Space') {
    event.preventDefault();
    togglePause();
  } else if (event.code === 'ArrowRight') {
    seekTo(page.player.getTime() + 5);
  } else if (event.code === 'ArrowLeft') {
    seekTo(page.player.getTime() - 5);
  }
}

function onResize() {
  if (page && page.pitchView) {
    page.pitchView.resize();
  }
}

function togglePause() {
  if (!page.started || page.finished) {
    return;
  }
  const button = document.getElementById('play-button');
  if (page.player.playing) {
    page.player.pause();
    if (page.recorder) {
      page.recorder.pause();
    }
    button.innerHTML = PLAY_LABEL;
  } else {
    page.player.play();
    if (page.recorder) {
      page.recorder.resume();
    }
    button.innerHTML = PAUSE_LABEL;
  }
}

// ---------- 設定（唱歌中也可以打開）----------
// 唱到一半打開：先暫停，關掉設定後自動繼續
function openSingSettings() {
  if (!page || page.finished) {
    return;
  }
  const myPage = page;
  const wasPlaying = page.started && page.player.playing;
  if (wasPlaying) {
    togglePause();
  }
  openSettingsDialog({
    onSaved: applySettings,
    onClose: function () {
      if (wasPlaying && page === myPage && !page.finished && !page.player.playing) {
        togglePause();
      }
    },
  });
}

// 存好的設定馬上用在這一首：音量、字幕顯示、MV、麥克風靈敏度、耳返、延遲補償、名字
// 評分的標準（難度、八度）唱到一半不換（一首歌前後標準會不一樣），按「重來」才換；
// 換麥克風要重新開麥克風，下一首才換；清掉小聲雜音（評分條進來時就排好了）要重新進入這首
// 回傳要顯示的提示（空字串 = 用預設的「設定已儲存」）
function applySettings(newSettings) {
  const old = page.settings;
  page.settings = newSettings;
  const singer = page.singers[0];
  singer.name = newSettings.playerName;

  page.player.setMasterVolume(newSettings.masterVolume);
  document.getElementById('master-slider').value = newSettings.masterVolume;
  if (singer.microphone) {
    singer.microphone.setGate(newSettings.micGate);
    singer.microphone.setMonitor(newSettings.monitor, newSettings.monitorVolume, newSettings.reverb);
  }
  page.lyricsView.setOptions(newSettings);
  applyMvSetting();

  const scoringChanged = old.difficulty !== newSettings.difficulty || old.octaveFree !== newSettings.octaveFree;
  const micChanged = old.micId !== newSettings.micId || old.echoCancel !== newSettings.echoCancel;
  const quietChanged = old.quietDb !== newSettings.quietDb;
  const later = [];
  if (quietChanged) {
    later.push(t('小聲雜音：重新進入這首歌後生效'));   // 評分條是進來時排好的
  }
  if (!page.started) {
    // 還沒開始唱：評分標準直接換（麥克風按「開始」時才開，也會用新的）
    singer.scorer = new Scorer(page.notes, newSettings, page.pitch.contour, page.pitch.heard);
    if (later.length === 0) {
      return '';
    }
    return t('設定已儲存（{later}）', { later: later.join(t('；')) });
  }
  if (scoringChanged) {
    later.push(t('難度、八度：按「重來」後生效'));
  }
  if (micChanged) {
    later.push(t('麥克風：下一首生效'));
  }
  if (later.length === 0) {
    return '';
  }
  return t('設定已儲存（{later}）', { later: later.join(t('；')) });
}

// MV：打開／關掉、亮度
function applyMvSetting() {
  const wantMv = page.song.has_video && page.settings.showMV;
  if (wantMv && !page.mv) {
    page.mv = new MvBackground(document.getElementById('sing-video'), api.videoUrl(page.songId),
      page.settings.mvBrightness);
  } else if (!wantMv && page.mv) {
    page.mv.destroy();
    page.mv = null;
  } else if (page.mv) {
    page.mv.setBrightness(page.settings.mvBrightness);
  }
}

function seekTo(time) {
  time = Math.max(page.trimStart, Math.min(time, page.trimEnd - 1));
  page.player.seek(time);
  for (const singer of page.singers) {
    singer.scorer.seek(time);
  }
  page.seeked = true;
}

// ---------- 跳過前奏、間奏 ----------
// 離下一個要唱的音還有 SKIP_MIN_WAIT 秒以上，就顯示「跳過前奏／間奏」按鈕，
// 按了跳到那個音的前 SKIP_LEAD 秒（中間沒有評分條，所以不影響分數）
const SKIP_MIN_WAIT = 8;
const SKIP_LEAD = 3;
const SKIP_AFTER = 0.3;   // 上一個音唱完 0.3 秒後才顯示（不然最後一個音還沒唱完，就被跳掉、算成 MISS）

// 現在之後，下一個要唱的音什麼時候開始；後面沒有了就回傳 null
function nextNoteStart(now) {
  for (const note of page.singers[0].scorer.notes) {
    if (note.s > now) {
      return note.s;
    }
  }
  return null;
}

// 已經開始的音裡，最晚什麼時候結束；還沒有音開始就回傳 -1
function previousNoteEnd(now) {
  let end = -1;
  for (const note of page.singers[0].scorer.notes) {
    if (note.s > now) {
      break;
    }
    end = Math.max(end, note.e);
  }
  return end;
}

// 每個畫面呼叫：決定要不要顯示「跳過」按鈕
function updateSkipButton(now) {
  const button = document.getElementById('skip-intro');
  const nextStart = nextNoteStart(now);
  const canSkip = page.started && !page.finished && page.player.playing &&
    nextStart !== null && nextStart - now >= SKIP_MIN_WAIT &&
    now >= previousNoteEnd(now) + SKIP_AFTER;
  button.classList.toggle('hidden', !canSkip);
  if (canSkip) {
    // 還沒唱過任何一個音 = 前奏，不然就是間奏
    const firstNote = nextNoteStart(-1);
    let text = t('跳過間奏');
    if (nextStart === firstNote) {
      text = t('跳過前奏');
    }
    if (button.dataset.label !== text) {   // 每一格畫面都會跑到這裡，字有變才換
      button.dataset.label = text;
      button.innerHTML = icon('skip') + ' ' + text;
    }
  }
}

function skipToNextNote() {
  const now = page.player.getTime();
  const nextStart = nextNoteStart(now);
  if (nextStart === null) {
    return;
  }
  const target = nextStart - SKIP_LEAD;
  // 跳之前，前面唱完的音先打分數（音唱完後要等一下才打分數，馬上按跳過的話會被當成「沒唱」）
  // 連擊也記下來：中間本來就沒有要唱的音，跳過去不應該斷連擊
  const combos = [];
  for (const singer of page.singers) {
    singer.scorer.update(target);
    combos.push(singer.scorer.combo);
  }
  // 中間沒有要唱的音，跳過去不算「跳過唱歌」，所以不改 page.seeked
  const seekedBefore = page.seeked;
  seekTo(target);
  page.seeked = seekedBefore;
  for (let i = 0; i < page.singers.length; i++) {
    page.singers[i].scorer.combo = combos[i];
  }
}

function restart() {
  if (!page.started) {
    return;
  }
  if (page.recordingUrl) {
    URL.revokeObjectURL(page.recordingUrl);
    page.recordingUrl = null;
  }
  page.finished = false;
  page.seeked = false;
  page.player.stop();
  page.player.seek(page.trimStart);   // 從裁切的開頭重新開始
  for (const singer of page.singers) {
    singer.scorer = new Scorer(page.notes, page.settings, page.pitch.contour, page.pitch.heard);
  }
  if (page.recorder) {
    page.recorder.stop();
  }
  createRecorder();
  if (page.recorder) {
    page.recorder.start();
  }
  hideOverlay();
  document.getElementById('play-button').innerHTML = PAUSE_LABEL;
  page.player.play();
}

// ---------- 結束 ----------

async function finish() {
  if (!page || !page.started || page.finished) {
    return;
  }
  page.finished = true;
  const myPage = page;
  const endTime = page.player.getTime();
  page.player.pause();

  const singer = page.singers[0];
  singer.scorer.finish(endTime);
  const result = calculateFinalScore(singer.scorer);

  // 錄音
  if (page.recorder) {
    const blob = await page.recorder.stop();
    if (page !== myPage) {
      return;
    }
    if (blob && blob.size > 0) {
      page.recordingUrl = URL.createObjectURL(blob);
    }
  }

  // 存分數：測試模式不存；唱不到一半也不存（「不計分的音」本來就不算，不列入）
  let skippedCount = 0;
  let total = 0;
  for (const note of singer.scorer.notes) {
    total++;
    if (note.skipped) {
      skippedCount++;
    }
  }
  let saveMessage = '';
  let isNewBest = false;
  if (page.testMode) {
    saveMessage = t('測試模式的分數不會存進排行');
  } else if (total === 0 || skippedCount > total * 0.5) {
    saveMessage = t('唱不到一半，這次不列入排行');
  } else {
    const oldBest = page.song.best_score;
    isNewBest = oldBest === null || oldBest === undefined || result.total > oldBest;
    try {
      await api.addScore(page.songId, {
        player: singer.name,
        total: result.total,
        details: {
          pitch: result.pitch, rhythm: result.rhythm, stability: result.stability,
          expression: result.expression, completion: result.completion,
          counts: result.counts, maxCombo: result.maxCombo, difficulty: page.settings.difficulty,
        },
      });
      page.song.best_score = Math.max(oldBest || 0, result.total);
      saveMessage = t('分數已存進排行');
      if (page.seeked) {
        saveMessage += t('（有跳過的部分不計分）');
      }
    } catch (error) {
      saveMessage = t('分數存檔失敗：{reason}', { reason: error.message });
    }
  }
  if (page !== myPage) {
    return;
  }

  const overlay = document.getElementById('sing-overlay');
  overlay.classList.remove('hidden');
  showResult(document.getElementById('overlay-box'), result, {
    recordingUrl: page.recordingUrl,
    recordingName: t('{title}-{score}分', { title: page.song.title, score: Math.round(result.total) }),
    saveMessage: saveMessage,
    isNewBest: isNewBest,
    onRetry: restart,
    backUrl: '#/song/' + encodeURIComponent(page.songId),
  });
}
