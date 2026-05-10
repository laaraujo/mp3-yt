"""Background worker that runs the full download/cut/tag pipeline.

The worker lives on its own ``QThread`` and communicates with the GUI via
signals so all filesystem and ffmpeg work happens off the GUI thread.
"""

from __future__ import annotations

import shutil
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from slicer.core import ffmpeg, tagger
from slicer.core.detect import detect_tracklist
from slicer.core.naming import safe_filename, track_filename
from slicer.core.tracklist import Track, TracklistError, parse_tracklist
from slicer.core.ytdownload import DownloadCancelledError, download_as_mp3


class MetadataWorker(QObject):
    """Fetches yt-dlp metadata and runs tracklist detection on a thread."""

    detected = Signal(object)  # DetectionResult
    failed = Signal(str)
    # Per-source progress strings (chapters → description → comments).
    statusChanged = Signal(str)

    def __init__(self, url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url

    @Slot()
    def run(self) -> None:
        try:
            result = detect_tracklist(
                self._url,
                on_status=self.statusChanged.emit,
            )
        except Exception as exc:
            # yt-dlp errors can be very long; collapse to the first line.
            msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            self.failed.emit(f"Could not fetch info for that URL: {msg}")
            return
        self.detected.emit(result)


@dataclass(frozen=True)
class CutJob:
    """All inputs needed to run one full cut pipeline."""

    youtube_url: str
    album: str
    artist: str
    tracklist_text: str
    output_dir: Path


class PipelineWorker(QObject):
    """Runs a :class:`CutJob` and emits progress / log / completion signals."""

    # fraction in [0, 1], status message
    progressChanged = Signal(float, str)
    # Live in-place line: "45%  •  12.4 MB / 27.5 MB  •  1.8 MB/s  •  ETA 0:08"
    progressDetail = Signal(str)
    # idx (1-based), total, title, ok, message
    trackFinished = Signal(int, int, str, bool, str)
    logLine = Signal(str)
    # success: bool, summary message
    finished = Signal(bool, str)

    def __init__(self, job: CutJob, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._cancelled = False

    @Slot()
    def cancel(self) -> None:
        """Mark the job for cancellation.

        The GUI calls this directly so it takes effect even while ``run`` is
        blocking the worker thread's Qt event loop. The yt-dlp progress hook
        checks the flag during download; cutting checks it between tracks.
        """
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:  # pragma: no cover - last-resort guard
            tb = traceback.format_exc()
            self.logLine.emit(tb)
            self.finished.emit(False, f"Unexpected error: {exc}")

    def _run_inner(self) -> None:
        job = self._job

        # Validate ffmpeg up-front so we fail fast with a clear message.
        try:
            bins = ffmpeg.find_binaries()
            ffmpeg_dir = Path(bins.ffmpeg).parent
            ffmpeg.configure_subprocess_environment(ffmpeg_dir)
            ffmpeg.ensure_binaries_runnable(bins)
        except ffmpeg.FfmpegNotFoundError as exc:
            self.finished.emit(False, str(exc))
            return

        try:
            tracks = parse_tracklist(job.tracklist_text)
        except TracklistError as exc:
            self.finished.emit(False, f"Tracklist error: {exc}")
            return

        tmp_dir = Path(tempfile.mkdtemp(prefix="yt2mp3slicer-"))
        try:
            self.logLine.emit(f"Downloading from YouTube to {tmp_dir} ...")

            def _ydl_progress(frac: float, msg: str) -> None:
                # Map yt-dlp's progress to the first ~15% of the overall bar.
                self.progressChanged.emit(min(frac * 0.15, 0.15), msg)

            def _ydl_progress_detail(text: str) -> None:
                self.progressDetail.emit(text)

            # Point yt-dlp at the same ffmpeg the cutter uses; otherwise it
            # falls back to PATH and fails inside frozen bundles.
            result = download_as_mp3(
                job.youtube_url,
                tmp_dir,
                on_progress=_ydl_progress,
                on_progress_detail=_ydl_progress_detail,
                cancel_requested=lambda: self._cancelled,
                ffmpeg_location=str(ffmpeg_dir),
            )
            if self._cancelled:
                self.finished.emit(False, "Cancelled.")
                return
            source_mp3 = result.path
            self.logLine.emit(f"Downloaded: {result.title} ({result.duration:.0f}s)")

            self._cut_all(tracks, source_mp3, bins)

        except DownloadCancelledError:
            self.finished.emit(False, "Cancelled.")
            return
        except Exception as exc:
            tb = traceback.format_exc()
            self.logLine.emit(tb)
            msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            self.finished.emit(False, f"Error: {msg}")
            return
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _cut_all(
        self,
        tracks: list[Track],
        source_mp3: Path,
        bins: ffmpeg.FfmpegBinaries,
    ) -> None:
        job = self._job

        try:
            total_duration = ffmpeg.probe_duration(source_mp3, bins=bins)
        except ffmpeg.FfmpegError as exc:
            self.finished.emit(False, str(exc))
            return

        if tracks[-1].start >= total_duration:
            self.finished.emit(
                False,
                (
                    f"Last track starts at {tracks[-1].start:.0f}s but the source "
                    f"is only {total_duration:.0f}s long. Check the tracklist."
                ),
            )
            return

        # Per-album subfolder so multiple cuts into the same chosen folder
        # stay tidy. The album name goes through the same sanitiser as track
        # titles. If somehow blank (the GUI requires it), write straight
        # into the chosen folder.
        album_subdir = safe_filename(job.album.strip()) if job.album.strip() else None
        album_folder = job.output_dir / album_subdir if album_subdir else job.output_dir
        album_folder.mkdir(parents=True, exist_ok=True)
        self.logLine.emit(f"Writing tracks to {album_folder}")

        n = len(tracks)
        ok_count = 0
        failed: list[str] = []

        for i, t in enumerate(tracks):
            if self._cancelled:
                self.finished.emit(False, "Cancelled.")
                return

            # Each track maps the remaining 85% of the bar evenly.
            frac_start = 0.15 + (i / n) * 0.85
            self.progressChanged.emit(frac_start, f"Cutting {i + 1}/{n}: {t.title}")

            end = tracks[i + 1].start if i + 1 < n else None
            dest = album_folder / track_filename(t.index, n, t.title)

            try:
                ffmpeg.cut_segment(source_mp3, dest, t.start, end, bins=bins)
                tagger.tag_track(
                    dest,
                    title=t.title,
                    artist=job.artist or "",
                    album=job.album or "",
                    track_number=t.index,
                    track_total=n,
                )
            except Exception as exc:
                msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
                failed.append(t.title)
                self.trackFinished.emit(t.index, n, t.title, False, msg)
                self.logLine.emit(f"FAILED: {t.title}: {msg}")
                continue

            ok_count += 1
            self.trackFinished.emit(t.index, n, t.title, True, str(dest))

        self.progressChanged.emit(1.0, "Done.")
        if failed:
            self.finished.emit(
                False,
                f"Finished with {len(failed)} failure(s): {', '.join(failed)}",
            )
        else:
            self.finished.emit(True, f"All {ok_count} tracks written to {album_folder}.")
