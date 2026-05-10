"""Thin wrappers around the ``ffmpeg`` and ``ffprobe`` CLIs.

We shell out instead of using a binding library: ffmpeg is required by
yt-dlp anyway, and ``ffmpeg -c copy`` gives lossless MP3 cuts in seconds.
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
    """Locations to check for an app-bundled ffmpeg/ffprobe (most-specific first)."""
    paths: list[Path] = []

    # Explicit override (handy for tests and portable installs).
    override = os.environ.get("YT2MP3SLICER_FFMPEG_DIR")
    if override:
        paths.append(Path(override))

    # PyInstaller bundle: `_MEIPASS` is `_internal/` (onedir) or a temp
    # extraction dir (onefile). Both work.
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "bin")
            paths.append(Path(meipass))
        # Also check next to the executable.
        exe_dir = Path(sys.executable).parent
        paths.append(exe_dir / "bin")
        paths.append(exe_dir)

    return paths


def _binary_name(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def _subprocess_startup_kwargs() -> dict:
    """Hide child ffmpeg/ffprobe consoles in Windows GUI builds."""
    if not sys.platform.startswith("win"):
        return {}

    kwargs: dict = {}
    startupinfo_factory = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_factory is not None:
        startupinfo = startupinfo_factory()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags

    return kwargs


def find_binaries() -> FfmpegBinaries:
    """Locate ``ffmpeg`` and ``ffprobe``.

    Search order: ``YT2MP3SLICER_FFMPEG_DIR`` env var → PyInstaller bundle
    → ``PATH``. Raises :class:`FfmpegNotFoundError` if either is missing.
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
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, **_subprocess_startup_kwargs())
    except subprocess.CalledProcessError as exc:
        raise FfmpegError(f"ffprobe failed for {path}: {exc.stderr.strip() or exc}") from exc
    try:
        data = json.loads(out.stdout)
        return float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise FfmpegError(f"Could not read duration from ffprobe output for {path}.") from exc


def cut_segment(
    src: Path,
    dest: Path,
    start: float,
    end: float | None,
    *,
    bins: FfmpegBinaries | None = None,
) -> None:
    """Cut ``[start, end)`` from ``src`` to ``dest`` losslessly via stream copy.

    ``end=None`` cuts to the end of the file. The destination is overwritten
    if present and its parent directory must already exist.
    """
    if start < 0:
        raise ValueError("start must be >= 0")
    if end is not None and end <= start:
        raise ValueError("end must be greater than start")

    bins = bins or find_binaries()

    # `-ss` before `-i` is the fast input seek; with `-c copy` it snaps to
    # MP3 frame boundaries (~26 ms — fine for tracklist splits).
    cmd: list[str] = [
        bins.ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
    ]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += [
        "-i",
        str(src),
        "-map",
        "0:a:0",
        "-c",
        "copy",
        # Strip inherited tags; we write fresh ones with mutagen later.
        "-map_metadata",
        "-1",
        "-write_xing",
        "1",
        str(dest),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, **_subprocess_startup_kwargs())
    except subprocess.CalledProcessError as exc:
        raise FfmpegError(f"ffmpeg failed cutting {src.name} -> {dest.name}: {exc.stderr.strip() or exc}") from exc
