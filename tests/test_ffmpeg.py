"""Tests for the ffmpeg binary lookup."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from slicer.core.ffmpeg import FfmpegNotFoundError, _subprocess_startup_kwargs, find_binaries


def test_find_binaries_uses_env_override(tmp_path, monkeypatch):
    """YT2MP3SLICER_FFMPEG_DIR is honored when both binaries are present."""
    suffix = ".exe" if sys.platform.startswith("win") else ""
    ff = tmp_path / f"ffmpeg{suffix}"
    fp = tmp_path / f"ffprobe{suffix}"
    ff.write_text("")
    fp.write_text("")

    monkeypatch.setenv("YT2MP3SLICER_FFMPEG_DIR", str(tmp_path))
    bins = find_binaries()
    assert bins.ffmpeg == str(ff)
    assert bins.ffprobe == str(fp)


def test_find_binaries_falls_through_when_override_dir_empty(tmp_path, monkeypatch):
    """Empty override dir → fall through to PATH."""
    monkeypatch.setenv("YT2MP3SLICER_FFMPEG_DIR", str(tmp_path))
    bins = find_binaries()
    assert Path(bins.ffmpeg).name.startswith("ffmpeg")


def test_find_binaries_raises_when_path_empty(tmp_path, monkeypatch):
    """Empty override + wiped PATH must raise a clear error."""
    monkeypatch.setenv("YT2MP3SLICER_FFMPEG_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(FfmpegNotFoundError):
        find_binaries()


def test_subprocess_startup_kwargs_hides_windows_console(monkeypatch):
    """Windows GUI builds must not flash cmd windows for ffmpeg/ffprobe."""

    class FakeStartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    kwargs = _subprocess_startup_kwargs()

    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags == 1
    assert kwargs["startupinfo"].wShowWindow == 0
