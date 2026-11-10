// 修譜時「評分條的音」：播放的時候，播到哪個評分條就發出那個音（嗶～），
// 跟原唱一起聽，就知道評分條的音高、長短對不對。

const TONE_LEVEL = 0.18;   // 音量（跟總音量相乘）

// 音高編號 → 頻率（69 = A4 = 440Hz）
function midiToFrequency(midi) {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

export class NoteTone {
  constructor(context) {
    this.context = context;
    this.gain = context.createGain();
    this.gain.gain.value = 0;
    this.gain.connect(context.destination);
    this.oscillator = context.createOscillator();
    this.oscillator.type = 'triangle';   // 比純正弦波好聽一點、又不刺耳
    this.oscillator.connect(this.gain);
    this.oscillator.start();
    this.level = TONE_LEVEL;
  }

  // 總音量（0~100）
  setMasterVolume(percent) {
    this.level = TONE_LEVEL * percent / 100;
  }

  // 每個畫面呼叫：time 這個時間有評分條就發出那個音，沒有（或 on = false）就安靜
  update(time, notes, on) {
    let current = null;
    if (on) {
      for (const note of notes) {
        if (note.s > time) {
          break;
        }
        if (time < note.e) {
          current = note;
        }
      }
    }
    const now = this.context.currentTime;
    if (current !== null) {
      this.oscillator.frequency.setTargetAtTime(midiToFrequency(current.p), now, 0.01);
      this.gain.gain.setTargetAtTime(this.level, now, 0.015);
    } else {
      this.gain.gain.setTargetAtTime(0, now, 0.02);
    }
  }

  destroy() {
    this.oscillator.stop();
    this.oscillator.disconnect();
    this.gain.disconnect();
  }
}
