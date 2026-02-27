"""Detect system hardware specs to show model compatibility info."""

import platform
import subprocess


def get_system_info() -> dict:
    """Return a dict with system hardware info relevant for LLM inference."""
    info = {
        "os": platform.system(),
        "os_version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.version(),
        "arch": platform.machine(),
        "cpu": _get_cpu_name(),
        "ram_gb": _get_ram_gb(),
        "gpu": _get_gpu_info(),
        "gpu_vram_gb": _get_gpu_vram_gb(),
        "apple_silicon": _is_apple_silicon(),
        "unified_memory_gb": _get_unified_memory_gb(),
    }
    return info


def get_model_recommendations(info: dict) -> list[dict]:
    """Return a list of model options with compatibility info based on system specs.

    Each item: {"name": ..., "size_gb": ..., "compatible": bool, "note": str}
    """
    total_mem = info.get("unified_memory_gb") or info.get("ram_gb") or 0
    gpu_vram = info.get("gpu_vram_gb") or 0
    apple = info.get("apple_silicon", False)

    # For Apple Silicon, unified memory is used for inference
    available_mem = total_mem if apple else max(gpu_vram, total_mem * 0.7)

    models = []

    # Q4_K_M quantized (~21GB)
    models.append({
        "name": "Qwen3.5 35B-A3B Q4_K_M",
        "param": "35B (3B active)",
        "size_gb": 21,
        "compatible": available_mem >= 24,
        "note": _compat_note(available_mem, 24, apple),
        "tag": "RECOMMENDED" if available_mem >= 24 else "TOO LARGE",
    })

    # Q8_0 quantized (~37GB)
    models.append({
        "name": "Qwen3.5 35B-A3B Q8_0",
        "param": "35B (3B active)",
        "size_gb": 37,
        "compatible": available_mem >= 42,
        "note": _compat_note(available_mem, 42, apple),
        "tag": "HIGH QUALITY" if available_mem >= 42 else "REQUIRES 48GB+",
    })

    # BF16 full precision (~69GB)
    models.append({
        "name": "Qwen3.5 35B-A3B BF16",
        "param": "35B (3B active)",
        "size_gb": 69,
        "compatible": available_mem >= 80,
        "note": _compat_note(available_mem, 80, apple),
        "tag": "FULL PRECISION" if available_mem >= 80 else "REQUIRES 96GB+",
    })

    return models


def format_system_summary(info: dict) -> str:
    """One-line system summary for status display."""
    parts = []
    if info.get("apple_silicon"):
        parts.append(f"Apple Silicon ({info['cpu']})")
        mem = info.get("unified_memory_gb", 0)
        if mem:
            parts.append(f"{mem}GB unified memory")
    else:
        parts.append(info.get("cpu", "Unknown CPU"))
        ram = info.get("ram_gb", 0)
        if ram:
            parts.append(f"{ram}GB RAM")
        gpu = info.get("gpu", "")
        if gpu and gpu != "Unknown":
            vram = info.get("gpu_vram_gb", 0)
            parts.append(f"{gpu}" + (f" {vram}GB" if vram else ""))

    return " // ".join(parts)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _compat_note(available_mem: float, required_mem: float, apple: bool) -> str:
    mem_type = "unified memory" if apple else "VRAM/RAM"
    if available_mem >= required_mem:
        headroom = available_mem - required_mem
        return f"OK — ~{headroom:.0f}GB headroom ({mem_type})"
    else:
        deficit = required_mem - available_mem
        return f"Need ~{deficit:.0f}GB more {mem_type}"


def _get_cpu_name() -> str:
    system = platform.system()
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            name = result.stdout.strip()
            if name:
                return name
            # Apple Silicon reports chip name differently
            result = subprocess.run(
                ["sysctl", "-n", "hw.chip"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() or platform.processor()
        except Exception:
            return platform.processor()
    elif system == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":")[1].strip()
        except Exception:
            pass
    return platform.processor() or "Unknown"


def _get_ram_gb() -> int:
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            return int(result.stdout.strip()) // (1024 ** 3)
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return kb // (1024 ** 2)
    except Exception:
        pass
    return 0


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _get_unified_memory_gb() -> int:
    """On Apple Silicon, all RAM is unified memory usable by the GPU."""
    if _is_apple_silicon():
        return _get_ram_gb()
    return 0


def _get_gpu_info() -> str:
    system = platform.system()
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Chipset Model:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        if _is_apple_silicon():
            return _get_cpu_name()
    elif system == "Linux":
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip().split("\n")[0]
        except Exception:
            pass
    return "Unknown"


def _get_gpu_vram_gb() -> int:
    """Get discrete GPU VRAM (not applicable for Apple Silicon unified memory)."""
    system = platform.system()
    if system == "Linux":
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            return int(result.stdout.strip().split("\n")[0]) // 1024
        except Exception:
            pass
    # macOS: use unified memory instead (handled by _get_unified_memory_gb)
    return 0
