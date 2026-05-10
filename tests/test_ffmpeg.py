"""Tests for the ffmpeg binary lookup."""

from __future__ import annotations

import os
import sys

import pytest

from mp3yt.core.ffmpeg import FfmpegNotFoundError, find_binaries


def test_find_binaries_uses_env_override(tmp_path, monkeypatch):
    """If MP3YT_FFMPEG_DIR points at a folder containing both binaries, use it."""
    suffix = ".exe" if sys.platform.startswith("win") else ""
    ff = tmp_path / f"ffmpeg{suffix}"
    fp = tmp_path / f"ffprobe{suffix}"
    ff.write_text("")
    fp.write_text("")

    monkeypatch.setenv("MP3YT_FFMPEG_DIR", str(tmp_path))
    bins = find_binaries()
    assert bins.ffmpeg == str(ff)
    assert bins.ffprobe == str(fp)


def test_find_binaries_falls_through_when_override_dir_empty(tmp_path, monkeypatch):
    """An override pointing at an empty dir should fall through to PATH."""
    monkeypatch.setenv("MP3YT_FFMPEG_DIR", str(tmp_path))
    # System ffmpeg should still be findable on the dev machine.
    bins = find_binaries()
    assert os.path.basename(bins.ffmpeg).startswith("ffmpeg")


def test_find_binaries_raises_when_path_empty(tmp_path, monkeypatch):
    """With an empty override dir AND a wiped PATH, we get a clear error."""
    monkeypatch.setenv("MP3YT_FFMPEG_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing executable here
    with pytest.raises(FfmpegNotFoundError):
        find_binaries()
