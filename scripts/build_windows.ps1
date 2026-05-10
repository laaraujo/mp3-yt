<#
.SYNOPSIS
    Build a self-contained Windows .exe of yt2mp3slicer with PyInstaller.

.DESCRIPTION
    Output:
        dist/yt2mp3slicer/yt2mp3slicer.exe
        dist/yt2mp3slicer-windows.zip

.PARAMETER Clean
    Rebuild from scratch (removes dist/, build/build/, build/ffmpeg-bin/, .venv).

.EXAMPLE
    PS> .\scripts\build_windows.ps1
    PS> .\scripts\build_windows.ps1 -Clean

.NOTES
    Run from PowerShell on Windows (not WSL). Requires `uv` on PATH.
#>

[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
Write-Host "Repo root: $RepoRoot"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "'uv' was not found on PATH. Install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 127
}

if ($Clean) {
    Write-Host "Cleaning previous build artifacts..."
    foreach ($p in @("dist", "build/build", "build/ffmpeg-bin", ".venv")) {
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
}

Write-Host "Syncing build environment with uv..."
& uv sync --group build
if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE" }

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

    # SilentlyContinue makes Invoke-WebRequest much faster on big downloads.
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

Write-Host "Running PyInstaller..."
& uv run pyinstaller --noconfirm --clean `
    --workpath build/build `
    --distpath dist `
    build/yt2mp3slicer.spec

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

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
