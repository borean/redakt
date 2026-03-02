#!/usr/bin/env python3
"""Build-time helper: download the correct llama-server binary for this platform.

Usage:
    python scripts/fetch_llamacpp.py

Downloads the latest llama.cpp release binary from GitHub and places it
in the bin/ directory, ready for PyInstaller bundling.
"""

import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# llama.cpp release tag to download (update as needed)
LLAMACPP_VERSION = "b5460"

# GitHub release asset patterns per platform
_ASSET_MAP = {
    ("Darwin", "arm64"): f"llama-{LLAMACPP_VERSION}-bin-macos-arm64.zip",
    ("Darwin", "x86_64"): f"llama-{LLAMACPP_VERSION}-bin-macos-x64.zip",
    ("Linux", "x86_64"): f"llama-{LLAMACPP_VERSION}-bin-ubuntu-x64.zip",
    ("Windows", "AMD64"): f"llama-{LLAMACPP_VERSION}-bin-win-avx2-x64.zip",
}

BASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMACPP_VERSION}"


def get_asset_name() -> str:
    system = platform.system()
    machine = platform.machine()
    key = (system, machine)
    if key not in _ASSET_MAP:
        print(f"ERROR: Unsupported platform: {system} {machine}")
        print(f"Supported: {list(_ASSET_MAP.keys())}")
        sys.exit(1)
    return _ASSET_MAP[key]


def main():
    project_root = Path(__file__).parent.parent
    bin_dir = project_root / "bin"
    bin_dir.mkdir(exist_ok=True)

    asset_name = get_asset_name()
    url = f"{BASE_URL}/{asset_name}"

    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Downloading: {url}")

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / asset_name
        urlretrieve(url, archive_path)
        print(f"Downloaded: {archive_path.stat().st_size / 1024 / 1024:.1f} MB")

        # Extract
        extract_dir = Path(tmpdir) / "extracted"
        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extract_dir)
        elif asset_name.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)

        # Find llama-server binary in extracted files
        binary_name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
        found = None
        for root, _dirs, files in os.walk(extract_dir):
            if binary_name in files:
                found = Path(root) / binary_name
                break

        if not found:
            print(f"ERROR: {binary_name} not found in archive")
            print("Contents:")
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    print(f"  {Path(root) / f}")
            sys.exit(1)

        dest = bin_dir / binary_name
        shutil.copy2(found, dest)

        # Make executable on Unix
        if platform.system() != "Windows":
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        print(f"Installed: {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
