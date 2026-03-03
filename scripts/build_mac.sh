#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IDENTITY="Developer ID Application: Hasan Bora Ulukapi (BT5DCKAT25)"
APP="$PROJECT_DIR/dist/Redakt.app"
ZIP="$PROJECT_DIR/dist/Redakt-macOS-arm64.zip"

cd "$PROJECT_DIR"

echo "==> Building with PyInstaller..."
.venv/bin/pyinstaller Redakt.spec --noconfirm

echo "==> Code signing..."
codesign --deep --force --options runtime --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict "$APP"

echo "==> Creating zip for notarization..."
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

echo "==> Submitting for notarization (this takes 2-5 minutes)..."
xcrun notarytool submit "$ZIP" --keychain-profile "notarytool" --wait

echo "==> Stapling ticket..."
xcrun stapler staple "$APP"

echo "==> Re-creating final zip..."
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

echo ""
echo "Done! Signed + notarized build at:"
echo "  $ZIP"
echo ""
echo "To upload to GitHub release, run:"
echo "  gh release upload v0.x.x \"$ZIP\" --clobber"
