// 一句最後一條評分條結束了，這一句就算唱完：字幕不再繼續填色。
//
// 字幕和評分條要同一個時間。評分條會照設定清掉小聲的聲音（quietParts.js），
// 清完之後一句的最後面可能沒有評分條了（殘留的和聲、回音、換氣），字卻還在慢慢填。
// 這裡把每一句的結束時間提早到「這一句裡最後一條會顯示的評分條結束」的時候：
//   - 超過那個時間的字跟著提早結束
//   - 字開始的時間不動（最後一個字如果在最後一條評分條之後才開始，就在它開始的時候一下子填滿）
//   - 整句都沒有評分條的不動
// 你修過譜的歌不用這個：照歌詞原本的時間。
// （server\game_bars.py 的 end_lines_at_last_bar 是這個的 Python 版，健檢工具用；改這裡那邊也要改）

import { isUnheardNote } from './scorer.js';

// 這一句裡最後一條會顯示的評分條結束的時間（沒有評分條回傳 null）
//   瀏覽器的耳朵聽不太到原唱的音不會顯示（scorer.js），不算；講話的評分條（f = 1）會顯示，要算
function lastBarEnd(line, bars, heard) {
  let last = null;
  for (const bar of bars) {
    if (bar.e <= line.start || bar.s >= line.end) {
      continue;
    }
    if (bar.f !== 1 && isUnheardNote(heard, bar.s, bar.e)) {
      continue;
    }
    if (last === null || bar.e > last) {
      last = bar.e;
    }
  }
  return last;
}

// 這一句提早在 time 結束：超過的字也跟著提早結束（字開始的時間不動）
function endLineAfter(line, time) {
  const tokens = [];
  let lastStart = line.start;   // 最後一個字開始的時間：句子不能在它之前就結束
  for (const token of line.tokens || []) {
    const copy = Object.assign({}, token);
    if (copy.end > time) {
      copy.end = Math.max(copy.start, time);
    }
    if (copy.syl > 0 && copy.start > lastStart) {
      lastStart = copy.start;
    }
    tokens.push(copy);
  }
  // 句子至少留 0.5 秒，字幕才不會一閃就不見
  const end = Math.min(line.end, Math.max(line.start + 0.5, time, lastStart));
  return Object.assign({}, line, { end: end, tokens: tokens });
}

// bars：排好的評分條；heard：pitch.heard。回傳整理好的歌詞（不改原本的）
export function endLinesAtLastBar(lyrics, bars, heard) {
  if (!lyrics || !lyrics.synced || !lyrics.lines || !bars || bars.length === 0) {
    return lyrics;
  }
  const lines = [];
  for (const line of lyrics.lines) {
    const last = lastBarEnd(line, bars, heard);
    if (last === null || last >= line.end) {
      lines.push(line);
    } else {
      lines.push(endLineAfter(line, last));
    }
  }
  return Object.assign({}, lyrics, { lines: lines });
}
