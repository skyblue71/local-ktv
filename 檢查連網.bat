@echo off
if "%KTV_UTF8%"=="1" goto utf8_ready
setlocal
set "KTV_UTF8=1"
chcp 65001 >nul
cmd /c ""%~f0" %*" & exit /b
:utf8_ready
rem 上面幾行只能有英文：命令視窗一開始不是 UTF-8（例如繁體中文 Windows 是 Big5）時，
rem 在同一個命令視窗程序裡切成 UTF-8，會把後面中文那幾行讀歪，把半句中文當成指令。
rem 所以先切成 UTF-8，再開一個新的命令視窗程序從頭跑這個檔案；新程序一開始就是 UTF-8，讀得正確
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
