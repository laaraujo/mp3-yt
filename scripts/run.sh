#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "Creating virtualenv in .venv ..." >&2
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
  ./.venv/bin/pip install -e . >/dev/null
fi

exec ./.venv/bin/python -m mp3yt "$@"
