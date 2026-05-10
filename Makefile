# Cross-platform convenience Makefile for yt2mp3slicer.
#
# Targets:
#   make                Show this help (default)
#   make help           Show this help
#   make sync           uv sync (creates/updates .venv from uv.lock)
#   make test           Run the test suite (uv run pytest)
#   make run            Launch the app (run.sh on Linux/macOS, run.bat on Windows)
#   make build          Build for the current host (alias for build-<HOST_OS>)
#   make build-linux    Build a self-contained Linux bundle  (must run on Linux)
#   make build-macos    Build a self-contained macOS .app    (must run on macOS)
#   make build-windows  Build a self-contained Windows .exe  (must run on Windows)
#   make clean          Remove build artifacts and the local .venv
#

# --- Host OS detection ----------------------------------------------------

ifeq ($(OS),Windows_NT)
    HOST_OS := windows
    RUN_CMD := scripts/run.bat
else
    UNAME_S := $(shell uname -s)
    RUN_CMD := ./scripts/run.sh
    ifeq ($(UNAME_S),Darwin)
        HOST_OS := macos
    else
        HOST_OS := linux
    endif
endif

# --- Targets --------------------------------------------------------------

.DEFAULT_GOAL := help
.PHONY: help sync test run build build-linux build-macos build-windows clean

help:
	@echo "yt2mp3slicer (host detected: $(HOST_OS))"
	@echo
	@echo "Targets:"
	@echo "  make sync           uv sync — install/refresh runtime + dev deps"
	@echo "  make test           Run pytest against tests/"
	@echo "  make run            Launch the app via the host's run script"
	@echo "  make build          Build for current host (alias for build-$(HOST_OS))"
	@echo "  make build-linux    Build a Linux bundle   (must run on Linux)"
	@echo "  make build-macos    Build a macOS .app     (must run on macOS)"
	@echo "  make build-windows  Build a Windows .exe   (must run on Windows)"
	@echo "  make clean          Remove dist/, build/build/, and .venv"

sync:
	uv sync

test:
	uv run pytest -q

run:
	$(RUN_CMD)

# Convenience alias: `make build` -> the right per-platform target.
build: build-$(HOST_OS)

build-linux:
	./scripts/build_linux.sh

build-macos:
	./scripts/build_macos.sh

build-windows:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1

clean:
	rm -rf dist build/build build/ffmpeg-bin build/ffmpeg-extracted .venv
