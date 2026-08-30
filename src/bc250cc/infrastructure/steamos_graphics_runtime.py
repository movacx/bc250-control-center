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
CURRENT_MESA_TAG = "mesa-26.2.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MESA_TAG = re.compile(r"^mesa-[0-9][0-9A-Za-z._-]*$")

STEAMOS_GRAPHICS_ACTIONS = frozenset({
    "status", "install", "install-fsr4", "uninstall", "uninstall-fsr4",
})


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
    command = {
        "status": f"/usr/bin/bash {qscript} status-json",
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
            f'/usr/bin/bash {qscript} status-json || true',
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
