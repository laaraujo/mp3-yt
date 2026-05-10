"""Download a YouTube (or any yt-dlp-supported) URL as a single MP3 file.

Audio extraction goes through yt-dlp's ``FFmpegExtractAudio`` postprocessor.
That postprocessor finds ffmpeg via ``shutil.which`` by default, which
breaks inside frozen .app bundles where PATH is minimal — so callers should
pass ``ffmpeg_location`` pointing at the bundled binaries.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


# Player clients yt-dlp should try when talking to YouTube. The default
# anonymous clients are increasingly hit by the "Sign in to confirm you're
# not a bot" challenge; ``android`` slips past it in most cases and returns
# playable formats. The rest are fallbacks for the day ``android`` breaks.
_PREFERRED_YT_PLAYER_CLIENTS: tuple[str, ...] = (
    "android",
    "ios",
    "mweb",
    "tv_simply",
    "web_safari",
)


def _apply_anti_bot(opts: dict) -> None:
    """Nudge yt-dlp toward player clients that aren't routinely PoT-challenged.

    No-op for non-YouTube URLs because ``extractor_args`` is namespaced.
    """
    existing = opts.get("extractor_args") or {}
    yt_args = dict(existing.get("youtube") or {})
    # Don't clobber an explicit caller-provided player_client.
    yt_args.setdefault("player_client", list(_PREFERRED_YT_PLAYER_CLIENTS))
    opts["extractor_args"] = {**existing, "youtube": yt_args}


@dataclass(frozen=True)
class DownloadResult:
    path: Path           # absolute path to the produced .mp3
    title: str
    duration: float      # seconds


@dataclass(frozen=True)
class Chapter:
    """A single YouTube chapter as exposed by yt-dlp."""

    start_time: float
    end_time: float
    title: str


@dataclass(frozen=True)
class VideoMetadata:
    """Subset of yt-dlp's info dict we care about."""

    title: str
    uploader: str
    description: str
    duration: float
    chapters: list[Chapter]


@dataclass(frozen=True)
class Comment:
    """A single top-level YouTube comment."""

    text: str
    author: str
    like_count: int


ProgressCallback = Callable[[float, str], None]
"""Receives (fraction in [0, 1], status message)."""

ProgressDetailCallback = Callable[[str], None]
"""Receives a single live progress line, e.g.
``'45.0%  •  12.4 MB / 27.5 MB  •  1.8 MB/s  •  ETA 0:08'``.

Throttled here to ~4×/s so the UI doesn't get hammered."""


def _human_bytes(n: float) -> str:
    """Format ``n`` bytes as a short human-readable string."""
    n = max(0.0, float(n))
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _format_eta(seconds: int | float) -> str:
    """Format an ETA in seconds as ``M:SS`` or ``H:MM:SS``."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_download_progress(d: dict) -> str:
    """Build the live progress string from yt-dlp's hook dict.

    Skips segments that aren't computable yet (no total / no speed / no ETA)
    rather than printing ``None``.
    """
    downloaded = float(d.get("downloaded_bytes") or 0)
    total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
    speed = d.get("speed")
    eta = d.get("eta")

    parts: list[str] = []
    if total > 0:
        pct = (downloaded / total) * 100
        parts.append(f"{pct:5.1f}%")
        parts.append(f"{_human_bytes(downloaded)} / {_human_bytes(total)}")
    else:
        parts.append(_human_bytes(downloaded))

    if speed:
        parts.append(f"{_human_bytes(speed)}/s")
    if eta is not None:
        parts.append(f"ETA {_format_eta(eta)}")

    return "  •  ".join(parts)


def fetch_metadata(url: str) -> VideoMetadata:
    """Resolve a URL to its video metadata without downloading the audio.

    Cheap (sub-second on a healthy connection). Raises whatever yt-dlp
    raises so the caller can surface a friendly error.
    """
    from yt_dlp import YoutubeDL

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    _apply_anti_bot(opts)
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


def fetch_top_comments(url: str, *, limit: int = 10) -> list[Comment]:
    """Return up to ``limit`` top-level comments, sorted by like count.

    yt-dlp's ``getcomments`` walks every thread by default, which is slow on
    popular videos. We cap retrieval via ``max_comments`` and skip replies
    so the call stays under a couple of seconds.

    Never raises: returns ``[]`` on any yt-dlp error.
    """
    from yt_dlp import YoutubeDL

    cap = max(1, limit)
    # max_comments format (per yt-dlp wiki):
    #   total / top-level / replies-per-top / threads-to-fetch-replies-from
    # Asking for a few more than ``limit`` gives the post-sort some headroom.
    pool = cap * 2
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "getcomments": True,
        "extractor_args": {
            "youtube": {
                "max_comments": [f"{pool},{pool},0,{pool}"],
                "comment_sort": ["top"],
            }
        },
    }
    _apply_anti_bot(opts)

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return []

    raw = info.get("comments") or []
    comments: list[Comment] = []
    for c in raw:
        # Top-level only; yt-dlp marks replies with a non-"root" parent id.
        if c.get("parent") not in (None, "", "root"):
            continue
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        try:
            likes = int(c.get("like_count") or 0)
        except (TypeError, ValueError):
            likes = 0
        comments.append(
            Comment(
                text=text,
                author=str(c.get("author") or "").strip(),
                like_count=likes,
            )
        )

    comments.sort(key=lambda c: c.like_count, reverse=True)
    return comments[:cap]


def download_as_mp3(
    url: str,
    out_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
    on_progress_detail: ProgressDetailCallback | None = None,
    quality_kbps: int = 192,
    ffmpeg_location: str | Path | None = None,
) -> DownloadResult:
    """Download ``url`` into ``out_dir`` as an MP3 file.

    ``on_progress`` and ``on_progress_detail`` fire from yt-dlp's worker
    thread; the caller must marshal back to the GUI thread. Detail
    callbacks are throttled to ~4×/s.

    ``ffmpeg_location`` is forwarded to yt-dlp so its ``FFmpegExtractAudio``
    postprocessor can find ffmpeg in our bundled location instead of PATH.
    """
    # Lazy import so the GUI starts even if yt_dlp has an import-time issue.
    from yt_dlp import YoutubeDL

    out_dir.mkdir(parents=True, exist_ok=True)

    # Throttle the detail callback — the hook fires on every network read.
    detail_state = {"last_emit": 0.0}
    detail_min_interval_s = 0.25

    def _hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            # Reserve the last 10% of the bar for ffmpeg extraction.
            if on_progress:
                on_progress(min(frac * 0.9, 0.9), "Downloading audio...")
            if on_progress_detail:
                now = time.monotonic()
                if now - detail_state["last_emit"] >= detail_min_interval_s:
                    detail_state["last_emit"] = now
                    on_progress_detail(_format_download_progress(d))
        elif status == "finished":
            if on_progress:
                on_progress(0.9, "Extracting audio to MP3...")

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(title).200B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        # We render our own progress; suppress yt-dlp's console line.
        "noprogress": True,
        "progress_hooks": [_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(quality_kbps),
            }
        ],
        # We tag per-track later; don't let yt-dlp embed video metadata.
        "writethumbnail": False,
        "embedthumbnail": False,
    }
    if ffmpeg_location is not None:
        ydl_opts["ffmpeg_location"] = str(ffmpeg_location)
    _apply_anti_bot(ydl_opts)

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # After FFmpegExtractAudio the final file is `prepare_filename` with .mp3.
        produced = Path(ydl.prepare_filename(info)).with_suffix(".mp3")

    if not produced.exists():
        # Fallback: use the most recently produced mp3 in out_dir.
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
