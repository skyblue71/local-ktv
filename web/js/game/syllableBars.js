// 評分條照字切開（每個字的時間是 server\word_timeline.py 算的，字幕和評分條用同一個時間）
//
// AI 抓到的一個音（一條評分條），如果同一個音高連唱好幾個字，會變成一條長長的評分條。
// 字幕裡每個字（一個字有好幾拍的話，每一拍）從幾秒開始，
// 只要有「下一拍開始」落在一條評分條中間，就從那裡切開，變成一拍一條（像 KTV 一樣）。
// 真正拉長的那一拍，中間沒有新的拍子開始，所以還是一整條。
//   - 切的地方前後留 GAP 秒的空隙，畫面上看得出是兩條
//   - 切出來太短的小段（短於 MIN_PIECE）不切，併在旁邊那段
//   - 你自己修過的譜（chart.json）不切，照你畫的
// （每一句的字都跟評分條同一個時間，所以每一句都切）

const MIN_PIECE = 0.12;   // 切出來每一段至少要有幾秒
const GAP = 0.04;         // 切開的地方留多少秒空隙

// 每個字「每一拍開始的時間」，由小到大
//   一個字有好幾拍（token.beats，例如「光」hi・ka・ri）就每一拍都算；沒有拍子資料就只算字的開始
function syllableStarts(lyrics) {
  const starts = [];
  for (const line of lyrics.lines) {
    for (const token of line.tokens || []) {
      if (token.syl <= 0) {
        continue;
      }
      if (token.beats && token.beats.length > 0) {
        for (const beat of token.beats) {
          // null：MMS 沒把握、落在長音中間的拍子（併回前一拍），不在這裡切
          if (beat !== null) {
            starts.push(beat);
          }
        }
      } else {
        starts.push(token.start);
      }
    }
  }
  starts.sort(function (a, b) {
    return a - b;
  });
  return starts;
}

// 複製一個音符，只換開始、結束時間（音高等其他資料一樣）
function copyNote(note, start, end) {
  const piece = {};
  for (const key in note) {
    piece[key] = note[key];
  }
  piece.s = Math.round(start * 1000) / 1000;
  piece.e = Math.round(end * 1000) / 1000;
  return piece;
}

export function splitAtSyllables(notes, lyrics) {
  if (!lyrics || !lyrics.synced || !lyrics.lines) {
    return notes;
  }
  const starts = syllableStarts(lyrics);
  const result = [];
  for (const note of notes) {
    let pieceStart = note.s;
    for (const start of starts) {
      if (start <= pieceStart + MIN_PIECE) {
        continue;
      }
      if (start >= note.e - MIN_PIECE) {
        break;
      }
      result.push(copyNote(note, pieceStart, start - GAP / 2));
      pieceStart = start + GAP / 2;
    }
    result.push(copyNote(note, pieceStart, note.e));
  }
  return result;
}
