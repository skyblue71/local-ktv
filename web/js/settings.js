// 使用者設定：存在瀏覽器裡（localStorage），下次開啟還在。

const STORAGE_KEY = 'karaoke-settings';

// 所有設定和它們的預設值
const DEFAULT_SETTINGS = {
  playerName: '我',        // 分數紀錄上的名字
  micId: '',               // 麥克風（空白 = 系統預設）
  latencyMs: 0,            // 額外延遲補償（毫秒），唱的時間被判太慢就調大
  difficulty: 'normal',    // easy / normal / hard
  octaveFree: true,        // 唱高八度、低八度也算對（男生唱女生的歌）
  quietDb: 12,             // 清掉小聲雜音：句尾、字和字中間的聲音，比歌聲小這麼多 dB 以上就不畫評分條（0 = 不清）
                           //   21 首歌實測：真的在唱的拉長音最多小 4.1 dB；
                           //   一個字尾的 s 小 23.6 dB；其他雜音小 12.5～28 dB
                           //   → 預設 12（耳朵聽起來不到一半大聲；每小 10 dB 聽起來大約小一半）。改了下次進唱歌、修譜就生效（game\quietParts.js）
  talkBars: true,          // 講話、rap、喊叫的地方（歌詞有字、有人聲，但量不到穩定的音高）也畫評分條：
                           //   這種評分條只看有沒有出聲，不看音高（game\talkBars.js）
  showRuby: true,          // 日文：漢字上方的假名
  showRoma: true,          // 日文/韓文：下方的羅馬音
  chineseStyle: 'zhuyin',  // 中文：'zhuyin' 上方注音 / 'pinyin' 下方拼音 / 'none' 不顯示
  masterVolume: 60,        // 總音量 0~100：你聽到的整體大小（不影響錄音）
  guideVolume: 0,          // 導唱（原唱人聲）音量 0~100（0 = 關掉）
  guideLastVolume: 70,     // 按「導唱」打開時，要開到多大聲（記住上次的音量）
  musicVolume: 100,        // 伴奏音量 0~100
  echoCancel: false,       // 迴音消除（用喇叭時開啟，用耳機時關閉比較準）
  micGate: 0.006,          // 麥克風靈敏度門檻（越小越靈敏）
  monitor: false,          // 耳返：從耳機聽到自己的聲音
  monitorVolume: 80,
  reverb: 30,              // 迴音效果 0~100
  record: true,            // 唱歌時錄音
  countdown: true,         // 按「開始」後先倒數 3、2、1
  showMV: true,            // 有影片的歌，唱歌時背景播 MV
  mvBrightness: 45,        // MV 亮度 10~100（太亮會看不清楚字幕）
  showSpectrum: true,      // 唱歌畫面最下面那排跟著音樂跳的柱子（只是好看，不影響分數）
  language: 'auto',        // 介面語言：'auto' 跟瀏覽器走，或是 i18n.js 的 LANGUAGES 裡的代號（'zh'、'en'）
  addSongTab: 'file',      // 「加入歌曲」上次用的是哪一頁：'file' 電腦檔案 / 'youtube'（下次打開直接是那一頁）
};

export function loadSettings() {
  let saved = {};
  try {
    const text = localStorage.getItem(STORAGE_KEY);
    if (text) {
      saved = JSON.parse(text);
    }
  } catch (error) {
    saved = {};
  }

  const settings = {};
  for (const key in DEFAULT_SETTINGS) {
    if (saved[key] !== undefined) {
      settings[key] = saved[key];
    } else {
      settings[key] = DEFAULT_SETTINGS[key];
    }
  }
  return settings;
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    // 瀏覽器不讓存的話就算了，只是下次要重設
  }
}
