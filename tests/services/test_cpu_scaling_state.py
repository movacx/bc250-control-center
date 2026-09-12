"""Detection of a board left without CPU frequency scaling.

The BC-250 firmware declares idle states but no performance states, so
without the reviewed ACPI override the kernel registers no cpufreq driver and
every core runs pinned near its base clock. The interface reported nothing.
"""

from __future__ import annotations

from pathlib import Path

from bc250cc.infrastructure.cpu_scaling_state import (
    ACPI_TABLES,
    CPU_ROOT,
    detect_cpu_scaling,
)


def _write(root: Path, relative: str, content: bytes | str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="ascii")


def test_absent_cpufreq_is_reported(tmp_path: Path) -> None:
    """The developer's own board, running the BC250 kernel without the fix."""
    state = detect_cpu_scaling(root=tmp_path)
    assert state["scaling_available"] is False
    assert state["scaling_driver"] == ""


def test_active_scaling_is_reported(tmp_path: Path) -> None:
    _write(tmp_path, f"{CPU_ROOT}/cpu0/cpufreq/scaling_driver", "acpi-cpufreq\n")
    _write(tmp_path, f"{CPU_ROOT}/cpu0/cpufreq/scaling_governor", "schedutil\n")
    state = detect_cpu_scaling(root=tmp_path)
    assert state["scaling_available"] is True
    assert state["scaling_driver"] == "acpi-cpufreq"
    assert state["governor"] == "schedutil"


def test_stock_firmware_tables_are_not_mistaken_for_the_fix(tmp_path: Path) -> None:
    """The board's own SSDT is OEM 'AMD'; only the fix carries HACK/PSTATES."""
    header = b"SSDT" + b"\x00" * 6 + b"AMD   " + b"AMD CPU " + b"\x00" * 16
    _write(tmp_path, f"{ACPI_TABLES}/SSDT1", header)
    assert detect_cpu_scaling(root=tmp_path)["acpi_override_active"] is False


def test_override_tables_are_recognised(tmp_path: Path) -> None:
    header = b"SSDT" + b"\x00" * 6 + b"HACK  " + b"PSTATES " + b"\x00" * 16
    _write(tmp_path, f"{ACPI_TABLES}/SSDT3", header)
    assert detect_cpu_scaling(root=tmp_path)["acpi_override_active"] is True


def test_unreadable_paths_never_raise(tmp_path: Path) -> None:
    """A health probe must not be the thing that breaks the report."""
    _write(tmp_path, f"{ACPI_TABLES}/SSDT1", b"")
    state = detect_cpu_scaling(root=tmp_path)
    assert state["scaling_available"] is False
