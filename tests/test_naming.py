"""Tests for the filename-sanitisation helpers.

Output filenames are user-visible and must round-trip safely on Windows
(where ``< > : " / \\ | ? *`` and trailing dots are illegal), so we exercise
the corner cases here rather than discovering them at runtime.
"""

from __future__ import annotations

import pytest

from slicer.core.naming import safe_filename, track_filename


# ---- safe_filename -----------------------------------------------------


def test_safe_filename_passes_clean_titles_through() -> None:
    assert safe_filename("Intro Theme") == "Intro Theme"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('Track <evil> name', "Track _evil_ name"),
        ('Quote " here',       "Quote _ here"),
        ("AC/DC",              "AC_DC"),
        ("path\\with\\back",   "path_with_back"),
        ("Bar | Pipe",         "Bar _ Pipe"),
        ("What?",              "What_"),
        ("Star * Wars",        "Star _ Wars"),
        ("Colon: title",       "Colon_ title"),
    ],
)
def test_safe_filename_replaces_illegal_chars(raw: str, expected: str) -> None:
    assert safe_filename(raw) == expected


def test_safe_filename_strips_control_chars() -> None:
    # ``\x01`` and ``\n`` are both inside the illegal-char regex's
    # ``\x00-\x1f`` range, so they each become ``_``.
    assert safe_filename("Foo\x01\nBar") == "Foo__Bar"


def test_safe_filename_collapses_whitespace_and_trims() -> None:
    assert safe_filename("   lots   of    spaces   ") == "lots of spaces"


def test_safe_filename_strips_trailing_dots_and_spaces() -> None:
    # Windows can't open files whose name ends with a dot or space.
    assert safe_filename("Trailing dots...") == "Trailing dots"
    assert safe_filename("Trailing space   ") == "Trailing space"


def test_safe_filename_strips_alternating_trailing_dots_and_spaces() -> None:
    """Catches the bug where a single ``.strip().strip(".")`` chain would
    leave a trailing space behind on inputs like ``"Track . . ."``."""
    assert safe_filename("Track . . .") == "Track"
    assert safe_filename("Track . ") == "Track"
    assert safe_filename("Track .") == "Track"


def test_safe_filename_falls_back_when_string_becomes_empty() -> None:
    # The fallback to "track" only triggers when cleaning leaves nothing
    # behind — empty input, pure whitespace, or pure dots.
    assert safe_filename("") == "track"
    assert safe_filename("   ") == "track"
    assert safe_filename("...") == "track"


def test_safe_filename_keeps_underscore_runs_for_all_illegal_input() -> None:
    # An all-illegal title becomes a run of underscores rather than the
    # generic "track" fallback. That preserves uniqueness across multiple
    # weird tracks on the same album.
    assert safe_filename("///\\\\???") == "________"


def test_safe_filename_truncates_to_max_len() -> None:
    long = "x" * 500
    out = safe_filename(long, max_len=180)
    assert len(out) == 180
    assert out == "x" * 180


def test_safe_filename_truncation_strips_trailing_garbage() -> None:
    # If the truncated tail ends with a dot/space it must still be cleaned.
    raw = ("a" * 178) + " ."
    out = safe_filename(raw, max_len=180)
    assert not out.endswith(".")
    assert not out.endswith(" ")


# ---- track_filename ----------------------------------------------------


def test_track_filename_pads_to_total_width() -> None:
    # 11 tracks → 2-digit prefix.
    assert track_filename(1, 11, "First")  == "01 - First.mp3"
    assert track_filename(11, 11, "Last") == "11 - Last.mp3"


def test_track_filename_widens_for_three_digit_totals() -> None:
    # 100+ tracks → 3-digit prefix.
    assert track_filename(1, 100, "First")   == "001 - First.mp3"
    assert track_filename(100, 100, "Last") == "100 - Last.mp3"


def test_track_filename_minimum_width_is_two() -> None:
    # Even a single-track album gets ``01`` rather than ``1`` for sort safety.
    assert track_filename(1, 1, "Solo") == "01 - Solo.mp3"


def test_track_filename_sanitises_title() -> None:
    # Slashes / colons / question marks all become underscores in the body.
    assert track_filename(1, 5, "AC/DC: Live?") == "01 - AC_DC_ Live_.mp3"


def test_track_filename_always_ends_in_mp3() -> None:
    assert track_filename(1, 5, "anything").endswith(".mp3")
