from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from bc250cc.platform.init.services import (
    detect_init_manager,
    inspect_service,
    service_key,
)

GPU_GOVERNOR_AUTO = "auto"
CYAN_GOVERNOR = "cyan-skillfish-governor-smu"
OBERON_GOVERNOR = "oberon-governor"
SUPPORTED_GPU_GOVERNORS = (CYAN_GOVERNOR, OBERON_GOVERNOR)
# Compatibility alias retained for callers and third-party integrations from
# releases where Cyan was the only supported backend.
SUPPORTED_GPU_GOVERNOR = CYAN_GOVERNOR

GOVERNOR_SPECS = {
    CYAN_GOVERNOR: {
        "identifier": CYAN_GOVERNOR,
        "service": "cyan-skillfish-governor-smu.service",
        "binary": CYAN_GOVERNOR,
        "package": CYAN_GOVERNOR,
        "config_path": "/etc/cyan-skillfish-governor-smu/config.toml",
        "display_name": "Cyan Skillfish Governor (SMU)",
        "known_sources": (
            "github.com/filippor/cyan-skillfish-governor/tree/smu",
        ),
    },
    OBERON_GOVERNOR: {
        "identifier": OBERON_GOVERNOR,
        "service": "oberon-governor.service",
        "binary": OBERON_GOVERNOR,
        "package": OBERON_GOVERNOR,
        "config_path": "/etc/oberon-config.yaml",
        "display_name": "Oberon Governor",
        # The original GitLab project and known community forks deliberately
        # keep the same binary, unit and configuration contract.
        "known_sources": (
            "gitlab.com/mothenjoyer69/oberon-governor",
            "github.com/filippor/oberon-governor",
            "github.com/alexghow903/oberon-governor",
        ),
    },
}


@dataclass(frozen=True)
class GovernorInstallation:
    identifier: str
    service: str
    active: bool = False
    enabled: bool = False
    package_installed: bool = False
    binary_path: str = ""
    unit_path: str = ""
    config_path: str = ""

    @property
    def detected(self) -> bool:
        return any((
            self.active,
            self.enabled,
            self.package_installed,
            bool(self.binary_path),
            bool(self.unit_path),
        ))

    def to_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "service": self.service,
            "active": self.active,
            "enabled": self.enabled,
            "package_installed": self.package_installed,
            "binary_path": self.binary_path,
            "unit_path": self.unit_path,
            "config_path": self.config_path,
            "detected": self.detected,
        }


# Historical name retained because the UI still describes a selected backend's
# *other* installed governor as incompatible with the selected runtime.
IncompatibleGovernor = GovernorInstallation


class GovernorConflictError(RuntimeError):
    def __init__(self, conflicts: list[dict[str, object]], selected: str = CYAN_GOVERNOR):
        self.conflicts = list(conflicts)
        self.selected = str(selected)
        names = ", ".join(str(item.get("identifier") or item.get("service")) for item in conflicts)
        super().__init__(
            "A second GPU frequency governor was detected: "
            f"{names}. Running it together with {self.selected} can crash the GPU or "
            "produce a green screen at the next boot. Stop and disable the other "
            "governor before continuing."
        )


# Compatibility structure used by older tests/UI code. Oberon is no longer
# globally incompatible; it is incompatible only while Cyan is selected.
KNOWN_INCOMPATIBLE_GOVERNORS = (GOVERNOR_SPECS[OBERON_GOVERNOR],)


def _package_installed(repository, package: str) -> bool:
    checks = (
        (["rpm", "-q", package], None),
        (["dpkg-query", "-W", "-f=${Status}", package], "install ok installed"),
        (["pacman", "-Q", package], None),
    )
    for command, expected_output in checks:
        if not shutil.which(command[0]):
            continue
        code, stdout, _stderr = repository._ejecutar(command, timeout=3)
        if code == 0 and (expected_output is None or expected_output in (stdout or "").lower()):
            return True
    return False


def _find_unit(service: str) -> str:
    init_manager = detect_init_manager()
    if init_manager.kind == 'openrc':
        candidate = Path('/etc/init.d') / service_key(service)
        return str(candidate) if candidate.is_file() and not candidate.is_symlink() else ''
    if init_manager.kind != 'systemd':
        return ''
    roots = (
        Path("/etc/systemd/system"),
        Path("/usr/local/lib/systemd/system"),
        Path("/usr/lib/systemd/system"),
        Path("/lib/systemd/system"),
    )
    for root in roots:
        candidate = root / service
        if candidate.exists() or candidate.is_symlink():
            return str(candidate)
    return ""


def _binary_path(repository, binary: str) -> str:
    resolver = getattr(repository, "_command_path", None)
    if callable(resolver):
        try:
            return str(resolver(binary) or "")
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
    return shutil.which(binary) or ""


def detect_supported_governors(repository) -> dict[str, dict[str, object]]:
    """Return deterministic runtime evidence for every supported backend."""
    detected: dict[str, dict[str, object]] = {}
    for identifier in SUPPORTED_GPU_GOVERNORS:
        spec = GOVERNOR_SPECS[identifier]
        service = str(spec["service"])
        service_state = inspect_service(
            repository._ejecutar,
            service,
            manager=detect_init_manager(),
            timeout=3,
        )
        item = GovernorInstallation(
            identifier=identifier,
            service=service,
            active=service_state.active == "active",
            enabled=service_state.enabled in {"enabled", "enabled-runtime"},
            package_installed=_package_installed(repository, str(spec["package"])),
            binary_path=_binary_path(repository, str(spec["binary"])),
            unit_path=_find_unit(str(spec["service"])),
            config_path=str(spec["config_path"]),
        )
        detected[identifier] = item.to_dict()
    return detected


def normalize_governor_preference(value: object) -> str:
    normalized = str(value or GPU_GOVERNOR_AUTO).strip().lower()
    aliases = {
        "cyan": CYAN_GOVERNOR,
        "cyan-skillfish-governor": CYAN_GOVERNOR,
        "oberon": OBERON_GOVERNOR,
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {GPU_GOVERNOR_AUTO, *SUPPORTED_GPU_GOVERNORS} else GPU_GOVERNOR_AUTO


def resolve_gpu_governor(
    repository,
    preference: object = GPU_GOVERNOR_AUTO,
    *,
    detected: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    """Resolve which backend the UI controls without hiding dual-start risk.

    An explicit user choice wins, even if it is not installed yet, so Prepare
    dependencies can install that backend. In automatic mode a uniquely active
    service wins, then a uniquely detected installation; Cyan remains the safe
    default for a clean system because it provides D-Bus and metric repair.
    """
    preference = normalize_governor_preference(preference)
    evidence = detected or detect_supported_governors(repository)
    active = [name for name in SUPPORTED_GPU_GOVERNORS if evidence[name].get("active")]
    installed = [name for name in SUPPORTED_GPU_GOVERNORS if evidence[name].get("detected")]
    if preference != GPU_GOVERNOR_AUTO:
        selected = preference
        reason = "user"
    elif len(active) == 1:
        selected = active[0]
        reason = "active"
    elif len(installed) == 1:
        selected = installed[0]
        reason = "installed"
    else:
        selected = CYAN_GOVERNOR
        reason = "default"
    # ``selected`` is the desired control backend.  It intentionally falls
    # back to Cyan on a clean installation so the preparation workflow knows
    # what to install, but that fallback is not proof that Cyan exists.  Keep
    # the detected backend separate so status UIs never present a preference
    # or installation target as discovered hardware state.
    if len(active) == 1:
        detected_backend = active[0]
    elif evidence[selected].get("detected"):
        detected_backend = selected
    elif len(installed) == 1:
        detected_backend = installed[0]
    else:
        detected_backend = ""
    other_installations = [
        evidence[name]
        for name in SUPPORTED_GPU_GOVERNORS
        if name != selected and evidence[name].get("detected")
    ]
    # Supported alternatives may coexist on disk. They conflict only when the
    # non-selected systemd unit is running now or armed for a future boot.
    # Treating a disabled binary/package as a conflict would make the selector
    # unusable after both backends had been prepared once.
    conflicts = [
        state for state in other_installations
        if bool(state.get("active") or state.get("enabled"))
    ]
    return {
        "preference": preference,
        "selected": selected,
        "detected_backend": detected_backend,
        "reason": reason,
        "detected": evidence,
        "selected_state": evidence[selected],
        "other_installations": other_installations,
        "conflicts": conflicts,
        "dual_active": len(active) > 1,
    }


def detect_incompatible_governors(
    repository,
    selected: object = CYAN_GOVERNOR,
) -> list[dict[str, object]]:
    normalized = normalize_governor_preference(selected)
    detected = detect_supported_governors(repository)
    if normalized == GPU_GOVERNOR_AUTO:
        normalized = str(resolve_gpu_governor(repository, normalized, detected=detected)["selected"])
    return [
        state
        for name, state in detected.items()
        if name != normalized and bool(state.get("active") or state.get("enabled"))
    ]


def ensure_no_incompatible_governors(
    repository,
    *,
    selected: object = CYAN_GOVERNOR,
    confirmed: bool = False,
) -> list[dict[str, object]]:
    normalized = normalize_governor_preference(selected)
    if normalized == GPU_GOVERNOR_AUTO:
        normalized = str(resolve_gpu_governor(repository, normalized)["selected"])
    conflicts = detect_incompatible_governors(repository, normalized)
    if conflicts and not confirmed:
        raise GovernorConflictError(conflicts, normalized)
    return conflicts
