"""Which BIOS image the board runs, told only as far as the evidence goes.

DMI says "P3.00" for ASRock's image, the Chipset Menu mod and MeiMeiDXE v3
alike. The dashboard names the image when something the running system
exposes without root settles it, and says it cannot when nothing does.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from bc250cc.infrastructure.firmware.board import (
    BoardFirmware,
    efi_variable_names,
    identify_installed_bios,
    load_prepared_kit,
    read_installed_bios,
    record_prepared_kit,
)
from bc250cc.infrastructure.vrm_telemetry_reader import sondear_telemetria_vrm

P3 = BoardFirmware(board="AMD BC-250", version="P3.00")
GIB = 1024 ** 3


@pytest.mark.parametrize("version, family", [("P2.00", "p2-stock"), ("P5.00", "p5-stock")])
def test_versions_only_asrock_publishes_are_settled_by_dmi(version, family):
    installed = identify_installed_bios(BoardFirmware(version=version), vram_total_bytes=8 * GIB)
    assert (installed.version, installed.variant, installed.family) == (version, "ASRock", family)


def test_p3_with_nothing_else_to_go_on_is_left_undecided():
    installed = identify_installed_bios(P3, vram_total_bytes=512 * 1024 ** 2, physical_cores=6)
    assert (installed.variant, installed.family) == ("", "")
    assert "same version" in installed.evidence


def test_meimeidxe_is_told_by_its_own_efi_variable():
    names = ("AmdSetup-3a997502", "MeiMeiDXEv3Config-0f5f6f7a")
    installed = identify_installed_bios(P3, efi_variables=names)
    assert installed.family == "meimeidxe-v3"


def test_vram_beyond_asrocks_menu_means_the_cbs_menu_was_opened():
    chipset = identify_installed_bios(P3, vram_total_bytes=4 * GIB, physical_cores=6)
    assert chipset.family == "p3-chipset-menu"
    eight_cores = identify_installed_bios(P3, vram_total_bytes=4 * GIB, physical_cores=8)
    assert eight_cores.family == "meimeidxe-v3"
    # 2 GB is still within ASRock's own (hidden) UMA option.
    assert identify_installed_bios(P3, vram_total_bytes=2 * GIB).family == ""


def test_a_kit_counts_only_when_the_version_changed_to_the_kits(tmp_path):
    kit = tmp_path / "kit.json"
    record_prepared_kit("p3-chipset-menu", "P3.00", "P2.00", kit)
    assert load_prepared_kit(kit) == {"family": "p3-chipset-menu", "version": "P3.00", "seen": "P2.00"}
    assert identify_installed_bios(P3, prepared_kit=load_prepared_kit(kit)).family == "p3-chipset-menu"

    # Written while the board already said P3.00: flashing it changed nothing
    # DMI can see, so the kit alone proves nothing.
    record_prepared_kit("p3-chipset-menu", "P3.00", "P3.00", kit)
    assert identify_installed_bios(P3, prepared_kit=load_prepared_kit(kit)).family == ""
    # A kit for another version says nothing about a P3.00 board either.
    record_prepared_kit("p5-stock", "P5.00", "P2.00", kit)
    assert identify_installed_bios(P3, prepared_kit=load_prepared_kit(kit)).family == ""


def test_unreadable_sources_give_an_honest_blank(tmp_path):
    (tmp_path / "kit.json").write_text("{not json", encoding="utf-8")
    assert load_prepared_kit(tmp_path / "kit.json") == {}
    assert efi_variable_names(tmp_path / "missing") == ()
    installed = read_installed_bios(
        dmi_root=tmp_path / "no-dmi", efivars_root=tmp_path / "missing", kit_path=tmp_path / "kit.json",
    )
    assert installed.version == "" and "did not report" in installed.evidence


def test_the_whole_reader_on_a_fake_sysfs(tmp_path):
    dmi = tmp_path / "dmi"
    dmi.mkdir()
    (dmi / "bios_version").write_text("P3.00\n", encoding="utf-8")
    (dmi / "board_name").write_text("AMD BC-250\n", encoding="utf-8")
    efivars = tmp_path / "efivars"
    efivars.mkdir()
    (efivars / "MeiMeiDXEv3Cores-1234").write_bytes(b"\x07\x00\x00\x00\xff")
    installed = read_installed_bios(dmi_root=dmi, efivars_root=efivars, kit_path=tmp_path / "none.json")
    assert (installed.version, installed.variant) == ("P3.00", "MeiMeiDXE v3")


def _snapshot(tmp_path, cpu_valid, age=0.0):
    path = tmp_path / "apu_telemetry.json"
    rail = {"vin": 12.1, "vout": 0.9, "iout": 3.0, "pout": 2.7, "temp": 41.0}
    path.write_text(json.dumps({"hardware": {
        "cpu": {"valid": cpu_valid, **rail},
        "gpu": {"valid": False, "vin": 0.0, "vout": 0.0, "iout": 0.0, "pout": 0.0, "temp": -1},
        "total_power": 0.0, "total_power_valid": False,
    }}), encoding="utf-8")
    if age:
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
    return path


def test_the_probe_keeps_what_the_checked_reader_throws_away(tmp_path):
    probe = sondear_telemetria_vrm(_snapshot(tmp_path, cpu_valid=False))
    assert probe["daemon"] == "running"
    assert probe["rails"]["cpu"] == {"valid": False, "vin": 12.1, "vout": 0.9, "iout": 3.0, "pout": 2.7, "temp": 41.0}
    # The daemon's -1 still means "did not answer".
    assert probe["rails"]["gpu"]["temp"] is None

    stale = sondear_telemetria_vrm(_snapshot(tmp_path, cpu_valid=True, age=60), max_age=5.0)
    assert stale["daemon"] == "stale" and stale["age_s"] >= 59
    assert sondear_telemetria_vrm(tmp_path / "absent.json")["daemon"] == "missing"
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert sondear_telemetria_vrm(tmp_path / "broken.json")["daemon"] == "unreadable"
