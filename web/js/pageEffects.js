// 換頁的特效（只管好不好看，跟功能無關）
//
// 每次換頁：最上面一條細細的彩色光從左邊射到右邊（.page-streak），就這樣。
// 整個畫面不閃、不變模糊；
// 特效只做在條、按鈕這些小元件上
// 動畫長什麼樣子寫在 style.css 的「換頁特效」那一段
//
// 用法：main.js 寫一行 import './pageEffects.js' 就好

// 最上面那條光：只做一個，每次換頁重播
const streak = document.createElement('div');
streak.className = 'page-streak';
streak.setAttribute('aria-hidden', 'true');
document.body.appendChild(streak);

function playPageEffect() {
  // 先拿掉再加上，動畫才會從頭播
  streak.classList.remove('run');
  void streak.offsetWidth;
  streak.classList.add('run');
}

window.addEventListener('hashchange', playPageEffect);
