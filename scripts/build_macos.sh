#!/usr/bin/env bash
# Build a self-contained macOS .app with PyInstaller. ffmpeg/ffprobe come
# from Homebrew; PyInstaller follows their dylibs into the .app bundle.
#
# Outputs:
#   dist/yt2mp3slicer.app                     macOS .app bundle
#   dist/yt2mp3slicer-macos-<arch>.zip        shareable zip
#
# The .app is unsigned/unnotarized — first launch requires right-click → Open
# (or `xattr -d com.apple.quarantine dist/yt2mp3slicer.app`).
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

if [[ "$(uname)" != "Darwin" ]]; then
  echo "build_macos.sh must be run on macOS." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required (https://brew.sh). Install brew, then re-run." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH." >&2
  echo "Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

if [[ "$CLEAN" -eq 1 ]]; then
  echo "Cleaning previous build artifacts..."
  rm -rf dist build/build build/ffmpeg-bin .venv
fi

echo "Syncing build environment with uv..."
# --locked: fail if uv.lock drifted from pyproject.toml; release builds
# must never silently re-resolve.
uv sync --locked --group build

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

echo "Running PyInstaller..."
uv run pyinstaller --noconfirm --clean \
  --workpath build/build \
  --distpath dist \
  build/yt2mp3slicer.spec

APP="dist/yt2mp3slicer.app"
if [[ ! -d "$APP" ]]; then
  echo "Build did not produce $APP" >&2
  exit 1
fi

echo "Verifying bundled ffmpeg tools..."
lib_paths=(
  "$APP/Contents/MacOS"
  "$APP/Contents/MacOS/_internal"
  "$APP/Contents/Frameworks"
)
for lib_path in "${lib_paths[@]}"; do
  if [[ -d "$lib_path" ]]; then
    export DYLD_LIBRARY_PATH="$lib_path${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
  fi
done
for tool in ffmpeg ffprobe; do
  tool_path="$(find "$APP" -type f -name "$tool" -perm -111 | head -n1)"
  if [[ -z "$tool_path" ]]; then
    echo "Bundled $tool not found or not executable." >&2
    exit 1
  fi
  "$tool_path" -version >/dev/null
  if otool -L "$tool_path" | grep -E '/(usr/local|opt/homebrew)/' >/dev/null; then
    echo "Bundled $tool still links to Homebrew paths:" >&2
    otool -L "$tool_path" >&2
    exit 1
  fi
done

ARCH="$(uname -m)"
ZIP="dist/yt2mp3slicer-macos-${ARCH}.zip"

# `ditto` preserves resource forks and symlinks (Frameworks/) where `zip` can't.
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

echo
echo "=== Build complete ==="
echo "  .app:  $APP"
echo "  Zip:   $ZIP"
echo
echo "Run it: open '$APP'"
echo "First-launch tip: right-click the .app -> Open (Gatekeeper)"
