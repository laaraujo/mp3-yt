"""PySide6 main window and ``run_app`` entry point."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QTextOption
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
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mp3yt import __version__
from mp3yt.core.tracklist import format_tracks
from mp3yt.workers import CutJob, MetadataWorker, PipelineWorker, SourceKind


class MainWindow(QMainWindow):
    """The single window that drives the whole app."""

    # Cancel signal forwarded to the worker.
    requestCancel = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"mp3-yt-cutter {__version__}")
        self.resize(820, 760)

        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._meta_thread: QThread | None = None
        self._meta_worker: MetadataWorker | None = None

        self._build_ui()

    # ---- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(objectName="centralWidget")
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Header
        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("MP3 / YouTube Cutter", objectName="titleLabel")
        subtitle = QLabel(
            "Split a long MP3 (or a YouTube video) into individually-tagged tracks "
            "from a pasted tracklist.",
            objectName="subtitleLabel",
        )
        subtitle.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        # Source group (tabbed: Local file / YouTube URL)
        root.addWidget(self._build_source_group())

        # Album / artist
        meta_box = QGroupBox("Album info")
        meta_layout = QFormLayout(meta_box)
        meta_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.album_edit = QLineEdit(placeholderText="e.g. Sonic the Hedgehog 2 OST")
        self.artist_edit = QLineEdit(placeholderText="e.g. Masato Nakamura")
        meta_layout.addRow(self._field_label("Album / disk:"), self.album_edit)
        meta_layout.addRow(self._field_label("Artist:"), self.artist_edit)
        root.addWidget(meta_box)

        # Tracklist
        tl_box = QGroupBox("Tracklist  (one line per track: 'mm:ss Title')")
        tl_layout = QVBoxLayout(tl_box)
        self.tracklist_edit = QPlainTextEdit()
        self.tracklist_edit.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.tracklist_edit.setPlaceholderText(
            "0:00 Emerald Hill Zone\n"
            "3:01 Spring Yard Zone\n"
            "5:32 Green Hill Zone\n"
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
        browse_out = QPushButton("Browse…")
        browse_out.clicked.connect(self._pick_output_dir)
        out_layout.addWidget(self.output_edit, stretch=1)
        out_layout.addWidget(browse_out)
        root.addWidget(out_box)

        # Action row
        actions = QHBoxLayout()
        self.cut_button = QPushButton("Cut into tracks", objectName="primaryButton")
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

        # Per-track results list
        self.results = QListWidget()
        self.results.setMinimumHeight(140)
        self.results.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.results, stretch=1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

    def _build_source_group(self) -> QGroupBox:
        box = QGroupBox("Source")
        layout = QVBoxLayout(box)
        self.source_tabs = QTabWidget()

        # --- Local file tab ---
        local_tab = QWidget()
        local_layout = QHBoxLayout(local_tab)
        self.local_path_edit = QLineEdit(
            placeholderText="Path to a long MP3 file (full album, podcast, set, ...)"
        )
        browse_local = QPushButton("Browse…")
        browse_local.clicked.connect(self._pick_local_file)
        local_layout.addWidget(self.local_path_edit, stretch=1)
        local_layout.addWidget(browse_local)
        self.source_tabs.addTab(local_tab, "Local MP3 file")

        # --- YouTube tab ---
        yt_tab = QWidget()
        yt_layout = QVBoxLayout(yt_tab)
        url_row = QHBoxLayout()
        self.yt_url_edit = QLineEdit(
            placeholderText="https://www.youtube.com/watch?v=..."
        )
        self.yt_fetch_button = QPushButton("Fetch info from URL")
        self.yt_fetch_button.setToolTip(
            "Read the video's chapters / description and auto-fill the album, "
            "artist and tracklist below."
        )
        self.yt_fetch_button.clicked.connect(self._on_fetch_clicked)
        url_row.addWidget(self.yt_url_edit, stretch=1)
        url_row.addWidget(self.yt_fetch_button)
        yt_layout.addLayout(url_row)

        yt_hint = QLabel(
            "Paste a YouTube URL, then click <b>Fetch info from URL</b> to "
            "auto-detect the tracklist from the video's chapters or description. "
            "The full audio is only downloaded when you press <b>Cut into "
            "tracks</b>."
        )
        yt_hint.setWordWrap(True)
        yt_hint.setObjectName("subtitleLabel")
        yt_layout.addWidget(yt_hint)
        self.source_tabs.addTab(yt_tab, "YouTube URL")

        layout.addWidget(self.source_tabs)
        return box

    @staticmethod
    def _field_label(text: str) -> QLabel:
        # The "class" property pairs with the `QLabel.fieldLabel` selector in
        # styles.qss to give field labels a slightly muted, semi-bold look.
        lbl = QLabel(text)
        lbl.setProperty("class", "fieldLabel")
        return lbl

    # ---- file/folder pickers --------------------------------------------

    def _pick_local_file(self) -> None:
        start_dir = self.local_path_edit.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a source MP3 file",
            start_dir,
            "Audio files (*.mp3 *.m4a *.aac *.flac *.wav *.opus *.ogg);;All files (*)",
        )
        if path:
            self.local_path_edit.setText(path)

    def _pick_output_dir(self) -> None:
        start_dir = self.output_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "Choose output folder", start_dir
        )
        if path:
            self.output_edit.setText(path)

    # ---- main action -----------------------------------------------------

    def _on_cut_clicked(self) -> None:
        if self._thread is not None:
            return  # already running

        # Gather inputs
        is_youtube = self.source_tabs.currentIndex() == 1
        if is_youtube:
            value = self.yt_url_edit.text().strip()
            kind = SourceKind.YOUTUBE
            if not value:
                self._error("Please paste a YouTube URL.")
                return
        else:
            value = self.local_path_edit.text().strip()
            kind = SourceKind.LOCAL
            if not value:
                self._error("Please choose a source MP3 file.")
                return
            if not Path(value).expanduser().is_file():
                self._error(f"File not found:\n{value}")
                return

        album = self.album_edit.text().strip()
        artist = self.artist_edit.text().strip()
        tracklist_text = self.tracklist_edit.toPlainText()
        output_dir_str = self.output_edit.text().strip()

        if not album:
            self._error("Please enter an album / disk name.")
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

        # Reset UI state
        self.results.clear()
        self.progress.setValue(0)

        job = CutJob(
            source_kind=kind,
            source_value=value,
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
        self._worker.trackFinished.connect(self._on_track_finished)
        self._worker.logLine.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self.requestCancel.connect(self._worker.cancel)

        self._set_running(True)
        self._thread.start()

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None:
            self.statusBar().showMessage("Cancelling after current track…")
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

        self._set_fetching(True)
        self.statusBar().showMessage("Fetching video info…")

        self._meta_thread = QThread(self)
        self._meta_worker = MetadataWorker(url)
        self._meta_worker.moveToThread(self._meta_thread)
        self._meta_thread.started.connect(self._meta_worker.run)
        self._meta_worker.detected.connect(self._on_metadata_detected)
        self._meta_worker.failed.connect(self._on_metadata_failed)
        self._meta_worker.detected.connect(self._meta_thread.quit)
        self._meta_worker.failed.connect(self._meta_thread.quit)
        self._meta_thread.finished.connect(self._teardown_meta_thread)
        self._meta_thread.start()

    def _on_metadata_detected(self, result) -> None:  # DetectionResult
        # Only fill empty fields so we never clobber what the user already typed.
        meta = result.metadata
        if not self.album_edit.text().strip():
            self.album_edit.setText(result.guessed_album or meta.title)
        if not self.artist_edit.text().strip():
            self.artist_edit.setText(result.guessed_artist or meta.uploader)

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

            origin = (
                "video chapters" if result.source == "chapters"
                else "video description"
            )
            self.statusBar().showMessage(
                f"Detected {len(result.tracks)} tracks from {origin}."
            )
        else:
            self.statusBar().showMessage(
                "No tracklist detected in chapters or description — paste one manually."
            )
            QMessageBox.information(
                self,
                "No tracklist found",
                "This video has no chapters and no recognizable timestamps in "
                "its description. Paste a tracklist manually below.",
            )

    def _on_metadata_failed(self, msg: str) -> None:
        self.statusBar().showMessage(msg)
        QMessageBox.warning(self, "Fetch failed", msg)

    def _teardown_meta_thread(self) -> None:
        if self._meta_thread is not None:
            self._meta_thread.wait(2000)
            self._meta_thread.deleteLater()
            self._meta_thread = None
        self._meta_worker = None
        self._set_fetching(False)

    # ---- worker signal handlers -----------------------------------------

    def _on_progress(self, frac: float, msg: str) -> None:
        frac = max(0.0, min(1.0, frac))
        self.progress.setValue(round(frac * 1000))
        self.statusBar().showMessage(msg)

    def _on_track_finished(
        self, idx: int, total: int, title: str, ok: bool, msg: str
    ) -> None:
        marker = "OK " if ok else "FAIL"
        item = QListWidgetItem(f"[{idx:02d}/{total:02d}] {marker}  {title}")
        if not ok:
            item.setToolTip(msg)
            item.setForeground(Qt.GlobalColor.red)
        else:
            item.setToolTip(msg)
        self.results.addItem(item)
        self.results.scrollToBottom()

    def _append_log(self, text: str) -> None:
        # Currently funneled into the status bar; could grow into a real log
        # pane later.
        for line in text.splitlines() or [text]:
            self.statusBar().showMessage(line)

    def _on_finished(self, ok: bool, msg: str) -> None:
        self._set_running(False)
        self.statusBar().showMessage(msg)
        if ok:
            QMessageBox.information(self, "Done", msg)
        else:
            QMessageBox.warning(self, "Finished with issues", msg)
        self._teardown_thread()

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None

    # ---- helpers ---------------------------------------------------------

    def _set_running(self, running: bool) -> None:
        self.cut_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.yt_fetch_button.setEnabled(not running)
        for w in (
            self.local_path_edit,
            self.yt_url_edit,
            self.album_edit,
            self.artist_edit,
            self.tracklist_edit,
            self.output_edit,
            self.source_tabs,
        ):
            w.setEnabled(not running)

    def _set_fetching(self, fetching: bool) -> None:
        self.yt_fetch_button.setEnabled(not fetching)
        self.yt_fetch_button.setText(
            "Fetching…" if fetching else "Fetch info from URL"
        )
        self.cut_button.setEnabled(not fetching)

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


def _load_stylesheet() -> str:
    try:
        return resources.files("mp3yt.ui").joinpath("styles.qss").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return ""


def run_app(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName("mp3-yt-cutter")
    app.setApplicationDisplayName("MP3 / YouTube Cutter")
    app.setOrganizationName("mp3yt")

    qss = _load_stylesheet()
    if qss:
        app.setStyleSheet(qss)

    # No bundled icon yet; the OS falls back to a generic window icon.
    icon = QIcon.fromTheme("multimedia-audio-player")
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    window.show()
    return app.exec()
