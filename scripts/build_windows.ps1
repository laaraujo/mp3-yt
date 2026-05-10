<#
.SYNOPSIS
    Build a self-contained Windows .exe of yt2mp3slicer using PyInstaller.

.DESCRIPTION
    Sets up a venv (in `.venv-build`), installs runtime + build dependencies,
    downloads a static ffmpeg/ffprobe build from BtbN/FFmpeg-Builds (LGPL),
    runs PyInstaller against `build/yt2mp3slicer.spec`, and zips the result.

    Output:
        dist/yt2mp3slicer/yt2mp3slicer.exe         <- the actual app
        dist/yt2mp3slicer-windows.zip               <- shareable zip of the folder

.PARAMETER Clean
    Remove `dist/`, `build/build/`, `build/ffmpeg-bin/` and the build venv before
    building, forcing a from-scratch rebuild.

.EXAMPLE
    PS> .\build\build_windows.ps1
    PS> .\build\build_windows.ps1 -Clean

.NOTES
    Run this from PowerShell on **Windows**, not from inside WSL.
    Requires Python 3.10+ on PATH.
#>

[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# Always run from the repo root no matter where the script was invoked from.
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
Write-Host "Repo root: $RepoRoot"

if ($Clean) {
    Write-Host "Cleaning previous build artifacts..."
    foreach ($p in @("dist", "build/build", "build/ffmpeg-bin", ".venv-build")) {
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
}

# 1. Build venv ------------------------------------------------------------
$VenvDir = ".venv-build"
$Python = Join-Path $VenvDir "Scripts/python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating build virtualenv in $VenvDir ..."
    python -m venv $VenvDir
}

& $Python -m pip install --upgrade pip | Out-Null
& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller

# 2. Download static ffmpeg/ffprobe ---------------------------------------
$FfmpegBinDir = "build/ffmpeg-bin"
$NeedFfmpegDownload = -not (
    (Test-Path (Join-Path $FfmpegBinDir "ffmpeg.exe")) -and
    (Test-Path (Join-Path $FfmpegBinDir "ffprobe.exe"))
)

if ($NeedFfmpegDownload) {
    Write-Host "Downloading ffmpeg static build (BtbN, LGPL, win64)..."
    New-Item -ItemType Directory -Force -Path $FfmpegBinDir | Out-Null
    $Url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
    $Zip = "build/ffmpeg.zip"
    $Extract = "build/ffmpeg-extracted"

    # ProgressPreference SilentlyContinue makes Invoke-WebRequest much faster
    # for large downloads.
    $oldProgress = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Zip
    } finally {
        $ProgressPreference = $oldProgress
    }

    if (Test-Path $Extract) { Remove-Item -Recurse -Force $Extract }
    Expand-Archive -Path $Zip -DestinationPath $Extract -Force

    $FfmpegExe = Get-ChildItem -Path $Extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    if (-not $FfmpegExe) { throw "Could not find ffmpeg.exe in downloaded archive." }
    $FfprobeExe = Join-Path $FfmpegExe.Directory.FullName "ffprobe.exe"
    if (-not (Test-Path $FfprobeExe)) { throw "Could not find ffprobe.exe alongside ffmpeg.exe." }

    Copy-Item $FfmpegExe.FullName $FfmpegBinDir
    Copy-Item $FfprobeExe         $FfmpegBinDir

    Remove-Item $Zip
    Remove-Item -Recurse -Force $Extract
} else {
    Write-Host "Reusing existing $FfmpegBinDir"
}

# 3. PyInstaller ----------------------------------------------------------
Write-Host "Running PyInstaller..."
& $Python -m PyInstaller --noconfirm --clean `
    --workpath build/build `
    --distpath dist `
    build/yt2mp3slicer.spec

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

# 4. Zip for distribution -------------------------------------------------
$DistFolder = "dist/yt2mp3slicer"
$DistZip    = "dist/yt2mp3slicer-windows.zip"

if (-not (Test-Path "$DistFolder/yt2mp3slicer.exe")) {
    throw "Build did not produce $DistFolder/yt2mp3slicer.exe"
}

if (Test-Path $DistZip) { Remove-Item $DistZip }
Compress-Archive -Path "$DistFolder/*" -DestinationPath $DistZip

Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "  Folder: $DistFolder"
Write-Host "  Zip:    $DistZip"
Write-Host ""
Write-Host "Run it directly:  $DistFolder\yt2mp3slicer.exe"
