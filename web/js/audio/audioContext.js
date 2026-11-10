// 整個網頁共用同一個 AudioContext（音訊引擎）。
// 播放音樂和麥克風用同一個，時間才能對得準。

let context = null;

export function getAudioContext() {
  if (context === null) {
    context = new AudioContext({ latencyHint: 'interactive' });
  }
  return context;
}

// 喇叭/耳機輸出的延遲（秒）
export function getOutputLatency() {
  const ctx = getAudioContext();
  let latency = 0;
  if (ctx.outputLatency) {
    latency += ctx.outputLatency;
  }
  if (ctx.baseLatency) {
    latency += ctx.baseLatency;
  }
  return latency;
}
