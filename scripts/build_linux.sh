#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building Redakt for Linux ==="

cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo "Building with PyInstaller..."
pyinstaller \
    --name "Redakt" \
    --windowed \
    --onedir \
    --icon assets/icon.png \
    --add-data "assets:assets" \
    --hidden-import "redakt" \
    --hidden-import "redakt.core" \
    --hidden-import "redakt.parsers" \
    --hidden-import "redakt.ui" \
    --noconfirm \
    --clean \
    redakt/__main__.py

echo ""
echo "=== Build complete ==="
echo "App: dist/Redakt/Redakt"
