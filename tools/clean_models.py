"""
清掉不用的 AI 模型（按 update.bat 時跑，tools\\update.py 的 tidy_up）：
  以前用過、現在不用的模型資料夾（server\\config.py 的 OLD_MODEL_FOLDERS），還在 models\\ 裡的話，
  列出名字和大小，問要不要丟到資源回收筒。
只動 models\\ 底下 OLD_MODEL_FOLDERS 寫的那幾個資料夾：現在還在用的、你自己放進 models\\ 的都不會動。
選了留著：下次按 update.bat 會再問。沒有要清的就什麼都不印。
畫面上的訊息每一句都有英文和中文。
"""
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 讓這個程式找得到 server 資料夾（讀 config.py）
sys.path.insert(0, PROJECT)

from clean_packages import to_recycle_bin   # noqa: E402（同一個 tools 資料夾的檔案）
from update import ask_yes_no, say          # noqa: E402

MB = 1024 * 1024


def folder_size(path):
    """資料夾裡全部檔案加起來多大（位元組）"""
    total = 0
    for root, _, names in os.walk(path):
        for name in names:
            total += os.path.getsize(os.path.join(root, name))
    return total


def old_folders():
    """OLD_MODEL_FOLDERS 裡、還在 models\\ 的資料夾（完整路徑）"""
    from server.config import MODEL_FOLDERS, MODELS_DIR, OLD_MODEL_FOLDERS
    in_use = set(MODEL_FOLDERS.values())
    result = []
    for name in OLD_MODEL_FOLDERS:
        # 只收單純的資料夾名字（不能是路徑、不能跑到 models\ 外面），而且現在沒在用
        if name in ("", ".", "..") or os.path.basename(name) != name or name in in_use:
            continue
        path = os.path.join(MODELS_DIR, name)
        if os.path.isdir(path):
            result.append(path)
    return result


def main():
    folders = old_folders()
    if len(folders) == 0:
        return
    print()
    say("These AI model folders are no longer used by this app:",
        "這些 AI 模型，現在的程式用不到了：")
    for path in folders:
        print("  " + os.path.relpath(path, PROJECT) + "  (%d MB)" % (folder_size(path) // MB))
    if not ask_yes_no("Move them to the Recycle Bin?", "要丟到資源回收筒嗎？"):
        say("Kept. You will be asked again the next time you run update.bat.",
            "先留著。下次按 update.bat 會再問。")
        print()
        return
    for path in folders:
        name = os.path.relpath(path, PROJECT)
        if to_recycle_bin(path):
            say("Moved to the Recycle Bin: " + name, "已經丟到資源回收筒：" + name)
        else:
            say("Could not move it. You can delete it yourself: " + path,
                "丟不了，可以自己刪：" + path)
    print()


if __name__ == "__main__":
    main()
