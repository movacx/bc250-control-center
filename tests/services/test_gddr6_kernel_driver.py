"""With the kernel's bc250_memory driver loaded, Control Center only reads it.

MastaG's BC-250 kernels carry Hexxeh's bc250_memory driver (off by default).
Loaded, it installs the first SMU payload itself and sends Queue 3 messages
from the kernel whenever its hwmon files are read, without the locks the
other SMU clients share. Patching or sampling the SMU beside it would be two
samplers on one mailbox, which is what used to hang boards. So the helpers
never patch while it is loaded; they read its sensors under those locks, and
no upstream checkout is needed.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from frontends.desktop.core.gddr6_monitor import KERNEL_SOURCE, Gddr6Reading

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"
LABELS = ["VRAM Hotspot", "VRAM Average", *(f"VRAM Chip {chip}" for chip in range(8))]


def _load(name: str, *, loaded: bool, tmp_path: Path):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_") + "_kd", str(HELPERS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    module_dir = tmp_path / "sys-module-bc250_memory"
    if loaded:
        module_dir.mkdir(exist_ok=True)
    module.KERNEL_DRIVER_MODULE = module_dir
    return module


def _hwmon(tmp_path: Path, millidegrees: list[object]) -> Path:
    """A /sys/class/hwmon tree with the driver's ten channels, plus another chip."""
    root = tmp_path / "hwmon"
    other = root / "hwmon0"
    other.mkdir(parents=True)
    (other / "name").write_text("amdgpu\n")
    (other / "temp1_label").write_text("VRAM Chip 0\n")  # not ours: ignored
    (other / "temp1_input").write_text("99000\n")
    driver = root / "hwmon3"
    driver.mkdir()
    (driver / "name").write_text("bc250_memory\n")
    values = [max(v for v in millidegrees if isinstance(v, int)), 0, *millidegrees]
    for index, (label, value) in enumerate(zip(LABELS, values), start=1):
        (driver / f"temp{index}_label").write_text(label + "\n")
        if value is not None:
            (driver / f"temp{index}_input").write_text(f"{value}\n")
    return root


# ------------------------------------------------------------ the reader


def test_the_chips_come_from_the_drivers_sensors(tmp_path):
    reader = _load("bc250-gddr6-temp-reader", loaded=True, tmp_path=tmp_path)
    root = _hwmon(tmp_path, [46000, 52000, 52000, 50000, 50000, 52000, 54000, 56000])

    relay = reader.read_kernel_driver(root=root)

    assert relay["source"] == KERNEL_SOURCE and relay["kernel_driver"] is True
    assert relay["patch_active"] is True and relay["blocked_reason"] == ""
    assert [(chip["chip"], chip["code"], chip["temperature_c"]) for chip in relay["chips"]] == [
        (0, 0x2B, 46), (1, 0x2E, 52), (2, 0x2E, 52), (3, 0x2D, 50),
        (4, 0x2D, 50), (5, 0x2E, 52), (6, 0x2F, 54), (7, 0x30, 56),
    ]
    assert relay["average_c"] == pytest.approx(51.5)
    assert (relay["hotspot_c"], relay["hotspot_chip"]) == (56, 7)


def test_a_timeout_the_driver_turned_into_470_degrees_is_reported(tmp_path):
    # Over the reviewed payload the driver decodes its 0xFF/0xFE timeouts as
    # (255 * 2) - 40 and (254 * 2) - 40 degrees.
    reader = _load("bc250-gddr6-temp-reader", loaded=True, tmp_path=tmp_path)
    root = _hwmon(tmp_path, [46000, 470000, 468000, 50500, None, 52000, 54000, 56000])

    relay = reader.read_kernel_driver(root=root)

    assert [chip["chip"] for chip in relay["chips"]] == [0, 5, 6, 7]
    assert [(error["chip"], error["error"]) for error in relay["chip_errors"]] == [
        (1, "stage1_timeout"), (2, "stage2_timeout"), (3, "out_of_range"), (4, "unavailable"),
    ]
    assert relay["hotspot_c"] == 56


def test_a_driver_without_sensors_is_named(tmp_path):
    reader = _load("bc250-gddr6-temp-reader", loaded=True, tmp_path=tmp_path)
    (tmp_path / "empty").mkdir()

    relay = reader.read_kernel_driver(root=tmp_path / "empty")

    assert relay["patch_active"] is False
    assert relay["blocked_reason"] == "GDDR6_KERNEL_DRIVER_NO_SENSOR"


def test_status_reads_no_temperature_so_it_sends_nothing(tmp_path):
    reader = _load("bc250-gddr6-temp-reader", loaded=True, tmp_path=tmp_path)
    root = _hwmon(tmp_path, [46000] * 8)
    for path in (root / "hwmon3").glob("temp*_input"):
        path.unlink()  # a read here would have been a round of SMU messages

    relay = reader.read_kernel_driver(chips_wanted=False, root=root)

    assert relay["patch_active"] is True and relay["chips"] == []


def _forbid(*_args, **_kwargs):
    raise AssertionError("the SMU must not be touched beside the kernel driver")


def test_a_read_never_opens_the_smu_but_holds_the_locks(tmp_path, monkeypatch, capsys):
    reader = _load("bc250-gddr6-temp-reader", loaded=True, tmp_path=tmp_path)
    locks = []

    @contextlib.contextmanager
    def window_lock():
        locks.append("smn")
        yield

    monkeypatch.setattr(reader, "smn_window_lock", window_lock)
    monkeypatch.setattr(reader, "governor_unsettled", lambda: "")
    monkeypatch.setattr(reader, "external_collector_lock", _forbid)
    monkeypatch.setattr(reader, "_open_smu", _forbid)
    monkeypatch.setattr(reader, "HWMON_ROOT", _hwmon(tmp_path, [46000] * 8))

    assert reader._do_read(tmp_path / "no-checkout", os.getuid(), chips_wanted=True) == 0

    payload = json.loads(capsys.readouterr().out)
    assert locks == ["smn"]
    assert payload["kernel_driver"] is True and len(payload["chips"]) == 8


def test_a_read_still_waits_out_a_starting_governor(tmp_path, monkeypatch, capsys):
    reader = _load("bc250-gddr6-temp-reader", loaded=True, tmp_path=tmp_path)
    monkeypatch.setattr(reader, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(reader, "governor_unsettled", lambda: "starting")
    monkeypatch.setattr(reader, "read_kernel_driver", _forbid)

    reader._do_read(tmp_path, os.getuid(), chips_wanted=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["deferred"] is True and payload["kernel_driver"] is True
    assert payload["blocked_reason"] == "GDDR6_GOVERNOR_UNSETTLED"


@pytest.mark.parametrize("name", ["bc250-gddr6-temp-reader", "bc250-gddr6-temp-helper"])
def test_no_checkout_is_validated_or_needed(name, tmp_path, monkeypatch):
    module = _load(name, loaded=True, tmp_path=tmp_path)
    seen = []
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module, "_trusted_self", lambda: True)
    monkeypatch.setattr(module, "_bc250_identity_present", lambda: True)
    monkeypatch.setattr(module, "_invoking_user", lambda: (1000, 1000, tmp_path))
    monkeypatch.setattr(module, "_validate_repository", _forbid)
    if name.endswith("reader"):
        monkeypatch.setattr(module, "_do_read", lambda repository, *a, **k: seen.append(repository) or 0)
        argv = [name, "--repo", "/home/user/missing", "--action", "read"]
    else:
        monkeypatch.setattr(module, "_do_apply", lambda repository, *a, **k: seen.append(repository) or 0)
        argv = [name, "--repo", "/home/user/missing", "--action", "apply"]

    assert module.main(argv) == 0
    assert seen == [Path("/home/user/missing")]


# ------------------------------------------------------------ the patcher


def test_nothing_is_patched_beside_the_driver(tmp_path, monkeypatch, capsys):
    helper = _load("bc250-gddr6-temp-helper", loaded=True, tmp_path=tmp_path)
    for name in ("staged_checkout", "_patch_status", "smn_window_lock", "external_collector_lock"):
        monkeypatch.setattr(helper, name, _forbid)
    monkeypatch.setattr(helper.subprocess, "run", _forbid)
    # Not even on another firmware: nothing is written, so it does not matter.
    monkeypatch.setattr(helper, "bios_version", lambda: "P5.00")

    assert helper._do_apply(tmp_path, os.getuid(), os.getgid()) == 0
    assert "bc250_memory" in capsys.readouterr().out


def test_a_status_from_the_driver_needs_no_patch(tmp_path):
    helper = _load("bc250-gddr6-temp-helper", loaded=False, tmp_path=tmp_path)
    assert helper._patch_arguments({"kernel_driver": True, "patch_active": True}) is None


def test_a_session_samples_the_driver_without_patching(tmp_path, monkeypatch, capsys):
    helper = _load("bc250-gddr6-temp-helper", loaded=True, tmp_path=tmp_path)
    sample = {"kernel_driver": True, "patch_active": True, "source": KERNEL_SOURCE,
              "chips": [{"chip": 0, "code": 43, "temperature_c": 46}]}
    reads = []
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(helper, "_read_once", lambda _r, _repo, _uid, action, **_kw: reads.append(action) or dict(sample))
    monkeypatch.setattr(helper, "_do_apply", _forbid)
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)

    assert helper._do_monitor(tmp_path, os.getuid(), os.getgid(), 0.03) == 0
    assert reads[0] == "status" and "read" in reads
    assert json.loads(capsys.readouterr().out.splitlines()[0])["source"] == KERNEL_SOURCE


def test_the_decky_helper_offers_homes_without_a_checkout(tmp_path, monkeypatch):
    loader = importlib.machinery.SourceFileLoader(
        "bc250_quick_access_helper_kd", str(HELPERS / "bc250-quick-access-helper")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    helper = importlib.util.module_from_spec(spec)
    loader.exec_module(helper)
    home = tmp_path / "home" / "user"
    home.mkdir(parents=True)
    monkeypatch.setattr(helper, "GDDR6_HOME_ROOTS", (tmp_path / "home",))
    monkeypatch.setattr(helper, "GDDR6_MIN_DESKTOP_UID", 0)

    monkeypatch.setattr(helper, "GDDR6_KERNEL_DRIVER", tmp_path / "absent")
    assert helper._gddr6_repository_candidates() == []

    monkeypatch.setattr(helper, "GDDR6_KERNEL_DRIVER", tmp_path)
    assert [path.parent.parent.parent.parent.parent for path, _uid in helper._gddr6_repository_candidates()] == [home]


# ------------------------------------------------------------ the desktop


def test_the_desktop_needs_no_checkout_and_no_firmware_gate(tmp_path):
    from tests.repositories.test_gddr6_memory_temp_repository import FakeRepository

    repository = FakeRepository(tmp_path, helper_path="/usr/libexec/helper", reader_path="/usr/libexec/reader",
                                bios_version="P5.00")
    repository.kernel_driver = True

    assert repository.estado_gddr6_memory_temp()["kernel_driver"] is True
    command = repository.comando_monitorizar_vram()
    assert "/usr/libexec/helper" in command and "monitor" in command

    repository.kernel_driver = False
    with pytest.raises(RuntimeError, match="GDDR6_FIRMWARE_UNSUPPORTED"):
        repository.comando_monitorizar_vram()


def test_live_monitoring_is_offered_without_a_checkout():
    reading = Gddr6Reading(
        hardware_detected=True, reader_ready=True, helper_ready=True,
        repository_ready=False, firmware_supported=False, kernel_driver=True,
    )

    assert reading.can_read and reading.can_monitor and not reading.can_apply
    assert reading.blocker() != "The reviewed upstream checkout is not prepared yet."
    assert "bc250_memory" in Gddr6Reading(
        hardware_detected=True, reader_ready=True, kernel_driver=True,
        blocked_reason="GDDR6_KERNEL_DRIVER_NO_SENSOR",
    ).notice()


def test_the_helpers_know_the_driver_by_the_same_name(tmp_path):
    reader = _load("bc250-gddr6-temp-reader", loaded=False, tmp_path=tmp_path)
    assert reader.KERNEL_DRIVER_NAME == KERNEL_SOURCE
    output = subprocess.run(
        ["grep", "-c", "/sys/module/bc250_memory", str(HELPERS / "bc250-gddr6-temp-helper"),
         str(HELPERS / "bc250-gddr6-temp-reader"), str(HELPERS / "bc250-quick-access-helper")],
        capture_output=True, text=True,
    ).stdout
    assert all(line.endswith(":1") for line in output.strip().splitlines())
