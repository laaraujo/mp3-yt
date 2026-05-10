#!/usr/bin/env bash
# Launch yt2mp3slicer via uv (https://docs.astral.sh/uv/).
#
# `uv run` will create/refresh `.venv` from `uv.lock` if needed, so this
# works from a clean clone with no manual venv activation. The only
# prerequisite is having `uv` on PATH; see the README's "Develop" section
# for installation instructions.

set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH." >&2
  echo "Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

exec uv run python -m slicer "$@"
