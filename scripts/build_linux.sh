#!/usr/bin/env bash
# Build a self-contained Linux binary of yt2mp3slicer using PyInstaller.
#
# Uses uv (https://docs.astral.sh/uv/) to set up the build environment
# from `uv.lock` plus the `build` dependency group (PyInstaller).
# Downloads a static ffmpeg/ffprobe build from BtbN/FFmpeg-Builds (LGPL),
# runs PyInstaller against build/yt2mp3slicer.spec, and produces a
# distributable tarball.
#
# Output:
#   dist/yt2mp3slicer/yt2mp3slicer            the launcher binary
#   dist/yt2mp3slicer-linux-<arch>.tar.gz     shareable archive
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

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH." >&2
  echo "Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

if [[ "$CLEAN" -eq 1 ]]; then
  echo "Cleaning previous build artifacts..."
  rm -rf dist build/build build/ffmpeg-bin build/ffmpeg-extracted build/ffmpeg.tar.xz .venv
fi

# 1. Sync the project venv with runtime + build deps (PyInstaller). The
#    same `.venv` is reused for `uv run pytest` etc; the extra build group
#    just adds PyInstaller on top.
echo "Syncing build environment with uv..."
uv sync --group build

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
uv run pyinstaller --noconfirm --clean \
  --workpath build/build \
  --distpath dist \
  build/yt2mp3slicer.spec

# 4. Tarball -------------------------------------------------------------
DIST_DIR="dist/yt2mp3slicer"
ARCH="$(uname -m)"
TARBALL="dist/yt2mp3slicer-linux-${ARCH}.tar.gz"

if [[ ! -x "$DIST_DIR/yt2mp3slicer" ]]; then
  echo "Build did not produce $DIST_DIR/yt2mp3slicer" >&2
  exit 1
fi

rm -f "$TARBALL"
tar -C dist -czf "$TARBALL" yt2mp3slicer

echo
echo "=== Build complete ==="
echo "  Folder:  $DIST_DIR"
echo "  Tarball: $TARBALL"
echo
echo "Run it directly: $DIST_DIR/yt2mp3slicer"
