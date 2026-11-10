// 這個檔案在「音訊執行緒」(AudioWorklet) 裡執行，負責即時偵測你唱的音高。
// 使用 YIN 演算法：找出聲音波形「多久重複一次」，就能算出頻率。
//
// 每大約 10 毫秒會送出一筆資料給主畫面：
//   { time: 時間(秒), freq: 頻率(Hz，0 代表沒聲音), clarity: 清晰度 0~1, rms: 音量 }

const WINDOW = 1024;     // 每次分析多少個取樣點（降取樣後，約 0.04 秒）
const STEP = 256;        // 每隔多少個取樣點分析一次（約 0.01 秒）
const THRESHOLD = 0.15;  // YIN 門檻：越小越嚴格
// 真人的聲音（有氣音、殘響、和聲）常常達不到上面的門檻。
// 這時候改用「最像的那一點」，只要低於這個值就採用
const FALLBACK = 0.5;
// 次諧波修正：抓到的週期如果是真正週期的 2~6 倍（聽成低好幾度的怪音），
// 檢查「週期 ÷ k」那一點，只要沒有比原本差超過這個值，就改用比較短的週期
const SUBHARMONIC_MARGIN = 0.2;
// 倍頻加總（和聲修正）：兩個音疊在一起（例如主唱 D4 + 和聲 G4），
// 波形要很久才重複一次，YIN 會抓到一個「根本沒有聲音」的低音（G2）。
// 這時候基音幾乎沒聲音，就改看「誰的倍頻加起來最強」。
// （跟 server\browser_ear.py 一樣，改一邊就要改另一邊）
const WEAK_BASE = 0.1;        // 基音不到最強倍頻的 1/10（-20dB）= 基音不見了
const MAX_K = 6;              // 候選音：YIN 的頻率 ×1 ~ ×6
const HARMONICS = 5;          // 每個候選音看 5 個倍頻
const HARMONIC_WEIGHT = 0.8;  // 越高的倍頻越不重要（第 h 個 × 0.8^(h-1)）
const CONTINUITY = 0.8;       // 跟上一格差 1 個半音以內的候選音，分數有最高分的 0.8 倍就選它（線比較連續）

class PitchProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 降取樣成一半（48000 → 24000），計算量變少很多
    this.rate = sampleRate / 2;
    this.buffer = new Float32Array(WINDOW);
    this.pending = new Float32Array(STEP);
    this.pendingCount = 0;
    this.previousSample = 0;
    this.isOddSample = false;

    this.minLag = Math.floor(this.rate / 1100);  // 最高音 1100Hz
    this.maxLag = Math.floor(this.rate / 60);    // 最低音 60Hz
    this.difference = new Float32Array(this.maxLag + 1);

    // 倍頻加總用：Hann 窗，和「乘上窗之後的聲音」
    this.hann = new Float64Array(WINDOW);
    for (let i = 0; i < WINDOW; i++) {
      this.hann[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (WINDOW - 1));
    }
    this.weighted = new Float64Array(WINDOW);
    this.lastFreq = 0;  // 上一格的結果（0 = 沒聲音），倍頻加總的「連續性」用

    this.gate = 0.006;  // 小於這個音量就當作沒在唱
    const self = this;
    this.port.onmessage = function (event) {
      if (event.data.gate !== undefined) {
        self.gate = event.data.gate;
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }
    const channel = input[0];
    for (let i = 0; i < channel.length; i++) {
      // 每兩個取樣點平均成一個
      if (this.isOddSample) {
        this.addSample((this.previousSample + channel[i]) * 0.5, i);
        this.isOddSample = false;
      } else {
        this.previousSample = channel[i];
        this.isOddSample = true;
      }
    }
    return true;
  }

  addSample(value, indexInBlock) {
    this.pending[this.pendingCount] = value;
    this.pendingCount++;
    if (this.pendingCount < STEP) {
      return;
    }
    // 舊的資料往前挪，新的放後面
    this.buffer.copyWithin(0, STEP);
    this.buffer.set(this.pending, WINDOW - STEP);
    this.pendingCount = 0;

    // 這一段聲音「中間」的時間點
    const endTime = (currentFrame + indexInBlock + 1) / sampleRate;
    const centerTime = endTime - (WINDOW / 2) / this.rate;
    this.analyze(centerTime);
  }

  analyze(time) {
    const x = this.buffer;

    // 1. 音量（RMS）
    let sum = 0;
    for (let i = 0; i < WINDOW; i++) {
      sum += x[i] * x[i];
    }
    const rms = Math.sqrt(sum / WINDOW);
    if (rms < this.gate) {
      this.lastFreq = 0;
      this.port.postMessage({ time: time, freq: 0, clarity: 0, rms: rms });
      return;
    }

    // 2. 差異函式：波形跟「往後移 lag 格的自己」差多少
    const d = this.difference;
    const length = WINDOW - this.maxLag;
    for (let lag = 1; lag <= this.maxLag; lag++) {
      let total = 0;
      for (let j = 0; j < length; j++) {
        const diff = x[j] - x[j + lag];
        total += diff * diff;
      }
      d[lag] = total;
    }

    // 3. 正規化（YIN 的關鍵步驟）
    d[0] = 1;
    let running = 0;
    for (let lag = 1; lag <= this.maxLag; lag++) {
      running += d[lag];
      if (running === 0) {
        d[lag] = 1;
      } else {
        d[lag] = d[lag] * lag / running;
      }
    }

    // 4. 找第一個低於門檻的「谷底」
    let best = -1;
    for (let lag = this.minLag; lag <= this.maxLag; lag++) {
      if (d[lag] < THRESHOLD) {
        while (lag + 1 <= this.maxLag && d[lag + 1] < d[lag]) {
          lag++;
        }
        best = lag;
        break;
      }
    }
    // 4-1. 找不到的話，改用最低的那一點（夠低才算）
    if (best === -1) {
      let lowest = this.minLag;
      for (let lag = this.minLag; lag <= this.maxLag; lag++) {
        if (d[lag] < d[lowest]) {
          lowest = lag;
        }
      }
      if (d[lowest] < FALLBACK) {
        best = lowest;
      }
    }
    if (best === -1) {
      this.lastFreq = 0;
      this.port.postMessage({ time: time, freq: 0, clarity: 0, rms: rms });
      return;
    }
    // 4-2. 次諧波修正
    best = this.fixSubharmonic(best);

    // 5. 拋物線內插，讓結果更精確
    let betterLag = best;
    if (best > 1 && best < this.maxLag) {
      const a = d[best - 1];
      const b = d[best];
      const c = d[best + 1];
      const bottom = a + c - 2 * b;
      if (bottom !== 0) {
        betterLag = best + (a - c) / (2 * bottom);
      }
    }

    // 6. 和聲修正：基音不見了的話，改用倍頻加總最強的那個音
    const k = this.chooseHarmonic(best);
    const freq = this.rate / betterLag * k;
    this.lastFreq = freq;

    this.port.postMessage({
      time: time,
      freq: freq,
      clarity: 1 - d[best],
      rms: rms,
    });
  }

  // 某個頻率有多強（振幅）：Goertzel 演算法，只算一個頻率的傅立葉轉換
  strengthAt(hz) {
    if (hz >= this.rate / 2) {
      return 0;
    }
    const coeff = 2 * Math.cos(2 * Math.PI * hz / this.rate);
    let s1 = 0;
    let s2 = 0;
    for (let i = 0; i < WINDOW; i++) {
      const s = this.weighted[i] + coeff * s1 - s2;
      s2 = s1;
      s1 = s;
    }
    const power = s1 * s1 + s2 * s2 - coeff * s1 * s2;
    return Math.sqrt(Math.max(0, power));
  }

  // 倍頻加總：回傳 k，真正的音高 = YIN 的頻率 × k（大部分時候 k = 1，不改）
  // 只有「基音幾乎沒聲音」時才比：每個候選音把自己的倍頻強度加起來，最強的就是主唱
  chooseHarmonic(lag) {
    for (let i = 0; i < WINDOW; i++) {
      this.weighted[i] = this.buffer[i] * this.hann[i];
    }
    const baseHz = this.rate / lag;
    const strengths = [0];   // strengths[m] = 頻率 × m 有多強
    for (let m = 1; m <= MAX_K; m++) {
      strengths.push(this.strengthAt(baseHz * m));
    }
    let strongest = 0;
    for (let m = 2; m <= MAX_K; m++) {
      strongest = Math.max(strongest, strengths[m]);
    }
    if (strongest <= 0 || strengths[1] >= strongest * WEAK_BASE) {
      return 1;   // 基音有聲音：YIN 是對的
    }
    for (let m = MAX_K + 1; m <= MAX_K * HARMONICS; m++) {
      strengths.push(this.strengthAt(baseHz * m));
    }
    const scores = [0];   // scores[k] = 候選音 × k 的倍頻加總
    let bestK = 1;
    for (let k = 1; k <= MAX_K; k++) {
      if (lag / k < this.minLag) {
        break;
      }
      let score = 0;
      for (let h = 1; h <= HARMONICS; h++) {
        score += strengths[k * h] * Math.pow(HARMONIC_WEIGHT, h - 1);
      }
      scores.push(score);
      if (score > scores[bestK]) {
        bestK = k;
      }
    }
    // 連續性：跟上一格接近（1 個半音以內）的候選音，分數夠高就選它
    if (this.lastFreq > 0) {
      for (let k = 1; k < scores.length; k++) {
        const close = Math.abs(12 * Math.log2(baseHz * k / this.lastFreq)) <= 1;
        if (close && scores[k] >= scores[bestK] * CONTINUITY) {
          return k;
        }
      }
    }
    return bestK;
  }

  // 聲音每隔 T 重複一次，當然每隔 2T、3T 也會重複，YIN 有時會抓到 3T（聽成怪音）。
  // 從「除以 6」開始檢查到「除以 2」，第一個夠低的就是真正的週期（最短的那個）
  fixSubharmonic(best) {
    const d = this.difference;
    for (let k = 6; k >= 2; k--) {
      const candidate = Math.round(best / k);
      if (candidate < this.minLag) {
        continue;
      }
      // 在 candidate 附近（±3%）找最低點
      const radius = Math.max(1, Math.round(candidate * 0.03));
      let lag = -1;
      for (let i = Math.max(this.minLag, candidate - radius); i <= Math.min(this.maxLag, candidate + radius); i++) {
        if (lag === -1 || d[i] < d[lag]) {
          lag = i;
        }
      }
      if (lag !== -1 && d[lag] <= d[best] + SUBHARMONIC_MARGIN) {
        return lag;
      }
    }
    return best;
  }
}

registerProcessor('pitch-processor', PitchProcessor);
