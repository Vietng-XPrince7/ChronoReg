"""Local device selection and conservative memory preflight (no model downloads)."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys

GIB = 1024 ** 3
CPU_MIN_AVAILABLE = 14 * GIB


def nvidia_detected() -> bool:
    candidate = shutil.which("nvidia-smi")
    if not candidate and sys.platform.startswith("linux"):
        wsl = Path("/usr/lib/wsl/lib/nvidia-smi")
        if wsl.is_file():
            candidate = str(wsl)
    if not candidate:
        return False
    try:
        p = subprocess.run([candidate, "-L"], capture_output=True, text=True, timeout=10)
        return p.returncode == 0 and "GPU " in p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def choose_device(requested: str) -> str:
    if requested not in ("auto", "cuda", "cpu"):
        raise ValueError(f"Unknown device: {requested}")
    if requested != "auto":
        return requested
    return "cuda" if nvidia_detected() else "cpu"


def _stdlib_available_ram() -> int:
    if sys.platform == "win32":
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullAvailPhys)
    elif sys.platform.startswith("linux") and Path("/proc/meminfo").is_file():
        for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return int(parts[1]) * 1024
    raise ModuleNotFoundError("No module named 'psutil'")


def effective_available_ram() -> int:
    try:
        import psutil
        available = int(psutil.virtual_memory().available)
    except ModuleNotFoundError:
        available = _stdlib_available_ram()
    # WSL reports guest RAM. On Linux also respect a finite cgroup v2 budget.
    try:
        if sys.platform.startswith("linux"):
            rel = next(line.split(":", 2)[2] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::"))
            root = Path("/sys/fs/cgroup")
            group = root / rel.lstrip("/")
            if not group.is_dir():
                group = root
            for parent in (group, *group.parents):
                if parent == root or root in parent.parents:
                    cap = (parent / "memory.max").read_text().strip()
                    if cap != "max":
                        used = int((parent / "memory.current").read_text().strip())
                        available = min(available, max(0, int(cap) - used))
                if parent == root:
                    break
    except (OSError, ValueError, StopIteration):
        pass
    return available


def require_cpu_memory() -> int:
    available = effective_available_ram()
    if available < CPU_MIN_AVAILABLE:
        raise RuntimeError(
            f"CPU_RAM_INSUFFICIENT: {available/GIB:.1f} GiB available; "
            "at least 14 GiB available required for FP32 Qwen 3B. "
            "24 GB or more installed RAM is recommended. Close applications, "
            "check WSL memory limits, or use a shared GPU server. No fake-answer fallback."
        )
    return available
