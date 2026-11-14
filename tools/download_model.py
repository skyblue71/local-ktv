"""
下載 AI 模型到這台電腦（每個模型放在 models\\ 裡它自己的資料夾，server\\config.py 的 download_path）。
  1. 去人聲模型 Mel-Band RoFormer（約 913MB）：https://huggingface.co/KimberleyJSN/melbandroformer （模型作者本人帳號）
     下載後比對大小、SHA256（Hugging Face 網頁公布的），再檢查檔案裡只有權重、沒有藏程式。
  2. 認音節模型 MMS（約 1.26GB）：https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt
     （Meta 官方伺服器，torchaudio 內建的 MMS_FA 用的就是這個檔案）
     下載後比對大小、伺服器公布的指紋（ETag）和 SHA256（網址、指紋寫在 server\\config.py）。

擋不擋只看「檔案是不是官方的」（大小、指紋）：下載到 .part，檢查通過才改名放進去，不對就刪掉（download_file）。
  網站的安全憑證驗不過（例如過期）：顯示警告、照樣下載，擋不擋一樣看檔案的指紋。
下載不了（連不上、下載到一半斷掉、檔案不對）：用中英文說明原因，不顯示一大串錯誤。
  - 去人聲模型：一定要有，停下來，請晚一點再試。
  - 認音節模型：沒有也能用（字幕每個字的時間用猜的），所以照樣繼續；之後按 update.bat 會再問要不要下載。

卡拉OK本身不連網（只讀電腦裡的模型檔），所以模型都要靠這個程式先下載好。
電腦裡已經有了（包括舊版放在使用者資料夾 .cache 的），就不會再下載。檔案大小不對（沒下載完）的當成沒有，重新下載。

執行方式（都是自動執行的，不用自己跑）：
  python tools\\download_model.py         setup.bat 用：模型都準備好（沒有的下載，已經有的檢查是不是官方的）
  python tools\\download_model.py --ask   update.bat 用（tools\\update.py）：只看檔案在不在、大小對不對（不連網、不算指紋，很快）。
                                         少了哪一個（例如被刪掉）：列出來、說沒有它會怎樣、從哪裡下載，
                                         問要不要下載，按 Y 才下載少的那幾個；都在就什麼都不印
"""
import hashlib
import os
import pickletools
import sys
import zipfile

# 讓這個程式找得到 server 資料夾（讀 config.py 的網址、指紋）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from update import ask_yes_no   # noqa: E402（同一個 tools 資料夾的檔案）


def model_list():
    """
    程式用的模型，每個一筆：
      name：檔名（config.py）、size：大小、url：下載網址、is_genuine：檢查是不是官方檔案的函式、
      required：一定要有嗎（沒有就不能用這個程式）、title：叫什麼、without：沒有的話會怎樣（英文、中文）
    """
    from server import config
    return [
        {
            "name": config.MELBAND_MODEL_NAME,
            "size": config.MELBAND_MODEL_SIZE,
            "url": config.MELBAND_MODEL_URL,
            "is_genuine": melband_is_genuine,
            "required": True,
            "title": ("Vocal separation model (about 913MB)", "去人聲模型（約 913MB）"),
            "without": ("without it, you cannot add new songs.", "沒有的話，不能加新歌。"),
        },
        {
            "name": config.MMS_MODEL_NAME,
            "size": config.MMS_MODEL_SIZE,
            "url": config.MMS_MODEL_URL,
            "is_genuine": mms_is_genuine,
            "required": False,
            "title": ("Syllable model (about 1.26GB)", "認音節模型（約 1.26GB）"),
            "without": ("without it, the word-by-word lyric fill of new songs is guessed and less exact.",
                        "沒有的話，新歌的字幕每個字什麼時候變色是用猜的，比較不準。"),
        },
    ]


def is_present(model):
    """這個模型在不在電腦裡（檔案在、大小跟官方一樣）"""
    from server.config import model_path
    path = model_path(model["name"])
    return os.path.isfile(path) and os.path.getsize(path) == model["size"]


def main():
    if "--ask" in sys.argv:
        ask_and_download()
        return
    for model in model_list():
        prepare(model, "setup.bat")


def prepare(model, again):
    """
    setup.bat 用：電腦裡有就檢查是不是官方的（不是就停下來），沒有就下載。
    again：下載不了的時候，叫人再按哪一個（setup.bat 或 update.bat）
    """
    from server.config import model_path
    title_english, title_chinese = model["title"]
    if is_present(model):
        path = model_path(model["name"])
        say(title_english + ": already on this computer, checking...", title_chinese + "：已經在電腦裡了，檢查中…")
        if not model["is_genuine"](path):
            say("Warning: this file does not match the official one. Do not use it! Delete it, then run setup.bat again.",
                "警告：這個檔案跟官方的不一樣，請不要使用！刪掉後再執行一次 setup.bat")
            print("檔案位置：" + path)
            sys.exit(1)
        say(title_english + ": checked, same as the official file.", title_chinese + "：檢查完成，跟官方的一樣。")
        return
    download(model, again)


def download(model, again):
    """下載一個模型。一定要有的下載不了就停下來；不一定要有的就說明、照樣繼續"""
    from server.config import download_path
    title_english, title_chinese = model["title"]
    say("Downloading " + title_english + ": " + model["url"], "下載" + title_chinese + "：" + model["url"])
    if download_file(model["url"], download_path(model["name"]), model["is_genuine"]):
        say(title_english + ": downloaded and checked, same as the official file.",
            title_chinese + "：下載完成，檢查過跟官方的一樣。")
        return
    without_english, without_chinese = model["without"]
    if model["required"]:
        say("This model is required. Run " + again + " again later.",
            "這個模型一定要有。請晚一點再執行一次 " + again)
        sys.exit(1)
    say("Continuing without it. You can still sing and get scored; " + without_english,
        "先不裝，照樣繼續。一樣可以唱歌、評分，只是" + without_chinese)
    say("To get it later: run update.bat. Songs you already added need \"Reprocess\" to use it.",
        "之後要補：按 update.bat。已經加過的歌要按「重新處理」才會用到。")


def ask_and_download():
    """update.bat 用：少了哪些模型就列出來，問要不要下載。都在的話什麼都不印"""
    missing = []
    for model in model_list():
        if not is_present(model):
            missing.append(model)
    if len(missing) == 0:
        return
    print()
    say("Some AI models are not on this computer (maybe they were deleted):",
        "電腦裡少了 AI 模型（可能被刪掉了）：")
    for model in missing:
        print("  - " + model["title"][0] + ": " + model["without"][0])
        print("    " + model["title"][1] + "：" + model["without"][1])
        print("    " + model["url"])
    say("Songs you already added still work. Files come only from the official addresses above.",
        "已經加好的歌照樣能唱。只從上面的官方網址下載。")
    if not ask_yes_no("Download now?", "現在下載嗎？"):
        say("Not downloaded. You will be asked again the next time you run update.bat.",
            "先不下載。下次按 update.bat 會再問。")
        print()
        return
    for model in missing:
        download(model, "update.bat")
    print()


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# PyTorch 模型檔裡的 pickle 會叫用的程式，純權重檔只需要這三個（Hugging Face 的掃描結果也是這三個）
ALLOWED_PICKLE_CALLS = [
    ("collections", "OrderedDict"),
    ("torch", "FloatStorage"),
    ("torch._utils", "_rebuild_tensor_v2"),
]


def pickle_calls(path):
    """不執行模型檔，只「讀」它：列出裡面的 pickle 會叫用哪些程式（木馬會藏在這裡）"""
    found = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(".pkl"):
                continue
            strings = []   # 最近讀到的文字（STACK_GLOBAL 用最後兩個當「模組、名字」）
            memo = {}
            for op, arg, _ in pickletools.genops(archive.read(name)):
                if op.name in ("SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "BINUNICODE8",
                               "SHORT_BINSTRING", "BINSTRING", "STRING"):
                    strings.append(arg)
                elif op.name in ("BINPUT", "LONG_BINPUT", "PUT") and strings:
                    memo[arg] = strings[-1]
                elif op.name == "MEMOIZE" and strings:
                    memo[len(memo)] = strings[-1]
                elif op.name in ("BINGET", "LONG_BINGET", "GET") and arg in memo:
                    strings.append(memo[arg])
                elif op.name == "GLOBAL":
                    module, func = arg.split(" ", 1)
                    found.append((module, func))
                elif op.name == "STACK_GLOBAL":
                    found.append((strings[-2], strings[-1]))
    return found


def melband_is_genuine(path):
    """Mel-Band RoFormer 模型檔：大小、SHA256 跟 Hugging Face 公布的一樣，而且裡面只有權重"""
    from server.config import MELBAND_MODEL_SHA256, MELBAND_MODEL_SIZE
    if os.path.getsize(path) != MELBAND_MODEL_SIZE:
        return False
    if sha256_of(path) != MELBAND_MODEL_SHA256:
        return False
    for call in pickle_calls(path):
        if call not in ALLOWED_PICKLE_CALLS:
            print("模型檔裡有不該有的程式：" + call[0] + "." + call[1])
            return False
    return True


def s3_etag_of(path, part_size=8 * 1024 * 1024):
    """Amazon S3 分段上傳的指紋：每 8 MiB 一段算 md5，再把這些 md5 合起來算一次 md5，加上「-段數」"""
    digests = []
    with open(path, "rb") as f:
        while True:
            block = f.read(part_size)
            if not block:
                break
            digests.append(hashlib.md5(block).digest())
    return hashlib.md5(b"".join(digests)).hexdigest() + "-" + str(len(digests))


def mms_is_genuine(path):
    """MMS 模型檔：大小、指紋（ETag）、SHA256 都跟 config.py 記的一樣才算"""
    from server.config import MMS_MODEL_ETAG, MMS_MODEL_SHA256, MMS_MODEL_SIZE
    if os.path.getsize(path) != MMS_MODEL_SIZE:
        return False
    if s3_etag_of(path) != MMS_MODEL_ETAG:
        return False
    return sha256_of(path) == MMS_MODEL_SHA256


def say(english, chinese):
    """印一句話：英文一行、中文一行"""
    print(english)
    print(chinese)


def short_reason(error):
    """把很長的連線錯誤縮成一小段原因，例如 certificate has expired"""
    text = str(error)
    mark = "certificate verify failed: "
    if mark in text:
        text = text.split(mark, 1)[1].split(" (_ssl", 1)[0]
    return text[:200]


MB = 1024 * 1024


def show_progress(done, total, shown):
    """
    在同一行顯示下載進度（[#####-----]  45%  410 / 913 MB），百分比變了才重畫。回傳這次顯示的百分比
    網站沒說檔案多大（total 是 0）：只顯示下載了幾 MB
    """
    if total <= 0:
        print("\r  %d MB" % (done // MB), end="", flush=True)
        return shown
    percent = done * 100 // total
    if percent != shown:
        filled = percent // 5
        bar = "#" * filled + "-" * (20 - filled)
        print("\r  [%s] %3d%%  %d / %d MB" % (bar, percent, done // MB, total // MB), end="", flush=True)
    return percent


def fetch(url, temp, check_certificate):
    """把 url 的內容存到 temp，邊下載邊顯示進度。check_certificate=False：不檢查網站的安全憑證"""
    import requests

    with requests.get(url, stream=True, timeout=60, verify=check_certificate) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        shown = -1
        try:
            with open(temp, "wb") as f:
                for chunk in response.iter_content(chunk_size=MB):
                    f.write(chunk)
                    done += len(chunk)
                    shown = show_progress(done, total, shown)
        finally:
            print()   # 進度那一行結束，後面的訊息從新的一行開始


def fetch_without_certificate(url, temp, error):
    """
    網站的安全憑證驗不過（過期、對不上）：顯示警告，不檢查憑證再下載一次。
    憑證只是用來確認「對面是不是真的那個網站」；下載到的檔案之後一定要過 is_genuine（大小、指紋跟官方一樣）
    才會留下來，所以就算對面是假的，假檔案也用不到
    """
    import urllib3

    say("Warning: the site's security certificate could not be verified (" + short_reason(error) + "). "
        "This is usually a problem on the site, for example an expired certificate.",
        "警告：這個網站的安全憑證驗不過（" + short_reason(error) + "）。通常是網站那邊的問題，例如憑證過期。")
    say("Downloading anyway. The file is only kept if its fingerprint matches the official one.",
        "照樣下載。下載到的檔案，指紋跟官方的一樣才會留下來。")
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)   # 上面已經講過了，不用再印一段英文警告
    fetch(url, temp, False)


def download_file(url, path, is_genuine):
    """
    把 url 下載到 path。成功回傳 True。
    先存成 .part，下載完用 is_genuine(.part 的路徑) 檢查是不是官方的檔案，通過才改名成 path。
    回傳 False 的情況（都會刪掉 .part、用中英文說明原因）：
      連不上、下載到一半斷掉；下載到的檔案跟官方的不一樣
    網站的安全憑證驗不過：顯示警告、照樣下載（fetch_without_certificate），擋不擋看 is_genuine
    """
    import requests

    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".part"
    try:
        try:
            fetch(url, temp, True)
        except requests.exceptions.SSLError as error:
            fetch_without_certificate(url, temp, error)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        remove_if_exists(temp)
        say("Download failed: could not reach the site, or it took too long to answer.",
            "下載失敗：連不上這個網站，或等太久沒有回應。")
        say("Check your network, then try again.",
            "請確認網路後再試一次。")
        return False
    except (requests.exceptions.RequestException, OSError) as error:
        # 其他情況（例如網站說沒有這個檔案、硬碟滿了）：把原因印出來
        remove_if_exists(temp)
        say("Download failed: " + short_reason(error),
            "下載失敗：" + short_reason(error))
        say("Check your network (and free disk space), then try again.",
            "請確認網路（和硬碟空間）後再試一次。")
        return False

    print("下載完成，檢查是不是官方的檔案…")
    if not is_genuine(temp):
        remove_if_exists(temp)
        say("The downloaded file does not match the official one (size or fingerprint). It was deleted and is not used.",
            "下載到的檔案跟官方的不一樣（大小或指紋不對），已經刪掉，不會使用。")
        return False
    os.replace(temp, path)
    return True


def remove_if_exists(path):
    if os.path.exists(path):
        os.remove(path)


if __name__ == "__main__":
    main()
