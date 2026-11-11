// 英文對照表：伺服器傳來的字：處理進度、錯誤訊息
// 每一筆寫成一行：  '中文': 'English',
// 會變的數字寫成 {n}；結尾是「：」的是一句話的前半段，後半段會另外查（i18n.js 的 tServer）

export const SERVER = {
  // 處理進度（server/song_processor.py、job_queue.py）
  '排隊中': 'Waiting',
  '讀取 YouTube 影片': 'Reading the YouTube video',
  '從 YouTube 下載畫面 {n}%': 'Downloading video from YouTube {n}%',
  '從 YouTube 下載聲音 {n}%': 'Downloading audio from YouTube {n}%',
  '轉換音訊格式': 'Converting audio',
  'AI 分離人聲與伴奏': 'AI separating vocals and backing track',
  '準備伴奏': 'Preparing the backing track',
  '分析旋律音高': 'Analyzing the melody',
  'AI 認音節': 'AI syllable timing',
  '搜尋歌詞': 'Searching for lyrics',
  '生成字幕與羅馬音': 'Building lyrics and romaji',
  '完成': 'Done',
  '處理失敗': 'Processing failed',

  // 歌詞是哪裡來的
  '手動輸入': 'Entered by hand',

  // 錯誤訊息（server/main.py）
  '找不到這首歌': 'Song not found',
  '不支援的檔案格式：': 'Unsupported file type: ',
  '歌名不能空白': 'Title can\'t be blank',
  '只有 instrumental 或 vocals': 'Only instrumental or vocals',
  '還沒有這個音軌': 'This track is not ready yet',
  '這首歌沒有 MV': 'This song has no MV',
  '找不到 MV 檔案': 'MV file not found',
  '沒有封面': 'No cover',
  '還沒有音高資料': 'No pitch data yet',
  '譜的資料不對：': 'The chart data is not valid: ',
  '字的時間不對：': 'The word timing is not valid: ',
  '沒有這種格式：': 'Unknown format: ',
  '虛擬環境裡沒有 yt-dlp，請執行 setup.bat（會用 pip 安裝 yt-dlp）': 'yt-dlp is not installed. Please run setup.bat (it installs yt-dlp with pip)',

  // 裁切（server/main.py、trim.py）
  '已儲存': 'Saved',
  '沒有時間軸歌詞，沒辦法判斷': 'No timed lyrics, so this cannot be checked',
  '沒有找到劇情': 'No story parts found',
  '開始的時間超過歌曲長度了': 'The start time is past the end of the song',
  '裁切後至少要留 {n} 秒': 'At least {n} s must remain after trimming',

  // 修譜、調字（server/chart_store.py、word_store.py）
  '音符太多了（最多 {n} 個）': 'Too many notes (max {n})',
  '有音符的時間不對': 'A note has an invalid time',
  '有音符超過歌曲長度': 'A note goes past the end of the song',
  '有音符的音高不對': 'A note has an invalid pitch',
  '調過的字太多了（最多 {n} 個）': 'Too many adjusted words (max {n})',
  '有字的時間不對': 'A word has an invalid time',
  '有字超過歌曲長度': 'A word goes past the end of the song',

  // 封面（server/cover_tools.py）
  '看不懂這個圖片檔，請換一張（jpg、png、webp 都可以）': 'Cannot read this image. Please try another one (jpg, png or webp)',
  '圖片太大了（最大 {n}MB）': 'The image is too large (max {n} MB)',

  // 加歌時的處理（server/audio_tools.py、pitch_analyzer.py、crepe_runner.py、youtube_import.py）
  '音訊轉換失敗：': 'Audio conversion failed: ',
  '音高辨識失敗：': 'Pitch detection failed: ',
  '找不到 torchcrepe 套件（CREPE 的模型檔在裡面），請執行 setup.bat': 'The torchcrepe package (it holds the CREPE model) is missing. Please run setup.bat',
  '請貼上影片網址（https:// 開頭）': 'Please paste a video link (starting with https://)',
  '讀不到影片資訊：': 'Cannot read the video info: ',
  'YouTube 下載失敗：': 'YouTube download failed: ',
  'YouTube 下載完了，但找不到 original.mp4': 'The YouTube download finished, but original.mp4 is missing',
};
