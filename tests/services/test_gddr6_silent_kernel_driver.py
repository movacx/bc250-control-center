"""bc250_memory loaded but silent: Control Center patches, then wakes it.

Reported 2026-11-20: on a stock P3.00 BIOS Hexxeh's driver logs "SMU debug
access is locked (0xFD)" and registers no sensor. The helpers took the
loaded module as the one reading, so they neither patched nor read, and the
Monitor live button showed nothing after the Polkit prompt.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"


def _load(name: str, tmp_path: Path, *, hwmon: bool):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_") + "_silent", str(HELPERS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    (tmp_path / "module").mkdir(exist_ok=True)
    root = tmp_path / "hwmon"
    root.mkdir(exist_ok=True)
    if hwmon:
        (root / "hwmon5").mkdir(exist_ok=True)
        (root / "hwmon5" / "name").write_text("bc250_memory\n")
    module.KERNEL_DRIVER_MODULE = tmp_path / "module"
    module.HWMON_ROOT = root
    return module


def test_a_loaded_driver_without_a_sensor_is_not_the_one_reading(tmp_path):
    for name in ("bc250-gddr6-temp-helper", "bc250-gddr6-temp-reader"):
        assert not _load(name, tmp_path, hwmon=False).kernel_driver_loaded()


def test_a_publishing_driver_still_owns_the_patch(tmp_path):
    for name in ("bc250-gddr6-temp-helper", "bc250-gddr6-temp-reader"):
        assert _load(name, tmp_path, hwmon=True).kernel_driver_loaded()


def test_after_patching_the_silent_driver_is_reloaded_under_the_lock(tmp_path, monkeypatch, capsys):
    helper = _load("bc250-gddr6-temp-helper", tmp_path, hwmon=False)
    events = []

    @contextlib.contextmanager
    def lock():
        events.append("lock")
        yield
        events.append("unlock")

    def run(argv, **_kwargs):
        events.append(" ".join(argv))
        if argv == ["modprobe", "bc250_memory"]:
            (tmp_path / "hwmon" / "hwmon5").mkdir()
            (tmp_path / "hwmon" / "hwmon5" / "name").write_text("bc250_memory\n")

    monkeypatch.setattr(helper, "smn_window_lock", lock)
    monkeypatch.setattr(helper.subprocess, "run", run)
    helper._wake_kernel_driver()

    assert events == ["lock", "modprobe -r bc250_memory", "modprobe bc250_memory", "unlock"]
    assert "now reads the memory temperature" in capsys.readouterr().out


def test_a_driver_that_already_reads_is_left_alone(tmp_path, monkeypatch):
    helper = _load("bc250-gddr6-temp-helper", tmp_path, hwmon=True)
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    helper._wake_kernel_driver()


def test_the_desktop_asks_for_the_sensor_not_just_the_module(tmp_path):
    from bc250cc.infrastructure.gddr6_memory_temp_repository import (
        kernel_driver_publishing,
    )

    (tmp_path / "module").mkdir()
    (tmp_path / "hwmon").mkdir()
    assert not kernel_driver_publishing(tmp_path / "module", tmp_path / "hwmon")
    (tmp_path / "hwmon" / "hwmon2").mkdir()
    (tmp_path / "hwmon" / "hwmon2" / "name").write_text("bc250_memory\n")
    assert kernel_driver_publishing(tmp_path / "module", tmp_path / "hwmon")
