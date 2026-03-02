"""Headless llama-server manager for API mode (no Qt dependency).

Reuses the pure-Python discovery logic from the main manager but avoids
QObject/Signal so it can run without a QApplication.
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

import httpx

from redakt.constants import LLAMACPP_HOST

log = logging.getLogger("redakt.llamacpp")

# Import pure-function discovery logic from the main manager
from redakt.core.llamacpp_manager import (
    _find_gguf,
    _find_llamacpp_binary,
)


class HeadlessLlamaCpp:
    """Manages llama-server lifecycle without Qt dependencies."""

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._binary_path: str | None = None
        self._gguf_path: Path | None = None
        self._we_started_it = False

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

    async def is_server_running(self) -> bool:
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(f"{LLAMACPP_HOST}/health", timeout=3.0)
                return resp.status_code == 200
        except Exception:
            return False

    def start_server(self) -> bool:
        binary = self.binary_path
        model_path = self.gguf_path
        if not binary or not model_path:
            log.error("Cannot start: binary=%s, model=%s", binary, model_path)
            return False

        port = LLAMACPP_HOST.rsplit(":", 1)[-1]
        cmd = [
            binary,
            "-m", str(model_path),
            "-ngl", "99",
            "-c", "8192",
            "--port", port,
            "-fa", "on",
            "--reasoning-budget", "0",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )
            self._we_started_it = True
            log.info("Started llama-server (PID %d)", self._process.pid)
            return True
        except Exception as e:
            log.error("Failed to start llama-server: %s", e)
            return False

    async def wait_for_server(self, timeout: int = 90) -> bool:
        for i in range(timeout):
            if self._process and self._process.poll() is not None:
                return False
            try:
                async with httpx.AsyncClient() as http:
                    resp = await http.get(f"{LLAMACPP_HOST}/health", timeout=3.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "ok":
                            return True
            except Exception:
                pass
            if i % 10 == 0 and i > 0:
                log.info("Waiting for model to load... (%ds)", i)
            await asyncio.sleep(1)
        return False

    def stop_server(self):
        if not self._we_started_it or self._process is None:
            return
        try:
            if self._process.poll() is None:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                else:
                    self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
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

    async def ensure_ready(self) -> bool:
        """Full lifecycle: check binary, check model, start server, wait."""
        if not self.is_installed():
            log.error("llama-server binary not found")
            return False

        if not self.has_model():
            log.error("GGUF model not found")
            return False

        if await self.is_server_running():
            log.info("llama-server already running")
            return True

        log.info("Starting llama-server...")
        if not self.start_server():
            return False

        log.info("Waiting for model to load (this may take 15-30s)...")
        if await self.wait_for_server(timeout=90):
            log.info("llama-server is ready")
            return True

        self.stop_server()
        log.error("llama-server failed to start within timeout")
        return False
