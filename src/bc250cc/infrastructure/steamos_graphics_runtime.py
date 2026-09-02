"""Evidence and protected commands for the SteamOS RADV/FSR4 runtime.

The keyboardspecialist SteamOS toolkit deliberately keeps its build state in
the logged-in user's home directory. Control Center validates those manifests
without executing the mutable checkout. Explicit lifecycle actions execute
only the exact root-owned toolkit staged by ``steamos_amdgpu_backend``.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import Path

from .steamos_amdgpu_backend import STEAMOS_GRAPHICS_BACKEND

CURRENT_UPSTREAM_COMMIT = "d3e6dc062c34d2523db0abe5741d1f5b0dea00d9"
LEGACY_UPSTREAM_COMMIT = "b66203e012594204e5e3049856b28a2681112985"
CURRENT_FSR4_PATCH_SHA256 = (
    "7fde37fad572b4ba4dcac6052792d10d8d3df65982b01236c63a3eff0a25d225"
)
STEAMOS_FSR4_LAUNCH_OPTION = (
    '"$HOME/.local/share/bc250-mesh-shader/fsr4/bc250-fsr4-run" %command%'
)
CURRENT_MESA_TAG = "mesa-26.2.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MESA_TAG = re.compile(r"^mesa-[0-9][0-9A-Za-z._-]*$")

STEAMOS_GRAPHICS_ACTIONS = frozenset({
    "status", "install", "install-fsr4", "uninstall", "uninstall-fsr4",
})
STEAMOS_SYSTEM_STATUS_HELPER = Path(
    "/usr/libexec/bc250-control-center/bc250-quick-access-helper"
)


def _graphics_status_report_command(
    script: Path,
    *,
    system_helper: Path | None = STEAMOS_SYSTEM_STATUS_HELPER,
) -> str:
    """Render graphics JSON plus optional read-only BC250 telemetry."""
    qscript = shlex.quote(str(script))
    qhelper = shlex.quote(str(system_helper)) if system_helper is not None else ""
    formatter = r'''import hashlib, json, os, sys
from pathlib import Path
chunks = sys.stdin.buffer.read().split(b"\0", 1)
state = json.loads(chunks[0] or b"{}")
system = json.loads(chunks[1] or b"{}") if len(chunks) == 2 else {}
def flag(value, yes="Yes", no="No"):
    return yes if value is True else no if value is False else "Unknown"
def label(value):
    return str(value or "Unknown").replace("-", " ").title()
def reading(value, suffix=""):
    return f"{value}{suffix}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "Unavailable"
def runtime_parameter_enabled(path):
    try:
        value = Path(path).read_text(encoding="ascii", errors="strict").strip().lower()
    except (OSError, UnicodeError):
        return None
    if value in {"1", "y", "yes", "true", "on"}:
        return True
    if value in {"0", "n", "no", "false", "off"}:
        return False
    return None
def section(title, rows):
    print(f"\n== {title} ==")
    for name, value in rows:
        print(f"{name:<22} {value}")
def attested_module_marker(name):
    release = os.uname().release
    module = Path(f"/usr/lib/modules/{release}/updates/amdgpu.ko.zst")
    marker = module.parent / name
    try:
        expected = marker.read_text(encoding="ascii", errors="strict").strip()
        digest = hashlib.sha256(module.read_bytes()).hexdigest()
    except (OSError, UnicodeError):
        return False
    return len(expected) == 64 and expected == digest
games = state.get("games")
rows = [
    ("Backend script", flag(state.get("scriptAvailable"), "Available", "Missing")),
    ("Graphics runtime", label(state.get("runtimeState"))),
    ("Mesa version", str(state.get("mesaVersion") or "Not detected")),
    ("ICD configuration", flag(state.get("configValid"), "Valid", "Invalid")),
    ("Kernel compatibility", flag(state.get("kernelReady"), "Ready", "Not ready")),
    ("Scheduler configured", flag(state.get("schedulerConfigured"))),
    ("Scheduler active", flag(state.get("schedulerActive"), "Active", "Inactive")),
    ("Global override", flag(state.get("globalEnabled"), "Enabled", "Disabled")),
    ("Restart required", flag(state.get("restartRequired"))),
    ("FSR4", label(state.get("fsr4State"))),
    ("Configured games", str(len(games)) if isinstance(games, list) else "Unknown"),
]
print("== Graphics stack ==")
for name, value in rows:
    print(f"{name:<22} {value}")
icd = state.get("icdPath")
if icd:
    print(f"\nICD manifest\n  {icd}")
if isinstance(games, list) and games:
    print("\nConfigured games")
    for game in games:
        if isinstance(game, dict):
            game_name = game.get("name") or game.get("executable") or "Unknown game"
            executable = game.get("executable")
            suffix = f" ({executable})" if executable and executable != game_name else ""
            print(f"  - {game_name}{suffix}")
        else:
            print(f"  - {game}")
extended = system.get("ok") is True and system.get("protocol") == 13
if extended:
    active_cus = system.get("cu_active_cus")
    total_cus = system.get("cu_total_cus")
    cu_value = f"{active_cus} / {total_cus}" if isinstance(active_cus, int) and isinstance(total_cus, int) else "Unavailable"
    cu_masks = system.get("cu_masks")
    mask_value = " ".join(f"0x{item:02x}" for item in cu_masks) if isinstance(cu_masks, list) and all(isinstance(item, int) for item in cu_masks) else "Unavailable"
    section("Compute units", [
        ("Active CUs", cu_value),
        ("WGP topology", flag(isinstance(system.get("cu_masks"), list), "Available", "Unavailable")),
        ("Active WGP masks", mask_value),
        ("Boot service", flag(system.get("cu_service_enabled"), "Enabled", "Disabled")),
    ])
    gpu_range = system.get("gpu_range")
    range_value = f"{gpu_range[0]}-{gpu_range[1]} MHz" if isinstance(gpu_range, list) and len(gpu_range) == 2 else "Unavailable"
    section("GPU governor and sensors", [
        ("Governor", str(system.get("gpu_governor_label") or "Not active")),
        ("Governor active", flag(system.get("gpu_governor_active"), "Active", "Inactive")),
        ("Performance mode", flag(system.get("gpu_performance_enabled"), "Enabled", "Disabled")),
        ("Configured range", range_value),
        ("Core clock", reading(system.get("gpu_core_mhz"), " MHz")),
        ("Voltage", reading(system.get("gpu_voltage_mv"), " mV")),
        ("Memory clock", reading(system.get("gpu_memory_clock_mhz"), " MHz")),
        ("VRAM usage", (
            f"{system['gpu_vram_used_mib']} / {system['gpu_vram_total_mib']} MiB"
            if isinstance(system.get("gpu_vram_used_mib"), int) and isinstance(system.get("gpu_vram_total_mib"), int)
            else "Unavailable"
        )),
        ("GPU load", reading(system.get("gpu_busy_percent"), "%")),
        ("GPU temperature", reading(system.get("gpu_temperature_c"), " C")),
    ])
    profile = system.get("cpu_active_profile")
    profile = profile if isinstance(profile, dict) else {}
    profile_mode = label(profile.get("mode")) if profile else "Not active"
    section("CPU overclock and sensors", [
        ("Live clock", reading(system.get("cpu_frequency_mhz"), " MHz")),
        ("CPU temperature", reading(system.get("cpu_temperature_c"), " C")),
        ("CPU OC active", flag(bool(profile), "Active", "Inactive")),
        ("OC profile", profile_mode),
        ("Target clock", reading(profile.get("frequency"), " MHz")),
        ("Estimated VID", reading(profile.get("estimated_vid"), " mV")),
        ("Scale", reading(profile.get("scale"))),
        ("Thermal limit", reading(profile.get("temperature"), " C")),
        ("Boot service", flag(system.get("cpu_service_enabled"), "Enabled", "Disabled")),
    ])
    raw_duty = system.get("system_fan_duty")
    duty = f"{round(raw_duty * 100 / 255)}% (PWM {raw_duty})" if isinstance(raw_duty, int) else "Unavailable"
    channels = system.get("system_fan_channels")
    channel_value = ", ".join(f"PWM {item}" for item in channels) if isinstance(channels, list) and channels else "Unavailable"
    fan_options = system.get("fan_channel_options")
    rpm_values = []
    if isinstance(fan_options, list):
        for option in fan_options:
            if isinstance(option, dict) and isinstance(option.get("channel"), int) and isinstance(option.get("rpm"), int):
                rpm_values.append(f"PWM {option['channel']}: {option['rpm']} RPM")
    section("Cooling", [
        ("Fan preset", label(system.get("system_fan_preset"))),
        ("Fan output", duty),
        ("Detected channels", channel_value),
        ("Fan speeds", ", ".join(rpm_values) if rpm_values else "Unavailable"),
    ])
else:
    print("\n[WARN] Extended BC250 telemetry is unavailable; reinstall Control Center or prepare its dependencies.")
fixes = []
if state.get("kernelReady") is True:
    fixes.extend([
        ("ACTIVE", "AMDGPU DP audio compatibility quirk"),
        ("ACTIVE", "Cyan Skillfish GPU activity metrics"),
        ("ACTIVE", "Cyan Skillfish live GFX clock query"),
        ("ACTIVE", "Cyan Skillfish 300-2230 MHz control range"),
        ("ACTIVE", "AMDGPU TTM NULL-page cleanup guard"),
        ("ACTIVE", "GFX1013 MMIO PASID routing"),
        ("ACTIVE", "GFX1013 compute GFXOFF guard"),
        ("ACTIVE", "GFX1013 scoped PASID type-0 handling"),
        ("ACTIVE", "GFX1013 loaded-module attestation"),
    ])
    runlist_enabled = runtime_parameter_enabled(
        "/sys/module/amdgpu/parameters/bc250_flush_by_runlist"
    )
    if runlist_enabled is True:
        fixes.append(("ACTIVE", "KFD runlist TLB-flush workaround"))
    elif runlist_enabled is False:
        fixes.append(("AVAILABLE", "KFD runlist TLB-flush workaround (disabled)"))
    else:
        fixes.append(("COMPILED", "KFD runlist TLB-flush support"))
    if os.uname().release.startswith("6.16."):
        fixes.insert(0, ("ACTIVE", "DCN 2.01 display clock selection"))
if attested_module_marker(".bc250-control-center-telemetry-oc-2400"):
    fixes.append(("ACTIVE", "BC250 500-2400 MHz read-only telemetry range"))
if state.get("schedulerActive") is True:
    fixes.append(("ACTIVE", "AMDGPU scheduler policy 2"))
elif state.get("schedulerConfigured") is True:
    fixes.append(("CONFIGURED", "AMDGPU scheduler policy 2 (restart required)"))
if state.get("runtimeState") == "ready":
    radv_status = "ACTIVE" if state.get("globalEnabled") is True else "INSTALLED"
    radv_suffix = "" if radv_status == "ACTIVE" else " (restart required)" if state.get("restartRequired") is True else ""
    fixes.extend([
        (radv_status, "RADV GFX1013 compute-queue fix" + radv_suffix),
        (radv_status, "RADV GFX1013 mesh/task shaders" + radv_suffix),
        (radv_status, "RADV GFX1013 task-mesh queries" + radv_suffix),
    ])
if state.get("fsr4State") == "ready":
    fixes.append(("INSTALLED", "BC250 FSR4 V3 per-game profile"))
print("\n== Verified fixes ==")
if fixes:
    for status, name in fixes:
        print(f"[{status:<10}] {name}")
else:
    print("No verified BC250 patch markers were detected.")
error = state.get("error")
if error:
    print(f"\nERROR: {error}")
elif state.get("restartRequired") is True:
    print("\n[WARN] Restart is required to activate all graphics changes.")
else:
    print("\n[OK] SteamOS graphics status was read successfully.")'''
    helper_probe = "system_status_json='{}'; "
    if system_helper is not None:
        helper_probe += (
            f'if sudo test -f {qhelper} && sudo test ! -L {qhelper} && '
            f'[ "$(sudo stat -c %u:%a {qhelper})" = "0:755" ]; then '
            f'if system_status_json="$(sudo {qhelper} status)"; then :; '
            'else system_status_json=\'{}\'; fi; fi; '
        )
    return (
        f'if graphics_status_json="$(/usr/bin/bash {qscript} status-json)"; '
        'then graphics_status_rc=0; else graphics_status_rc=$?; fi; '
        f'{helper_probe}'
        f'printf "%s\\0%s" "$graphics_status_json" "$system_status_json" | '
        f'/usr/bin/python3 -c {shlex.quote(formatter)} && '
        '[ "$graphics_status_rc" -eq 0 ]'
    )


def build_steamos_graphics_command(
    action: str,
    *,
    checkout_command: str = ":",
    backend_guard: str,
    script: Path = STEAMOS_GRAPHICS_BACKEND,
) -> str:
    """Build one finite lifecycle command against the protected toolkit.

    The mutable ResourceTools checkout may only be used by ``checkout_command``
    to stage an exact reviewed Git tree. It is never invoked directly.
    """
    action = str(action or "").strip().lower()
    if action not in STEAMOS_GRAPHICS_ACTIONS:
        raise ValueError(f"Unsupported SteamOS graphics action: {action}")
    qscript = shlex.quote(str(script))
    guard = str(backend_guard or "").strip()
    if not guard:
        raise ValueError("SteamOS graphics commands require a protected backend guard.")
    status_report = _graphics_status_report_command(script)
    command = {
        "status": status_report,
        "install": f"/usr/bin/bash {qscript} setup",
        "install-fsr4": f"/usr/bin/bash {qscript} setup --fsr4",
        "uninstall": f"/usr/bin/bash {qscript} uninstall",
        "uninstall-fsr4": f"/usr/bin/bash {qscript} uninstall --fsr4",
    }[action]
    mutation = action != "status"
    steps = [
        'echo "== SteamOS BC-250 graphics stack =="',
        'grep -Eiq "steamos|steamdeck|holo" /etc/os-release || { echo "ERROR: this workflow is available only on SteamOS"; exit 39; }',
    ]
    if mutation:
        steps.append(str(checkout_command or ":").strip())
    steps.extend((
        f'{guard} || {{ echo "ERROR: the reviewed root-owned SteamOS graphics backend is unavailable or changed"; exit 38; }}',
        command,
    ))
    if mutation:
        steps.extend((
            'echo "== Verified post-action state =="',
            f'{status_report} || true',
        ))
    return "; ".join(steps)


def _regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _regular_directory(path: Path) -> bool:
    try:
        return path.is_dir() and not path.is_symlink()
    except OSError:
        return False


def _sha256(path: Path) -> str:
    if not _regular_file(path):
        return ""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return ""
    return digest.hexdigest()


def _tokens(path: Path, count: int) -> tuple[str, ...] | None:
    if not _regular_file(path):
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if len(lines) != 1:
        return None
    values = tuple(lines[0].split())
    return values if len(values) == count else None


def _global_runtime_state(
    *, state_dir: Path, driver_path: Path, icd_path: Path
) -> dict[str, object]:
    manifest = state_dir / "install.conf"
    artifacts_present = any(
        path.exists() or path.is_symlink()
        for path in (manifest, driver_path, icd_path, state_dir / "install-transaction")
    )
    values = _tokens(manifest, 4)
    if values is None:
        return {
            "state": "invalid" if artifacts_present else "not-installed",
            "present": artifacts_present,
            "ready": False,
            "current": False,
            "legacy": False,
            "mesa_tag": "",
            "upstream_commit": "",
        }
    driver_sha, icd_sha, mesa_tag, upstream_commit = values
    manifest_valid = bool(
        _SHA256.fullmatch(driver_sha)
        and _SHA256.fullmatch(icd_sha)
        and _MESA_TAG.fullmatch(mesa_tag)
        and upstream_commit in {CURRENT_UPSTREAM_COMMIT, LEGACY_UPSTREAM_COMMIT}
    )
    intact = bool(
        manifest_valid
        and _regular_directory(state_dir)
        and _sha256(driver_path) == driver_sha
        and _sha256(icd_path) == icd_sha
    )
    current = bool(
        intact
        and upstream_commit == CURRENT_UPSTREAM_COMMIT
        and mesa_tag == CURRENT_MESA_TAG
    )
    return {
        "state": "ready" if intact else "invalid",
        "present": True,
        "ready": intact,
        "current": current,
        "legacy": bool(intact and upstream_commit == LEGACY_UPSTREAM_COMMIT),
        "mesa_tag": mesa_tag if manifest_valid else "",
        "upstream_commit": upstream_commit if manifest_valid else "",
    }


def _fsr4_runtime_state(*, state_dir: Path) -> dict[str, object]:
    profile = state_dir / "fsr4"
    manifest = profile / "install.conf"
    driver = profile / "libvulkan_radeon.so"
    icd = profile / "radeon_fsr4_icd.x86_64.json"
    runner = profile / "bc250-fsr4-run"
    artifacts_present = any(
        path.exists() or path.is_symlink()
        for path in (profile, state_dir / "fsr4-install-transaction")
    )
    values = _tokens(manifest, 5)
    if values is None:
        return {
            "state": "invalid" if artifacts_present else "not-installed",
            "present": artifacts_present,
            "ready": False,
            "current": False,
            "mesa_tag": "",
            "runner_path": "",
            "steam_launch_option": "",
        }
    driver_sha, icd_sha, runner_sha, mesa_tag, patch_sha = values
    manifest_valid = bool(
        all(_SHA256.fullmatch(item) for item in (driver_sha, icd_sha, runner_sha, patch_sha))
        and _MESA_TAG.fullmatch(mesa_tag)
    )
    try:
        runner_executable = bool(runner.stat().st_mode & 0o111)
    except OSError:
        runner_executable = False
    intact = bool(
        manifest_valid
        and _regular_directory(profile)
        and _sha256(driver) == driver_sha
        and _sha256(icd) == icd_sha
        and _sha256(runner) == runner_sha
        and runner_executable
    )
    current = bool(
        intact
        and mesa_tag == CURRENT_MESA_TAG
        and patch_sha == CURRENT_FSR4_PATCH_SHA256
    )
    return {
        "state": "ready" if intact else "invalid",
        "present": True,
        "ready": intact,
        "current": current,
        "mesa_tag": mesa_tag if manifest_valid else "",
        "runner_path": str(runner) if current else "",
        "steam_launch_option": STEAMOS_FSR4_LAUNCH_OPTION if current else "",
    }


def probe_steamos_graphics_runtime(
    *,
    home: Path | None = None,
    driver_path: Path | None = None,
    icd_path: Path | None = None,
) -> dict[str, object]:
    """Return non-invasive evidence for the reviewed SteamOS graphics stack.

    ``driver_path`` and ``icd_path`` are injectable only for tests.  Production
    uses the fixed paths declared by the reviewed external runtime.
    """
    home = Path.home() if home is None else Path(home)
    state_dir = home / ".local" / "share" / "bc250-mesh-shader"
    global_runtime = _global_runtime_state(
        state_dir=state_dir,
        driver_path=driver_path or Path("/usr/lib/libvulkan_radeon_driconf.so"),
        icd_path=icd_path or home / "radeon_driconf_icd.x86_64.json",
    )
    fsr4 = _fsr4_runtime_state(state_dir=state_dir)
    return {
        "upstream": "https://github.com/keyboardspecialist/bc250-steamos",
        "state_dir": str(state_dir),
        "radv": global_runtime,
        "fsr4": fsr4,
        "legacy_radv_detected": bool(global_runtime["legacy"]),
        "incomplete": bool(
            global_runtime["state"] == "invalid" or fsr4["state"] == "invalid"
        ),
    }
