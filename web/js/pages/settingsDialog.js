// 設定對話方塊：麥克風、延遲補償、難度、字幕顯示、耳返…
// 有「測試麥克風」功能，可以即時看到你唱的音名，確認麥克風正常。
// 畫面上只放短短的名稱，詳細說明收在旁邊的小問號（helpTip）裡。
//
// 用法：openSettingsDialog()                    一般頁面（上方的「⚙ 設定」）
//       openSettingsDialog({ onSaved, onClose }) 唱歌畫面：存好後馬上套用在這一首
//         onSaved(新的設定) 回傳要顯示的提示（空字串 = 「設定已儲存」）
//         onClose()         不管有沒有存，關掉時呼叫

import { getAudioContext } from '../audio/audioContext.js';
import { listMicrophones, Microphone } from '../audio/microphone.js';
import { frequencyToMidi, midiToName } from '../game/noteNames.js';
import { icon } from '../icons.js';
import { loadSettings, saveSettings } from '../settings.js';
import { escapeHtml, helpTip, openDialog, showToast } from '../ui.js';

let testMicrophone = null;

function stopTest() {
  if (testMicrophone) {
    testMicrophone.stop();
    testMicrophone = null;
  }
}

export async function openSettingsDialog(options) {
  if (!options) {
    options = {};
  }
  const settings = loadSettings();

  // 每一列：左邊名字、右邊開關或數值（對齊成兩欄）
  function row(label, forId, control) {
    return '<label for="' + forId + '">' + label + '</label>' + control;
  }
  function switchRow(label, id) {
    return row(label, id, '<div><input type="checkbox" class="switch" id="' + id + '"></div>');
  }
  function rangeRow(label, id, min, max, step) {
    return row(label, id,
      '<div class="range-row"><input type="range" id="' + id + '" min="' + min + '" max="' + max + '" step="' + step + '">' +
      '<span class="range-value" id="' + id + '-value"></span></div>');
  }

  const html =
    '<div class="settings-columns">' +
    '  <div>' +
    '    <section class="settings-section tone-pink">' +
    '      <h4>' + icon('mic') + ' 麥克風</h4>' +
    '      <div class="form-grid">' +
    row('名字' + helpTip('顯示在分數排行上'), 'set-name', '<input class="input" id="set-name">') +
    row('麥克風', 'set-mic', '<select class="input" id="set-mic"><option value="">系統預設</option></select>') +
    '        <span>測試</span>' +
    '        <div class="mic-test">' +
    '          <button type="button" class="btn btn-small" id="mic-test-button">' + icon('mic') + ' 試試看</button>' +
    '          <div class="mic-meter wide"><div class="mic-meter-fill" id="test-meter"></div></div>' +
    '          <span class="test-note" id="test-note">—</span>' +
    '        </div>' +
    rangeRow('靈敏度' + helpTip('數字越小越靈敏；旁邊太吵就調大'), 'set-gate', 1, 40, 1) +
    switchRow('迴音消除' + helpTip('用喇叭唱的時候打開；戴耳機請關掉，比較準'), 'set-echo') +
    '      </div>' +
    '    </section>' +
    '    <section class="settings-section tone-gold">' +
    '      <h4>' + icon('star') + ' 評分</h4>' +
    '      <div class="form-grid">' +
    row('難度' + helpTip('簡單：音差一點也算對\n困難：要很準\n\n只影響之後唱的分數，已經存的分數不會變'), 'set-difficulty',
      '<select class="input" id="set-difficulty">' +
      '<option value="easy">簡單</option><option value="normal">普通</option><option value="hard">困難</option>' +
      '</select>') +
    switchRow('高低八度都算對' + helpTip('男生唱女生的歌（或相反）時打開\n\n只影響評分，評分條的位置不變'), 'set-octave') +
    rangeRow('延遲補償' + helpTip('明明準時開口，卻常常被判「慢」，就往右調\n\n只影響評分的時間，字幕和評分條不會動'), 'set-latency', -200, 400, 10) +
    rangeRow('清掉小聲雜音' + helpTip('句尾、字和字中間的聲音，比歌聲小這麼多分貝以上（回音、換氣、s 的尾音），就不畫評分條。\n' +
      '數字越小，清掉越多；太小會清到真的拉長音。0 = 不清\n\n' +
      '會影響：全部歌的評分條、句尾的字幕會早一點結束。\n' +
      '不會影響：你修過譜的歌、檔案本身。\n唱到一半改的話，重新進入這首歌才生效'), 'set-quiet', 0, 30, 1) +
    '      </div>' +
    '    </section>' +
    '    <section class="settings-section tone-cyan">' +
    '      <h4>' + icon('lyrics') + ' 字幕</h4>' +
    '      <div class="form-grid">' +
    switchRow('日文假名' + helpTip('漢字上方顯示假名'), 'set-ruby') +
    switchRow('羅馬拼音' + helpTip('日文、韓文下方顯示羅馬拼音'), 'set-roma') +
    row('中文歌', 'set-chinese',
      '<select class="input" id="set-chinese">' +
      '<option value="zhuyin">上方顯示注音</option><option value="pinyin">下方顯示拼音</option>' +
      '<option value="none">都不顯示</option></select>') +
    '      </div>' +
    '    </section>' +
    '  </div>' +
    '  <div>' +
    '    <section class="settings-section tone-violet">' +
    '      <h4>' + icon('volume') + ' 音量、MV</h4>' +
    '      <div class="form-grid">' +
    rangeRow('總音量' + helpTip('你聽到的整體大小（不影響錄音）。唱歌畫面下面也可以隨時調'), 'set-master-volume', 0, 100, 5) +
    switchRow('背景播 MV' + helpTip('有影片的歌才有（從 YouTube 加的歌、mp4 影片）'), 'set-mv') +
    rangeRow('MV 亮度' + helpTip('太亮會看不清楚字幕'), 'set-mv-brightness', 10, 100, 5) +
    '      </div>' +
    '    </section>' +
    '    <section class="settings-section tone-green">' +
    '      <h4>' + icon('music') + ' 耳返、錄音</h4>' +
    '      <div class="form-grid">' +
    switchRow('耳返' + helpTip('從耳機聽到自己的聲音。一定要戴耳機，不然會嘯叫'), 'set-monitor') +
    rangeRow('耳返音量', 'set-monitor-volume', 0, 100, 1) +
    rangeRow('迴音效果', 'set-reverb', 0, 100, 1) +
    switchRow('唱歌時錄音' + helpTip('唱完可以重聽、下載。不影響分數'), 'set-record') +
    switchRow('倒數 3、2、1' + helpTip('開始唱之前先倒數'), 'set-countdown') +
    '      </div>' +
    '    </section>' +
    '  </div>' +
    '</div>' +
    '<div class="dialog-actions">' +
    '  <button type="button" class="btn" id="settings-cancel">取消</button>' +
    '  <button type="button" class="btn btn-primary" id="settings-save">' + icon('save') + ' 儲存</button>' +
    '</div>';

  const dialog = openDialog('設定', html, function () {
    stopTest();
    if (options.onClose) {
      options.onClose();
    }
  }, 'wide');
  const box = dialog.box;
  box.querySelector('#settings-cancel').addEventListener('click', function () {
    dialog.close();
  });

  // 把目前的設定放進表單
  box.querySelector('#set-name').value = settings.playerName;
  box.querySelector('#set-gate').value = Math.round(settings.micGate * 1000);
  box.querySelector('#set-echo').checked = settings.echoCancel;
  box.querySelector('#set-difficulty').value = settings.difficulty;
  box.querySelector('#set-octave').checked = settings.octaveFree;
  box.querySelector('#set-latency').value = settings.latencyMs;
  box.querySelector('#set-quiet').value = settings.quietDb;
  box.querySelector('#set-ruby').checked = settings.showRuby;
  box.querySelector('#set-roma').checked = settings.showRoma;
  box.querySelector('#set-chinese').value = settings.chineseStyle;
  box.querySelector('#set-monitor').checked = settings.monitor;
  box.querySelector('#set-monitor-volume').value = settings.monitorVolume;
  box.querySelector('#set-reverb').value = settings.reverb;
  box.querySelector('#set-record').checked = settings.record;
  box.querySelector('#set-countdown').checked = settings.countdown;
  box.querySelector('#set-master-volume').value = settings.masterVolume;
  box.querySelector('#set-mv').checked = settings.showMV;
  box.querySelector('#set-mv-brightness').value = settings.mvBrightness;

  function showNumbers() {
    box.querySelector('#set-latency-value').textContent = box.querySelector('#set-latency').value + ' 毫秒';
    box.querySelector('#set-quiet-value').textContent = quietText(Number(box.querySelector('#set-quiet').value));
    box.querySelector('#set-mv-brightness-value').textContent = box.querySelector('#set-mv-brightness').value + '%';
    box.querySelector('#set-master-volume-value').textContent = box.querySelector('#set-master-volume').value + '%';
    box.querySelector('#set-monitor-volume-value').textContent = box.querySelector('#set-monitor-volume').value + '%';
    box.querySelector('#set-reverb-value').textContent = box.querySelector('#set-reverb').value + '%';
    box.querySelector('#set-gate-value').textContent = (box.querySelector('#set-gate').value / 1000).toFixed(3);
  }
  showNumbers();
  for (const id of ['#set-latency', '#set-quiet', '#set-mv-brightness', '#set-master-volume', '#set-monitor-volume', '#set-reverb']) {
    box.querySelector(id).addEventListener('input', showNumbers);
  }
  box.querySelector('#set-gate').addEventListener('input', function () {
    showNumbers();
    if (testMicrophone) {
      testMicrophone.setGate(box.querySelector('#set-gate').value / 1000);
    }
  });

  // 麥克風清單
  await fillMicrophoneList(box, settings.micId);

  box.querySelector('#mic-test-button').addEventListener('click', function () {
    toggleMicTest(box);
  });

  box.querySelector('#settings-save').addEventListener('click', function () {
    settings.playerName = box.querySelector('#set-name').value.trim() || '我';
    settings.micId = box.querySelector('#set-mic').value;
    settings.micGate = box.querySelector('#set-gate').value / 1000;
    settings.echoCancel = box.querySelector('#set-echo').checked;
    settings.difficulty = box.querySelector('#set-difficulty').value;
    settings.octaveFree = box.querySelector('#set-octave').checked;
    settings.latencyMs = Number(box.querySelector('#set-latency').value);
    settings.quietDb = Number(box.querySelector('#set-quiet').value);
    settings.showRuby = box.querySelector('#set-ruby').checked;
    settings.showRoma = box.querySelector('#set-roma').checked;
    settings.chineseStyle = box.querySelector('#set-chinese').value;
    settings.monitor = box.querySelector('#set-monitor').checked;
    settings.monitorVolume = Number(box.querySelector('#set-monitor-volume').value);
    settings.reverb = Number(box.querySelector('#set-reverb').value);
    settings.record = box.querySelector('#set-record').checked;
    settings.countdown = box.querySelector('#set-countdown').checked;
    settings.masterVolume = Number(box.querySelector('#set-master-volume').value);
    settings.showMV = box.querySelector('#set-mv').checked;
    settings.mvBrightness = Number(box.querySelector('#set-mv-brightness').value);
    saveSettings(settings);
    let message = '';
    if (options.onSaved) {
      message = options.onSaved(settings) || '';
    }
    if (message === '') {
      message = '設定已儲存';
    }
    showToast(message, 'ok');
    dialog.close();
  });
}

// 「清掉小聲雜音」旁邊的字
function quietText(db) {
  if (db === 0) {
    return '不清';
  }
  return db + ' 分貝';
}

async function fillMicrophoneList(box, selectedId) {
  const select = box.querySelector('#set-mic');
  let microphones = [];
  try {
    microphones = await listMicrophones();
  } catch (error) {
    return;
  }
  let html = '<option value="">系統預設</option>';
  for (const mic of microphones) {
    if (mic.id === 'default' || mic.id === '') {
      continue;
    }
    html += '<option value="' + escapeHtml(mic.id) + '">' + escapeHtml(mic.name) + '</option>';
  }
  select.innerHTML = html;
  select.value = selectedId;
  if (select.value !== selectedId) {
    select.value = '';
  }
}

async function toggleMicTest(box) {
  const button = box.querySelector('#mic-test-button');
  if (testMicrophone) {
    stopTest();
    button.innerHTML = icon('mic') + ' 試試看';
    return;
  }
  const context = getAudioContext();
  await context.resume();
  testMicrophone = new Microphone(context);
  try {
    await testMicrophone.start(box.querySelector('#set-mic').value, box.querySelector('#set-echo').checked);
  } catch (error) {
    testMicrophone = null;
    showToast('無法開啟麥克風：' + error.message, 'error');
    return;
  }
  testMicrophone.setGate(box.querySelector('#set-gate').value / 1000);
  button.innerHTML = icon('stop') + ' 停止';
  // 第一次允許麥克風之後，才看得到麥克風的名字，所以重新整理清單
  fillMicrophoneList(box, box.querySelector('#set-mic').value);

  const meter = box.querySelector('#test-meter');
  const noteLabel = box.querySelector('#test-note');
  testMicrophone.onPitch = function (frame) {
    let percent = 0;
    if (frame.rms > 0) {
      percent = Math.max(0, Math.min(100, (20 * Math.log10(frame.rms) + 60) / 60 * 100));
    }
    meter.style.width = percent + '%';
    if (frame.freq > 0) {
      noteLabel.textContent = midiToName(frequencyToMidi(frame.freq)) + '（' + Math.round(frame.freq) + ' Hz）';
    }
  };
}
