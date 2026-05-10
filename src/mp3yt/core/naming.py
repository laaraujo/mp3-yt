"""Filename helpers shared by the UI and the worker."""

from __future__ import annotations

import re

# Characters that are illegal on Windows file systems (also problematic on
# macOS / Linux in some shells). We replace each with an underscore.
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, *, max_len: int = 180) -> str:
    """Return a version of ``name`` that's safe to use as a filename component.

    * Replaces illegal characters with ``_``.
    * Collapses whitespace.
    * Trims trailing dots/spaces (Windows hates those).
    * Truncates to ``max_len`` to leave room for the extension and prefix.
    """
    cleaned = _ILLEGAL_RE.sub("_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    if not cleaned:
        cleaned = "track"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip().strip(".")
    return cleaned


def track_filename(index: int, total: int, title: str) -> str:
    """Build the ``NN - Title.mp3`` filename used for output tracks."""
    width = max(2, len(str(total)))
    return f"{index:0{width}d} - {safe_filename(title)}.mp3"
