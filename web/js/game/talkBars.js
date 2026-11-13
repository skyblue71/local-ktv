// 講話、rap、喊叫的地方也要有評分條。
//
// 評分條是照音高畫的，講話沒有穩定的音高，AI 就不會寫音符，那一段會空著。
// 原則：有歌詞的地方就是要唱的地方，都要有評分條。
// 這裡把「句子正在唱、卻沒有評分條」的地方補上一種評分條（note.f = 1）：
//   只看你有沒有在那個時間出聲，不看音高（scorer.js）；畫面上是空心、虛線邊的（pitchView.js）。
//   要不要補，由「設定 → 講話也評分」決定（settings.talkBars）。
// 補的條件：
//   - 在句子的時間裡（跟評分條同一個時間，lyricNotes.js 的 lineRanges），而且不在「清掉小聲雜音」清掉的段落裡
//   - 連續長到 SHORTEST（最短的評分條）以上
//   - 瀏覽器的耳朵至少聽得到一點原唱出聲（完全聽不到就沒辦法評，不補）
// 不看分出來的人聲大不大聲：大家一起喊的句子常被 AI 分到伴奏那一軌，人聲軌幾乎沒聲音，但歌詞有就是要唱。
// 畫在哪個高度：瀏覽器的耳朵聽到的音高的中位數，搬到最接近旁邊那條評分條的八度（只是位置，不拿來評分）。
// 補好的再照字切開（syllableBars.js），一拍一條。
// 你修過譜的歌不補：照你畫的。
// （server\game_bars.py 的 add_talk_bars 是這個的 Python 版，健檢工具用；改這裡那邊也要改）

import { SHORTEST, lineRanges } from './lyricNotes.js';
import { CONTOUR_HOP, isUnheardNote } from './scorer.js';
import { splitAtSyllables } from './syllableBars.js';
import { nearOctave } from './twoEars.js';

// 把 start～end 這段時間的格子都設成 value
function mark(grid, start, end, value) {
  const first = Math.max(0, Math.round(start / CONTOUR_HOP));
  const last = Math.min(grid.length, Math.round(end / CONTOUR_HOP));
  for (let i = first; i < last; i++) {
    grid[i] = value;
  }
}

// 離 start～end 這段時間最近的評分條（沒有評分條回傳 null）
function nearestBar(bars, start, end) {
  let best = null;
  let bestGap = Infinity;
  for (const bar of bars) {
    const gap = Math.max(bar.s - end, start - bar.e, 0);
    if (gap < bestGap) {
      best = bar;
      bestGap = gap;
    }
  }
  return best;
}

// bars：排好的評分條；lyrics 要先經過 applyQuietSetting。回傳補好的清單（不改原本的）
export function addTalkBars(bars, pitch, lyrics) {
  if (!pitch || !pitch.heard || !lyrics || !lyrics.synced || !lyrics.lines) {
    return bars;
  }
  const heard = pitch.heard;
  const size = heard.length;

  // 句子正在唱的格子（清掉的小聲段落不算）
  const inside = new Array(size).fill(false);
  for (const range of lineRanges(lyrics.lines)) {
    mark(inside, range[0], range[1], true);
  }
  for (const range of lyrics.quiet || []) {
    mark(inside, range[0], range[1], false);
  }
  // 已經有評分條的格子（瀏覽器聽不到原唱的那些不會顯示，不算）
  const shown = [];
  const covered = new Array(size).fill(false);
  for (const bar of bars) {
    if (!isUnheardNote(heard, bar.s, bar.e)) {
      shown.push(bar);
      mark(covered, bar.s, bar.e, true);
    }
  }

  const added = [];
  let begin = null;
  for (let i = 0; i <= size; i++) {
    const open = i < size && inside[i] && !covered[i];
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
      if (values.length === 0) {
        continue;
      }
      values.sort(function (a, b) {
        return a - b;
      });
      let p = Math.round(values[Math.floor(values.length / 2)] / 10);
      const neighbor = nearestBar(shown, start * CONTOUR_HOP, end * CONTOUR_HOP);
      if (neighbor) {
        p = nearOctave(p, neighbor.p);
      }
      added.push({ s: start * CONTOUR_HOP, e: end * CONTOUR_HOP, p: p, f: 1 });
    }
  }
  if (added.length === 0) {
    return bars;
  }
  const result = bars.concat(splitAtSyllables(added, lyrics));
  result.sort(function (a, b) {
    return a.s - b.s;
  });
  return result;
}
