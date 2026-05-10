@echo off
REM Launch yt2mp3slicer via uv. Requires `uv` on PATH (see README "Develop").

setlocal
cd /d "%~dp0\.."

where uv >nul 2>nul
if errorlevel 1 (
    echo error: 'uv' not found on PATH. 1>&2
    echo Install it from https://docs.astral.sh/uv/getting-started/installation/ 1>&2
    exit /b 127
)

uv run python -m slicer %*
