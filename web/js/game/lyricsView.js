// 卡拉 OK 字幕：上下兩行交替顯示，唱到哪裡字就變色到哪裡。
// 每個字下面可以顯示羅馬音，日文漢字上面可以顯示假名。
//
// 變色的做法（跟 KTV 一樣）：每個詞有兩層一模一樣的字疊在一起
//   底層（tok-base）：白字黑邊 → 還沒唱
//   上層（tok-over）：彩色字黑邊 → 唱到的部分，從左邊慢慢露出來（--fill 從 0% 到 100%）
// 對唱：整句加上 singer-1（男）、singer-2（女）、singer-3（合）的 class，上層換顏色

import { t } from '../i18n.js';
import { escapeHtml } from '../ui.js';

const LEAD = 0.1;          // 字幕填色稍微走在歌聲前面 0.1 秒（跟 KTV 一樣），看起來才不會慢一拍
const KEEP_AFTER = 0.2;    // 一句唱完（填完色）之後再留 0.2 秒，才讓位置給下一句
const COUNTDOWN_GAP = 4;   // 前面空了這麼多秒以上（前奏、間奏）的句子，開始前顯示 ●●●● 倒數
const COUNTDOWN_DOTS = 4;  // 倒數幾個點：開始前 4 秒出現 4 個點，每秒少一個

// 一個詞的內容（有假名的話放在 ruby 裡）
function partsHtml(parts, showRuby) {
  let html = '';
  for (const part of parts) {
    if (part.ruby && showRuby) {
      html += '<ruby>' + escapeHtml(part.text) + '<rt>' + escapeHtml(part.ruby) + '</rt></ruby>';
    } else {
      html += escapeHtml(part.text);
    }
  }
  return html;
}

// 一個會變色的詞：底層＋上層
// row：'main'（原文）或 'roma'（下面那行羅馬拼音）；填色時每一拍的寬度兩行不一樣（見 fillPercent）
function tokenHtml(index, inner, row) {
  return '<span class="tok" data-index="' + index + '" data-row="' + row + '">' +
    '<span class="tok-base">' + inner + '</span>' +
    '<span class="tok-over" aria-hidden="true">' + inner + '</span>' +
    '</span>';
}

// 一句歌詞的 HTML（原文一行 + 羅馬音一行）
// options 就是使用者設定：
//   日文：showRuby（漢字上方的假名）、showRoma（下方的羅馬音）
//   中文：chineseStyle = 'zhuyin'（上方注音）/ 'pinyin'（下方拼音）/ 'none'（都不顯示）
export function lineHtml(line, options) {
  const isChinese = line.lang === 'zh';
  let showRuby = options.showRuby;
  let showRoma = options.showRoma;
  if (isChinese) {
    showRuby = options.chineseStyle === 'zhuyin';
    showRoma = options.chineseStyle === 'pinyin';
  }

  let main = '';
  let roma = '';
  let hasRoma = false;
  for (let i = 0; i < line.tokens.length; i++) {
    const token = line.tokens[i];
    if (token.space && i > 0) {
      main += ' ';
    }

    // 中文要顯示注音的話，把注音放在字的上方
    let parts = token.parts;
    if (isChinese && token.zhuyin) {
      parts = [{ text: token.text, ruby: token.zhuyin }];
    }
    main += tokenHtml(i, partsHtml(parts, showRuby), 'main');

    if (token.roma) {
      hasRoma = true;
      if (i > 0 && !token.join) {
        roma += ' ';
      }
      roma += tokenHtml(i, escapeHtml(token.roma), 'roma');
    }
  }
  // 加上語言標記，瀏覽器才會用對的字型（日文漢字和中文漢字長得不太一樣）
  let langCode = 'zh-Hant';
  if (line.lang === 'ja') {
    langCode = 'ja';
  } else if (line.lang === 'ko') {
    langCode = 'ko';
  } else if (line.lang === 'other') {
    langCode = 'en';
  }
  // 對唱：這一句是誰唱的（0 = 沒有標記，用預設顏色）
  const singerClass = ' singer-' + (line.singer || 0);
  let html = '<div class="lyric-main' + singerClass + '" lang="' + langCode + '">' + main + '</div>';
  if (showRoma && hasRoma) {
    html += '<div class="lyric-roma' + singerClass + '">' + roma + '</div>';
  }
  return html;
}

export class LyricsView {
  constructor(container, lyrics, options) {
    this.container = container;
    this.lines = [];
    if (lyrics && lyrics.synced) {
      this.lines = lyrics.lines;
    }
    this.options = options;   // 使用者設定（要不要顯示假名、羅馬音、注音…）

    container.innerHTML =
      '<div class="lyric-slot slot-top"><div class="countdown"></div><div class="lyric-content"></div></div>' +
      '<div class="lyric-slot slot-bottom"><div class="countdown"></div><div class="lyric-content"></div></div>';
    this.slots = container.querySelectorAll('.lyric-slot');
    this.slotLine = [-1, -1];   // 每個位置現在放第幾句

    if (this.lines.length === 0) {
      let message = t('（這首歌還沒有歌詞，可以到「編輯歌詞」加入）');
      if (lyrics && !lyrics.synced) {
        message = t('（歌詞沒有時間軸，請到「編輯歌詞」用點按同步）');
      }
      this.slots[0].querySelector('.lyric-content').innerHTML = '<div class="lyric-empty">' + message + '</div>';
    }
  }

  // 換了顯示設定（例如唱到一半在設定裡打開假名）：下一個畫面重新畫字幕
  setOptions(options) {
    this.options = options;
    this.slotLine = [-1, -1];
  }

  // 找出「現在這一句」：還沒唱完（還沒填完色）的第一句。
  // 一句要填完色、再留 KEEP_AFTER 秒，才算唱完，位置才會讓給再下一句
  currentIndex(time) {
    for (let i = 0; i < this.lines.length; i++) {
      if (this.lines[i].end + KEEP_AFTER > time) {
        return i;
      }
    }
    return this.lines.length - 1;
  }

  update(songTime) {
    if (this.lines.length === 0) {
      return;
    }
    const time = songTime + LEAD;
    const current = this.currentIndex(time);
    // 第 current 句和下一句，分別放到上下兩個位置（單數句在下、雙數句在上）
    this.placeLine(current, time);
    if (current + 1 < this.lines.length) {
      this.placeLine(current + 1, time);
    } else {
      this.clearSlot((current + 1) % 2);
    }
  }

  clearSlot(slotIndex) {
    if (this.slotLine[slotIndex] !== -2) {
      this.slotLine[slotIndex] = -2;
      this.slots[slotIndex].querySelector('.lyric-content').innerHTML = '';
      this.slots[slotIndex].querySelector('.countdown').textContent = '';
    }
  }

  placeLine(lineIndex, time) {
    const slotIndex = lineIndex % 2;
    const slot = this.slots[slotIndex];
    const line = this.lines[lineIndex];

    if (this.slotLine[slotIndex] !== lineIndex) {
      this.slotLine[slotIndex] = lineIndex;
      const content = slot.querySelector('.lyric-content');
      content.innerHTML = lineHtml(line, this.options);
      content.classList.remove('appear');
      void content.offsetWidth;  // 讓動畫重新播放
      content.classList.add('appear');
      slot.tokenElements = content.querySelectorAll('.tok');
    }

    // 倒數提示：前奏、間奏（前面空了 COUNTDOWN_GAP 秒以上）的句子，開始前顯示 ●●●●，每秒少一個
    // 第一句的「前一句結束時間」當作 0 秒，所以前奏也會有
    const countdown = slot.querySelector('.countdown');
    let previousEnd = 0;
    if (lineIndex > 0) {
      previousEnd = this.lines[lineIndex - 1].end;
    }
    const waitTime = line.start - time;
    if (line.start - previousEnd > COUNTDOWN_GAP && waitTime > 0 && waitTime <= COUNTDOWN_DOTS) {
      countdown.textContent = '●'.repeat(Math.ceil(waitTime));
    } else {
      countdown.textContent = '';
    }

    // 每個詞的變色進度
    for (const element of slot.tokenElements) {
      const token = line.tokens[Number(element.dataset.index)];
      // 每一拍在畫面上從哪裡開始：原文照讀音（beat_x），羅馬拼音那行照字母（beat_roma_x）
      let positions = token.beat_x;
      if (element.dataset.row === 'roma') {
        positions = token.beat_roma_x;
      }
      const percent = fillPercent(token, time, positions);
      const text = percent.toFixed(1) + '%';
      if (element.lastFill !== text) {
        element.lastFill = text;
        element.style.setProperty('--fill', text);
      }
    }
  }
}

// 一個詞填色到幾 %
//   沒有拍子資料：從開始到結束平均填
//   有拍子資料（token.beats，認音節 MMS 聽出每一拍從幾秒開始，例如「光」hi・ka・ri）：
//     每一拍照自己的時間填（拉長的那一拍就填得慢）
//     positions：畫面上每一拍從哪裡開始（0～1）
//       原文照讀音 token.beat_x（「弱」念よわ 2 拍，各佔「弱」這個字的一半）
//       羅馬拼音照字母 token.beat_roma_x（ka・yo・wa・i → 0、2/7、4/7、6/7）
function fillPercent(token, time, positions) {
  if (time >= token.end) {
    return 100;
  }
  if (time <= token.start) {
    return 0;
  }
  const times = beatTimes(token);
  if (times === null) {
    return (time - token.start) / (token.end - token.start) * 100;
  }
  // 現在唱到第幾拍
  let index = 0;
  for (let k = 0; k < times.length; k++) {
    if (time >= times[k]) {
      index = k;
    }
  }
  let beatEnd = token.end;
  if (index + 1 < times.length) {
    beatEnd = times[index + 1];
  }
  let inside = 1;
  if (beatEnd > times[index]) {
    inside = Math.min(1, (time - times[index]) / (beatEnd - times[index]));
  }
  // 這一拍在畫面上從哪裡到哪裡（沒有資料就每一拍一樣寬）
  let left = index / times.length;
  let right = (index + 1) / times.length;
  if (positions && positions.length === times.length) {
    left = positions[index];
    right = 1;
    if (index + 1 < positions.length) {
      right = positions[index + 1];
    }
  }
  return (left + inside * (right - left)) * 100;
}

// 每一拍開始的時間；MMS 沒把握的拍子（null）在前後兩個有時間的拍子中間平均分
// 沒有拍子資料就回傳 null
function beatTimes(token) {
  const beats = token.beats;
  if (!beats || beats.length < 2) {
    return null;
  }
  const times = beats.slice();
  times[0] = token.start;
  for (let k = 1; k < times.length; k++) {
    if (times[k] !== null) {
      continue;
    }
    // 找後面第一個有時間的拍子（沒有就用這個詞的結束）
    let next = k + 1;
    while (next < times.length && times[next] === null) {
      next++;
    }
    let nextTime = token.end;
    if (next < times.length) {
      nextTime = times[next];
    }
    const previousTime = times[k - 1];
    times[k] = previousTime + (nextTime - previousTime) / (next - (k - 1));
  }
  return times;
}
