"""Deterministic Qt setup for the automated desktop test suite."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

import pytest

# Files the tests create get the same modes everywhere. Ubuntu gives desktop
# users umask 002, so a payload the test wrote came out group-writable and the
# GDDR6 ownership check (rightly) refused it on that machine only.
os.umask(0o022)

# UI tests must not compete with the developer's active Wayland/X11 window for
# keyboard focus. Callers can still choose another Qt backend explicitly.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Nor may they read or write the real ~/.config/bc250-control-center/ui.conf.
# Pages restore the user's saved profiles from it at construction, so a
# developer who had renamed a GPU profile saw two unrelated GPU tests fail on
# their machine and pass everywhere else — and a test that saves a profile was
# writing into their live configuration. One throwaway directory per run fixes
# both directions. Set before any Qt or application import so nothing has
# resolved the path yet.
_ISOLATED_CONFIG = tempfile.mkdtemp(prefix="bc250-tests-config-")
os.environ["XDG_CONFIG_HOME"] = _ISOLATED_CONFIG
atexit.register(shutil.rmtree, _ISOLATED_CONFIG, ignore_errors=True)
# The same for ~/.local/state: every red dialog a test opens is recorded in the
# diagnostic history, and terminal logs live there too.
_ISOLATED_STATE = tempfile.mkdtemp(prefix="bc250-tests-state-")
os.environ["XDG_STATE_HOME"] = _ISOLATED_STATE
atexit.register(shutil.rmtree, _ISOLATED_STATE, ignore_errors=True)


# Nor may they see the machine's own root fan service (GitHub #15). With
# "control from boot" switched on, the real /var/lib and /run files say the
# system service owns the fan, and every daemon test expecting a desktop write
# saw none. Tests that exercise the service point these at their own files.
_NO_SYSTEM_FAN_CONTROL = tempfile.mkdtemp(prefix="bc250-tests-no-fan-service-")
atexit.register(shutil.rmtree, _NO_SYSTEM_FAN_CONTROL, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolated_system_fan_control(monkeypatch):
    from pathlib import Path

    from bc250cc.infrastructure import system_fan_control

    root = Path(_NO_SYSTEM_FAN_CONTROL)
    for name in ("POLICY_FILE", "STATUS_FILE", "OVERRIDE_FILE", "UNIT_WANTS", "OPENRC_LINK"):
        monkeypatch.setattr(system_fan_control, name, root / name.lower())


# Nor may they depend on which init system the machine happens to run. The
# developer's board and GitHub's runners boot systemd, a container boots none,
# and every CPU/CU persistence test then refused with "unknown init". Unless a
# test passes its own paths, the detector sees a systemd host.
_SIMULATED_SYSTEMD = tempfile.mkdtemp(prefix="bc250-tests-systemd-")
atexit.register(shutil.rmtree, _SIMULATED_SYSTEMD, ignore_errors=True)


@pytest.fixture(autouse=True)
def _simulated_systemd_host(monkeypatch):
    from pathlib import Path

    from bc250cc.platform.init import services

    defaults = dict(services.detect_init_manager.__kwdefaults__)
    defaults.update(
        openrc_softlevel=Path(_SIMULATED_SYSTEMD) / "no-openrc-softlevel",
        systemd_runtime=Path(_SIMULATED_SYSTEMD),
        which=lambda name: f"/usr/bin/{name}" if name == "systemctl" else None,
    )
    monkeypatch.setattr(services.detect_init_manager, "__kwdefaults__", defaults)


# Nor the host kernel's own CU unlock: on linux-cachyos-bc250 with
# bc250_cc_write_mode=3 every CU write surface turns read-only, which would
# fail the CU page tests on that machine only. Tests that need it opt in.
@pytest.fixture(autouse=True)
def _no_host_kernel_cu_unlock(monkeypatch):
    try:
        from bc250cc.infrastructure import cu_kernel_unlock, cu_repository
    except Exception:  # noqa: BLE001 - suites without the package
        return
    monkeypatch.setattr(cu_kernel_unlock, "CU_WRITE_MODE_PARAMETER", cu_kernel_unlock.Path("/nonexistent/bc250_cc_write_mode"))
    monkeypatch.setattr(cu_repository, "kernel_cu_unlock_active", lambda: False)
