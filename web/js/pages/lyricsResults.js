// 歌詞搜尋結果清單（「加入歌曲」的歌詞選單和「編輯歌詞」頁共用）
//   sortResults    最可能對的排前面
//   isRecommended  這一筆算不算「推薦」（有時間軸、長度差 15 秒以內）
//   resultsHtml    做出清單的 HTML：每一筆整列都可以點（data-pick="第幾筆"），選到的左邊打勾

import { t } from '../i18n.js';
import { icon } from '../icons.js';
import { escapeHtml, formatTime } from '../ui.js';

// 長度差幾秒以內算「推薦」（跟伺服器自動挑歌詞的標準一樣）
const RECOMMEND_LIMIT = 15;
// 每一筆下面顯示幾句歌詞，讓你看得出是不是這首、是不是這個版本
const PREVIEW_LINES = 2;

// 這筆歌詞「不像」你的歌的程度：數字越小越可能是對的
//   有時間軸的比只有文字的好；長度越接近你的歌越好（差幾秒就加幾分）
export function matchScore(item, duration) {
  let score = 0;
  if (!item.synced) {
    score += 1000;
  }
  if (duration && item.duration) {
    score += Math.abs(item.duration - duration);
  } else {
    score += 500;  // 不知道長度，沒辦法比
  }
  return score;
}

export function sortResults(results, duration) {
  results.sort(function (a, b) {
    return matchScore(a, duration) - matchScore(b, duration);
  });
  return results;
}

export function isRecommended(item, duration) {
  return matchScore(item, duration) <= RECOMMEND_LIMIT;
}

// 歌詞的前幾句（去掉時間標記），例如「作詞：某某 / 第一句歌詞…」
function previewText(item) {
  const text = item.synced || item.plain || '';
  const lines = [];
  for (let line of text.split('\n')) {
    line = line.replace(/\[[^\]]*\]/g, '').replace(/<\d+:\d+(\.\d+)?>/g, '').trim();
    if (line === '') {
      continue;
    }
    lines.push(line);
    if (lines.length >= PREVIEW_LINES) {
      break;
    }
  }
  return lines.join(' / ');
}

// 長度：跟你的歌差不多就打個綠勾；差很多寫「長 60 秒」「短 60 秒」
const SAME_LENGTH = 2;   // 差幾秒以內算一樣長

function lengthHtml(item, duration) {
  let html = formatTime(item.duration);
  if (duration && item.duration) {
    const difference = Math.round(item.duration - duration);
    if (Math.abs(difference) <= SAME_LENGTH) {
      html += ' <span class="ok-text" title="' + t('跟你的歌一樣長') + '">' + icon('check') + '</span>';
    } else if (difference > 0) {
      html += ' <span class="warn-text">' + t('長 {seconds} 秒', { seconds: difference }) + '</span>';
    } else {
      html += ' <span class="warn-text">' + t('短 {seconds} 秒', { seconds: -difference }) + '</span>';
    }
  }
  return html;
}

// 「字幕跳出來時原唱沒在唱」的句子，幾句以內不算時間不準
//   （一兩句常常是 AI 去人聲時，把加了效果的人聲當成伴奏分走了，歌詞本身沒錯）
const FEW_SILENT = 2;

// 多份歌詞互相比對的結果（伺服器 lyrics_consensus.py）：
//   check = { diff: 整首比大部分版本早（負）／晚（正）幾秒, off: 整首差太多, odd: [寫錯的句子] }；比不了是 null
// 有問題就回傳一句話（例如「整首比大部分版本早 6.0 秒」），沒問題回傳 ''
export function checkProblem(check) {
  if (!check) {
    return '';
  }
  if (check.off) {
    const seconds = Math.abs(check.diff).toFixed(1);
    if (check.diff < 0) {
      return t('整首比大部分版本早 {seconds} 秒', { seconds: seconds });
    }
    return t('整首比大部分版本晚 {seconds} 秒', { seconds: seconds });
  }
  if (check.odd.length > 0) {
    return t('有 {count} 句時間跟大部分版本不一樣', { count: check.odd.length });
  }
  return '';
}

// 寫錯的句子（最多 3 句），例如「某一句」在 0:19，大部分版本在 0:38
export function checkDetail(check) {
  if (!check || check.odd.length === 0) {
    return '';
  }
  const lines = [];
  for (const odd of check.odd.slice(0, 3)) {
    lines.push(t('「{text}」在 {time}，大部分版本在 {others}',
      { text: odd.text, time: formatTime(odd.time), others: formatTime(odd.others) }));
  }
  return lines.join('\n');
}

// 這份歌詞的時間準不準的標籤（只放一個，詳細的說明放在滑鼠移上去才出現的提示裡）
//   item.match：伺服器比對的結果 { shift, silent, silent_at, check }（「編輯歌詞」頁才有；沒有時間軸的是 null）
//   silent：字幕跳出來時，原唱（AI 分出來的人聲）幾乎沒聲音的句數
//   check：跟網路上其他版本比的結果（見 checkProblem）
const NO_TIME_TAG = '<span class="tag tag-warn" title="' + t('這份歌詞沒有時間，唱歌時不會有字幕') + '">' +
  t('只有文字') + '</span>';

function matchTag(item) {
  if (item.match === null || !item.synced) {
    return NO_TIME_TAG;
  }
  const problem = checkProblem(item.match.check);
  if (problem !== '') {
    let tip = t('{problem}，換一份比較好', { problem: problem });
    const detail = checkDetail(item.match.check);
    if (detail !== '') {
      tip += '\n' + detail;
    }
    return '<span class="tag tag-warn" title="' + escapeHtml(tip) + '">' + icon('warn') + ' ' + t('可能不準') + '</span>';
  }
  if (item.match.silent <= FEW_SILENT) {
    let tip = t('字幕會準時出現');
    if (Math.abs(item.match.shift) >= 0.1) {
      tip += t('（程式會自己調 {seconds} 秒）', { seconds: Math.abs(item.match.shift).toFixed(1) });
    }
    return '<span class="tag tag-ok" title="' + tip + '">' + icon('check') + ' ' + t('時間準') + '</span>';
  }
  const tip = t('從 {time} 開始，字幕出來的時候沒人在唱。換一份比較好', { time: formatTime(item.match.silent_at) });
  return '<span class="tag tag-warn" title="' + tip + '">' + icon('warn') + ' ' + t('可能不準') + '</span>';
}

// 照「時間準不準」排（有比對結果才用）：
//   有時間軸的排前面 → 跟大部分版本整首差很多的排很後面 → 時間可能不準（3 句以上原唱沒在唱）的排後面
//   → 有幾句跟大部分版本不一樣的往後 → 要整首移才準的排後面
//   → 一兩句原唱沒在唱的稍微後面（可能只是 AI 去人聲分錯，不一定是錯的）→ 長度接近
export function sortByMatch(results, duration) {
  results.sort(function (a, b) {
    return matchRank(a, duration) - matchRank(b, duration);
  });
  return results;
}

function matchRank(item, duration) {
  if (!item.match || !item.synced) {
    return 100000 + matchScore(item, duration);
  }
  let rank = 0;
  if (item.match.silent > FEW_SILENT) {
    rank += 1000 * item.match.silent;
  } else {
    rank += 30 * item.match.silent;
  }
  if (Math.abs(item.match.shift) >= 0.1) {
    rank += 100;
  }
  // 跟網路上大部分版本比：整首差太多的排很後面，有幾句寫錯的每句往後一點
  const check = item.match.check;
  if (check) {
    if (check.off) {
      rank += 3000;
    }
    rank += 300 * check.odd.length;
  }
  return rank + matchScore(item, duration);
}

// 一列（可以點的選項）：左邊圓圈（選到的打勾）、中間內容、右邊（標籤、試聽鍵）
//   index：第幾筆（-1 = 「不用歌詞」那一列）
export function choiceRowHtml(index, chosen, infoHtml, actionsHtml, extraClass) {
  let rowClass = 'result-item';
  if (extraClass) {
    rowClass += ' ' + extraClass;
  }
  let mark = '';
  if (chosen) {
    rowClass += ' chosen';
    mark = icon('check');
  }
  return '<div class="' + rowClass + '" data-pick="' + index + '" role="radio" tabindex="0" aria-checked="' + chosen + '">' +
    '<span class="pick-mark">' + mark + '</span>' +
    '<div class="result-info">' + infoHtml + '</div>' +
    '<div class="result-actions">' + (actionsHtml || '') + '</div>' +
    '</div>';
}

// chosenIndex：已經選好的是第幾筆（-1 = 沒有選），那一列打勾
// canListen：有時間的那幾筆右邊要不要有「▶」試聽鍵（data-listen="第幾筆"）；
//            「編輯歌詞」頁才有，加歌時還沒有音樂可以播
export function resultsHtml(results, duration, chosenIndex, canListen) {
  let html = '';
  for (let i = 0; i < results.length; i++) {
    const item = results[i];
    const hasMatch = item.match !== undefined;

    let recommend = '';
    if (i === 0) {
      if (hasMatch && item.match && item.match.silent <= FEW_SILENT && checkProblem(item.match.check) === '') {
        recommend = '<span class="tag tag-star">' + icon('star') + ' ' + t('推薦') + '</span>';
      } else if (!hasMatch && isRecommended(item, duration)) {
        recommend = '<span class="tag tag-star">' + icon('star') + ' ' + t('推薦') + '</span>';
      }
    }

    // 下面一行小字：專輯 · 長度（加歌時跟你的歌比長度）
    const details = [];
    if (item.album && item.album !== '-' && item.album !== 'null') {
      details.push(escapeHtml(item.album));
    }
    if (hasMatch) {
      details.push(formatTime(item.duration));
    } else {
      details.push(lengthHtml(item, duration));
    }

    // 右邊：時間準不準（編輯歌詞頁才比得出來；加歌時只標「只有文字」）、試聽鍵
    let actions = '';
    if (hasMatch) {
      actions += matchTag(item);
    } else if (!item.synced) {
      actions += NO_TIME_TAG;
    }
    if (canListen && item.synced) {
      actions += '<button type="button" class="btn btn-icon btn-listen" data-listen="' + i + '" title="' + t('試聽') + '" aria-label="' + t('試聽') + '">' +
        icon('play') + '</button>';
    }

    let preview = '';
    const previewWords = previewText(item);
    if (previewWords !== '') {
      preview = '<div class="result-preview small">' + escapeHtml(previewWords) + '</div>';
    }

    const info =
      '<div class="result-title">' + recommend + '<b>' + escapeHtml(item.title) + '</b>' +
      '<span class="muted"> · ' + escapeHtml(item.artist) + '</span></div>' +
      '<div class="muted small">' + details.join(' · ') + '</div>' +
      preview;
    html += choiceRowHtml(i, i === chosenIndex, info, actions);
  }
  return html;
}
