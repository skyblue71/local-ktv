// 修譜的資料：音符清單、現在選了哪一個、復原（Ctrl+Z）
//
// 每個音符 { s: 開始秒數, e: 結束秒數, p: 音高(半音編號), u: 1 }
//   u = 1：你畫的或改過的（唱歌時你畫的就算、只照你畫的音高評分）
//   沒有 u：AI 原本的音，沒動過

const MIN_LENGTH = 0.08;   // 一個音最短幾秒（太短的拖不出來，也按不到）
const HISTORY_LIMIT = 100; // 最多可以復原幾步

function copyNotes(notes) {
  const result = [];
  for (const note of notes) {
    const copy = { s: note.s, e: note.e, p: note.p };
    if (note.u === 1) {
      copy.u = 1;
    }
    result.push(copy);
  }
  return result;
}

// 時間取到 0.01 秒
function roundTime(seconds) {
  return Math.round(seconds * 100) / 100;
}

export class ChartModel {
  constructor(notes) {
    this.load(notes);
  }

  // 換成另一份譜（例如還原 AI 的譜）：復原的紀錄也清掉
  load(notes) {
    this.notes = copyNotes(notes);
    this.sort();
    this.selected = null;
    this.history = [];
  }

  sort() {
    this.notes.sort(function (a, b) {
      return a.s - b.s;
    });
  }

  // 改之前先記下來（復原用）
  remember() {
    this.history.push(copyNotes(this.notes));
    if (this.history.length > HISTORY_LIMIT) {
      this.history.shift();
    }
  }

  // 剛剛記下來、結果沒有改（例如只是點一下選音符）：那一筆不要
  forget() {
    this.history.pop();
  }

  canUndo() {
    return this.history.length > 0;
  }

  undo() {
    if (this.history.length === 0) {
      return false;
    }
    this.notes = this.history.pop();
    this.selected = null;
    return true;
  }

  // 新增一個你畫的音（會自動選起來）
  add(start, end, pitch) {
    const note = { s: roundTime(start), e: roundTime(end), p: pitch, u: 1 };
    this.notes.push(note);
    this.selected = note;
    return note;
  }

  // 刪掉選起來的音
  removeSelected() {
    const index = this.notes.indexOf(this.selected);
    if (index < 0) {
      return false;
    }
    this.notes.splice(index, 1);
    this.selected = null;
    return true;
  }

  // 改時間（start、end 會照順序排好，太短就拉到最短長度）
  setTimes(note, start, end) {
    start = Math.max(0, roundTime(start));
    end = roundTime(end);
    if (end - start < MIN_LENGTH) {
      end = roundTime(start + MIN_LENGTH);
    }
    note.s = start;
    note.e = end;
    note.u = 1;
  }

  setPitch(note, pitch) {
    note.p = pitch;
    note.u = 1;
  }

  isTooShort(note) {
    return note.e - note.s < MIN_LENGTH;
  }

  // 要存檔的資料
  plainNotes() {
    return copyNotes(this.notes);
  }
}

export { MIN_LENGTH };
