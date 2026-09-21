"""Small, explicit init-system boundary for BC250 persistent actions.

The application must never assume that a ``systemctl`` binary means that the
host is actually booted with systemd.  OpenRC installations such as Artix need
their own service/runlevel protocol.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

OPENRC_SERVICE_NAMES = frozenset({
    "bc250-cu-live-manager",
    "bc250-smu-oc",
    "cyan-skillfish-governor-smu",
    "oberon-governor",
    "nct6687-load",
    "bc250-fan-pwm-restore",
})


@dataclass(frozen=True)
class InitManagerState:
    kind: str
    available: bool
    detail: str
    persistence_supported: bool | None = None

    def __post_init__(self) -> None:
        if self.persistence_supported is None:
            object.__setattr__(
                self, "persistence_supported", self.kind in {"systemd", "openrc"}
            )

    @property
    def display_name(self) -> str:
        return {
            "systemd": "systemd",
            "openrc": "OpenRC",
            "runit": "runit",
            "s6": "s6 / s6-rc",
            "dinit": "dinit",
            "sysvinit": "SysVinit",
            "unknown": "unknown init",
        }.get(self.kind, self.kind or "unknown init")

    @property
    def persistence_detail(self) -> str:
        if self.persistence_supported:
            return f"Boot persistence is supported through {self.display_name}."
        return (
            f"Boot persistence is not supported through {self.display_name}; "
            "live hardware readings remain available."
        )


@dataclass(frozen=True)
class ServiceRuntimeState:
    manager: str
    service: str
    active: str
    enabled: str
    exists: bool
    active_returncode: int | None = None
    enabled_returncode: int | None = None
    active_output: str = ""
    enabled_output: str = ""

    @property
    def persistence_supported(self) -> bool:
        return self.manager in {"systemd", "openrc"}


def _read_pid1_comm(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii", errors="replace").strip().lower()
    except OSError:
        return ""


def detect_init_manager(
    *,
    openrc_softlevel: Path = Path("/run/openrc/softlevel"),
    systemd_runtime: Path = Path("/run/systemd/system"),
    pid1_comm: Path = Path("/proc/1/comm"),
    which: Callable[[str], str | None] = shutil.which,
) -> InitManagerState:
    """Detect the active init manager independently from the package family.

    Only systemd and OpenRC currently have reviewed persistence backends.  The
    remaining managers are still identified so callers can keep passive/live
    hardware state available without falling through to ``systemctl``.
    """
    openrc_ready = bool(which("openrc-run") and which("rc-service") and which("rc-update"))
    if openrc_ready and openrc_softlevel.exists():
        return InitManagerState(
            "openrc", True, "OpenRC runlevel management is available.", True
        )
    if systemd_runtime.exists() and which("systemctl"):
        return InitManagerState(
            "systemd", True, "systemd unit management is available.", True
        )

    comm = _read_pid1_comm(pid1_comm)
    if comm in {"runit", "runsvdir"}:
        ready = bool(which("sv"))
        return InitManagerState(
            "runit", ready,
            "runit is active; BC250 service persistence is detected-only."
            if ready else "runit appears active, but its sv command was not found.",
        )
    if comm in {"s6-svscan", "s6-supervise"}:
        ready = bool(which("s6-svstat") or which("s6-rc"))
        return InitManagerState(
            "s6", ready,
            "s6 is active; BC250 service persistence is detected-only."
            if ready else "s6 appears active, but no s6 service-status command was found.",
        )
    if comm == "dinit":
        ready = bool(which("dinitctl"))
        return InitManagerState(
            "dinit", ready,
            "dinit is active; BC250 service persistence is detected-only."
            if ready else "dinit appears active, but dinitctl was not found.",
        )
    if comm in {"init", "sysvinit"} and which("service"):
        return InitManagerState(
            "sysvinit", True,
            "SysVinit is active; BC250 service persistence is detected-only.",
        )
    if openrc_ready:
        return InitManagerState(
            "unknown", False,
            "OpenRC commands are installed but OpenRC is not the active init system.",
        )
    return InitManagerState(
        "unknown", False, "No recognized active init manager was detected."
    )


def service_key(service: str) -> str:
    value = str(service or "").strip()
    value = value.removesuffix(".service")
    if value not in OPENRC_SERVICE_NAMES:
        raise ValueError(f"Unsupported BC250 service: {service}")
    return value


def service_display_name(service: str, manager: str) -> str:
    key = service_key(service)
    return key if manager == "openrc" else f"{key}.service"


def openrc_status_argv(service: str) -> tuple[str, ...]:
    return ("rc-service", service_key(service), "status")


def openrc_start_argv(service: str, action: str) -> tuple[str, ...]:
    if action not in {"start", "stop", "restart"}:
        raise ValueError("Unsupported OpenRC service action")
    return ("rc-service", service_key(service), action)


def openrc_enable_argv(service: str, enabled: bool) -> tuple[str, ...]:
    return ("rc-update", "add" if enabled else "del", service_key(service), "default")


def parse_openrc_status(returncode: int, output: str) -> str:
    """Normalize OpenRC's terse status result without parsing translated UI."""
    text = str(output or "").lower()
    if int(returncode) == 0 and ("started" in text or "status" in text or text == ""):
        return "active"
    if "stopped" in text or "inactive" in text:
        return "inactive"
    if "crashed" in text or "failed" in text:
        return "failed"
    return "unknown"


def parse_openrc_runlevel(output: str, service: str) -> bool:
    key = service_key(service)
    return any(line.split()[0] == key for line in str(output or "").splitlines() if line.split())


def inspect_service(
    runner: Callable[..., tuple[int, str, str]],
    service: str,
    *,
    manager: InitManagerState | None = None,
    timeout: int = 4,
    user: bool = False,
    init_script_root: Path = Path("/etc/init.d"),
) -> ServiceRuntimeState:
    """Read service state through the active init manager without side effects."""
    selected = manager or detect_init_manager()
    name = str(service or "").strip()
    if selected.kind == "openrc" and not user:
        key = service_key(name)
        active_rc, active_out, active_err = runner(
            list(openrc_status_argv(key)), timeout=timeout
        )
        enabled_rc, enabled_out, enabled_err = runner(
            ["rc-update", "show", "default"], timeout=timeout
        )
        active_output = active_out or active_err or ""
        enabled_output = enabled_out or enabled_err or ""
        return ServiceRuntimeState(
            manager="openrc",
            service=key,
            active=parse_openrc_status(active_rc, active_output),
            enabled=(
                "unknown" if enabled_rc != 0
                else "enabled" if parse_openrc_runlevel(enabled_out, key)
                else "disabled"
            ),
            exists=(init_script_root / key).is_file(),
            active_returncode=active_rc,
            enabled_returncode=enabled_rc,
            active_output=active_output,
            enabled_output=enabled_output,
        )
    if selected.kind == "systemd":
        prefix = ["systemctl"] + (["--user"] if user else [])
        active_rc, active_out, active_err = runner(
            prefix + ["is-active", name], timeout=timeout
        )
        enabled_rc, enabled_out, enabled_err = runner(
            prefix + ["is-enabled", name], timeout=timeout
        )
        # stderr describes failures; it is never a machine-readable state.
        active = str(active_out or "").strip().casefold()
        enabled = str(enabled_out or "").strip().casefold()
        if active not in {
            "active", "reloading", "inactive", "failed", "activating",
            "deactivating", "maintenance", "refreshing", "unknown",
        }:
            active = "unknown"
        if enabled not in {
            "enabled", "enabled-runtime", "linked", "linked-runtime", "alias",
            "masked", "masked-runtime", "static", "disabled", "indirect",
            "generated", "transient", "not-found", "bad",
        }:
            enabled = "unknown"
        exists = enabled not in {"not-found", "unknown"} or active in {
            "active", "reloading", "failed", "activating", "deactivating",
            "maintenance", "refreshing",
        }
        return ServiceRuntimeState(
            manager="systemd",
            service=name,
            active=active,
            enabled=enabled,
            exists=exists,
            active_returncode=active_rc,
            enabled_returncode=enabled_rc,
            active_output=active_out or active_err or "",
            enabled_output=enabled_out or enabled_err or "",
        )
    return ServiceRuntimeState(
        manager=selected.kind,
        service=name,
        active="unknown",
        enabled="unsupported",
        exists=False,
    )


def openrc_preflight(*, commands: Sequence[str], has_polkit: bool, has_dbus: bool) -> dict[str, object]:
    required = ("openrc-run", "rc-service", "rc-update")
    found = {str(item) for item in commands}
    missing = [command for command in required if command not in found]
    if not has_polkit:
        missing.append("pkexec")
    dbus_ready = bool(has_dbus)
    return {
        # CU, CPU and PWM do not need D-Bus.  Cyan checks it separately;
        # making it a global OpenRC prerequisite would disable healthy local
        # hardware controls on minimal Artix/Alpine installations.
        "ready": not missing,
        "missing": missing,
        "dbus_ready": dbus_ready,
        "missing_for_cyan": [] if dbus_ready else ["system D-Bus"],
        "manager": "openrc",
        "detail": "OpenRC prerequisites are ready." if not missing else "Missing: " + ", ".join(missing),
    }
