"""Entry point: ``python -m slicer``."""

from __future__ import annotations

import sys


def main() -> int:
    # Imported lazily so `--help` style flags or syntax errors elsewhere don't
    # pull in the whole Qt stack before we need it.
    from slicer.ui.main_window import run_app

    return run_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
