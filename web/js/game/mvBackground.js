// MV 背景：唱歌時在背景播影片，跟伴奏保持同步。
//
// 影片是「靜音」的，聲音一律用伴奏和導唱。
// 每個畫面都比對一次「伴奏播到第幾秒」和「影片播到第幾秒」，
// 差太多就把影片拉回來（暫停、倒退、快轉、重來都會自動跟上）。

const MAX_DRIFT_PLAYING = 0.25;  // 播放中：差超過 0.25 秒才拉回來（太常拉畫面會卡）
const MAX_DRIFT_PAUSED = 0.05;   // 暫停中：停在正確的畫面

export class MvBackground {
  constructor(video, url, brightness) {
    this.video = video;
    this.video.muted = true;
    this.video.src = url;
    this.setBrightness(brightness);
    this.video.classList.remove('hidden');
  }

  // MV 亮度（10～100%，太亮會看不清楚字幕）
  setBrightness(brightness) {
    this.video.style.filter = 'brightness(' + brightness / 100 + ')';
  }

  // 每個畫面呼叫一次。songTime：伴奏現在在第幾秒；playing：伴奏是不是正在播
  sync(songTime, playing) {
    const video = this.video;
    if (video.readyState === 0 || video.seeking) {
      return;  // 影片還沒載入，或正在跳到別的地方
    }
    const target = Math.max(0, Math.min(songTime, video.duration || 0));

    if (playing) {
      if (video.paused && target < video.duration) {
        video.play().catch(function () {
          // 瀏覽器不讓播就算了，不影響唱歌
        });
      }
      if (Math.abs(video.currentTime - target) > MAX_DRIFT_PLAYING) {
        video.currentTime = target;
      }
    } else {
      if (!video.paused) {
        video.pause();
      }
      if (Math.abs(video.currentTime - target) > MAX_DRIFT_PAUSED) {
        video.currentTime = target;
      }
    }
  }

  destroy() {
    this.video.pause();
    this.video.removeAttribute('src');
    this.video.load();  // 釋放影片佔用的記憶體
    this.video.classList.add('hidden');
  }
}
