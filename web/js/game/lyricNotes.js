// 哪些音符要評分：**只有句子在唱的時候**（原則：一句歌詞的時間裡，原唱有在唱，就有評分條）
//
// 每一句從幾秒唱到幾秒，是字幕程式算好的（server\lyrics_builder.py；「歌詞時間」選照歌詞檔或自動對齊）。
// 音符只留在這些時間裡面的部分，超出去的剪掉，所以前奏、間奏、MV 劇情（說話、引擎聲…）不會有評分條。
// 句子裡每個字幾秒只管字的填色，不管有沒有評分條：字的時間算錯，評分條也不會少
//   （算錯的地方會有一小段「評分條在跑、字還沒填色」）。
// 句子的時間不對的話，評分條也會跟著不對：到「編輯歌詞」改，或到「修譜」修評分條。
// 句尾很小聲的聲音（回音、換氣、子音尾巴，例如「fears」最後的 s）：
//   照你的設定挑出來的段落在 lyrics.quiet（要先經過 quietParts.js 的 applyQuietSetting），音符落在那裡面的部分也剪掉
// 剪剩的一小段短於 SHORTEST 就不要（太短的碎音）
// 沒有時間軸歌詞的歌：沒辦法知道哪裡是歌詞，整首都算。
// （server\game_bars.py 是這個檔案的 Python 版，健檢工具用；改這裡的話那邊也要改）

export const SHORTEST = 0.15;    // 剪剩的一小段短於這個就不要（跟 server\pitch_analyzer.py 的 MIN_NOTE 一樣：太短的碎音）

// 有字要唱的句子（只有標點符號的不算）
function hasSungWord(line) {
  for (const token of line.tokens || []) {
    if (token.syl > 0) {
      return true;
    }
  }
  return false;
}

// 每一句的時間 [開始, 結束]，重疊、連在一起的合成一段（兩句一起唱的時候會重疊）
// 評分條、補評分條（twoEars.js、talkBars.js）都用這個時間
export function lineRanges(lines) {
  const ranges = [];
  for (const line of lines) {
    if (hasSungWord(line) && line.end > line.start) {
      ranges.push([line.start, line.end]);
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

// 只留落在句子的時間裡的部分
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
  const ranges = lineRanges(lyrics.lines);
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
