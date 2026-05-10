"""Filename helpers shared by the UI and the worker."""

from __future__ import annotations

import re

# Illegal on Windows (and shell-hostile elsewhere); replaced with `_`.
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Trailing dots/spaces make Windows refuse to open the file. Strip *all* in
# one pass to handle alternating patterns like `"Track . ."`.
_TRAILING_DOTS_SPACES_RE = re.compile(r"[. ]+$")


def safe_filename(name: str, *, max_len: int = 180) -> str:
    """Return a filename-safe version of ``name``.

    Replaces illegal characters with ``_``, collapses whitespace, strips
    trailing dots/spaces, and truncates to ``max_len``.
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
