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


@pytest.fixture(autouse=True)
def _keep_qtbot_widgets_until_closed(request):
    """Hold every widget given to ``qtbot.addWidget`` until pytest-qt closes it.

    pytest-qt keeps only a weak reference. A page whose signals point back at
    itself outlives the test function as a reference cycle, still shown, and
    pytest-qt's event processing right after the call paints it; Python's
    garbage collector could then run in the middle of that paint and destroy
    the page under it. Running the i18n tests before the GPU ones did exactly
    that to the GPU governor view: "wrapped C/C++ object has been deleted",
    then a segmentation fault. Held here, each widget stays alive until
    pytest-qt's teardown has closed it and deleted it through the event loop.
    """
    if "qtbot" not in request.fixturenames:
        yield
        return
    qtbot = request.getfixturevalue("qtbot")
    held = request.node._bc250_held_widgets = []
    add_widget = qtbot.addWidget

    def add_and_hold(widget, *args, **kwargs):
        held.append(widget)
        return add_widget(widget, *args, **kwargs)

    qtbot.addWidget = add_and_hold
    yield
    held.clear()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item):
    """Forget held widgets a test destroyed on purpose before pytest-qt closes.

    Without the hold their weak references had died and pytest-qt skipped
    them; held, it would call close() on a deleted object.
    """
    held = getattr(item, "_bc250_held_widgets", None)
    if held:
        from PyQt6 import sip

        destroyed = {id(widget) for widget in held if sip.isdeleted(widget)}
        if destroyed:
            item.qt_widgets = [
                entry for entry in getattr(item, "qt_widgets", [])
                if id(entry[0]()) not in destroyed
            ]
    yield


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


# Nor the host's SteamOS toolkit module: with it installed, every editor
# keeps the GPU at 2230 MHz and the high-point tests would fail on that board
# only. Tests of the limit pass their own root.
@pytest.fixture(autouse=True)
def _no_host_gpu_frequency_ceiling(monkeypatch):
    try:
        from bc250cc.infrastructure.gpu import governor_toml
    except Exception:  # noqa: BLE001 - suites without the package
        return
    monkeypatch.setattr(
        governor_toml.gpu_frequency_ceiling,
        "__defaults__",
        (governor_toml.Path("/nonexistent/bc250-host-root"), None),
    )


# --- No test touches a real disk --------------------------------------------------
#
# A test once pressed every button of the terminal interface with a "yes" to every
# question and reached the real BIOS-USB preparation: UDisks2 unmounted every
# partition of the developer's USB disk before asking for the password that would
# have erased it. Any process that mounts, unmounts, partitions, formats or writes
# a block device now fails the test instead, and so does opening a disk for writing.

DISK_TOOLS = frozenset({"mount", "umount", "udisksctl", "parted", "sfdisk", "sgdisk", "fdisk", "dd", "wipefs",
                        "mkfs", "mkfs.vfat", "mkfs.fat", "mkfs.ext4", "mkfs.exfat", "mkdosfs", "blkdiscard"})
DISK_PREFIXES = ("/dev/sd", "/dev/nvme", "/dev/mmcblk", "/dev/vd", "/dev/hd")


class RealDiskAccess(AssertionError):
    """A test tried to touch a real disk."""


def disk_command(argv) -> str:
    """Why ``argv`` would touch a disk, or ""."""
    if isinstance(argv, (str, bytes)):
        argv = [argv]
    words = [os.fsdecode(word) if isinstance(word, bytes) else str(word) for word in argv]
    first = 1 if words and os.path.basename(words[0]) in ("sudo", "pkexec", "doas", "run0") else 0
    while first < len(words) and words[first].startswith("-"):
        first += 1
    tool = os.path.basename(words[first]) if first < len(words) else ""
    if tool in DISK_TOOLS or tool.startswith("mkfs."):
        return tool
    if tool == "busctl" and "call" in words and any("UDisks2" in word for word in words):
        return "a UDisks2 method call"
    return ""


@pytest.fixture(autouse=True)
def _no_real_disk_access(monkeypatch):
    import builtins
    import subprocess

    popen_init, real_open, os_open = subprocess.Popen.__init__, builtins.open, os.open

    def guarded_popen(self, args, *rest, **kwargs):
        reason = disk_command(args)
        if reason:
            raise RealDiskAccess(f"a test tried to run {reason}: {args!r}")
        popen_init(self, args, *rest, **kwargs)

    def writes_a_disk(path, writing: bool) -> bool:
        return writing and isinstance(path, (str, bytes, os.PathLike)) and \
            os.fsdecode(os.fspath(path)).startswith(DISK_PREFIXES)

    def guarded_open(file, mode="r", *args, **kwargs):
        if writes_a_disk(file, any(flag in mode for flag in "wax+")):
            raise RealDiskAccess(f"a test tried to write {file}")
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if writes_a_disk(path, bool(flags & (os.O_WRONLY | os.O_RDWR))):
            raise RealDiskAccess(f"a test tried to write {path}")
        return os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", guarded_popen)
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
