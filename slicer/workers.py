"""Background worker that runs the full download/cut/tag pipeline.

The worker lives on its own ``QThread`` and communicates with the GUI via
signals. All filesystem and ffmpeg work happens off the GUI thread so the
window stays responsive.
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
from slicer.core.naming import track_filename
from slicer.core.tracklist import Track, TracklistError, parse_tracklist


class MetadataWorker(QObject):
    """Fetches yt-dlp metadata and runs tracklist detection on a thread."""

    # Emitted with the final result on success.
    detected = Signal(object)  # DetectionResult
    # Emitted with a friendly error message on failure.
    failed = Signal(str)

    def __init__(self, url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url

    @Slot()
    def run(self) -> None:
        try:
            result = detect_tracklist(self._url)
        except Exception as exc:
            # Most yt-dlp errors are quite verbose; collapse to first line.
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
    # idx (1-based), total, title, ok, message
    trackFinished = Signal(int, int, str, bool, str)
    # general log line
    logLine = Signal(str)
    # success: bool, summary message
    finished = Signal(bool, str)

    def __init__(self, job: CutJob, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._cancelled = False

    @Slot()
    def cancel(self) -> None:
        """Mark the job for cancellation. Takes effect between tracks."""
        self._cancelled = True

    # ---- main entry ------------------------------------------------------

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

        # 1. Validate ffmpeg up-front so we fail fast with a clear message.
        try:
            bins = ffmpeg.find_binaries()
        except ffmpeg.FfmpegNotFoundError as exc:
            self.finished.emit(False, str(exc))
            return

        # 2. Parse the tracklist.
        try:
            tracks = parse_tracklist(job.tracklist_text)
        except TracklistError as exc:
            self.finished.emit(False, f"Tracklist error: {exc}")
            return

        # 3. Download the YouTube audio to a scratch directory.
        tmp_dir = Path(tempfile.mkdtemp(prefix="yt2mp3slicer-"))
        try:
            self.logLine.emit(f"Downloading from YouTube to {tmp_dir} ...")
            from slicer.core.ytdownload import download_as_mp3

            def _ydl_progress(frac: float, msg: str) -> None:
                # Map yt-dlp progress to the first ~15% of the overall bar.
                self.progressChanged.emit(min(frac * 0.15, 0.15), msg)

            # Point yt-dlp's FFmpegExtractAudio postprocessor at the same
            # binaries the cutter uses; otherwise it falls back to PATH and
            # fails inside frozen .app/.exe bundles where PATH is minimal.
            result = download_as_mp3(
                job.youtube_url,
                tmp_dir,
                on_progress=_ydl_progress,
                ffmpeg_location=str(Path(bins.ffmpeg).parent),
            )
            source_mp3 = result.path
            self.logLine.emit(
                f"Downloaded: {result.title} ({result.duration:.0f}s)"
            )

            self._cut_all(tracks, source_mp3, bins)

        except Exception as exc:
            tb = traceback.format_exc()
            self.logLine.emit(tb)
            self.finished.emit(False, f"Error: {exc}")
            return
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---- cutting ---------------------------------------------------------

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

        # Sanity-check: the last track's start must be before the file ends.
        if tracks[-1].start >= total_duration:
            self.finished.emit(
                False,
                (
                    f"Last track starts at {tracks[-1].start:.0f}s but the source "
                    f"is only {total_duration:.0f}s long. Check the tracklist."
                ),
            )
            return

        job.output_dir.mkdir(parents=True, exist_ok=True)

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
            dest = job.output_dir / track_filename(t.index, n, t.title)

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
            self.finished.emit(True, f"All {ok_count} tracks written to {job.output_dir}.")
