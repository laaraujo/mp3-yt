"""Parse pasted tracklist text into structured ``Track`` objects.

Accepted line shapes (whitespace-tolerant)::

    0:00 Intro
    03:01 Sunrise
    1:23:45 A Long Bonus Track
    1. 0:00 Intro
    01) 0:00 Intro
    1 - 0:00 Intro
    [00:00] Intro
    0:00 - Intro

Blank lines and comment lines starting with ``#`` are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise


# Optional leading "track number" prefix: "1." / "01)" / "1 -" / "01 ".
# Followed by a timestamp and the title (which may itself begin with - or :).
_LINE_RE = re.compile(
    r"""
    ^\s*
    (?:\d{1,3}\s*[.\)\]]\s+|\d{1,3}\s+-\s+)?    # optional track-number prefix
    \[?                                          # optional [ around timestamp
    (?P<ts>\d{1,2}(?::\d{1,2}){1,2})             # the timestamp (M:SS or H:MM:SS)
    \]?                                          # optional ]
    \s*[-\u2013\u2014:]?\s*                      # optional separator (-, en/em dash, :)
    (?P<title>\S.*?)                             # the title
    \s*$
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Track:
    """A parsed tracklist entry."""

    index: int          # 1-based position in the source tracklist
    start: float        # start time in seconds
    title: str          # cleaned-up song title


class TracklistError(ValueError):
    """Raised when the tracklist text cannot be parsed into valid tracks."""


def format_timestamp(seconds: float) -> str:
    """Format seconds as ``M:SS`` or ``H:MM:SS`` (the canonical paste format)."""
    s = max(0, round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_tracks(tracks: list[Track]) -> str:
    """Render a list of tracks as a tracklist string editable in the UI."""
    return "\n".join(f"{format_timestamp(t.start)} {t.title}" for t in tracks)


def find_tracklist_in_text(text: str) -> list[Track]:
    """Lenient scanner: pull the longest strictly-increasing tracklist out of
    arbitrary text such as a YouTube description or a pinned comment.

    Unlike :func:`parse_tracklist`, this never raises: it just returns ``[]``
    when fewer than 2 viable lines are found. Non-matching lines (links,
    sponsor blurbs, hashtags) are simply skipped.
    """
    candidates: list[tuple[float, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _LINE_RE.match(stripped)
        if not m:
            continue
        try:
            start = _parse_timestamp(m.group("ts"))
        except TracklistError:
            continue
        title = _clean_title(m.group("title"))
        if title:
            candidates.append((start, title))

    if len(candidates) < 2:
        return []

    # Find the longest contiguous run of strictly increasing timestamps.
    best_lo, best_hi = 0, 1
    cur_lo = 0
    for i in range(1, len(candidates)):
        if candidates[i][0] > candidates[i - 1][0]:
            if i + 1 - cur_lo > best_hi - best_lo:
                best_lo, best_hi = cur_lo, i + 1
        else:
            cur_lo = i

    if best_hi - best_lo < 2:
        return []

    return [
        Track(index=j + 1, start=start, title=title)
        for j, (start, title) in enumerate(candidates[best_lo:best_hi])
    ]


def _parse_timestamp(ts: str) -> float:
    """Convert ``M:SS``, ``MM:SS`` or ``H:MM:SS`` into seconds (float)."""
    parts = ts.split(":")
    if not 2 <= len(parts) <= 3:
        raise TracklistError(f"Bad timestamp: {ts!r}")
    try:
        nums = [int(p) for p in parts]
    except ValueError as exc:
        raise TracklistError(f"Bad timestamp: {ts!r}") from exc
    if any(n < 0 for n in nums):
        raise TracklistError(f"Negative component in timestamp: {ts!r}")
    if len(nums) == 2:
        m, s = nums
        h = 0
        # In MM:SS form we allow large minutes (some tracklists write "90:00").
        if s >= 60:
            raise TracklistError(f"Seconds must be <60 in: {ts!r}")
    else:
        h, m, s = nums
        if s >= 60 or m >= 60:
            raise TracklistError(f"Minutes/seconds must be <60 in: {ts!r}")
    return h * 3600 + m * 60 + s


def parse_tracklist(text: str) -> list[Track]:
    """Parse a multi-line tracklist string into a list of :class:`Track`.

    Raises :class:`TracklistError` if no valid tracks were found, if any line
    can't be parsed, or if timestamps are not strictly increasing.
    """
    tracks: list[Track] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            raise TracklistError(
                f"Line {lineno}: could not parse {raw!r}. "
                f"Expected something like '0:00 Title'."
            )
        start = _parse_timestamp(m.group("ts"))
        title = _clean_title(m.group("title"))
        if not title:
            raise TracklistError(f"Line {lineno}: missing title in {raw!r}.")
        tracks.append(Track(index=len(tracks) + 1, start=start, title=title))

    if not tracks:
        raise TracklistError("Tracklist is empty.")

    # Strictly increasing timestamps; allowing equal would produce zero-length
    # tracks which is almost certainly a typo.
    for prev, cur in pairwise(tracks):
        if cur.start <= prev.start:
            raise TracklistError(
                f"Timestamps must be strictly increasing: track {cur.index} "
                f"({cur.title!r} @ {cur.start:.0f}s) is not after track "
                f"{prev.index} ({prev.title!r} @ {prev.start:.0f}s)."
            )

    return tracks


# --- helpers --------------------------------------------------------------


_TITLE_TRIM_RE = re.compile(r"^[\s\-\u2013\u2014:]+|[\s\-\u2013\u2014:]+$")


def _clean_title(title: str) -> str:
    """Normalize whitespace and strip leading/trailing dashes/colons."""
    cleaned = _TITLE_TRIM_RE.sub("", title)
    return re.sub(r"\s+", " ", cleaned).strip()
