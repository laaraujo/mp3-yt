"""Tests for tracklist auto-detection from yt-dlp metadata.

We avoid actually hitting YouTube; we drive the pure-logic helpers directly.
"""

from __future__ import annotations

from slicer.core.detect import (
    chapters_to_tracks,
    guess_artist_and_album,
)
from slicer.core.ytdownload import Chapter


def test_chapters_to_tracks_basic() -> None:
    chapters = [
        Chapter(start_time=0.0, end_time=181.0, title="Emerald Hill Zone"),
        Chapter(start_time=181.0, end_time=332.0, title="Spring Yard Zone"),
        Chapter(start_time=332.0, end_time=504.0, title="Green Hill Zone"),
    ]
    tracks = chapters_to_tracks(chapters)
    assert [t.index for t in tracks] == [1, 2, 3]
    assert [t.start for t in tracks] == [0.0, 181.0, 332.0]
    assert [t.title for t in tracks] == [
        "Emerald Hill Zone",
        "Spring Yard Zone",
        "Green Hill Zone",
    ]


def test_guess_artist_and_album_dash_form() -> None:
    artist, album = guess_artist_and_album("Masato Nakamura - Sonic 2 OST")
    assert artist == "Masato Nakamura"
    assert album == "Sonic 2 OST"


def test_guess_artist_and_album_strips_trailing_brackets() -> None:
    artist, album = guess_artist_and_album(
        "Masato Nakamura - Sonic 2 OST [Full Album] (Remastered)"
    )
    assert artist == "Masato Nakamura"
    assert album == "Sonic 2 OST"


def test_guess_artist_and_album_handles_em_dash() -> None:
    artist, album = guess_artist_and_album("Some Band \u2014 Some Album")
    assert artist == "Some Band"
    assert album == "Some Album"


def test_guess_artist_and_album_returns_none_when_no_dash() -> None:
    assert guess_artist_and_album("Just a video title") == (None, None)
