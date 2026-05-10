@echo off
REM Launch mp3-yt-cutter using whichever `python` is on PATH.
REM
REM Assumes the project virtualenv is already active (so `python` resolves
REM to the venv interpreter with PySide6/yt-dlp/mutagen installed). See the
REM "Setup" section of the README for one-time environment setup.

setlocal
cd /d "%~dp0\.."
python -m mp3yt %*
