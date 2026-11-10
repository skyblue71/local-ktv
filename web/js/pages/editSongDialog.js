// 「編輯歌曲資料」對話方塊：改歌名、歌手、封面（加入之後隨時可以改）
//   封面：按「選擇圖片」、把圖片拖進來、或複製圖片後在這裡按 Ctrl+V
//   換過封面的話，可以「還原原本的封面」（YouTube 縮圖或檔案內附的封面）

import * as api from '../api.js';
import { icon } from '../icons.js';
import { escapeHtml, helpTip, openDialog, showToast } from '../ui.js';

export function openEditSongDialog(song, onSaved) {
  let restoreButton = '';
  if (song.cover_custom) {
    restoreButton = '<button class="btn btn-small" id="cover-restore">' + icon('undo') + ' 還原封面</button>';
  }

  const html =
    '<div class="form-grid">' +
    '  <label for="edit-title">歌名</label><input class="input" id="edit-title">' +
    '  <label for="edit-artist">歌手</label><input class="input" id="edit-artist" placeholder="可以空白">' +
    '  <span>封面</span>' +
    '  <div class="cover-editor">' +
    '    <div class="cover-drop" id="cover-drop" title="按這裡選圖片，或把圖片拖進來"></div>' +
    '    <div class="cover-actions">' +
    '      <div><button class="btn btn-small" id="cover-choose">' + icon('image') + ' 選圖片</button>' +
    helpTip('也可以把圖片拖到左邊，或複製圖片後按 Ctrl+V。\njpg、png、webp 都可以') + '</div>' +
    '      ' + restoreButton +
    '      <div class="small" id="cover-status"></div>' +
    '    </div>' +
    '    <input type="file" id="cover-file" accept="image/*" hidden>' +
    '  </div>' +
    '</div>' +
    '<div class="dialog-actions">' +
    '  <button class="btn" id="edit-cancel">取消</button>' +
    '  <button class="btn btn-primary" id="edit-save">' + icon('save') + ' 儲存</button>' +
    '</div>';

  // 不管怎麼關（儲存、取消、✕、Esc、點外面），都要把「貼上」的監聽拿掉、釋放預覽圖
  const dialog = openDialog('編輯歌曲資料', html, function () {
    document.removeEventListener('paste', onPaste);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
  });
  const box = dialog.box;
  const titleInput = box.querySelector('#edit-title');
  const artistInput = box.querySelector('#edit-artist');
  titleInput.value = song.title || '';
  artistInput.value = song.artist || '';

  let newCover = null;      // 選好的新封面（還沒存）
  let previewUrl = null;    // 新封面的預覽網址（用完要釋放）

  function showCover(url) {
    const drop = box.querySelector('#cover-drop');
    if (url) {
      drop.innerHTML = '<img src="' + url + '" alt="">';
    } else {
      drop.innerHTML = '<span class="cover-letter">' + escapeHtml((song.title || '?').charAt(0)) + '</span>';
    }
  }
  if (song.has_cover) {
    showCover(api.coverUrl(song.id, song.cover_version));
  } else {
    showCover(null);
  }

  function chooseCover(file) {
    if (!file) {
      return;
    }
    if (!file.type.startsWith('image/')) {
      showToast('這不是圖片檔', 'error');
      return;
    }
    newCover = file;
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    previewUrl = URL.createObjectURL(file);
    showCover(previewUrl);
    box.querySelector('#cover-status').textContent = '新封面：' + (file.name || '貼上的圖片');
  }

  const fileInput = box.querySelector('#cover-file');
  box.querySelector('#cover-choose').addEventListener('click', function () {
    fileInput.click();
  });
  box.querySelector('#cover-drop').addEventListener('click', function () {
    fileInput.click();
  });
  fileInput.addEventListener('change', function () {
    chooseCover(fileInput.files[0]);
  });

  // 拖曳圖片進來
  const drop = box.querySelector('#cover-drop');
  drop.addEventListener('dragover', function (event) {
    event.preventDefault();
    drop.classList.add('drag-over');
  });
  drop.addEventListener('dragleave', function () {
    drop.classList.remove('drag-over');
  });
  drop.addEventListener('drop', function (event) {
    event.preventDefault();
    drop.classList.remove('drag-over');
    chooseCover(event.dataTransfer.files[0]);
  });

  // Ctrl+V 貼上圖片
  function onPaste(event) {
    if (!event.clipboardData) {
      return;
    }
    for (const item of event.clipboardData.items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        event.preventDefault();
        chooseCover(item.getAsFile());
        return;
      }
    }
  }
  document.addEventListener('paste', onPaste);

  function close() {
    dialog.close();
  }

  box.querySelector('#edit-cancel').addEventListener('click', close);

  const restore = box.querySelector('#cover-restore');
  if (restore) {
    restore.addEventListener('click', async function () {
      try {
        await api.restoreCover(song.id);
        showToast('已還原原本的封面', 'ok');
        close();
        if (onSaved) {
          onSaved();
        }
      } catch (error) {
        showToast('還原失敗：' + error.message, 'error');
      }
    });
  }

  const saveButton = box.querySelector('#edit-save');
  saveButton.addEventListener('click', async function () {
    const title = titleInput.value.trim();
    if (title === '') {
      showToast('歌名不能空白', 'error');
      return;
    }
    saveButton.disabled = true;
    try {
      if (title !== song.title || artistInput.value.trim() !== (song.artist || '')) {
        await api.updateSong(song.id, { title: title, artist: artistInput.value.trim() });
      }
      if (newCover) {
        box.querySelector('#cover-status').textContent = '上傳封面中…';
        await api.uploadCover(song.id, newCover);
      }
      showToast('已儲存', 'ok');
      close();
      if (onSaved) {
        onSaved();
      }
    } catch (error) {
      showToast('儲存失敗：' + error.message, 'error');
      saveButton.disabled = false;
    }
  });
}
