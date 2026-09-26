"""The boot units around the fan never form an ordering cycle (GitHub #15).

nct6687-load.service runs after graphical.target so its settle delay never
holds up the login screen. A multi-user.target unit ordered after it closes a
cycle -- multi-user.target is implicitly ordered after the units it wants --
and systemd resolves that at boot by silently dropping a start job. On a real
BC-250 it dropped bc250-fan-pwm-restore.service on every boot, and it would
have dropped the system fan control service the same way.
"""

from __future__ import annotations

import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged" / "helpers" / "bc250-fan-pwm-helper"
COMMON_INSTALLER = ROOT / "packaging" / "common" / "os-scripts" / "common" / "install-fan-persistence.sh"
SYSTEM_UNITS = Path("/usr/lib/systemd/system")


def _heredoc(text: str, unit: str) -> str:
    match = re.search(rf"tee /etc/systemd/system/{re.escape(unit)} >/dev/null <<'?EOF'?\n(.*?)\nEOF\n", text, re.S)
    assert match, f"{unit} is no longer written by the installer"
    return match.group(1) + "\n"


def _units() -> dict[str, str]:
    installer = COMMON_INSTALLER.read_text(encoding="utf-8")
    control = runpy.run_path(str(HELPER))["control_unit_text"](Path("/usr/bin/true"))
    return {
        "nct6687-load.service": _heredoc(installer, "nct6687-load.service"),
        "bc250-fan-pwm-restore.service": _heredoc(installer, "bc250-fan-pwm-restore.service"),
        "bc250-fan-control.service": control,
    }


def _after(unit_text: str) -> set[str]:
    names: set[str] = set()
    for line in unit_text.splitlines():
        if line.startswith("After="):
            names.update(line.partition("=")[2].split())
    return names


def test_the_control_service_wants_the_module_loader_but_is_not_ordered_after_it():
    control = _units()["bc250-fan-control.service"]
    assert "Wants=nct6687-load.service" in control
    assert "nct6687-load.service" not in _after(control)
    assert "WantedBy=multi-user.target" in control


def test_units_ordered_after_the_late_module_loader_are_also_after_multi_user():
    units = _units()
    late = "multi-user.target" in _after(units["nct6687-load.service"])
    for name, text in units.items():
        if late and "nct6687-load.service" in _after(text) and "WantedBy=multi-user.target" in text:
            assert "multi-user.target" in _after(text), name


@pytest.mark.skipif(
    shutil.which("systemd-analyze") is None or not SYSTEM_UNITS.is_dir(),
    reason="needs systemd-analyze and the distribution's unit directory",
)
def test_a_simulated_boot_transaction_has_no_ordering_cycle(tmp_path):
    wants = tmp_path / "multi-user.target.wants"
    wants.mkdir()
    for name, text in _units().items():
        text = re.sub(r"(?m)^ExecStart(Pre)?=.*$", r"ExecStart\1=/usr/bin/true", text)
        text = re.sub(r"(?m)^ConditionPathExists=.*$", "", text)
        (tmp_path / name).write_text(text, encoding="utf-8")
        (wants / name).symlink_to(tmp_path / name)
    result = subprocess.run(
        ["systemd-analyze", "verify", "--man=no", "graphical.target"],
        env={**os.environ, "SYSTEMD_UNIT_PATH": f"{tmp_path}:{SYSTEM_UNITS}"},
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    output = result.stdout + result.stderr
    assert "ordering cycle" not in output.lower(), output
    assert "deleted to break" not in output, output
