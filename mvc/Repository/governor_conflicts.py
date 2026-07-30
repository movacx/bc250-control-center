from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


SUPPORTED_GPU_GOVERNOR = "cyan-skillfish-governor-smu"


@dataclass(frozen=True)
class IncompatibleGovernor:
    identifier: str
    service: str
    active: bool = False
    enabled: bool = False
    package_installed: bool = False
    binary_path: str = ""
    unit_path: str = ""

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
        }


class GovernorConflictError(RuntimeError):
    def __init__(self, conflicts: list[dict[str, object]]):
        self.conflicts = list(conflicts)
        names = ", ".join(str(item.get("identifier") or item.get("service")) for item in conflicts)
        super().__init__(
            "An incompatible GPU frequency governor was detected: "
            f"{names}. Running two governors can crash the GPU or produce a green screen "
            "at the next boot. Disable the conflicting governor before continuing."
        )


KNOWN_INCOMPATIBLE_GOVERNORS = (
    {
        "identifier": "oberon-governor",
        "service": "oberon-governor.service",
        "binary": "oberon-governor",
        "package": "oberon-governor",
        # The original GitLab project and the known filippor/alexghow903
        # community forks intentionally keep this same runtime contract.
        "known_sources": (
            "gitlab.com/mothenjoyer69/oberon-governor",
            "github.com/filippor/oberon-governor",
            "github.com/alexghow903/oberon-governor",
        ),
    },
)


def _systemctl_state(repository, action: str, service: str) -> bool:
    code, stdout, _stderr = repository._ejecutar(
        ["systemctl", action, service],
        timeout=3,
    )
    if code != 0:
        return False
    state = (stdout or "").strip().lower()
    expected = {"is-active": "active", "is-enabled": "enabled"}[action]
    return state == expected


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


def detect_incompatible_governors(repository) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []
    for spec in KNOWN_INCOMPATIBLE_GOVERNORS:
        item = IncompatibleGovernor(
            identifier=spec["identifier"],
            service=spec["service"],
            active=_systemctl_state(repository, "is-active", spec["service"]),
            enabled=_systemctl_state(repository, "is-enabled", spec["service"]),
            package_installed=_package_installed(repository, spec["package"]),
            binary_path=shutil.which(spec["binary"]) or "",
            unit_path=_find_unit(spec["service"]),
        )
        if item.detected:
            conflicts.append(item.to_dict())
    return conflicts


def ensure_no_incompatible_governors(repository, *, confirmed: bool = False) -> list[dict[str, object]]:
    conflicts = detect_incompatible_governors(repository)
    if conflicts and not confirmed:
        raise GovernorConflictError(conflicts)
    return conflicts
