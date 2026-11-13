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

rem 測過可以用的 Python 版本（有好幾個就用空白隔開，排前面的優先用）
rem 電腦裡沒有這些版本、但有別的夠新的 Python 時，會先用那個試試看，並提醒版本不一樣
set "TESTED_PYTHON=3.12"

rem 最低要的 Python 版本：requirements.txt 裡的套件有幾個比這版舊就裝不起來
rem （numpy、scipy）。換套件版本的時候，這裡要跟著看一下
set "MIN_PYTHON=3.12"

echo ==========================================
echo   Local KTV: setup
echo   本機KTV：安裝環境
echo ==========================================
echo This will:
echo   1. Create a virtual environment .venv (your system Python is not changed)
echo   2. Install the packages with pip
echo   3. Download two AI models once (after that the app downloads nothing)
echo 這個程式會：
echo   1. 建立虛擬環境 .venv（不會動到系統的 Python）
echo   2. 用 pip 下載並安裝需要的套件
echo   3. 下載去人聲模型、認音節模型各一次（之後程式就不再連網下載）
echo.
echo Download sources (all official) / 下載來源（都是官方網站）：
echo   PyTorch: https://download.pytorch.org/whl/cu128
echo   Other packages / 其他套件: https://pypi.org  (requirements.txt, requirements-nodeps.txt)
echo   Vocal separation model / 去人聲模型 Mel-Band RoFormer, 913 MB: https://huggingface.co/KimberleyJSN/melbandroformer
echo   Syllable model / 認音節模型 MMS, 1.26 GB: https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt
echo.
echo Needs Python %MIN_PYTHON% or newer (https://www.python.org). Tested with: %TESTED_PYTHON%. If this PC already has one, it is used first.
echo 需要 Python %MIN_PYTHON% 以上，測過的版本：%TESTED_PYTHON%。電腦裡已經有的話會先用它。
echo Node.js 22 or newer (https://nodejs.org) is recommended for better video quality from YouTube. It works without it too.
echo 建議也安裝 Node.js 22 以上：從 YouTube 加歌能拿到比較好的畫質，沒有也能用。
echo About 5.3 GB will be downloaded. Make sure your connection is stable.
echo 大約要下載 5.3GB，請確認網路穩定。
echo.

rem 已經建過虛擬環境、而且它的 Python 夠新：直接用，不用再找 Python
rem 它的 Python 太舊：等一下找到夠新的 Python 再重建
set "REBUILD_VENV=no"
if not exist ".venv\Scripts\python.exe" goto find_python
".venv\Scripts\python.exe" tools\check_python.py %MIN_PYTHON%
if not errorlevel 1 goto ready
set "REBUILD_VENV=yes"

:find_python
rem 找電腦裡的 Python：先找測過的版本，沒有再找別的
set "PYTHON_CMD="
set "OLD_VERSION="
set "PYTHON_TESTED=yes"
for %%v in (%TESTED_PYTHON%) do call :try_python py -%%v
if not defined PYTHON_CMD (
  set "PYTHON_TESTED=no"
  call :try_python py -3
  call :try_python python
)
if defined PYTHON_CMD goto python_found

if defined OLD_VERSION (
  echo The Python on this PC is %OLD_VERSION%. That is too old: this app needs Python %MIN_PYTHON% or newer.
  echo Please install Python %TESTED_PYTHON% from https://www.python.org and run setup.bat again. You can keep your old Python.
  echo 這台電腦的 Python 是 %OLD_VERSION%，太舊了：這個程式要 Python %MIN_PYTHON% 以上。
  echo 請安裝 Python %TESTED_PYTHON%，再執行一次 setup.bat。原本的 Python 不用移除。
) else (
  echo Python was not found. Please install Python %TESTED_PYTHON% from https://www.python.org and run setup.bat again.
  echo 找不到 Python。請先安裝 Python %TESTED_PYTHON%，再執行一次 setup.bat
)
pause
exit /b 1

:python_found
set "PYTHON_VERSION="
for /f "delims=" %%i in ('%PYTHON_CMD% -c "import platform; print(platform.python_version())"') do set "PYTHON_VERSION=%%i"
echo Using the Python on this PC: %PYTHON_VERSION%
echo 會用電腦裡的 Python %PYTHON_VERSION%
if "%PYTHON_TESTED%"=="no" (
  echo.
  echo WARNING: this app was tested with Python %TESTED_PYTHON%. Your version is different, so there may be problems.
  echo It will be tried anyway. If setup fails, install a tested version and run setup.bat again.
  echo 警告：這個程式測過的 Python 版本是 %TESTED_PYTHON%，你的版本不一樣，可能會有問題。
  echo 會先用它試試看；裝不起來的話，請安裝測過的版本再執行一次。
)
if "%REBUILD_VENV%"=="yes" (
  echo.
  echo The .venv folder from before was made with a Python that is too old. It will be made again.
  echo 之前的 .venv 是用太舊的 Python 建的，會重新建一個。
)
echo.

:ready
echo Press any key to start. Close this window if you do not want to install.
echo 按任意鍵開始安裝，不想安裝就直接關掉這個視窗。
pause >nul

if "%REBUILD_VENV%"=="yes" (
  %PYTHON_CMD% -m venv --clear .venv
  if errorlevel 1 goto failed
)
if not exist ".venv\Scripts\python.exe" (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install --no-cache-dir --upgrade pip
if errorlevel 1 goto failed
rem --no-cache-dir：pip 不要在資料夾外面（使用者資料夾的 AppData）另外存一份下載的檔案
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements-torch.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 goto failed
rem 這份只裝套件本身、不裝它要的其他套件（原因寫在檔案裡）
".venv\Scripts\python.exe" -m pip install --no-cache-dir --no-deps -r requirements-nodeps.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\download_model.py
if errorlevel 1 goto failed

rem 最後確認程式真的載得起來（Python 版本不合、或檔案被 Windows 擋住，這裡會先發現）
".venv\Scripts\python.exe" -c "import server.main"
if errorlevel 1 goto cannot_run

rem 做一個記號：安裝完成了（start.bat 看到這個檔案才會直接啟動）
echo 安裝完成 > ".venv\setup_done.txt"

echo.
echo Setup finished. Scanning the .venv folder with Windows Defender is recommended.
echo Double-click start.bat to start singing.
echo 安裝完成！建議用 Windows Defender 掃描一下 .venv 資料夾。
echo 之後雙擊 start.bat 就可以開始唱歌了。
pause
exit /b 0

:failed
echo.
echo Setup failed. See the error above. If it is a network problem, check your connection, then run setup.bat again.
echo 安裝失敗：請看上面的錯誤訊息。如果是網路的問題，確認網路後再執行一次 setup.bat
pause
exit /b 1

:cannot_run
echo.
echo The packages were installed, but the app cannot load (see the error above).
echo This Python version may not work, or Windows may have blocked a file.
echo You can try: delete the .venv folder, install Python %TESTED_PYTHON%, then run setup.bat again.
echo 套件裝好了，但是程式載不起來（錯誤訊息在上面）。
echo 可能是這個版本的 Python 不合，或是有檔案被 Windows 擋住。
echo 可以試試：刪掉 .venv 資料夾，安裝 Python %TESTED_PYTHON% 之後再執行一次 setup.bat
pause
exit /b 1

rem 試一個 Python 指令（用法：call :try_python py -3.12）
rem   能跑而且夠新：記在 PYTHON_CMD
rem   能跑但是太舊：把它的版本記在 OLD_VERSION
:try_python
if defined PYTHON_CMD goto :eof
%* -c "" >nul 2>nul
if errorlevel 1 goto :eof
%* tools\check_python.py %MIN_PYTHON%
if errorlevel 1 goto remember_old
set "PYTHON_CMD=%*"
goto :eof

:remember_old
for /f "delims=" %%i in ('%* -c "import platform; print(platform.python_version())"') do set "OLD_VERSION=%%i"
goto :eof
