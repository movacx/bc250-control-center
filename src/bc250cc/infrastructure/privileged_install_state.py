"""Whether the root helpers on this system belong to the running version.

Both installers copy ``privileged/`` byte for byte to
``/usr/libexec/bc250-control-center`` and keep the same tree beside the
application, so the two copies can be compared without root. A difference
means the privileged half is from another version: a local install that
skipped the helpers, an update that stopped half way, or a checkout run
from a source tree. Features backed by an older helper then fail with
errors that do not name the cause.

Nothing is reported unless the answer is certain: with no helper
installed at all (an rpm-ostree script install, a SteamOS update that
reset /usr) or no copy beside the application, the state is ``unknown``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

INSTALLED_ROOT = Path("/usr/libexec/bc250-control-center")
#: Every file both installers put under INSTALLED_ROOT from ``privileged/``.
HELPERS = (
    "bc250-system-setup-helper",
    "bc250-cu-helper",
    "bc250-fan-pwm-helper",
    "bc250-cyan-overlay-preflight",
    "bc250-steamos-game-helper",
    "bc250-governor-config-helper",
    "bc250-quick-access-helper",
    "bc250-core-unlock-helper",
    "bc250-cpu-smu-helper",
    "bc250-gddr6-temp-helper",
    "bc250-gddr6-temp-reader",
    "bc250-openrc-service-helper",
    "bc250-service-helper",
    "bc250-maintenance-helper",
)
LIBRARIES = (
    "system_setup_common.py",
    "system_setup_memory.py",
    "system_setup_acpi.py",
    "system_setup_telemetry.py",
    "system_setup_kernel_args.py",
    "system_setup_ttm.py",
    "system_setup_vram.py",
    "acpi_payload.py",
    "bc250_contract.py",
    "governor_toml.py",
    "bc250_smu_oc_vendor.zip",
)
#: Far above any helper; a larger file is not one of ours.
_MAX_BYTES = 8 * 1024 * 1024


def _pairs(project_root: Path, installed_root: Path) -> list[tuple[Path, Path]]:
    source = project_root / "privileged"
    return [
        (source / "helpers" / name, installed_root / name) for name in HELPERS
    ] + [
        (source / "lib" / name, installed_root / "lib" / name) for name in LIBRARIES
    ]


def _read(path: Path) -> bytes | None:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


#: Package manager query for "which package owns this file", most specific first.
_OWNER_QUERIES = (
    ("pacman", ("pacman", "-Qqo"), None),
    ("rpm", ("rpm", "-qf", "--qf", "%{NAME}\\n"), None),
    ("dpkg", ("dpkg-query", "-S"), "dpkg"),
)


def owning_package(path: Path) -> str:
    """The package a file belongs to, or ``""`` when no manager claims it.

    A local install copies over files a package still owns; the fix for that
    is the package manager, not another local install on top.
    """
    for _name, command, parser in _OWNER_QUERIES:
        if shutil.which(command[0]) is None:
            continue
        try:
            done = subprocess.run(
                [*command, str(path)], capture_output=True, text=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode != 0:
            continue
        line = done.stdout.strip().splitlines()[0].strip() if done.stdout.strip() else ""
        if parser == "dpkg":
            # "package[:arch]: /path"
            line = line.split(":", 1)[0]
        if line and not line.startswith(("error", "file ")):
            return line
    return ""


def privileged_install_state(
    project_root: Path | None = None,
    installed_root: Path = INSTALLED_ROOT,
) -> dict:
    """``current``, ``outdated`` (with the names that differ) or ``unknown``."""
    root = project_root if project_root is not None else Path(__file__).resolve().parents[3]
    outdated: list[str] = []
    compared = 0
    for source, installed in _pairs(root, installed_root):
        expected = _read(source)
        if expected is None:
            # This build does not carry the file (or cannot read it): nothing
            # to hold the installed copy against.
            continue
        present = _read(installed)
        if present is None:
            if installed.exists() or installed.is_symlink():
                # There, but not a readable regular file: not ours to judge.
                continue
            outdated.append(installed.name)
            continue
        compared += 1
        if present != expected:
            outdated.append(installed.name)
    # A source checkout has no updater; its fix is running the installer.
    checkout = (root / ".git").exists()
    if compared == 0:
        # None installed, or none readable: a missing set is not "outdated".
        return {"state": "unknown", "outdated": [], "checkout": checkout, "package": ""}
    package = ""
    if outdated:
        for name in outdated:
            candidate = next(
                (path for path in (installed_root / name, installed_root / "lib" / name) if path.exists()),
                None,
            )
            if candidate is not None:
                package = owning_package(candidate)
                break
    return {
        "state": "outdated" if outdated else "current",
        "outdated": outdated,
        "checkout": checkout,
        "package": package,
    }
