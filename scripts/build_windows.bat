@echo off
echo === Building QwenKK / DeIdentify for Windows ===

cd /d "%~dp0\.."

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -e ".[dev]" --quiet

echo Building .exe with PyInstaller...
pyinstaller ^
    --name "DeIdentify" ^
    --windowed ^
    --onedir ^
    --icon assets\icon.ico ^
    --add-data "assets;assets" ^
    --hidden-import "qwenkk" ^
    --hidden-import "qwenkk.core" ^
    --hidden-import "qwenkk.parsers" ^
    --hidden-import "qwenkk.ui" ^
    --noconfirm ^
    --clean ^
    qwenkk\__main__.py

echo.
echo === Build complete ===
echo App: dist\DeIdentify\DeIdentify.exe
