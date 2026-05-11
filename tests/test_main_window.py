"""Regression tests for main-window metadata autofill behavior."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slicer.core.detect import DetectionResult
from slicer.core.ytdownload import VideoMetadata
from slicer.ui import main_window
from slicer.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _disable_metadata_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *args, **kwargs: None)


def _result(
    *,
    title: str,
    uploader: str,
    guessed_album: str | None = None,
    guessed_artist: str | None = None,
) -> DetectionResult:
    return DetectionResult(
        source=None,
        tracks=[],
        metadata=VideoMetadata(
            title=title,
            uploader=uploader,
            description="",
            duration=120.0,
            chapters=[],
        ),
        guessed_artist=guessed_artist,
        guessed_album=guessed_album,
    )


def test_fetching_same_url_preserves_manual_album_and_artist(qapp: QApplication) -> None:
    window = MainWindow()
    try:
        url = "https://www.youtube.com/watch?v=zcYVH4fYCkg"
        window.yt_url_edit.setText(url)
        window._on_metadata_detected(
            _result(
                title="Original Title",
                uploader="Original Uploader",
                guessed_album="Detected Album",
                guessed_artist="Detected Artist",
            )
        )

        window.album_edit.setText("Manual Album")
        window.artist_edit.setText("Manual Artist")
        window._on_metadata_detected(
            _result(
                title="Updated Title",
                uploader="Updated Uploader",
                guessed_album="Updated Album",
                guessed_artist="Updated Artist",
            )
        )

        assert window.album_edit.text() == "Manual Album"
        assert window.artist_edit.text() == "Manual Artist"
    finally:
        window.close()


def test_fetching_new_url_replaces_previous_album_and_artist(qapp: QApplication) -> None:
    window = MainWindow()
    try:
        first_url = "https://www.youtube.com/watch?v=zcYVH4fYCkg"
        window.yt_url_edit.setText(first_url)
        window._on_metadata_detected(
            _result(
                title="First Title",
                uploader="First Uploader",
                guessed_album="First Album",
                guessed_artist="First Artist",
            )
        )

        second_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        window.yt_url_edit.setText(second_url)
        window._on_metadata_detected(
            _result(
                title="Second Title",
                uploader="Second Uploader",
                guessed_album="Second Album",
                guessed_artist="Second Artist",
            )
        )

        assert window.album_edit.text() == "Second Album"
        assert window.artist_edit.text() == "Second Artist"
    finally:
        window.close()


def test_track_result_updates_cutting_status_message(qapp: QApplication) -> None:
    window = MainWindow()
    try:
        window._on_progress(0.5, "Cutting 1/2: Intro")

        assert window.messages.count() == 1
        assert "[01/02] CUT   Intro" in window.messages.item(0).text()

        window._on_track_finished(1, 2, "Intro", True, "/tmp/Intro.mp3")

        assert window.messages.count() == 1
        assert "[01/02] OK    Intro" in window.messages.item(0).text()
        assert window.messages.item(0).toolTip() == "/tmp/Intro.mp3"
    finally:
        window.close()
