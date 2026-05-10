"""Download a YouTube (or any yt-dlp-supported) URL as a single MP3 file.

Audio is extracted with ffmpeg. yt-dlp's ``FFmpegExtractAudio`` postprocessor
locates ffmpeg/ffprobe via ``shutil.which`` by default, which doesn't work
when we're running from a frozen macOS ``.app`` bundle (its ``PATH`` doesn't
include the bundled ``bin/`` folder). Callers should pass ``ffmpeg_location``
pointing at the directory containing both binaries.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DownloadResult:
    path: Path           # absolute path to the produced .mp3
    title: str           # video title as reported by YouTube
    duration: float      # duration in seconds (from yt-dlp metadata)


@dataclass(frozen=True)
class Chapter:
    """A single YouTube chapter as exposed by yt-dlp."""

    start_time: float
    end_time: float
    title: str


@dataclass(frozen=True)
class VideoMetadata:
    """Subset of yt-dlp's info dict that we care about."""

    title: str
    uploader: str
    description: str
    duration: float
    chapters: list[Chapter]


ProgressCallback = Callable[[float, str], None]
"""Receives (fraction in [0, 1], status message)."""


def fetch_metadata(url: str) -> VideoMetadata:
    """Resolve a URL to its video metadata without downloading the audio.

    Always cheap — yt-dlp just hits YouTube's player endpoint. Raises whatever
    yt-dlp raises (``yt_dlp.utils.DownloadError`` for bad URLs etc.) so the
    caller can present a friendly message.
    """
    from yt_dlp import YoutubeDL

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # We don't need the comments fetch for chapter/description detection,
        # which keeps this fast (sub-second on a healthy connection).
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    chapters_raw = info.get("chapters") or []
    chapters: list[Chapter] = []
    for ch in chapters_raw:
        try:
            chapters.append(
                Chapter(
                    start_time=float(ch.get("start_time") or 0.0),
                    end_time=float(ch.get("end_time") or 0.0),
                    title=str(ch.get("title") or "").strip() or "Untitled",
                )
            )
        except (TypeError, ValueError):
            continue

    return VideoMetadata(
        title=str(info.get("title") or "").strip(),
        uploader=str(info.get("uploader") or info.get("channel") or "").strip(),
        description=str(info.get("description") or ""),
        duration=float(info.get("duration") or 0.0),
        chapters=chapters,
    )


def download_as_mp3(
    url: str,
    out_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
    quality_kbps: int = 192,
    ffmpeg_location: str | Path | None = None,
) -> DownloadResult:
    """Download ``url`` into ``out_dir`` as an MP3 file and return the result.

    ``on_progress`` is called from yt-dlp's worker thread with download
    progress; do not touch Qt widgets directly from inside it.

    ``ffmpeg_location`` is forwarded to yt-dlp so its ``FFmpegExtractAudio``
    postprocessor can find ffmpeg/ffprobe in our bundled location instead of
    relying on ``PATH``. May be a directory containing both binaries or the
    path to ``ffmpeg`` itself; yt-dlp accepts either. When ``None``, yt-dlp
    falls back to ``shutil.which``.
    """
    # Imported lazily so the GUI starts even if yt_dlp has an import-time issue.
    from yt_dlp import YoutubeDL

    out_dir.mkdir(parents=True, exist_ok=True)

    def _hook(d: dict) -> None:
        if not on_progress:
            return
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            # Reserve the last 10% of the bar for the ffmpeg extraction step.
            on_progress(min(frac * 0.9, 0.9), "Downloading audio...")
        elif status == "finished":
            on_progress(0.9, "Extracting audio to MP3...")

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(title).200B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(quality_kbps),
            }
        ],
        # We'll write our own per-track tags later; don't let yt-dlp embed
        # video metadata as ID3 on the long file.
        "writethumbnail": False,
        "embedthumbnail": False,
    }
    if ffmpeg_location is not None:
        ydl_opts["ffmpeg_location"] = str(ffmpeg_location)

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # After the FFmpegExtractAudio postprocessor, the final file is the
        # `prepare_filename` output but with a .mp3 extension.
        produced = Path(ydl.prepare_filename(info)).with_suffix(".mp3")

    if not produced.exists():
        # As a fallback, scan for the most recently produced mp3 in out_dir.
        candidates = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError(
                f"yt-dlp did not produce an mp3 in {out_dir}. URL: {url}"
            )
        produced = candidates[-1]

    if on_progress:
        on_progress(1.0, "Download complete.")

    return DownloadResult(
        path=produced.resolve(),
        title=str(info.get("title") or produced.stem),
        duration=float(info.get("duration") or 0.0),
    )
