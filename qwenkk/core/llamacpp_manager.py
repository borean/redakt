"""Manage the llama-server lifecycle so the user never touches a terminal.

The manager can:
- Locate the ``llama-server`` binary (Homebrew, PATH, custom)
- Locate the GGUF model file automatically from ollama's blob store,
  or from well-known directories — zero manual setup needed
- Start llama-server as a child process with the correct flags
- Wait for the ``/health`` endpoint to become ready
- Stop the server gracefully on app exit
"""

import asyncio
import json as _json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, Signal

from qwenkk.constants import LLAMACPP_HOST, LLAMACPP_MODEL

# ── GGUF discovery ───────────────────────────────────────────────────────

_GGUF_FILENAME = f"{LLAMACPP_MODEL}.gguf"

# The ollama model tag we pull from HuggingFace
_OLLAMA_HF_MANIFEST = (
    Path.home()
    / ".ollama"
    / "models"
    / "manifests"
    / "hf.co"
    / "unsloth"
    / "Qwen3.5-35B-A3B-GGUF"
    / "Q4_K_M"
)

# Explicit directories to check (in priority order)
_GGUF_SEARCH_DIRS: list[Path] = [
    Path.home() / ".qwenkk" / "models",
    Path.home() / "Library" / "Application Support" / "QwenKK" / "models",
    Path.home() / "Projects" / "QwenKK" / "models",
    Path.home() / "models",
]


def _find_gguf_in_ollama() -> Path | None:
    """Read the ollama manifest and return the blob path for the GGUF layer.

    When a user runs ``ollama pull hf.co/unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M``,
    ollama stores the GGUF as a blob under ``~/.ollama/models/blobs/``.
    The manifest tells us which blob corresponds to the model weights.
    """
    if not _OLLAMA_HF_MANIFEST.exists():
        return None

    try:
        manifest = _json.loads(_OLLAMA_HF_MANIFEST.read_text())
        for layer in manifest.get("layers", []):
            media = layer.get("mediaType", "")
            if "model" in media and "projector" not in media:
                digest: str = layer["digest"]  # e.g. "sha256:e8c60ba..."
                # Ollama stores blobs as ~/.ollama/models/blobs/<digest>
                # with ":" replaced by "-"
                blob = (
                    Path.home()
                    / ".ollama"
                    / "models"
                    / "blobs"
                    / digest.replace(":", "-")
                )
                if blob.exists():
                    return blob
    except Exception:
        pass
    return None


def _find_gguf() -> Path | None:
    """Search for the GGUF: first in ollama blobs, then well-known dirs."""
    # 1. Auto-discover from ollama's blob store (zero-config)
    blob = _find_gguf_in_ollama()
    if blob:
        return blob

    # 2. Check explicit directories for a named .gguf file
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


def _resolve_ollama_manifest(manifest_path: Path) -> Path | None:
    """Read an ollama manifest and return the blob path for the model layer."""
    try:
        manifest = _json.loads(manifest_path.read_text())
        for layer in manifest.get("layers", []):
            media = layer.get("mediaType", "")
            if "model" in media and "projector" not in media:
                digest = layer["digest"]
                blob = (
                    Path.home()
                    / ".ollama"
                    / "models"
                    / "blobs"
                    / digest.replace(":", "-")
                )
                if blob.exists():
                    return blob
    except Exception:
        pass
    return None


# Known quantization identifiers for filename matching
_KNOWN_QUANTS = (
    "Q4_K_M", "Q8_0", "Q4_K_S", "Q5_K_M", "Q5_K_S",
    "Q6_K", "BF16", "F16", "Q2_K", "Q3_K_M", "Q3_K_S",
    "Q3_K_L", "IQ4_XS", "IQ4_NL",
)


def find_all_ggufs() -> list[GGUFInfo]:
    """Discover all available GGUF model files.

    Searches two sources:
    1. Ollama manifests — each file under the manifest directory represents
       a quantization (Q4_K_M, Q8_0, etc.) pulled via
       ``ollama pull hf.co/unsloth/Qwen3.5-35B-A3B-GGUF:<quant>``.
    2. Local directories listed in ``_GGUF_SEARCH_DIRS`` for any ``.gguf`` files.
    """
    results: list[GGUFInfo] = []
    seen_paths: set[str] = set()

    # 1. Check ollama manifests for multiple quantizations
    manifest_parent = (
        Path.home()
        / ".ollama"
        / "models"
        / "manifests"
        / "hf.co"
        / "unsloth"
        / "Qwen3.5-35B-A3B-GGUF"
    )
    if manifest_parent.exists():
        for entry in sorted(manifest_parent.iterdir()):
            if not entry.is_file():
                continue
            quant_name = entry.name  # e.g. "Q4_K_M", "Q8_0"
            blob_path = _resolve_ollama_manifest(entry)
            if blob_path and str(blob_path) not in seen_paths:
                size_gb = blob_path.stat().st_size / (1024**3)
                results.append(
                    GGUFInfo(
                        path=blob_path,
                        name=f"Qwen3.5 35B-A3B {quant_name}",
                        quant=quant_name,
                        size_gb=round(size_gb, 1),
                        source="auto-discovered",
                    )
                )
                seen_paths.add(str(blob_path))

    # 2. Scan local directories for .gguf files
    for search_dir in _GGUF_SEARCH_DIRS:
        if not search_dir.exists():
            continue
        for gguf_file in sorted(search_dir.glob("*.gguf")):
            if str(gguf_file) in seen_paths:
                continue
            size_gb = gguf_file.stat().st_size / (1024**3)
            # Try to extract quantization from filename
            fname_upper = gguf_file.stem.upper()
            quant = "Unknown"
            for q in _KNOWN_QUANTS:
                if q in fname_upper:
                    quant = q
                    break
            results.append(
                GGUFInfo(
                    path=gguf_file,
                    name=gguf_file.stem,
                    quant=quant,
                    size_gb=round(size_gb, 1),
                    source="local",
                )
            )
            seen_paths.add(str(gguf_file))

    return results


def _find_llamacpp_binary() -> str | None:
    """Locate the llama-server binary."""
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
        """Return all discovered GGUF models."""
        return find_all_ggufs()

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
                "llama-server not found.\n\n"
                "Install it with: brew install llama.cpp"
            )
            return False

        model_path = self.gguf_path
        if not model_path:
            self.error_occurred.emit(
                f"GGUF model not found.\n\n"
                "Download it with:\n"
                "  ollama pull hf.co/unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M"
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
                "llama-server is not installed.\n\n"
                "Install with: brew install llama.cpp\n"
                "(or see https://github.com/ggml-org/llama.cpp)"
            )
            return False

        # Step 2: Model file (auto-discovered from ollama blobs)
        self.status_message.emit("Locating GGUF model...")
        if not self.has_model():
            self.error_occurred.emit(
                "GGUF model not found.\n\n"
                "Download it with:\n"
                "  ollama pull hf.co/unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M\n\n"
                "The app will find it automatically in ollama's store."
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
