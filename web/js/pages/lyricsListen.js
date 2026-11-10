// 選歌詞時的「▶ 試聽」：從第一句前面開始播原曲，畫面跟著跑「這一份」的字幕。
// 一邊聽一邊看：歌手開口時字幕剛好出來，就是準的。
//
// 用法：
//   const listen = new LyricsListen(song);
//   listen.start(lrc 文字, 那一筆的元素);   // 試聽框會出現在那一筆下面
//   listen.stop();                          // 停止、收起試聽框
//   listen.destroy();                       // 離開頁面時呼叫
//
// 字幕是伺服器照這首歌的設定（自動對齊、裁切）做的，跟按「使用」之後唱歌時一模一樣，但不會存檔。
// 不加整體偏移：按「使用」換歌詞時偏移會歸零（舊的偏移是給舊歌詞用的）。

import * as api from '../api.js';
import { getAudioContext, getOutputLatency } from '../audio/audioContext.js';
import { SongPlayer } from '../audio/songPlayer.js';
import { LyricsView } from '../game/lyricsView.js';
import { applyQuietSetting } from '../game/quietParts.js';
import { trimStart } from '../game/trimRange.js';
import { icon } from '../icons.js';
import { loadSettings } from '../settings.js';
import { escapeHtml, formatTime } from '../ui.js';

const LEAD_IN = 3;   // 從第一句前面幾秒開始播（先聽一點前奏，才知道字幕有沒有太早出來）

export class LyricsListen {
  constructor(song) {
    this.song = song;
    this.player = null;
    this.loading = null;     // 正在載入音樂（載過一次，換別份試聽就不用再載）
    this.box = null;         // 試聽框
    this.view = null;        // 字幕
    this.animation = 0;
    this.seeking = false;    // 正在拖進度條
    this.turn = 0;           // 第幾次按試聽（按很快的時候，舊的那次就不要了）
    this.destroyed = false;
  }

  // 載入伴奏＋原唱（只載一次）
  async loadPlayer() {
    if (this.loading === null) {
      const player = new SongPlayer(getAudioContext());
      let vocalsUrl = null;
      if (this.song.has_vocals) {
        vocalsUrl = api.audioUrl(this.song.id, 'vocals');
      }
      this.loading = player.load(api.audioUrl(this.song.id, 'instrumental'), vocalsUrl);
    }
    const player = await this.loading;
    if (this.destroyed) {
      player.destroy();
      throw new Error('已經離開這一頁');
    }
    player.setGuideVolume(100);   // 要聽得到原唱，才知道字幕準不準
    this.player = player;
    return player;
  }

  async start(lrcText, row) {
    this.stop();
    const myTurn = this.turn;

    const box = document.createElement('div');
    box.className = 'listen-box';
    box.innerHTML = '<p class="muted small">載入中…</p>';
    row.after(box);
    this.box = box;
    box.scrollIntoView({ block: 'nearest' });

    let lyrics = null;
    try {
      await getAudioContext().resume();   // 瀏覽器規定：要按了按鈕才能出聲
      // 不加你設的整體偏移：按「使用」換成這份時偏移會歸零，試聽看到的才會一樣
      const answer = await api.previewLyrics(this.song.id, lrcText, true);
      lyrics = answer.lyrics;
      await this.loadPlayer();
    } catch (error) {
      if (this.player === null) {
        this.loading = null;   // 下次再試著載一次
      }
      if (myTurn === this.turn) {
        box.innerHTML = '<p class="muted small">沒辦法試聽：' + escapeHtml(error.message) + '</p>';
      }
      return;
    }
    if (myTurn !== this.turn) {
      return;   // 載入的時候又按了別的
    }
    this.play(lyrics);
  }

  play(lyrics) {
    const self = this;
    const player = this.player;
    const settings = loadSettings();
    player.setMasterVolume(settings.masterVolume);
    lyrics = applyQuietSetting(lyrics, settings.quietDb);   // 字幕填色跟唱歌時一樣

    let begin = trimStart(this.song);
    if (lyrics.lines.length > 0) {
      begin = Math.max(begin, lyrics.lines[0].start - LEAD_IN);
    }

    this.box.innerHTML =
      '<div class="listen-lyrics"></div>' +
      '<div class="listen-controls">' +
      '  <span class="listen-time">' + formatTime(begin) + '</span>' +
      '  <input type="range" class="listen-seek" min="0" max="' + player.getDuration().toFixed(1) +
      '" step="0.1" value="' + begin.toFixed(1) + '" title="拖到想聽的地方">' +
      '  <button type="button" class="btn btn-icon listen-stop" title="停止" aria-label="停止">' + icon('stop') + '</button>' +
      '</div>';
    this.view = new LyricsView(this.box.querySelector('.listen-lyrics'), lyrics, settings);

    const timeLabel = this.box.querySelector('.listen-time');
    const seekBar = this.box.querySelector('.listen-seek');
    seekBar.addEventListener('input', function () {
      self.seeking = true;
      timeLabel.textContent = formatTime(Number(seekBar.value));
    });
    seekBar.addEventListener('change', function () {
      self.seeking = false;
      player.seek(Number(seekBar.value));
    });
    this.box.querySelector('.listen-stop').addEventListener('click', function () {
      self.stop();
    });

    player.onEnded = function () {
      self.stop();
    };
    player.seek(begin);
    player.play();

    let lastText = '';
    let scrolled = false;
    function frame() {
      if (self.view === null) {
        return;
      }
      self.animation = requestAnimationFrame(frame);
      let now = player.getTime();
      if (player.playing) {
        now -= getOutputLatency();   // 畫面配合「你聽到的」時間（跟唱歌時一樣）
      }
      self.view.update(now);
      if (!scrolled) {
        // 第一次放上字幕後，試聽框才是完整的高度，這時再把它整個捲進畫面裡
        scrolled = true;
        self.box.scrollIntoView({ block: 'nearest' });
      }
      if (!self.seeking) {
        seekBar.value = now.toFixed(1);
        const text = formatTime(now);
        if (text !== lastText) {
          lastText = text;
          timeLabel.textContent = text;
        }
      }
    }
    this.animation = requestAnimationFrame(frame);
  }

  // 停止、收起試聽框（音樂留著，下次試聽不用再載）
  stop() {
    this.turn++;
    if (this.animation) {
      cancelAnimationFrame(this.animation);
      this.animation = 0;
    }
    if (this.player) {
      this.player.onEnded = null;
      this.player.pause();
    }
    if (this.box) {
      this.box.remove();
      this.box = null;
    }
    this.view = null;
    this.seeking = false;
  }

  destroy() {
    this.stop();
    this.destroyed = true;
    if (this.player) {
      this.player.destroy();
      this.player = null;
    }
  }
}
