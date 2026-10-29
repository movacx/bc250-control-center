"""Hardware and driver evidence a problem report carries on its own.

A support thread used to stall on "please run this and paste the output":
which NCT module is loaded, what hwmon sees, what the kernel said about the
fan chip or the GPU, which services run, which headers exist. Everything here
is collected without privileges and without a password prompt, each command
bounded by a timeout, so the report can carry it the moment it is sent.

Nothing here writes, loads a module or asks for root. ``dmesg`` is often
restricted to root (kernel.dmesg_restrict); the kernel journal is tried first
because desktop users in the wheel or systemd-journal group may read it.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bc250cc.shared.error_origins import redact

COMMAND_TIMEOUT_S = 4.0
#: One section never crowds the others out of the form's answer.
SECTION_LIMIT = 2500
#: Logs get more room: the line that explains the failure is often in them.
LOG_SECTION_LIMIT = 4500
TOTAL_LIMIT = 30000

#: The fan chip and sensors: every line of the boot, they are few and they say
#: which chip answered, what the driver refused and whether it tainted.
_FAN_LOG = re.compile(
    r"nct6[0-9]{3}|it87|super ?i/?o|hwmon|lm.?sensors|module verification|taint|dkms|"
    r"acpi.*(?:conflict|resource)|resource conflict|ec firmware",
    re.IGNORECASE,
)
#: GPU and crash lines, without the boot inventory (rings, planes, VM engines).
_GPU_LOG = re.compile(
    r"(?:amdgpu|drm|radeon|\bgpu\b).*(?:error|fail|timeout|\breset\b|wedged|\bfault\b|\bhang|coredump|"
    r"unsupported|throttl|refused|invalid|not supported)|"
    r"kernel: (?-i:WARNING|RIP|BUG):|\boops\b|call trace|segfault|general protection|page fault|"
    r"soft lockup|hard lockup|watchdog: (?:bug|.*stuck)|mce: \[hardware error\]|machine check|"
    r"hardware error|reset reason|thermal.*(?:critical|shutdown|trip|emergency)|throttl|"
    r"out of memory|oom-kill",
    re.IGNORECASE,
)
#: A clean end of a boot leaves one of these in its journal.
_CLEAN_END = re.compile(r"systemd-shutdown|reboot: (?:restarting|power down)|System Power Off|Reached target .*(?:Power-Off|Reboot|Shutdown)", re.IGNORECASE)
POLKIT_TIMEOUT_S = 90.0

_UNITS = (
    "cyan-skillfish-governor-smu.service",
    "oberon-governor.service",
    "bc250-smu-oc.service",
    "bc250-fan-control.service",
    "nct6687-load.service",
    "bc250-cu-live-manager.service",
)
_OPENRC_SERVICES = ("cyan-skillfish-governor-smu", "oberon-governor", "bc250-smu-oc", "bc250-fan-control")
_PACKAGE_PATTERN = re.compile(
    r"^(?:linux|kernel|mesa|vulkan-radeon|mesa-vulkan|dkms|nct|umr|python-?pyqt6|python3-pyqt6|"
    r"bc250|cyan|oberon|polkit|steamos|lm.?sensors|libdrm|firmware|amd)",
    re.IGNORECASE,
)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _run(argv: list[str], *, merge: bool = False, timeout: float = COMMAND_TIMEOUT_S) -> str:
    if not shutil.which(argv[0]):
        return ""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "HOME": str(Path.home())},
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = result.stdout or ""
    if merge and result.stderr:
        text += result.stderr
    return text.strip()


def _read(path: str | Path, limit: int = 8192) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit).strip()
    except OSError:
        return ""


def _kernel() -> str:
    release = platform.release()
    build = Path("/usr/lib/modules") / release / "build"
    if not build.exists():
        build = Path("/lib/modules") / release / "build"
    headers = "present" if (build / "Makefile").exists() else "missing"
    return "\n".join((
        _run(["uname", "-a"]) or release,
        f"headers for the running kernel: {headers} ({build})",
        f"tainted: {_read('/proc/sys/kernel/tainted') or '?'}",
        f"secure boot: {_run(['mokutil', '--sb-state']) or 'unknown'}",
        f"uptime: {(_read('/proc/uptime').split(' ') or ['?'])[0]} s",
    ))


def _modules() -> str:
    loaded = _run(["lsmod"]).splitlines()
    wanted = [line for line in loaded if re.match(r"(nct|it87|k10temp|amdgpu|zenpower|ryzen_smu)", line)]
    lines = wanted or ["(none of nct*, it87, k10temp, amdgpu, zenpower, ryzen_smu is loaded)"]
    for module in ("nct6687", "nct6683"):
        vermagic = _run(["modinfo", "-F", "vermagic", module])
        filename = _run(["modinfo", "-F", "filename", module])
        if vermagic or filename:
            lines.append(f"{module}: {filename or '?'} · vermagic {vermagic or '?'}")
    private = Path("/var/lib/nct6687/nct6687.ko")
    if private.exists():
        lines.append(f"{private}: vermagic {_run(['modinfo', '-F', 'vermagic', str(private)]) or '?'}")
    for pattern in ("/etc/modprobe.d/*nct*", "/etc/modprobe.d/sensors.conf",
                    "/etc/modules-load.d/*nct*", "/etc/modules-load.d/99-sensors.conf"):
        for path in sorted(glob.glob(pattern)):
            lines.append(f"{path}: {' | '.join(_read(path).splitlines())}")
    return "\n".join(lines)


def _hwmon_number(path: str) -> int:
    digits = re.sub(r"\D", "", path)
    return int(digits) if digits else 0


def _hwmon() -> str:
    lines = []
    for directory in sorted(glob.glob("/sys/class/hwmon/hwmon*"), key=_hwmon_number):
        name = _read(f"{directory}/name") or "?"
        fans = sorted(Path(directory).glob("fan*_input"))
        pwms = sorted(p for p in Path(directory).glob("pwm[0-9]") if p.is_file())
        temps = sorted(Path(directory).glob("temp*_input"))
        detail = [f"{len(fans)} fan", f"{len(pwms)} pwm", f"{len(temps)} temp"]
        if fans:
            detail.append("rpm " + ",".join(_read(p) or "?" for p in fans[:8]))
        if pwms:
            detail.append("pwm/enable " + ",".join(
                f"{_read(p) or '?'}/{_read(f'{p}_enable') or '?'}" for p in pwms[:8]
            ))
        if temps:
            values = []
            for path in temps[:6]:
                raw = _read(path)
                values.append(str(int(raw) // 1000) if raw.lstrip("-").isdigit() else "?")
            detail.append("°C " + ",".join(values))
        lines.append(f"{directory}: {name} · {' · '.join(detail)}")
    return "\n".join(lines) or "(no hwmon devices)"


def _kernel_text(boot: str = "0") -> tuple[str, str]:
    """The whole kernel log of one boot, and where it came from.

    The journal first (readable by wheel and systemd-journal members), then
    dmesg, and for the running boot, when both are closed to this user, dmesg
    through polkit: the desktop asks for the password once.
    """
    text = _run(["journalctl", "-k", "-b", boot, "--no-pager", "-o", "short-monotonic", "-q"], timeout=15)
    if text or boot != "0":
        return text, "journalctl -k"
    text = _run(["dmesg"])
    if text:
        return text, "dmesg"
    dmesg = shutil.which("dmesg") or "/usr/bin/dmesg"
    text = _run(["pkexec", dmesg], timeout=POLKIT_TIMEOUT_S)
    return text, "dmesg via polkit"


def kernel_log_needs_password() -> bool:
    """True when only polkit could read the running boot's kernel log.

    Cheap and unprivileged, so the report form can warn before the password
    dialog appears. Never raises.
    """
    try:
        if _run(["journalctl", "-k", "-b", "-n", "1", "-q", "--no-pager"], timeout=1):
            return False
        return not _run(["dmesg"], timeout=1)
    except Exception:  # noqa: BLE001 - a warning must never break the form
        return False


_KERNEL_CACHE: dict[str, tuple[str, str]] = {}


def _kernel_cached(boot: str = "0") -> tuple[str, str]:
    if boot not in _KERNEL_CACHE:
        _KERNEL_CACHE[boot] = _kernel_text(boot)
    return _KERNEL_CACHE[boot]


#: Lines that name a module only in passing: the list printed under every
#: kernel warning, and its CPU/taint banner.
_NOISE = re.compile(r"Modules linked in:|ommand line:|kernel: CPU: \d+ UID:|kernel: Tainted: \[|kernel: Hardware name:")


def _filtered(pattern: re.Pattern, boot: str = "0", keep: int = 60) -> str:
    text, source = _kernel_cached(boot)
    if not text:
        return "(the kernel log could not be read, not even through polkit)"
    matches = _group_similar(
        line for line in text.splitlines() if pattern.search(line) and not _NOISE.search(line)
    )
    return f"[{source}, filtered]\n" + "\n".join(matches[-keep:] or ["(nothing this boot)"])


def _fan_log() -> str:
    return _filtered(_FAN_LOG)


def _kernel_log() -> str:
    return _filtered(_GPU_LOG)


def _previous_boot() -> str:
    """How the last boot ended: a freeze or a reset leaves no shutdown."""
    lines = []
    current, _source = _kernel_cached("0")
    reasons = [line.split("kernel:", 1)[-1].strip() for line in current.splitlines() if "reset reason" in line.lower()]
    lines.extend(reasons or ["reset reason: not reported by this CPU"])
    previous = _run(["journalctl", "-b", "-1", "--no-pager", "-o", "short-monotonic", "-q", "-n", "400"], timeout=15)
    if not previous:
        lines.append("previous boot: no journal (persistent journal off, or first boot)")
    else:
        clean = bool(_CLEAN_END.search(previous))
        lines.append("previous boot ended: " + ("cleanly (shutdown or reboot)" if clean
                                                 else "ABRUPTLY — no shutdown was logged (freeze, reset or power loss)"))
        tail = _collapse_repeats(previous.splitlines()[-15:])
        lines.append("[last lines of the previous boot]")
        lines.extend(tail)
        crash = _group_similar(
            line for line in _kernel_cached("-1")[0].splitlines()
            if _GPU_LOG.search(line) and not _NOISE.search(line)
        )
        if crash:
            lines.append("[GPU and crash lines of the previous boot]")
            lines.extend(crash[-25:])
    return "\n".join(lines)


def _black_box() -> str:
    from bc250cc.infrastructure.blackbox import last_session

    return last_session()


def _sensors() -> str:
    return _run(["sensors"]) or "(lm_sensors is not installed)"


_TIMESTAMP = re.compile(r"^\[\s*[\d.]+\]\s*(?:\S+\s+kernel:\s*)?")


_DIGITS = re.compile(r"\d+")


def _group_similar(lines) -> list[str]:
    """Each message once, at its first time, with how often it came back.

    Messages differing only in a number (``source=9``, ``source=10``) are the
    same message: a boot prints dozens of them and they would push a later
    ring timeout out of the report.
    """
    order: list[str] = []
    first: dict[str, str] = {}
    counts: dict[str, int] = {}
    for line in lines:
        key = _DIGITS.sub("#", _TIMESTAMP.sub("", line))
        if key not in first:
            first[key] = line
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
    return [first[key] + (f"  (×{counts[key]})" if counts[key] > 1 else "") for key in order]


def _collapse_repeats(lines) -> list[str]:
    """One line per run of the same message, so a spam of "Unsupported clock
    type" cannot push a ring timeout out of the report."""
    collapsed: list[str] = []
    previous, count = None, 0
    for line in lines:
        message = _TIMESTAMP.sub("", line)
        if message == previous:
            count += 1
            continue
        if count > 1:
            collapsed.append(f"  (previous line repeated {count} times)")
        collapsed.append(line)
        previous, count = message, 1
    if count > 1:
        collapsed.append(f"  (previous line repeated {count} times)")
    return collapsed


def _gpu() -> str:
    for device in sorted(glob.glob("/sys/class/drm/card*/device")):
        if _read(f"{device}/vendor") != "0x1002":
            continue
        lines = [f"{os.path.realpath(device)} · {_read(f'{device}/device')}"]
        for name in ("power_dpm_force_performance_level", "gpu_busy_percent", "pp_dpm_sclk",
                     "pp_dpm_mclk", "mem_info_vram_total", "mem_info_gtt_total"):
            value = _read(f"{device}/{name}")
            if value:
                lines.append(f"  {name}: {' | '.join(value.splitlines())}")
        return "\n".join(lines)
    return "(no AMD GPU in /sys/class/drm)"


def _system_setup_helper() -> str:
    """Explain the protected helper's decisions without changing the machine."""
    from bc250cc.infrastructure import system_setup

    state = system_setup.inventory()
    lines = [
        f"helper_available: {state.get('helper_available', False)}",
        f"reason: {state.get('reason') or '—'}",
    ]
    memory = state.get("memory") if isinstance(state.get("memory"), dict) else {}
    for key in ("supported", "reason", "policies", "policy_reasons", "configured_policy", "phase", "steamos", "zram", "zswap", "swap"):
        value = memory.get(key)
        if value not in (None, "", (), [], {}):
            lines.append(f"memory.{key}: {value}")
    for name in ("ttm", "vram"):
        values = state.get(name) if isinstance(state.get(name), dict) else {}
        for key in (("supported", "managed", "reason") if name == "ttm" else ("supported", "reason")):
            value = values.get(key)
            if value not in (None, "", (), [], {}):
                lines.append(f"{name}.{key}: {value}")
    lines.append("[raw helper run]")
    lines.extend(_raw_helper_run())
    return "\n".join(lines)


def _raw_helper_run() -> list[str]:
    """Run the helper exactly as the app does, but keep what inventory() swallows."""
    from bc250cc.infrastructure import system_setup

    helper = system_setup.HELPER
    try:
        info = helper.stat()
    except OSError:
        return [f"helper file: {helper} (missing)"]
    lines = [
        f"helper file: {helper} (owner uid {info.st_uid}, mode {info.st_mode & 0o7777:04o}, "
        f"symlink {helper.is_symlink()})",
        "python3: /usr/bin/python3",
    ]
    argv = ["/usr/bin/python3", "-I", str(helper), "status"]
    started = time.monotonic()
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return lines + ["exit code: none (timed out after 20 s)"]
    except (OSError, subprocess.SubprocessError) as error:
        return lines + [f"could not run: {error}"]
    elapsed = time.monotonic() - started
    lines.append(f"exit code: {result.returncode}")
    lines.append(f"elapsed: {elapsed:.2f} s")
    if elapsed > 8:
        lines.append("NOTE: slower than the app's 8 s limit; the app would disable the memory/TTM controls.")
    stderr = "\n".join((result.stderr or "").strip().splitlines()[-40:])
    if stderr:
        lines.append("stderr (last lines):\n" + stderr)
    try:
        json.loads(result.stdout)
    except ValueError:
        lines.append("stdout (not valid JSON):\n" + (result.stdout or "").strip()[:1500])
    return lines


def _is_steamos() -> bool:
    return bool(re.search(r'^ID="?steamos"?\s*$', _read("/etc/os-release"), re.MULTILINE))


def _steamos() -> str:
    if not _is_steamos():
        return "(not SteamOS)"
    fields = dict(re.findall(r"^(VERSION_ID|BUILD_ID)=(.*)$", _read("/etc/os-release"), re.MULTILINE))
    lines = [f"{key}: {fields.get(key, '—').strip(chr(34))}" for key in ("VERSION_ID", "BUILD_ID")]
    lines.append("steamos-readonly: " + (_run(["steamos-readonly", "status"], merge=True) or "unavailable"))
    # status-json is explicitly read-only; never use the setup/install commands
    # here, because a diagnostics report must never prompt for a password.
    from bc250cc.infrastructure.steamos_graphics_runtime import STEAMOS_GRAPHICS_BACKEND
    if STEAMOS_GRAPHICS_BACKEND.is_file():
        lines.append("[BC-250 graphics stack]")
        lines.append(_run(["/usr/bin/bash", str(STEAMOS_GRAPHICS_BACKEND), "status-json"], merge=True) or "status unavailable")
    else:
        lines.append("BC-250 graphics stack: backend not staged")
    return "\n".join(lines)


def _graphics_stack() -> str:
    lines = [f"VK_ICD_FILENAMES: {os.environ.get('VK_ICD_FILENAMES') or '(not set)'}"]
    manifests = sorted(glob.glob("/usr/share/vulkan/icd.d/*.json"))
    # Only an AMD driver can run on the BC-250: the others (asahi, broadcom,
    # intel...) filled half the section in every report, so they are named.
    amd = [path for path in manifests if re.search(r"radeon|amd|radv", Path(path).name, re.I)]
    lines.extend(f"ICD: {path}\n{_read(path, 2048) or '(unreadable)'}" for path in amd)
    others = [Path(path).name for path in manifests if path not in amd]
    if others:
        lines.append("other ICDs: " + ", ".join(others))
    summary = _run(["vulkaninfo", "--summary"], merge=True)
    lines.append("[vulkaninfo --summary]\n" + (summary or "vulkaninfo is not installed or did not answer"))
    return "\n".join(lines)


def _services() -> str:
    lines = []
    if shutil.which("systemctl") and Path("/run/systemd/system").exists():
        for unit in _UNITS:
            active = (_run(["systemctl", "is-active", unit], merge=True) or "?").splitlines()[0]
            enabled = (_run(["systemctl", "is-enabled", unit], merge=True) or "?").splitlines()[0]
            if active == "inactive" and enabled in {"disabled", "not-found"} or "not-found" in enabled:
                continue
            lines.append(f"{unit}: {active} · {enabled}")
        failed = _run(["systemctl", "--failed", "--no-legend", "--plain"])
        lines.append("failed units: " + (" | ".join(failed.splitlines()) or "none"))
        for unit in ("cyan-skillfish-governor-smu.service", "nct6687-load.service", "bc250-fan-control.service"):
            journal = _run(["journalctl", "-u", unit, "-b", "--no-pager", "-n", "15", "-o", "cat"])
            if journal and "No entries" not in journal:
                lines.append(f"[{unit}]\n{journal}")
    elif Path("/run/openrc/softlevel").exists():
        for service in _OPENRC_SERVICES:
            if Path(f"/etc/init.d/{service}").exists():
                lines.append(f"{service}: {_run(['rc-service', service, 'status'], merge=True) or '?'}")
        lines.append(_run(["rc-status", "--crashed"]) or "crashed services: none")
    return "\n".join(lines) or "(no known services)"


def _packages() -> str:
    if shutil.which("pacman"):
        listed = _run(["pacman", "-Q"])
    elif shutil.which("dpkg-query"):
        listed = _run(["dpkg-query", "-W", "-f", "${Package} ${Version}\n"])
    elif shutil.which("rpm"):
        listed = _run(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}-%{RELEASE}\n"])
    elif shutil.which("apk"):
        listed = _run(["apk", "info", "-v"])
    else:
        listed = ""
    lines = sorted(line for line in listed.splitlines() if _PACKAGE_PATTERN.match(line))
    extra = []
    if shutil.which("rpm-ostree"):
        extra.append(_run(["rpm-ostree", "status", "--booted"]))
    if shutil.which("steamos-readonly"):
        extra.append("steamos-readonly: " + (_run(["steamos-readonly", "status"], merge=True) or "?"))
    if shutil.which("dkms"):
        extra.append("dkms: " + (" | ".join(_run(["dkms", "status"]).splitlines()) or "no modules"))
    return "\n".join([*lines[:120], *filter(None, extra)]) or "(package list unavailable)"


def _storage() -> str:
    rows = _run(["df", "-h", "--output=source,target,size,avail,pcent", "/", "/var", "/boot", "/home", "/tmp"]).splitlines()
    seen, unique = set(), []
    for row in rows:
        source = row.split(" ", 1)[0]
        if source not in seen:
            seen.add(source)
            unique.append(row)
    return "\n".join(unique) or "?"


def _control_center() -> str:
    lines = []
    libexec = Path("/usr/libexec/bc250-control-center")
    if libexec.is_dir():
        for path in sorted(libexec.iterdir()):
            try:
                info = path.stat()
            except OSError:
                continue
            lines.append(f"{path.name} · {info.st_size} B · uid {info.st_uid} · {oct(info.st_mode & 0o7777)}")
    else:
        lines.append(f"{libexec}: missing")
    lines.extend(f"{path}: present" for path in sorted(glob.glob("/etc/bc250-control-center/*")))
    for config in ("/etc/cyan-skillfish-governor-smu/config.toml", "/etc/bc250-smu-oc.conf"):
        if Path(config).exists():
            body = [row.strip() for row in _read(config, 16384).splitlines()]
            lines.append(f"[{config}]\n" + "\n".join(row for row in body if row and not row.startswith("#")))
    plugins = Path.home() / "homebrew" / "plugins"
    if plugins.is_dir():
        lines.append("decky plugins: " + ", ".join(sorted(p.name for p in plugins.iterdir())))
    return "\n".join(lines)


def workflow_log_directory() -> Path:
    state = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(state) if state else Path.home() / ".local" / "state"
    return root / "bc250-control-center" / "terminal"


def _last_workflow_log() -> str:
    logs = []
    for path in workflow_log_directory().glob("workflow-*.log"):
        try:
            logs.append((path.stat().st_mtime, path))
        except OSError:
            continue
    if not logs:
        return "(no workflow has been run from the app yet)"
    latest = max(logs)[1]
    tail = _ANSI.sub("", _read(latest, 400_000)).splitlines()[-60:]
    return f"[{latest.name}]\n" + "\n".join(tail)


SECTIONS = (
    ("Kernel", _kernel),
    ("Previous boot", _previous_boot),
    ("Black box", _black_box),
    ("Modules", _modules),
    ("Kernel log: fan chip and sensors", _fan_log),
    ("Sensors (hwmon)", _hwmon),
    ("sensors", _sensors),
    ("Kernel log: GPU and crashes", _kernel_log),
    ("GPU", _gpu),
    ("Graphics stack", _graphics_stack),
    ("System setup helper", _system_setup_helper),
    ("SteamOS", _steamos),
    ("Services", _services),
    ("Last workflow log", _last_workflow_log),
    ("Packages", _packages),
    ("Storage", _storage),
    ("Control Center files", _control_center),
)


_KERNEL_READERS = frozenset({_fan_log, _kernel_log, _previous_boot})

#: Logs end with what matters, so they keep their last lines when cut.
_TAIL_SECTIONS = frozenset({
    "Kernel log: fan chip and sensors", "Kernel log: GPU and crashes", "Last workflow log", "Black box",
})


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 20].rstrip() + "\n… (cut)"


def _clip_tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head, _, rest = text.partition("\n")
    return head + "\n(… earlier lines cut)\n" + rest[-(limit - len(head) - 40):].split("\n", 1)[-1]


def collect_diagnostics(
    sections=SECTIONS,
    *,
    section_limit: int = SECTION_LIMIT,
    log_limit: int = LOG_SECTION_LIMIT,
    total_limit: int = TOTAL_LIMIT,
    fresh: bool = True,
) -> str:
    """Every section as plain text, redacted and bounded for the form.

    The limits fit the report's own answer; the attachment sent after it
    asks for the same sections with far more room.
    """
    def one(item):
        title, read = item
        try:
            body = str(read() or "").strip() or "—"
        except Exception as error:  # noqa: BLE001 - one unreadable section must not hide the rest
            body = f"(could not be read: {type(error).__name__})"
        if title in _TAIL_SECTIONS or title == "Previous boot":
            clip = _clip_tail if title in _TAIL_SECTIONS else _clip
            return f"== {title} ==\n{clip(body, log_limit)}"
        return f"== {title} ==\n{_clip(body, section_limit)}"

    # Read once, before the sections run in parallel: a system that needs
    # polkit for the kernel log asks for the password a single time.
    # ``fresh=False`` reuses the log the report just read: on a system that
    # needs polkit for it, the full diagnosis must not ask a second time.
    if fresh:
        _KERNEL_CACHE.clear()
    if any(read in _KERNEL_READERS for _title, read in sections):
        _kernel_cached("0")
        _kernel_cached("-1")
    with ThreadPoolExecutor(max_workers=6) as pool:
        parts = list(pool.map(one, sections))
    # Home folders, and also the machine's name, addresses and ids: this text is pasted in public.
    from bc250cc.infrastructure.privacy import redact_machine

    return _clip(redact_machine("\n\n".join(parts)), total_limit)
