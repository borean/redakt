"""GGUF model download manager with resume support.

Downloads models from HuggingFace with:
- Resumable downloads via HTTP Range headers
- Disk space verification before starting
- Progress reporting via Qt Signals (for UI) or callbacks (for headless)
- Partial file pattern (.partial suffix) to avoid serving incomplete models
"""

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from redakt.constants import GGUF_HF_BASE_URL, GGUF_HF_REPO

log = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """Return the platform-appropriate directory for storing downloaded models."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Redakt"
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        base = Path(local) / "Redakt"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        base = Path(xdg) / "redakt"
    models_dir = base / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


@dataclass
class ModelDownloadInfo:
    """Metadata for a downloadable GGUF model."""

    repo_id: str
    filename: str
    url: str
    size_bytes: int
    quant: str
    display_name: str

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024**3), 1)


# Pre-defined model catalog
AVAILABLE_MODELS: list[ModelDownloadInfo] = [
    ModelDownloadInfo(
        repo_id=GGUF_HF_REPO,
        filename="Qwen3.5-35B-A3B-Q4_K_M.gguf",
        url=f"{GGUF_HF_BASE_URL}/Qwen3.5-35B-A3B-Q4_K_M.gguf",
        size_bytes=21_474_836_480,  # ~20 GB
        quant="Q4_K_M",
        display_name="Qwen3.5 35B-A3B Q4_K_M (recommended)",
    ),
    ModelDownloadInfo(
        repo_id=GGUF_HF_REPO,
        filename="Qwen3.5-35B-A3B-Q8_0.gguf",
        url=f"{GGUF_HF_BASE_URL}/Qwen3.5-35B-A3B-Q8_0.gguf",
        size_bytes=35_433_480_192,  # ~33 GB
        quant="Q8_0",
        display_name="Qwen3.5 35B-A3B Q8_0 (high quality)",
    ),
]


def check_disk_space(dest_dir: Path, required_bytes: int) -> bool:
    """Return True if dest_dir has enough free space for the download."""
    usage = shutil.disk_usage(dest_dir)
    # Require 2 GB headroom beyond the model size
    return usage.free >= required_bytes + 2 * 1024**3


async def download_model(
    model_info: ModelDownloadInfo,
    dest_dir: Path | None = None,
    on_progress: "callable | None" = None,
    cancel_event: "asyncio.Event | None" = None,
) -> Path:
    """Download a GGUF model with resume support.

    Args:
        model_info: Which model to download.
        dest_dir: Where to save. Defaults to get_data_dir().
        on_progress: Callback(percent: float, downloaded_mb: float, total_mb: float, status: str).
        cancel_event: Set this event to cancel the download.

    Returns:
        Path to the completed .gguf file.

    Raises:
        RuntimeError: On disk space, network, or cancellation errors.
    """
    import asyncio

    if dest_dir is None:
        dest_dir = get_data_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    final_path = dest_dir / model_info.filename
    partial_path = dest_dir / (model_info.filename + ".partial")

    # Already downloaded?
    if final_path.exists():
        size = final_path.stat().st_size
        if size >= model_info.size_bytes * 0.95:  # Allow 5% tolerance
            log.info("Model already exists: %s (%s GB)", final_path, model_info.size_gb)
            return final_path
        else:
            # Corrupt/incomplete without .partial — remove and re-download
            final_path.unlink()

    # Check disk space
    if not check_disk_space(dest_dir, model_info.size_bytes):
        usage = shutil.disk_usage(dest_dir)
        free_gb = round(usage.free / 1024**3, 1)
        raise RuntimeError(
            f"Not enough disk space. Need ~{model_info.size_gb} GB, "
            f"only {free_gb} GB free in {dest_dir}"
        )

    # Resume support: check partial file
    resume_pos = 0
    if partial_path.exists():
        resume_pos = partial_path.stat().st_size
        log.info("Resuming download from %.1f GB", resume_pos / 1024**3)

    headers = {}
    if resume_pos > 0:
        headers["Range"] = f"bytes={resume_pos}-"

    total_mb = model_info.size_bytes / (1024**2)

    def _report(downloaded: int, status: str = "Downloading..."):
        if on_progress:
            pct = (downloaded / model_info.size_bytes) * 100 if model_info.size_bytes > 0 else 0
            on_progress(min(pct, 100.0), downloaded / (1024**2), total_mb, status)

    _report(resume_pos, "Resuming download..." if resume_pos > 0 else "Starting download...")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", model_info.url, headers=headers) as resp:
                if resp.status_code == 416:
                    # Range not satisfiable — file is already complete or server doesn't support it
                    if partial_path.exists():
                        partial_path.rename(final_path)
                        return final_path
                    raise RuntimeError("Download server returned 416 Range Not Satisfiable")

                resp.raise_for_status()

                mode = "ab" if resume_pos > 0 else "wb"
                downloaded = resume_pos
                chunk_count = 0

                with open(partial_path, mode) as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):  # 1 MB chunks
                        if cancel_event and cancel_event.is_set():
                            raise RuntimeError("Download cancelled by user")

                        f.write(chunk)
                        downloaded += len(chunk)
                        chunk_count += 1

                        # Report progress every 5 chunks (~5 MB)
                        if chunk_count % 5 == 0:
                            _report(downloaded)

                _report(downloaded, "Verifying download...")

    except httpx.HTTPError as e:
        _report(resume_pos, f"Network error: {e}")
        raise RuntimeError(
            f"Download failed: {e}\n\n"
            f"The partial download has been saved. "
            f"Run the app again to resume."
        ) from e

    # Verify file size
    actual_size = partial_path.stat().st_size
    if actual_size < model_info.size_bytes * 0.95:
        raise RuntimeError(
            f"Download appears incomplete: got {actual_size / 1024**3:.1f} GB, "
            f"expected {model_info.size_gb} GB. Run again to resume."
        )

    # Rename .partial → final
    partial_path.rename(final_path)
    _report(actual_size, "Download complete!")
    log.info("Download complete: %s (%.1f GB)", final_path, actual_size / 1024**3)
    return final_path
