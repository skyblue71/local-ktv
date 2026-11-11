// 唱完的結果畫面：總分、五角形能力圖、各等級數量、錄音。

import { icon } from '../icons.js';
import { escapeHtml } from '../ui.js';

const AXES = [
  { key: 'pitch', label: '音準' },
  { key: 'rhythm', label: '節奏' },
  { key: 'stability', label: '穩定' },
  { key: 'expression', label: '表現力' },
  { key: 'completion', label: '完成度' },
];

// options: { recordingUrl, fileName, saveMessage, isNewBest, onRetry, backUrl }
export function showResult(container, result, options) {
  let recordingHtml = '';
  if (options.recordingUrl) {
    recordingHtml =
      '<div class="result-recording">' +
      '  <div class="muted small">你的錄音</div>' +
      '  <audio controls src="' + options.recordingUrl + '"></audio>' +
      '  <a class="btn btn-small" href="' + options.recordingUrl + '" download="' + escapeHtml(options.fileName) + '">' + icon('download') + ' 下載錄音</a>' +
      '</div>';
  }

  let barsHtml = '';
  for (const axis of AXES) {
    barsHtml +=
      '<div class="result-bar">' +
      '  <span class="result-bar-label">' + axis.label + '</span>' +
      '  <div class="result-bar-track"><div class="result-bar-fill" style="width:' + result[axis.key] + '%"></div></div>' +
      '  <span class="result-bar-value">' + result[axis.key].toFixed(1) + '</span>' +
      '</div>';
  }

  container.innerHTML =
    '<div class="result">' +
    (options.isNewBest ? '<div class="new-best">' + icon('star') + ' 新紀錄！</div>' : '') +
    '  <div class="result-top">' +
    '    <div class="result-score-box">' +
    '      <div class="result-rank rank-' + result.rank + '">' + result.rank + '</div>' +
    '      <div class="result-total" id="result-total">0.000</div>' +
    bonusHtml(result) +
    '      <div class="muted small">' + escapeHtml(options.saveMessage) + '</div>' +
    '    </div>' +
    '    <canvas class="radar" id="radar-canvas" width="260" height="240"></canvas>' +
    '  </div>' +
    '  <p class="result-comment">' + escapeHtml(result.comment) + '</p>' +
    '  <div class="result-bars">' + barsHtml + '</div>' +
    '  <div class="result-counts">' +
    '    <div><span class="grade grade-PERFECT">PERFECT</span><b>' + result.counts.PERFECT + '</b></div>' +
    '    <div><span class="grade grade-GREAT">GREAT</span><b>' + result.counts.GREAT + '</b></div>' +
    '    <div><span class="grade grade-GOOD">GOOD</span><b>' + result.counts.GOOD + '</b></div>' +
    '    <div><span class="grade grade-MISS">MISS</span><b>' + result.counts.MISS + '</b></div>' +
    '    <div><span class="grade">最大連擊</span><b>' + result.maxCombo + '</b></div>' +
    '  </div>' +
    techniquesHtml(result) +
    recordingHtml +
    '  <div class="button-row result-actions">' +
    '    <button class="btn btn-primary" id="retry-button">' + icon('refresh') + ' 再唱一次</button>' +
    '    <a class="btn" href="' + options.backUrl + '">返回</a>' +
    '  </div>' +
    '</div>';

  const audio = container.querySelector('.result-recording audio');
  if (audio) {
    findRecordingLength(audio);
  }
  container.querySelector('#retry-button').addEventListener('click', options.onRetry);
  drawRadar(container.querySelector('#radar-canvas'), result);
  countUp(container.querySelector('#result-total'), result.total);
}

// 讓播放條知道錄音總共多長。
// 瀏覽器錄的檔案裡沒有寫「總共多長」，不處理的話播放條只會顯示 0:00、看不到總長度、也不能拖。
// 做法：叫它跳到很後面，瀏覽器就會把整個檔案讀過一遍、算出長度；算好再跳回開頭。
// 這時候沒有在播放，不會出聲音。
function findRecordingLength(audio) {
  const FAR_AWAY = 1e101;   // 一個比任何錄音都長的秒數
  audio.addEventListener('loadedmetadata', function () {
    if (audio.duration !== Infinity) {
      return;   // 已經知道長度了，不用處理
    }
    function onLengthKnown() {
      if (audio.duration === Infinity) {
        return;   // 還沒算好
      }
      audio.removeEventListener('durationchange', onLengthKnown);
      audio.currentTime = 0;
    }
    audio.addEventListener('durationchange', onLengthKnown);
    audio.currentTime = FAR_AWAY;
  });
}

// 分數下面的「技巧加分 +X.X」（沒有加分就不顯示）
function bonusHtml(result) {
  if (!result.bonus || result.bonus <= 0) {
    return '';
  }
  return '<div class="result-bonus">' + icon('music') + ' 含技巧加分 +' + result.bonus.toFixed(1) + '</div>';
}

// 技巧次數：像日本 KTV 一樣，唱對的音符上有用技巧才算
function techniquesHtml(result) {
  const techniques = result.techniques || { scoop: 0, kobushi: 0, fall: 0 };
  const items = [
    { name: 'しゃくり', hint: '往上滑音', count: techniques.scoop },
    { name: 'こぶし', hint: '轉音', count: techniques.kobushi },
    { name: 'フォール', hint: '尾音下滑', count: techniques.fall },
    { name: 'ビブラート', hint: '顫音', count: result.vibratoCount },
  ];
  let html = '<div class="result-techniques">';
  for (const item of items) {
    html +=
      '<div>' +
      '  <span class="technique-name" lang="ja">' + item.name + '</span>' +
      '  <span class="technique-hint">' + item.hint + '</span>' +
      '  <b>' + item.count + '</b>' +
      '</div>';
  }
  html += '</div>';
  return html;
}

// 分數從 0 慢慢跳到最後的分數
function countUp(element, target) {
  const startTime = performance.now();
  const duration = 1500;
  function step(now) {
    if (!element.isConnected) {
      return;
    }
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = (target * eased).toFixed(3);
    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }
  requestAnimationFrame(step);
}

// 五角形能力圖
function drawRadar(canvas, result) {
  const ctx = canvas.getContext('2d');
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2 + 8;
  const radius = 85;
  const count = AXES.length;

  function pointAt(index, ratio) {
    const angle = -Math.PI / 2 + index * 2 * Math.PI / count;
    return {
      x: centerX + Math.cos(angle) * radius * ratio,
      y: centerY + Math.sin(angle) * radius * ratio,
    };
  }

  // 底下的格線
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  for (let level = 1; level <= 4; level++) {
    ctx.beginPath();
    for (let i = 0; i < count; i++) {
      const point = pointAt(i, level / 4);
      if (i === 0) {
        ctx.moveTo(point.x, point.y);
      } else {
        ctx.lineTo(point.x, point.y);
      }
    }
    ctx.closePath();
    ctx.stroke();
  }

  // 文字
  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  ctx.font = '13px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let i = 0; i < count; i++) {
    const point = pointAt(i, 1.22);
    ctx.fillText(AXES[i].label, point.x, point.y);
  }

  // 你的能力
  ctx.beginPath();
  for (let i = 0; i < count; i++) {
    const value = Math.max(0.05, result[AXES[i].key] / 100);
    const point = pointAt(i, value);
    if (i === 0) {
      ctx.moveTo(point.x, point.y);
    } else {
      ctx.lineTo(point.x, point.y);
    }
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(79, 240, 255, 0.3)';
  ctx.fill();
  ctx.strokeStyle = '#4ff0ff';
  ctx.lineWidth = 2;
  ctx.stroke();
}
