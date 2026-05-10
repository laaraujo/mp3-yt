# mp3-yt-cutter

A small cross-platform desktop app that splits a long MP3 (or a YouTube
video) into individually-tagged tracks based on a `mm:ss Title` tracklist.
Runs on **Windows**, **macOS**, and **Linux**.

- Two source modes: a **local MP3 file**, or a **YouTube URL** (downloads via `yt-dlp`).
- **Auto-detects** the tracklist from a YouTube video's chapters or description.
- **Lossless** cutting via `ffmpeg -c copy` — frame-accurate, near-instant.
- Writes ID3v2 tags (title, artist, album, track number) automatically.

## Install

Grab the latest build for your platform from the project's **Releases**
page. Each archive is fully self-contained — `ffmpeg` and `ffprobe` are
bundled, nothing else to install.

| Platform | File                                  | First-launch notes                                                              |
|----------|---------------------------------------|---------------------------------------------------------------------------------|
| Windows  | `mp3-yt-cutter-windows.zip`           | Unzip and double-click `mp3-yt-cutter.exe`.                                     |
| macOS    | `mp3-yt-cutter-macos-arm64.zip`       | Unzip the `.app`. The bundle is **unsigned**, so on first launch right-click → *Open*. |
| Linux    | `mp3-yt-cutter-linux-x86_64.tar.gz`   | Untar and run `./mp3-yt-cutter`.                                                |

## Use

1. Pick a source: **Local MP3 file** or **YouTube URL**.
   - On the YouTube tab, click *Fetch info from URL* to auto-fill the album,
     artist, and tracklist from the video's chapters or description.
2. Confirm/edit the album, artist, and tracklist.
3. Pick an output folder.
4. Click **Cut into tracks**.

### Tracklist format

One line per track: `mm:ss Title`. `H:MM:SS` works for 1+ hour videos.
Leading track numbers (`1.`, `01)`, `1 -`) and ` - ` separators are tolerated.

```
0:00 Emerald Hill Zone
3:01 Spring Yard Zone
1:23:45 A Long Bonus Track
```

The end of each track is the start of the next; the last track ends at the
end of the source file.

### Output

Files are written into your chosen folder as
`01 - Emerald Hill Zone.mp3`, `02 - Spring Yard Zone.mp3`, … each tagged
with `title`, `artist`, `album`, `albumartist`, and `tracknumber: N/Total`.

## Develop

Requires Python 3.10+ and `ffmpeg` on `PATH` (`brew install ffmpeg`,
`sudo apt install ffmpeg`, or `winget install Gyan.FFmpeg`).

One-time setup:

```bash
git clone <repo> mp3-yt-cutter
cd mp3-yt-cutter

python -m venv .venv
source .venv/bin/activate           # Linux / macOS / WSL
# .venv\Scripts\Activate.ps1        # Windows PowerShell

pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
pip install pytest                  # for `make test`
```

Then, with the venv active:

```bash
make            # list targets
make run        # launch the app
make test       # run the test suite
make build      # build a self-contained bundle for your current OS
```

The Makefile and `scripts/run.{sh,bat}` assume the venv is already
active — they don't manage it for you.

### Releases

Tags and releases are managed from GitHub itself — no `git tag` /
`git push --tags` needed.

1. On GitHub, go to **Releases** → *Draft a new release*.
2. Under *Choose a tag*, type a new tag (e.g. `v0.1.0`) and pick
   *Create new tag on publish*.
3. Fill in the title and notes, then click **Publish release**.

Publishing fires `.github/workflows/build-all.yml`, which builds Windows,
Linux, and macOS in parallel and uploads
`mp3-yt-cutter-windows.zip`, `mp3-yt-cutter-linux-x86_64.tar.gz`, and
`mp3-yt-cutter-macos-arm64.zip` to that release. The release page will
show the binaries a few minutes after publish.

To dry-run the builds without cutting a release, run *Build All* manually
from the **Actions** tab — the archives end up as run artifacts. To build
a single platform locally, see `scripts/build_linux.sh`,
`scripts/build_macos.sh`, or `scripts/build_windows.ps1`.

## License

MIT — see [LICENSE](LICENSE).
