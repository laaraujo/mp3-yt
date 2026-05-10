"""Write ID3v2 tags onto cut MP3 files using mutagen."""

from __future__ import annotations

from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3


def tag_track(
    path: Path,
    *,
    title: str,
    artist: str,
    album: str,
    track_number: int,
    track_total: int,
) -> None:
    """Set basic tags on an MP3 file, creating an ID3 header if missing."""
    try:
        audio = EasyID3(path)
    except ID3NoHeaderError:
        # File has no ID3 header yet; add one and try again.
        mp3 = MP3(path)
        mp3.add_tags()
        mp3.save()
        audio = EasyID3(path)

    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album
    audio["albumartist"] = artist
    audio["tracknumber"] = f"{track_number}/{track_total}"
    audio.save()
