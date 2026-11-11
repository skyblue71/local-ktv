// 英文對照表：左邊是程式裡寫的中文，右邊是英文。
// 照畫面分成幾個檔案放在 lang/en/ 裡，這裡合成一份。
// 每一筆寫成一行：  '中文': 'English',

import { CHART } from './en/chart.js';
import { COMMON } from './en/common.js';
import { LIBRARY } from './en/library.js';
import { LYRICS } from './en/lyrics.js';
import { SERVER } from './en/server.js';
import { SING } from './en/sing.js';
import { SONG } from './en/song.js';

export const EN = Object.assign({}, COMMON, LIBRARY, SONG, LYRICS, CHART, SING, SERVER);
