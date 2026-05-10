"""PySide6 main window and ``run_app`` entry point."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QColor, QIcon, QTextOption
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from slicer import __version__
from slicer.core.tracklist import format_tracks
from slicer.core.youtube_url import is_shorts_url, youtube_video_id
from slicer.workers import CutJob, MetadataWorker, PipelineWorker

# Severity → foreground color for the Messages list.
MessageKind = Literal["info", "success", "warning", "error"]
_MESSAGE_COLORS: dict[str, QColor] = {
    "info":    QColor("#c5c9da"),
    "success": QColor("#4ade80"),
    "warning": QColor("#facc15"),
    "error":   QColor("#f87171"),
}

# QSettings key for the last-used output folder. Kept in a module-level
# constant so we can't typo it in two different places.
_SETTINGS_OUTPUT_DIR = "output/last_dir"


class MainWindow(QMainWindow):
    """The single window that drives the whole app."""

    # Cancel signal forwarded to the worker.
    requestCancel = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"yt2mp3slicer {__version__}")
        self.resize(820, 760)

        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._meta_thread: QThread | None = None
        self._meta_worker: MetadataWorker | None = None
        # Used to dedupe the "Downloading audio…" / "Cutting N/M…" phase
        # strings that yt-dlp's progress hook emits on every byte tick.
        self._last_progress_msg: str | None = None
        # The QListWidgetItem currently being updated in place by the live
        # download-progress line. ``None`` means "no live line right now —
        # the next live tick should append a fresh item". Cleared by every
        # non-live ``_append_message`` so the live line never overwrites
        # phase headers, log entries or per-track outcomes.
        self._live_message_item: QListWidgetItem | None = None
        # Video titles we've seen from a successful "Fetch info",
        # keyed by the URL string. Used to decorate the "Starting cut job
        # for …" message so the user has a friendly identifier instead of a
        # raw URL. Falls back to the URL when we haven't fetched.
        self._titles_by_url: dict[str, str] = {}
        # Tracks whether the URL field currently holds a valid YouTube video
        # URL. Updated from ``_on_url_changed`` and consumed by
        # ``_refresh_form_state`` to gate the rest of the form.
        self._url_is_valid: bool = False

        self._build_ui()
        self._restore_output_dir()
        # Apply the initial enabled/disabled state now that all widgets exist
        # (no URL → everything but the URL field starts disabled).
        self._refresh_form_state()

    # ---- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Header
        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("YouTube → MP3 Slicer")
        subtitle = QLabel(
            "Split a YouTube video into individually-tagged MP3 tracks "
            "from a pasted tracklist.",
        )
        subtitle.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        root.addWidget(self._build_source_group())

        # Album / artist
        meta_box = QGroupBox("Album info")
        meta_layout = QFormLayout(meta_box)
        meta_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.album_edit = QLineEdit(placeholderText="e.g. Echoes of Tomorrow")
        self.artist_edit = QLineEdit(placeholderText="e.g. Anna Rivers")
        meta_layout.addRow(self._field_label("Album:"), self.album_edit)
        meta_layout.addRow(self._field_label("Artist:"), self.artist_edit)
        root.addWidget(meta_box)

        # Tracklist
        tl_box = QGroupBox("Tracklist  (one line per track: 'mm:ss Title')")
        tl_layout = QVBoxLayout(tl_box)
        self.tracklist_edit = QPlainTextEdit()
        self.tracklist_edit.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.tracklist_edit.setPlaceholderText(
            "0:00 Intro\n"
            "3:01 Sunrise\n"
            "5:32 Departure\n"
            "..."
        )
        self.tracklist_edit.setMinimumHeight(180)
        tl_layout.addWidget(self.tracklist_edit)
        root.addWidget(tl_box, stretch=1)

        # Output folder
        out_box = QGroupBox("Output folder")
        out_layout = QHBoxLayout(out_box)
        self.output_edit = QLineEdit(
            placeholderText="Where the individual track MP3s will be written"
        )
        # Persist whatever the user types once they tab/click away — covers
        # paths typed in directly without using the Browse button.
        self.output_edit.editingFinished.connect(self._persist_output_dir)
        self.browse_out_button = QPushButton("Browse…")
        self.browse_out_button.clicked.connect(self._pick_output_dir)
        out_layout.addWidget(self.output_edit, stretch=1)
        out_layout.addWidget(self.browse_out_button)
        root.addWidget(out_box)

        # Action row
        actions = QHBoxLayout()
        self.cut_button = QPushButton("Cut and download")
        self.cut_button.clicked.connect(self._on_cut_clicked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        actions.addWidget(self.cut_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        root.addLayout(actions)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)  # finer granularity than 0..100
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        root.addWidget(self.progress)

        # Messages / activity log. Replaces what used to live in the status
        # bar: download progress phases, per-track outcomes, fetch lifecycle,
        # cancellation and completion summaries — all in one scrollable list.
        msg_box = QGroupBox("Messages")
        msg_layout = QVBoxLayout(msg_box)
        self.messages = QListWidget()
        self.messages.setMinimumHeight(160)
        self.messages.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # Backwards-compatible alias: older handlers used ``self.results``.
        self.results = self.messages
        msg_layout.addWidget(self.messages)
        root.addWidget(msg_box, stretch=1)

        self.setCentralWidget(central)

    def _build_source_group(self) -> QGroupBox:
        box = QGroupBox("YouTube URL")
        layout = QVBoxLayout(box)

        url_row = QHBoxLayout()
        self.yt_url_edit = QLineEdit(
            placeholderText="https://www.youtube.com/watch?v=..."
        )
        # Re-validate on every keystroke so the rest of the form follows
        # along — fields stay disabled until a recognisable video URL is in.
        self.yt_url_edit.textChanged.connect(self._on_url_changed)
        self.yt_fetch_button = QPushButton("Fetch info")
        self.yt_fetch_button.setToolTip(
            "Read the video's chapters / description and auto-fill the album, "
            "artist and tracklist below."
        )
        self.yt_fetch_button.clicked.connect(self._on_fetch_clicked)
        url_row.addWidget(self.yt_url_edit, stretch=1)
        url_row.addWidget(self.yt_fetch_button)
        layout.addLayout(url_row)

        # Inline validation message for the URL field. Hidden by default;
        # shown in red when the user has typed something that doesn't parse
        # as a supported video URL (e.g. a Shorts link or a channel page).
        self.url_error_label = QLabel("")
        self.url_error_label.setObjectName("urlErrorLabel")
        self.url_error_label.setWordWrap(True)
        self.url_error_label.setStyleSheet("color: #f87171;")
        self.url_error_label.hide()
        layout.addWidget(self.url_error_label)

        hint = QLabel(
            "<ol style='margin: 0; padding-left: 20px;'>"
            "<li>Paste a YouTube URL above.</li>"
            "<li>Click <b>Fetch info</b> to auto-detect the "
            "tracklist from the video's chapters, description, or top comments.</li>"
            "<li>Press <b>Cut and download</b> to fetch the full audio and "
            "save the tagged tracks.</li>"
            "</ol>"
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(hint)

        return box

    @staticmethod
    def _field_label(text: str) -> QLabel:
        return QLabel(text)

    # ---- file/folder pickers --------------------------------------------

    def _pick_output_dir(self) -> None:
        start_dir = self.output_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "Choose output folder", start_dir
        )
        if path:
            self.output_edit.setText(path)
            # Save immediately on picker selection — picking a folder is an
            # explicit user choice, no reason to wait for ``editingFinished``.
            self._persist_output_dir()

    # ---- output-folder persistence --------------------------------------

    def _restore_output_dir(self) -> None:
        """Pre-fill the output field with the last-used folder, if any."""
        saved = QSettings().value(_SETTINGS_OUTPUT_DIR, "", type=str)
        if saved:
            # Restore even if the path no longer exists on disk; the existing
            # validation in ``_on_cut_clicked`` will tell the user clearly,
            # and a stale path still serves as a useful "you used this last
            # time" hint they can edit.
            self.output_edit.setText(saved)

    def _persist_output_dir(self) -> None:
        """Save the current output-folder text to QSettings if non-empty."""
        text = self.output_edit.text().strip()
        if not text:
            return
        QSettings().setValue(_SETTINGS_OUTPUT_DIR, text)

    # ---- main action -----------------------------------------------------

    def _on_cut_clicked(self) -> None:
        if self._thread is not None:
            return  # already running

        url = self.yt_url_edit.text().strip()
        album = self.album_edit.text().strip()
        artist = self.artist_edit.text().strip()
        tracklist_text = self.tracklist_edit.toPlainText()
        output_dir_str = self.output_edit.text().strip()

        if not url:
            self._error("Please paste a YouTube URL.")
            return
        if not album:
            self._error("Please enter an album name.")
            return
        if not artist:
            self._error("Please enter an artist.")
            return
        if not tracklist_text.strip():
            self._error("Please paste a tracklist.")
            return
        if not output_dir_str:
            self._error("Please choose an output folder.")
            return

        output_dir = Path(output_dir_str).expanduser()

        # Persist now in case the user typed the path in directly and clicked
        # Cut without ever losing focus on the line edit.
        self._persist_output_dir()

        self.messages.clear()
        self._last_progress_msg = None
        self._live_message_item = None
        self.progress.setValue(0)
        # Prefer the cached video title (from a previous Fetch) for a
        # human-friendly identifier; fall back to the raw URL otherwise so
        # the message always says "for <something>".
        title = self._titles_by_url.get(url)
        descriptor = f'"{title}"' if title else url
        self._append_message(f"Starting cut job for {descriptor}…")

        job = CutJob(
            youtube_url=url,
            album=album,
            artist=artist,
            tracklist_text=tracklist_text,
            output_dir=output_dir,
        )

        # Spin up worker thread
        self._thread = QThread(self)
        self._worker = PipelineWorker(job)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progressChanged.connect(self._on_progress)
        # Live in-place download progress (%/size/speed/ETA).
        self._worker.progressDetail.connect(self._update_live_message)
        self._worker.trackFinished.connect(self._on_track_finished)
        self._worker.logLine.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self.requestCancel.connect(self._worker.cancel)

        self._refresh_form_state()
        self._thread.start()

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None:
            self._append_message(
                "Cancelling after current track…", kind="warning"
            )
            self.cancel_button.setEnabled(False)
            self.requestCancel.emit()

    # ---- YouTube info fetch ---------------------------------------------

    def _on_fetch_clicked(self) -> None:
        if self._meta_thread is not None:
            return  # already fetching

        url = self.yt_url_edit.text().strip()
        if not url:
            self._error("Paste a YouTube URL first.")
            return

        self._last_progress_msg = None
        self._live_message_item = None
        self._append_message("Fetching video info…")

        self._meta_thread = QThread(self)
        self._meta_worker = MetadataWorker(url)
        self._meta_worker.moveToThread(self._meta_thread)
        self._meta_thread.started.connect(self._meta_worker.run)
        self._meta_worker.detected.connect(self._on_metadata_detected)
        self._meta_worker.failed.connect(self._on_metadata_failed)
        # Per-source "Trying to get tracklist from …" updates from detect.py.
        self._meta_worker.statusChanged.connect(self._append_message)
        self._meta_worker.detected.connect(self._meta_thread.quit)
        self._meta_worker.failed.connect(self._meta_thread.quit)
        self._meta_thread.finished.connect(self._teardown_meta_thread)
        self._refresh_form_state()
        self._meta_thread.start()

    def _on_metadata_detected(self, result) -> None:  # DetectionResult
        # Only fill empty fields so we never clobber what the user already typed.
        meta = result.metadata
        if not self.album_edit.text().strip():
            self.album_edit.setText(result.guessed_album or meta.title)
        if not self.artist_edit.text().strip():
            self.artist_edit.setText(result.guessed_artist or meta.uploader)

        # Cache the title so the upcoming "Starting cut job for …" message
        # has a friendly identifier instead of just the URL.
        url_at_fetch = self.yt_url_edit.text().strip()
        if meta.title and url_at_fetch:
            self._titles_by_url[url_at_fetch] = meta.title

        if result.tracks:
            tracklist_text = format_tracks(result.tracks)
            existing = self.tracklist_edit.toPlainText().strip()
            if existing:
                # Don't overwrite: ask before replacing.
                resp = QMessageBox.question(
                    self,
                    "Replace tracklist?",
                    f"Detected {len(result.tracks)} tracks from the video's "
                    f"{result.source}. Replace your current tracklist with them?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if resp == QMessageBox.StandardButton.Yes:
                    self.tracklist_edit.setPlainText(tracklist_text)
            else:
                self.tracklist_edit.setPlainText(tracklist_text)

            self._append_message(
                f"Loaded {len(result.tracks)} tracks into the tracklist.",
                kind="success",
            )
        else:
            self._append_message(
                "No tracklist detected in chapters, description or top "
                "comments — paste one manually.",
                kind="warning",
            )
            QMessageBox.information(
                self,
                "No tracklist found",
                "This video has no chapters and no recognizable timestamps "
                "in its description or top comments. Paste a tracklist "
                "manually below.",
            )

    def _on_metadata_failed(self, msg: str) -> None:
        self._append_message(msg, kind="error")
        QMessageBox.warning(self, "Fetch failed", msg)

    def _teardown_meta_thread(self) -> None:
        if self._meta_thread is not None:
            self._meta_thread.wait(2000)
            self._meta_thread.deleteLater()
            self._meta_thread = None
        self._meta_worker = None
        self._refresh_form_state()

    # ---- messages list ---------------------------------------------------

    def _messages_at_bottom(self) -> bool:
        """True if the messages list is currently scrolled to the bottom.

        Used to keep auto-scroll polite: if the user has scrolled up to read
        an earlier message we don't yank them back down on every live tick.
        Two-pixel slack swallows rounding errors from style-sheet padding.
        """
        bar = self.messages.verticalScrollBar()
        return bar.value() >= bar.maximum() - 2

    def _append_message(
        self,
        text: str,
        *,
        kind: MessageKind = "info",
        tooltip: str = "",
    ) -> None:
        """Append a timestamped, colour-coded line to the Messages list."""
        was_at_bottom = self._messages_at_bottom()
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{timestamp}]  {text}")
        item.setForeground(_MESSAGE_COLORS.get(kind, _MESSAGE_COLORS["info"]))
        if tooltip:
            item.setToolTip(tooltip)
        self.messages.addItem(item)
        # Any normal append ends the current "live line" run, so the next
        # in-place update will create a fresh item below this one rather
        # than overwriting a phase header / outcome / log entry.
        self._live_message_item = None
        if was_at_bottom:
            self.messages.scrollToBottom()

    def _update_live_message(self, text: str) -> None:
        """Update the current live progress line in place, or create one.

        Used by the download-progress hook to render ``%``/size/speed/ETA
        without flooding the list — every tick refreshes the same item
        instead of appending a new one.
        """
        was_at_bottom = self._messages_at_bottom()
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}]  {text}"
        if self._live_message_item is None:
            item = QListWidgetItem(formatted)
            item.setForeground(_MESSAGE_COLORS["info"])
            self.messages.addItem(item)
            self._live_message_item = item
        else:
            self._live_message_item.setText(formatted)
        if was_at_bottom:
            self.messages.scrollToBottom()

    # ---- worker signal handlers -----------------------------------------

    def _on_progress(self, frac: float, msg: str) -> None:
        frac = max(0.0, min(1.0, frac))
        self.progress.setValue(round(frac * 1000))
        # Progress hooks fire on every byte tick, so only log when the human
        # readable phase string actually changes.
        if msg and msg != self._last_progress_msg:
            self._last_progress_msg = msg
            self._append_message(msg)

    def _on_track_finished(
        self, idx: int, total: int, title: str, ok: bool, msg: str
    ) -> None:
        marker = "OK  " if ok else "FAIL"
        text = f"[{idx:02d}/{total:02d}] {marker}  {title}"
        self._append_message(
            text,
            kind="success" if ok else "error",
            tooltip=msg,
        )

    def _append_log(self, text: str) -> None:
        for line in text.splitlines() or [text]:
            line = line.rstrip()
            if line:
                self._append_message(line)

    def _on_finished(self, ok: bool, msg: str) -> None:
        # Tear down the worker thread first so ``self._thread`` is cleared,
        # then refresh form state so the modal below opens against an
        # already-re-enabled form.
        self._teardown_thread()
        self._refresh_form_state()
        self._append_message(msg, kind="success" if ok else "error")
        if ok:
            QMessageBox.information(self, "Done", msg)
        else:
            QMessageBox.warning(self, "Finished with issues", msg)

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None

    # ---- helpers ---------------------------------------------------------

    def _on_url_changed(self, text: str) -> None:
        """Re-validate the URL field on every keystroke."""
        text = text.strip()
        self.url_error_label.hide()
        self.url_error_label.setText("")

        if not text:
            # Empty isn't an error per se — just disables downstream fields.
            self._url_is_valid = False
        elif is_shorts_url(text):
            self._url_is_valid = False
            self.url_error_label.setText(
                "YouTube Shorts aren't supported — paste a regular video URL."
            )
            self.url_error_label.show()
        elif youtube_video_id(text) is None:
            self._url_is_valid = False
            self.url_error_label.setText(
                "That doesn't look like a YouTube video URL "
                "(expected youtube.com/watch?v=… or youtu.be/…)."
            )
            self.url_error_label.show()
        else:
            self._url_is_valid = True

        self._refresh_form_state()

    def _refresh_form_state(self) -> None:
        """Single source of truth for which controls are enabled.

        Three independent inputs decide widget state:

        * ``self._url_is_valid`` — set by :meth:`_on_url_changed`.
        * ``self._thread is not None`` — a cut pipeline is running.
        * ``self._meta_thread is not None`` — a metadata fetch is running.
        """
        cutting = self._thread is not None
        fetching = self._meta_thread is not None
        busy = cutting or fetching
        can_edit_form = self._url_is_valid and not busy

        # The URL field is the one input that's editable except while busy
        # — users still need to be able to change it before fetching/cutting.
        self.yt_url_edit.setEnabled(not busy)

        # Fetching needs a valid URL and idle workers.
        self.yt_fetch_button.setEnabled(self._url_is_valid and not busy)
        self.yt_fetch_button.setText(
            "Fetching…" if fetching else "Fetch info"
        )

        # Everything downstream of the URL is gated behind a valid URL too.
        for w in (
            self.album_edit,
            self.artist_edit,
            self.tracklist_edit,
            self.output_edit,
            self.browse_out_button,
        ):
            w.setEnabled(can_edit_form)

        self.cut_button.setEnabled(can_edit_form and not cutting)
        self.cancel_button.setEnabled(cutting)

    def _error(self, msg: str) -> None:
        QMessageBox.warning(self, "Missing input", msg)

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            if self._worker is not None:
                self._worker.cancel()
            self._thread.quit()
            self._thread.wait(2000)
        if self._meta_thread is not None and self._meta_thread.isRunning():
            self._meta_thread.quit()
            self._meta_thread.wait(2000)
        super().closeEvent(event)


# --- entry point ---------------------------------------------------------


def run_app(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName("yt2mp3slicer")
    app.setApplicationDisplayName("YouTube → MP3 Slicer")
    app.setOrganizationName("yt2mp3slicer")

    # No bundled icon yet; the OS falls back to a generic window icon.
    icon = QIcon.fromTheme("multimedia-audio-player")
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    window.show()
    return app.exec()
