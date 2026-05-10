"""Auto-detect a tracklist for a YouTube URL.

Order of preference:

1. **Chapters** — YouTube's structured chapter list. When present, this is
   exactly what the uploader intended as the splits.
2. **Description scan** — many uploaders still write the tracklist directly
   in the description as ``mm:ss Title`` lines.

If neither produces 2+ entries we return :class:`DetectionResult` with
``source=None`` and an empty ``tracks`` list, so the caller can still fill
album/artist hints from the same metadata fetch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from slicer.core.tracklist import Track, find_tracklist_in_text
from slicer.core.ytdownload import Chapter, VideoMetadata, fetch_metadata


@dataclass(frozen=True)
class DetectionResult:
    source: str | None     # "chapters" | "description" | None
    tracks: list[Track]
    metadata: VideoMetadata
    # Optional best-guess artist/album parsed from the video title
    # ("Artist - Album" style). May be ``None`` when we can't tell.
    guessed_artist: str | None
    guessed_album: str | None


def chapters_to_tracks(chapters: list[Chapter]) -> list[Track]:
    """Convert yt-dlp chapters into our internal :class:`Track` list."""
    tracks: list[Track] = []
    for i, ch in enumerate(chapters, start=1):
        tracks.append(Track(index=i, start=ch.start_time, title=ch.title))
    return tracks


# "<Artist> - <Album>" or "<Artist> – <Album>" or "<Artist> — <Album>".
# Anything in trailing brackets/parens (e.g. "[Full Album]", "(Remastered)")
# is stripped first so it doesn't end up in the album name.
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


def detect_tracklist(url: str) -> DetectionResult:
    """Fetch metadata for ``url`` and return whatever tracklist we can detect."""
    metadata = fetch_metadata(url)
    artist, album = guess_artist_and_album(metadata.title)

    if metadata.chapters:
        tracks = chapters_to_tracks(metadata.chapters)
        if len(tracks) >= 2:
            return DetectionResult(
                source="chapters",
                tracks=tracks,
                metadata=metadata,
                guessed_artist=artist,
                guessed_album=album,
            )

    desc_tracks = find_tracklist_in_text(metadata.description)
    if desc_tracks:
        return DetectionResult(
            source="description",
            tracks=desc_tracks,
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
