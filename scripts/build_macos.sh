#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building QwenKK / DeIdentify for macOS ==="

cd "$PROJECT_DIR"

# Ensure venv
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo "Building .app bundle with PyInstaller..."
pyinstaller \
    --name "DeIdentify" \
    --windowed \
    --onedir \
    --icon assets/icon.icns \
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
echo "App: dist/DeIdentify.app"
echo ""

# Create DMG if create-dmg is available
if command -v create-dmg &> /dev/null; then
    echo "Creating DMG..."
    create-dmg \
        --volname "DeIdentify" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon "DeIdentify.app" 150 185 \
        --app-drop-link 450 185 \
        "dist/DeIdentify.dmg" \
        "dist/DeIdentify.app"
    echo "DMG: dist/DeIdentify.dmg"
else
    echo "Tip: Install create-dmg for DMG packaging:"
    echo "  brew install create-dmg"
fi
