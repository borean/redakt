#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building QwenKK / DeIdentify for Linux ==="

cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo "Building with PyInstaller..."
pyinstaller \
    --name "DeIdentify" \
    --windowed \
    --onedir \
    --icon assets/icon.png \
    --add-data "assets:assets" \
    --hidden-import "qwenkk" \
    --hidden-import "qwenkk.core" \
    --hidden-import "qwenkk.parsers" \
    --hidden-import "qwenkk.ui" \
    --noconfirm \
    --clean \
    qwenkk/__main__.py

echo ""
echo "=== Build complete ==="
echo "App: dist/DeIdentify/DeIdentify"
