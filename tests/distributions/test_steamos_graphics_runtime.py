from __future__ import annotations

import hashlib
from pathlib import Path

from bc250cc.infrastructure.steamos_graphics_runtime import (
    CURRENT_FSR4_PATCH_SHA256,
    CURRENT_MESA_TAG,
    CURRENT_UPSTREAM_COMMIT,
    LEGACY_UPSTREAM_COMMIT,
    STEAMOS_FSR4_LAUNCH_OPTION,
    probe_steamos_graphics_runtime,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: bytes | str, *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
    if executable:
        path.chmod(0o700)
    return path


def _install_current_runtime(tmp_path: Path, *, fsr4: bool = False) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    state = home / ".local/share/bc250-mesh-shader"
    driver = _write(tmp_path / "system/libvulkan_radeon_driconf.so", b"radv")
    icd = _write(home / "radeon_driconf_icd.x86_64.json", b'{"ICD": "radv"}')
    _write(
        state / "install.conf",
        f"{_digest(driver)} {_digest(icd)} {CURRENT_MESA_TAG} {CURRENT_UPSTREAM_COMMIT}\n",
    )
    if fsr4:
        fsr4_dir = state / "fsr4"
        fsr4_driver = _write(fsr4_dir / "libvulkan_radeon.so", b"fsr4-radv")
        fsr4_icd = _write(fsr4_dir / "radeon_fsr4_icd.x86_64.json", b'{"ICD": "fsr4"}')
        runner = _write(fsr4_dir / "bc250-fsr4-run", "#!/bin/sh\n", executable=True)
        _write(
            fsr4_dir / "install.conf",
            " ".join((
                _digest(fsr4_driver), _digest(fsr4_icd), _digest(runner),
                CURRENT_MESA_TAG, CURRENT_FSR4_PATCH_SHA256,
            )) + "\n",
        )
    return home, driver, icd


def test_probe_reports_absent_external_runtime_without_creating_files(tmp_path):
    home = tmp_path / "home"

    state = probe_steamos_graphics_runtime(home=home)

    assert state["radv"]["state"] == "not-installed"
    assert state["fsr4"]["state"] == "not-installed"
    assert not home.exists()


def test_probe_verifies_current_radv_and_per_game_fsr4_profile(tmp_path):
    home, driver, icd = _install_current_runtime(tmp_path, fsr4=True)

    state = probe_steamos_graphics_runtime(
        home=home, driver_path=driver, icd_path=icd
    )

    assert state["radv"] == {
        "state": "ready", "present": True, "ready": True, "current": True,
        "legacy": False, "mesa_tag": CURRENT_MESA_TAG,
        "upstream_commit": CURRENT_UPSTREAM_COMMIT,
    }
    assert state["fsr4"]["state"] == "ready"
    assert state["fsr4"]["current"] is True
    assert state["fsr4"]["runner_path"].endswith("/fsr4/bc250-fsr4-run")
    assert state["fsr4"]["steam_launch_option"] == STEAMOS_FSR4_LAUNCH_OPTION
    assert state["incomplete"] is False


def test_probe_marks_tampered_profile_as_invalid_without_following_symlinks(tmp_path):
    home, driver, icd = _install_current_runtime(tmp_path, fsr4=True)
    profile = home / ".local/share/bc250-mesh-shader/fsr4"
    (profile / "bc250-fsr4-run").unlink()
    (profile / "bc250-fsr4-run").symlink_to(tmp_path / "other-runner")

    state = probe_steamos_graphics_runtime(
        home=home, driver_path=driver, icd_path=icd
    )

    assert state["radv"]["state"] == "ready"
    assert state["fsr4"]["state"] == "invalid"
    assert state["incomplete"] is True


def test_probe_distinguishes_a_verified_legacy_manifest_from_current_runtime(tmp_path):
    home, driver, icd = _install_current_runtime(tmp_path)
    manifest = home / ".local/share/bc250-mesh-shader/install.conf"
    manifest.write_text(
        f"{_digest(driver)} {_digest(icd)} {CURRENT_MESA_TAG} {LEGACY_UPSTREAM_COMMIT}\n",
        encoding="utf-8",
    )

    state = probe_steamos_graphics_runtime(
        home=home, driver_path=driver, icd_path=icd
    )

    assert state["radv"]["state"] == "ready"
    assert state["radv"]["legacy"] is True
    assert state["legacy_radv_detected"] is True
