// 畫面小工具：提示訊息、對話方塊、時間格式…（每一頁都會用到）

import { t } from './i18n.js';

// 把文字裡的特殊符號換掉，避免放進 HTML 時出問題
export function escapeHtml(text) {
  if (text === null || text === undefined) {
    return '';
  }
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

// 秒數 → 「分:秒」，例如 125 → 2:05
export function formatTime(seconds) {
  if (!seconds || seconds < 0) {
    seconds = 0;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  let text = String(rest);
  if (rest < 10) {
    text = '0' + text;
  }
  return minutes + ':' + text;
}

// 右下角跳出提示訊息，幾秒後自動消失
export function showToast(message, type) {
  const area = document.getElementById('toast-area');
  const toast = document.createElement('div');
  toast.className = 'toast';
  if (type) {
    toast.classList.add('toast-' + type);
  }
  toast.textContent = message;
  area.appendChild(toast);
  setTimeout(function () {
    toast.classList.add('toast-hide');
  }, 3000);
  setTimeout(function () {
    toast.remove();
  }, 3500);
}

// 開啟一個對話方塊。回傳 { box, close }，box 是對話方塊內容的元素
//   size：'wide' = 寬一點（加歌、設定這種東西多的）；不給 = 一般寬度
export function openDialog(title, bodyHtml, onClose, size) {
  const backdrop = document.createElement('div');
  backdrop.className = 'dialog-backdrop';
  let dialogClass = 'dialog';
  if (size === 'wide') {
    dialogClass += ' dialog-wide';
  }
  backdrop.innerHTML =
    '<div class="' + dialogClass + '">' +
    '  <div class="dialog-header">' +
    '    <h3>' + escapeHtml(title) + '</h3>' +
    '    <button class="btn btn-icon btn-ghost dialog-close" title="' + t('關閉') + '" aria-label="' + t('關閉') + '">' +
    '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>' +
    '  </div>' +
    '  <div class="dialog-body">' + bodyHtml + '</div>' +
    '</div>';
  document.body.appendChild(backdrop);

  let closed = false;
  function close() {
    if (closed) {
      return;
    }
    closed = true;
    backdrop.remove();
    document.removeEventListener('keydown', onKeyDown);
    openDialogs.splice(openDialogs.indexOf(close), 1);
    if (onClose) {
      onClose();
    }
  }

  // 按 Esc 關閉
  function onKeyDown(event) {
    if (event.key === 'Escape') {
      close();
    }
  }

  backdrop.querySelector('.dialog-close').addEventListener('click', close);
  backdrop.addEventListener('mousedown', function (event) {
    if (event.target === backdrop) {
      close();
    }
  });
  document.addEventListener('keydown', onKeyDown);
  openDialogs.push(close);

  return { box: backdrop.querySelector('.dialog-body'), close: close };
}

// 目前開著的對話方塊（換頁時全部關掉）
const openDialogs = [];

export function closeAllDialogs() {
  const list = openDialogs.slice();
  for (const close of list) {
    close();
  }
}

// 這一下按鍵是不是輸入法正在選字
//   中文、日文輸入法用 Enter 確認選的字，這時候的 Enter 不能當成「送出」「搜尋」，不然字還沒打完就送出去了。
//   輸入框自己處理 Enter 的地方都要先問這個。
//   isComposing：瀏覽器說正在選字；
//   keyCode 229：有些瀏覽器（Safari）確認選字的那一下 Enter，isComposing 已經變回 false，只剩這個看得出來
export function isChoosingWord(event) {
  return event.isComposing || event.keyCode === 229;
}

// 問使用者「確定嗎？」
export function confirmAction(message) {
  return window.confirm(message);
}

// ---------- 小問號（說明）----------
// 畫面上只放短短的字，詳細說明收在旁邊的小「?」裡：
//   滑鼠移上去就看得到，點一下會固定住（再點一次、或點別的地方就關掉）
// 用法：'<label>靈敏度' + helpTip('數字越小越靈敏') + '</label>'
//   說明裡的 \n 會換行

export function helpTip(text) {
  return '<button type="button" class="help-tip" data-help="' + escapeHtml(text) + '" aria-label="' + t('說明') + '">?</button>';
}

let helpBubble = null;     // 現在打開的說明泡泡
let helpOwner = null;      // 是哪一個「?」打開的
let helpPinned = false;    // 是不是點了固定住（固定住的，滑鼠移開也不會關）

function showHelp(button) {
  hideHelp();
  helpOwner = button;
  helpBubble = document.createElement('div');
  helpBubble.className = 'help-bubble';
  helpBubble.textContent = button.dataset.help;
  document.body.appendChild(helpBubble);

  // 放在「?」的下面；超出畫面的話往左、往上移
  const rect = button.getBoundingClientRect();
  const width = helpBubble.offsetWidth;
  const height = helpBubble.offsetHeight;
  let left = rect.left + rect.width / 2 - width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
  let top = rect.bottom + 8;
  if (top + height > window.innerHeight - 8) {
    top = rect.top - height - 8;
  }
  helpBubble.style.left = left + 'px';
  helpBubble.style.top = Math.max(8, top) + 'px';
}

function hideHelp() {
  if (helpBubble) {
    helpBubble.remove();
  }
  helpBubble = null;
  helpOwner = null;
  helpPinned = false;
}

function findHelpTip(event) {
  if (!event.target || !event.target.closest) {
    return null;
  }
  return event.target.closest('.help-tip');
}

document.addEventListener('mouseover', function (event) {
  const button = findHelpTip(event);
  if (button && button !== helpOwner && !helpPinned) {
    showHelp(button);
  }
});

document.addEventListener('mouseout', function (event) {
  const button = findHelpTip(event);
  if (button && button === helpOwner && !helpPinned) {
    hideHelp();
  }
});

// 點「?」：固定住／關掉；點別的地方：關掉
//（「?」放在勾選框、展開標題裡也不會順便勾到、展開）
document.addEventListener('click', function (event) {
  const button = findHelpTip(event);
  if (!button) {
    if (helpBubble) {
      hideHelp();
    }
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  if (button === helpOwner && helpPinned) {
    hideHelp();
    return;
  }
  if (button !== helpOwner) {
    showHelp(button);
  }
  helpPinned = true;
}, true);

// 捲動、換頁時泡泡會對不到「?」的位置，直接關掉
window.addEventListener('scroll', hideHelp, true);
window.addEventListener('hashchange', hideHelp);
