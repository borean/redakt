@echo off
echo === Building Redakt for Windows ===

cd /d "%~dp0\.."

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -e ".[dev]" --quiet

echo Building .exe with PyInstaller...
pyinstaller ^
    --name "Redakt" ^
    --windowed ^
    --onedir ^
    --icon assets\icon.ico ^
    --add-data "assets;assets" ^
    --hidden-import "redakt" ^
    --hidden-import "redakt.core" ^
    --hidden-import "redakt.parsers" ^
    --hidden-import "redakt.ui" ^
    --noconfirm ^
    --clean ^
    redakt\__main__.py

echo.
echo === Build complete ===
echo App: dist\Redakt\Redakt.exe
