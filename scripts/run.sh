#!/usr/bin/env bash
# Launch mp3-yt-cutter using whichever `python` is on PATH.
#
# Assumes the project virtualenv is already active (so `python` resolves to
# the venv interpreter with PySide6/yt-dlp/mutagen installed). See the
# "Setup" section of the README for one-time environment setup.

set -euo pipefail
cd "$(dirname "$0")/.."
exec python -m mp3yt "$@"
