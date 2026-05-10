# yt2mp3slicer

A small cross-platform desktop app that downloads a YouTube
video — typically a full-album upload, DJ mix, or OST compilation — and
splits its audio into individually-tagged MP3 tracks based on a
`mm:ss Title` tracklist. Runs on **Windows**, **macOS**, and **Linux**.

> **Looking to grab a single song as MP3?** This isn't the right tool.
> yt2mp3slicer's whole purpose is to *slice* one long video into many
> tagged tracks. If you just want to download a single video as one MP3
> file, any of the dozens of free online "YouTube to MP3" converters
> will do that in one click — no install required.

- Downloads via `yt-dlp` and cuts the audio losslessly (`ffmpeg -c copy`).
- **Auto-detects** the tracklist from the video's chapters, description,
  or top comments.
- Writes ID3v2 tags (title, artist, album, track number) automatically.

## Install

Grab the latest build for your platform from the project's **Releases**
page. Each archive is fully self-contained — `ffmpeg` and `ffprobe` are
bundled, nothing else to install.

| Platform | File                                  | First-launch notes                                                              |
|----------|---------------------------------------|---------------------------------------------------------------------------------|
| Windows  | `yt2mp3slicer-windows.zip`           | Unzip and double-click `yt2mp3slicer.exe`.                                     |
| macOS    | `yt2mp3slicer-macos-arm64.zip`       | Unzip the `.app`. The bundle is **unsigned**, so on first launch right-click → *Open*. |
| Linux    | `yt2mp3slicer-linux-x86_64.tar.gz`   | Untar and run `./yt2mp3slicer`.                                                |

## Use

1. Paste a YouTube URL.
2. Click *Fetch info* to auto-fill the album, artist, and tracklist
   from the video's chapters, description, or top comments.
3. Confirm/edit the album, artist, and tracklist.
4. Pick an output folder.
5. Click **Cut and download**.

### Tracklist format

One line per track: `mm:ss Title`. `H:MM:SS` works for 1+ hour videos.
Leading track numbers (`1.`, `01)`, `1 -`) and ` - ` separators are tolerated.

```
0:00 Intro
3:01 Sunrise
1:23:45 A Long Bonus Track
```

The end of each track is the start of the next; the last track ends at the
end of the source file.

### Output

Inside your chosen folder, the app creates a subfolder named after the
album (for example `Echoes of Tomorrow/`) and writes the cuts there as
`01 - Intro.mp3`, `02 - Sunrise.mp3`, … each tagged with `title`, `artist`,
`album`, `albumartist`, and `tracknumber: N/Total`. This keeps multiple
albums tidy when you reuse the same output folder.

## Develop

Project setup is managed by [**uv**](https://docs.astral.sh/uv/) — a
single fast tool that handles the Python interpreter, the virtualenv,
and locked dependencies. You also need `ffmpeg` on `PATH` for local runs
(`brew install ffmpeg`, `sudo apt install ffmpeg`, or
`winget install Gyan.FFmpeg`); the bundled releases ship their own copy.

One-time setup:

```bash
# 1. Install uv (skip if you already have it).
curl -LsSf https://astral.sh/uv/install.sh | sh        # Linux / macOS / WSL
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
# (or: brew install uv, winget install astral-sh.uv, etc.)

# 2. Clone and install pinned deps.
git clone <repo> yt2mp3slicer
cd yt2mp3slicer
uv sync           # creates .venv from uv.lock (Python + runtime + dev deps)
```

Day-to-day:

```bash
make             # list targets
make run         # launch the app  (uv run python -m slicer)
make test        # run the test suite  (uv run pytest -q)
make build       # build a self-contained bundle for your current OS
```

`uv run` (and the `make` targets that wrap it) automatically
creates/refreshes `.venv` from `uv.lock`, so there's no virtualenv to
activate manually. Adding or upgrading a dependency is a single
`uv add <pkg>` (or `uv add --group dev <pkg>` for tooling); commit the
updated `pyproject.toml` and `uv.lock` together.

### Releases

Tags and releases are managed from GitHub itself — no `git tag` /
`git push --tags` needed.

1. On GitHub, go to **Releases** → *Draft a new release*.
2. Under *Choose a tag*, type a new tag (e.g. `v0.1.0`) and pick
   *Create new tag on publish*.
3. Fill in the title and notes, then click **Publish release**.

Publishing fires `.github/workflows/build-all.yml`, which builds Windows,
Linux, and macOS in parallel and uploads
`yt2mp3slicer-windows.zip`, `yt2mp3slicer-linux-x86_64.tar.gz`, and
`yt2mp3slicer-macos-arm64.zip` to that release. The release page will
show the binaries a few minutes after publish.

To dry-run the builds without cutting a release, run *Build All* manually
from the **Actions** tab — the archives end up as run artifacts. To build
a single platform locally, see `scripts/build_linux.sh`,
`scripts/build_macos.sh`, or `scripts/build_windows.ps1`.

## License

MIT — see [LICENSE](LICENSE).
