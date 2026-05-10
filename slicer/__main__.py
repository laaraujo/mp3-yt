"""Entry point: ``python -m slicer``."""

from __future__ import annotations

import sys

from slicer.runtime import configure_tls_ca_bundle


def main() -> int:
    configure_tls_ca_bundle()

    # Lazy import so a yt-dlp/Qt import error doesn't block --help-style flags.
    from slicer.ui.main_window import run_app

    return run_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
