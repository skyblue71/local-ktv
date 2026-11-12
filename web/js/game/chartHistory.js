// 修譜的「復原／重做」：每改一步之前，把那時候的樣子記下來
//   復原 = 回到那一步之前的樣子
//   重做 = 把剛剛復原的那一步再做回來
//   復原之後又改了新的東西：原本可以重做的那幾步就沒有了
// 「樣子」裡面放什麼由用的人決定（修譜頁放的是評分條和你調過的字），這裡只管一步一步記

const HISTORY_LIMIT = 100;   // 最多可以復原幾步

export class ChartHistory {
  constructor() {
    this.before = [];   // 可以復原的：每一步之前的樣子，最後面是最近的一步
    this.after = [];    // 可以重做的：最後面是最近復原的那一步
  }

  // 要改了：記下改之前的樣子
  record(state) {
    this.before.push(state);
    if (this.before.length > HISTORY_LIMIT) {
      this.before.shift();
    }
    this.after = [];
  }

  // 記下來之後結果沒改成（例如沒存到）：那一筆不要
  drop(state) {
    const index = this.before.indexOf(state);
    if (index >= 0) {
      this.before.splice(index, 1);
    }
  }

  canUndo() {
    return this.before.length > 0;
  }

  canRedo() {
    return this.after.length > 0;
  }

  // 復原：current = 現在的樣子（留給「重做」用）。回傳要換回去的樣子；沒有可以復原的回傳 null
  undo(current) {
    if (this.before.length === 0) {
      return null;
    }
    this.after.push(current);
    return this.before.pop();
  }

  // 重做：current = 現在的樣子（留給「復原」用）。回傳要換過去的樣子；沒有可以重做的回傳 null
  redo(current) {
    if (this.after.length === 0) {
      return null;
    }
    this.before.push(current);
    return this.after.pop();
  }
}
