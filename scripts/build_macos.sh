#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building Redakt for macOS ==="

cd "$PROJECT_DIR"

# Ensure venv
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo "Building .app bundle with PyInstaller..."
pyinstaller Redakt.spec --noconfirm --clean

echo ""
echo "=== Build complete ==="
echo "App: dist/Redakt.app"
echo ""

# Create DMG if create-dmg is available
if command -v create-dmg &> /dev/null; then
    echo "Creating DMG..."
    create-dmg \
        --volname "Redakt" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon "Redakt.app" 150 185 \
        --app-drop-link 450 185 \
        "dist/Redakt.dmg" \
        "dist/Redakt.app"
    echo "DMG: dist/Redakt.dmg"
else
    echo "Tip: Install create-dmg for DMG packaging:"
    echo "  brew install create-dmg"
fi
