#!/usr/bin/env bash
# Build a self-contained Linux binary of mp3-yt-cutter using PyInstaller.
#
# Sets up a build venv (.venv-build), installs runtime + build dependencies,
# downloads a static ffmpeg/ffprobe build from BtbN/FFmpeg-Builds (LGPL),
# runs PyInstaller against build/mp3-yt-cutter.spec, and produces a
# distributable tarball.
#
# Output:
#   dist/mp3-yt-cutter/mp3-yt-cutter           the launcher binary
#   dist/mp3-yt-cutter-linux-<arch>.tar.gz     shareable archive
#
# Usage:
#   ./scripts/build_linux.sh           # incremental (reuses ffmpeg + venv)
#   ./scripts/build_linux.sh --clean   # rebuild from scratch

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CLEAN=0
case "${1:-}" in
  -c|--clean) CLEAN=1 ;;
  "") ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac

if [[ "$CLEAN" -eq 1 ]]; then
  echo "Cleaning previous build artifacts..."
  rm -rf dist build/build build/ffmpeg-bin build/ffmpeg-extracted build/ffmpeg.tar.xz .venv-build
fi

# 1. Build venv ----------------------------------------------------------
VENV=".venv-build"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating build virtualenv in $VENV ..."
  python3 -m venv "$VENV"
fi

"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r requirements.txt
"$PY" -m pip install -e .
"$PY" -m pip install pyinstaller

# 2. Download static ffmpeg/ffprobe --------------------------------------
FFMPEG_DIR="build/ffmpeg-bin"
if [[ ! -x "$FFMPEG_DIR/ffmpeg" || ! -x "$FFMPEG_DIR/ffprobe" ]]; then
  echo "Downloading ffmpeg static build (BtbN, LGPL)..."
  mkdir -p "$FFMPEG_DIR"

  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64|amd64)
      URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-lgpl.tar.xz"
      ;;
    aarch64|arm64)
      URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-lgpl.tar.xz"
      ;;
    *)
      echo "Unsupported Linux architecture: $ARCH" >&2
      echo "Drop static ffmpeg + ffprobe binaries into $FFMPEG_DIR/ and re-run." >&2
      exit 1
      ;;
  esac

  TARFILE="build/ffmpeg.tar.xz"
  EXTRACT="build/ffmpeg-extracted"

  curl -L --fail --silent --show-error "$URL" -o "$TARFILE"

  rm -rf "$EXTRACT"
  mkdir -p "$EXTRACT"
  # --no-same-owner: don't try to honor the archive's uid/gid (relevant when
  # extracting as root inside a container/sandbox).
  tar --no-same-owner -xJf "$TARFILE" -C "$EXTRACT"

  BIN_DIR="$(find "$EXTRACT" -type d -name bin | head -n1)"
  if [[ -z "$BIN_DIR" ]]; then
    echo "Could not find a bin/ directory inside the ffmpeg archive." >&2
    exit 1
  fi
  cp "$BIN_DIR/ffmpeg" "$FFMPEG_DIR/"
  cp "$BIN_DIR/ffprobe" "$FFMPEG_DIR/"
  chmod +x "$FFMPEG_DIR"/ffmpeg "$FFMPEG_DIR"/ffprobe

  rm -f "$TARFILE"
  rm -rf "$EXTRACT"
else
  echo "Reusing existing $FFMPEG_DIR"
fi

# 3. PyInstaller ---------------------------------------------------------
echo "Running PyInstaller..."
"$PY" -m PyInstaller --noconfirm --clean \
  --workpath build/build \
  --distpath dist \
  build/mp3-yt-cutter.spec

# 4. Tarball -------------------------------------------------------------
DIST_DIR="dist/mp3-yt-cutter"
ARCH="$(uname -m)"
TARBALL="dist/mp3-yt-cutter-linux-${ARCH}.tar.gz"

if [[ ! -x "$DIST_DIR/mp3-yt-cutter" ]]; then
  echo "Build did not produce $DIST_DIR/mp3-yt-cutter" >&2
  exit 1
fi

rm -f "$TARBALL"
tar -C dist -czf "$TARBALL" mp3-yt-cutter

echo
echo "=== Build complete ==="
echo "  Folder:  $DIST_DIR"
echo "  Tarball: $TARBALL"
echo
echo "Run it directly: $DIST_DIR/mp3-yt-cutter"
