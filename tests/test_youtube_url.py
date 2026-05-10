"""Tests for the YouTube URL validation regex.

The validator gates the entire UI form (URL → all fields below light up), so
it's worth covering the surface thoroughly: happy-path video shapes, every
flavour of Shorts URL we want to reject, and obvious junk.
"""

from __future__ import annotations

import pytest

from slicer.core.youtube_url import is_shorts_url, youtube_video_id


# A canonical 11-character base64-url id used across the parametrised cases.
_VID = "zcYVH4fYCkg"


# ---- happy path: recognised video URLs ---------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={_VID}",
        f"http://youtube.com/watch?v={_VID}",
        f"https://m.youtube.com/watch?v={_VID}",
        f"https://music.youtube.com/watch?v={_VID}",
        f"https://www.youtube.com/watch?v={_VID}&t=120",
        f"https://www.youtube.com/watch?v={_VID}&list=PLabc",
        f"https://www.youtube.com/watch?list=PLabc&v={_VID}",
        f"https://www.youtube.com/watch?list=PLabc&index=2&v={_VID}",
        f"https://www.youtube.com/watch?v={_VID}#t=10",
        f"https://www.youtube.com/live/{_VID}",
        f"https://www.youtube.com/embed/{_VID}",
        f"https://www.youtube.com/v/{_VID}",
        f"https://youtu.be/{_VID}",
        f"https://youtu.be/{_VID}?t=20",
        f"https://youtu.be/{_VID}?si=abc",
        f"  https://www.youtube.com/watch?v={_VID}  ",  # surrounding whitespace
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={_VID}",      # case-insensitive scheme/host
    ],
)
def test_youtube_video_id_extracts_id_from_supported_urls(url: str) -> None:
    assert youtube_video_id(url) == _VID
    assert is_shorts_url(url) is False


# ---- shorts: extracted but flagged via is_shorts_url -------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/shorts/{_VID}",
        f"https://m.youtube.com/shorts/{_VID}",
        f"https://youtube.com/shorts/{_VID}",
        f"https://www.youtube.com/shorts/{_VID}?feature=share",
        # Even with surrounding whitespace it should still register as Shorts.
        f"   https://www.youtube.com/shorts/{_VID}   ",
        # Case-insensitive host.
        f"https://WWW.YOUTUBE.COM/shorts/{_VID}",
    ],
)
def test_shorts_urls_are_flagged_and_rejected(url: str) -> None:
    assert is_shorts_url(url) is True
    # Even though the id is technically present, we don't expose it — Shorts
    # are not a supported source for the slicer.
    assert youtube_video_id(url) is None


# ---- junk / unsupported: must return None and not be Shorts ------------


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "ftp://www.youtube.com/watch?v=" + _VID,        # wrong scheme
        "https://www.youtube.com/",                      # bare host
        "https://www.youtube.com/playlist?list=PLabc",   # playlist page
        "https://www.youtube.com/@SomeChannel",          # @-handle channel
        "https://www.youtube.com/c/SomeChannel",         # /c/ channel
        "https://www.youtube.com/channel/UCabc",         # /channel/ channel
        "https://example.com/watch?v=" + _VID,           # not a YouTube host
        "https://www.youtube.com/watch?v=tooshort",      # < 11 char id
        "https://www.youtube.com/watch?v=" + _VID + "EXTRA",  # > 11 char id
        "https://www.youtube.com/watch",                 # missing v= entirely
        "https://www.youtube.com/watch?foo=bar",         # no v= param
    ],
)
def test_junk_urls_are_rejected(url: str) -> None:
    assert youtube_video_id(url) is None
    assert is_shorts_url(url) is False


# ---- edge-case sanity --------------------------------------------------


def test_youtube_video_id_preserves_case_and_underscore_dash() -> None:
    """The id alphabet contains - and _ as well as mixed case; verify both
    are returned verbatim instead of being normalised."""
    weird_id = "A_z-9876543"
    assert youtube_video_id(f"https://youtu.be/{weird_id}") == weird_id


def test_youtube_video_id_returns_none_for_none_like_input() -> None:
    # The function is documented to take a str; this just guards against a
    # bare empty input not erroring out.
    assert youtube_video_id("") is None
    assert youtube_video_id("   \n  ") is None
