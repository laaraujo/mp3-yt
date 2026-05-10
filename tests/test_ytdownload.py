"""Tests for the pure-logic yt-dlp wrapper helpers (no network)."""

from __future__ import annotations

from slicer.core.ytdownload import (
    _PREFERRED_YT_PLAYER_CLIENTS,
    _apply_anti_bot,
    _format_download_progress,
    _format_eta,
    _human_bytes,
)


def test_apply_anti_bot_sets_player_client_when_missing() -> None:
    opts: dict = {}
    _apply_anti_bot(opts)
    yt_args = opts["extractor_args"]["youtube"]
    assert yt_args["player_client"] == list(_PREFERRED_YT_PLAYER_CLIENTS)


def test_apply_anti_bot_preserves_caller_supplied_player_client() -> None:
    """A caller-pinned player_client must not be clobbered."""
    opts: dict = {"extractor_args": {"youtube": {"player_client": ["android_creator"]}}}
    _apply_anti_bot(opts)
    assert opts["extractor_args"]["youtube"]["player_client"] == ["android_creator"]


def test_apply_anti_bot_preserves_other_youtube_args() -> None:
    """Other youtube args (and other extractors) must survive."""
    opts: dict = {
        "extractor_args": {
            "youtube": {"max_comments": ["20,20,0,20"]},
            "twitch": {"client_id": "abc"},
        },
    }
    _apply_anti_bot(opts)
    yt = opts["extractor_args"]["youtube"]
    assert yt["max_comments"] == ["20,20,0,20"]
    assert yt["player_client"] == list(_PREFERRED_YT_PLAYER_CLIENTS)
    assert opts["extractor_args"]["twitch"] == {"client_id": "abc"}


def test_apply_anti_bot_does_not_mutate_input_extractor_args_in_place() -> None:
    """Reassigns rather than mutating the caller's ``extractor_args``.

    Protects callers reusing a shared options template across calls.
    """
    shared = {"youtube": {"max_comments": ["20,20,0,20"]}}
    opts = {"extractor_args": shared}
    _apply_anti_bot(opts)

    assert "player_client" not in shared["youtube"]
    assert "player_client" in opts["extractor_args"]["youtube"]


# ---- progress formatters -----------------------------------------------


def test_human_bytes_steps_through_units() -> None:
    assert _human_bytes(0) == "0.0 B"
    assert _human_bytes(512) == "512.0 B"
    assert _human_bytes(1024) == "1.0 KB"
    assert _human_bytes(1500) == "1.5 KB"
    assert _human_bytes(1024 * 1024) == "1.0 MB"
    assert _human_bytes(1024**3) == "1.0 GB"
    assert _human_bytes(1024**4) == "1.0 TB"
    assert _human_bytes(1024**5) == "1024.0 TB"  # never overflows the unit list


def test_human_bytes_clamps_negative() -> None:
    # Weird/None values must never crash.
    assert _human_bytes(-50) == "0.0 B"


def test_format_eta_short_durations() -> None:
    assert _format_eta(0) == "0:00"
    assert _format_eta(7) == "0:07"
    assert _format_eta(75) == "1:15"
    assert _format_eta(599) == "9:59"


def test_format_eta_uses_h_mm_ss_above_one_hour() -> None:
    assert _format_eta(3600) == "1:00:00"
    assert _format_eta(3661) == "1:01:01"
    assert _format_eta(7200) == "2:00:00"


def test_format_eta_handles_floats_and_negatives() -> None:
    assert _format_eta(7.9) == "0:07"  # truncates
    assert _format_eta(-5) == "0:00"


def test_format_download_progress_full_dict() -> None:
    out = _format_download_progress(
        {
            "downloaded_bytes": 12_500_000,
            "total_bytes": 27_500_000,
            "speed": 1_800_000,
            "eta": 8,
        }
    )
    assert " 45.5%" in out
    assert "11.9 MB / 26.2 MB" in out
    assert "1.7 MB/s" in out
    assert "ETA 0:08" in out


def test_format_download_progress_uses_estimate_when_total_missing() -> None:
    out = _format_download_progress(
        {
            "downloaded_bytes": 5_000_000,
            "total_bytes_estimate": 10_000_000,
            "speed": 500_000,
            "eta": 10,
        }
    )
    assert " 50.0%" in out
    assert "ETA 0:10" in out


def test_format_download_progress_omits_unknown_segments() -> None:
    """Speed/ETA are often None at the start; skip them instead of printing None."""
    out = _format_download_progress(
        {
            "downloaded_bytes": 1024,
        }
    )
    assert "None" not in out
    assert "%" not in out
    assert "/s" not in out
    assert "ETA" not in out
    assert "1.0 KB" in out
