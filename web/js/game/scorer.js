// 評分器：一位歌手一個。
// 每收到一筆「你唱的音高」，就跟「這個時間該唱的音符」比較，累積分數。
//
// 未來要共唱：每個人建立自己的 new Scorer(...)，分開計分就好。

import { median } from './scoreMath.js';

const TOLERANCE = 0.1;      // 時間容許誤差（秒）：早一點、晚一點開口都還算
const EDGE_FORGIVE = 0.06;  // 每個音符頭尾的轉音不算（秒）：換音的瞬間本來就不會剛好在音上
export const CONTOUR_HOP = 0.01;   // 原唱音高曲線：每 0.01 秒一格
const TRACE_SMOOTH = 7;     // 畫線用：取最近 7 筆音高（約 0.07 秒）的中位數，線才不會抖來抖去（評分不受影響）
// 畫線用的八度（只影響畫面，評分不受影響）：
const TRACE_LOOKAHEAD = 1;    // 兩個音中間的空檔，下一個音 1 秒內就到的話，線先跟它比
const OCTAVE_SWITCH = 8.5;    // 線跟評分條差 8.5 個半音以上（快一個八度）才把整條線換八度；8 個半音以內照實畫
const OCTAVE_ERROR = 10;      // 跟最近幾筆的多數差 10 個半音以上，才當成偵測器聽錯八度（一般的大跳音照實畫）
const OCTAVE_CLOSE = 2;       // 而且要剛好差「幾個八度 ± 2 個半音」才算（差 19 個半音那種第 3 倍音的錯，不硬摺成怪的值）
const VOTE_WINDOW = 15;       // 多數決看最近 15 筆「原始聽到的值」（約 0.15 秒）：真的唱在那裡的音很快就會變多數
const TRUST_FIRST = 3;        // 剛開口的前 3 筆照實收，之後才用多數決擋聽錯八度的值
// 瀏覽器的耳朵連原唱都聽不太到的音（聽得到的時間不到 30%）：不顯示、不計分
// 裁判聽不到原唱唱這個音，就不拿它來評分（多半是句尾很小聲、帶氣音的短音）
const UNHEARD_LIMIT = 0.3;

// 難度：[完全正確的誤差, 零分的誤差]（單位：半音）
const DIFFICULTY = {
  easy: [0.75, 2.0],
  normal: [0.5, 1.5],
  hard: [0.3, 1.0],
};

// 等級的門檻（這個音符唱對的比例）
const GRADES = [
  { name: 'PERFECT', min: 0.8 },
  { name: 'GREAT', min: 0.6 },
  { name: 'GOOD', min: 0.35 },
  { name: 'MISS', min: 0 },
];

// 差幾個半音 → 換算到最近的八度（-6～+6）。擋偵測器聽錯八度用（跟「八度都算對」的設定無關）
function nearestOctave(diff) {
  return diff - 12 * Math.round(diff / 12);
}

// start ~ end 之間，這份原唱音高（每 0.01 秒一格）有幾格「有聲音」
function countVoiced(reference, start, end) {
  let count = 0;
  const first = Math.max(0, Math.round(start / CONTOUR_HOP));
  const last = Math.min(reference.length, Math.round(end / CONTOUR_HOP));
  for (let i = first; i < last; i++) {
    if (reference[i] !== 0) {
      count++;
    }
  }
  return count;
}

// 瀏覽器的耳朵是不是連原唱都聽不太到這個音（聽得到的時間 < UNHEARD_LIMIT）→ 不顯示、不計分
// （修譜頁也用這個，修譜頁看到的評分條才會跟唱歌時一樣）
export function isUnheardNote(heard, start, end) {
  if (!heard) {
    return false;   // 舊的歌沒有 heard：照常計分
  }
  const totalFrames = Math.max(1, Math.round((end - start) / CONTOUR_HOP));
  return countVoiced(heard, start, end) / totalFrames < UNHEARD_LIMIT;
}

export class Scorer {
  // notes：音符清單 [{s, e, p}]，options：{ difficulty, octaveFree }
  // 原唱的音高（每 0.01 秒一格，單位 0.1 半音，0 = 沒在唱），兩個都可以不給：
  //   contour：AI（CREPE）聽到的原唱
  //   heard  ：「瀏覽器的耳朵」（跟唱歌時一樣的 YIN）聽到的原唱
  // 音準會跟「音符」「contour」「heard」三個比，取最好的：
  //   跟著原唱的滑音、轉音唱也算對；測試模式（原唱自己唱）也不會被另一隻耳朵挑毛病
  // 你在「修譜」畫的或改過的音（note.u = 1）：你畫的就算——
  //   不會因為 AI 聽不到而拿掉、只照你畫的音高比、整個音的長度都要唱
  // 講話的地方補的評分條（note.f = 1，talkBars.js）：只看你有沒有出聲，不看音高
  constructor(notes, options, contour, heard) {
    this.difficulty = DIFFICULTY[options.difficulty] || DIFFICULTY.normal;
    this.octaveFree = options.octaveFree;
    this.contour = contour || null;
    this.heard = heard || null;

    this.notes = [];
    this.hiddenCount = 0;   // 因為瀏覽器聽不到原唱而拿掉的音符數
    for (const note of notes) {
      const manual = note.u === 1;
      const free = note.f === 1;
      if (!manual && !free && isUnheardNote(this.heard, note.s, note.e)) {
        this.hiddenCount++;
        continue;
      }
      let needed = this.neededTime(note.s, note.e);
      if (manual) {
        needed = this.fullNeededTime(note.s, note.e);
      }
      this.notes.push({
        s: note.s,
        e: note.e,
        p: note.p,
        manual: manual,  // 你在修譜畫的或改過的
        free: free,      // 講話的地方：只看有沒有出聲，不看音高
        needed: needed,  // 要唱對多久才算滿分
        hit: 0,          // 唱對的時間（秒，加權）
        sung: 0,         // 有出聲的時間
        firstHit: null,  // 第一次唱對的時間（看節奏用）
        samples: [],     // 每一格的音高差（看穩定度、顫音用）
        loudness: 0,     // 音量加總
        judged: false,
        grade: '',
        ratio: 0,
        skipped: false,  // 跳過的不計分（例如拖動進度條）
      });
    }

    this.cursor = 0;
    this.combo = 0;
    this.maxCombo = 0;
    this.trace = [];      // 最近幾秒你唱的音高（畫線用）
    this.recent = [];     // 最近幾筆音高（畫線平滑用）
    this.votes = [];      // 最近幾筆「原始聽到的」音高（判斷偵測器有沒有聽錯八度用）
    this.events = [];     // 等級提示（PERFECT 等）
    this.lastTime = null;
    this.lastPitch = 64;
    this.displayShift = 0;  // 畫線用：整條線移了幾個半音（換八度：0、-12、+12…）
    this.lastMiddle = null; // 畫線用：上一筆的中位數（看有沒有一下子跳一個八度）
    this.lastShown = null;  // 畫線用：上一筆畫出來的音高
  }

  // 依音高誤差算出 0~1 的準確度
  accuracyOf(error) {
    const full = this.difficulty[0];
    const zero = this.difficulty[1];
    if (error <= full) {
      return 1;
    }
    if (error >= zero) {
      return 0;
    }
    return 1 - (error - full) / (zero - full);
  }

  // 差了幾個八度都沒關係（有開「高八度、低八度都算對」的話）：換算到最接近的那一個
  foldOctave(diff) {
    if (this.octaveFree) {
      return diff - 12 * Math.round(diff / 12);
    }
    return diff;
  }

  // 跟某一份原唱音高（contour 或 heard）差多少半音；那個時間原唱沒聲音就回傳 null
  differenceTo(reference, time, midi) {
    if (reference === null) {
      return null;
    }
    const index = Math.round(time / CONTOUR_HOP);
    if (index < 0 || index >= reference.length || reference[index] === 0) {
      return null;
    }
    return this.foldOctave(midi - reference[index] / 10);
  }

  // 跟原唱差多少半音：contour、heard 兩份裡比較接近的那一個（都沒有就回傳 null）
  contourDiff(time, midi) {
    const toContour = this.differenceTo(this.contour, time, midi);
    const toHeard = this.differenceTo(this.heard, time, midi);
    if (toContour === null) {
      return toHeard;
    }
    if (toHeard === null) {
      return toContour;
    }
    if (Math.abs(toHeard) < Math.abs(toContour)) {
      return toHeard;
    }
    return toContour;
  }

  // 要唱對多久才算滿分：只算「原唱真的有發聲」的時間（子音、氣音的地方不要求）
  //   先用瀏覽器的耳朵（heard），沒有的話用 AI 的（contour），都沒有就用音符長度
  //   再乘 0.9、扣掉頭尾轉音，但至少要一半
  neededTime(start, end) {
    let reference = this.heard;
    if (reference === null) {
      reference = this.contour;
    }
    let length = end - start;
    if (reference !== null) {
      const frames = countVoiced(reference, start, end);
      if (frames > 0) {
        length = frames * CONTOUR_HOP;
      }
    }
    return Math.max(length * 0.9 - EDGE_FORGIVE, length * 0.5);
  }

  // 你畫的音：照你畫的長度（一樣乘 0.9、扣掉頭尾轉音）
  fullNeededTime(start, end) {
    const length = end - start;
    return Math.max(length * 0.9 - EDGE_FORGIVE, length * 0.5);
  }

  // 跟原唱差多少（你畫的音不跟原唱比，只照你畫的音高：回傳 null）
  originalDiff(note, time, midi) {
    if (note.manual) {
      return null;
    }
    return this.contourDiff(time, midi);
  }

  // 這個音符在 time 唱 midi 這個音高的準確度（0~1）
  //   講話的地方（note.free）：有出聲就算對，不看音高
  noteAccuracy(note, time, midi) {
    if (note.free) {
      return 1;
    }
    return this.bestAccuracy(this.foldOctave(midi - note.p), this.originalDiff(note, time, midi));
  }

  // 準確度（0~1）：跟音符比，也跟原唱曲線比，取比較好的
  bestAccuracy(diff, toOriginal) {
    let accuracy = this.accuracyOf(Math.abs(diff));
    if (toOriginal !== null) {
      accuracy = Math.max(accuracy, this.accuracyOf(Math.abs(toOriginal)));
    }
    return accuracy;
  }

  // 畫線時跟哪個音高比：現在的音符 → 1 秒內就到的下一個音符 → 上一個音符
  displayReference(time, note) {
    if (note !== null) {
      this.lastPitch = note.p;
      return note.p;
    }
    const next = this.notes[this.cursor];
    if (next !== undefined && next.s > time && next.s - time <= TRACE_LOOKAHEAD) {
      return next.p;
    }
    return this.lastPitch;
  }

  // 畫線用的音高（只影響畫面，評分用原本的數值）。回傳 { m: 音高, jump: 有沒有換八度 }
  //   1. 跟「最近 VOTE_WINDOW 筆原始值的多數」差 OCTAVE_ERROR 個半音以上，當成偵測器偶爾聽錯八度、接回多數的八度
  //      （投票用原始值，錯的值不會自己延續下去；剛開口的前 TRUST_FIRST 筆照實收）
  //   2. 最近 TRACE_SMOOTH 筆取中位數：偶爾跳一下的錯誤值會被濾掉
  //   3. 跟評分條差 8 個半音以內：照實畫（唱高就畫高，唱比畫面還高時球停在畫面頂端）
  //      差到 OCTAVE_SWITCH（快一個八度）以上：整條線換到評分條的八度
  //      （男生唱女生的歌、或偵測器一整段聽成差一個八度；換的那一下不連線）
  //   （差太少就換的話，唱高 8 個半音會被畫成低 4 個半音，看起來從底部冒出來）
  // 沒出聲就回傳 null，並重新開始收集
  smoothForDisplay(midi, reference) {
    if (midi === null) {
      this.recent = [];
      this.votes = [];
      this.lastMiddle = null;
      this.lastShown = null;
      return null;
    }
    this.votes.push(midi);
    if (this.votes.length > VOTE_WINDOW) {
      this.votes.shift();
    }
    let value = midi;
    if (this.votes.length > TRUST_FIRST) {
      const anchor = median(this.votes);
      const diff = midi - anchor;
      if (Math.abs(diff) >= OCTAVE_ERROR && Math.abs(nearestOctave(diff)) <= OCTAVE_CLOSE) {
        value = anchor + nearestOctave(diff);
      }
    }
    this.recent.push(value);
    if (this.recent.length > TRACE_SMOOTH) {
      this.recent.shift();
    }
    const middle = median(this.recent);
    // 中位數一下子跳了快一個八度（剛把偵測器聽錯的八度修回來、或真的大跳）：重新選一次最靠近評分條的八度
    let recheck = false;
    if (this.lastMiddle !== null && Math.abs(middle - this.lastMiddle) >= OCTAVE_ERROR) {
      recheck = true;
    }
    this.lastMiddle = middle;
    let shown = middle - this.displayShift;
    let jump = false;
    if (this.octaveFree && (recheck || Math.abs(shown - reference) >= OCTAVE_SWITCH)) {
      const newShift = 12 * Math.round((middle - reference) / 12);
      if (newShift !== this.displayShift) {
        this.displayShift = newShift;
        shown = middle - newShift;
        jump = true;   // 整條線換了八度：這一點不跟上一點連起來（不然會畫出一條直線）
      }
    }
    // 畫出來的線一下子跳 OCTAVE_ERROR 個半音以上（多半是偵測器瞬間聽錯）：也不連線，留個小缺口
    if (this.lastShown !== null && Math.abs(shown - this.lastShown) >= OCTAVE_ERROR) {
      jump = true;
    }
    this.lastShown = shown;
    return { m: shown, jump: jump };
  }

  // 找出 time 這個時間點應該唱的音符（找不到回傳 null）
  findNote(time) {
    while (this.cursor < this.notes.length && this.notes[this.cursor].e + TOLERANCE < time) {
      this.cursor++;
    }
    let best = null;
    for (let i = this.cursor; i < this.notes.length && i < this.cursor + 3; i++) {
      const note = this.notes[i];
      if (note.s <= time && time <= note.e) {
        return note;  // 剛好在音符裡面
      }
      if (note.s - TOLERANCE <= time && time <= note.e + TOLERANCE && best === null) {
        best = note;
      }
    }
    return best;
  }

  // 收到一筆音高。midi 是音高編號（null = 沒出聲），loudness 是音量
  addPitch(time, midi, loudness) {
    let step = 0.0107;
    if (this.lastTime !== null) {
      step = time - this.lastTime;
      if (step <= 0 || step > 0.05) {
        step = 0.0107;
      }
    }
    this.lastTime = time;

    const note = this.findNote(time);

    // ---- 評分：用原本的音高（不平滑）----
    if (midi !== null && note !== null && !note.judged) {
      let diff = this.foldOctave(midi - note.p);          // 跟音符差多少
      let toOriginal = this.originalDiff(note, time, midi);   // 跟原唱差多少
      const accuracy = this.noteAccuracy(note, time, midi);
      if (note.free) {
        diff = 0;            // 講話的地方不看音高：不留音高差（穩定度、顫音、技巧都不算它）
        toOriginal = null;
      }
      note.hit += accuracy * step;
      note.sung += step;
      // d：跟音符差多少（看顫音、技巧用）；r：跟原唱差多少（看穩定度用）
      note.samples.push({ t: time, d: diff, r: toOriginal });
      note.loudness += loudness;
      if (accuracy >= 0.5 && note.firstHit === null) {
        note.firstHit = time;
      }
    }

    // ---- 畫線：用平滑過的音高，線才不會抖 ----
    const reference = this.displayReference(time, note);
    const smooth = this.smoothForDisplay(midi, reference);
    let shown = null;
    let jump = false;
    let shownAccuracy = -1;   // -1 = 這裡沒有要唱的音（線畫成淡淡的白色）
    if (smooth !== null) {
      shown = smooth.m;
      jump = smooth.jump;
      if (note !== null) {
        shownAccuracy = this.noteAccuracy(note, time, shown);
      }
    }

    // jump：這一點整條線換了八度，畫的時候不要跟上一點連起來（不然會出現一條直線）
    this.trace.push({ t: time, m: shown, a: shownAccuracy, jump: jump });
    while (this.trace.length > 0 && this.trace[0].t < time - 4) {
      this.trace.shift();
    }
  }

  // 每個畫面更新時呼叫：把已經唱完的音符打分數
  update(time) {
    for (const note of this.notes) {
      if (note.s > time) {
        break;
      }
      if (!note.judged && note.e + TOLERANCE < time) {
        this.judge(note);
      }
    }
  }

  judge(note) {
    note.ratio = Math.min(1, note.hit / note.needed);
    note.judged = true;
    for (const grade of GRADES) {
      if (note.ratio >= grade.min) {
        note.grade = grade.name;
        break;
      }
    }
    if (note.grade === 'MISS') {
      this.combo = 0;
    } else {
      this.combo++;
      if (this.combo > this.maxCombo) {
        this.maxCombo = this.combo;
      }
    }
    this.events.push({ grade: note.grade, time: note.e, pitch: note.p });
    if (this.events.length > 20) {
      this.events.shift();
    }
  }

  // 拖動進度條：之前沒唱的音符不計分，之後的重來
  seek(time) {
    for (const note of this.notes) {
      if (note.s >= time) {
        note.hit = 0;
        note.sung = 0;
        note.firstHit = null;
        note.samples = [];
        note.loudness = 0;
        note.judged = false;
        note.grade = '';
        note.ratio = 0;
        note.skipped = false;
      } else if (!note.judged || note.e > time) {
        note.judged = true;
        note.skipped = true;
        note.grade = '';
      }
    }
    this.cursor = 0;
    this.combo = 0;
    this.trace = [];
    this.events = [];
    this.lastTime = null;
  }

  // 結束時：還沒打分的音符全部打分（提早結束的話，後面的當作跳過）
  finish(time) {
    for (const note of this.notes) {
      if (note.judged) {
        continue;
      }
      if (note.s < time) {
        this.judge(note);
      } else {
        note.judged = true;
        note.skipped = true;
      }
    }
  }

  // 目前的即時分數（0~100，隨著歌曲進行慢慢累積上去）
  liveScore() {
    let total = 0;
    let earned = 0;
    for (const note of this.notes) {
      if (note.skipped) {
        continue;
      }
      const duration = note.e - note.s;
      total += duration;
      if (note.judged) {
        earned += note.ratio * duration;
      }
    }
    if (total === 0) {
      return 0;
    }
    return earned / total * 100;
  }
}
