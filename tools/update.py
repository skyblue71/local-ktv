"""
更新和整理：看 GitHub 上有沒有新版，有的話問要不要更新；再整理套件和 AI 模型。

兩種用法：
  python tools\\update.py           update.bat 用：更新（問 Y / N）、整理（tidy_up）
  python tools\\update.py --start   start.bat 啟動時用：只看有沒有新版，有就說一句「要更新請按 update.bat」，
                                   不問、不改任何東西
做法：
  1. （--start）問 GitHub 最新版的編號（很小的一次連線）。連不上、或跟上次比過的一樣：什麼都不做
  2. 下載最新版的壓縮檔到暫存資料夾（只有程式，不到幾 MB）
  3. 一個一個檔案比：最新版有、這裡沒有或內容不一樣的，就是要更新的
     另外問 GitHub「上次比過的版本」到「最新版」之間拿掉了哪些程式檔（removed_files），這裡還有的就要刪掉；
     （update.bat）再加上 OLD_PROGRAM_FILES 名單上、這裡還有的（old_program_files：從哪一版更新過來都刪得到）
  4. 都一樣、也沒有要刪的：已經是最新版，記下編號
  5. 有不一樣：（--start）說一句有新版就結束；（update.bat）列出來，問 Y / N。按 Y 才會動這個資料夾
  6. 更新：被換掉、被刪掉的舊檔案先備份到 data\\update_backup\\時間\\，再放上新的、刪掉舊的
  7. 套件清單（requirements-torch.txt、requirements.txt、requirements-nodeps.txt）有變：用 pip 安裝套件
     （只裝在這個程式的 .venv 裡；還沒安裝環境就不裝，留給 start.bat 第一次啟動）
  8. 整理（tidy_up，按 update.bat 就會做，不管有沒有新版、按 Y 還是 N、資料夾是不是 Git 管理的）：
     - 套件：清掉 .venv 裡現在的程式用不到的（tools\\clean_packages.py）
     - AI 模型：少了的問要不要下載（tools\\download_model.py --ask）、以前用過現在不用的問要不要清掉（tools\\clean_models.py）
不會動的：data（歌、分數）、models（AI 模型，交給第 8 步）、.venv、你自己放進這個資料夾的檔案
（只刪我們的舊版有、新版拿掉的程式檔：GitHub 說拿掉的、和 OLD_PROGRAM_FILES 名單上的）。
這個資料夾如果是 Git 管理的（有 .git）：不動檔案（換掉檔案的話，之後用 Git 更新會打架）。
  GitHub 上有這個資料夾還沒抓過的新版，就提醒一句「請執行 git pull」（remind_git）。
只用 Python 內建的功能，所以還沒安裝環境、只有 update.bat 一個檔案的時候也能跑。
畫面上的訊息每一句都有英文和中文。
"""
import json
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
# 比較兩個版本差在哪些檔案的網址（{old}、{new} 換成版本編號）
COMPARE_URL = "https://api.github.com/repos/" + REPO + "/compare/{old}...{new}"
# 這些資料夾裡的東西一定不刪（歌和分數、AI 模型、虛擬環境、Git 的資料）
NEVER_REMOVE = ["data", "models", ".venv", ".git"]
# 以前有、後來拿掉的程式檔（相對路徑，用 /）。按 update.bat 時，這個資料夾裡還有、最新版裡也沒有的，
# 跟新版拿掉的檔案一起列出來，按 Y 才先備份再刪掉。拿掉一個程式檔的時候，把它的名字加進這裡
#   （只靠「上次比過的版本」到「最新版」之間的差別會漏掉：例如用舊版的更新程式更新過，那一段拿掉的就不知道了）
OLD_PROGRAM_FILES = [
    "server/demucs_separator.py",
]
# 連線最多等幾秒：啟動時問編號要快（連不上就照常啟動），下載壓縮檔可以久一點
CHECK_SECONDS = 5
DOWNLOAD_SECONDS = 60
# 下載回來的東西裡一定要有這幾個檔案，才算是這個程式（不然不更新）
MUST_HAVE = ["start.bat", "setup.bat", "requirements.txt", os.path.join("server", "main.py")]
# 列出要更新的檔案時，最多列幾個（其他的只寫還有幾個）
SHOW_FILES = 15
# 按 update.bat 時整理用的程式（tools 資料夾裡的檔名, 要加的參數），照這個順序跑（tidy_up）
TIDY_STEPS = [
    ("clean_packages.py", []),                   # 套件：清掉用不到的
    ("download_model.py", ["--ask"]),            # AI 模型：少了的問要不要下載
    ("clean_models.py", []),                     # AI 模型：以前用過、現在不用的問要不要清掉
]

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


def inside_project(path):
    """path 是不是在這個程式的資料夾裡面（不是資料夾本身、也不是外面）。換檔案、刪檔案之前都要先過這一關"""
    root = os.path.normcase(os.path.abspath(PROJECT))
    full = os.path.normcase(os.path.abspath(path))
    return full.startswith(root + os.sep)


def removed_files(old, new):
    """
    舊版（old）有、新版（new）拿掉的程式檔，而且這個資料夾裡還有的（相對路徑）。
    問 GitHub 這兩個版本差在哪裡：狀態是「removed」的、和「renamed」的舊名字。
    不知道舊版是哪一版、連不上、或回來的東西看不懂：回傳空的（什麼都不刪）
    """
    if old == "" or new == "" or old == new:
        return []
    try:
        with open_url(COMPARE_URL.format(old=old, new=new), DOWNLOAD_SECONDS, "application/vnd.github+json") as reply:
            data = json.loads(reply.read().decode("utf-8"))
    except Exception:
        return []
    names = []
    for item in data.get("files", []):
        if item.get("status") == "removed":
            names.append(item.get("filename", ""))
        elif item.get("status") == "renamed":
            names.append(item.get("previous_filename", ""))
    result = []
    for name in names:
        parts = name.split("/")
        # 路徑不能跑到資料夾外面，也不能在一定不刪的資料夾裡
        if name == "" or name.startswith("/") or ".." in parts or parts[0] in NEVER_REMOVE:
            continue
        local = os.path.join(*parts)
        full = os.path.join(PROJECT, local)
        if inside_project(full) and os.path.isfile(full):
            result.append(local)
    result.sort()
    return result


def old_program_files(new_folder):
    """OLD_PROGRAM_FILES 名單上、這個資料夾裡還有、最新版（new_folder）裡沒有的檔案（相對路徑）"""
    result = []
    for name in OLD_PROGRAM_FILES:
        parts = name.split("/")
        # 路徑不能跑到資料夾外面，也不能在一定不刪的資料夾裡
        if name == "" or name.startswith("/") or ".." in parts or parts[0] in NEVER_REMOVE:
            continue
        local = os.path.join(*parts)
        full = os.path.join(PROJECT, local)
        if inside_project(full) and os.path.isfile(full) and not os.path.exists(os.path.join(new_folder, local)):
            result.append(local)
    return result


def ask_yes_no(english, chinese):
    """問一個要不要的問題，回傳 True = 要（一定要打 Y 或 N）"""
    while True:
        print(english + " [Y] Yes  [N] No")
        try:
            # 有些程式傳進來的字最前面會多一個看不見的字元（BOM，﻿），一起拿掉
            answer = input(chinese + " [Y] 要  [N] 不要：").replace("﻿", "").strip().lower()
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
        if not inside_project(target):
            continue   # 不在這個資料夾裡的不動
        if os.path.exists(target):
            backup = os.path.join(backup_folder, name)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(target, backup)
            saved += 1
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(new_folder, name), target)
    return saved


def remove_files(removed, backup_folder):
    """刪掉 removed 這些舊的程式檔（先搬到 backup_folder 備份）；刪完變成空的資料夾也拿掉"""
    for name in removed:
        target = os.path.join(PROJECT, name)
        if not inside_project(target) or not os.path.isfile(target):
            continue   # 不在這個資料夾裡的、不是檔案的不動
        backup = os.path.join(backup_folder, name)
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        shutil.move(target, backup)
        folder = os.path.dirname(target)
        while inside_project(folder) and os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
            folder = os.path.dirname(folder)


def installed():
    """這個程式的虛擬環境（.venv）裝好了沒、現在是不是用它在跑"""
    venv = os.path.join(PROJECT, ".venv")
    running = os.path.abspath(sys.executable)
    return running.startswith(os.path.abspath(venv) + os.sep)


# 套件清單：(檔名, pip 要多加的參數)。跟 setup.bat 裝的一樣（tools\clean_packages.py 也照這份）
PACKAGE_LISTS = [
    ("requirements-torch.txt", []),               # PyTorch（清單裡寫了從 PyTorch 官方網站下載）
    ("requirements.txt", []),
    ("requirements-nodeps.txt", ["--no-deps"]),   # 只裝套件本身，不裝它要的其他套件
]


def install_packages():
    """照套件清單安裝套件，回傳 True = 成功"""
    for name, extra in PACKAGE_LISTS:
        # --no-cache-dir：pip 不要在資料夾外面（使用者資料夾的 AppData）另外存一份下載的檔案
        command = [sys.executable, "-m", "pip", "install", "--no-cache-dir"] + extra + ["-r", name]
        result = subprocess.run(command, cwd=PROJECT)
        if result.returncode != 0:
            return False
    return True


def package_list_changed(changed):
    """更新的檔案裡有沒有套件清單"""
    for name, _ in PACKAGE_LISTS:
        if name in changed:
            return True
    return False


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


def show_names(names):
    for name in names[:SHOW_FILES]:
        print("  " + name)
    if len(names) > SHOW_FILES:
        say("  ... and %d more" % (len(names) - SHOW_FILES), "  …還有 %d 個" % (len(names) - SHOW_FILES))


def show_changes(changed, removed):
    """列出要更新、要刪掉的檔案（只有要刪的、沒有要更新的：不說「有新版」）"""
    print()
    if len(changed) > 0:
        say("A newer version is available.", "有新版。")
        say("%d file(s) will be updated:" % len(changed), "會更新 %d 個檔案：" % len(changed))
        show_names(changed)
    if len(removed) > 0:
        say("%d old file(s) are no longer part of the app and will be removed:" % len(removed),
            "新版拿掉了 %d 個舊的程式檔，會刪掉：" % len(removed))
        show_names(removed)
    say("Your songs and scores are not touched, and neither are files you added yourself. The old files are backed up first.",
        "不會動到你的歌和分數，也不會動你自己放的檔案。舊的檔案會先備份。")
    print()


def apply_update(new_folder, changed, removed):
    """換檔案、刪掉新版拿掉的舊檔案、需要的話裝套件。回傳 True = 都成功"""
    backup_folder = os.path.join(PROJECT, "data", "update_backup", time.strftime("%Y%m%d-%H%M%S"))
    saved = replace_files(new_folder, changed, backup_folder)
    remove_files(removed, backup_folder)
    if len(changed) > 0:
        say("Updated %d file(s)." % len(changed), "更新了 %d 個檔案。" % len(changed))
    if len(removed) > 0:
        say("Removed %d old file(s)." % len(removed), "刪掉了 %d 個舊的程式檔。" % len(removed))
    if saved + len(removed) > 0:
        say("Old files are in: " + backup_folder, "舊的檔案在：" + backup_folder)
    if not installed():
        # 還沒安裝環境（例如只下載了 update.bat）：套件留給 start.bat 第一次啟動時裝，不動電腦裡的 Python
        return True
    if package_list_changed(changed):
        say("The package list changed. Installing packages with pip (source: https://pypi.org)...",
            "套件清單有變，正在用 pip 安裝套件（來源：https://pypi.org）…")
        if not install_packages():
            say("Installing packages failed. Please run setup.bat again.",
                "套件安裝失敗，請再執行一次 setup.bat")
            return False
    return True


def tidy_up():
    """
    按 update.bat：照 TIDY_STEPS 整理套件和 AI 模型（每個程式自己會說明、該問的會問）。
    用新版的檔案跑（更新完才叫這個）。還沒安裝環境、或沒有那個檔案就不跑
    """
    if not installed():
        return
    for name, extra in TIDY_STEPS:
        path = os.path.join(PROJECT, "tools", name)
        if os.path.exists(path):
            subprocess.run([sys.executable, path] + extra, cwd=PROJECT)


def known_versions():
    """
    這個 Git 資料夾認得的版本編號：現在用的版本、每個分支、上次從 GitHub 抓回來的。
    直接讀 .git 裡記編號的小檔案，不用呼叫 git（電腦裡不一定有 git 指令）。讀不到就是空的
    """
    git_folder = os.path.join(PROJECT, ".git")
    paths = []
    for name in ["HEAD", "ORIG_HEAD", "FETCH_HEAD", "packed-refs"]:
        paths.append(os.path.join(git_folder, name))
    for folder, _, names in os.walk(os.path.join(git_folder, "refs")):
        for name in names:
            paths.append(os.path.join(folder, name))
    found = set()
    for path in paths:
        try:
            with open(path, encoding="ascii", errors="ignore") as file:
                found.update(re.findall(r"[0-9a-f]{40}", file.read()))
        except OSError:
            pass
    return found


def remind_git(from_start):
    """
    這個資料夾是 Git 管理的：不動檔案，只提醒。回傳結束代碼
    GitHub 上最新的版本，這個資料夾不認得（還沒抓過）→ 提醒一句「請執行 git pull」。
    認得的話不提醒：已經是最新版，或這裡有自己還沒上傳的修改
    """
    version = latest_version()
    known = known_versions()
    if version != "" and len(known) > 0 and version not in known:
        say("A newer version is on GitHub. To update, run:  git pull",
            "GitHub 上有新版。要更新請執行：  git pull")
    elif not from_start:
        say("This folder is managed by Git. Please update it with Git.",
            "這個資料夾是 Git 管理的，請用 Git 更新。")
    if not from_start:
        tidy_up()   # 按 update.bat：程式檔交給 Git，套件和 AI 模型還是一樣整理
    return 0


def main(from_start):
    """from_start：是不是 start.bat 啟動時叫的。回傳結束代碼"""
    if os.path.exists(os.path.join(PROJECT, ".git")):
        return remind_git(from_start)

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
        removed = removed_files(read_checked(), version)
        if not from_start:
            # 按 update.bat：名單上以前拿掉、這裡還有的舊程式檔也一起列（啟動時只看有沒有新版）
            for name in old_program_files(new_folder):
                if name not in removed:
                    removed.append(name)
            removed.sort()
        if len(changed) == 0 and len(removed) == 0:
            write_checked(version)
            if not from_start:
                say("You already have the latest version.", "已經是最新版了。")
                tidy_up()
            return 0

        if from_start:
            # 啟動時只說一句，不問、不改（下次啟動還沒更新的話會再說）
            print()
            say("A newer version is available. To update: close Local KTV, then run update.bat.",
                "有新版。要更新的話：關掉本機KTV，再按 update.bat。")
            print()
            return 0

        show_changes(changed, removed)
        if len(changed) > 0:
            agreed = ask_yes_no("Update now?", "要現在更新嗎？")
            refused = ("Not updated. The current version is used.", "沒有更新，繼續用現在的版本。")
        else:
            agreed = ask_yes_no("Remove them now?", "要現在刪掉嗎？")
            refused = ("Kept. You will be asked again the next time you run update.bat.", "先留著。下次按 update.bat 會再問。")
        if not agreed:
            say(refused[0], refused[1])
            tidy_up()
            return 0
        if not apply_update(new_folder, changed, removed):
            return 1
        write_checked(version)
        tidy_up()

        if not installed():
            say("Done. Run start.bat: the first run installs everything.",
                "更新完成。執行 start.bat，第一次會自動安裝。")
            return 0
        say("Done. Run start.bat to start.", "更新完成，執行 start.bat 就可以開始。")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main("--start" in sys.argv[1:]))
