"""Cyan v0.4.15 binds its service to the GPU device its udev rule creates.

Upstream's unit (Debian package, AUR, COPR, its own install.sh) carries
``BindsTo=dev-cyan_skillfish_gpu.device``. Without the rule, or before udev has
seen the GPU with it, the service cannot start: pacman runs no udev trigger, so
an AUR update left Cyan failing with "Dependency failed" until the next boot.
Control Center's own fallback unit has no BindsTo and must stay untouched.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

INSTALLER = Path("packaging/common/os-scripts/common/install-cyan-upstream-release.sh")


def _function(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", INSTALLER.read_text(), re.M | re.S)
    assert match, name
    return match.group(0)


def _run(tmp_path, *, binds_to: str, device_active: bool, rule_installed: bool, rule_in_source=True):
    log = tmp_path / "log"
    source = tmp_path / "source"
    source.mkdir()
    if rule_in_source:
        (source / "70-cyan-skillfish-governor.rules").write_text("# upstream rule\n")
    etc, lib = tmp_path / "etc-rules", tmp_path / "lib-rules"
    lib.mkdir()
    if rule_installed:
        (lib / "70-cyan-skillfish-governor.rules").write_text("# package rule\n")
    script = "\n".join((
        "set -Eeuo pipefail",
        'SERVICE="cyan-skillfish-governor-smu.service"',
        'GPU_DEVICE_UNIT="dev-cyan_skillfish_gpu.device"',
        'UDEV_RULE_NAME="70-cyan-skillfish-governor.rules"',
        f'UDEV_RULE_DIRS=({etc} {lib})',
        f'UDEV_RULE="{etc}/$UDEV_RULE_NAME"',
        f'SOURCE_DIR="{source}"',
        f'LOG="{log}"',
        "have() { command -v \"$1\" >/dev/null 2>&1 || [ \"$1\" = udevadm ]; }",
        'info() { echo "INFO $*" >>"$LOG"; }',
        'die() { echo "DIE $*" >>"$LOG"; exit 1; }',
        'as_root() { echo "ROOT $*" >>"$LOG"; if [ "$1" = install ]; then command "$@"; fi; }',
        "systemctl() {",
        f'  if [ "$1" = show ]; then echo "{binds_to}"; return 0; fi',
        f'  if [ "$1" = is-active ]; then return {0 if device_active else 3}; fi',
        "}",
        _function("ensure_gpu_device_unit"),
        "ensure_gpu_device_unit",
    ))
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return result, (log.read_text() if log.exists() else ""), etc


def test_the_apps_own_unit_without_binds_to_is_left_alone(tmp_path):
    result, log, etc = _run(tmp_path, binds_to="", device_active=False, rule_installed=False)
    assert result.returncode == 0
    assert log == "" and not etc.exists()


def test_a_package_rule_that_udev_has_not_applied_yet_is_triggered(tmp_path):
    result, log, etc = _run(
        tmp_path, binds_to="dev-cyan_skillfish_gpu.device", device_active=False, rule_installed=True
    )
    assert result.returncode == 0
    assert "ROOT udevadm trigger --action=change --subsystem-match=drm" in log
    assert "ROOT install" not in log and not etc.exists()


def test_a_missing_rule_is_added_from_the_reviewed_checkout(tmp_path):
    result, log, etc = _run(
        tmp_path, binds_to="dev-cyan_skillfish_gpu.device", device_active=False, rule_installed=False
    )
    assert result.returncode == 0
    assert (etc / "70-cyan-skillfish-governor.rules").read_text() == "# upstream rule\n"
    assert log.index("ROOT udevadm control --reload-rules") < log.index("ROOT udevadm trigger")


def test_a_registered_device_needs_nothing(tmp_path):
    result, log, _etc = _run(
        tmp_path, binds_to="dev-cyan_skillfish_gpu.device", device_active=True, rule_installed=True
    )
    assert result.returncode == 0
    assert "ROOT" not in log


def test_a_bound_unit_with_no_rule_anywhere_stops_with_a_reason(tmp_path):
    result, log, _etc = _run(
        tmp_path, binds_to="dev-cyan_skillfish_gpu.device", device_active=False,
        rule_installed=False, rule_in_source=False,
    )
    assert result.returncode == 1
    assert "DIE The Cyan service needs 70-cyan-skillfish-governor.rules" in log


def test_start_and_restart_from_the_app_register_the_device_first(monkeypatch):
    from types import SimpleNamespace

    from bc250cc.infrastructure import gpu_repository as module

    monkeypatch.setattr(module, "detect_init_manager", lambda: SimpleNamespace(kind="systemd"))
    repository = module.GPURepository.__new__(module.GPURepository)
    repository._cyan_metrics_overlay_preflight_command = lambda: "PREFLIGHT;"
    repository._cyan_activation_dbus_repair_command = lambda: "DBUS_REPAIR"
    service = "cyan-skillfish-governor-smu.service"
    step = module.GPURepository._cyan_gpu_device_command(service)
    assert "-p BindsTo --value" in step and "dev-cyan_skillfish_gpu.device" in step
    assert "udevadm trigger --action=change --subsystem-match=drm" in step

    start = repository._governor_activation_command(module.CYAN_GOVERNOR, service, "")
    restart = repository._governor_restart_command(module.CYAN_GOVERNOR, service, "")
    assert start.index(step) < start.index(f"sudo systemctl enable --now {service}")
    assert restart.index(step) < restart.index(f"sudo systemctl restart {service}")
    # Oberon has no such device.
    oberon = repository._governor_restart_command("oberon", "oberon-governor.service", "")
    assert "udevadm" not in oberon
