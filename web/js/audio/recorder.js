// 錄音：把「伴奏 + 你的歌聲」一起錄下來，唱完可以重聽或下載。

export class Recorder {
  constructor(context) {
    this.context = context;
    this.destination = context.createMediaStreamDestination();
    this.mediaRecorder = null;
    this.chunks = [];
    this.mimeType = '';
  }

  // 把要錄的聲音接進來（可以接很多個）
  addInput(node) {
    node.connect(this.destination);
  }

  start() {
    const choices = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'];
    this.mimeType = '';
    for (const choice of choices) {
      if (MediaRecorder.isTypeSupported(choice)) {
        this.mimeType = choice;
        break;
      }
    }
    const options = {};
    if (this.mimeType) {
      options.mimeType = this.mimeType;
    }
    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(this.destination.stream, options);
    const self = this;
    this.mediaRecorder.ondataavailable = function (event) {
      if (event.data && event.data.size > 0) {
        self.chunks.push(event.data);
      }
    };
    this.mediaRecorder.start(1000);
  }

  pause() {
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.mediaRecorder.pause();
    }
  }

  resume() {
    if (this.mediaRecorder && this.mediaRecorder.state === 'paused') {
      this.mediaRecorder.resume();
    }
  }

  // 停止錄音，回傳錄好的檔案（Blob）
  stop() {
    const self = this;
    return new Promise(function (resolve) {
      if (!self.mediaRecorder || self.mediaRecorder.state === 'inactive') {
        resolve(null);
        return;
      }
      self.mediaRecorder.onstop = function () {
        resolve(new Blob(self.chunks, { type: self.mimeType || 'audio/webm' }));
      };
      self.mediaRecorder.stop();
    });
  }
}
