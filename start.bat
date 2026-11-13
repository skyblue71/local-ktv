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

rem 畫面上的訊息每一句都有英文和中文。
rem 注意：if ( ... ) 括號裡的 echo 不能出現半形的括號，會被當成括號的結尾

rem 啟動時要不要檢查更新：yes = 要（問一下 GitHub 最新版的編號，有新版才問你要不要更新），no = 不要（啟動時完全不連網）
set "CHECK_UPDATE=yes"

rem 第一次使用（例如換新電腦）：還沒安裝的話，先自動安裝
if not exist ".venv\setup_done.txt" (
  echo First run: the environment needs to be installed first.
  echo 第一次使用，要先安裝環境。
  call "%~dp0setup.bat"
)
if not exist ".venv\setup_done.txt" (
  echo Setup is not finished. Please run setup.bat first.
  echo 還沒安裝完成，請先執行 setup.bat
  pause
  exit /b
)

rem 讓中文訊息正常顯示
set PYTHONIOENCODING=utf-8

rem 檢查更新（tools\update.py）。更新可能會換掉這個檔案自己，所以：
rem   檢查完不接著往下跑，而是重新執行一次 start.bat（帶 noupdate = 這次不用再檢查），讀到的就是新的檔案
rem   這些都寫在同一行（這一行讀進來之後就不會再讀檔案）
rem   結束代碼 20 = 更新完你選了「不要開啟」
if "%~1"=="noupdate" goto launch
if /i not "%CHECK_UPDATE%"=="yes" goto launch
if not exist "tools\update.py" goto launch
".venv\Scripts\python.exe" tools\update.py --start & if errorlevel 20 (exit /b) else ("%~f0" noupdate)

:launch
rem 去人聲模型已經在安裝時下載好，程式設定成不連網（開關在 server\config.py 的 ALLOW_MODEL_DOWNLOAD）

echo ==========================================
echo   Local KTV is starting...
echo   Your browser will open http://127.0.0.1:8000
echo   To quit, close this window.
echo.
echo   本機KTV 啟動中…
echo   瀏覽器會自動開啟 http://127.0.0.1:8000
echo   要關掉的話，關閉這個視窗就好。
echo ==========================================

rem 等 3 秒（讓伺服器先準備好）再開瀏覽器
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"

".venv\Scripts\python.exe" -m uvicorn server.main:app --host 127.0.0.1 --port 8000
pause
