"""Tests for ``PipelineWorker._cut_all`` (album-subfolder convention).

ffmpeg and the network are stubbed; we call ``_cut_all`` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from slicer import workers
from slicer.core import ffmpeg as ffmpeg_mod
from slicer.core.tracklist import Track
from slicer.workers import CutJob, PipelineWorker


@pytest.fixture(autouse=True)
def _stub_ffmpeg_and_tagger(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Stub ffmpeg/tagger so ``_cut_all`` only does filesystem + naming work."""
    calls: dict[str, list[Any]] = {"cut": [], "tag": []}

    def fake_probe_duration(_src: Path, *, bins: Any) -> float:
        return 600.0  # long enough for any test tracklist

    def fake_cut_segment(
        _src: Path,
        dest: Path,
        start: float,
        end: float | None,
        *,
        bins: Any,
    ) -> None:
        # Placeholder so callers that stat the result still work.
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"")
        calls["cut"].append((dest, start, end))

    def fake_tag_track(dest: Path, **kwargs: Any) -> None:
        calls["tag"].append((dest, kwargs))

    monkeypatch.setattr(ffmpeg_mod, "probe_duration", fake_probe_duration)
    monkeypatch.setattr(ffmpeg_mod, "cut_segment", fake_cut_segment)
    monkeypatch.setattr(workers.tagger, "tag_track", fake_tag_track)
    return calls


def _make_job(output_dir: Path, *, album: str, artist: str = "The Band") -> CutJob:
    return CutJob(
        youtube_url="https://example.invalid/v",
        album=album,
        artist=artist,
        tracklist_text="ignored — we feed Tracks directly",
        output_dir=output_dir,
    )


def _tracks() -> list[Track]:
    return [
        Track(index=1, start=0.0, title="Intro"),
        Track(index=2, start=60.0, title="Sunrise"),
        Track(index=3, start=180.0, title="Outro"),
    ]


def _drive_cut_all(worker: PipelineWorker, tracks: list[Track]) -> dict[str, Any]:
    """Run ``_cut_all`` and capture the emitted ``finished`` payload + log lines."""
    captured: dict[str, Any] = {"finished": None, "logs": []}

    worker.finished.connect(lambda ok, msg: captured.__setitem__("finished", (ok, msg)))
    worker.logLine.connect(lambda line: captured["logs"].append(line))

    # ``bins`` is opaque to the stubs; any sentinel works.
    worker._cut_all(tracks, Path("/dev/null"), bins=object())  # type: ignore[arg-type]
    return captured


def test_cut_all_writes_into_album_subfolder(
    tmp_path: Path,
    _stub_ffmpeg_and_tagger: dict[str, list[Any]],
) -> None:
    job = _make_job(tmp_path, album="Echoes of Tomorrow")
    worker = PipelineWorker(job)

    captured = _drive_cut_all(worker, _tracks())

    album_dir = tmp_path / "Echoes of Tomorrow"
    assert album_dir.is_dir(), "album subfolder must be created"

    written = sorted(p.name for p in album_dir.iterdir())
    assert written == ["01 - Intro.mp3", "02 - Sunrise.mp3", "03 - Outro.mp3"]

    ok, msg = captured["finished"]
    assert ok is True
    assert str(album_dir) in msg
    assert "All 3 tracks written to" in msg

    # Cuts and tags target the per-album folder, not the chosen root.
    cut_dests = [dest for dest, _start, _end in _stub_ffmpeg_and_tagger["cut"]]
    assert all(dest.parent == album_dir for dest in cut_dests)
    tag_dests = [dest for dest, _kwargs in _stub_ffmpeg_and_tagger["tag"]]
    assert all(dest.parent == album_dir for dest in tag_dests)


def test_cut_all_sanitises_album_name_for_subfolder(
    tmp_path: Path,
) -> None:
    # Windows-illegal characters + trailing dots/spaces.
    job = _make_job(tmp_path, album="Live: Greatest Hits? <Vol. 1>  . ")
    worker = PipelineWorker(job)

    _drive_cut_all(worker, _tracks())

    children = list(tmp_path.iterdir())
    assert len(children) == 1, f"expected exactly one album dir, got {children!r}"
    album_dir = children[0]
    assert album_dir.is_dir()
    name = album_dir.name
    for bad in (":", "?", "<", ">"):
        assert bad not in name
    assert not name.endswith(".") and not name.endswith(" ")
    assert "Live" in name and "Greatest Hits" in name and "Vol. 1" in name


def test_cut_all_falls_back_to_output_dir_when_album_blank(
    tmp_path: Path,
) -> None:
    # Defensive fallback if a whitespace-only album sneaks past the GUI.
    job = _make_job(tmp_path, album="   ")
    worker = PipelineWorker(job)

    captured = _drive_cut_all(worker, _tracks())

    # No subdir; mp3s land directly in tmp_path.
    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["01 - Intro.mp3", "02 - Sunrise.mp3", "03 - Outro.mp3"]

    ok, msg = captured["finished"]
    assert ok is True
    assert str(tmp_path) in msg
