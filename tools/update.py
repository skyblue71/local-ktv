"""
檢查更新：看 GitHub 上有沒有新版，有的話問要不要更新。

兩種用法：
  python tools\\update.py           update.bat 用：每次都下載最新版來比
  python tools\\update.py --start   start.bat 啟動時用：先問一下最新版的編號，跟上次比過的一樣就什麼都不做；
                                   更新完會問要不要開啟（不要 = 結束代碼 NO_START，start.bat 就不啟動）
做法：
  1. （--start）問 GitHub 最新版的編號（很小的一次連線）。連不上、或跟上次比過的一樣：照常啟動
  2. 下載最新版的壓縮檔到暫存資料夾（只有程式，不到幾 MB）
  3. 一個一個檔案比：最新版有、這裡沒有或內容不一樣的，就是要更新的
  4. 都一樣：已經是最新版，記下編號
  5. 有不一樣：列出來，問 Y / N。按 Y 才會動這個資料夾
  6. 更新：被換掉的舊檔案先備份到 data\\update_backup\\時間\\，再放上新的
  7. requirements.txt 有變：用 pip 安裝套件（只裝在這個程式的 .venv 裡；還沒安裝環境就不裝，留給 start.bat）
不會動的：data（歌、分數）、.venv、最新版裡沒有的檔案。
這個資料夾如果是 Git 管理的（有 .git），不更新，請用 Git。
只用 Python 內建的功能，所以還沒安裝環境、只有 update.bat 一個檔案的時候也能跑。
畫面上的訊息每一句都有英文和中文。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

# 程式放在 GitHub 的哪裡、要抓哪一個分支
REPO = "skyblue71/local-ktv"
BRANCH = "main"
REPO_PAGE = "https://github.com/" + REPO
# 問最新版編號的網址（回傳一串 40 個字的編號）
VERSION_URL = "https://api.github.com/repos/" + REPO + "/commits/" + BRANCH
# 連線最多等幾秒：啟動時問編號要快（連不上就照常啟動），下載壓縮檔可以久一點
CHECK_SECONDS = 5
DOWNLOAD_SECONDS = 60
# 下載回來的東西裡一定要有這幾個檔案，才算是這個程式（不然不更新）
MUST_HAVE = ["start.bat", "setup.bat", "requirements.txt", os.path.join("server", "main.py")]
# 列出要更新的檔案時，最多列幾個（其他的只寫還有幾個）
SHOW_FILES = 15
# start.bat 看到這個結束代碼就不啟動（更新完你選了「不要開啟」）
NO_START = 20

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 上次比過、確定跟這個資料夾一樣的版本編號記在這裡
CHECKED_FILE = os.path.join(PROJECT, ".venv", "update_version.txt")


def say(english, chinese):
    """印一句話：英文一行、中文一行"""
    print(english)
    print(chinese)


def open_url(url, seconds, accept=""):
    """連到 url，回傳可以讀的東西"""
    headers = {"User-Agent": "local-ktv-updater"}
    if accept != "":
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=seconds)


def latest_version():
    """GitHub 上最新版的編號；連不上、或回來的不是編號就回傳空字串"""
    try:
        with open_url(VERSION_URL, CHECK_SECONDS, "application/vnd.github.sha") as reply:
            text = reply.read(200).decode("ascii", "ignore").strip()
    except Exception:
        return ""
    if re.fullmatch(r"[0-9a-f]{40}", text):
        return text
    return ""


def read_checked():
    """上次比過的版本編號（沒有就是空字串）"""
    try:
        with open(CHECKED_FILE, encoding="ascii") as file:
            return file.read().strip()
    except OSError:
        return ""


def write_checked(version):
    """記下「這個資料夾跟這個版本一樣」（不知道編號、或還沒有 .venv 就不記）"""
    if version == "" or not os.path.isdir(os.path.dirname(CHECKED_FILE)):
        return
    with open(CHECKED_FILE, "w", encoding="ascii") as file:
        file.write(version + "\n")


def zip_url(version):
    """最新版壓縮檔的網址：知道編號就抓那一版，不知道就抓分支最新的"""
    if version != "":
        return REPO_PAGE + "/archive/" + version + ".zip"
    return REPO_PAGE + "/archive/refs/heads/" + BRANCH + ".zip"


def download(url, target):
    """把 url 下載到 target 這個檔案"""
    with open_url(url, DOWNLOAD_SECONDS) as reply:
        with open(target, "wb") as file:
            shutil.copyfileobj(reply, file)


def unpack(zip_path, folder):
    """解壓縮到 folder，回傳裡面那一層程式資料夾的路徑（GitHub 的壓縮檔最外面會多包一層資料夾）"""
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            # 路徑不能跑到資料夾外面
            if name.startswith("/") or name.startswith("\\") or ".." in name.replace("\\", "/").split("/"):
                raise ValueError("壓縮檔裡有奇怪的路徑：" + name)
        archive.extractall(folder)
    inside = os.listdir(folder)
    if len(inside) == 1 and os.path.isdir(os.path.join(folder, inside[0])):
        return os.path.join(folder, inside[0])
    return folder


def all_files(folder):
    """folder 裡全部的檔案（相對路徑）"""
    result = []
    for root, directories, files in os.walk(folder):
        for name in files:
            full = os.path.join(root, name)
            result.append(os.path.relpath(full, folder))
    result.sort()
    return result


def same_content(first, second):
    """兩個檔案內容是不是一模一樣"""
    if not os.path.exists(first) or not os.path.exists(second):
        return False
    with open(first, "rb") as file:
        first_bytes = file.read()
    with open(second, "rb") as file:
        second_bytes = file.read()
    return first_bytes == second_bytes


def find_changes(new_folder):
    """最新版裡，這個資料夾沒有、或內容不一樣的檔案（相對路徑）"""
    changed = []
    for name in all_files(new_folder):
        if not same_content(os.path.join(new_folder, name), os.path.join(PROJECT, name)):
            changed.append(name)
    return changed


def ask_yes_no(english, chinese):
    """問一個要不要的問題，回傳 True = 要（一定要打 Y 或 N）"""
    while True:
        print(english + " [Y] Yes  [N] No")
        try:
            answer = input(chinese + " [Y] 要  [N] 不要：").strip().lower()
        except EOFError:
            return False   # 沒辦法輸入（不是在視窗裡跑）：當成不要
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def replace_files(new_folder, changed, backup_folder):
    """把 changed 這些檔案換成新的；舊的先備份到 backup_folder。回傳備份了幾個檔案"""
    saved = 0
    for name in changed:
        target = os.path.join(PROJECT, name)
        if os.path.exists(target):
            backup = os.path.join(backup_folder, name)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(target, backup)
            saved += 1
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(new_folder, name), target)
    return saved


def installed():
    """這個程式的虛擬環境（.venv）裝好了沒、現在是不是用它在跑"""
    venv = os.path.join(PROJECT, ".venv")
    running = os.path.abspath(sys.executable)
    return running.startswith(os.path.abspath(venv) + os.sep)


def install_packages():
    """照 requirements.txt 安裝套件，回傳 True = 成功"""
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=PROJECT)
    return result.returncode == 0


def fetch_latest(version, work):
    """下載、解開最新版，回傳程式資料夾的路徑；失敗回傳 None（訊息已經印了）"""
    url = zip_url(version)
    say("Downloading the latest version from: " + url, "正在下載最新版，來源：" + url)
    zip_path = os.path.join(work, "latest.zip")
    try:
        download(url, zip_path)
        new_folder = unpack(zip_path, os.path.join(work, "files"))
    except Exception as error:
        say("Could not download the latest version. Check your connection and try again.",
            "下載不了最新版，請確認網路後再試一次。")
        print(error)
        return None
    for name in MUST_HAVE:
        if not os.path.exists(os.path.join(new_folder, name)):
            say("The download does not look like this app. Nothing was changed.",
                "下載回來的東西不像是這個程式，什麼都沒有改。")
            return None
    return new_folder


def show_changes(changed):
    """列出要更新的檔案"""
    print()
    say("A newer version is available. %d file(s) will be updated:" % len(changed),
        "有新版，會更新 %d 個檔案：" % len(changed))
    for name in changed[:SHOW_FILES]:
        print("  " + name)
    if len(changed) > SHOW_FILES:
        say("  ... and %d more" % (len(changed) - SHOW_FILES), "  …還有 %d 個" % (len(changed) - SHOW_FILES))
    say("Your songs and scores are not touched. The old files are backed up first.",
        "不會動到你的歌和分數。舊的檔案會先備份。")
    print()


def apply_update(new_folder, changed):
    """換檔案、需要的話裝套件。回傳 True = 都成功"""
    backup_folder = os.path.join(PROJECT, "data", "update_backup", time.strftime("%Y%m%d-%H%M%S"))
    saved = replace_files(new_folder, changed, backup_folder)
    say("Updated %d file(s)." % len(changed), "更新了 %d 個檔案。" % len(changed))
    if saved > 0:
        say("Old files are in: " + backup_folder, "舊的檔案在：" + backup_folder)
    if not installed():
        # 還沒安裝環境（例如只下載了 update.bat）：套件留給 start.bat 第一次啟動時裝，不動電腦裡的 Python
        return True
    if "requirements.txt" in changed:
        say("The package list changed. Installing packages with pip (source: https://pypi.org)...",
            "套件清單有變，正在用 pip 安裝套件（來源：https://pypi.org）…")
        if not install_packages():
            say("Installing packages failed. Please run setup.bat again.",
                "套件安裝失敗，請再執行一次 setup.bat")
            return False
    return True


def main(from_start):
    """from_start：是不是 start.bat 啟動時叫的。回傳結束代碼"""
    if os.path.exists(os.path.join(PROJECT, ".git")):
        if not from_start:
            say("This folder is managed by Git. Please update it with Git.",
                "這個資料夾是 Git 管理的，請用 Git 更新。")
        return 0

    version = latest_version()
    if from_start:
        # 啟動時：連不上、或跟上次比過的版本一樣，就什麼都不做，照常啟動
        if version == "" or version == read_checked():
            return 0

    work = tempfile.mkdtemp(prefix="local-ktv-update-")
    try:
        new_folder = fetch_latest(version, work)
        if new_folder is None:
            return 0 if from_start else 1
        changed = find_changes(new_folder)
        if len(changed) == 0:
            write_checked(version)
            if not from_start:
                say("You already have the latest version.", "已經是最新版了。")
            return 0

        show_changes(changed)
        if not ask_yes_no("Update now?", "要現在更新嗎？"):
            say("Not updated. The current version is used.", "沒有更新，繼續用現在的版本。")
            return 0
        if not apply_update(new_folder, changed):
            return 1
        write_checked(version)

        if not installed():
            say("Done. Run start.bat: the first run installs everything.",
                "更新完成。執行 start.bat，第一次會自動安裝。")
            return 0
        if from_start:
            say("Update finished.", "更新完成。")
            if not ask_yes_no("Start Local KTV now?", "要現在開啟本機KTV嗎？"):
                return NO_START
            return 0
        say("Done. Run start.bat to start.", "更新完成，執行 start.bat 就可以開始。")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main("--start" in sys.argv[1:]))
