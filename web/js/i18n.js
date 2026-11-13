// 介面語言：中文或英文。
//
// 程式裡的字一律寫中文，用 t() 包起來：
//   t('加入歌曲')
//   t('「{title}」已加入', { title: song.title })   ← {名字} 的地方會換成後面給的東西
// 顯示中文時就是寫的那個字；顯示英文時去對照表（lang/en.js）查，查不到就還是顯示中文。
//
// 伺服器傳來的字（處理進度、錯誤訊息）用 tServer()，查的是同一份對照表。
//
// 要多一種語言：做一份對照表，在下面的 LANGUAGES 加一列。
// 檢查有沒有漏翻：.venv\Scripts\python tools\check_language.py

import { EN } from './lang/en.js';
import { loadSettings } from './settings.js';

// 可以選的語言
//   id      ：存在設定裡的代號，也拿來比對瀏覽器的語言（瀏覽器語言的開頭一樣就算）
//   label   ：設定裡顯示的名字（用那個語言自己的寫法）
//   htmlLang：告訴瀏覽器這一頁是什麼語言
//   table   ：對照表。中文是程式裡本來的字，不用對照表
export const LANGUAGES = [
  { id: 'zh', label: '中文', htmlLang: 'zh-Hant-TW', table: null },
  { id: 'en', label: 'English', htmlLang: 'en', table: EN },
];

// 設定選「跟瀏覽器」，而瀏覽器的語言不在上面的清單裡時，用哪一個
const OTHER_LANGUAGE = 'en';

function findLanguage(id) {
  for (const language of LANGUAGES) {
    if (language.id === id) {
      return language;
    }
  }
  return null;
}

// choice：設定裡存的值。'auto' = 跟瀏覽器走，其他是語言的代號
function pickLanguage(choice) {
  const chosen = findLanguage(choice);
  if (chosen) {
    return chosen;
  }
  const browser = (navigator.language || '').toLowerCase();
  for (const language of LANGUAGES) {
    if (browser.startsWith(language.id)) {
      return language;
    }
  }
  return findLanguage(OTHER_LANGUAGE);
}

// 現在用的語言。換語言要重新整理畫面才會換（設定存檔時會自動重新整理）
const current = pickLanguage(loadSettings().language);
document.documentElement.lang = current.htmlLang;

// 把 {名字} 換成 values 裡的東西
function fill(text, values) {
  if (!values) {
    return text;
  }
  let result = text;
  for (const name in values) {
    result = result.split('{' + name + '}').join(String(values[name]));
  }
  return result;
}

function lookUp(text) {
  if (current.table && current.table[text] !== undefined) {
    return current.table[text];
  }
  return text;
}

// 程式裡寫的字 → 現在的語言
export function t(text, values) {
  return fill(lookUp(text), values);
}

// 伺服器傳來的字 → 現在的語言。
// 伺服器的字裡常常有會變的東西，所以照順序試三種查法：
//   1. 整句直接查
//   2. 把數字換成 {n} 再查（例如「從 YouTube 下載畫面 45%」查的是「從 YouTube 下載畫面 {n}%」），查到再把數字放回去
//   3. 切成「：」前面和後面兩段，各自再查一次（例如「不支援的檔案格式：.xyz」）
// 都查不到就原樣顯示
export function tServer(text) {
  if (typeof text !== 'string' || text === '') {
    return text;
  }
  const whole = lookUp(text);
  if (whole !== text) {
    return whole;
  }

  const numberPattern = /\d+(\.\d+)?/g;
  const numbers = text.match(numberPattern);
  if (numbers) {
    const key = text.replace(numberPattern, '{n}');
    let translated = lookUp(key);
    if (translated !== key) {
      for (const number of numbers) {
        translated = translated.replace('{n}', number);
      }
      return translated;
    }
  }

  const colon = text.indexOf('：');
  if (colon > 0) {
    const head = text.substring(0, colon + 1);
    const translated = lookUp(head);
    if (translated !== head) {
      return translated + tServer(text.substring(colon + 1));
    }
  }
  return text;
}
