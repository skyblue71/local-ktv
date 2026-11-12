"""
安裝時用：把 AI 模型下載一次到這台電腦。
  1. 去人聲模型（看 server\\config.py 的 SEPARATOR，只下載要用的那一個）：
     - Mel-Band RoFormer（預設，約 913MB）：https://huggingface.co/KimberleyJSN/melbandroformer （模型作者本人帳號）
       下載後比對大小、SHA256（Hugging Face 網頁公布的），再檢查檔案裡只有權重、沒有藏程式。
     - HTDemucs（另一個選擇，約 80MB）：https://huggingface.co/adefossez/HTDemucs （demucs 原作者本人帳號）
       下載後比對 SHA256，確定跟官方公布的一樣。
  2. 認音節模型 MMS（約 1.26GB）：https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt
     （Meta 官方伺服器，torchaudio 內建的 MMS_FA 用的就是這個檔案）
     下載後比對大小、伺服器公布的指紋（ETag）和 SHA256（網址、指紋寫在 server\\config.py）。

擋不擋只看「檔案是不是官方的」（大小、指紋）：下載到 .part，檢查通過才改名放進去，不對就刪掉（download_file）。
  網站的安全憑證驗不過（例如過期）：顯示警告、照樣下載，擋不擋一樣看檔案的指紋。
下載不了（連不上、下載到一半斷掉、檔案不對）：用中英文說明原因，不顯示一大串錯誤。
  - 去人聲模型：一定要有，停下來，請晚一點再執行 setup.bat。
  - 認音節模型：沒有也能用（字幕每個字的時間用猜的），所以安裝照樣完成；再執行一次 setup.bat 會補下載。

平常卡拉OK是「不連網」的（server\\config.py 的 ALLOW_MODEL_DOWNLOAD = False），
所以換新電腦第一次安裝時，要靠這個程式先把模型下載好。
電腦裡已經有了，就不會再下載。

執行方式：setup.bat 會自動執行，不用自己跑。
"""
import hashlib
import os
import pickletools
import sys
import zipfile

# 讓這個程式找得到 server 資料夾（讀 config.py 的 MMS 網址、指紋）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ID = "adefossez/HTDemucs"
CONFIG_FILE = "htdemucs.yaml"
WEIGHTS_FILE = "955717e8.safetensors"
# Hugging Face 官方網頁標示的 SHA256
WEIGHTS_SHA256 = "d9fa14133cfcc034a6758923bb3a8ca9f8dfd0b582134643bbf83f72c17576dd"


def find_in_cache(filename):
    """模型檔已經在電腦裡的話回傳路徑，沒有就回傳 None"""
    from huggingface_hub import try_to_load_from_cache
    path = try_to_load_from_cache(REPO_ID, filename)
    if isinstance(path, str) and os.path.exists(path):
        return path
    return None


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main():
    # 只有這個安裝程式允許連網（一定要在載入 huggingface_hub 之前設定）
    os.environ["HF_HUB_OFFLINE"] = "0"
    # 下載時 Hugging Face 會印一大段英文警告：「Windows 不支援捷徑（symlink），存檔會多佔一點空間」
    # 我們只存一個版本的模型，沒差，所以把它關掉（只有下載時才會出現，所以只寫在這裡）
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

    from server.config import SEPARATOR
    if SEPARATOR == "demucs":
        download_demucs()
    else:
        download_melband()
    download_mms()


def download_demucs():
    if find_in_cache(CONFIG_FILE) and find_in_cache(WEIGHTS_FILE):
        print("去人聲模型已經在電腦裡了，不用下載。")
    else:
        print("下載去人聲模型（約 80MB）：https://huggingface.co/" + REPO_ID)
        from demucs.pretrained import get_model
        get_model("hf://htdemucs")   # 只從 Hugging Face 下載

    weights = find_in_cache(WEIGHTS_FILE)
    if weights is None:
        print("模型下載失敗，請確認網路後再執行一次 setup.bat")
        sys.exit(1)

    if sha256_of(weights) != WEIGHTS_SHA256:
        print("警告：模型檔的 SHA256 跟官方不一樣，請不要使用，並重新下載！")
        print("檔案位置：" + weights)
        sys.exit(1)
    print("模型檢查完成：SHA256 跟官方一樣。")


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


def fetch(url, temp, check_certificate):
    """把 url 的內容存到 temp。check_certificate=False：不檢查網站的安全憑證"""
    import requests

    with requests.get(url, stream=True, timeout=60, verify=check_certificate) as response:
        response.raise_for_status()
        with open(temp, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)


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


def download_melband():
    """去人聲模型 Mel-Band RoFormer：從作者本人的 Hugging Face 下載單一檔案。下載不了就停下來（沒有它不能去人聲）"""
    from server.config import MELBAND_MODEL_DIR, MELBAND_MODEL_NAME, MELBAND_MODEL_URL

    path = os.path.join(MELBAND_MODEL_DIR, MELBAND_MODEL_NAME)
    if os.path.exists(path):
        print("去人聲模型已經在電腦裡了，檢查中…")
        if not melband_is_genuine(path):
            print("警告：去人聲模型的大小、SHA256 或內容跟官方不一樣，請不要使用！刪掉後再執行一次 setup.bat")
            print("檔案位置：" + path)
            sys.exit(1)
    else:
        print("下載去人聲模型（約 913MB）：" + MELBAND_MODEL_URL)
        if not download_file(MELBAND_MODEL_URL, path, melband_is_genuine):
            say("The vocal separation model is required. Run setup.bat again later.",
                "去人聲模型一定要有。請晚一點再執行一次 setup.bat")
            sys.exit(1)
    print("去人聲模型檢查完成：大小、SHA256 都跟官方一樣，裡面只有權重。")


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


def download_mms():
    """
    認音節模型 MMS：直接從 Meta 官方網址下載單一檔案。
    下載不了：安裝照樣繼續。沒有這個模型程式也能用（server\\syllable_model.py 的 is_available），
    只是字幕每個字的時間用猜的；之後再執行一次 setup.bat 會補下載
    """
    from server.config import MMS_MODEL_DIR, MMS_MODEL_NAME, MMS_MODEL_URL

    path = os.path.join(MMS_MODEL_DIR, MMS_MODEL_NAME)
    if os.path.exists(path):
        print("認音節模型已經在電腦裡了，檢查中…")
        if not mms_is_genuine(path):
            print("警告：認音節模型的大小或指紋跟官方不一樣，請不要使用！刪掉後再執行一次 setup.bat")
            print("檔案位置：" + path)
            sys.exit(1)
    else:
        print("下載認音節模型（約 1.26GB）：" + MMS_MODEL_URL)
        if not download_file(MMS_MODEL_URL, path, mms_is_genuine):
            say("Setup continues without the syllable model. You can still sing and get scored; "
                "only the word-by-word lyric fill is estimated and less exact.",
                "安裝會繼續，先不裝認音節模型。一樣可以唱歌、評分，只是字幕每個字填色的時間用猜的，比較不準。")
            say("To get it later: run setup.bat again. Songs you already added need \"Reprocess\" to use it.",
                "之後要補：再執行一次 setup.bat。已經加過的歌要按「重新處理」才會用到。")
            return
    print("認音節模型檢查完成：大小、指紋、SHA256 都跟官方一樣。")


if __name__ == "__main__":
    main()
