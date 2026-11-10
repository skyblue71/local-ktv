// 音樂頻譜：聽「現在正在播的音樂」，算出低音到高音各有多大聲，
// 給唱歌畫面畫一排跟著音樂跳的柱子（只管好不好看，不影響聲音、不影響評分）。
//
// 做法：在播放器的 master 旁邊多接一個「分析器」（AnalyserNode）。
//   分析器只是在旁邊聽，不會改到聲音，也不會多出聲音。
//   master 在「總音量」的前面，所以把總音量關到 0，柱子還是會跳。
//
// 用法：
//   const spectrum = new MusicSpectrum(context, player.master);
//   const levels = spectrum.read();   // 每個畫面呼叫一次，回傳 BAR_COUNT 個 0～1 的數字（左邊低音、右邊高音）
//   spectrum.destroy();               // 離開頁面時

const BAR_COUNT = 56;      // 幾根柱子
const FFT_SIZE = 2048;     // 分析的細緻度（越大，低音分得越細）
const LOW_HZ = 50;         // 最左邊那根柱子從幾赫茲開始
const HIGH_HZ = 10000;     // 最右邊那根柱子到幾赫茲
const SMOOTHING = 0.72;    // 0～1，越大柱子動得越慢、越平順
const QUIET_DB = -80;      // 比這個小聲（分貝）的柱子高度算 0
const LOUD_DB = -18;       // 這麼大聲（分貝）柱子就到頂。兩個數字拉開一點，大聲的歌才不會每根都頂到最高

export class MusicSpectrum {
  constructor(context, source) {
    this.source = source;
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = FFT_SIZE;
    this.analyser.smoothingTimeConstant = SMOOTHING;
    this.analyser.minDecibels = QUIET_DB;
    this.analyser.maxDecibels = LOUD_DB;
    source.connect(this.analyser);

    this.bins = new Uint8Array(this.analyser.frequencyBinCount);
    this.levels = [];
    this.ranges = [];   // 每根柱子管分析結果的第幾格到第幾格

    // 照「倍數」分：低音每根柱子管的赫茲少、高音管的多（人的耳朵也是這樣聽的）
    const hzPerBin = context.sampleRate / FFT_SIZE;
    const lastBin = this.bins.length - 1;
    for (let i = 0; i < BAR_COUNT; i++) {
      const fromHz = LOW_HZ * Math.pow(HIGH_HZ / LOW_HZ, i / BAR_COUNT);
      const toHz = LOW_HZ * Math.pow(HIGH_HZ / LOW_HZ, (i + 1) / BAR_COUNT);
      const from = Math.min(lastBin, Math.floor(fromHz / hzPerBin));
      const to = Math.min(lastBin, Math.max(from, Math.ceil(toHz / hzPerBin) - 1));
      this.ranges.push([from, to]);
      this.levels.push(0);
    }
  }

  // 現在每根柱子多高（0～1）
  read() {
    this.analyser.getByteFrequencyData(this.bins);
    for (let i = 0; i < this.ranges.length; i++) {
      const range = this.ranges[i];
      let loudest = 0;
      for (let bin = range[0]; bin <= range[1]; bin++) {
        if (this.bins[bin] > loudest) {
          loudest = this.bins[bin];
        }
      }
      this.levels[i] = loudest / 255;
    }
    return this.levels;
  }

  destroy() {
    try {
      this.source.disconnect(this.analyser);
    } catch (error) {
      // 已經拔掉了
    }
  }
}
