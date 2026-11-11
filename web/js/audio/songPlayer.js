// 歌曲播放器：同時播放「伴奏」和「導唱人聲」，兩個保持同步。
//
// 聲音的路線：
//   伴奏 → musicGain ─┐
//                    ├→ master → output（總音量）→ 喇叭
//   人聲 → vocalTap → guideGain ┘
// vocalTap 是給「測試模式」用的：把原唱人聲直接送進音高偵測（不受導唱音量影響）。
// 錄音是從 master 接出去的，所以「總音量」只影響你聽到的大小，不影響錄音。

import { t } from '../i18n.js';

export class SongPlayer {
  constructor(context) {
    this.context = context;
    this.instrumentalBuffer = null;
    this.vocalsBuffer = null;

    this.output = context.createGain();
    this.output.connect(context.destination);

    this.master = context.createGain();
    this.master.connect(this.output);

    this.musicGain = context.createGain();
    this.musicGain.connect(this.master);

    this.guideGain = context.createGain();
    this.guideGain.gain.value = 0;
    this.guideGain.connect(this.master);

    this.vocalTap = context.createGain();
    this.vocalTap.connect(this.guideGain);

    this.sources = [];
    this.playing = false;
    this.offset = 0;       // 暫停時停在第幾秒
    this.startedAt = 0;    // 開始播放時，AudioContext 的時間 - 歌曲秒數
    this.onEnded = null;   // 歌曲播完時要做的事
  }

  // 下載並解碼音訊。onProgress(0~1) 用來顯示進度
  async load(instrumentalUrl, vocalsUrl, onProgress) {
    const self = this;
    function report(part, ratio) {
      if (onProgress) {
        if (vocalsUrl) {
          onProgress(part * 0.5 + ratio * 0.5);
        } else {
          onProgress(ratio);
        }
      }
    }
    this.instrumentalBuffer = await loadAudioBuffer(this.context, instrumentalUrl, function (ratio) {
      report(0, ratio);
    });
    if (vocalsUrl) {
      this.vocalsBuffer = await loadAudioBuffer(this.context, vocalsUrl, function (ratio) {
        report(1, ratio);
      });
    }
    return self;
  }

  getDuration() {
    if (this.instrumentalBuffer) {
      return this.instrumentalBuffer.duration;
    }
    return 0;
  }

  hasVocals() {
    return this.vocalsBuffer !== null;
  }

  play() {
    if (this.playing) {
      return;
    }
    const startTime = this.context.currentTime + 0.05;
    this.startSource(this.instrumentalBuffer, this.musicGain, startTime);
    if (this.vocalsBuffer) {
      this.startSource(this.vocalsBuffer, this.vocalTap, startTime);
    }
    this.startedAt = startTime - this.offset;
    this.playing = true;
  }

  startSource(buffer, destination, startTime) {
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(destination);
    const self = this;
    source.onended = function () {
      // 只有「真的播完」才算結束（按暫停也會觸發 onended）
      if (self.playing && self.getTime() >= self.getDuration() - 0.1) {
        self.playing = false;
        self.offset = self.getDuration();
        if (self.onEnded) {
          self.onEnded();
        }
      }
    };
    source.start(startTime, Math.max(0, this.offset));
    this.sources.push(source);
  }

  stopSources() {
    for (const source of this.sources) {
      source.onended = null;
      try {
        source.stop();
      } catch (error) {
        // 已經停了
      }
      source.disconnect();
    }
    this.sources = [];
  }

  pause() {
    if (!this.playing) {
      return;
    }
    this.offset = this.getTime();
    this.playing = false;
    this.stopSources();
  }

  seek(time) {
    const wasPlaying = this.playing;
    this.pause();
    this.offset = Math.max(0, Math.min(time, this.getDuration() - 0.1));
    if (wasPlaying) {
      this.play();
    }
  }

  stop() {
    this.pause();
    this.offset = 0;
  }

  // 現在播到歌曲的第幾秒
  getTime() {
    if (this.playing) {
      return this.context.currentTime - this.startedAt;
    }
    return this.offset;
  }

  // AudioContext 的時間 → 歌曲的秒數
  contextTimeToSongTime(contextTime) {
    return contextTime - this.startedAt;
  }

  setMusicVolume(percent) {
    this.musicGain.gain.value = percent / 100;
  }

  setGuideVolume(percent) {
    this.guideGain.gain.value = percent / 100;
  }

  // 總音量：你聽到的整體大小（0~100）
  setMasterVolume(percent) {
    this.output.gain.value = percent / 100;
  }

  destroy() {
    this.stopSources();
    this.master.disconnect();
    this.output.disconnect();
  }
}

// 下載一個音訊檔並轉成可以播放的 AudioBuffer
async function loadAudioBuffer(context, url, onProgress) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(t('音訊下載失敗：{url}', { url: url }));
  }
  const total = Number(response.headers.get('Content-Length')) || 0;
  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;
  while (true) {
    const result = await reader.read();
    if (result.done) {
      break;
    }
    chunks.push(result.value);
    received += result.value.length;
    if (total > 0 && onProgress) {
      onProgress(received / total);
    }
  }
  const bytes = new Uint8Array(received);
  let position = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, position);
    position += chunk.length;
  }
  return await context.decodeAudioData(bytes.buffer);
}
