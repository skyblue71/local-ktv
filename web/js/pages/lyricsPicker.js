// 歌詞清單：「加入歌曲」和「編輯歌詞」用同一個，樣子、排法、試聽都一樣
//   有自己的「歌名、歌手」搜尋欄和搜尋鍵（按 Enter 也可以）
//   每一份是一列，**點那一列就是選它**（左邊打勾），不用另外按按鈕；鍵盤 Enter、空白鍵也可以
//   1. 搜到後先照長度排（lyricsResults.js）；還沒有歌的時候（加歌、還沒按加入）先幫你選好最可能對的
//   2. 有歌、而且處理好了（setSong，「編輯歌詞」才有）：每一份都拿去跟這首歌的歌聲比（伺服器 lyrics/match），
//      標出「時間準／可能不準」、最準的排前面，有時間的右邊有 ▶ 可以試聽
//      加歌時還沒有歌聲，所以只照長度排、不能試聽
//   3. 有歌之後點一列 = 馬上換成這份（onChoose 存檔）；
//      歌名或歌手是空白的，用這份歌詞上的補上（songNames.js）
//
// 用法：
//   const picker = new LyricsPicker(區塊, {
//     getQuery:     function () { return { title, artist, duration }; }   搜尋欄空白時用這個
//     currentLrc:   function () { return 現在用的歌詞文字; }   還沒有歌（加歌、還沒按加入）回傳 null
//     onChoose:     async function (item) { 存檔，成功回傳 true }   有歌之後點一列（加歌時用不到，可以不給）
//     confirmChoose: function (inList) { 回傳 true = 可以換 }   換之前問一下（可以不給）；
//                    inList = 現在用的歌詞在不在清單裡（不在 = 可能是你自己改過的）
//     onSongChange: function (song) { }   補了歌名、歌手之後（可以不給）
//     beforeListen: function () { }       按 ▶ 試聽之前（可以不給，例如先停掉點按同步）
//     allowNone:    true = 清單最後多一列「不用歌詞」（加歌、還沒按加入時才有）
//     showLyrics:   true = 清單下面多一塊，列出選好的那一份歌詞的每一句（加歌時用；「編輯歌詞」頁自己有預覽）
//   });
//   picker.followSong(歌名, 歌手)   歌曲名稱改了：搜尋欄還沒自己打過字的話，跟著換
//   picker.reset()                 清掉結果和搜尋欄
//   picker.search()                搜尋
//   picker.finishSearch()          等目前的搜尋做完；還沒搜過就現在搜
//   picker.chosenItem()            選好的那一筆（沒選 = null）
//   picker.setSong(song)           歌處理好了：開始比對、可以試聽
//   picker.updateChosen()          歌詞在別的地方存了（例如手動編輯）：重新標「✓ 已選」
//   picker.stopListen()            停止試聽
//   picker.destroy()               不用了（關掉對話方塊、離開頁面）

import * as api from '../api.js';
import { t } from '../i18n.js';
import { icon } from '../icons.js';
import { escapeHtml, formatTime, helpTip } from '../ui.js';
import { LyricsListen } from './lyricsListen.js';
import {
  checkDetail, checkProblem, chip, choiceRowHtml, isRecommended, lyricLines, resultsHtml, sortByMatch, sortResults,
} from './lyricsResults.js';
import { changedNames } from './songNames.js';

const LATER_TIP = t('沒有歌詞也可以先加入，之後到「編輯歌詞」再找');
const SEARCH_TIP = t('試試看：只打歌名、換成原文歌名（日文、英文），') +
  t('或去掉「Official Music Video」這類多餘的字');

// 兩份歌詞文字是不是一樣（換行寫法、前後空白不算）
function sameText(a, b) {
  return a.replace(/\r\n/g, '\n').trim() === b.replace(/\r\n/g, '\n').trim();
}

export class LyricsPicker {
  constructor(area, options) {
    this.area = area;
    this.options = options;
    this.results = [];
    this.chosen = -1;          // 「✓ 已選」的是第幾筆（-1 = 沒有）
    this.searched = false;     // 搜尋過了沒
    this.pending = null;       // 正在進行的搜尋
    this.searchNumber = 0;     // 第幾次搜尋（比較慢回來的舊結果就不要了）
    this.duration = 0;
    this.edited = false;       // 搜尋欄是不是你自己打過字（打過就不再跟著歌曲名稱換）
    this.stale = false;        // 搜尋之後搜尋欄又改了，清單還是舊的
    this.lastQuery = '';       // 上一次搜尋的字（顯示「找不到『…』」用）
    this.song = null;          // 處理好的歌（有了才能比對、試聽）
    this.listen = null;        // ▶ 試聽
    this.matchNote = '';       // 清單上面的一行小字（比對中…、比對失敗）
    this.currentCheck = null;  // 現在用的歌詞跟網路上大部分版本比的結果
    this.saving = false;       // 正在換成選的那一份
    this.saveError = '';
    this.lastPicked = null;    // 最後按「選這個」存好的那一份
    this.destroyed = false;
    this.searching = false;    // 正在搜尋（清單先留著、變淡，等新的結果回來再換）
    this.matching = false;     // 正在跟歌聲比對（比完才把清單放上來）
    this.searchingFor = null;  // 正在搜的字 { title, artist }
    this.searchedFor = null;   // 現在這份清單是搜什麼字找到的（一樣的字不用再搜一次）
    this.shownLyrics = null;   // 「歌詞內容」那一塊現在顯示的是哪一份

    let lyricsBox = '';
    if (options.showLyrics) {
      lyricsBox = '<div class="picker-lyrics hidden" data-role="lyrics"></div>';
    }
    area.innerHTML =
      '<div class="picker-search">' +
      '  <input class="input" data-role="title" placeholder="' + t('歌名') + '" aria-label="' + t('搜尋的歌名') + '">' +
      '  <input class="input" data-role="artist" placeholder="' + t('歌手') + '" aria-label="' + t('搜尋的歌手') + '">' +
      '  <button type="button" class="btn btn-icon btn-primary" data-role="search" title="' + t('搜尋') +
      '" aria-label="' + t('搜尋') + '">' +
      icon('search') + '</button>' +
      '</div>' +
      '<div class="picker-status-row">' +
      '  <div class="picker-status small" data-role="status"></div>' +
      '  <div class="picker-length" data-role="length"></div>' +
      '</div>' +
      '<div class="search-results picker-results" data-role="results" role="radiogroup" aria-label="' + t('歌詞') + '"></div>' +
      lyricsBox;

    const picker = this;
    this.part('search').addEventListener('click', function () {
      picker.search(true);
    });
    // 點一列 = 選這一份（點到右邊的試聽鍵、標籤不算）
    const results = this.part('results');
    results.addEventListener('click', function (event) {
      const listenButton = event.target.closest('[data-listen]');
      if (listenButton) {
        picker.startListen(Number(listenButton.dataset.listen), listenButton.closest('.result-item'));
        return;
      }
      if (event.target.closest('.listen-box')) {
        return;   // 試聽框裡的停止鍵、進度條
      }
      const row = event.target.closest('[data-pick]');
      if (row) {
        picker.choose(Number(row.dataset.pick));
      }
    });
    results.addEventListener('keydown', function (event) {
      const row = event.target.closest('[data-pick]');
      if (row && event.target === row && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        picker.choose(Number(row.dataset.pick));
      }
    });
    for (const role of ['title', 'artist']) {
      const input = this.part(role);
      input.addEventListener('input', function () {
        picker.edited = true;
        picker.markStale();
      });
      // 在搜尋欄按 Enter = 按「搜尋」（不要觸發對話方塊的其他按鈕）
      input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          picker.search(true);
        }
      });
    }
  }

  part(role) {
    return this.area.querySelector('[data-role="' + role + '"]');
  }

  setStatus(html) {
    this.part('status').innerHTML = html;
  }

  // 清單右上角：你這首歌有多長（清單每一份都標了長度，放在一起好對照）；還不知道多長就不顯示
  showSongLength() {
    const seconds = this.options.getQuery().duration || 0;
    let html = '';
    if (seconds > 0) {
      html = chip(icon('music') + ' ' + t('你的歌 {time}', { time: formatTime(seconds) }), 'song',
        t('你這首歌的長度'));
    }
    this.part('length').innerHTML = html;
  }

  // 歌曲名稱、歌手改了：搜尋欄還沒自己打過字的話，跟著換成一樣的
  followSong(title, artist) {
    if (this.edited) {
      return;
    }
    const changed = this.part('title').value !== title || this.part('artist').value !== artist;
    this.part('title').value = title;
    this.part('artist').value = artist;
    if (changed) {
      this.markStale();
    }
  }

  // 清掉結果和搜尋欄（例如切換「電腦檔案／YouTube」分頁、換了檔案或網址）
  reset() {
    this.searchNumber++;
    this.pending = null;
    this.results = [];
    this.chosen = -1;
    this.searched = false;
    this.stale = false;
    this.edited = false;
    this.matchNote = '';
    this.currentCheck = null;
    this.searching = false;
    this.matching = false;
    this.searchingFor = null;
    this.searchedFor = null;
    this.part('title').value = '';
    this.part('artist').value = '';
    this.render();
  }

  // 搜尋欄現在的字，跟 words（{ title, artist }，上次搜的字）是不是一樣
  sameWords(words) {
    if (words === null) {
      return false;
    }
    return words.title === this.part('title').value.trim() && words.artist === this.part('artist').value.trim();
  }

  // 搜尋。同樣的字不重複搜（不然會「搜尋中 → 找不到 → 又搜尋中 → 又找不到」閃兩次）：
  //   同樣的字正在搜 → 等那一次就好
  //   同樣的字剛搜過（不管有沒有找到）→ 不再搜；again = true（你自己按搜尋鍵、按 Enter）才會再搜一次
  search(again) {
    if (this.pending !== null && this.sameWords(this.searchingFor)) {
      return this.pending;
    }
    if (!again && this.pending === null && this.sameWords(this.searchedFor)) {
      this.stale = false;
      this.setStatus(this.statusHtml());
      return Promise.resolve();
    }
    this.pending = this.runSearch();
    return this.pending;
  }

  async finishSearch() {
    if (this.pending !== null) {
      await this.pending;
    } else if (!this.searched) {
      await this.search();
    }
  }

  async runSearch() {
    this.searchNumber++;
    const myNumber = this.searchNumber;
    const song = this.options.getQuery();
    this.duration = song.duration || 0;
    this.stale = false;
    this.saveError = '';
    this.showSongLength();

    // 搜尋欄是空的：先用歌曲名稱、歌手
    if (this.part('title').value.trim() === '' && this.part('artist').value.trim() === '') {
      this.part('title').value = song.title;
      this.part('artist').value = song.artist;
    }
    const title = this.part('title').value.trim();
    const artist = this.part('artist').value.trim();
    this.lastQuery = (title + ' ' + artist).trim();

    if (title === '' && artist === '') {
      this.results = [];
      this.chosen = -1;
      this.searched = true;
      this.pending = null;
      this.searchedFor = null;
      this.render();
      let tip = SEARCH_TIP;
      if (this.options.allowNone) {
        tip = LATER_TIP;
      }
      this.setStatus(t('請先打歌名') + helpTip(tip));
      return;
    }

    // 舊的清單先留著、變淡（不先清空：清空再出現會閃一下），新的結果回來再換
    this.stopListen();
    this.searching = true;
    this.matching = false;
    this.searchingFor = { title: title, artist: artist };
    this.part('results').classList.add('busy');
    this.setStatus(t('搜尋歌詞中…'));
    let results = [];
    let failed = '';
    try {
      results = await api.searchLyrics(title, artist);
    } catch (error) {
      failed = error.message;
    }
    if (this.destroyed || myNumber !== this.searchNumber) {
      return;   // 這段時間又搜了一次（或清掉了），這次的結果不要了
    }
    this.searching = false;
    this.searchingFor = null;
    this.searchedFor = null;
    if (failed === '') {
      this.searchedFor = { title: title, artist: artist };
    }

    // 同名的歌可能有很多首：先照長度排
    this.results = sortResults(results, this.duration);
    this.matchNote = '';
    this.currentCheck = null;
    this.pickDefault();
    this.searched = true;
    this.pending = null;

    // 有歌了（「編輯歌詞」頁）：還要拿每一份跟歌聲比，最準的排前面。
    // 等比完再把清單放上來：先照長度排一次、比完又重排一次的話，清單會跳兩次、「推薦」也會換人
    const willMatch = failed === '' && this.song !== null && this.results.length > 0;
    if (!willMatch) {
      this.render();
    }
    if (failed !== '') {
      this.setStatus(t('搜尋失敗：{message}', { message: escapeHtml(failed) }) + helpTip(SEARCH_TIP));
      return;
    }
    if (willMatch) {
      await this.runMatch();
    }
  }

  // 「✓ 已選」標哪一筆：
  //   還沒有歌（加歌、還沒按加入）→ 先幫你選最可能對的（有時間軸、長度差不多）
  //   有歌了 → 現在用的那一份（不在清單裡就不標）
  pickDefault() {
    const current = this.options.currentLrc();
    this.chosen = -1;
    if (current === null) {
      this.lastPicked = null;
      if (this.results.length > 0 && isRecommended(this.results[0], this.duration)) {
        this.chosen = 0;
        this.lastPicked = this.results[0];
      }
      return;
    }
    // 好幾份的字一模一樣時（同一份歌詞放在不同專輯），標你按的那一份
    const preferred = this.results.indexOf(this.lastPicked);
    if (preferred >= 0 && sameText(this.lastPicked.synced || this.lastPicked.plain || '', current)) {
      this.chosen = preferred;
      return;
    }
    for (let i = 0; i < this.results.length; i++) {
      const item = this.results[i];
      const text = item.synced || item.plain || '';
      if (text !== '' && sameText(text, current)) {
        this.chosen = i;
        return;
      }
    }
  }

  // 每一份歌詞跟這首歌的歌聲比對（伺服器 lyrics/match），標出時間準不準，最準的排前面
  //   比對的時候清單先不換（舊的留著、變淡），上面那一行寫「找到 N 份　比對中…」，比完才一次放上來
  async runMatch() {
    const myResults = this.results;
    this.matching = true;
    this.part('results').classList.add('busy');
    this.setStatus(this.statusHtml());
    let answer = null;
    let failed = '';
    try {
      const versions = [];
      for (const item of myResults) {
        versions.push(item.synced || '');
      }
      answer = await api.matchLyrics(this.song.id, versions);
    } catch (error) {
      failed = error.message;
    }
    if (this.destroyed || myResults !== this.results) {
      return;   // 比對的時候又搜尋了一次
    }
    this.matching = false;
    if (answer === null) {
      this.matchNote = '<p class="muted small">' + t('比對失敗') + helpTip(failed + '\n' + t('先照長度排')) + '</p>';
      this.render();
      return;
    }
    for (let i = 0; i < myResults.length; i++) {
      myResults[i].match = answer.results[i];
    }
    this.currentCheck = answer.current;
    sortByMatch(this.results, this.duration);
    this.pickDefault();   // 排過了，「✓ 已選」重新找
    this.matchNote = '';
    this.render();
  }

  // 歌處理好了：可以比對、試聽（已經有搜尋結果的話，現在就比）
  async setSong(song) {
    this.song = song;
    if (this.listen) {
      this.listen.destroy();
    }
    this.listen = new LyricsListen(song);
    this.render();
    if (this.results.length > 0) {
      await this.runMatch();
    }
  }

  // 歌詞在別的地方存了：「你現在的歌詞」那一行是舊的比對結果，拿掉；「✓ 已選」重新找
  updateChosen() {
    this.currentCheck = null;
    this.pickDefault();
    this.render();
  }

  async choose(index) {
    // 還沒有歌（加歌、還沒按加入）：先選好就好，按加入時才送出
    if (this.options.currentLrc() === null) {
      this.chosen = index;
      this.lastPicked = this.results[index] || null;
      this.render();
      return;
    }
    const item = this.results[index];
    if (this.saving || !item || index === this.chosen) {
      return;   // 正在存、或按的是現在用的那一份（再存一次會把整體偏移歸零）
    }
    // 點一下就會換掉，先問一下（例如你自己改過的歌詞會不見、調過的時間會歸零）
    if (this.options.confirmChoose && !this.options.confirmChoose(this.chosen >= 0)) {
      return;
    }
    this.saving = true;
    this.saveError = '';
    this.render();
    let ok = false;
    try {
      ok = await this.options.onChoose(item);
    } catch (error) {
      this.saveError = error.message;
    }
    if (this.destroyed) {
      return;
    }
    if (ok) {
      this.lastPicked = item;
      await this.fillNames(item);
    } else if (this.saveError === '') {
      this.saveError = t('沒有存到');
    }
    this.saving = false;
    this.updateChosen();
  }

  // 歌名或歌手是空白的：用這份歌詞上的補上
  async fillNames(item) {
    const changes = changedNames(this.song, item);
    if (changes === null) {
      return;
    }
    try {
      this.song = await api.updateSong(this.song.id, changes);
      if (this.options.onSongChange) {
        this.options.onSongChange(this.song);
      }
    } catch (error) {
      this.saveError = t('補歌名、歌手失敗：{message}', { message: error.message });
    }
  }

  chosenItem() {
    if (this.chosen < 0 || this.chosen >= this.results.length) {
      return null;
    }
    return this.results[this.chosen];
  }

  // 搜尋之後搜尋欄又改了：提醒要再按搜尋（清單先留著，只改上面那一行）
  markStale() {
    if (!this.searched || this.stale) {
      return;
    }
    this.stale = true;
    this.setStatus(this.statusHtml());
  }

  startListen(index, row) {
    const item = this.results[index];
    if (!item || this.listen === null) {
      return;
    }
    if (this.options.beforeListen) {
      this.options.beforeListen();
    }
    this.listen.start(item.synced, row);
  }

  stopListen() {
    if (this.listen) {
      this.listen.stop();
    }
  }

  destroy() {
    this.destroyed = true;
    this.searchNumber++;
    if (this.listen) {
      this.listen.destroy();
      this.listen = null;
    }
  }

  // 清單上面一行：你現在的歌詞跟網路上大部分版本比（比不了就不顯示）
  //   例如「你現在的歌詞：整首比大部分版本早 6.0 秒」（某支 MV 舊歌詞有兩句時間寫錯，整首早了一句）
  currentHtml() {
    if (!this.currentCheck) {
      return '';
    }
    const problem = checkProblem(this.currentCheck);
    if (problem === '') {
      return '<p class="small current-check ok-text">' + icon('check') + ' ' + t('你現在的歌詞跟大部分版本一樣') + '</p>';
    }
    let tip = t('網路上的歌詞各自對齊這首歌，大部分放的時間跟你的不一樣。');
    const detail = checkDetail(this.currentCheck);
    if (detail !== '') {
      tip += '\n' + detail;
    }
    tip += t('\n換一份「時間準」的，或改這幾句的時間');
    return '<p class="small current-check warn-text">' + icon('warn') + ' ' +
      t('你現在的歌詞{problem}', { problem: escapeHtml(problem) }) + helpTip(tip) + '</p>';
  }

  render() {
    if (this.destroyed) {
      return;
    }
    this.stopListen();   // 清單要重畫了，試聽框也會不見
    const box = this.part('results');
    let html = '';
    if (this.results.length > 0) {
      html = this.matchNote + this.currentHtml();
    }
    html += resultsHtml(this.results, this.duration, this.chosen, this.listen !== null);
    // 加歌時：最後一列「不用歌詞」（一份都沒選 = 選這一列）
    if (this.options.allowNone && this.options.currentLrc() === null && this.searched) {
      html += choiceRowHtml(-1, this.chosen < 0,
        '<div class="result-title">' + t('不用歌詞') + '</div><div class="muted small">' +
        t('之後可以到「編輯歌詞」再找') + '</div>',
        '', 'result-none');
    }
    // 重畫之後捲動的位置要一樣（不然點了下面的一列，清單會跳回最上面，那一列就看不到了）
    const scrolled = box.scrollTop;
    box.innerHTML = html;
    box.scrollTop = scrolled;
    box.classList.toggle('busy', this.saving || this.searching || this.matching);
    this.showChosenLyrics();
    this.showSongLength();
    this.setStatus(this.statusHtml());
  }

  // 清單下面那一塊：選好的那一份歌詞的每一句（options.showLyrics 才有）
  showChosenLyrics() {
    const box = this.part('lyrics');
    if (!box) {
      return;
    }
    const item = this.chosenItem();
    if (item === this.shownLyrics) {
      return;   // 還是同一份：不重畫，捲到哪裡就留在哪裡
    }
    this.shownLyrics = item;
    if (item === null) {
      box.classList.add('hidden');
      box.innerHTML = '';
      return;
    }
    let html = '<div class="picker-lyrics-title small muted">' + t('歌詞內容') + '</div><div class="picker-lyrics-lines">';
    for (const line of lyricLines(item)) {
      let time = '';
      if (line.time !== null) {
        time = formatTime(line.time);
      }
      html += '<div class="picker-lyrics-line"><span class="line-time">' + time + '</span>' +
        '<span>' + escapeHtml(line.text) + '</span></div>';
    }
    box.innerHTML = html + '</div>';
    box.classList.remove('hidden');
  }

  statusHtml() {
    if (this.saving) {
      return t('儲存中…');
    }
    if (this.matching) {
      return '<span class="muted">' + t('找到 {count} 份', { count: this.results.length }) + '　' + t('比對中…') + '</span>';
    }
    const beforeAdd = this.options.currentLrc() === null;
    let text = '';
    if (!this.searched) {
      if (beforeAdd) {
        text = '<span class="muted">' + t('選好歌曲就會自動找') + '</span>';
      }
    } else if (this.results.length === 0) {
      let tip = SEARCH_TIP;
      if (this.options.allowNone) {
        tip += '\n' + LATER_TIP;
      }
      text = t('找不到「{query}」', { query: escapeHtml(this.lastQuery) }) + helpTip(tip);
    } else {
      let tip = t('點一列就換成那一份。按 ▶ 可以先聽聽看，字幕有沒有跟歌聲同時出來\n\n') +
        t('換了會影響：字幕和評分條重做、整首移動歸零。\n') +
        t('不會影響：你修過的譜、裁切。\n你調過的字，句子文字一樣的才留著');
      if (beforeAdd) {
        tip = t('點一列選它。長度打綠勾（跟你的歌一樣長）的通常是對的版本');
      }
      text = '<span class="muted">' + t('找到 {count} 份', { count: this.results.length }) + '</span>' + helpTip(tip);
    }
    if (this.saveError !== '') {
      text += ' <span class="warn-text">' + t('儲存失敗：{message}', { message: escapeHtml(this.saveError) }) + '</span>';
    }
    if (this.stale) {
      text += ' <span class="warn-text">' + t('改了搜尋的字，按搜尋鍵更新') + '</span>';
    }
    return text;
  }
}
