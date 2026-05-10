# Cross-platform convenience Makefile for mp3-yt-cutter.
#
# Targets:
#   make                Show this help (default)
#   make help           Show this help
#   make test           Run the test suite
#   make run            Launch the app (run.sh on Linux/macOS, run.bat on Windows)
#   make build          Build for the current host (alias for build-<HOST_OS>)
#   make build-linux    Build a self-contained Linux bundle  (must run on Linux)
#   make build-macos    Build a self-contained macOS .app    (must run on macOS)
#   make build-windows  Build a self-contained Windows .exe  (must run on Windows)
#
# Requires GNU Make. On Windows that means GNU Make from Git Bash, MSYS2,
# Scoop, or Chocolatey -- not Microsoft `nmake`.
#
# Notes:
#   * `make test` and `make run` both assume the project virtualenv is
#     already active so `python` resolves to the venv interpreter. See the
#     "Setup" section of the README for one-time environment setup.

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
.PHONY: help test run build build-linux build-macos build-windows

help:
	@echo "mp3-yt-cutter (host detected: $(HOST_OS))"
	@echo
	@echo "Targets:"
	@echo "  make test           Run pytest against tests/"
	@echo "  make run            Launch the app via the host's run script"
	@echo "  make build          Build for current host (alias for build-$(HOST_OS))"
	@echo "  make build-linux    Build a Linux bundle   (must run on Linux)"
	@echo "  make build-macos    Build a macOS .app     (must run on macOS)"
	@echo "  make build-windows  Build a Windows .exe   (must run on Windows)"

test:
	python -m pytest tests/ -q

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
