// 兩隻耳朵共用：寫評分條的 AI（CREPE）漏掉、瀏覽器的耳朵聽得到的地方，補上評分條。
//
// 評分條是加歌時 AI 聽原唱寫的。AI 有時候唱到一半沒把握就不寫（例如一個拉長的字的前半段），
// 但「瀏覽器的耳朵」（唱歌時聽你聲音的那一隻，加歌時也聽過一遍原唱，存在 pitch.heard）聽得到。
// 只補「字正在唱」的時間裡的：
//   一段時間 AI 沒寫音符、聲音不是小聲雜音（比這首歌的歌聲小不到你設的「清掉小聲雜音」dB；設 0 = 不管大小聲）、
//   瀏覽器的耳朵一半以上的時間聽得到音高、長到 SHORTEST（最短的評分條）以上、
//   而且緊接著 AI 寫的音符（是唱到一半漏掉的）→ 補一條。
// 音高用瀏覽器聽到的中位數；它常常聽錯八度，所以搬到最接近旁邊那個音符的八度。
// 字的時間不會變（不改 pitch.notes，只在排評分條的時候補），所以不會影響字幕。
// （server\game_bars.py 的 fill_missed 是這個的 Python 版，健檢工具用；改這裡那邊也要改）

import { SHORTEST } from './lyricNotes.js';
import { CONTOUR_HOP } from './scorer.js';

// 回傳補好的音符清單（不改原本的）。lyrics 要先經過 applyQuietSetting
export function fillMissed(notes, pitch, lyrics, quietDb) {
  if (!notes || notes.length === 0 || !pitch || !pitch.heard || !pitch.loudness ||
      !lyrics || !lyrics.synced || !lyrics.lines) {
    return notes;
  }
  const heard = pitch.heard;
  const loudness = pitch.loudness;
  const size = Math.min(heard.length, loudness.length);

  // AI 寫了音符的格子、這首歌的歌聲多大聲（音符每一格音量的中位數）
  const noted = new Array(size).fill(false);
  const sung = [];
  const startsAt = {};   // 第幾格 → 從這一格開始的音符
  const endsAt = {};     // 第幾格 → 到這一格結束的音符
  for (const note of notes) {
    const first = Math.max(0, Math.round(note.s / CONTOUR_HOP));
    const last = Math.min(size, Math.round(note.e / CONTOUR_HOP));
    for (let i = first; i < last; i++) {
      noted[i] = true;
      sung.push(loudness[i]);
    }
    startsAt[first] = note;
    endsAt[last] = note;
  }
  if (sung.length === 0) {
    return notes;
  }
  sung.sort(function (a, b) {
    return a - b;
  });
  let limit = -Infinity;
  if (quietDb > 0) {
    limit = sung[Math.floor(sung.length / 2)] - quietDb;
  }

  // 字正在唱的格子
  const inside = new Array(size).fill(false);
  for (const line of lyrics.lines) {
    for (const token of line.tokens || []) {
      if (token.syl > 0 && token.end > token.start) {
        const first = Math.max(0, Math.round(token.start / CONTOUR_HOP));
        const last = Math.min(size, Math.round(token.end / CONTOUR_HOP));
        for (let i = first; i < last; i++) {
          inside[i] = true;
        }
      }
    }
  }

  const added = [];
  let begin = null;
  for (let i = 0; i <= size; i++) {
    const open = i < size && inside[i] && !noted[i] && loudness[i] >= limit;
    if (open && begin === null) {
      begin = i;
    }
    if (!open && begin !== null) {
      const start = begin;
      const end = i;
      begin = null;
      if ((end - start) * CONTOUR_HOP < SHORTEST) {
        continue;
      }
      const values = [];
      for (let k = start; k < end; k++) {
        if (heard[k] !== 0) {
          values.push(heard[k]);
        }
      }
      if (values.length < (end - start) * 0.5) {
        continue;
      }
      const neighbor = endsAt[start] || startsAt[end];   // 前面（或後面）緊接著的音符
      if (!neighbor) {
        continue;
      }
      values.sort(function (a, b) {
        return a - b;
      });
      let p = Math.round(values[Math.floor(values.length / 2)] / 10);
      p -= 12 * Math.round((p - neighbor.p) / 12);
      added.push({ s: start * CONTOUR_HOP, e: end * CONTOUR_HOP, p: p });
    }
  }
  if (added.length === 0) {
    return notes;
  }
  const sorted = notes.concat(added);
  sorted.sort(function (a, b) {
    return a.s - b.s;
  });
  // 補的那段跟旁邊連著、音高又一樣：接成同一條
  const result = [];
  for (const note of sorted) {
    const last = result[result.length - 1];
    if (last && last.p === note.p && Math.abs(note.s - last.e) < 0.005) {
      result[result.length - 1] = Object.assign({}, last, { e: note.e });
    } else {
      result.push(note);
    }
  }
  return result;
}
