// 「加入歌曲」對話方塊（寬的，分左右兩邊）：
//   左邊「歌曲」：
//     電腦檔案：選檔案（或拖進來）→ 歌名、歌手（空白的話自動讀）
//     YouTube：貼網址 → 讀取歌名、歌手 → 伺服器下載影片（可以當 MV 背景）
//   右邊「歌詞」：選好歌曲就自動上網找（lyricsPicker.js），點一列選它；不要歌詞就點最下面「不用歌詞」
//     也可以貼自己的歌詞（貼了就用自己的）
// 按「加入」就關掉對話方塊，背景繼續處理；之後想換歌詞、試聽，到「編輯歌詞」（同一個清單）
// 歌名、歌手空白的話，用選的那份歌詞上的補上（songNames.js）

import * as api from '../api.js';
import { t } from '../i18n.js';
import { icon } from '../icons.js';
import { escapeHtml, formatTime, helpTip, openDialog, showToast } from '../ui.js';
import { LyricsPicker } from './lyricsPicker.js';
import { fillNames } from './songNames.js';

export function openAddSongDialog(systemInfo, onDone) {
  const canSeparate = !systemInfo || systemInfo.separator;
  const canYoutube = !systemInfo || systemInfo.youtube;

  let youtubePanel = '<div class="notice">' + t('沒有安裝 yt-dlp') + helpTip(t('執行 setup.bat 安裝')) + '</div>';
  if (canYoutube) {
    youtubePanel =
      '<div class="youtube-row">' +
      '  <input class="input" id="youtube-url" placeholder="' + t('貼上 YouTube 網址') + '">' +
      '  <button type="button" class="btn" id="youtube-read">' + t('讀取') + '</button>' +
      '</div>' +
      '<div class="small muted" id="youtube-status">' +
      '  ' + t('會下載影片當 MV 背景') + helpTip(t('最高 1080p。請只下載你有權利使用的影片')) +
      '</div>';
  }
  let separateNote = helpTip(t('分出伴奏和原唱：評分更準，也可以開導唱'));
  let separateAttribute = 'checked';
  if (!canSeparate) {
    separateNote = '<span class="muted small">' + t('（未安裝）') + '</span>';
    separateAttribute = 'disabled';
  }

  const html =
    '<div class="add-layout">' +
    // ---- 左邊：歌曲 ----
    '  <section class="add-column">' +
    '    <h4 class="column-title">' + icon('music') + ' ' + t('歌曲') + '</h4>' +
    '    <div class="tabs" role="tablist">' +
    '      <button type="button" class="tab active" data-tab="file">' + icon('folder') + ' ' + t('電腦檔案') + '</button>' +
    '      <button type="button" class="tab" data-tab="youtube">' + icon('video') + ' YouTube</button>' +
    '    </div>' +
    '    <div id="file-panel">' +
    '      <div class="drop-zone" id="drop-zone" tabindex="0" role="button">' +
    '        <div class="drop-icon">' + icon('upload') + '</div>' +
    '        <div id="drop-text">' + t('拖進來，或<b>按這裡選</b>') + '</div>' +
    '        <div class="muted small">' + t('mp3、m4a、flac、wav、ogg、mp4') + '</div>' +
    '        <input type="file" id="file-input" accept="audio/*,video/*" hidden>' +
    '      </div>' +
    '    </div>' +
    '    <div id="youtube-panel" class="hidden">' + youtubePanel + '</div>' +
    '    <div class="form-grid">' +
    '      <label for="title-input">' + t('歌名') + '</label>' +
    '      <input class="input" id="title-input" placeholder="' + t('空白就自動讀') + '">' +
    '      <label for="artist-input">' + t('歌手') + '</label>' +
    '      <input class="input" id="artist-input" placeholder="' + t('可以空白') + '">' +
    '      <label for="separate-check">' + t('AI 去人聲') + separateNote + '</label>' +
    '      <div><input type="checkbox" class="switch" id="separate-check" ' + separateAttribute + '></div>' +
    '    </div>' +
    '  </section>' +
    // ---- 右邊：歌詞 ----
    '  <section class="add-column">' +
    '    <h4 class="column-title">' + icon('lyrics') + ' ' + t('歌詞') +
    helpTip(t('從 LRCLIB 網站搜尋（只送出歌名、歌手）')) + '</h4>' +
    '    <div class="lyrics-picker" id="lyrics-picker"></div>' +
    '    <details class="own-lyrics">' +
    '      <summary>' + t('貼上自己的歌詞') + helpTip(t('LRC 格式。貼了就用這份，不用上面搜到的')) + '</summary>' +
    '      <textarea class="input" id="lrc-input" rows="6" placeholder="' + t('[00:12.34]第一句歌詞&#10;[00:18.00]第二句歌詞') + '"></textarea>' +
    '    </details>' +
    '  </section>' +
    '</div>' +
    '<div class="progress hidden" id="upload-progress"><div class="progress-fill" id="upload-fill"></div></div>' +
    '<div class="dialog-actions">' +
    '  <button type="button" class="btn" id="cancel-button">' + t('取消') + '</button>' +
    '  <button type="button" class="btn btn-primary" id="upload-button" disabled>' + icon('plus') + ' ' + t('加入') + '</button>' +
    '</div>';

  const dialog = openDialog(t('加入歌曲'), html, onDialogClose, 'wide');
  const box = dialog.box;
  const uploadButton = box.querySelector('#upload-button');

  let mode = 'file';         // 'file' 或 'youtube'
  let chosenFile = null;     // 選好的檔案
  let fileDuration = 0;      // 選好的檔案有多長（秒，讀不到就 0）
  let youtubeInfo = null;    // 讀取到的影片資訊

  const titleInput = box.querySelector('#title-input');
  const artistInput = box.querySelector('#artist-input');
  const lrcInput = box.querySelector('#lrc-input');

  box.querySelector('#cancel-button').addEventListener('click', function () {
    dialog.close();
  });

  // ---------- 歌詞選單 ----------

  // 搜尋歌詞用的歌名、歌手、長度
  function lyricsQuery() {
    let title = titleInput.value.trim();
    let duration = 0;
    if (mode === 'file') {
      if (title === '' && chosenFile) {
        title = chosenFile.name.replace(/\.[^.]+$/, '');   // 沒填歌名就用檔名
      }
      duration = fileDuration;
    } else if (youtubeInfo) {
      duration = youtubeInfo.duration || 0;
    }
    return { title: title, artist: artistInput.value.trim(), duration: duration };
  }

  // 還沒有歌，所以 currentLrc 回傳 null：點一列只是先選好，按加入時才一起送出
  const picker = new LyricsPicker(box.querySelector('#lyrics-picker'), {
    getQuery: lyricsQuery,
    currentLrc: function () {
      return null;
    },
    allowNone: true,
  });

  // 歌曲名稱、歌手改了：選單的搜尋欄還沒自己打過字的話，跟著換
  function followSong() {
    const query = lyricsQuery();
    picker.followSong(query.title, query.artist);
  }
  titleInput.addEventListener('input', followSong);
  artistInput.addEventListener('input', followSong);

  // 貼了自己的歌詞：搜到的清單用不到了，變淡
  lrcInput.addEventListener('input', function () {
    box.querySelector('#lyrics-picker').classList.toggle('faded', lrcInput.value.trim() !== '');
  });

  // 加入前要不要先停下來讓你挑歌詞：沒有自己貼歌詞、還沒搜尋過
  function needLyricsChoice() {
    return lrcInput.value.trim() === '' && !picker.searched;
  }

  // 要送給伺服器的歌詞：{ lrc: 歌詞文字（空的 = 不放歌詞）, source: 從哪來的 }
  function lyricsToSend() {
    if (lrcInput.value.trim() !== '') {
      return { lrc: lrcInput.value, source: '手動輸入' };
    }
    const item = picker.chosenItem();
    if (item === null) {
      return { lrc: '', source: '' };   // 選了「不用歌詞」或找不到
    }
    return { lrc: item.synced || item.plain, source: 'LRCLIB' };
  }

  // ---------- 切換分頁 ----------

  function updateButton() {
    uploadButton.innerHTML = icon('plus') + ' ' + t('加入');
    if (mode === 'file') {
      uploadButton.disabled = chosenFile === null;
    } else {
      const urlInput = box.querySelector('#youtube-url');
      uploadButton.disabled = !canYoutube || !urlInput || urlInput.value.trim() === '';
    }
  }

  for (const tab of box.querySelectorAll('.tab')) {
    tab.addEventListener('click', function () {
      mode = tab.dataset.tab;
      for (const other of box.querySelectorAll('.tab')) {
        other.classList.toggle('active', other === tab);
      }
      box.querySelector('#file-panel').classList.toggle('hidden', mode !== 'file');
      box.querySelector('#youtube-panel').classList.toggle('hidden', mode !== 'youtube');
      picker.reset();   // 換了來源，剛剛搜到的歌詞不一定是這首
      updateButton();
      if (mode === 'youtube' && canYoutube) {
        box.querySelector('#youtube-url').focus();
      }
    });
  }

  // 讀檔案有多長（只讀檔頭資訊，不會播放）
  function readFileDuration(file) {
    return new Promise(function (resolve) {
      const url = URL.createObjectURL(file);
      const media = document.createElement('audio');
      media.preload = 'metadata';
      media.muted = true;
      media.onloadedmetadata = function () {
        let seconds = 0;
        if (isFinite(media.duration)) {
          seconds = media.duration;
        }
        URL.revokeObjectURL(url);
        resolve(seconds);
      };
      media.onerror = function () {
        URL.revokeObjectURL(url);
        resolve(0);
      };
      media.src = url;
    });
  }

  // ---------- 電腦檔案 ----------

  const fileInput = box.querySelector('#file-input');
  const dropZone = box.querySelector('#drop-zone');

  async function chooseFile(file) {
    if (!file) {
      return;
    }
    chosenFile = file;
    fileDuration = 0;
    picker.reset();   // 換了檔案，剛剛搜到的歌詞不算
    dropZone.classList.add('has-file');
    box.querySelector('#drop-text').innerHTML = icon('check') + ' <b>' + escapeHtml(file.name) + '</b>';
    updateButton();
    fileDuration = await readFileDuration(file);
    if (chosenFile === file) {
      followSong();
      picker.search();
    }
  }

  dropZone.addEventListener('click', function () {
    fileInput.click();
  });
  dropZone.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener('change', function () {
    chooseFile(fileInput.files[0]);
  });
  dropZone.addEventListener('dragover', function (event) {
    event.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', function () {
    dropZone.classList.remove('drag-over');
  });
  dropZone.addEventListener('drop', function (event) {
    event.preventDefault();
    dropZone.classList.remove('drag-over');
    chooseFile(event.dataTransfer.files[0]);
  });

  // ---------- YouTube 網址 ----------

  async function readYoutubeInfo() {
    const url = box.querySelector('#youtube-url').value.trim();
    const status = box.querySelector('#youtube-status');
    status.textContent = t('讀取中…');
    youtubeInfo = await api.getYoutubeInfo(url);

    // 歌名、歌手還沒填的話，幫忙填上
    if (titleInput.value.trim() === '') {
      titleInput.value = youtubeInfo.title;
    }
    if (artistInput.value.trim() === '') {
      artistInput.value = youtubeInfo.artist;
    }
    status.innerHTML = '<span class="ok-text">' + icon('check') + '</span> ' + escapeHtml(youtubeInfo.title) +
      ' · ' + formatTime(youtubeInfo.duration);

    // 讀到歌名了，順便搜尋歌詞給你挑
    followSong();
    picker.search();
  }

  if (canYoutube) {
    const urlInput = box.querySelector('#youtube-url');
    urlInput.addEventListener('input', function () {
      youtubeInfo = null;   // 網址改了，要重新讀取
      picker.reset();       // 剛剛搜到的歌詞也不算了
      updateButton();
    });
    // 貼上網址就自動讀取（不用再按「讀取」）
    urlInput.addEventListener('paste', function () {
      setTimeout(function () {
        if (urlInput.value.trim() !== '') {
          box.querySelector('#youtube-read').click();
        }
      }, 0);
    });
    urlInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        box.querySelector('#youtube-read').click();
      }
    });
    box.querySelector('#youtube-read').addEventListener('click', async function () {
      if (urlInput.value.trim() === '') {
        return;
      }
      try {
        await readYoutubeInfo();
      } catch (error) {
        box.querySelector('#youtube-status').innerHTML = '<span class="warn-text">' + escapeHtml(error.message) + '</span>';
      }
    });
  }

  // ---------- 送出 ----------

  // 要送出的歌名、歌手：空白的用選的那份歌詞上的補上（自己貼的歌詞沒有歌名，不補）
  function namesToSend(lyrics) {
    let item = null;
    if (lyrics.source === 'LRCLIB') {
      item = picker.chosenItem();
    }
    return fillNames(titleInput.value, artistInput.value, item);
  }

  // 歌詞已經在對話方塊裡挑好了，所以 auto_lyrics 一律送 false（伺服器不要自己再挑一次）
  // 回傳加入的歌
  async function submitFile() {
    const lyrics = lyricsToSend();
    const names = namesToSend(lyrics);
    const form = new FormData();
    form.append('file', chosenFile);
    form.append('title', names.title);
    form.append('artist', names.artist);
    form.append('separate', box.querySelector('#separate-check').checked ? 'true' : 'false');
    form.append('auto_lyrics', 'false');
    form.append('lrc', lyrics.lrc);
    form.append('lyrics_source', lyrics.source);

    uploadButton.textContent = t('上傳中…');
    box.querySelector('#upload-progress').classList.remove('hidden');
    return await api.uploadSong(form, function (ratio) {
      box.querySelector('#upload-fill').style.width = Math.round(ratio * 100) + '%';
    });
  }

  async function submitYoutube() {
    // 還沒按「讀取」的話，先讀取標題和歌手
    if (youtubeInfo === null) {
      uploadButton.textContent = t('讀取中…');
      await readYoutubeInfo();
    }
    uploadButton.textContent = t('加入中…');
    const lyrics = lyricsToSend();
    const names = namesToSend(lyrics);
    return await api.addYoutubeSong({
      url: box.querySelector('#youtube-url').value.trim(),
      title: names.title,
      artist: names.artist,
      separate: box.querySelector('#separate-check').checked,
      auto_lyrics: false,
      lrc: lyrics.lrc,
      lyrics_source: lyrics.source,
    });
  }

  // 關掉對話方塊：還在搜尋的歌詞結果不要了
  function onDialogClose() {
    picker.destroy();
  }

  // 還沒搜尋歌詞就按了加入：先搜尋、列出來給你挑，這次先不加入
  async function showLyricsChoiceFirst() {
    uploadButton.textContent = t('找歌詞中…');
    if (mode === 'youtube' && youtubeInfo === null) {
      await readYoutubeInfo();   // 讀完會自動開始搜尋歌詞
    }
    await picker.finishSearch();
    box.querySelector('#lyrics-picker').scrollIntoView({ block: 'nearest' });
    showToast(t('先看一下右邊的歌詞，再按一次「加入」'), 'ok');
  }

  uploadButton.addEventListener('click', async function () {
    uploadButton.disabled = true;
    try {
      if (needLyricsChoice()) {
        await showLyricsChoiceFirst();
        updateButton();
        return;
      }
      let song = null;
      if (mode === 'file') {
        if (!chosenFile) {
          return;
        }
        song = await submitFile();
        showToast(t('「{title}」已加入，正在背景處理…', { title: song.title }), 'ok');
      } else {
        song = await submitYoutube();
        showToast(t('「{title}」已加入，正在背景下載和處理…', { title: song.title }), 'ok');
      }
      if (onDone) {
        onDone(song);
      }
      dialog.close();   // 加入就關掉，背景繼續處理
    } catch (error) {
      showToast(error.message, 'error');
      updateButton();
    }
  });
}
