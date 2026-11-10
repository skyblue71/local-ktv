// 麥克風：開啟麥克風 → 送進音高偵測（pitch-worklet.js）→ 每 10 毫秒回報一次音高。
// 也負責「耳返」（從耳機聽到自己的聲音，可加回音效果）。
//
// 未來要共唱時：每一位歌手建立一個 Microphone（選不同的麥克風）就可以了。

let workletReady = null;

function loadWorklet(context) {
  if (workletReady === null) {
    workletReady = context.audioWorklet.addModule('js/audio/pitch-worklet.js');
  }
  return workletReady;
}

// 做一個「迴音」效果用的聲音樣本（越來越小聲的雜訊）
function makeReverbImpulse(context, seconds) {
  const length = Math.floor(context.sampleRate * seconds);
  const impulse = context.createBuffer(2, length, context.sampleRate);
  for (let channel = 0; channel < 2; channel++) {
    const data = impulse.getChannelData(channel);
    for (let i = 0; i < length; i++) {
      const fade = Math.pow(1 - i / length, 3);
      data[i] = (Math.random() * 2 - 1) * fade;
    }
  }
  return impulse;
}

export class Microphone {
  constructor(context) {
    this.context = context;
    this.stream = null;
    this.input = null;
    this.detector = null;
    this.onPitch = null;      // 收到音高時要做的事 function(frame)
    this.level = 0;           // 最近的音量（畫音量條用）
    this.inputLatency = 0;
    this.simulated = false;

    // 人聲混音：乾聲 + 迴音
    this.voiceMix = context.createGain();
    this.monitorGain = context.createGain();
    this.monitorGain.gain.value = 0;
    this.voiceMix.connect(this.monitorGain);
    this.monitorGain.connect(context.destination);

    this.reverbGain = context.createGain();
    this.reverbGain.gain.value = 0.3;
    this.convolver = context.createConvolver();
    this.convolver.buffer = makeReverbImpulse(context, 2.0);
    this.convolver.connect(this.reverbGain);
    this.reverbGain.connect(this.voiceMix);
  }

  // 開啟真的麥克風
  async start(deviceId, echoCancel) {
    await loadWorklet(this.context);
    const constraints = {
      audio: {
        echoCancellation: echoCancel,
        noiseSuppression: false,   // 關掉降噪，音高才準
        autoGainControl: false,
      },
    };
    if (deviceId) {
      constraints.audio.deviceId = { exact: deviceId };
    }
    this.stream = await navigator.mediaDevices.getUserMedia(constraints);
    const track = this.stream.getAudioTracks()[0];
    const trackSettings = track.getSettings();
    if (trackSettings.latency) {
      this.inputLatency = trackSettings.latency;
    }

    this.input = this.context.createMediaStreamSource(this.stream);
    this.input.connect(this.voiceMix);
    this.input.connect(this.convolver);
    this.connectDetector(this.input);
    this.simulated = false;
  }

  // 測試模式：不用麥克風，改用原唱人聲
  async startSimulation(sourceNode) {
    await loadWorklet(this.context);
    this.input = sourceNode;
    this.connectDetector(sourceNode);
    this.inputLatency = 0;
    this.simulated = true;
  }

  connectDetector(node) {
    this.detector = new AudioWorkletNode(this.context, 'pitch-processor');
    node.connect(this.detector);
    // 接一個音量 0 的出口，確保瀏覽器會一直執行它
    const silent = this.context.createGain();
    silent.gain.value = 0;
    this.detector.connect(silent);
    silent.connect(this.context.destination);
    this.silent = silent;

    const self = this;
    this.detector.port.onmessage = function (event) {
      const frame = event.data;
      self.level = frame.rms;
      if (self.onPitch) {
        self.onPitch(frame);
      }
    };
  }

  // 靈敏度門檻
  setGate(value) {
    if (this.detector) {
      this.detector.port.postMessage({ gate: value });
    }
  }

  // 耳返設定：enabled 開關、volume 0~100、reverb 0~100
  setMonitor(enabled, volume, reverb) {
    if (enabled && !this.simulated) {
      this.monitorGain.gain.value = volume / 100;
    } else {
      this.monitorGain.gain.value = 0;
    }
    this.reverbGain.gain.value = reverb / 100;
  }

  // 給錄音用的「人聲」輸出
  getVoiceOutput() {
    return this.voiceMix;
  }

  stop() {
    if (this.stream) {
      for (const track of this.stream.getTracks()) {
        track.stop();
      }
      this.stream = null;
    }
    if (this.detector) {
      if (this.input) {
        try {
          this.input.disconnect(this.detector);
        } catch (error) {
          // 已經斷開了
        }
      }
      this.detector.port.onmessage = null;
      this.detector.disconnect();
      this.detector = null;
    }
    if (this.silent) {
      this.silent.disconnect();
    }
    if (this.input && !this.simulated) {
      this.input.disconnect();
    }
    this.input = null;
    this.voiceMix.disconnect();
    this.monitorGain.disconnect();
  }
}

// 列出電腦上的麥克風
export async function listMicrophones() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const result = [];
  for (const device of devices) {
    if (device.kind === 'audioinput') {
      result.push({ id: device.deviceId, name: device.label || '麥克風 ' + (result.length + 1) });
    }
  }
  return result;
}
