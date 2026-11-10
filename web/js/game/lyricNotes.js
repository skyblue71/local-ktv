// 哪些音符要評分：**只有字在唱的時候**（原則：歌詞本來就應該是對的，有歌詞的地方才唱、才評分）
//
// 每個字從幾秒唱到幾秒，是字幕程式算好的（server\word_timeline.py：AI 聽字、照歌聲修正）。
// 音符只留在這些時間裡面的部分，超出去的剪掉，所以：
//   - 前奏、間奏、MV 劇情（說話、引擎聲…）不會有評分條
//   - 不會「有評分條、卻沒有字在填色」，也不會「字都填完了還有評分條」：評分條跟字幕用同一個時間
// 字的時間不對的話，評分條也會跟著不對：到「修譜」拖那個字，或到「編輯歌詞」改。
// 句尾很小聲的聲音（回音、換氣、子音尾巴，例如「fears」最後的 s）：
//   照你的設定挑出來的段落在 lyrics.quiet（要先經過 quietParts.js 的 applyQuietSetting），音符落在那裡面的部分也剪掉
// 剪剩的一小段短於 SHORTEST 就不要（太短的碎音）
// 沒有時間軸歌詞的歌：沒辦法知道哪裡是歌詞，整首都算。
// （server\game_bars.py 是這個檔案的 Python 版，健檢工具用；改這裡的話那邊也要改）

export const SHORTEST = 0.15;    // 剪剩的一小段短於這個就不要（跟 server\pitch_analyzer.py 的 MIN_NOTE 一樣：太短的碎音）

// 每個字的時間 [開始, 結束]（標點符號不算），重疊、連在一起的合成一段（兩句一起唱的時候會重疊）
function wordRanges(lines) {
  const ranges = [];
  for (const line of lines) {
    for (const token of line.tokens || []) {
      if (token.syl > 0 && token.end > token.start) {
        ranges.push([token.start, token.end]);
      }
    }
  }
  ranges.sort(function (a, b) {
    return a[0] - b[0];
  });
  const merged = [];
  for (const range of ranges) {
    const previous = merged[merged.length - 1];
    if (previous && range[0] <= previous[1]) {
      previous[1] = Math.max(previous[1], range[1]);
    } else {
      merged.push([range[0], range[1]]);
    }
  }
  return merged;
}

// 把音符落在「很小聲、不是歌詞」那幾段裡的部分剪掉，回傳剩下的幾段
function cutOutQuiet(note, quiet) {
  let pieces = [note];
  for (const range of quiet) {
    const next = [];
    for (const piece of pieces) {
      if (piece.e <= range[0] || piece.s >= range[1]) {
        next.push(piece);   // 沒碰到
        continue;
      }
      if (piece.s < range[0]) {
        next.push(Object.assign({}, piece, { e: range[0] }));   // 留前面
      }
      if (piece.e > range[1]) {
        next.push(Object.assign({}, piece, { s: range[1] }));   // 留後面
      }
    }
    pieces = next;
  }
  return pieces;
}

// 只留落在字的時間裡的部分
function keepInside(piece, ranges) {
  const result = [];
  for (const range of ranges) {
    const start = Math.max(piece.s, range[0]);
    const end = Math.min(piece.e, range[1]);
    if (end > start) {
      result.push(Object.assign({}, piece, { s: start, e: end }));
    }
  }
  return result;
}

export function notesInLyrics(notes, lyrics) {
  if (!lyrics || !lyrics.synced || !lyrics.lines || lyrics.lines.length === 0) {
    return notes;
  }
  const quiet = lyrics.quiet || [];
  const ranges = wordRanges(lyrics.lines);
  const result = [];
  for (const note of notes) {
    for (const piece of cutOutQuiet(note, quiet)) {
      for (const kept of keepInside(piece, ranges)) {
        // 被剪過、剪剩很短的碎片不要（沒被剪的短音照樣留著）
        const wasCut = kept.s !== note.s || kept.e !== note.e;
        if (wasCut && kept.e - kept.s < SHORTEST) {
          continue;
        }
        result.push(kept);
      }
    }
  }
  return result;
}
