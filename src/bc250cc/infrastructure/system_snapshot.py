"""The facts a problem report needs, read once and without privileges.

What a support thread asks first, in one place: the version and how it was
installed, the distribution, the kernel and its options, the BIOS, the cores
the firmware left running, the GPU and its VBIOS, Mesa, and which governor
runs. Every read is bounded and fails to "—" rather than raising, because a
missing file is itself worth reporting.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from bc250cc.infrastructure.gpu_reset_log import read_gpu_resets
from bc250cc.infrastructure.install_source import UpdateChannel, detect_install_source
from bc250cc.shared.version import application_version

UNKNOWN = "—"
QUERY_TIMEOUT_S = 3.0
#: Boot options that identify disks or keys, never useful in a report.
_PRIVATE_OPTIONS = re.compile(
    r"^(?:root|resume|cryptdevice|rd\.luks\.[a-z]+|luks\.[a-z]+|cryptkey|BOOT_IMAGE|initrd)=",
    re.IGNORECASE,
)
GOVERNOR_UNITS = (
    ("cyan-skillfish-governor-smu.service", "Cyan"),
    ("oberon-governor.service", "Oberon"),
)


def _read(path: str | Path, limit: int = 65536) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit).strip()
    except OSError:
        return ""


def _run(argv: list[str]) -> str:
    if not shutil.which(argv[0]):
        return ""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=QUERY_TIMEOUT_S, check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (_read("/etc/os-release") or _read("/usr/lib/os-release")).splitlines():
        key, _, value = line.partition("=")
        if key:
            values[key.strip()] = value.strip().strip('"')
    return values


def _installation(root: Path) -> str:
    if (root / ".git").exists():
        return "Source checkout"
    source = detect_install_source()
    if source.channel is UpdateChannel.AUR:
        return f"AUR ({source.package})"
    if source.channel is UpdateChannel.PACKAGE:
        return f"Package ({source.manager}: {source.package})"
    return f"install-local.sh ({root.parent.parent})" if root.parent.name == "share" else f"Script ({root})"


def _kernel_options() -> str:
    options = [option for option in _read("/proc/cmdline").split() if not _PRIVATE_OPTIONS.match(option)]
    return " ".join(options) or UNKNOWN


def _cpu() -> str:
    text = _read("/proc/cpuinfo", 1 << 20)
    model = next(
        (line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("model name")),
        platform.processor() or UNKNOWN,
    )
    cores = {
        (block.get("physical id", "0"), block.get("core id", str(index)))
        for index, block in enumerate(
            dict(
                (key.strip(), value.strip())
                for key, _, value in (line.partition(":") for line in chunk.splitlines())
            )
            for chunk in text.split("\n\n") if chunk.strip()
        )
    }
    threads = os.cpu_count() or 0
    return f"{model} · {len(cores)} cores / {threads} threads" if cores else model


def _memory() -> str:
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB", _read("/proc/meminfo"), re.MULTILINE)
    return f"{int(match.group(1)) / 1024 / 1024:.1f} GiB" if match else UNKNOWN


def _amdgpu_device() -> Path | None:
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        device = card / "device"
        if "-" not in card.name and (device / "vbios_version").exists():
            return device
    return None


def _gpu() -> str:
    device = _amdgpu_device()
    if device is None:
        return UNKNOWN
    parts = [f"VBIOS {_read(device / 'vbios_version') or UNKNOWN}"]
    vram = _read(device / "mem_info_vram_total")
    if vram.isdigit():
        parts.append(f"{int(vram) / 1024 ** 3:.1f} GiB VRAM")
    gtt = _read(device / "mem_info_gtt_total")
    if gtt.isdigit():
        parts.append(f"{int(gtt) / 1024 ** 3:.1f} GiB GTT")
    return " · ".join(parts)


def _mesa() -> str:
    for argv in (
        ["pacman", "-Q", "mesa"],
        ["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", "mesa-vulkan-drivers"],
        ["dpkg-query", "-W", "-f", "${Version}", "mesa-vulkan-drivers"],
    ):
        answer = _run(argv)
        if answer:
            return answer.split()[-1]
    return UNKNOWN


def _vulkan_driver() -> str:
    """The Vulkan driver a game really gets, which the package manager may not know.

    A per-user RADV build (FSR4, async compute) never shows up in ``pacman -Q mesa``.
    """
    text = _run(["vulkaninfo", "--summary"])
    device = driver = ""
    for line in text.splitlines():
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "deviceName" and not device and "llvmpipe" not in value.lower():
            device = value
        elif key == "driverInfo" and device and not driver:
            driver = value
    return " · ".join(part for part in (device, driver) if part) or UNKNOWN


def _gpu_resets() -> str:
    summary = read_gpu_resets()
    return summary.label() if summary is not None else UNKNOWN


def _governor() -> str:
    running = [name for unit, name in GOVERNOR_UNITS if _run(["systemctl", "is-active", unit]) == "active"]
    return ", ".join(running) if running else "None running"


def _session() -> str:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or UNKNOWN
    kind = os.environ.get("XDG_SESSION_TYPE") or ""
    if os.environ.get("GAMESCOPE_WAYLAND_DISPLAY") or os.environ.get("SteamGamepadUI"):
        desktop = f"Game Mode ({desktop})"
    return f"{desktop} · {kind}" if kind else desktop


def system_snapshot(project_root: Path | None = None) -> list[tuple[str, str]]:
    """``(label, value)`` rows; labels are English catalogue keys."""
    root = project_root if project_root is not None else Path(__file__).resolve().parents[3]
    release = _os_release()
    bios = " · ".join(filter(None, (
        _read("/sys/class/dmi/id/bios_version"),
        _read("/sys/class/dmi/id/bios_date"),
        _read("/sys/class/dmi/id/board_name"),
    ))) or UNKNOWN
    rows: list[tuple[str, Callable[[], str]]] = [
        ("Control Center", lambda: application_version()),
        ("Installation", lambda: _installation(root)),
        ("Operating system", lambda: release.get("PRETTY_NAME") or release.get("NAME") or UNKNOWN),
        ("Kernel", platform.release),
        ("Kernel options", _kernel_options),
        ("BIOS", lambda: bios),
        ("Processor", _cpu),
        ("Memory", _memory),
        ("Graphics", _gpu),
        ("Mesa", _mesa),
        ("Vulkan driver", _vulkan_driver),
        ("GPU governor", _governor),
        ("GPU resets", _gpu_resets),
        ("Session", _session),
        ("Python", lambda: platform.python_version()),
    ]
    snapshot = []
    for label, read in rows:
        try:
            value = str(read() or UNKNOWN)
        except Exception:  # noqa: BLE001 - one unreadable fact must not hide the rest
            value = UNKNOWN
        snapshot.append((label, value))
    return snapshot
