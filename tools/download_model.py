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


def download_melband():
    """去人聲模型 Mel-Band RoFormer：從作者本人的 Hugging Face 下載單一檔案（先存成 .part，下載完才改名）"""
    import requests
    from server.config import MELBAND_MODEL_DIR, MELBAND_MODEL_NAME, MELBAND_MODEL_URL

    path = os.path.join(MELBAND_MODEL_DIR, MELBAND_MODEL_NAME)
    if os.path.exists(path):
        print("去人聲模型已經在電腦裡了，檢查中…")
    else:
        print("下載去人聲模型（約 913MB）：" + MELBAND_MODEL_URL)
        os.makedirs(MELBAND_MODEL_DIR, exist_ok=True)
        temp = path + ".part"
        with requests.get(MELBAND_MODEL_URL, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(temp, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        os.replace(temp, path)

    if not melband_is_genuine(path):
        print("警告：去人聲模型的大小、SHA256 或內容跟官方不一樣，請不要使用！刪掉後再執行一次 setup.bat")
        print("檔案位置：" + path)
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
    """認音節模型 MMS：直接從 Meta 官方網址下載單一檔案（先存成 .part，下載完才改名）"""
    import requests
    from server.config import MMS_MODEL_DIR, MMS_MODEL_NAME, MMS_MODEL_URL

    path = os.path.join(MMS_MODEL_DIR, MMS_MODEL_NAME)
    if os.path.exists(path):
        print("認音節模型已經在電腦裡了，檢查中…")
    else:
        print("下載認音節模型（約 1.26GB）：" + MMS_MODEL_URL)
        os.makedirs(MMS_MODEL_DIR, exist_ok=True)
        temp = path + ".part"
        with requests.get(MMS_MODEL_URL, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(temp, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        os.replace(temp, path)

    if not mms_is_genuine(path):
        print("警告：認音節模型的大小或指紋跟官方不一樣，請不要使用！刪掉後再執行一次 setup.bat")
        print("檔案位置：" + path)
        sys.exit(1)
    print("認音節模型檢查完成：大小、指紋、SHA256 都跟官方一樣。")


main()
