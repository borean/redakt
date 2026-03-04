# Redakt — Development Guide

## What is this?
Redakt is a **local** medical document de-identification desktop app. It detects and redacts PII (names, dates, IDs, addresses, etc.) from medical documents using a local LLM — no cloud, no internet required after initial model download.

**Stack**: Tauri 2 (Rust) · Vanilla JS · llama.cpp sidecar · Qwen3.5 GGUF

## Project Layout

```
redakt-tauri/
  src-tauri/
    src/
      main.rs           # Entry point → lib.rs
      lib.rs            # Tauri app setup, plugins, state
      commands.rs       # 13 IPC command handlers
      entities.rs       # PIIEntity, ScanResult, AppSettings
      anonymizer.rs     # PII detection (LLM + regex), age conversion, date parsing
      llm.rs            # llama-server process lifecycle & HTTP inference
      redactor.rs       # HTML rendering, CATEGORY_COLORS
      download.rs       # Model catalog & GGUF download with progress
      export.rs         # DOCX/PDF/Markdown export
    Cargo.toml          # Dependencies: tauri 2, tokio, reqwest, chrono, regex
    binaries/           # llama-server sidecar (per-platform, downloaded by CI)
    icons/              # App icons (png, icns, ico)
    tauri.conf.json     # Tauri config (version, window, CSP, bundle settings)
  src/
    app.js              # Frontend: state, i18n (TR/EN), IPC calls, DOM
    index.html          # HTML structure with drag-drop, entity table, chips
    style.css           # Dark/light theme, responsive layout
manifesto/              # Marketing website (deployed via Vercel)
  index.html            # Single-page site with download links
.github/workflows/
  release.yml           # CI/CD: builds macOS (ARM+Intel), Windows, Linux
```

## Key Patterns

### IPC Architecture
Frontend calls Rust via `window.__TAURI__.core.invoke(command, args)`.
Backend emits events via `app.emit()` (e.g., download progress).

### PII Detection Pipeline
1. LLM inference via llama.cpp HTTP API (structured JSON output)
2. Post-LLM regex supplement (catches TC Kimlik 11-digit IDs the LLM misses)
3. Age conversion: 4-strategy cascade to find birth date, then converts dates to patient age

### Date Parsing
`anonymizer.rs::_parse_date()` handles 10+ formats including:
- Standard: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD
- Turkish text: "15 Ocak 2024"
- Standalone years with context

### i18n
Frontend i18n in `app.js` — TR/EN translations object. LLM prompts in `anonymizer.rs` for both languages.

## Build & Run

```bash
# Dev mode (requires llama-server sidecar in binaries/)
cd redakt-tauri && cargo tauri dev

# Production build
cd redakt-tauri && cargo tauri build

# CI builds all platforms via GitHub Actions on tag push (v*)
git tag v0.3.1 && git push origin v0.3.1
```

## Rules

- **Bug-first testing**: When a bug is reported, write a failing test first, then fix
- **Push after fixing**: Commit and push to main after completing fixes
- **No preview_start**: This is a desktop app, not a web server
- **CI/CD handles releases**: Push a `v*` tag to trigger cross-platform builds

## Releases

- GitHub releases at https://github.com/borean/redakt/releases
- macOS: `.dmg` (Apple Silicon + Intel)
- Windows: `.exe` installer + `.msi`
- Linux: `.deb` + `.rpm`
- Manifesto site links to latest release via `releases/latest/download/`
