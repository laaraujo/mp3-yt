"""Tests for tracklist auto-detection. Network helpers are monkeypatched."""

from __future__ import annotations

import slicer.core.detect as detect
from slicer.core.detect import (
    chapters_to_tracks,
    detect_tracklist,
    guess_artist_and_album,
)
from slicer.core.ytdownload import Chapter, Comment, VideoMetadata


def _make_metadata(
    *,
    title: str = "Some Mix - The Greatest Hits",
    uploader: str = "DJ Example",
    description: str = "",
    chapters: list[Chapter] | None = None,
    duration: float = 3600.0,
) -> VideoMetadata:
    return VideoMetadata(
        title=title,
        uploader=uploader,
        description=description,
        duration=duration,
        chapters=list(chapters or []),
    )


def _patch_fetchers(
    monkeypatch,
    *,
    metadata: VideoMetadata,
    comments: list[Comment] | None = None,
) -> None:
    """Replace the two network helpers with deterministic stand-ins."""
    monkeypatch.setattr(detect, "fetch_metadata", lambda url: metadata)
    monkeypatch.setattr(
        detect,
        "fetch_top_comments",
        lambda url, *, limit=10: list(comments or []),
    )


def test_chapters_to_tracks_basic() -> None:
    chapters = [
        Chapter(start_time=0.0, end_time=181.0, title="Intro"),
        Chapter(start_time=181.0, end_time=332.0, title="Sunrise"),
        Chapter(start_time=332.0, end_time=504.0, title="Departure"),
    ]
    tracks = chapters_to_tracks(chapters)
    assert [t.index for t in tracks] == [1, 2, 3]
    assert [t.start for t in tracks] == [0.0, 181.0, 332.0]
    assert [t.title for t in tracks] == [
        "Intro",
        "Sunrise",
        "Departure",
    ]


def test_guess_artist_and_album_dash_form() -> None:
    artist, album = guess_artist_and_album("Anna Rivers - Echoes of Tomorrow")
    assert artist == "Anna Rivers"
    assert album == "Echoes of Tomorrow"


def test_guess_artist_and_album_strips_trailing_brackets() -> None:
    artist, album = guess_artist_and_album(
        "Anna Rivers - Echoes of Tomorrow [Full Album] (Remastered)"
    )
    assert artist == "Anna Rivers"
    assert album == "Echoes of Tomorrow"


def test_guess_artist_and_album_handles_em_dash() -> None:
    artist, album = guess_artist_and_album("Some Band \u2014 Some Album")
    assert artist == "Some Band"
    assert album == "Some Album"


def test_guess_artist_and_album_returns_none_when_no_dash() -> None:
    assert guess_artist_and_album("Just a video title") == (None, None)


# ---- detect_tracklist orchestration ------------------------------------


def test_detect_tracklist_uses_chapters_when_present(monkeypatch) -> None:
    chapters = [
        Chapter(start_time=0.0,   end_time=181.0, title="Intro"),
        Chapter(start_time=181.0, end_time=332.0, title="Sunrise"),
    ]
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(chapters=chapters),
        comments=[Comment(text="anything", author="@nobody", like_count=0)],
    )

    result = detect_tracklist("http://fake")

    assert result.source == "chapters"
    assert [t.title for t in result.tracks] == ["Intro", "Sunrise"]
    # "Some Mix - The Greatest Hits" → ("Some Mix", "The Greatest Hits").
    assert result.guessed_artist == "Some Mix"
    assert result.guessed_album == "The Greatest Hits"


def test_detect_tracklist_falls_back_to_description(monkeypatch) -> None:
    description = (
        "Subscribe!\n"
        "0:00 Intro\n"
        "2:34 Pulse Train\n"
        "7:12 Crystal Drift\n"
        "Follow me!\n"
    )
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description=description),
        comments=[],
    )

    result = detect_tracklist("http://fake")

    assert result.source == "description"
    assert [t.title for t in result.tracks] == ["Intro", "Pulse Train", "Crystal Drift"]


def test_detect_tracklist_falls_back_to_top_comments(monkeypatch) -> None:
    # First comment is noise; second contains the tracklist.
    comments = [
        Comment(text="First!! banger as always", author="@first", like_count=999),
        Comment(
            text="Tracklist:\n0:00 - Intro\n2:34 Pulse Train\n7:12 Crystal Drift",
            author="@DJ_Source",
            like_count=421,
        ),
    ]
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description="No timestamps anywhere here."),
        comments=comments,
    )

    result = detect_tracklist("http://fake")

    assert result.source == "comments"
    assert [t.title for t in result.tracks] == ["Intro", "Pulse Train", "Crystal Drift"]


def test_detect_tracklist_returns_none_source_when_nothing_matches(
    monkeypatch,
) -> None:
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description="No timestamps anywhere here."),
        comments=[Comment(text="cool", author="@a", like_count=1)],
    )

    result = detect_tracklist("http://fake")

    assert result.source is None
    assert result.tracks == []
    # Hints still come through so the UI can pre-fill album/artist.
    assert result.guessed_artist == "Some Mix"
    assert result.guessed_album == "The Greatest Hits"


def test_detect_tracklist_ignores_chapters_with_only_one_entry(
    monkeypatch,
) -> None:
    """A single chapter isn't a tracklist — fall through to description."""
    description = "0:00 Solo Intro\n3:00 Solo Outro\n"
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(
            chapters=[Chapter(start_time=0.0, end_time=120.0, title="Whole video")],
            description=description,
        ),
        comments=[],
    )

    result = detect_tracklist("http://fake")

    assert result.source == "description"
    assert len(result.tracks) == 2


# ---- detect_tracklist on_status callback -------------------------------


def test_detect_status_emits_only_for_attempted_sources_chapters(
    monkeypatch,
) -> None:
    """When chapters hit, no description/comments status is emitted."""
    msgs: list[str] = []
    chapters = [
        Chapter(start_time=0.0,   end_time=100.0, title="A"),
        Chapter(start_time=100.0, end_time=200.0, title="B"),
    ]
    _patch_fetchers(
        monkeypatch, metadata=_make_metadata(chapters=chapters), comments=[]
    )

    detect_tracklist("http://fake", on_status=msgs.append)

    assert msgs == [
        "Trying to get tracklist from chapters…",
        "Found tracklist in video chapters (2 tracks).",
    ]


def test_detect_status_includes_comment_author(monkeypatch) -> None:
    """The comments-branch ``Found …`` line names the comment author."""
    msgs: list[str] = []
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description="no timestamps here"),
        comments=[
            Comment(
                text="Tracklist:\n0:00 One\n3:00 Two",
                author="@DJ_Source",
                like_count=5,
            ),
        ],
    )

    detect_tracklist("http://fake", on_status=msgs.append)

    assert msgs == [
        "Trying to get tracklist from chapters…",
        "Trying to get tracklist from description…",
        "Trying to get tracklist from top comments…",
        "Found tracklist in top comment by @DJ_Source (2 tracks).",
    ]


def test_detect_status_falls_back_when_comment_has_no_author(monkeypatch) -> None:
    msgs: list[str] = []
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description="no timestamps here"),
        comments=[
            Comment(
                text="Tracklist:\n0:00 One\n3:00 Two",
                author="",
                like_count=5,
            ),
        ],
    )

    detect_tracklist("http://fake", on_status=msgs.append)

    assert msgs[-1] == "Found tracklist in top comment by an unknown user (2 tracks)."


def test_detect_status_emits_all_three_when_nothing_matches(monkeypatch) -> None:
    msgs: list[str] = []
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description="no timestamps here"),
        comments=[Comment(text="cool", author="@a", like_count=1)],
    )

    detect_tracklist("http://fake", on_status=msgs.append)

    # All three "Trying"; no "Found".
    assert msgs == [
        "Trying to get tracklist from chapters…",
        "Trying to get tracklist from description…",
        "Trying to get tracklist from top comments…",
    ]


def test_detect_works_without_status_callback(monkeypatch) -> None:
    """``on_status`` is optional; default of None must not raise."""
    _patch_fetchers(
        monkeypatch,
        metadata=_make_metadata(description="0:00 One\n3:00 Two\n"),
        comments=[],
    )

    result = detect_tracklist("http://fake")
    assert result.source == "description"
    assert len(result.tracks) == 2
