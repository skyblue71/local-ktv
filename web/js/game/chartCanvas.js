// 修譜的畫面（畫在 <canvas> 上）：
//   上面一條：時間尺（點一下從那裡播放）
//   中間：評分條（橫軸是時間，縱軸是音高，越上面越高；左邊寫音名）
//   下面一排：每個字（從開始唱到唱完，可以拖：調字的時間）
//   最下面一條：歌詞（看得出每一句在哪裡）
// 這個檔案只管「畫」和「座標換算」，改音符的動作在 chartModel.js、滑鼠操作在 chartPage.js

import { midiToName } from './noteNames.js';

const RULER_HEIGHT = 24;    // 上面時間尺的高度
const LYRICS_HEIGHT = 46;   // 下面歌詞的高度（兩行交替，時間很近的兩句才不會疊在一起）
const WORDS_HEIGHT = 30;    // 歌詞上面那一排「每個字」的高度（可以拖：調字的時間）
const WORD_COLOR = 'rgba(90, 200, 255, 0.30)';         // 程式算的字
const WORD_MANUAL_COLOR = 'rgba(255, 120, 170, 0.55)';  // 你調過的字
const KEYS_WIDTH = 44;      // 左邊音名的寬度
const EDGE_GRAB = 7;        // 評分條頭尾幾像素內，算「拉長縮短」

const AI_COLOR = 'rgba(90, 200, 255, 0.85)';       // AI 的音（沒動過）
const MANUAL_COLOR = 'rgba(255, 120, 170, 0.92)';  // 你畫的或改過的音
const BLACK_KEYS = [1, 3, 6, 8, 10];               // 黑鍵（那幾列顏色深一點，比較好認）

// 時間文字，例如 75.3 → "1:15.3"
export function timeText(seconds) {
  if (seconds < 0) {
    seconds = 0;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  let text = rest.toFixed(1);
  if (rest < 10) {
    text = '0' + text;
  }
  return minutes + ':' + text;
}

export class ChartCanvas {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d');
    this.viewStart = 0;        // 畫面最左邊是第幾秒
    this.secondsVisible = 12;  // 畫面寬度放幾秒
    this.low = 55;             // 最低顯示的音
    this.high = 79;            // 最高顯示的音
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

  // 依照全部的音符決定上下顯示的範圍（上下各多留幾個半音，至少 18 個半音）
  fitPitchRange(notes, low, high) {
    for (const note of notes) {
      low = Math.min(low, note.p);
      high = Math.max(high, note.p);
    }
    low -= 3;
    high += 3;
    if (high - low < 18) {
      const middle = Math.round((high + low) / 2);
      low = middle - 9;
      high = middle + 9;
    }
    this.low = low;
    this.high = high;
  }

  gridTop() {
    return RULER_HEIGHT;
  }

  gridBottom() {
    return this.height - LYRICS_HEIGHT - WORDS_HEIGHT;
  }

  // 「每個字」那一排的上緣（就在評分條區域下面）
  wordsTop() {
    return this.gridBottom();
  }

  // 一個字在畫面上的方塊
  wordRect(token) {
    const x1 = this.timeToX(token.start);
    const x2 = this.timeToX(token.end);
    return { x: x1, y: this.wordsTop() + 3, width: Math.max(3, x2 - x1), height: WORDS_HEIGHT - 6 };
  }

  // 滑鼠點到哪個字的哪裡：回傳 { line（第幾句）, index（這一句第幾個字，標點不算）, token, part }，沒點到回傳 null
  hitWord(x, lines) {
    if (!lines) {
      return null;
    }
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (line.end < this.viewStart - 1 || line.start > this.viewStart + this.secondsVisible + 1) {
        continue;
      }
      let index = -1;
      let found = null;
      for (const token of line.tokens || []) {
        if (!(token.syl > 0)) {
          continue;
        }
        index++;
        const rect = this.wordRect(token);
        if (x < rect.x - 2 || x > rect.x + rect.width + 2) {
          continue;
        }
        const grab = Math.min(EDGE_GRAB, rect.width / 3);
        let part = 'body';
        if (x - rect.x <= grab) {
          part = 'start';
        } else if (rect.x + rect.width - x <= grab) {
          part = 'end';
        }
        found = { line: i, index: index, token: token, part: part };
      }
      if (found !== null) {
        return found;
      }
    }
    return null;
  }

  timeToX(time) {
    return KEYS_WIDTH + (time - this.viewStart) / this.secondsVisible * (this.width - KEYS_WIDTH);
  }

  xToTime(x) {
    return this.viewStart + (x - KEYS_WIDTH) / (this.width - KEYS_WIDTH) * this.secondsVisible;
  }

  rowHeight() {
    return (this.gridBottom() - this.gridTop()) / (this.high - this.low + 1);
  }

  // 這個音那一列的上緣
  pitchToY(pitch) {
    return this.gridTop() + (this.high - pitch) * this.rowHeight();
  }

  yToPitch(y) {
    const pitch = this.high - Math.floor((y - this.gridTop()) / this.rowHeight());
    return Math.max(this.low, Math.min(this.high, pitch));
  }

  // 滑鼠在哪一區：'ruler'（時間尺）、'lyrics'（歌詞）、'keys'（音名）、'grid'（評分條）
  areaAt(x, y) {
    if (y < this.gridTop()) {
      return 'ruler';
    }
    if (y >= this.gridBottom() + WORDS_HEIGHT) {
      return 'lyrics';
    }
    if (y >= this.gridBottom()) {
      return 'words';
    }
    if (x < KEYS_WIDTH) {
      return 'keys';
    }
    return 'grid';
  }

  // 一個音符在畫面上的方塊
  noteRect(note) {
    const x1 = this.timeToX(note.s);
    const x2 = this.timeToX(note.e);
    const row = this.rowHeight();
    const height = Math.max(5, row * 0.8);
    const y = this.pitchToY(note.p) + (row - height) / 2;
    return { x: x1, y: y, width: Math.max(3, x2 - x1), height: height };
  }

  // 滑鼠點到哪個音符的哪裡：回傳 { note, part: 'start'（頭）| 'end'（尾）| 'body'（中間）}，沒點到回傳 null
  // 後面畫的在上面，所以從後面找
  hitNote(x, y, notes) {
    for (let i = notes.length - 1; i >= 0; i--) {
      const note = notes[i];
      const rect = this.noteRect(note);
      if (x < rect.x - 2 || x > rect.x + rect.width + 2 || y < rect.y - 2 || y > rect.y + rect.height + 2) {
        continue;
      }
      // 很短的音：頭尾各只留三分之一，中間才拖得動
      const grab = Math.min(EDGE_GRAB, rect.width / 3);
      let part = 'body';
      if (x - rect.x <= grab) {
        part = 'start';
      } else if (rect.x + rect.width - x <= grab) {
        part = 'end';
      }
      return { note: note, part: part };
    }
    return null;
  }

  // 每個畫面呼叫一次
  //   data = { notes, selected, ghosts（AI 有聽到、但沒在譜裡的音）, contour, hop, lines（歌詞）, now（播放到第幾秒）}
  draw(data) {
    const ctx = this.context;
    ctx.clearRect(0, 0, this.width, this.height);
    this.drawRows();
    this.drawTimeGrid();

    // 評分條區域：畫出去的部分切掉
    ctx.save();
    ctx.beginPath();
    ctx.rect(KEYS_WIDTH, this.gridTop(), this.width - KEYS_WIDTH, this.gridBottom() - this.gridTop());
    ctx.clip();
    this.drawContour(data.contour, data.hop);
    this.drawGhosts(data.ghosts);
    this.drawNotes(data.notes, data.selected);
    ctx.restore();

    this.drawWords(data.lines, data.selectedWord);
    this.drawLyrics(data.lines);
    this.drawKeys();
    this.drawNowLine(data.now);
  }

  // 每一列（每個半音）的底色，黑鍵深一點，C 那一列畫線
  drawRows() {
    const ctx = this.context;
    const row = this.rowHeight();
    for (let pitch = this.low; pitch <= this.high; pitch++) {
      const y = this.pitchToY(pitch);
      const key = ((pitch % 12) + 12) % 12;
      if (BLACK_KEYS.indexOf(key) >= 0) {
        ctx.fillStyle = 'rgba(0, 0, 0, 0.22)';
      } else {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.025)';
      }
      ctx.fillRect(KEYS_WIDTH, y, this.width - KEYS_WIDTH, row);
      if (key === 0) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.16)';
        ctx.fillRect(KEYS_WIDTH, y + row - 1, this.width - KEYS_WIDTH, 1);
      }
    }
  }

  // 時間格線和上面的時間尺
  drawTimeGrid() {
    const ctx = this.context;
    let step = 1;
    if (this.secondsVisible > 40) {
      step = 10;
    } else if (this.secondsVisible > 15) {
      step = 5;
    }
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.fillRect(0, 0, this.width, RULER_HEIGHT);
    ctx.font = '11px sans-serif';
    ctx.textBaseline = 'middle';
    const first = Math.ceil(this.viewStart / step) * step;
    for (let time = first; time <= this.viewStart + this.secondsVisible; time += step) {
      const x = this.timeToX(time);
      if (x < KEYS_WIDTH) {
        continue;
      }
      ctx.fillStyle = 'rgba(255, 255, 255, 0.07)';
      ctx.fillRect(x, this.gridTop(), 1, this.gridBottom() - this.gridTop());
      ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
      ctx.fillRect(x, RULER_HEIGHT - 6, 1, 6);
      ctx.fillText(timeText(time).replace(/\.0$/, ''), x + 3, RULER_HEIGHT / 2);
    }
  }

  // 左邊的音名（C 一定寫；格子夠高的話每個音都寫）
  drawKeys() {
    const ctx = this.context;
    const row = this.rowHeight();
    ctx.fillStyle = '#15121f';
    ctx.fillRect(0, this.gridTop(), KEYS_WIDTH, this.gridBottom() - this.gridTop());
    ctx.font = '11px sans-serif';
    ctx.textBaseline = 'middle';
    for (let pitch = this.low; pitch <= this.high; pitch++) {
      const key = ((pitch % 12) + 12) % 12;
      if (key !== 0 && row < 15) {
        continue;
      }
      if (key === 0) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      } else {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
      }
      ctx.fillText(midiToName(pitch), 6, this.pitchToY(pitch) + row / 2);
    }
  }

  // 原唱的音高曲線（AI 聽到的，淡淡的線）：照著它畫評分條
  drawContour(contour, hop) {
    if (!contour || contour.length === 0) {
      return;
    }
    const ctx = this.context;
    const row = this.rowHeight();
    const first = Math.max(0, Math.floor(this.viewStart / hop));
    const last = Math.min(contour.length - 1, Math.ceil((this.viewStart + this.secondsVisible) / hop));
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.45)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let drawing = false;
    for (let i = first; i <= last; i++) {
      const value = contour[i];
      if (value === 0) {
        drawing = false;
        continue;
      }
      const x = this.timeToX(i * hop);
      // 曲線是 0.1 半音一格；畫在那個音那一列的正中間
      const y = this.pitchToY(value / 10) + row / 2;
      if (drawing) {
        ctx.lineTo(x, y);
      } else {
        ctx.moveTo(x, y);
        drawing = true;
      }
    }
    ctx.stroke();
  }

  // AI 有聽到、但現在不在譜裡的音：虛線框（點一下可以加進來）
  drawGhosts(ghosts) {
    const ctx = this.context;
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.lineWidth = 1;
    for (const note of ghosts) {
      if (note.e < this.viewStart || note.s > this.viewStart + this.secondsVisible) {
        continue;
      }
      const rect = this.noteRect(note);
      ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1);
    }
    ctx.setLineDash([]);
  }

  drawNotes(notes, selected) {
    const ctx = this.context;
    for (const note of notes) {
      if (note.e < this.viewStart || note.s > this.viewStart + this.secondsVisible) {
        continue;
      }
      const rect = this.noteRect(note);
      if (note.u === 1) {
        ctx.fillStyle = MANUAL_COLOR;
      } else {
        ctx.fillStyle = AI_COLOR;
      }
      roundRect(ctx, rect.x, rect.y, rect.width, rect.height, Math.min(4, rect.height / 2));
      ctx.fill();
      if (note === selected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
        // 頭尾的小把手：看得出可以拉
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(rect.x + 1, rect.y + 2, 2, rect.height - 4);
        ctx.fillRect(rect.x + rect.width - 3, rect.y + 2, 2, rect.height - 4);
      }
    }
  }

  // 每個字一格（從這個字開始唱到唱完）：可以拖。藍色是程式算的，粉紅色是你調過的
  drawWords(lines, selected) {
    const ctx = this.context;
    const top = this.wordsTop();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
    ctx.fillRect(0, top, this.width, WORDS_HEIGHT);
    if (!lines) {
      return;
    }
    ctx.save();
    ctx.beginPath();
    ctx.rect(KEYS_WIDTH, top, this.width - KEYS_WIDTH, WORDS_HEIGHT);
    ctx.clip();
    ctx.font = '12px sans-serif';
    ctx.textBaseline = 'middle';
    for (const line of lines) {
      if (line.start === undefined || line.end < this.viewStart - 1 || line.start > this.viewStart + this.secondsVisible + 1) {
        continue;
      }
      for (const token of line.tokens || []) {
        if (!(token.syl > 0)) {
          continue;
        }
        const rect = this.wordRect(token);
        if (rect.x + rect.width < KEYS_WIDTH || rect.x > this.width) {
          continue;
        }
        ctx.fillStyle = token.manual ? WORD_MANUAL_COLOR : WORD_COLOR;
        ctx.fillRect(rect.x + 0.5, rect.y, Math.max(1, rect.width - 1), rect.height);
        if (token === selected) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.strokeRect(rect.x + 1, rect.y + 1, Math.max(1, rect.width - 2), rect.height - 2);
        }
        // 字寫在格子裡（太窄就切掉）
        ctx.save();
        ctx.beginPath();
        ctx.rect(rect.x, rect.y, rect.width, rect.height);
        ctx.clip();
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.fillText(token.text, rect.x + 3, rect.y + rect.height / 2);
        ctx.restore();
      }
    }
    ctx.restore();
  }

  // 下面的歌詞：每一句一個淡色的長條（從開始到結束），字寫在開頭；單數句、雙數句上下交替
  drawLyrics(lines) {
    const ctx = this.context;
    const top = this.gridBottom() + WORDS_HEIGHT;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.fillRect(0, top, this.width, LYRICS_HEIGHT);
    if (!lines) {
      return;
    }
    const half = LYRICS_HEIGHT / 2;
    ctx.font = '13px sans-serif';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.start === undefined || line.end < this.viewStart || line.start > this.viewStart + this.secondsVisible) {
        continue;
      }
      const y = top + (i % 2) * half;
      const x1 = Math.max(KEYS_WIDTH, this.timeToX(line.start));
      const x2 = this.timeToX(line.end);
      if (x2 <= KEYS_WIDTH) {
        continue;
      }
      ctx.fillStyle = 'rgba(255, 79, 139, 0.16)';
      ctx.fillRect(x1, y + 2, x2 - x1, half - 4);
      ctx.save();
      ctx.beginPath();
      ctx.rect(x1, y, Math.max(0, x2 - x1), half);
      ctx.clip();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
      ctx.fillText(line.text, x1 + 4, y + half / 2);
      ctx.restore();
    }
  }

  // 播放到哪裡：一條直線
  drawNowLine(now) {
    const x = this.timeToX(now);
    if (x < KEYS_WIDTH || x > this.width) {
      return;
    }
    const ctx = this.context;
    ctx.fillStyle = 'rgba(255, 79, 139, 0.95)';
    ctx.fillRect(x - 1, 0, 2, this.height);
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
