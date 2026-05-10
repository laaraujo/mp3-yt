# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for yt2mp3slicer.

Produces a one-folder build at ``dist/yt2mp3slicer/``; on macOS also wraps
it as ``dist/yt2mp3slicer.app``. If ``build/ffmpeg-bin/`` contains
ffmpeg/ffprobe (populated by the per-platform build scripts), they're
bundled into the app's ``bin/`` folder so it's fully self-contained.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

datas = []
try:
    import certifi
except ImportError:
    pass
else:
    datas.append((certifi.where(), "certifi"))

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
    # Pulled in by some optional yt-dlp deps; we don't need them.
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
    console=False,
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
    app = BUNDLE(
        coll,
        name="yt2mp3slicer.app",
        icon=None,
        bundle_identifier="com.lautaro.yt2mp3slicer",
        info_plist={
            "CFBundleName": "YouTube → MP3 Slicer",
            "CFBundleDisplayName": "YouTube → MP3 Slicer",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSUIElement": False,
        },
    )
