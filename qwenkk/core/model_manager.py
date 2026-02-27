import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
from ollama import AsyncClient

from PySide6.QtCore import QObject, Signal

from qwenkk.constants import DEFAULT_MODEL, OLLAMA_HOST, VISION_MODEL


class ModelManager(QObject):
    """Manages the full ollama lifecycle: install, start, pull model."""

    # Signals for UI
    status_message = Signal(str)          # human-readable status text
    ollama_status_changed = Signal(bool)  # is ollama reachable
    model_status_changed = Signal(str)    # model status text
    model_pull_progress = Signal(float, str)  # percent, detail
    model_ready = Signal()
    error_occurred = Signal(str)
    ollama_install_needed = Signal()      # user must install ollama

    def __init__(self, host: str = OLLAMA_HOST):
        super().__init__()
        self.host = host
        self.client = AsyncClient(host=host)
        self._current_model = DEFAULT_MODEL
        self._vision_model = VISION_MODEL

    @property
    def current_model(self) -> str:
        return self._current_model

    @current_model.setter
    def current_model(self, value: str):
        self._current_model = value

    @property
    def vision_model(self) -> str:
        return self._vision_model

    # ── Detection ──────────────────────────────────────────────────────

    @staticmethod
    def is_ollama_installed() -> bool:
        """Check if ollama binary exists on the system."""
        # Check common install locations
        if shutil.which("ollama"):
            return True
        # macOS: check if Ollama.app exists
        if sys.platform == "darwin":
            if Path("/Applications/Ollama.app").exists():
                return True
        # Windows: check common install path
        if sys.platform == "win32":
            appdata = Path.home() / "AppData" / "Local" / "Programs" / "Ollama"
            if appdata.exists():
                return True
        return False

    async def is_ollama_running(self) -> bool:
        """Check if ollama server is responding."""
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(self.host, timeout=5.0)
                return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def start_ollama() -> bool:
        """Try to start the ollama server."""
        try:
            if sys.platform == "darwin":
                # Open the Ollama.app which starts the server
                if Path("/Applications/Ollama.app").exists():
                    subprocess.Popen(["open", "-a", "Ollama"])
                    return True
                # Fallback: try ollama serve in background
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            elif sys.platform == "win32":
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return True
            else:
                # Linux
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
        except Exception:
            return False

    async def wait_for_ollama(self, timeout: int = 30) -> bool:
        """Wait for ollama server to become responsive."""
        for _ in range(timeout):
            if await self.is_ollama_running():
                return True
            await asyncio.sleep(1)
        return False

    async def is_model_available(self, model_name: str | None = None) -> bool:
        model_name = model_name or self._current_model
        try:
            response = await self.client.list()
            names = [m.model for m in response.models]
            return any(model_name in n for n in names)
        except Exception:
            return False

    # ── Model Pull ─────────────────────────────────────────────────────

    async def pull_model(self, model_name: str | None = None):
        """Pull model using raw httpx to avoid SDK ProgressResponse bugs.

        The ollama SDK's ProgressResponse has ``completed: Optional[int]``
        and ``total: Optional[int]``.  Status-only messages (e.g.
        ``"pulling manifest"``, ``"verifying sha256 digest"``) arrive
        with *neither* field, so both are ``None``.  Any ``>`` comparison
        on a ``None`` value raises ``TypeError``.  We therefore use raw
        httpx streaming and guard every arithmetic/comparison path.
        """
        import json as _json

        model_name = model_name or self._current_model
        self.model_status_changed.emit(f"Downloading {model_name}...")
        try:
            async with httpx.AsyncClient(timeout=None) as http:
                async with http.stream(
                    "POST",
                    f"{self.host}/api/pull",
                    json={"model": model_name, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        try:
                            data = _json.loads(line)
                            if "error" in data:
                                self.error_occurred.emit(
                                    f"Model download failed: {data['error']}"
                                )
                                return
                            status = data.get("status", "")
                            total = data.get("total")
                            completed = data.get("completed")
                            if (
                                isinstance(total, int)
                                and isinstance(completed, int)
                                and total > 0
                            ):
                                pct = completed / total * 100.0
                                self.model_pull_progress.emit(pct, status)
                            else:
                                self.model_pull_progress.emit(0.0, status)
                        except (_json.JSONDecodeError, ValueError, TypeError):
                            pass
            self.model_status_changed.emit("Ready")
            self.model_ready.emit()
        except Exception as e:
            self.error_occurred.emit(f"Model download failed: {e}")

    async def ensure_vision_model(self) -> bool:
        """Pull the vision model on demand (for image processing)."""
        if await self.is_model_available(self._vision_model):
            return True
        self.status_message.emit(f"Downloading vision model ({self._vision_model})...")
        await self.pull_model(self._vision_model)
        return await self.is_model_available(self._vision_model)

    # ── Full Bootstrap ─────────────────────────────────────────────────

    async def ensure_ready(self) -> bool:
        """
        Full first-run bootstrap:
        1. Check if ollama is installed → prompt install if not
        2. Check if ollama is running → start it if not
        3. Check if model is pulled → pull if not
        """
        # Step 1: Is ollama installed?
        self.status_message.emit("Checking for Ollama...")
        if not self.is_ollama_installed():
            self.ollama_status_changed.emit(False)
            self.ollama_install_needed.emit()
            return False

        # Step 2: Is ollama running?
        self.status_message.emit("Connecting to Ollama...")
        if not await self.is_ollama_running():
            self.status_message.emit("Starting Ollama...")
            self.start_ollama()
            if not await self.wait_for_ollama(timeout=30):
                self.ollama_status_changed.emit(False)
                self.error_occurred.emit(
                    "Could not start Ollama. Please start it manually."
                )
                return False

        self.ollama_status_changed.emit(True)

        # Step 3: Is model available?
        self.status_message.emit("Checking AI model...")
        if not await self.is_model_available():
            self.status_message.emit(
                f"Downloading AI model ({self._current_model})...\n"
                "This is a one-time download (~18 GB)."
            )
            await self.pull_model()
        else:
            self.model_status_changed.emit("Ready")
            self.model_ready.emit()

        return True
