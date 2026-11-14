"""
清掉用不到的套件：套件清單（requirements*.txt）改過之後，舊清單裝的、新清單用不到的套件，從 .venv 移到資源回收筒。
按 update.bat 時跑（tools\\update.py 的 tidy_up），不連網，沒事的話不到一秒。

怎麼知道哪些是「舊清單裝的」：
  每次跑完都記一份「照現在的清單，要裝哪些套件」在 .venv\\packages_from_lists.txt。
  下次清單改了，記錄裡有、現在不需要的，就是舊清單裝、新清單用不到的 → 直接移掉，跟你說移了哪些。
  不在記錄裡的（你自己裝的）不會動。
還沒有記錄的時候：分不出是舊清單裝的還是你自己裝的，所以列出「現在的清單用不到的套件」問你 Y / N。
  選了留著（N）的記在 .venv\\packages_kept.txt，下次按 update.bat 會再問一次。
移的時候：
  1. 照每個套件自己的檔案清單（RECORD），把它的資料夾和檔案搬到 .venv\\removed_packages\\時間\\
     （跟留下來的套件共用的不搬）
  2. 確認程式還載得起來（import server.main）。載不起來就全部搬回去
  3. 載得起來：整個資料夾丟到資源回收筒。丟不了等一下再試（RECYCLE_TRIES）；還是不行就先留在原地、告訴你在哪裡，
     下次跑的時候再丟一次（recycle_leftovers）
畫面上的訊息每一句都有英文和中文。
"""
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import time

from update import PACKAGE_LISTS, ask_yes_no, say

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(PROJECT, ".venv")
SITE = os.path.join(VENV, "Lib", "site-packages")
RECORD_FILE = os.path.join(VENV, "packages_from_lists.txt")
KEPT_FILE = os.path.join(VENV, "packages_kept.txt")   # 問過、你選了留著的（更新的時候再問）
REMOVED_FOLDER = os.path.join(VENV, "removed_packages")
# 丟資源回收筒失敗的話，最多試幾次、每次之間等幾秒（to_recycle_bin）
RECYCLE_TRIES = 3
RECYCLE_WAIT_SECONDS = 3
# 建立虛擬環境就有的，不算在清單裡，也不會被移掉
ALWAYS_KEEP = ["pip"]
# 套件清單裡沒寫、但程式需要的檢查：移完之後確認這個載得起來
CHECK_COMMAND = [sys.executable, "-c", "import server.main"]


def plain_name(name):
    """套件名字統一寫法（大小寫、- _ . 都當成一樣），例如 PyYAML、pyyaml 是同一個"""
    return re.sub(r"[-_.]+", "-", name).lower()


def list_entries():
    """每一份套件清單裡的套件：[(名字, 要不要連它需要的其他套件一起算)]"""
    entries = []
    for file_name, extra in PACKAGE_LISTS:
        path = os.path.join(PROJECT, file_name)
        if not os.path.exists(path):
            continue
        with_deps = "--no-deps" not in extra
        with open(path, encoding="utf-8") as file:
            for line in file:
                line = line.split("#")[0].strip()
                if line == "" or line.startswith("-"):
                    continue   # 空白行、說明、--index-url 這類設定
                found = re.match(r"[A-Za-z0-9._-]+", line)
                if found:
                    entries.append((plain_name(found.group(0)), with_deps))
    return entries


def installed_packages():
    """.venv 裡裝了哪些套件：{名字: 套件資料}"""
    result = {}
    for dist in importlib.metadata.distributions(path=[SITE]):
        name = dist.metadata["Name"]
        if name:
            result[plain_name(name)] = dist
    return result


def needed_packages(installed, entries):
    """照現在的清單要裝哪些套件：清單上的，加上它們需要的、需要的再需要的…（照每個套件寫的 Requires-Dist）"""
    from pip._vendor.packaging.requirements import Requirement

    result = set()
    todo = []
    for name, with_deps in entries:
        if with_deps:
            todo.append(name)
        else:
            result.add(name)
    while len(todo) > 0:
        name = todo.pop()
        if name in result:
            continue
        result.add(name)
        dist = installed.get(name)
        if dist is None:
            continue
        for text in dist.requires or []:
            requirement = Requirement(text)
            # 只在某些情況才需要的（例如 extra == "dev"、別的作業系統）不算
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            todo.append(plain_name(requirement.name))
    return result


def read_names(path):
    """讀一份套件名字的記錄（一行一個）；檔案不存在回傳 None"""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as file:
        return set(line.strip() for line in file if line.strip() != "")


def write_names(path, names):
    """寫一份套件名字的記錄；沒有名字就把檔案刪掉"""
    if len(names) == 0:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as file:
        for name in sorted(names):
            file.write(name + "\n")


def inside_venv(path):
    """path 是不是在這個程式的 .venv 裡面（不是 .venv 本身、也不是外面）。搬東西之前都要先過這一關"""
    root = os.path.normcase(os.path.abspath(VENV))
    full = os.path.normcase(os.path.abspath(path))
    return full.startswith(root + os.sep)


def items_of(dist):
    """
    這個套件佔的東西：site-packages 底下的第一層資料夾或檔案，和 site-packages 外面、.venv 裡面的檔案
    （例如 Scripts 裡的指令）。套件的檔案清單如果寫到 .venv 外面，那些不算，不會動
    """
    site = os.path.normcase(os.path.abspath(SITE))
    result = set()
    for part in dist.files or []:
        full = os.path.abspath(str(dist.locate_file(part)))
        if os.path.normcase(full).startswith(site + os.sep):
            first = full[len(site) + 1:].split(os.sep)[0]
            if first != "__pycache__":
                result.add(os.path.join(SITE, first))
        elif inside_venv(full):
            result.add(full)
    return result


def move_away(names, installed):
    """把 names 這些套件搬到 .venv\\removed_packages\\時間\\。回傳 (搬到哪個資料夾, [(原本的位置, 搬到的位置)])"""
    keep = set()
    for name, dist in installed.items():
        if name not in names:
            keep.update(os.path.normcase(item) for item in items_of(dist))
    folder = os.path.join(REMOVED_FOLDER, time.strftime("%Y%m%d-%H%M%S"))
    moved = []
    for name in names:
        for item in sorted(items_of(installed[name])):
            if os.path.normcase(item) in keep or not os.path.exists(item) or not inside_venv(item):
                continue   # 跟留下來的套件共用的、已經不在的、不在 .venv 裡的
            target = os.path.join(folder, os.path.relpath(item, VENV))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(item, target)
            moved.append((item, target))
    return folder, moved


def move_back(moved):
    for original, target in reversed(moved):
        if os.path.exists(target) and not os.path.exists(original):
            shutil.move(target, original)


def recycle_once(path):
    """
    把 path 丟到資源回收筒一次（Windows 的 SHFileOperationW）。回傳結果代碼：0 = 成功；
    其他是 Windows 給的代碼，-1 = 叫不到這個功能，-2 = Windows 說好了、東西卻還在
    """
    import ctypes
    from ctypes import wintypes

    class FileOperation(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    delete = 3                                     # FO_DELETE
    flags = 0x0040 | 0x0010 | 0x0004 | 0x0400      # 可以還原、不要問、不顯示進度、不跳錯誤視窗
    operation = FileOperation()
    operation.wFunc = delete
    operation.pFrom = os.path.abspath(path) + "\0"   # 結尾要兩個 \0
    operation.fFlags = flags
    try:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    except (AttributeError, OSError):
        return -1
    if result == 0 and (operation.fAnyOperationsAborted or os.path.exists(path)):
        return -2
    return result


def to_recycle_bin(path):
    """
    把 path 丟到資源回收筒。成功回傳 True。
    失敗的話等一下再試（剛搬過的檔案，防毒軟體有時還在掃描、暫時鎖住），試了 RECYCLE_TRIES 次還是不行，
    就把 Windows 給的代碼印出來（查原因用）
    """
    code = 0
    for attempt in range(RECYCLE_TRIES):
        if attempt > 0:
            time.sleep(RECYCLE_WAIT_SECONDS)
        code = recycle_once(path)
        if code == 0:
            return True
    if code > 0:
        code_text = hex(code)
    else:
        code_text = str(code)
    say("Could not move it to the Recycle Bin (code from Windows: " + code_text + ").",
        "丟不到資源回收筒（Windows 回傳的代碼：" + code_text + "）。")
    return False


def remove_empty_folder(path):
    """path 是空的資料夾就拿掉"""
    if os.path.isdir(path) and len(os.listdir(path)) == 0:
        os.rmdir(path)


def packages_in(folder):
    """
    移掉的套件放的資料夾（.venv\\removed_packages\\時間\\）裡有哪些套件：["名字 版本", ...]
    看裡面每個套件的 *.dist-info（套件自己的名字、版本記在這裡）
    """
    site = os.path.join(folder, "Lib", "site-packages")
    result = []
    if not os.path.isdir(site):
        return result
    for name in sorted(os.listdir(site)):
        if not name.endswith(".dist-info"):
            continue
        try:
            dist = importlib.metadata.Distribution.at(os.path.join(site, name))
            result.append(dist.metadata["Name"] + " " + dist.version)
        except Exception:
            result.append(name[:-len(".dist-info")])
    return result


def recycle_leftovers():
    """
    以前移掉、但當時丟不到資源回收筒的套件（還放在 .venv\\removed_packages\\時間\\），列出是哪些套件，再丟一次。
    這些當時已經確定要移掉、而且程式沒有它們也載得起來，所以不用再問
    """
    if not os.path.isdir(REMOVED_FOLDER):
        return
    names = sorted(os.listdir(REMOVED_FOLDER))
    if len(names) > 0:
        print()
        say("Packages removed earlier are still kept in " + REMOVED_FOLDER + ". Moving them to the Recycle Bin again:",
            "以前移掉的套件還放在 " + REMOVED_FOLDER + "，再丟一次資源回收筒：")
        for name in names:
            path = os.path.join(REMOVED_FOLDER, name)
            print("  " + name)
            packages = packages_in(path)
            if len(packages) == 0:
                say("    (no package names found inside)", "    （裡面看不出是哪些套件）")
            for package in packages:
                print("    " + package)
            if to_recycle_bin(path):
                say("Moved to the Recycle Bin: " + name, "已經丟到資源回收筒：" + name)
            else:
                say("Still kept here (you can delete it yourself): " + path,
                    "還留在這裡（可以自己刪掉）：" + path)
        print()
    remove_empty_folder(REMOVED_FOLDER)


def remove_packages(names, installed):
    """移掉 names 這些套件（先搬走、確認程式載得起來、再丟到資源回收筒）。回傳 True = 成功"""
    folder, moved = move_away(names, installed)
    check = subprocess.run(CHECK_COMMAND, cwd=PROJECT, capture_output=True)
    if check.returncode != 0:
        move_back(moved)
        shutil.rmtree(folder, ignore_errors=True)
        say("After removing them the app could not load, so they were put back. Nothing was changed.",
            "移掉之後程式載不起來，所以全部放回去了，什麼都沒有改。")
        return False
    if to_recycle_bin(folder):
        say("Moved to the Recycle Bin.", "已經移到資源回收筒。")
        remove_empty_folder(REMOVED_FOLDER)
    else:
        say("Removed. The files are kept here for now: " + folder,
            "已經移掉。檔案先放在這裡：" + folder)
        say("Next time you run update.bat it tries the Recycle Bin again. You can also delete this folder yourself.",
            "下次按 update.bat 會再試一次丟到資源回收筒，也可以自己刪掉這個資料夾。")
    return True


def show_names(names, installed):
    for name in names:
        print("  " + installed[name].metadata["Name"] + " " + installed[name].version)


def ask_and_remove(names, installed):
    """問要不要移掉 names 這些套件。回傳還留著的（你選了不要、或移不掉的）"""
    if ask_yes_no("Move them to the Recycle Bin?", "要移到資源回收筒嗎？"):
        if remove_packages(names, installed):
            return set()
        return set(names)
    say("Kept. To remove them later, run update.bat any time (no new version needed) and you will be asked again.",
        "先留著。之後想刪的話，隨時按 update.bat 就會再問一次（不用等有新版）。")
    return set(names)


def main():
    if os.path.normcase(os.path.abspath(sys.prefix)) != os.path.normcase(os.path.abspath(VENV)):
        return   # 不是用這個程式的 .venv 在跑
    try:
        from pip._vendor.packaging.requirements import Requirement  # noqa: F401（看 pip 在不在）
    except ImportError:
        return
    recycle_leftovers()
    entries = list_entries()
    if len(entries) == 0:
        return
    installed = installed_packages()
    now = needed_packages(installed, entries)
    before = read_names(RECORD_FILE)
    kept = read_names(KEPT_FILE) or set()
    asked = set()   # 這一次已經問過的（同一次不要問兩遍）

    if before is None:
        # 還沒有記錄：分不出是誰裝的，問一次
        extra = sorted(set(installed) - now - set(plain_name(n) for n in ALWAYS_KEEP))
        if len(extra) > 0:
            print()
            say("These %d package(s) are not used by the current package lists." % len(extra),
                "這 %d 個套件現在的套件清單用不到：" % len(extra))
            show_names(extra, installed)
            say("They may be from an older version of this app, or you may have installed them yourself.",
                "可能是舊版裝的，也可能是你自己裝的。")
            kept = kept | ask_and_remove(extra, installed)
            asked = set(extra)
            print()
    else:
        # 有記錄：記錄裡有、現在用不到的，是舊清單裝的，直接移掉（移不掉的留著，更新時再問）
        leftover = sorted((before & set(installed)) - now - kept)
        if len(leftover) > 0:
            print()
            say("The package lists changed. %d package(s) from the old lists are no longer used:" % len(leftover),
                "套件清單改過了，舊清單裝的這 %d 個套件新版用不到：" % len(leftover))
            show_names(leftover, installed)
            if not remove_packages(leftover, installed):
                kept = kept | set(leftover)
            print()

    # 你上次選了留著、現在還是用不到的，再問一次
    installed = installed_packages()
    kept = (kept & set(installed)) - now
    names = sorted(kept - asked)
    if len(names) > 0:
        print()
        say("Last time you chose to keep these %d package(s). They are still not used by this app:" % len(names),
            "上次你選了留著的這 %d 個套件，現在的程式還是用不到：" % len(names))
        show_names(names, installed)
        kept = (kept - set(names)) | ask_and_remove(names, installed)
        print()
    write_names(KEPT_FILE, kept)
    write_names(RECORD_FILE, now)


if __name__ == "__main__":
    main()
