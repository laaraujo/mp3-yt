#!/usr/bin/env bash
# Build a self-contained Linux binary with PyInstaller.
#
# Output:
#   dist/yt2mp3slicer/yt2mp3slicer            launcher binary
#   dist/yt2mp3slicer-linux-<arch>.tar.gz     shareable archive
#
# Usage:
#   ./scripts/build_linux.sh           # incremental
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

echo "Syncing build environment with uv..."
# --locked: fail if uv.lock drifted from pyproject.toml; release builds
# must never silently re-resolve.
uv sync --locked --group build

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
  # --no-same-owner: don't honor archive uid/gid when extracting as root.
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

echo "Running PyInstaller..."
uv run pyinstaller --noconfirm --clean \
  --workpath build/build \
  --distpath dist \
  build/yt2mp3slicer.spec

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
