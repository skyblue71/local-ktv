# 本機KTV

[English](README.en.md)

在自己電腦上唱歌、評分的 KTV 程式。歌自己加，AI 在你的電腦上把歌處理好，全部資料都留在你的電腦裡。

**這個專案不附任何歌曲、影片或歌詞。**

## 功能

- **自己加歌**：電腦裡的音樂檔（mp3、m4a、flac、wav、mp4…），或貼 YouTube 網址
- **AI 去人聲**：自動分出「伴奏」和「原唱人聲」，原唱可以當導唱隨時開關
- **即時評分**：音準、節奏、穩定、表現力、完成度，加上技巧加分；rap、唸白的地方也有評分條
- **逐字字幕**：唱到哪裡變色到哪裡；日文有假名和羅馬拼音，中文有注音或拼音
- **自動找歌詞**：從 LRCLIB 找有時間的歌詞，程式會把它對到歌手真的唱的地方
- **MV 背景**：有影片的歌，唱歌時背景播 MV
- **自己修**：評分條、每個字的時間都可以用滑鼠拖
- **耳返、迴音、錄音**：唱完可以重聽，也可以下載成 MP3
- **中文、英文介面**：在設定裡切換
- **自動更新**：有新版時，啟動會先問你要不要更新，歌和分數不會動

## 需要什麼

- Windows 10 / 11
- [Python](https://www.python.org) 3.12 以上：測過的是 3.12。電腦裡已經有更新的版本會先用它試，安裝時會提醒版本不一樣
- 建議有 NVIDIA 顯示卡：加歌時 AI 會快很多。沒有也能用，但加一首歌會慢很多
- 建議裝 [Node.js 22 以上](https://nodejs.org)：從 YouTube 加歌能拿到比較好的畫質，沒有也能用
- 大約 8 GB 的硬碟空間和穩定的網路（安裝時要下載約 5.3 GB）

唱歌的時候不需要顯示卡，評分是瀏覽器在做的。

## 怎麼開始

1. 下載這個專案，放在一個資料夾裡。
2. 雙擊 `start.bat`。第一次會自動安裝：建立虛擬環境 `.venv`、用 pip 裝套件、下載 AI 模型各一次。
3. 裝好後瀏覽器會打開 http://127.0.0.1:8000 。唱歌時不要關掉 `start.bat` 的黑色視窗。
4. 按「加入歌曲」，選一首歌，等它處理完，再按「開始唱歌」。

建議戴耳機唱，不然喇叭的伴奏會被麥克風收進去，評分會不準。

> 從 YouTube 加歌：請只用在你有權利下載的影片。

## 用到的 AI

加歌的時候各跑一次，結果存在那首歌的資料夾裡。

| 做什麼 | 用什麼 | 怎麼下載 | 來源 |
|---|---|---|---|
| 分人聲和伴奏 | Mel-Band RoFormer（Kimberley Jensen 的人聲模型） | 安裝時從 Hugging Face 下載模型檔 | 模型：https://huggingface.co/KimberleyJSN/melbandroformer<br>程式：https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model （原本來自 https://github.com/lucidrains/BS-RoFormer ） |
| 聽音高、寫評分條 | CREPE（torchcrepe 附的模型） | 用 pip 安裝 torchcrepe，模型檔包在套件裡 | https://github.com/maxrmorrison/torchcrepe |
| 聽每個字在第幾秒 | Meta MMS 強制對齊模型（torchaudio 的 MMS_FA） | 安裝時從 Meta 的官方網址下載模型檔 | https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt |
| 分人聲的另一個選擇（比較輕） | Demucs `htdemucs` | 預設不下載；改用它時才從 Hugging Face 下載 | https://huggingface.co/adefossez/HTDemucs |

其他：從 YouTube 加歌用 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，歌詞來自 [LRCLIB](https://lrclib.net)。

這些模型和工具各有自己的授權。其中 Meta MMS 模型是 CC-BY-NC 4.0，**不能用在商業用途**，所以這個程式也只適合非商業使用。

## 隱私

- 伺服器只開在 `127.0.0.1`，別人連不到。
- 會連網的只有三件事：搜尋歌詞、從 YouTube 加歌、啟動時看 GitHub 有沒有新版。
- 不想在啟動時連網：把 `start.bat` 裡的 `CHECK_UPDATE` 改成 `no`。
- 你的歌、錄音、分數都只存在你電腦的 `data\` 資料夾，不會傳出去。

## 授權

這個專案自己的程式碼是 MIT 授權，見 [LICENSE](LICENSE)。

有幾個檔案是照別人公開的程式寫的，原作者的授權聲明放在 [第三方授權.md](第三方授權.md)。
