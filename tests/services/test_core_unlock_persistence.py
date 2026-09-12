"""Whether an active CPU core unlock survives a full power off.

Upstream bc250-core-unlock is explicit: "survives warm reboots. a full power
off clears it, so redo after every cold boot." Before this, a board could run
with 8 cores and silently return to 6, with nothing reporting it.
"""

from __future__ import annotations

from pathlib import Path

from bc250cc.infrastructure.core_unlock_persistence import (
    EFI_SHIM_BOOT_LABEL,
    EFI_SHIM_PATHS,
    detect_core_unlock_persistence,
)


def test_stock_core_count_is_not_reported_as_at_risk(tmp_path: Path) -> None:
    state = detect_core_unlock_persistence(
        physical_cores=6, logical_cpus=12, root=tmp_path
    )
    assert state["mechanism"] == "stock"
    assert state["survives_power_off"] is True


def test_unlocked_without_a_shim_is_volatile(tmp_path: Path) -> None:
    """The real state of the developer's board while this was written."""
    state = detect_core_unlock_persistence(
        physical_cores=8, logical_cpus=16, root=tmp_path
    )
    assert state["mechanism"] == "volatile"
    assert state["survives_power_off"] is False


def test_installed_efi_shim_counts_as_persistent(tmp_path: Path) -> None:
    shim = tmp_path / EFI_SHIM_PATHS[0].lstrip("/")
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_bytes(b"MZ")
    state = detect_core_unlock_persistence(
        physical_cores=8, logical_cpus=16, root=tmp_path
    )
    assert state["mechanism"] == "efi-shim"
    assert state["survives_power_off"] is True
    assert state["shim_paths"] == [EFI_SHIM_PATHS[0]]


def test_efi_boot_entry_alone_counts_as_persistent(tmp_path: Path) -> None:
    def run(command, timeout=0):
        assert command == ["efibootmgr"]
        return 0, f"Boot0003* {EFI_SHIM_BOOT_LABEL}", ""

    state = detect_core_unlock_persistence(
        physical_cores=8, logical_cpus=16, root=tmp_path, run_command=run
    )
    assert state["boot_entry_present"] is True
    assert state["mechanism"] == "efi-shim"


def test_a_failing_efibootmgr_never_breaks_detection(tmp_path: Path) -> None:
    def run(command, timeout=0):
        raise OSError("efibootmgr is not installed")

    state = detect_core_unlock_persistence(
        physical_cores=8, logical_cpus=16, root=tmp_path, run_command=run
    )
    assert state["boot_entry_present"] is False
    assert state["mechanism"] == "volatile"


def test_detection_never_installs_or_changes_boot_state() -> None:
    """Detection is read-only: a mistake here leaves the board unbootable."""
    source = Path("src/bc250cc/infrastructure/core_unlock_persistence.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("--create", "efibootmgr --", "subprocess", "dd ", "mkfs"):
        assert forbidden not in source, f"detection must not use {forbidden!r}"
