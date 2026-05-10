"""Auto-detect a tracklist for a YouTube URL.

Tries chapters, then description, then top comments (in that order). If
none yield 2+ entries, returns an empty :class:`DetectionResult` so the
caller can still use the metadata-derived album/artist hints.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from slicer.core.tracklist import Track, find_tracklist_in_text
from slicer.core.ytdownload import (
    Chapter,
    VideoMetadata,
    fetch_metadata,
    fetch_top_comments,
)

StatusCallback = Callable[[str], None]
"""Receives short progress strings during detection."""


@dataclass(frozen=True)
class DetectionResult:
    # "chapters" | "description" | "comments" | None
    source: str | None
    tracks: list[Track]
    metadata: VideoMetadata
    # Best-guess "Artist - Album" parse from the video title; ``None`` if unknown.
    guessed_artist: str | None
    guessed_album: str | None


def chapters_to_tracks(chapters: list[Chapter]) -> list[Track]:
    """Convert yt-dlp chapters into :class:`Track` objects."""
    tracks: list[Track] = []
    for i, ch in enumerate(chapters, start=1):
        tracks.append(Track(index=i, start=ch.start_time, title=ch.title))
    return tracks


# Strip trailing brackets/parens (e.g. "[Full Album]") before splitting on dash.
_TRAILING_BRACKET_RE = re.compile(r"\s*[\[\(].*?[\]\)]\s*$")
_ARTIST_ALBUM_RE = re.compile(r"^\s*(?P<artist>[^-\u2013\u2014]+?)\s*[-\u2013\u2014]\s*(?P<album>.+?)\s*$")


def guess_artist_and_album(video_title: str) -> tuple[str | None, str | None]:
    """Try to split ``Artist - Album`` from a YouTube title."""
    cleaned = _TRAILING_BRACKET_RE.sub("", video_title).strip()
    m = _ARTIST_ALBUM_RE.match(cleaned)
    if not m:
        return None, None
    artist = m.group("artist").strip()
    album = m.group("album").strip()
    if not artist or not album:
        return None, None
    return artist, album


def detect_tracklist(
    url: str,
    *,
    on_status: StatusCallback | None = None,
) -> DetectionResult:
    """Fetch metadata for ``url`` and detect a tracklist if one is available.

    ``on_status`` receives a short user-facing string before each detection
    step so the GUI can show progress during the slow comments fetch.
    """
    def _say(msg: str) -> None:
        if on_status is not None:
            on_status(msg)

    metadata = fetch_metadata(url)
    artist, album = guess_artist_and_album(metadata.title)

    _say("Trying to get tracklist from chapters…")
    if metadata.chapters:
        tracks = chapters_to_tracks(metadata.chapters)
        if len(tracks) >= 2:
            _say(f"Found tracklist in video chapters ({len(tracks)} tracks).")
            return DetectionResult(
                source="chapters",
                tracks=tracks,
                metadata=metadata,
                guessed_artist=artist,
                guessed_album=album,
            )

    _say("Trying to get tracklist from description…")
    desc_tracks = find_tracklist_in_text(metadata.description)
    if desc_tracks:
        _say(
            f"Found tracklist in video description "
            f"({len(desc_tracks)} tracks)."
        )
        return DetectionResult(
            source="description",
            tracks=desc_tracks,
            metadata=metadata,
            guessed_artist=artist,
            guessed_album=album,
        )

    _say("Trying to get tracklist from top comments…")
    for comment in fetch_top_comments(url, limit=10):
        comment_tracks = find_tracklist_in_text(comment.text)
        if comment_tracks:
            who = comment.author or "an unknown user"
            _say(
                f"Found tracklist in top comment by {who} "
                f"({len(comment_tracks)} tracks)."
            )
            return DetectionResult(
                source="comments",
                tracks=comment_tracks,
                metadata=metadata,
                guessed_artist=artist,
                guessed_album=album,
            )

    return DetectionResult(
        source=None,
        tracks=[],
        metadata=metadata,
        guessed_artist=artist,
        guessed_album=album,
    )
