"""Manage the llama-server lifecycle so the user never touches a terminal.

The manager can:
- Locate the ``llama-server`` binary (Homebrew, PATH, custom)
- Locate the GGUF model file from download dir or well-known directories
- Start llama-server as a child process with the correct flags
- Wait for the ``/health`` endpoint to become ready
- Stop the server gracefully on app exit
"""

import asyncio
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, Signal

from redakt.constants import LLAMACPP_HOST, LLAMACPP_MODEL

# ── GGUF discovery ───────────────────────────────────────────────────────

_GGUF_FILENAME = f"{LLAMACPP_MODEL}.gguf"

# Explicit directories to check (in priority order)
_GGUF_SEARCH_DIRS: list[Path] = [
    # Platform-appropriate data dir (primary — where downloads go)
    # Imported lazily to avoid circular imports; inserted at runtime in _find_gguf()
    Path.home() / ".redakt" / "models",
    Path.home() / "Library" / "Application Support" / "Redakt" / "models",
    Path.home() / "models",
]


def _find_gguf() -> Path | None:
    """Search for the GGUF: download dir first, then well-known dirs."""
    # 0. Check the platform download directory first (where download_manager saves)
    try:
        from redakt.core.download_manager import get_data_dir

        data_dir = get_data_dir()
        # Check any .gguf file in the data dir
        for gguf_file in sorted(data_dir.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True):
            return gguf_file
    except Exception:
        pass

    # 1. Check explicit directories for a named .gguf file
    for d in _GGUF_SEARCH_DIRS:
        candidate = d / _GGUF_FILENAME
        if candidate.exists():
            return candidate

    return None


@dataclass
class GGUFInfo:
    """Discovered GGUF model file."""

    path: Path
    name: str  # Display name, e.g. "Qwen3.5 35B-A3B Q4_K_M"
    quant: str  # Quantization type, e.g. "Q4_K_M", "Q8_0"
    size_gb: float  # File size in GB
    source: str  # "auto-discovered" or "local"


# Known quantization identifiers for filename matching
_KNOWN_QUANTS = (
    "Q4_K_M", "Q8_0", "Q4_K_S", "Q5_K_M", "Q5_K_S",
    "Q6_K", "BF16", "F16", "Q2_K", "Q3_K_M", "Q3_K_S",
    "Q3_K_L", "IQ4_XS", "IQ4_NL",
)


def _friendly_gguf_name(stem: str, size_gb: float, quant: str) -> str:
    """Generate a friendly display name for a GGUF file.

    If the filename is a SHA hash or otherwise opaque, produce a name like
    "Qwen3.5 35B-A3B Q4_K_M" based on size and quant.
    """
    # Detect opaque filenames: SHA hashes, UUIDs, etc.
    is_opaque = (
        stem.startswith("sha256-")
        or stem.startswith("sha512-")
        or (len(stem) > 40 and all(c in "0123456789abcdef-" for c in stem.lower()))
    )
    if not is_opaque:
        return stem

    # Build friendly name from the model identity in constants
    quant_label = quant if quant != "Unknown" else ""
    return f"Qwen3.5 35B-A3B {quant_label}".strip()


def find_all_ggufs() -> list[GGUFInfo]:
    """Discover all available GGUF model files from download dir and well-known dirs."""
    results: list[GGUFInfo] = []
    seen_paths: set[str] = set()

    def _make_info(gguf_file: Path, source: str) -> GGUFInfo:
        size_gb = gguf_file.stat().st_size / (1024**3)
        fname_upper = gguf_file.stem.upper()
        quant = "Unknown"
        for q in _KNOWN_QUANTS:
            if q in fname_upper:
                quant = q
                break
        # Infer quant from file size if filename is opaque
        if quant == "Unknown":
            if 18 <= size_gb <= 24:
                quant = "Q4_K_M"
            elif 30 <= size_gb <= 38:
                quant = "Q8_0"
        name = _friendly_gguf_name(gguf_file.stem, size_gb, quant)
        return GGUFInfo(
            path=gguf_file,
            name=name,
            quant=quant,
            size_gb=round(size_gb, 1),
            source=source,
        )

    # 0. Download directory first
    try:
        from redakt.core.download_manager import get_data_dir

        data_dir = get_data_dir()
        if data_dir.exists():
            for gguf_file in sorted(data_dir.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True):
                if str(gguf_file) not in seen_paths:
                    results.append(_make_info(gguf_file, "local"))
                    seen_paths.add(str(gguf_file))
    except Exception:
        pass

    # 1. Scan local directories for .gguf files
    for search_dir in _GGUF_SEARCH_DIRS:
        if not search_dir.exists():
            continue
        for gguf_file in sorted(search_dir.glob("*.gguf")):
            if str(gguf_file) in seen_paths:
                continue
            results.append(_make_info(gguf_file, "local"))
            seen_paths.add(str(gguf_file))

    return results


def _find_llamacpp_binary() -> str | None:
    """Locate the llama-server binary.

    Priority: bundled in app → PATH → Homebrew → common system paths.
    """
    # 0. Bundled binary (PyInstaller app bundle)
    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", ""))
        bundled = bundle_dir / "bin" / ("llama-server.exe" if sys.platform == "win32" else "llama-server")
        if bundled.exists():
            return str(bundled)
    else:
        # Development: check for binary alongside the project
        dev_bin = Path(__file__).parent.parent.parent / "bin" / (
            "llama-server.exe" if sys.platform == "win32" else "llama-server"
        )
        if dev_bin.exists():
            return str(dev_bin)

    # 1. PATH / which
    found = shutil.which("llama-server")
    if found:
        return found
    # 2. Homebrew (Apple Silicon)
    p = Path("/opt/homebrew/bin/llama-server")
    if p.exists():
        return str(p)
    # 3. Homebrew (Intel Mac)
    p = Path("/usr/local/bin/llama-server")
    if p.exists():
        return str(p)
    # 4. Common Linux paths
    for d in ("/usr/bin", "/usr/local/bin", "/snap/bin"):
        p = Path(d) / "llama-server"
        if p.exists():
            return str(p)
    return None


class LlamaCppManager(QObject):
    """Manages the llama-server process lifecycle."""

    # Signals for UI feedback
    status_message = Signal(str)
    server_status_changed = Signal(bool)   # True = running & healthy
    error_occurred = Signal(str)
    server_ready = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._binary_path: str | None = None
        self._gguf_path: Path | None = None
        self._we_started_it = False  # Only stop if we started it

    # ── Discovery ────────────────────────────────────────────────────────

    @property
    def binary_path(self) -> str | None:
        if self._binary_path is None:
            self._binary_path = _find_llamacpp_binary()
        return self._binary_path

    @property
    def gguf_path(self) -> Path | None:
        if self._gguf_path is None:
            self._gguf_path = _find_gguf()
        return self._gguf_path

    @gguf_path.setter
    def gguf_path(self, path: Path):
        self._gguf_path = path

    def is_installed(self) -> bool:
        return self.binary_path is not None

    def has_model(self) -> bool:
        return self.gguf_path is not None

    def get_available_ggufs(self) -> list[GGUFInfo]:
        """Return all discovered GGUF models, including current path if set."""
        results = find_all_ggufs()
        # Include current gguf_path if it exists and isn't already in the list
        if self._gguf_path and self._gguf_path.exists():
            path_str = str(self._gguf_path)
            if not any(str(r.path) == path_str for r in results):
                size_gb = self._gguf_path.stat().st_size / (1024**3)
                fname_upper = self._gguf_path.stem.upper()
                quant = "Unknown"
                for q in _KNOWN_QUANTS:
                    if q in fname_upper:
                        quant = q
                        break
                if quant == "Unknown":
                    if 18 <= size_gb <= 24:
                        quant = "Q4_K_M"
                    elif 30 <= size_gb <= 38:
                        quant = "Q8_0"
                name = _friendly_gguf_name(self._gguf_path.stem, size_gb, quant)
                results.insert(
                    0,
                    GGUFInfo(
                        path=self._gguf_path,
                        name=name,
                        quant=quant,
                        size_gb=round(size_gb, 1),
                        source="current",
                    ),
                )
        return results

    def set_gguf(self, info: GGUFInfo):
        """Set the active GGUF model file. Restarts server if running."""
        self._gguf_path = info.path
        if self._process and self._process.poll() is None:
            # Server is running with old model — restart needed
            self.stop_server()

    # ── Health check ─────────────────────────────────────────────────────

    async def is_server_running(self) -> bool:
        """Check if llama-server responds on /health."""
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(f"{LLAMACPP_HOST}/health", timeout=3.0)
                return resp.status_code == 200
        except Exception:
            return False

    async def wait_for_server(self, timeout: int = 60) -> bool:
        """Poll /health until the server is ready (model loaded).

        llama-server can take 10-30s to load a 22 GB GGUF into GPU.
        """
        for i in range(timeout):
            if self._process and self._process.poll() is not None:
                # Process died
                return False
            try:
                async with httpx.AsyncClient() as http:
                    resp = await http.get(f"{LLAMACPP_HOST}/health", timeout=3.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        # llama-server returns {"status":"ok"} when model is loaded
                        if data.get("status") == "ok":
                            return True
            except Exception:
                pass
            if i % 5 == 0 and i > 0:
                self.status_message.emit(
                    f"Loading model into GPU... ({i}s)"
                )
            await asyncio.sleep(1)
        return False

    # ── Start / Stop ─────────────────────────────────────────────────────

    def start_server(self) -> bool:
        """Start llama-server as a subprocess.

        Returns True if the process was launched (doesn't mean it's ready yet).
        """
        binary = self.binary_path
        if not binary:
            self.error_occurred.emit(
                "llama-server binary not found.\n\n"
                "If running from source, install with: brew install llama.cpp"
            )
            return False

        model_path = self.gguf_path
        if not model_path:
            self.error_occurred.emit(
                "GGUF model not found.\n\n"
                "The model will be downloaded automatically on first launch."
            )
            return False

        # Extract port from LLAMACPP_HOST
        port = LLAMACPP_HOST.rsplit(":", 1)[-1]

        cmd = [
            binary,
            "-m", str(model_path),
            "-ngl", "99",               # Offload all layers to GPU
            "-c", "8192",               # Context length
            "--port", port,
            "-fa", "on",                # Flash attention
            "--reasoning-budget", "0",  # Disable thinking mode
        ]

        try:
            # Redirect output to devnull; user doesn't need server logs
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # Start in a new process group so we can kill it cleanly
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )
            self._we_started_it = True
            return True
        except Exception as e:
            self.error_occurred.emit(f"Failed to start llama-server: {e}")
            return False

    def stop_server(self):
        """Gracefully stop the llama-server if we started it."""
        if not self._we_started_it or self._process is None:
            return

        try:
            if self._process.poll() is None:
                # Send SIGTERM to the process group
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                else:
                    self._process.terminate()

                # Give it a few seconds to shut down
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill
                    if sys.platform != "win32":
                        os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                    else:
                        self._process.kill()
                    self._process.wait(timeout=3)
        except Exception:
            pass
        finally:
            self._process = None
            self._we_started_it = False

    # ── Full bootstrap ───────────────────────────────────────────────────

    async def ensure_ready(self) -> bool:
        """Full lifecycle: check binary, check model, start server, wait.

        Returns True when the server is healthy and ready for requests.
        """
        # Step 1: Binary
        self.status_message.emit("Checking for llama-server...")
        if not self.is_installed():
            self.error_occurred.emit(
                "llama-server binary not found.\n\n"
                "The app will attempt to locate it automatically.\n"
                "If running from source, install with: brew install llama.cpp"
            )
            return False

        # Step 2: Model file
        self.status_message.emit("Locating GGUF model...")
        if not self.has_model():
            self.error_occurred.emit(
                "GGUF model not found.\n\n"
                "The model will be downloaded automatically on first launch.\n"
                "Please restart the app to begin the download."
            )
            return False

        # Step 3: Already running?
        self.status_message.emit("Checking if llama-server is running...")
        if await self.is_server_running():
            self.server_status_changed.emit(True)
            self.server_ready.emit()
            return True

        # Step 4: Start
        self.status_message.emit("Starting llama-server...")
        if not self.start_server():
            return False

        # Step 5: Wait for health
        self.status_message.emit("Loading model into GPU... (this may take 15-30s)")
        if await self.wait_for_server(timeout=90):
            self.server_status_changed.emit(True)
            self.server_ready.emit()
            return True
        else:
            self.stop_server()
            self.server_status_changed.emit(False)
            self.error_occurred.emit(
                "llama-server failed to start.\n\n"
                "Check that no other process is using port "
                f"{LLAMACPP_HOST.rsplit(':', 1)[-1]}."
            )
            return False
