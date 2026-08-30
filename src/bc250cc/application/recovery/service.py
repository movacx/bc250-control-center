"""Read-only application facade for local recovery snapshot inventory."""

from __future__ import annotations

import os
import re
from dataclasses import asdict
from pathlib import Path

from bc250cc.infrastructure.persistence.recovery_engine import (
    RecoverySnapshotRepository,
)
from bc250cc.platform.init.services import detect_init_manager

_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
DEFAULT_RECOVERY_SOURCES = (
    "/etc/bc250-smu-oc.conf",
    "/etc/cyan-skillfish-governor-smu/config.toml",
    "/etc/oberon-config.yaml",
    "/etc/bc250-cu-live-manager.conf",
    "/etc/modprobe.d/nct6683.conf",
    "/etc/modprobe.d/nct6687.conf",
    "/etc/modprobe.d/sensors.conf",
    "/etc/modules-load.d/nct6687.conf",
    "/etc/modules-load.d/99-sensors.conf",
    "/etc/modules-load.d/nct6683.conf",
    "/etc/systemd/system/bc250-smu-oc.service",
    "/etc/systemd/system/bc250-cu-live-manager.service",
    "/etc/systemd/system/bc250-cu-live-manager.service.d/10-bc250-storage.conf",
    "/etc/systemd/system/bc250-persistence-recovery.service",
    "/etc/systemd/system/nct6687-load.service",
    "/etc/init.d/bc250-smu-oc",
    "/etc/init.d/bc250-cu-live-manager",
    "/etc/init.d/cyan-skillfish-governor-smu",
    "/etc/init.d/oberon-governor",
    "/etc/init.d/nct6687-load",
    "/etc/systemd/system/var-lib-bc250\\x2dcontrol.mount",
    "/etc/systemd/system/oberon-governor.service",
    "/etc/systemd/system/cyan-skillfish-governor-smu.service.d/90-bc250-control-center-upstream.conf",
    "/etc/dbus-1/system.d/com.cyanskillfish.Governor.conf",
    "/usr/local/sbin/bc250-load-nct6687",
    "/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay",
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/patch-driver.sh",
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/boot-config.sh",
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-update-persistence.sh",
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-storage.sh",
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/.bc250-control-center-reviewed-revision",
    "/usr/local/lib/systemd/system/cyan-skillfish-governor-smu.service",
    "/var/lib/bc250-control/helper/bc250-storage.sh",
    "/etc/atomic-update.conf.d/bc250-amdgpu.conf",
    "/etc/atomic-update.conf.d/bc250-storage.conf",
    "/etc/default/grub",
    "/etc/default/grub.d/bc250-amdgpu.cfg",
    "/etc/kernel/cmdline",
    "/etc/mkinitcpio.conf",
)

# The historical recovery contract was systemd-only.  Keep the public constant
# as that contract for compatibility with exported snapshots/tests, but select
# an OpenRC-specific contract at runtime instead of reporting a healthy OpenRC
# host as incomplete for lacking .service files it must never create.
RECOVERY_SOURCE_GROUPS = {
    "gpu_governors": frozenset({
        "/etc/cyan-skillfish-governor-smu/config.toml",
        "/etc/oberon-config.yaml",
        "/etc/systemd/system/oberon-governor.service",
        "/etc/dbus-1/system.d/com.cyanskillfish.Governor.conf",
    }),
    "cpu_tuning": frozenset({
        "/etc/bc250-smu-oc.conf",
        "/etc/systemd/system/bc250-smu-oc.service",
    }),
    "compute_units": frozenset({
        "/etc/bc250-cu-live-manager.conf",
        "/etc/systemd/system/bc250-cu-live-manager.service",
        "/etc/systemd/system/bc250-cu-live-manager.service.d/10-bc250-storage.conf",
    }),
    "fan_pwm": frozenset({
        "/etc/modprobe.d/nct6687.conf",
        "/etc/systemd/system/nct6687-load.service",
        "/usr/local/sbin/bc250-load-nct6687",
    }),
    "steamos_boot": frozenset({
        "/etc/default/grub",
        "/etc/default/grub.d/bc250-amdgpu.cfg",
        "/etc/atomic-update.conf.d/bc250-amdgpu.conf",
    }),
    "steamos_amdgpu_runtime": frozenset({
        "/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/patch-driver.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/boot-config.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-update-persistence.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-storage.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/.bc250-control-center-reviewed-revision",
    }),
    "steamos_persistence": frozenset({
        "/etc/systemd/system/bc250-persistence-recovery.service",
        "/etc/systemd/system/var-lib-bc250\\x2dcontrol.mount",
        "/etc/atomic-update.conf.d/bc250-storage.conf",
        "/var/lib/bc250-control/helper/bc250-storage.sh",
    }),
}

OPENRC_RECOVERY_SOURCE_GROUPS = {
    "gpu_governors": frozenset({
        "/etc/cyan-skillfish-governor-smu/config.toml",
        "/etc/oberon-config.yaml",
        "/etc/init.d/cyan-skillfish-governor-smu",
        "/etc/init.d/oberon-governor",
        "/etc/dbus-1/system.d/com.cyanskillfish.Governor.conf",
    }),
    "cpu_tuning": frozenset({
        "/etc/bc250-smu-oc.conf",
        "/etc/init.d/bc250-smu-oc",
    }),
    "compute_units": frozenset({
        "/etc/bc250-cu-live-manager.conf",
        "/etc/init.d/bc250-cu-live-manager",
    }),
    "fan_pwm": frozenset({
        "/etc/modprobe.d/nct6687.conf",
        "/etc/init.d/nct6687-load",
        "/usr/local/sbin/bc250-load-nct6687",
    }),
}


def recovery_capture_readiness(
    sources: tuple[str, ...] | list[str] | None = None,
    *,
    init_manager: str = "systemd",
) -> dict[str, object]:
    if sources is None:
        sources = DEFAULT_RECOVERY_SOURCES
    configured = frozenset(str(source) for source in sources)
    manager = "openrc" if init_manager == "openrc" else "systemd"
    required_groups = (
        OPENRC_RECOVERY_SOURCE_GROUPS if manager == "openrc" else RECOVERY_SOURCE_GROUPS
    )
    groups = {
        key: {
            "complete": required.issubset(configured),
            "missing_sources": sorted(required - configured),
        }
        for key, required in required_groups.items()
    }
    capture_complete = all(item["complete"] for item in groups.values())
    return {
        "capture_contract_complete": capture_complete,
        "init_manager": manager,
        "source_groups": groups,
        "restore_executor_enabled": False,
        "physical_boot_recovery_proven": False,
        "blockers": [
            "Automatic system restore is deliberately disabled.",
            "Service enablement, live hardware state and reboot success require post-restore verification.",
            "Boot-critical recovery requires a separately proven physical/offline path.",
        ],
    }


class RecoveryRepository:
    def _recovery_snapshot_root(self) -> Path:
        state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local/state"))
        return state_home / "bc250-control-center/recovery"

    def recovery_inventory(self, limit: int = 50) -> dict[str, object]:
        root = self._recovery_snapshot_root()
        bounded_limit = max(1, min(int(limit), 200))
        snapshots: list[dict[str, object]] = []
        if root.is_dir() and not root.is_symlink():
            candidates = sorted(root.iterdir(), key=lambda item: item.name, reverse=True)
            for candidate in candidates:
                if len(snapshots) >= bounded_limit:
                    break
                if (
                    candidate.name.startswith(".")
                    or candidate.is_symlink()
                    or not candidate.is_dir()
                    or not _SNAPSHOT_ID.fullmatch(candidate.name)
                ):
                    continue
                plan = RecoverySnapshotRepository.build_restore_plan(candidate)
                label = "Invalid snapshot"
                created_at: float | None = None
                try:
                    metadata = RecoverySnapshotRepository.metadata(candidate)
                    label = str(metadata["label"])
                    created_at = float(metadata["created_at"])
                except (OSError, TypeError, ValueError):
                    pass
                snapshots.append(
                    {
                        "id": candidate.name,
                        "label": label,
                        "created_at": created_at,
                        "verified": plan.verified,
                        "blocked": plan.blocked,
                        "actions": len(plan.actions),
                        "automatic_actions": sum(action.automatic_allowed for action in plan.actions),
                    }
                )
        return {
            "root": str(root),
            "snapshots": snapshots,
            "restore_available": False,
            "readiness": recovery_capture_readiness(init_manager=detect_init_manager().kind),
        }

    def create_recovery_snapshot(self, label: str = "manual-before-change") -> dict[str, object]:
        root = self._recovery_snapshot_root()
        snapshot = RecoverySnapshotRepository(root).capture(
            list(DEFAULT_RECOVERY_SOURCES), label=label
        )
        plan = RecoverySnapshotRepository.build_restore_plan(snapshot)
        entries = RecoverySnapshotRepository.load(snapshot)
        states: dict[str, int] = {}
        for entry in entries:
            states[entry.state] = states.get(entry.state, 0) + 1
        return {
            "id": snapshot.name,
            "path": str(snapshot),
            "verified": plan.verified,
            "blocked": plan.blocked,
            "restore_available": False,
            "entries": len(entries),
            "states": states,
            "boot_critical": sum(entry.boot_critical for entry in entries),
            "readiness": recovery_capture_readiness(init_manager=detect_init_manager().kind),
        }

    def _resolve_snapshot(self, snapshot_id: str) -> Path:
        identifier = str(snapshot_id or "")
        if not _SNAPSHOT_ID.fullmatch(identifier):
            raise ValueError("Invalid recovery snapshot identifier")
        root = self._recovery_snapshot_root()
        snapshot = root / identifier
        if snapshot.is_symlink() or not snapshot.is_dir():
            raise ValueError("Recovery snapshot does not exist")
        return snapshot

    def recovery_plan(self, snapshot_id: str) -> dict[str, object]:
        snapshot = self._resolve_snapshot(snapshot_id)
        plan = RecoverySnapshotRepository.build_restore_plan(snapshot)
        current_state = RecoverySnapshotRepository.inspect_current_state(snapshot)
        return {
            "snapshot": plan.snapshot,
            "verified": plan.verified,
            "blocked": plan.blocked,
            "restore_available": False,
            "actions": [asdict(action) for action in plan.actions],
            "current_state": [asdict(item) for item in current_state],
            "readiness": recovery_capture_readiness(
                [action.source for action in plan.actions],
                init_manager=detect_init_manager().kind,
            ),
        }

    def export_recovery_snapshot(
        self, snapshot_id: str, destination: str | Path
    ) -> dict[str, object]:
        snapshot = self._resolve_snapshot(snapshot_id)
        return RecoverySnapshotRepository.export_portable_bundle(
            snapshot, destination
        )
