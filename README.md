# mp3-yt-cutter

A small cross-platform desktop app that cuts a single long MP3 (e.g. a full
album rip or a YouTube video) into individual, properly-tagged tracks based on
a pasted tracklist of `mm:ss Title` lines.

Built with **Python + PySide6 (Qt 6)**. No Electron. Native window, modern look,
runs on **Windows**, **macOS**, **Linux**, and **WSL** (via WSLg).

## Features

- Two input sources:
  - **Local MP3 file** — point at a file on disk.
  - **YouTube URL** — downloads as MP3 with `yt-dlp` + `ffmpeg`, then cuts.
- Tracklist parser that accepts `M:SS`, `MM:SS`, and `H:MM:SS` timestamps,
  with optional leading track numbers like `1.`, `01)`, or `1 -`.
- Lossless cutting via `ffmpeg -c copy` (no re-encoding, near-instant).
- Automatic ID3v2 tagging: title, artist, album, track number / track total.
- Background worker thread with progress bar and per-track log.

## Requirements

- **Python 3.10+** (developed on 3.12).
- **ffmpeg** and **ffprobe** on `PATH`.
  - Linux: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: install from <https://www.gyan.dev/ffmpeg/builds/> and add `bin/`
    to `PATH`, or `winget install Gyan.FFmpeg`.

## Setup

```bash
git clone <repo> mp3-yt-cutter
cd mp3-yt-cutter

python -m venv .venv
# Linux / macOS / WSL:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install -e .
```

The last line installs this project in editable mode so `python -m mp3yt`
can find the package; the convenience launchers below do this automatically.

## Run

```bash
# from the project root, with the venv active:
python -m mp3yt
```

Or use the convenience launchers:

- Linux / WSL / macOS: `./scripts/run.sh`
- Windows: `scripts\run.bat`

## Tracklist format

Paste lines of the form:

```
0:00 Emerald Hill Zone
3:01 Spring Yard Zone
5:32 Green Hill Zone
8:24 Chemical Plant Zone
1:23:45 A Long Bonus Track
```

Accepted timestamp shapes: `M:SS`, `MM:SS`, `H:MM:SS`. Leading track numbers
(`1.`, `01)`, `1 -`) are tolerated and stripped. Blank lines are ignored.

The end of each track is the start of the next; the last track ends at the
end of the source file.

## Output

Files are written into the chosen output folder as:

```
01 - Emerald Hill Zone.mp3
02 - Spring Yard Zone.mp3
...
```

Each file is tagged with `title`, `artist`, `album`, `tracknumber` (`N/Total`).

## Building self-contained desktop apps

The repo ships everything needed to produce one-folder builds for Windows,
Linux, and macOS. Each build contains the GUI **and** a static `ffmpeg` /
`ffprobe` (or their `.exe` counterparts) — users just run the launcher,
nothing else to install.

> PyInstaller does not cross-compile. Each platform's build has to run **on
> that platform** (locally or via the matching CI runner).

### Build matrix

| Target  | Local script                  | GitHub Actions                          | Output                                       |
|---------|-------------------------------|-----------------------------------------|----------------------------------------------|
| Windows | `scripts\build_windows.ps1`   | `.github/workflows/build-windows.yml`   | `dist\mp3-yt-cutter\mp3-yt-cutter.exe` + zip |
| Linux   | `scripts/build_linux.sh`      | `.github/workflows/build-linux.yml`     | `dist/mp3-yt-cutter/mp3-yt-cutter` + tar.gz  |
| macOS   | `scripts/build_macos.sh`      | `.github/workflows/build-macos.yml`     | `dist/mp3-yt-cutter.app` + zip               |

All three scripts call the same `build/mp3-yt-cutter.spec`, which knows how
to emit a `.app` bundle on macOS and a plain folder elsewhere. The `build/`
folder holds the build machinery (the spec and the downloaded ffmpeg
binaries); the user-facing entry points all live under `scripts/`.

### Local builds

```bash
# Windows (PowerShell, on the Windows host — not WSL)
.\scripts\build_windows.ps1          # add -Clean to rebuild from scratch

# Linux (any distro with python3 + curl + tar)
./scripts/build_linux.sh             # --clean to rebuild from scratch

# macOS (requires Homebrew)
./scripts/build_macos.sh             # --clean to rebuild from scratch
```

Each script:

1. Sets up `.venv-build/` and installs runtime + build deps.
2. Acquires `ffmpeg` / `ffprobe`:
   - **Windows / Linux**: downloads a [BtbN LGPL static
     build](https://github.com/BtbN/FFmpeg-Builds/releases/latest) into
     `build/ffmpeg-bin/`.
   - **macOS**: copies them from Homebrew. PyInstaller follows their dylib
     dependencies and pulls the supporting libs into the `.app`'s
     `Frameworks/` folder.
3. Runs PyInstaller against `build/mp3-yt-cutter.spec`.
4. Produces a shareable archive next to the unpacked build.

### CI builds (GitHub Actions)

Four workflows in `.github/workflows/`:

| Workflow | Triggers | What it does |
|----------|----------|--------------|
| `build-all.yml`     | `workflow_dispatch`, `push: tags: v*` | **Recommended entry point.** Fans out to the three platform workflows in parallel, then (on tag push) creates a single GitHub Release with all three artifacts attached. |
| `build-windows.yml` | `workflow_dispatch`, `workflow_call`  | `windows-latest` → `mp3-yt-cutter-windows.zip` |
| `build-linux.yml`   | `workflow_dispatch`, `workflow_call`  | `ubuntu-22.04` (broad glibc baseline) → `mp3-yt-cutter-linux-x86_64.tar.gz` |
| `build-macos.yml`   | `workflow_dispatch`, `workflow_call`  | `macos-latest` (Apple Silicon, **unsigned**) → `mp3-yt-cutter-macos-arm64.zip` |

The per-platform workflows are **reusable** (`workflow_call`); the
orchestrator calls them with `uses: ./.github/workflows/build-X.yml`. They
also remain individually triggerable from the Actions tab when you want to
test a single platform without paying for the other two runners.

To produce a release:

```bash
git tag v0.1.0
git push --tags
```

The `Build All` workflow runs the three builds in parallel (~5–10 min total),
then a final `release` job downloads all three artifacts and publishes a
GitHub Release tagged `v0.1.0` with `mp3-yt-cutter-windows.zip`,
`mp3-yt-cutter-linux-x86_64.tar.gz`, and `mp3-yt-cutter-macos-<arch>.zip`
attached.

Each runner does a smoke-test launch with `QT_QPA_PLATFORM=offscreen`
(or `minimal` on Windows) before publishing its artifact, so a broken build
never silently ships.

### How the bundle finds ffmpeg

`mp3yt.core.ffmpeg.find_binaries()` looks in this order:

1. The directory pointed at by the `MP3YT_FFMPEG_DIR` env var (handy for
   portable installs and tests).
2. The PyInstaller bundle (`sys._MEIPASS/bin`, then next to the launcher).
3. `PATH` via `shutil.which` (the dev path on a normal venv).

The same source code runs from a venv on Linux/WSL **and** as a packaged
binary on any of the three platforms with zero changes.

### Platform-specific notes

- **Linux**: built on `ubuntu-22.04` to keep glibc compatibility broad. The
  workflow installs Qt's runtime xcb dependencies (`libxkbcommon0`, `libxcb-*`)
  on the build host so PyInstaller can locate them; the resulting bundle
  ships its own copies, so end users on most modern distros don't need to
  install anything extra. On very minimal distros, install
  `libxcb-cursor0 libxkbcommon-x11-0` if the bundle won't start.
- **macOS**: the `.app` is **unsigned and unnotarized**. On first launch
  Gatekeeper will block it; users either right-click → *Open* once, or run
  `xattr -d com.apple.quarantine /path/to/mp3-yt-cutter.app`. Code-signing +
  notarization can be added to the workflow later when an Apple Developer
  ID is available. The CI build is **arm64-only** (Apple Silicon); Intel
  Mac users would need a `macos-13` matrix entry.
- **Windows**: console window is suppressed (`console=False` in the spec).
  The GHA workflow's smoke test uses `QT_QPA_PLATFORM=minimal`.

## License

MIT.
