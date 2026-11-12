# Local KTV

[中文](README.md)

A karaoke app that runs on your own PC and scores your singing. You add the songs, the AI processes them on your machine, and all the data stays on your computer.

**This project does not include any songs, videos or lyrics.**

## Features

- **Add your own songs**: music files on your PC (mp3, m4a, flac, wav, mp4…) or a YouTube link
- **AI vocal separation**: splits each song into a backing track and the original vocals. The original vocals can be turned on as a guide at any time
- **Live scoring**: pitch, rhythm, stability, expression and completion, plus bonus points for techniques. Rap and spoken parts get bars too
- **Word-by-word lyrics**: words light up as they are sung. Japanese shows kana and romaji, Chinese shows Zhuyin or Pinyin
- **Automatic lyrics**: finds timed lyrics on LRCLIB and lines them up with where the singer actually sings
- **MV background**: songs with video play the MV behind the lyrics
- **Edit it yourself**: drag the pitch bars and the timing of each word with the mouse, with step-by-step undo and redo
- **Monitor, reverb, recording**: listen again after singing, or download the recording as MP3
- **Chinese and English interface**: switch in Settings
- **Updates itself**: when a newer version is out, it asks before it starts. Your songs and scores are not touched

## Requirements

- Windows 10 / 11
- [Python](https://www.python.org) 3.12 or newer: tested with 3.12. If your PC already has a newer version, setup tries it first and shows a warning
- An NVIDIA graphics card is recommended: the AI is much faster when adding songs. It works without one, but adding a song is much slower
- [Node.js 22 or newer](https://nodejs.org) is recommended: better video quality from YouTube. It works without it
- About 8 GB of disk space and a stable connection (setup downloads about 5.3 GB)

Singing does not need a graphics card. Scoring runs in the browser.

## Getting started

1. Download this project into a folder.
2. Double-click `start.bat`. The first run installs everything: it creates a virtual environment `.venv`, installs the packages with pip, and downloads each AI model once.
3. When it is ready, your browser opens http://127.0.0.1:8000 . Keep the black `start.bat` window open while you sing.
4. Click "Add song", pick a song, wait for it to finish processing, then click "Start singing".

Headphones are recommended. Otherwise the microphone picks up the backing track from the speakers and scoring is less accurate.

> Adding songs from YouTube: only use it for videos you have the right to download.

## AI models used

Each one runs once when a song is added. The results are saved in that song's folder.

| What it does | What is used | How it is downloaded | Source |
|---|---|---|---|
| Separates vocals and backing track | Mel-Band RoFormer (vocal model by Kimberley Jensen) | Model file downloaded from Hugging Face during setup | Model: https://huggingface.co/KimberleyJSN/melbandroformer<br>Code: https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model (originally from https://github.com/lucidrains/BS-RoFormer ) |
| Detects pitch and writes the pitch bars | CREPE (the model shipped with torchcrepe) | Installed with pip as torchcrepe. The model file is inside the package | https://github.com/maxrmorrison/torchcrepe |
| Finds when each word is sung | Meta MMS forced alignment model (MMS_FA in torchaudio) | Model file downloaded from Meta's official URL during setup | https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt |
| Another option for vocal separation (lighter) | Demucs `htdemucs` | Not downloaded by default. Downloaded from Hugging Face only if you switch to it | https://huggingface.co/adefossez/HTDemucs |

Also: [yt-dlp](https://github.com/yt-dlp/yt-dlp) for adding songs from YouTube, and lyrics from [LRCLIB](https://lrclib.net).

These models and tools each have their own license. The Meta MMS model is CC-BY-NC 4.0 and **cannot be used commercially**, so this app is for non-commercial use only.

## Privacy

- The server only listens on `127.0.0.1`. Other people cannot connect to it.
- Only three things go online: searching for lyrics, adding a song from YouTube, and checking GitHub for a newer version at startup.
- To stay offline at startup, set `CHECK_UPDATE` to `no` in `start.bat`.
- Your songs, recordings and scores are stored only in the `data\` folder on your PC. Nothing is sent anywhere.

## License

The code of this project is under the MIT License. See [LICENSE](LICENSE).

A few files are based on other people's public code. The original license notices are in [第三方授權.md](第三方授權.md).
