"""Validation helpers for YouTube *video* URLs.

Used by the GUI to enable/disable downstream form fields. Deliberately strict:

* Shorts URLs (``/shorts/<id>``) are rejected explicitly so we can surface a
  clear "Shorts aren't supported" message — they're meant for ≤60s clips and
  the slicing workflow targets full-length videos.
* Channel / playlist / search URLs are not recognised as videos either.

Anything that yields a real 11-character video id from ``watch?v=``,
``youtu.be/``, ``/live/``, ``/embed/`` or ``/v/`` is accepted.
"""

from __future__ import annotations

import re

# YouTube video IDs are an 11-character base64-url alphabet.
_VIDEO_ID_RE = r"[A-Za-z0-9_-]{11}"

# Hosts we treat as YouTube proper (incl. mobile and YouTube Music).
_YT_HOST = r"(?:www\.|m\.|music\.)?youtube\.com"

# Recognised YouTube *video* URL shapes:
#   https://(www.|m.|music.)youtube.com/watch?...&v=ID
#   https://(www.|m.)youtube.com/live/ID
#   https://(www.|m.)youtube.com/embed/ID
#   https://(www.|m.)youtube.com/v/ID
#   https://youtu.be/ID
# Trailing query / fragment after the id is allowed (e.g. ``?t=120``).
_VIDEO_URL_RE = re.compile(
    rf"^https?://(?:"
    rf"{_YT_HOST}/(?:watch\?(?:[^#]*&)?v=|live/|embed/|v/)({_VIDEO_ID_RE})"
    rf"|"
    rf"youtu\.be/({_VIDEO_ID_RE})"
    rf")(?:[?&#].*)?$",
    re.IGNORECASE,
)

# Shorts URL — matched separately so the caller can show a specific error.
_SHORTS_URL_RE = re.compile(
    rf"^https?://(?:www\.|m\.)?youtube\.com/shorts/{_VIDEO_ID_RE}",
    re.IGNORECASE,
)


def is_shorts_url(text: str) -> bool:
    """Return True if ``text`` is a recognisably-Shorts URL."""
    return bool(_SHORTS_URL_RE.match(text.strip()))


def youtube_video_id(text: str) -> str | None:
    """Return the 11-char video id if ``text`` is a supported video URL.

    Returns ``None`` for empty input, Shorts URLs, channel/playlist URLs and
    anything else we don't want to feed into the slicer.
    """
    text = text.strip()
    if not text or is_shorts_url(text):
        return None
    m = _VIDEO_URL_RE.match(text)
    if not m:
        return None
    return m.group(1) or m.group(2)
