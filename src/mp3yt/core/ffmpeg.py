"""Thin wrappers around ``ffmpeg`` and ``ffprobe`` command-line tools.

We intentionally shell out instead of using a binding library:

* ``ffmpeg`` is the de-facto standard and is required anyway by ``yt-dlp``.
* For MP3, ``ffmpeg -c copy`` gives us frame-accurate, lossless cuts in O(seconds).
* No extra Python wheel to maintain.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class FfmpegNotFoundError(RuntimeError):
    """Raised when ffmpeg or ffprobe are not on PATH."""


class FfmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe invocation exits non-zero."""


@dataclass(frozen=True)
class FfmpegBinaries:
    ffmpeg: str
    ffprobe: str


def _bundled_search_paths() -> list[Path]:
    """Locations to check for an app-bundled copy of ffmpeg/ffprobe.

    Order matters: more specific / explicit paths first.
    """
    paths: list[Path] = []

    # 1. Explicit override (handy for tests and portable installs).
    override = os.environ.get("MP3YT_FFMPEG_DIR")
    if override:
        paths.append(Path(override))

    # 2. PyInstaller bundle.
    #    In onedir mode `_MEIPASS` is the `_internal/` folder; in onefile mode
    #    it's a temp extraction directory. Both work for our purposes.
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "bin")
            paths.append(Path(meipass))
        # Also try next to the executable in case someone drops binaries there.
        exe_dir = Path(sys.executable).parent
        paths.append(exe_dir / "bin")
        paths.append(exe_dir)

    return paths


def _binary_name(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def find_binaries() -> FfmpegBinaries:
    """Locate ``ffmpeg`` and ``ffprobe``.

    Looks in (in order):

    1. ``MP3YT_FFMPEG_DIR`` env var.
    2. PyInstaller bundle (``_MEIPASS/bin`` and next to the executable).
    3. ``PATH`` via :func:`shutil.which`.

    Raises :class:`FfmpegNotFoundError` with a helpful message if either
    binary is missing.
    """
    ffmpeg_name = _binary_name("ffmpeg")
    ffprobe_name = _binary_name("ffprobe")

    for d in _bundled_search_paths():
        ffmpeg = d / ffmpeg_name
        ffprobe = d / ffprobe_name
        if ffmpeg.is_file() and ffprobe.is_file():
            return FfmpegBinaries(ffmpeg=str(ffmpeg), ffprobe=str(ffprobe))

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    missing = [n for n, v in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if not v]
    if missing:
        raise FfmpegNotFoundError(
            f"Could not find {', '.join(missing)} on PATH. "
            "Install ffmpeg (https://ffmpeg.org/download.html) and try again."
        )
    assert ffmpeg and ffprobe  # for type checkers
    return FfmpegBinaries(ffmpeg=ffmpeg, ffprobe=ffprobe)


def probe_duration(path: Path, *, bins: FfmpegBinaries | None = None) -> float:
    """Return the duration of the audio file at ``path`` in seconds."""
    bins = bins or find_binaries()
    cmd = [
        bins.ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    try:
        out = subprocess.run(
            cmd, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as exc:
        raise FfmpegError(
            f"ffprobe failed for {path}: {exc.stderr.strip() or exc}"
        ) from exc
    try:
        data = json.loads(out.stdout)
        return float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise FfmpegError(
            f"Could not read duration from ffprobe output for {path}."
        ) from exc


def cut_segment(
    src: Path,
    dest: Path,
    start: float,
    end: float | None,
    *,
    bins: FfmpegBinaries | None = None,
) -> None:
    """Cut ``[start, end)`` from ``src`` to ``dest`` losslessly via stream copy.

    If ``end`` is ``None`` the cut goes to the end of the file. The destination
    parent directory must already exist; the file is overwritten if present.
    """
    if start < 0:
        raise ValueError("start must be >= 0")
    if end is not None and end <= start:
        raise ValueError("end must be greater than start")

    bins = bins or find_binaries()

    # `-ss` before `-i` is the fast (input) seek; combined with `-c copy` it's
    # near-instant. For MP3 the cut snaps to MP3 frame boundaries (~26 ms),
    # which is plenty accurate for splitting an album rip by tracklist.
    cmd: list[str] = [
        bins.ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{start:.3f}",
    ]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += [
        "-i", str(src),
        "-map", "0:a:0",
        "-c", "copy",
        # Strip any inherited tags; we'll write fresh ones with mutagen later.
        "-map_metadata", "-1",
        "-write_xing", "1",
        str(dest),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise FfmpegError(
            f"ffmpeg failed cutting {src.name} -> {dest.name}: "
            f"{exc.stderr.strip() or exc}"
        ) from exc
