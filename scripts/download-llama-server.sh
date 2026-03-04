#!/bin/bash
set -euo pipefail

# Downloads the correct platform-specific llama-server binary from
# llama.cpp GitHub releases and places it in src-tauri/binaries/
# with the Tauri target-triple naming convention.

LLAMA_VERSION="b8196"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BINARIES_DIR="$PROJECT_DIR/redakt-tauri/src-tauri/binaries"

# Detect platform
OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}-${ARCH}" in
    Darwin-arm64)
        ARCHIVE="llama-${LLAMA_VERSION}-bin-macos-arm64.tar.gz"
        TARGET_TRIPLE="aarch64-apple-darwin"
        ;;
    Darwin-x86_64)
        ARCHIVE="llama-${LLAMA_VERSION}-bin-macos-x64.tar.gz"
        TARGET_TRIPLE="x86_64-apple-darwin"
        ;;
    Linux-x86_64)
        ARCHIVE="llama-${LLAMA_VERSION}-bin-ubuntu-x64.tar.gz"
        TARGET_TRIPLE="x86_64-unknown-linux-gnu"
        ;;
    MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64)
        ARCHIVE="llama-${LLAMA_VERSION}-bin-win-cpu-x64.zip"
        TARGET_TRIPLE="x86_64-pc-windows-msvc"
        ;;
    *)
        echo "ERROR: Unsupported platform: ${OS}-${ARCH}"
        exit 1
        ;;
esac

DOWNLOAD_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_VERSION}/${ARCHIVE}"

if [[ "$TARGET_TRIPLE" == *"windows"* ]]; then
    DEST_NAME="llama-server-${TARGET_TRIPLE}.exe"
    BINARY_NAME="llama-server.exe"
else
    DEST_NAME="llama-server-${TARGET_TRIPLE}"
    BINARY_NAME="llama-server"
fi

DEST_PATH="$BINARIES_DIR/$DEST_NAME"

# Skip if already exists
if [ -f "$DEST_PATH" ]; then
    echo "Already exists: $DEST_PATH ($(du -h "$DEST_PATH" | cut -f1))"
    echo "Delete it to re-download."
    exit 0
fi

echo "Platform:    ${OS} ${ARCH} (${TARGET_TRIPLE})"
echo "Downloading: ${DOWNLOAD_URL}"

mkdir -p "$BINARIES_DIR"

TMPDIR="$(mktemp -d)"
trap "rm -rf $TMPDIR" EXIT

# Download
curl -L --fail --progress-bar -o "$TMPDIR/$ARCHIVE" "$DOWNLOAD_URL"

# Extract
cd "$TMPDIR"
if [[ "$ARCHIVE" == *.tar.gz ]]; then
    tar xzf "$ARCHIVE"
elif [[ "$ARCHIVE" == *.zip ]]; then
    unzip -q "$ARCHIVE"
fi

# Find llama-server binary
FOUND=$(find . -name "$BINARY_NAME" -type f | head -1)
if [ -z "$FOUND" ]; then
    echo "ERROR: $BINARY_NAME not found in archive"
    echo "Archive contents:"
    find . -type f | head -20
    exit 1
fi

cp "$FOUND" "$DEST_PATH"
chmod +x "$DEST_PATH"

echo "Installed: $DEST_PATH ($(du -h "$DEST_PATH" | cut -f1))"
