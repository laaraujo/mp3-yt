"""Validation helpers for YouTube *video* URLs.

Used by the GUI to gate downstream form fields. Strict on purpose: Shorts
URLs are rejected explicitly so we can show a clear "not supported" message,
and channel/playlist/search URLs aren't accepted as videos.
"""

from __future__ import annotations

import re

# YouTube IDs are 11 chars from the base64-url alphabet.
_VIDEO_ID_RE = r"[A-Za-z0-9_-]{11}"

# YouTube hosts (incl. mobile and YouTube Music).
_YT_HOST = r"(?:www\.|m\.|music\.)?youtube\.com"

# Recognised video URL shapes:
#   https://(www.|m.|music.)youtube.com/watch?...&v=ID
#   https://(www.|m.)youtube.com/{live,embed,v}/ID
#   https://youtu.be/ID
# Trailing query/fragment after the id is allowed.
_VIDEO_URL_RE = re.compile(
    rf"^https?://(?:"
    rf"{_YT_HOST}/(?:watch\?(?:[^#]*&)?v=|live/|embed/|v/)({_VIDEO_ID_RE})"
    rf"|"
    rf"youtu\.be/({_VIDEO_ID_RE})"
    rf")(?:[?&#].*)?$",
    re.IGNORECASE,
)

# Matched separately so the caller can show a Shorts-specific error.
_SHORTS_URL_RE = re.compile(
    rf"^https?://(?:www\.|m\.)?youtube\.com/shorts/{_VIDEO_ID_RE}",
    re.IGNORECASE,
)


def is_shorts_url(text: str) -> bool:
    """Return True if ``text`` is a recognisably-Shorts URL."""
    return bool(_SHORTS_URL_RE.match(text.strip()))


def youtube_video_id(text: str) -> str | None:
    """Return the 11-char video id if ``text`` is a supported video URL, else None.

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
