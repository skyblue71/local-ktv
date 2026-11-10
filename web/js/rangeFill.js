// 滑桿的填色：讓滑桿「已經拉到的那一段」有顏色（只管好不好看，跟功能無關）
//
// 瀏覽器自己不會幫滑桿左邊上色，所以這裡算出「拉到百分之幾」，
// 寫進滑桿的 --range-fill，style.css 再照這個數字畫顏色。
//
// 什麼時候算：
//   1. 你拉滑桿的時候（馬上算）
//   2. 每隔一小段時間全部看一次（程式自己改數字的時候不會通知，例如試聽的進度條、剛打開的設定）
//
// 用法：main.js 寫一行 import './rangeFill.js' 就好，每一頁的滑桿都會有

const CHECK_EVERY = 150;   // 幾毫秒全部看一次

// 算一個滑桿拉到百分之幾，有變才寫進去
function paintRange(input) {
  const min = Number(input.min || 0);
  const max = Number(input.max || 100);
  let percent = 0;
  if (max > min) {
    percent = (Number(input.value) - min) / (max - min) * 100;
  }
  percent = Math.max(0, Math.min(100, percent));
  const text = percent.toFixed(1) + '%';
  if (input.dataset.fill !== text) {
    input.dataset.fill = text;
    input.style.setProperty('--range-fill', text);
  }
}

function paintAllRanges() {
  for (const input of document.querySelectorAll('input[type="range"]')) {
    paintRange(input);
  }
}

document.addEventListener('input', function (event) {
  const target = event.target;
  if (target && target.type === 'range') {
    paintRange(target);
  }
});

setInterval(paintAllRanges, CHECK_EVERY);
paintAllRanges();
