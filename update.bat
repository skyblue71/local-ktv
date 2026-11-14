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

rem 更新和整理（tools\update.py）：到 GitHub 看有沒有新版，有的話問你要不要更新；
rem 再整理 .venv 裡的套件、models 裡的 AI 模型（要刪、要下載都會先問或說明）
rem 只有這一個檔案也可以用：缺的更新工具會先從 GitHub 下載，其他檔案再由它補齊
rem 畫面上的訊息每一句都有英文和中文。
rem 注意：if ( ... ) 括號裡的 echo 不能出現半形的括號，會被當成括號的結尾

rem 更新工具放在 GitHub 的哪裡（只有 tools\update.py 不見的時候才會用到）
set "TOOL_URL=https://raw.githubusercontent.com/skyblue71/local-ktv/main/tools/update.py"

rem 讓中文訊息正常顯示
set PYTHONIOENCODING=utf-8

echo ==========================================
echo   Local KTV: update and tidy up
echo   本機KTV：更新和整理
echo ==========================================
echo Please close Local KTV first (close the start.bat window).
echo 請先關掉本機KTV（關閉 start.bat 的視窗）。
echo.
echo 1. Program files: compared with the latest version on the official GitHub page. Nothing is changed until you press Y.
echo 2. Packages in .venv: missing ones can be installed, unused ones are removed.
echo 3. AI models in models: missing ones can be downloaded, unused ones removed. You are asked first.
echo 1. 程式：跟 GitHub 官方頁面上的最新版比一比。你按 Y 之前，什麼都不會改。
echo 2. 套件（.venv 裡的）：少了的可以裝、用不到的清掉。
echo 3. AI 模型（models 裡的）：少了的可以下載、用不到的可以清掉，都會先問你。
echo.

rem 用哪個 Python：裝好的虛擬環境優先；還沒安裝就用電腦裡的 Python（更新工具只用 Python 內建的功能）
set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=".venv\Scripts\python.exe""
if not defined PYTHON_CMD (
  py -3 -c "" >nul 2>nul && set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
  python -c "" >nul 2>nul && set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo Python was not found. Please install Python from https://www.python.org and run update.bat again.
  echo 找不到 Python。請先安裝 Python，再執行一次 update.bat
  pause
  exit /b
)

rem 只有這個檔案、還沒有更新工具：先下載更新工具
if exist "tools\update.py" goto run_update
echo The update tool is missing. Downloading it from: %TOOL_URL%
echo 還沒有更新工具，先下載，來源：%TOOL_URL%
if not exist "tools" mkdir "tools"
curl -f -L -s -o "tools\update.py" "%TOOL_URL%"
if errorlevel 1 (
  if exist "tools\update.py" del "tools\update.py"
  echo Could not download the update tool. Check your connection and try again.
  echo 下載不了更新工具，請確認網路後再試一次。
  pause
  exit /b
)
echo.

:run_update
rem 更新可能會換掉這個檔案自己，所以後面要做的事全部寫在同一行（這一行讀進來之後就不會再讀檔案）
%PYTHON_CMD% tools\update.py & echo. & pause & exit /b
