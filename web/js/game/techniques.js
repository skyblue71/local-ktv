// 技巧偵測：像日本 KTV 一樣，唱出技巧會加分。
//   しゃくり（往上滑音）：音的開頭從下面很快滑上來，然後穩穩停在音上
//   こぶし（轉音）    ：音的中間，音高很快地拐一下，又回到音上
//   フォール（尾音下滑）：句尾的長音，最後往下掉
// 只算「唱對」的音符（PERFECT、GREAT、GOOD）：音唱錯的話，技巧再多也不加分。
//
// 每個音符的 samples 是 [{ t: 時間, d: 跟音符差幾個半音 }, ...]（評分器 scorer.js 收集的）

import { median, movingAverage } from './scoreMath.js';

const ERROR_LIMIT = 3.0;     // 跟音符差超過 3 個半音：偵測器聽錯了，不看
const ON_PITCH = 0.35;       // 跟音符差這麼多以內，算「在音上」

const SCOOP_BELOW = 0.7;     // しゃくり：一開始至少比音符低 0.7 個半音
const SCOOP_WINDOW = 0.25;   //          而且音符開始後 0.25 秒內要滑到音上
const FALL_DROP = 1.0;       // フォール：最後至少往下掉 1 個半音
const KOBUSHI_SIZE = 0.6;    // こぶし：拐的幅度至少 0.6 個半音
const KOBUSHI_WIDTH = 0.2;   //        而且 0.2 秒內就回到音上

const POINTS_EACH = 0.2;     // 每個技巧加 0.2 分
const MAX_BONUS = 3;         // 最多加 3 分

// 整理一個音符的音高：去掉聽錯的，再稍微抹平（不然一點點抖動就會被當成技巧）
function cleanPoints(note) {
  const times = [];
  const values = [];
  for (const sample of note.samples) {
    if (Math.abs(sample.d) <= ERROR_LIMIT) {
      times.push(sample.t);
      values.push(sample.d);
    }
  }
  if (values.length < 5) {
    return [];
  }
  const smooth = movingAverage(values, 2);
  const points = [];
  for (let i = 0; i < smooth.length; i++) {
    points.push({ t: times[i], d: smooth[i] });
  }
  return points;
}

// 時間在 from ~ to 之間的點
function pointsBetween(points, from, to) {
  const result = [];
  for (const point of points) {
    if (point.t >= from && point.t <= to) {
      result.push(point);
    }
  }
  return result;
}

// 差幾個半音（只要大小，不管往上或往下）
function sizes(points) {
  const result = [];
  for (const point of points) {
    result.push(Math.abs(point.d));
  }
  return result;
}

// しゃくり（往上滑音）
function isScoop(note, points, previous) {
  if (note.e - note.s < 0.3) {
    return false;
  }
  // 從比較低的音直接接上來，是旋律本身，不算
  if (previous !== null && note.s - previous.e < 0.12 && previous.p < note.p) {
    return false;
  }
  const head = pointsBetween(points, -Infinity, note.s + SCOOP_WINDOW);
  if (head.length < 5) {
    return false;
  }
  // 一開始要比音符低
  const first = (head[0].d + head[1].d + head[2].d) / 3;
  if (first > -SCOOP_BELOW) {
    return false;
  }
  // 找「滑到音上」的時間
  let landedAt = null;
  for (let i = 3; i < head.length; i++) {
    if (Math.abs(head[i].d) <= ON_PITCH) {
      landedAt = head[i].t;
      break;
    }
  }
  if (landedAt === null) {
    return false;
  }
  // 滑上來之後要穩穩停在音上 0.1 秒
  const after = pointsBetween(points, landedAt, landedAt + 0.1);
  return after.length >= 5 && median(sizes(after)) <= ON_PITCH;
}

// フォール（尾音下滑）
function isFall(note, points, following) {
  if (note.e - note.s < 0.3) {
    return false;
  }
  // 後面馬上接下一個音的話，往下只是換到下一個音，不算
  if (following !== null && following.s - note.e < 0.25) {
    return false;
  }
  const middle = pointsBetween(points, note.s + 0.1, note.e - 0.2);
  const tail = pointsBetween(points, note.e - 0.2, Infinity);
  if (middle.length < 5 || tail.length < 5) {
    return false;
  }
  // 中間要在音上
  if (median(sizes(middle)) > ON_PITCH) {
    return false;
  }
  // 最後往下掉
  const last = (tail[tail.length - 1].d + tail[tail.length - 2].d + tail[tail.length - 3].d) / 3;
  return last <= -FALL_DROP;
}

// こぶし（轉音）
function isKobushi(note, points) {
  if (note.e - note.s < 0.4) {
    return false;
  }
  const inner = pointsBetween(points, note.s + 0.1, note.e - 0.1);
  for (let i = 1; i < inner.length - 1; i++) {
    const size = Math.abs(inner[i].d);
    // 要拐得夠大，而且是附近最大的那一點
    if (size < KOBUSHI_SIZE || size < Math.abs(inner[i - 1].d) || size < Math.abs(inner[i + 1].d)) {
      continue;
    }
    // 拐之前、拐之後都要在音上
    const t = inner[i].t;
    const before = sizes(pointsBetween(inner, t - 0.15, t - 0.08));
    const after = sizes(pointsBetween(inner, t + 0.08, t + 0.15));
    if (before.length === 0 || after.length === 0) {
      continue;
    }
    if (Math.min(...before) > ON_PITCH || Math.min(...after) > ON_PITCH) {
      continue;
    }
    // 離開音的時間要很短（很快就回來）
    const away = [];
    for (const point of pointsBetween(inner, t - KOBUSHI_WIDTH, t + KOBUSHI_WIDTH)) {
      if (Math.abs(point.d) > ON_PITCH) {
        away.push(point.t);
      }
    }
    if (away.length > 0 && Math.max(...away) - Math.min(...away) <= KOBUSHI_WIDTH) {
      return true;
    }
  }
  return false;
}

// 數一數整首歌的技巧次數（notes 是評分器裡全部的音符，照時間排好）
export function countTechniques(notes) {
  const result = { scoop: 0, kobushi: 0, fall: 0 };
  for (let i = 0; i < notes.length; i++) {
    const note = notes[i];
    // 只算唱對的音符（跳過的、MISS 的不算；講話的地方不看音高，也不算）
    if (note.skipped || note.free || note.grade === '' || note.grade === 'MISS') {
      continue;
    }
    const points = cleanPoints(note);
    if (points.length === 0) {
      continue;
    }
    // 前一個、後一個音符（判斷是不是旋律本身的上下）
    let previous = null;
    if (i > 0) {
      previous = notes[i - 1];
    }
    let following = null;
    if (i + 1 < notes.length) {
      following = notes[i + 1];
    }
    if (isScoop(note, points, previous)) {
      result.scoop++;
    }
    if (isKobushi(note, points)) {
      result.kobushi++;
    }
    if (isFall(note, points, following)) {
      result.fall++;
    }
  }
  return result;
}

// 技巧加分：每個技巧 0.2 分，最多 3 分
export function techniqueBonus(techniques) {
  const total = techniques.scoop + techniques.kobushi + techniques.fall;
  return Math.min(MAX_BONUS, total * POINTS_EACH);
}
