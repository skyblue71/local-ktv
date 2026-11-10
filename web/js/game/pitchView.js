// 音高畫面：畫在 <canvas> 上。
//   橫軸是時間（往左流動），縱軸是音高（越上面越高）
//   長條 = 該唱的音符，線 = 你唱的音高，豎線 = 現在的時間
//
// 視覺效果（只管「怎麼畫」；時間、音高的位置由 timeToX、pitchToY、updateRange 算）：
//   跟著音樂：最下面一排頻譜柱（setSpectrum 給資料，audio\musicSpectrum.js 算的）
//   跟著你唱的：
//     你的音高線越舊越淡，像彗星的尾巴
//     正在唱的那一條會亮起來，現在時間線上有一個圈圈標出「要唱到這裡」
//     唱準的時候：音高球外面有光圈一圈一圈擴散、往後噴火花
//     唱對的部分用金色填進長條，最前面有一顆亮點
//   打分數的時候：長條變成等級的顏色、有一圈光炸開；PERFECT 還多一圈小星星

import { midiToName } from './noteNames.js';

const SECONDS_BEFORE = 1.8;   // 現在時間線左邊顯示幾秒
const SECONDS_AFTER = 4.5;    // 右邊顯示幾秒
const NOW_POSITION = 0.28;    // 現在時間線在畫面寬度的哪裡
const BALL_EDGE = 8;          // 你的音高球最多到畫面邊緣往內幾像素（唱太高、太低時停在邊上）

// ---- 下面這些只影響好不好看，可以隨意調 ----
const ON_PITCH = 0.7;         // 準確度多少以上算「唱準」（跟音高線變色的標準一樣）
const SPARK_RATE = 50;        // 唱準的時候每秒噴幾顆火花
const SPARK_LIFE = 0.6;       // 一顆火花活幾秒
const SPARK_LIMIT = 100;      // 畫面上最多幾顆火花（太多會變慢）
const RING_SPEED = 1.5;       // 唱準時的光圈每秒擴散幾圈
const EVENT_SECONDS = 0.9;    // 等級提示（PERFECT…）顯示幾秒
const SPECTRUM_HEIGHT = 0.26; // 頻譜柱最高佔畫面高度的多少
const SPECTRUM_FALL = 1.6;    // 頻譜柱每秒最多掉多少（1 = 整根），慢慢掉比較好看
const SPECTRUM_CURVE = 1.8;   // 越大，小聲的柱子越矮、只有大聲的才衝高（1 = 照原本的大小）
const FONT = '"Segoe UI", "Microsoft JhengHei", sans-serif';

// 等級的顏色（紅、綠、藍三個數字，畫的時候再配上透明度）
const GRADE_RGB = {
  PERFECT: '255, 213, 74',
  GREAT: '108, 240, 160',
  GOOD: '90, 200, 255',
  MISS: '255, 120, 140',
};

function gradeColor(grade, alpha) {
  return 'rgba(' + (GRADE_RGB[grade] || GRADE_RGB.GOOD) + ', ' + alpha + ')';
}

export class PitchView {
  constructor(canvas, pitchData) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d');
    this.contour = pitchData.contour || [];
    this.hop = pitchData.hop || 0.01;
    this.viewLow = (pitchData.low || 60) - 3;
    this.viewHigh = (pitchData.high || 72) + 3;
    this.spectrum = null;     // 音樂頻譜（沒給就不畫）
    this.barLevels = [];      // 畫面上每根頻譜柱現在的高度（慢慢掉）
    this.sparks = [];         // 火花：{ x, y, vx, vy, life, color }
    this.sparkDebt = 0;       // 還欠幾顆火花沒噴（不到一顆的先存著）
    this.lastClock = 0;       // 上一個畫面的時間（算這一格過了幾秒）
    this.resize();
  }

  resize() {
    const ratio = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = Math.round(rect.width * ratio);
    this.canvas.height = Math.round(rect.height * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  timeToX(time, now) {
    const nowX = this.width * NOW_POSITION;
    const pixelsPerSecond = (this.width - nowX) / SECONDS_AFTER;
    return nowX + (time - now) * pixelsPerSecond;
  }

  pitchToY(pitch) {
    const range = this.viewHigh - this.viewLow;
    return this.height - ((pitch - this.viewLow) / range) * this.height;
  }

  // 依照附近的音符，慢慢調整上下的顯示範圍
  updateRange(notes, now) {
    let low = 999;
    let high = -999;
    for (const note of notes) {
      if (note.e < now - SECONDS_BEFORE || note.s > now + SECONDS_AFTER + 2) {
        continue;
      }
      low = Math.min(low, note.p);
      high = Math.max(high, note.p);
    }
    if (low > high) {
      return;
    }
    let targetLow = low - 4;
    let targetHigh = high + 4;
    // 至少顯示 14 個半音
    if (targetHigh - targetLow < 14) {
      const middle = (targetHigh + targetLow) / 2;
      targetLow = middle - 7;
      targetHigh = middle + 7;
    }
    this.viewLow += (targetLow - this.viewLow) * 0.03;
    this.viewHigh += (targetHigh - this.viewHigh) * 0.03;
  }

  // 給這一格畫面的音樂頻譜：一排 0～1 的數字（左邊低音、右邊高音）。不給（null）就不畫
  setSpectrum(levels) {
    this.spectrum = levels;
  }

  // 每一個畫面呼叫一次。singers = [{ scorer, color }]（未來共唱會有好幾個）
  draw(now, singers) {
    const ctx = this.context;
    const notes = singers[0].scorer.notes;
    this.updateRange(notes, now);

    // 特效用的時鐘：用真的時間，不用歌曲的時間（暫停時火花、頻譜柱還是會慢慢消失）
    const clock = performance.now() / 1000;
    const step = Math.max(0, Math.min(0.1, clock - this.lastClock));   // 這一格過了幾秒
    this.lastClock = clock;

    ctx.clearRect(0, 0, this.width, this.height);
    this.drawGrid();
    this.drawSpectrum(step);
    this.drawContour(now);
    const active = this.drawNotes(notes, now);
    for (const singer of singers) {
      this.drawTrace(singer.scorer.trace, now, singer.color);
    }
    this.drawNowLine(now, singers, active, clock, step);
    this.drawSparks(step);
    for (const singer of singers) {
      this.drawEvents(singer.scorer.events, now);
    }
  }

  drawGrid() {
    const ctx = this.context;
    ctx.font = '11px ' + FONT;
    ctx.textBaseline = 'middle';
    ctx.lineWidth = 1;
    for (let pitch = Math.ceil(this.viewLow); pitch <= this.viewHigh; pitch++) {
      const y = this.pitchToY(pitch);
      const isC = ((pitch % 12) + 12) % 12 === 0;
      ctx.strokeStyle = isC ? 'rgba(255,255,255,0.14)' : 'rgba(255,255,255,0.05)';
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();
      if (isC) {
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.fillText(midiToName(pitch), 6, y);
      }
    }
  }

  // 最下面一排跟著音樂跳的柱子：音樂大聲就高。往上跳是馬上的，掉下來是慢慢的
  drawSpectrum(step) {
    if (this.spectrum === null || this.spectrum.length === 0) {
      return;
    }
    const ctx = this.context;
    const count = this.spectrum.length;
    const slot = this.width / count;          // 每根柱子佔多寬（含旁邊的空隙）
    const barWidth = Math.max(2, slot * 0.62);
    const maxHeight = this.height * SPECTRUM_HEIGHT;

    // 顏色：下面粉紅、上面青色，越上面越透明
    const gradient = ctx.createLinearGradient(0, this.height, 0, this.height - maxHeight);
    gradient.addColorStop(0, 'rgba(255, 79, 139, 0.36)');
    gradient.addColorStop(0.55, 'rgba(255, 138, 92, 0.24)');
    gradient.addColorStop(1, 'rgba(79, 232, 255, 0.2)');
    ctx.fillStyle = gradient;

    for (let i = 0; i < count; i++) {
      const target = this.spectrum[i];
      let level = this.barLevels[i] || 0;
      if (target > level) {
        level = target;
      } else {
        level = Math.max(target, level - SPECTRUM_FALL * step);
      }
      this.barLevels[i] = level;
      if (level < 0.02) {
        continue;
      }
      const barHeight = Math.pow(level, SPECTRUM_CURVE) * maxHeight;
      const x = i * slot + (slot - barWidth) / 2;
      roundRect(ctx, x, this.height - barHeight, barWidth, barHeight + 4, barWidth / 2);
      ctx.fill();
    }
  }

  // 原唱的音高曲線（淡淡的）
  drawContour(now) {
    if (this.contour.length === 0) {
      return;
    }
    const ctx = this.context;
    const startIndex = Math.max(0, Math.floor((now - SECONDS_BEFORE) / this.hop));
    const endIndex = Math.min(this.contour.length - 1, Math.ceil((now + SECONDS_AFTER) / this.hop));
    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let drawing = false;
    for (let i = startIndex; i <= endIndex; i += 2) {
      const value = this.contour[i];
      if (value === 0) {
        drawing = false;
        continue;
      }
      const x = this.timeToX(i * this.hop, now);
      const y = this.pitchToY(value / 10);
      if (drawing) {
        ctx.lineTo(x, y);
      } else {
        ctx.moveTo(x, y);
        drawing = true;
      }
    }
    ctx.stroke();
  }

  // 畫所有看得到的音符。回傳「現在正在唱的那一條」（沒有就 null），給現在時間線畫目標圈用
  drawNotes(notes, now) {
    const ctx = this.context;
    const rowHeight = this.height / (this.viewHigh - this.viewLow);
    const barHeight = Math.max(6, rowHeight * 0.75);
    const radius = barHeight / 2;
    let active = null;

    for (const note of notes) {
      if (note.e < now - SECONDS_BEFORE) {
        continue;
      }
      if (note.s > now + SECONDS_AFTER) {
        break;
      }
      const x1 = this.timeToX(note.s, now);
      const x2 = this.timeToX(note.e, now);
      const y = this.pitchToY(note.p) - barHeight / 2;
      const width = Math.max(3, x2 - x1);
      const singingNow = note.s <= now && now <= note.e;
      if (singingNow && active === null) {
        active = note;
      }

      if (note.judged && !note.skipped) {
        // 打過分數的：等級的顏色。唱對的外面多一圈淡淡的光，上面有一道亮邊
        if (note.grade === 'MISS') {
          ctx.fillStyle = 'rgba(255,255,255,0.12)';
          roundRect(ctx, x1, y, width, barHeight, radius);
          ctx.fill();
        } else {
          ctx.fillStyle = gradeColor(note.grade, 0.2);
          roundRect(ctx, x1 - 3, y - 3, width + 6, barHeight + 6, radius + 3);
          ctx.fill();
          ctx.fillStyle = gradeColor(note.grade, 1);
          roundRect(ctx, x1, y, width, barHeight, radius);
          ctx.fill();
          this.drawShine(x1, y, width, barHeight);
        }
        continue;
      }

      // 還沒打分數的：半透明的長條，有一圈細邊。正在唱的那一條亮起來
      if (singingNow) {
        ctx.fillStyle = 'rgba(255,255,255,0.1)';
        roundRect(ctx, x1 - 4, y - 4, width + 8, barHeight + 8, radius + 4);
        ctx.fill();
      }
      ctx.fillStyle = singingNow ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.18)';
      roundRect(ctx, x1, y, width, barHeight, radius);
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = singingNow ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.3)';
      ctx.stroke();

      // 唱到一半：用金色填滿「唱對的部分」（跟評分器用同一個「要唱多久」），最前面一顆亮點
      if (!note.judged && note.hit > 0) {
        const ratio = Math.min(1, note.hit / note.needed);
        const filled = Math.max(3, width * ratio);
        const gold = ctx.createLinearGradient(x1, 0, x1 + width, 0);
        gold.addColorStop(0, 'rgba(255, 170, 70, 0.95)');
        gold.addColorStop(1, 'rgba(255, 228, 120, 0.98)');
        ctx.fillStyle = gold;
        roundRect(ctx, x1, y, filled, barHeight, radius);
        ctx.fill();
        this.drawShine(x1, y, filled, barHeight);
        if (singingNow) {
          const headX = x1 + filled - radius;
          const headY = y + barHeight / 2;
          ctx.fillStyle = 'rgba(255, 240, 180, 0.35)';
          ctx.beginPath();
          ctx.arc(headX, headY, radius + 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
          ctx.beginPath();
          ctx.arc(headX, headY, Math.max(2, radius * 0.55), 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    return active;
  }

  // 長條上面那道亮邊（看起來有一點立體）
  drawShine(x, y, width, height) {
    if (width < 8 || height < 6) {
      return;
    }
    const ctx = this.context;
    ctx.fillStyle = 'rgba(255,255,255,0.28)';
    roundRect(ctx, x + 3, y + 1.5, width - 6, height * 0.3, height * 0.15);
    ctx.fill();
  }

  // 你唱的音高線：越舊的地方越淡（像彗星的尾巴）
  drawTrace(trace, now, color) {
    const ctx = this.context;
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    let previous = null;
    for (const point of trace) {
      if (point.t < now - SECONDS_BEFORE || point.m === null) {
        previous = null;
        continue;
      }
      if (point.jump) {
        previous = point;   // 這一點換了八度：不跟上一點連起來
        continue;
      }
      if (previous !== null && point.t - previous.t < 0.06) {
        if (point.a < 0) {
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';   // 這裡沒有要唱的音：淡淡的白色
        } else if (point.a >= ON_PITCH) {
          ctx.strokeStyle = color;
        } else if (point.a > 0) {
          ctx.strokeStyle = 'rgba(255, 200, 90, 0.9)';
        } else {
          ctx.strokeStyle = 'rgba(255, 110, 130, 0.75)';
        }
        const age = Math.max(0, Math.min(1, (now - point.t) / SECONDS_BEFORE));   // 0 = 剛唱的，1 = 最舊的
        ctx.globalAlpha = 1 - age * 0.8;
        ctx.beginPath();
        ctx.moveTo(this.timeToX(previous.t, now), this.pitchToY(previous.m));
        ctx.lineTo(this.timeToX(point.t, now), this.pitchToY(point.m));
        ctx.stroke();
      }
      previous = point;
    }
    ctx.globalAlpha = 1;
  }

  // 現在時間線、目標圈、你的音高球（唱準時有光圈、噴火花）
  //   active：現在正在唱的那一條音符（沒有就 null）
  drawNowLine(now, singers, active, clock, step) {
    const ctx = this.context;
    const x = this.timeToX(now, now);

    // 豎線：中間亮、兩頭淡；旁邊一片淡淡的光
    const glow = ctx.createLinearGradient(0, 0, 0, this.height);
    glow.addColorStop(0, 'rgba(255,79,139,0)');
    glow.addColorStop(0.5, 'rgba(255,79,139,0.16)');
    glow.addColorStop(1, 'rgba(255,79,139,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(x - 9, 0, 18, this.height);
    const gradient = ctx.createLinearGradient(0, 0, 0, this.height);
    gradient.addColorStop(0, 'rgba(255,79,139,0)');
    gradient.addColorStop(0.5, 'rgba(255,79,139,0.9)');
    gradient.addColorStop(1, 'rgba(255,79,139,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(x - 1.5, 0, 3, this.height);

    // 目標圈：現在要唱到這個高度
    if (active !== null) {
      const targetY = this.pitchToY(active.p);
      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(255,255,255,0.6)';
      ctx.beginPath();
      ctx.arc(x, targetY, 12, 0, Math.PI * 2);
      ctx.stroke();
    }

    // 你現在的音高：一顆發光的球
    for (const singer of singers) {
      const trace = singer.scorer.trace;
      if (trace.length === 0) {
        continue;
      }
      const last = trace[trace.length - 1];
      if (last.m === null || now - last.t > 0.25) {
        continue;
      }
      // 唱得比畫面還高（或還低）：球停在畫面的頂端（底端），看得出來唱太高（太低）
      const y = Math.max(BALL_EDGE, Math.min(this.height - BALL_EDGE, this.pitchToY(last.m)));

      // 唱準了：光圈一圈一圈往外擴散、往後噴火花
      if (last.a >= ON_PITCH) {
        for (let i = 0; i < 2; i++) {
          const phase = (clock * RING_SPEED + i * 0.5) % 1;   // 0 → 1：這一圈擴散到哪了
          ctx.globalAlpha = (1 - phase) * 0.8;
          ctx.lineWidth = 2;
          ctx.strokeStyle = singer.color;
          ctx.beginPath();
          ctx.arc(x, y, 9 + phase * 20, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        this.addSparks(x, y, singer.color, step);
      }

      ctx.shadowColor = singer.color;
      ctx.shadowBlur = 16;
      ctx.fillStyle = singer.color;
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = 'rgba(255,255,255,0.9)';   // 球中間一點白，比較亮
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // 從 (x, y) 噴火花：照這一格過了幾秒，決定噴幾顆
  addSparks(x, y, color, step) {
    this.sparkDebt += SPARK_RATE * step;
    while (this.sparkDebt >= 1) {
      this.sparkDebt -= 1;
      if (this.sparks.length >= SPARK_LIMIT) {
        continue;
      }
      // 一半是歌手的顏色、一半是金色，往左邊（已經唱過的方向）散開
      let sparkColor = color;
      if (Math.random() < 0.5) {
        sparkColor = '#ffe27a';
      }
      this.sparks.push({
        x: x,
        y: y,
        vx: -(50 + Math.random() * 170),
        vy: (Math.random() - 0.5) * 150,
        life: SPARK_LIFE * (0.5 + Math.random() * 0.5),
        color: sparkColor,
      });
    }
  }

  // 火花：往後飛、慢慢往下掉、越來越小越來越淡
  drawSparks(step) {
    if (this.sparks.length === 0) {
      return;
    }
    const ctx = this.context;
    const alive = [];
    ctx.globalCompositeOperation = 'lighter';   // 疊在一起會更亮
    for (const spark of this.sparks) {
      spark.life -= step;
      if (spark.life <= 0) {
        continue;
      }
      spark.x += spark.vx * step;
      spark.y += spark.vy * step;
      spark.vy += 120 * step;
      const strength = Math.min(1, spark.life / SPARK_LIFE);
      ctx.globalAlpha = strength;
      ctx.fillStyle = spark.color;
      ctx.beginPath();
      ctx.arc(spark.x, spark.y, 1 + strength * 2, 0, Math.PI * 2);
      ctx.fill();
      alive.push(spark);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
    this.sparks = alive;
  }

  // 等級提示：字往上飄、慢慢消失；唱對的多一圈炸開的光，PERFECT 再多一圈小星星
  drawEvents(events, now) {
    const ctx = this.context;
    ctx.textAlign = 'center';
    for (const event of events) {
      const age = now - event.time;
      if (age < 0 || age > EVENT_SECONDS) {
        continue;
      }
      const progress = age / EVENT_SECONDS;   // 0 → 1
      const alpha = 1 - progress;
      const x = this.timeToX(event.time, now);
      const centerY = this.pitchToY(event.pitch);

      if (event.grade !== 'MISS') {
        ctx.lineWidth = 1 + 3 * alpha;
        ctx.strokeStyle = gradeColor(event.grade, alpha * 0.9);
        ctx.beginPath();
        ctx.arc(x, centerY, 8 + progress * 36, 0, Math.PI * 2);
        ctx.stroke();
      }
      if (event.grade === 'PERFECT') {
        // 八顆小星星往外飛（角度照這個音的時間決定，每個音不太一樣）
        ctx.fillStyle = gradeColor('PERFECT', alpha);
        for (let i = 0; i < 8; i++) {
          const angle = i * Math.PI / 4 + event.time;
          const distance = 12 + progress * 46;
          ctx.beginPath();
          ctx.arc(x + Math.cos(angle) * distance, centerY + Math.sin(angle) * distance, 2.6 * alpha + 0.4, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // 字：剛出現的 0.12 秒大一點，像跳出來
      const pop = Math.max(0, 1 - age / 0.12);
      ctx.font = 'bold ' + Math.round(18 + pop * 8) + 'px ' + FONT;
      ctx.fillStyle = 'rgba(0,0,0,' + alpha * 0.55 + ')';   // 字後面一點黑影，背景亮的時候也看得清楚
      ctx.fillText(event.grade, x + 1, centerY - 18 - age * 40 + 1.5);
      ctx.fillStyle = gradeColor(event.grade, alpha);
      ctx.fillText(event.grade, x, centerY - 18 - age * 40);
    }
    ctx.textAlign = 'left';
  }
}

// 畫圓角長方形
function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.arcTo(x + width, y, x + width, y + r, r);
  ctx.lineTo(x + width, y + height - r);
  ctx.arcTo(x + width, y + height, x + width - r, y + height, r);
  ctx.lineTo(x + r, y + height);
  ctx.arcTo(x, y + height, x, y + height - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}
