@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtualenv in .venv ...
  python -m venv .venv || goto :err
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul || goto :err
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
  ".venv\Scripts\python.exe" -m pip install -e . >nul || goto :err
)

".venv\Scripts\python.exe" -m mp3yt %*
goto :eof

:err
echo Failed to set up environment.
exit /b 1
