#!/usr/bin/env bash
# Build a self-contained macOS .app of yt2mp3slicer using PyInstaller.
#
# Outputs:
#   dist/yt2mp3slicer/yt2mp3slicer           the raw launcher (folder mode)
#   dist/yt2mp3slicer.app                     the macOS .app bundle
#   dist/yt2mp3slicer-macos-<arch>.zip        shareable zip of the .app
#
# The .app is **unsigned and unnotarized**. On first launch users will need
# to right-click -> Open to bypass Gatekeeper, or run:
#   xattr -d com.apple.quarantine dist/yt2mp3slicer.app
#
# ffmpeg / ffprobe are sourced from Homebrew. PyInstaller follows their
# dylib dependencies and bundles the relevant Homebrew dylibs into the
# .app's Frameworks folder, so the resulting bundle is portable.
#
# Usage:
#   ./scripts/build_macos.sh           # incremental
#   ./scripts/build_macos.sh --clean   # rebuild from scratch

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
  rm -rf dist build/build build/ffmpeg-bin .venv-build
fi

# 1. Sanity checks -------------------------------------------------------
if [[ "$(uname)" != "Darwin" ]]; then
  echo "build_macos.sh must be run on macOS." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required (https://brew.sh). Install brew, then re-run." >&2
  exit 1
fi

# 2. Build venv ----------------------------------------------------------
VENV=".venv-build"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating build virtualenv in $VENV ..."
  python3 -m venv "$VENV"
fi

"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r requirements.txt
"$PY" -m pip install pyinstaller

# 3. Pull ffmpeg/ffprobe from Homebrew ----------------------------------
FFMPEG_DIR="build/ffmpeg-bin"
if [[ ! -x "$FFMPEG_DIR/ffmpeg" || ! -x "$FFMPEG_DIR/ffprobe" ]]; then
  echo "Installing ffmpeg via Homebrew..."
  if ! brew list --formula | grep -qx ffmpeg; then
    brew install ffmpeg
  fi

  BREW_PREFIX="$(brew --prefix)"
  if [[ ! -x "$BREW_PREFIX/bin/ffmpeg" || ! -x "$BREW_PREFIX/bin/ffprobe" ]]; then
    echo "Could not find ffmpeg/ffprobe under $BREW_PREFIX/bin." >&2
    exit 1
  fi

  mkdir -p "$FFMPEG_DIR"
  cp "$BREW_PREFIX/bin/ffmpeg"  "$FFMPEG_DIR/"
  cp "$BREW_PREFIX/bin/ffprobe" "$FFMPEG_DIR/"
  chmod +x "$FFMPEG_DIR/ffmpeg" "$FFMPEG_DIR/ffprobe"
else
  echo "Reusing existing $FFMPEG_DIR"
fi

# 4. PyInstaller ---------------------------------------------------------
echo "Running PyInstaller..."
"$PY" -m PyInstaller --noconfirm --clean \
  --workpath build/build \
  --distpath dist \
  build/yt2mp3slicer.spec

# 5. Verify and zip the .app ---------------------------------------------
APP="dist/yt2mp3slicer.app"
if [[ ! -d "$APP" ]]; then
  echo "Build did not produce $APP" >&2
  exit 1
fi

ARCH="$(uname -m)"
ZIP="dist/yt2mp3slicer-macos-${ARCH}.zip"

# Use ditto so resource forks and symlinks (Frameworks/) are preserved.
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

echo
echo "=== Build complete ==="
echo "  .app:  $APP"
echo "  Zip:   $ZIP"
echo
echo "Run it: open '$APP'"
echo "First-launch tip: right-click the .app -> Open (Gatekeeper)"
