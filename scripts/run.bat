@echo off
REM Launch yt2mp3slicer via uv (https://docs.astral.sh/uv/).
REM
REM `uv run` creates/refreshes .venv from uv.lock on demand, so this
REM works from a clean clone with no manual venv activation. The only
REM prerequisite is having `uv` on PATH; see the README's "Develop"
REM section for installation instructions.

setlocal
cd /d "%~dp0\.."

where uv >nul 2>nul
if errorlevel 1 (
    echo error: 'uv' not found on PATH. 1>&2
    echo Install it from https://docs.astral.sh/uv/getting-started/installation/ 1>&2
    exit /b 127
)

uv run python -m slicer %*
