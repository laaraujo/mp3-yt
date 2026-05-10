# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for yt2mp3slicer.

The same spec is used on Windows, Linux and macOS:

* On **Windows** and **Linux** it produces a one-folder build at
  ``dist/yt2mp3slicer/`` containing the launcher binary plus an
  ``_internal/`` folder with Qt, Python, and bundled ffmpeg.
* On **macOS** it additionally wraps the result in a ``.app`` bundle at
  ``dist/yt2mp3slicer.app/``.

If ``build/ffmpeg-bin/`` exists and contains ``ffmpeg`` and ``ffprobe`` (or
their ``.exe`` counterparts), they're bundled into the app's ``bin/`` folder
so it's fully self-contained and never touches the user's ``PATH``. The
per-platform build scripts under ``build/`` populate that folder before
invoking PyInstaller.
"""

import sys
from pathlib import Path

# `SPECPATH` is set by PyInstaller and points at the directory containing this
# spec file (``<repo>/build``). We resolve everything relative to the repo root.
ROOT = Path(SPECPATH).parent

datas = [
    # Stylesheet must live next to the package so importlib.resources finds it.
    (str(ROOT / "slicer" / "ui" / "styles.qss"), "slicer/ui"),
]

binaries = []
ffmpeg_dir = ROOT / "build" / "ffmpeg-bin"
if ffmpeg_dir.is_dir():
    for name in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
        candidate = ffmpeg_dir / name
        if candidate.is_file():
            binaries.append((str(candidate), "bin"))

a = Analysis(
    [str(ROOT / "slicer" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # `tkinter` is pulled in by some optional yt-dlp dependencies but we don't
    # need it; excluding it shaves a few MB and skips a Tcl/Tk runtime.
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="yt2mp3slicer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # GUI app -> no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="yt2mp3slicer",
)

if sys.platform == "darwin":
    # On macOS, also wrap the COLLECTed folder in a proper .app bundle so
    # users can drag it into Applications and double-click to launch.
    app = BUNDLE(
        coll,
        name="yt2mp3slicer.app",
        icon=None,
        bundle_identifier="com.lautaro.yt2mp3slicer",
        info_plist={
            "CFBundleName": "YT → MP3 Slicer",
            "CFBundleDisplayName": "YT → MP3 Slicer",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # Avoid the system trying to assign us a default file association.
            "LSUIElement": False,
        },
    )
