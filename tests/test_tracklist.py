"""Tests for the tracklist parser."""

from __future__ import annotations

import pytest

from slicer.core.tracklist import (
    TracklistError,
    find_tracklist_in_text,
    format_timestamp,
    format_tracks,
    parse_tracklist,
)


def _seconds(tracks):
    return [(t.index, t.start, t.title) for t in tracks]


def test_basic_example_from_user() -> None:
    text = """\
0:00 Intro
3:01 Sunrise
5:32 Departure
8:24 Crossroads
11:53 Reflection
14:19 Storm
16:53 Calm
19:29 Awakening
22:38 Echoes
24:33 Horizon
26:30 Outro
"""
    tracks = parse_tracklist(text)
    assert len(tracks) == 11
    assert tracks[0].start == 0
    assert tracks[0].title == "Intro"
    assert tracks[1].start == 3 * 60 + 1
    assert tracks[-1].start == 26 * 60 + 30
    assert tracks[-1].title == "Outro"
    assert [t.index for t in tracks] == list(range(1, 12))


def test_handles_h_mm_ss() -> None:
    text = "0:00 Intro\n1:23:45 Long Bonus Track\n"
    tracks = parse_tracklist(text)
    assert tracks[1].start == 1 * 3600 + 23 * 60 + 45


def test_strips_track_number_prefixes() -> None:
    text = """\
1. 0:00 First
02) 1:30 Second
3 - 3:00 Third
"""
    tracks = parse_tracklist(text)
    assert [t.title for t in tracks] == ["First", "Second", "Third"]
    assert [t.start for t in tracks] == [0, 90, 180]


def test_strips_dash_separator_between_timestamp_and_title() -> None:
    tracks = parse_tracklist("0:00 - The Title\n1:00 — Em Dash Title\n")
    assert tracks[0].title == "The Title"
    assert tracks[1].title == "Em Dash Title"


def test_ignores_blank_and_comment_lines() -> None:
    text = """\
# this is a comment
0:00 First

# another comment
1:00 Second
"""
    tracks = parse_tracklist(text)
    assert len(tracks) == 2


def test_rejects_empty_input() -> None:
    with pytest.raises(TracklistError):
        parse_tracklist("")


def test_rejects_unparseable_line() -> None:
    with pytest.raises(TracklistError):
        parse_tracklist("0:00 First\nthis is not a track\n")


def test_rejects_non_increasing_timestamps() -> None:
    with pytest.raises(TracklistError):
        parse_tracklist("0:00 First\n0:00 Second\n")
    with pytest.raises(TracklistError):
        parse_tracklist("1:00 First\n0:30 Second\n")


def test_rejects_bad_timestamp_components() -> None:
    # seconds >= 60 always rejected
    with pytest.raises(TracklistError):
        parse_tracklist("0:99 Bad\n")
    # minutes >= 60 rejected only in H:MM:SS form
    with pytest.raises(TracklistError):
        parse_tracklist("1:99:00 Bad\n")


def test_allows_minutes_above_60_in_mm_ss_form() -> None:
    # Some tracklists for long videos write "90:00" instead of "1:30:00".
    tracks = parse_tracklist("0:00 First\n90:00 Second\n")
    assert tracks[1].start == 90 * 60


# ---- formatting helpers --------------------------------------------------


def test_format_timestamp_prefers_mm_ss_under_one_hour() -> None:
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(59) == "0:59"
    assert format_timestamp(60) == "1:00"
    assert format_timestamp(181) == "3:01"


def test_format_timestamp_uses_h_mm_ss_at_one_hour_or_more() -> None:
    assert format_timestamp(3600) == "1:00:00"
    assert format_timestamp(3661) == "1:01:01"


def test_format_tracks_round_trips_through_parse() -> None:
    text = "0:00 First\n3:01 Second\n1:23:45 Third\n"
    parsed = parse_tracklist(text)
    formatted = format_tracks(parsed)
    re_parsed = parse_tracklist(formatted)
    assert [(t.start, t.title) for t in re_parsed] == [
        (t.start, t.title) for t in parsed
    ]


# ---- lenient text scanner (for YouTube descriptions) ---------------------


def test_find_tracklist_in_text_handles_youtube_description() -> None:
    desc = """\
Subscribe for more!

Tracklist:
0:00 Intro
3:01 Sunrise
5:32 Departure

Follow me on Twitter: @example
#playlist #liveset
"""
    tracks = find_tracklist_in_text(desc)
    assert len(tracks) == 3
    assert tracks[0].start == 0
    assert tracks[0].title == "Intro"
    assert tracks[2].start == 5 * 60 + 32


def test_find_tracklist_in_text_picks_longest_increasing_run() -> None:
    # Mixed content with a small early "decoy" group and a longer real one.
    desc = """\
Outro from previous episode at 12:30 etc.
This part has 0:30 only one fake match.

The real list:
0:00 Intro
1:00 Verse
2:30 Chorus
4:00 Bridge
"""
    tracks = find_tracklist_in_text(desc)
    titles = [t.title for t in tracks]
    assert titles == ["Intro", "Verse", "Chorus", "Bridge"]


def test_find_tracklist_in_text_returns_empty_when_nothing_useful() -> None:
    assert find_tracklist_in_text("Hello world\nNo timestamps here\n") == []
    assert find_tracklist_in_text("0:00 Just one entry\n") == []
