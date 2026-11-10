@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   本機KTV：安裝環境（換新電腦時用）
echo ==========================================
echo 這個程式會：
echo   1. 建立虛擬環境 .venv（不會動到系統的 Python）
echo   2. 用 pip 下載並安裝需要的套件
echo   3. 下載去人聲模型、認音節模型各一次（之後程式就不再連網下載）
echo.
echo 下載來源（都是官方網站）：
echo   PyTorch：https://download.pytorch.org/whl/cu128 （PyTorch 官方）
echo   其他套件：https://pypi.org （Python 官方套件庫），清單和版本在 requirements.txt
echo   去人聲模型 Mel-Band RoFormer（約 913MB）：https://huggingface.co/KimberleyJSN/melbandroformer （模型作者本人帳號）
echo   認音節模型 MMS（約 1.26GB）：https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt （Meta 官方）
echo.
echo 需要先安裝 Python 3.12（https://www.python.org）
echo 建議也安裝 Node.js 22 以上（https://nodejs.org）：從 YouTube 加歌能拿到比較好的畫質，沒有也能用。
echo 大約要下載 5.3GB，請確認網路穩定。
echo.
echo 按任意鍵開始安裝，不想安裝就直接關掉這個視窗。
pause >nul

if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\download_model.py
if errorlevel 1 goto failed

rem 做一個記號：安裝完成了（start.bat 看到這個檔案才會直接啟動）
echo 安裝完成 > ".venv\setup_done.txt"

echo.
echo 安裝完成！建議用 Windows Defender 掃描一下 .venv 資料夾。
echo 之後雙擊 start.bat 就可以開始唱歌了。
pause
exit /b 0

:failed
echo.
echo 安裝失敗：請看上面的錯誤訊息，確認網路後再執行一次 setup.bat
pause
exit /b 1
