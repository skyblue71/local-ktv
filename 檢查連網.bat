@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 找不到虛擬環境 .venv，請先執行 setup.bat
  pause
  exit /b
)

rem 讓中文訊息正常顯示
set PYTHONIOENCODING=utf-8

echo ==========================================
echo   檢查程式會不會連到外面的網路
echo   會擋住所有對外連線，只允許連自己這台電腦
echo   不會動到你的歌曲，也不會發出聲音
echo   大約需要 30 秒～1 分鐘
echo ==========================================
echo.
echo ------ 測試一：假裝模型被刪掉 ------
".venv\Scripts\python.exe" tools\check_missing_model.py
echo.
echo ------ 測試二：整個程式跑一遍 ------
".venv\Scripts\python.exe" tools\check_network.py
echo.
echo 測試結束，看上面兩個【通過】就是正常。
pause
