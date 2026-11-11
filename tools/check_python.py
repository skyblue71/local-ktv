# -*- coding: utf-8 -*-
# 檢查「正在跑這個檔案的 Python」夠不夠新（setup.bat 用的）。
# 用法：python tools\check_python.py 3.12
# 夠新：結束代碼 0；太舊：結束代碼 1。
# 這個檔案會被很舊的 Python 執行，所以只用最基本的寫法。

import sys

# 最低要的版本，例如 "3.12" 拆成 3 和 12
parts = sys.argv[1].split(".")
need_major = int(parts[0])
need_minor = int(parts[1])

have_major = sys.version_info[0]
have_minor = sys.version_info[1]

new_enough = False
if have_major > need_major:
    new_enough = True
if have_major == need_major and have_minor >= need_minor:
    new_enough = True

if new_enough:
    sys.exit(0)
sys.exit(1)
