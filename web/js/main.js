// 程式入口：負責「換頁」。
// 網址 # 後面的部分決定要顯示哪一頁，例如：
//   #/                 歌曲庫
//   #/song/<ID>         歌曲詳情
//   #/song/<ID>/lyrics  編輯歌詞
//   #/song/<ID>/chart   修譜（自己修評分條）
//   #/sing/<ID>         唱歌畫面（#/sing/<ID>?test=1 是測試模式）

import * as libraryPage from './pages/libraryPage.js';
import * as songPage from './pages/songPage.js';
import * as lyricsPage from './pages/lyricsPage.js';
import * as chartPage from './pages/chartPage.js';
import * as singPage from './pages/singPage.js';
import { icon } from './icons.js';
import { openSettingsDialog } from './pages/settingsDialog.js';
import { closeAllDialogs } from './ui.js';
import './rangeFill.js';     // 滑桿左邊的填色（只管外觀）
import './pageEffects.js';   // 換頁的特效（只管外觀）

const routes = [
  { pattern: /^\/$/, page: libraryPage },
  { pattern: /^\/song\/([^/]+)$/, page: songPage },
  { pattern: /^\/song\/([^/]+)\/lyrics$/, page: lyricsPage },
  { pattern: /^\/song\/([^/]+)\/chart$/, page: chartPage },
  { pattern: /^\/sing\/([^/]+)$/, page: singPage },
];

let currentPage = null;

// 把 "a=1&b=2" 變成 { a: '1', b: '2' }
function parseQuery(text) {
  const result = {};
  if (!text) {
    return result;
  }
  const pairs = text.split('&');
  for (const pair of pairs) {
    const parts = pair.split('=');
    result[decodeURIComponent(parts[0])] = decodeURIComponent(parts[1] || '');
  }
  return result;
}

function showPage() {
  // 先讓上一頁收拾乾淨（停止音樂、計時器、關掉對話方塊…）
  closeAllDialogs();
  if (currentPage && currentPage.leave) {
    currentPage.leave();
  }
  currentPage = null;

  let hash = location.hash.replace(/^#/, '');
  if (hash === '') {
    hash = '/';
  }
  const questionMark = hash.indexOf('?');
  let path = hash;
  let query = {};
  if (questionMark >= 0) {
    path = hash.substring(0, questionMark);
    query = parseQuery(hash.substring(questionMark + 1));
  }

  const app = document.getElementById('app');
  for (const route of routes) {
    const match = path.match(route.pattern);
    if (match) {
      currentPage = route.page;
      window.scrollTo(0, 0);
      route.page.enter(app, decodeURIComponent(match[1] || ''), query);
      return;
    }
  }
  location.hash = '#/';
}

window.addEventListener('hashchange', showPage);

const settingsButton = document.getElementById('settings-button');
settingsButton.innerHTML = icon('settings') + ' 設定';
settingsButton.addEventListener('click', function () {
  openSettingsDialog();
});

showPage();
