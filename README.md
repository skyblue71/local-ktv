# 本機KTV

在自己電腦上唱歌、評分的卡拉 OK 程式。歌自己加，AI 在你的電腦上把歌處理好，全部資料都留在你的電腦裡。

**這個專案不附任何歌曲、影片或歌詞。**

## 可以做什麼

- **自己加歌**：電腦裡的音樂檔（mp3、m4a、flac、wav、mp4…），或貼 YouTube 網址
- **AI 去人聲**：自動分出「伴奏」和「原唱人聲」，原唱可以當導唱隨時開關
- **即時評分**：音準、節奏、穩定、表現力、完成度，加上技巧加分
- **逐字字幕**：唱到哪裡變色到哪裡；日文有假名和羅馬拼音，中文有注音或拼音
- **自動找歌詞**：從 LRCLIB 找有時間的歌詞，程式會把它對到歌手真的唱的地方
- **MV 背景**：有影片的歌，唱歌時背景播 MV
- **自己修**：評分條、每個字的時間都可以用滑鼠拖
- **耳返、迴音、錄音**

## 需要什麼

- Windows 10 / 11
- [Python 3.12](https://www.python.org)
- 建議有 NVIDIA 顯示卡：加歌時 AI 會快很多。沒有也能用，但加一首歌會慢很多
- 建議裝 [Node.js 22 以上](https://nodejs.org)：從 YouTube 加歌能拿到比較好的畫質，沒有也能用
- 大約 8 GB 的硬碟空間和穩定的網路（安裝時要下載約 5.3 GB）

唱歌的時候不需要顯示卡，評分是瀏覽器在做的。

## 怎麼開始

1. 下載這個專案，放在一個資料夾裡。
2. 雙擊 `start.bat`。第一次會自動執行 `setup.bat` 安裝環境：
   - 建立虛擬環境 `.venv`（不會動到系統的 Python）
   - 用 pip 安裝需要的套件
   - 下載 AI 模型各一次，並比對檔案指紋
3. 裝好後瀏覽器會打開 http://127.0.0.1:8000 。唱歌時不要關掉 `start.bat` 的黑色視窗。
4. 按「加入歌曲」，選一首歌，等它處理完，再按「開始唱歌」。

建議戴耳機唱，不然喇叭的伴奏會被麥克風收進去，評分會不準。

> 從 YouTube 加歌：請只用在你有權利下載的影片。

## 程式裡的 AI

加歌的時候各跑一次，結果存在那首歌的資料夾裡：

| 做什麼 | 用什麼 | 怎麼下載 | 來源 |
|---|---|---|---|
| 分人聲和伴奏 | Mel-Band RoFormer（Kimberley Jensen 的人聲模型） | 安裝時從 Hugging Face 下載模型檔 | 模型：https://huggingface.co/KimberleyJSN/melbandroformer<br>程式：https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model （原本來自 https://github.com/lucidrains/BS-RoFormer ） |
| 聽音高、寫評分條 | CREPE（torchcrepe 附的模型） | 用 pip 安裝 torchcrepe，模型檔包在套件裡 | https://github.com/maxrmorrison/torchcrepe |
| 聽每個字在第幾秒 | Meta MMS 強制對齊模型（torchaudio 的 MMS_FA） | 安裝時從 Meta 的官方網址下載模型檔 | https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt |
| 分人聲的另一個選擇（比較輕） | Demucs `htdemucs` | 預設不下載；改用它時才從 Hugging Face 下載 | https://huggingface.co/adefossez/HTDemucs |

其他：從 YouTube 加歌用 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，歌詞來自 [LRCLIB](https://lrclib.net)。

這些模型和工具各有自己的授權，使用前請看它們各自的官方頁面。其中 Meta MMS 模型是 CC-BY-NC 4.0，**不能用在商業用途**，所以這個程式也只適合非商業使用。

有幾個檔案是照別人公開的程式寫的，原作者的授權聲明放在 [第三方授權.md](第三方授權.md)。

模型檔下載後會比對大小和 SHA256（寫在 `server\config.py`）；PyTorch 格式的模型一律用「只讀數字」的安全模式載入。

## AI 的限制

- 聽字的 AI 是用「講話」練出來的。拉長的音、哼唱、「Wow」這類語助詞它常常聽不出來，那幾句的字幕時間會不準。
- 評分條不認字：一個字可能唱好幾個音，兩個字也可能在同一個音上。
- 所以 AI 做錯的地方，可以到歌曲頁的「修譜」自己拖評分條和字；「編輯歌詞」可以選「自動」或「照歌詞檔」。

## 程式會不會連網

- 伺服器只開在 `127.0.0.1`，別人連不到。
- 只有兩個功能會連網，而且都是你按了才會：搜尋歌詞（把歌名和歌手送到 lrclib.net）、從 YouTube 加歌。
- AI 模型只在安裝時下載一次，之後只讀電腦裡的檔案。
- 你的歌、聲音、錄音、分數都存在你的電腦，不會傳出去；程式沒有任何回報功能。
- 想自己檢查：雙擊 `檢查連網.bat`，它會擋住對外網路把整個流程跑一遍，看到兩個【通過】就是正常。

## 資料放在哪裡

每首歌一個資料夾，在 `data\songs\`：原始檔、伴奏、人聲、評分條、字幕、分數、封面，還有你自己修過的譜和調過的字。`data\` 不在這個專案裡，要自己備份。

## 程式結構

每個檔案只做一件事，註解都是中文。

```
start.bat / setup.bat     啟動、安裝
requirements.txt          套件清單（版本固定）
server/                   後端（Python，FastAPI）
  main.py                 網址 → 要做什麼
  song_processor.py       加一首歌的完整流程
  separator.py            分人聲（melband_separator.py / demucs_separator.py）
  pitch_analyzer.py       聽音高、寫評分條（crepe_*.py）
  syllable_model.py       聽字（MMS）
  word_timeline.py        每個字從幾秒唱到幾秒（字幕、評分條都照它）
  lyrics_builder.py       歌詞 → 字幕
  song_alignment.py       影片跟歌詞版本不一樣時，整段搬到歌手唱的地方
  word_store.py / chart_store.py   你調過的字、你修過的譜
web/                      前端（純 JavaScript，沒有框架）
  js/pages/               每一頁的畫面
  js/game/                評分、字幕、評分條、唱歌畫面
  js/audio/               播放、麥克風、即時音高偵測、錄音
tools/                    安裝、檢查、重新整理舊歌用的小程式
```

## 常見問題

| 問題 | 怎麼辦 |
|---|---|
| 明明準時開口，一直被判「慢」 | 設定 →「延遲補償」往右調 |
| 男生唱女生的歌，分數很低 | 設定 → 打開「高低八度都算對」 |
| 字幕整首早或晚 | 「編輯歌詞」→ 歌詞時間選「照歌詞檔」，再用「整首移動」調 |
| 某幾句的字幕跑太快或太慢 | 「修譜」→ 拖下面那一排字 |
| 沒在唱的地方有評分條 | 設定 →「清掉小聲雜音」調小一點；或到「修譜」刪掉 |
| 假名、注音標錯 | 「編輯歌詞」→ 在字後面加 `{正確讀音}`，例如 `私{わたし}` |
| 找不到歌詞 | 「編輯歌詞」換原文歌名再搜尋，或自己貼歌詞後用「點按同步」 |
| 從 YouTube 加歌失敗 | YouTube 常改版，更新 yt-dlp：`.venv\Scripts\python -m pip install -U yt-dlp yt-dlp-ejs` |
| Windows 擋住某個檔案 | 「智慧型應用程式控制」有時會擋沒有簽章的檔案。這個程式已經避開會被擋的套件；請不要為了它關掉 Windows 的保護 |
