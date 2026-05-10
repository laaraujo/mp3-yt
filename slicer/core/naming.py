"""Filename helpers shared by the UI and the worker."""

from __future__ import annotations

import re

# Characters that are illegal on Windows file systems (also problematic on
# macOS / Linux in some shells). We replace each with an underscore.
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Trailing dots and spaces in a filename make Windows refuse to open the file,
# so we strip *all* of them from the end in one pass — this catches alternating
# patterns like ``"Track . ."`` that a single ``.strip().strip(".")`` chain
# would leave a trailing space behind in.
_TRAILING_DOTS_SPACES_RE = re.compile(r"[. ]+$")


def safe_filename(name: str, *, max_len: int = 180) -> str:
    """Return a version of ``name`` that's safe to use as a filename component.

    * Replaces illegal characters with ``_``.
    * Collapses whitespace.
    * Trims trailing dots/spaces (Windows hates those).
    * Truncates to ``max_len`` to leave room for the extension and prefix.
    """
    cleaned = _ILLEGAL_RE.sub("_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _TRAILING_DOTS_SPACES_RE.sub("", cleaned)
    if not cleaned:
        cleaned = "track"
    if len(cleaned) > max_len:
        cleaned = _TRAILING_DOTS_SPACES_RE.sub("", cleaned[:max_len])
    return cleaned


def track_filename(index: int, total: int, title: str) -> str:
    """Build the ``NN - Title.mp3`` filename used for output tracks."""
    width = max(2, len(str(total)))
    return f"{index:0{width}d} - {safe_filename(title)}.mp3"
