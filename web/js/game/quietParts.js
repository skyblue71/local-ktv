// 清掉小聲雜音：句子頭尾、比歌聲小很多的聲音（回音、換氣、子音的尾巴，例如「fears」最後的 s；第一個字開始前的雜音）
//
// 伺服器只負責「量」：每一段比歌聲小幾 dB，記在 lyrics.quiet（server\lyrics_builder.py）
//   句首的一段：{ s, e, db }
//   句尾的一段：{ s, e, db, line, cut }   line = 第幾句；cut = 清掉這段的話，這一句結束在哪裡
// 這裡照你的設定（設定 → 清掉小聲雜音，settings.quietDb）決定清哪幾段：
//   db 有到你設的數字 → 清掉：不放評分條（lyricNotes.js），這一句的最後一個字也提早填完色
//   設 0 = 都不清
// 唱歌、修譜、試聽都先經過這裡，看到的才會一樣。
//
// 句子「裡面」小聲的那一段時間也清（quietStretches）：字和字中間的回音、換氣被寫成了音符
//   （例如一個字唱完後的回音）。用同一個設定的數字：
//   這一句的歌聲 = 句子裡的音符每一格音量的中位數；連續比它小你設的 dB 以上、
//   而且長到 SHORTEST（最短的評分條）以上的一段 → 不放評分條。
//   只剪那一段時間，不是整條評分條：真的在唱的長音只會少掉變小聲的尾巴。字的填色不變。
//   （server\game_bars.py 的 quiet_stretches 是這個的 Python 版，健檢工具用；改這裡那邊也要改）

import { SHORTEST } from './lyricNotes.js';
import { CONTOUR_HOP } from './scorer.js';

// 中位數（排好後取中間那個）
function medianOf(values) {
  const ordered = values.slice().sort(function (a, b) {
    return a - b;
  });
  return ordered[Math.floor(ordered.length / 2)];
}

// 句子裡面小聲的段落 [[開始, 結束], ...]。pitch：這首歌的音高資料（要有 notes、loudness）
export function quietStretches(lines, pitch, quietDb) {
  const ranges = [];
  if (!(quietDb > 0) || !pitch || !pitch.loudness || pitch.loudness.length === 0) {
    return ranges;
  }
  const loudness = pitch.loudness;
  const notes = pitch.notes || [];
  for (const line of lines) {
    const first = Math.max(0, Math.round(line.start / CONTOUR_HOP));
    const last = Math.min(loudness.length, Math.round(line.end / CONTOUR_HOP));
    const sung = [];
    for (const note of notes) {
      if (note.e <= line.start || note.s >= line.end) {
        continue;
      }
      const noteFirst = Math.max(first, Math.round(note.s / CONTOUR_HOP));
      const noteLast = Math.min(last, Math.round(note.e / CONTOUR_HOP));
      for (let i = noteFirst; i < noteLast; i++) {
        sung.push(loudness[i]);
      }
    }
    if (sung.length === 0) {
      continue;
    }
    const limit = medianOf(sung) - quietDb;
    let start = null;
    for (let i = first; i <= last; i++) {
      const quiet = i < last && loudness[i] <= limit;
      if (quiet && start === null) {
        start = i;
      }
      if (!quiet && start !== null) {
        if ((i - start) * CONTOUR_HOP >= SHORTEST) {
          ranges.push([start * CONTOUR_HOP, i * CONTOUR_HOP]);
        }
        start = null;
      }
    }
  }
  return ranges;
}

// 舊的歌（還沒重新整理過）存的是 [開始, 結束]：那時候已經用 12 dB 挑過了，當作小 12 dB
const OLD_FORMAT_DB = 12;

// 把一段整理成同一種樣子
function readPart(part) {
  if (Array.isArray(part)) {
    return { s: part[0], e: part[1], db: OLD_FORMAT_DB };
  }
  return part;
}

// 回傳照設定整理好的歌詞（不改到原本的）：
//   quiet 只剩要清掉的段落 [[開始, 結束], ...]
//   句尾清掉的話，那一句和裡面的字提早結束
//   pitch 有給的話，句子裡面小聲的段落也清（試聽字幕不用評分條，可以不給）
export function applyQuietSetting(lyrics, quietDb, pitch) {
  if (!lyrics || !lyrics.lines) {
    return lyrics;
  }
  const ranges = [];
  const cutAt = {};   // 第幾句 → 要結束在哪裡
  if (quietDb > 0) {
    for (const raw of lyrics.quiet || []) {
      const part = readPart(raw);
      if (part.db < quietDb) {
        continue;
      }
      ranges.push([part.s, part.e]);
      if (part.line !== undefined && part.cut !== undefined) {
        if (cutAt[part.line] === undefined || part.cut < cutAt[part.line]) {
          cutAt[part.line] = part.cut;
        }
      }
    }
  }

  const lines = [];
  for (let index = 0; index < lyrics.lines.length; index++) {
    const line = lyrics.lines[index];
    if (cutAt[index] === undefined) {
      lines.push(line);
    } else {
      lines.push(endLineAt(line, cutAt[index]));
    }
  }
  for (const range of quietStretches(lines, pitch, quietDb)) {
    ranges.push(range);
  }
  return Object.assign({}, lyrics, { lines: lines, quiet: ranges });
}

// 這一句提早在 time 結束：超過的字也跟著提早
function endLineAt(line, time) {
  const tokens = [];
  for (const token of line.tokens || []) {
    const copy = Object.assign({}, token);
    if (copy.end > time) {
      copy.end = Math.max(copy.start, time);
    }
    if (copy.start > time) {
      copy.start = copy.end;
    }
    tokens.push(copy);
  }
  // 句子至少留 0.5 秒，字幕才不會一閃就不見
  const end = Math.min(line.end, Math.max(line.start + 0.5, time));
  return Object.assign({}, line, { end: end, tokens: tokens });
}
