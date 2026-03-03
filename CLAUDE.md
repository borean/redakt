# Redakt — Development Guide

## What is this?
Redakt is a **local** medical document de-identification desktop app. It detects and redacts PII (names, dates, IDs, addresses, etc.) from medical documents using a local LLM — no cloud, no internet required after initial model download.

**Stack**: Python 3.14 · PySide6 (Qt) · llama.cpp · Qwen3.5 (3B GGUF) · PyInstaller

## Project Layout

```
redakt/
  __main__.py          # Entry point
  app.py               # QApplication setup, window icon, theme init
  constants.py         # App name, supported extensions, Language enum
  core/
    anonymizer.py      # PII detection engine (LLM + regex), date parsing, age conversion
    entities.py        # PIIEntity, PIIResponse dataclasses
    llamacpp_manager.py # llama-server process lifecycle & HTTP inference
    prompts.py         # System/user prompts for TR and EN
    redactor.py        # Text highlighting, redaction rendering, CATEGORY_COLORS
    md_renderer.py     # Markdown export of redacted documents
  ui/
    main_window.py     # Main application window (~1500 lines)
    i18n.py            # All UI strings: t(key, lang) → TR/EN translations
    status_bar.py      # Status bar: Ready/Processing/Error + "100% LOCAL" badge
    settings_dialog.py # Settings (theme, language, model path)
    setup_wizard.py    # First-run setup wizard
    theme.py           # ThemeManager with dark/light mode support
  parsers/             # PDF, DOCX, image text extraction
  api/                 # REST API for programmatic access
assets/
  icon.png             # App icon (used for window/taskbar)
  icon.icns            # macOS app bundle icon
  icon.ico             # Windows app icon
manifesto/             # Marketing website (deployed via Vercel)
  index.html           # Single-page site with download links
tests/
  test_age_conversion.py  # Main test suite (100+ tests)
Redakt.spec            # PyInstaller build spec
```

## Key Patterns

### i18n
All UI strings go through `t(key, lang)` from `redakt/ui/i18n.py`. Never hardcode English strings in UI code. The `Language` enum is in `constants.py` (EN, TR).

### PII Detection Pipeline
1. LLM inference via llama.cpp HTTP API (structured JSON output)
2. Post-LLM regex supplement (catches TC Kimlik 11-digit IDs the LLM misses)
3. Age conversion: 4-strategy cascade to find birth date, then converts dates to patient age

### Date Parsing
`Anonymizer._parse_date()` handles 10+ formats including:
- Standard: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD
- Turkish text: "15 Ocak 2024"
- Standalone years with context: "menarş 2022"

### Category Chips
Colored toggle buttons in main_window.py `_build_category_chips()`. Colors from `CATEGORY_COLORS` in `redactor.py`. White text on tinted colored backgrounds for contrast.

## Build & Test

```bash
# Run tests
.venv/bin/python -m pytest tests/ -q

# Build macOS app
.venv/bin/pyinstaller Redakt.spec --noconfirm
# Output: dist/Redakt.app

# Run from source
.venv/bin/python -m redakt
```

## Rules

- **Always rebuild after code changes**: Run `.venv/bin/pyinstaller Redakt.spec --noconfirm` after any change
- **Bug-first testing**: When a bug is reported, write a failing test first, then fix
- **Push after fixing**: Commit, rebuild, and push to main after completing fixes
- **No preview_start**: This is a desktop app, not a web server. Verify via tests + build + smoke test

## Releases

- GitHub releases at https://github.com/borean/redakt/releases
- macOS (Apple Silicon): `Redakt-macOS-arm64.zip`
- Windows/Linux: Coming soon
- Manifesto site links to latest release download
