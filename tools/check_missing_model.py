"""
測試：假裝去人聲模型被刪掉，程式會不會偷偷跑去別的地方下載？

做法：
  1. 擋住所有對外網路
  2. 叫程式去一個「空的暫存資料夾」找模型（真正的模型完全不會被動到）
  3. 載入模型 → 應該要顯示「找不到模型」的中文錯誤，而且連到外面 0 次

執行方法：雙擊專案資料夾裡的「檢查連網.bat」
"""
import os
import shutil
import sys
import tempfile

# 讓這個程式找得到 tools 和 server 資料夾
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.dirname(TOOLS_DIR))

import network_guard  # noqa: E402

# 第 1 步：擋住網路（要在載入其他程式之前）
network_guard.start()

from server import config, separator  # noqa: E402

# 第 2 步：模型的位置（models\ 和舊版放在外面的位置）都改到空的暫存資料夾，假裝模型不見了（config.py 的 model_path）
empty_melband_folder = tempfile.mkdtemp(prefix="karaoke_test_melband_")
config.MODELS_DIR = empty_melband_folder
config.OLD_MODEL_DIRS = {name: empty_melband_folder for name in config.OLD_MODEL_DIRS}

print()
print("【測試】假裝模型被刪掉，載入模型…")
got_chinese_error = False
try:
    separator.load_model()
    print("結果：竟然載入成功（不應該發生）")
except Exception as error:
    message = str(error)
    print("結果：" + message[:80] + "…")
    if "找不到去人聲模型" in message:
        got_chinese_error = True

no_network = network_guard.print_report()

# 刪掉剛剛建立的空資料夾
shutil.rmtree(empty_melband_folder, ignore_errors=True)

print()
if got_chinese_error and no_network:
    print("【通過】模型不見時，程式不會偷偷下載，只會顯示中文說明。")
else:
    print("【沒通過】請看上面的訊息。")
