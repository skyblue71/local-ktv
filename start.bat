@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 第一次使用（例如換新電腦）：還沒安裝的話，先自動安裝
if not exist ".venv\setup_done.txt" (
  echo 第一次使用，要先安裝環境。
  call "%~dp0setup.bat"
)
if not exist ".venv\setup_done.txt" (
  echo 還沒安裝完成，請先執行 setup.bat
  pause
  exit /b
)

rem 讓中文訊息正常顯示
set PYTHONIOENCODING=utf-8
rem 去人聲模型已經在安裝時下載好，程式設定成不連網（開關在 server\config.py 的 ALLOW_MODEL_DOWNLOAD）

echo ==========================================
echo   本機KTV 啟動中…
echo   瀏覽器會自動開啟 http://127.0.0.1:8000
echo   要關掉的話，關閉這個視窗就好。
echo ==========================================

rem 等 3 秒（讓伺服器先準備好）再開瀏覽器
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"

".venv\Scripts\python.exe" -m uvicorn server.main:app --host 127.0.0.1 --port 8000
pause
