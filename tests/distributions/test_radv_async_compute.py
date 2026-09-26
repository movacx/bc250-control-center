"""Async compute from the patched RADV alone, on Arch-family kernels 7.2+.

Bazzite's release runs the patched RADV on the stock amdgpu of its OGC 7.2
kernel, and the amdgpu of 7.2 is the same on CachyOS, so there the driver is
all async compute needs. These tests pin who is offered it, what the
installed files mean, what the embedded terminal runs, and the generator that
decides, at every login, whether a session gets the patched driver.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import radv_async_compute as radv
from bc250cc.infrastructure.radv_async_compute import (
    RADV_ASYNC_MESA_VERSION,
    RADV_ASYNC_REVIEWED_COMMIT,
    build_radv_async_command,
    radv_async_state,
    radv_async_supported,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "system" / "bc250-async-compute-radv.sh"


@pytest.mark.parametrize(
    ("family", "distro_id", "kernel", "allowed"),
    [
        ("cachyos", "cachyos", "7.2.7-1-cachyos", True),
        ("arch", "arch", "7.3.0-arch1-1", True),
        ("manjaro", "manjaro", "7.2.1-1-MANJARO", True),
        ("arch", "arch", "7.1.9-arch1-1", False),
        ("arch", "arch", "6.18.52-1-lts", False),
        ("cachyos", "cachyos", "7.2.7-1-cachyos-bc250", False),
        ("bazzite", "bazzite", "7.2.1-ogc4.1.fc44.x86_64", False),
        ("steamos", "steamos", "7.2.0-valve1", False),
        ("fedora", "fedora", "7.2.3-200.fc44.x86_64", False),
        ("debian", "debian", "7.2.0-1-amd64", False),
    ],
)
def test_only_arch_family_kernels_from_7_2_are_offered(family, distro_id, kernel, allowed):
    supported, reason = radv_async_supported(family=family, distro_id=distro_id, kernel=kernel)
    assert supported is allowed
    assert bool(reason) is (not allowed)


def test_bazzite_is_never_offered_this_route():
    """Its async-compute release is untouchable; this build must refuse it."""
    for kernel in ("7.2.1-ogc4.1", "7.3.0-ogc1"):
        supported, reason = radv_async_supported(family="bazzite", distro_id="bazzite", kernel=kernel)
        assert not supported and "Bazzite" in reason
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'bazzite) die "Bazzite keeps its own reviewed async-compute release' in text
    assert radv_async_supported(family="arch", kernel="7.2.7", immutable=True)[0] is False


@pytest.fixture
def installed(tmp_path, monkeypatch):
    prefix_root = tmp_path / "opt"
    conf = tmp_path / "etc"
    run = tmp_path / "run"
    monkeypatch.setattr(radv, "PREFIX_ROOT", prefix_root)
    monkeypatch.setattr(radv, "CONF_DIR", conf)
    monkeypatch.setattr(radv, "GFX1013_RUN_DIR", run)

    def install(*, version=RADV_ASYNC_MESA_VERSION, enabled=True, driver=True):
        conf.mkdir(parents=True, exist_ok=True)
        (conf / "active.env").write_text(f"{radv.MARKER}\nVERSION={version}\n", encoding="utf-8")
        if enabled:
            (conf / "enabled").write_text("", encoding="utf-8")
        if driver:
            base = prefix_root / version
            (base / "lib").mkdir(parents=True, exist_ok=True)
            (base / "lib/libvulkan_radeon.so").write_text("so", encoding="utf-8")
            (base / "share/vulkan/icd.d").mkdir(parents=True, exist_ok=True)
            (base / "share/vulkan/icd.d/radeon_icd.x86_64.json").write_text("{}", encoding="utf-8")
        return prefix_root / version / "share/vulkan/icd.d/radeon_icd.x86_64.json"

    return install, run


def _state(**kwargs):
    return radv_async_state(family="cachyos", distro_id="cachyos", kernel="7.2.7-1-cachyos", **kwargs)


def test_the_state_follows_the_files_and_the_session(installed):
    install, run = installed
    assert _state(environ={})["state"] == "not-installed"

    icd = install()
    assert _state(environ={})["state"] == "relogin-required"
    assert _state(environ={"VK_DRIVER_FILES": f"{icd}:/usr/share/vulkan/icd.d/lvp_icd.x86_64.json"})["state"] == "active"

    (radv.CONF_DIR / "enabled").unlink()
    assert _state(environ={})["state"] == "switched-off"

    run.mkdir(parents=True, exist_ok=True)
    (run / "loaded").write_text("patched\n", encoding="utf-8")
    assert _state(environ={})["state"] == "deferred"


def test_missing_driver_files_ask_for_a_repair_and_an_old_build_for_an_update(installed):
    install, _run = installed
    install(driver=False)
    assert _state(environ={})["state"] == "invalid"
    install(version="26.2.1")
    state = _state(environ={})
    assert state["outdated"] is True and state["version"] == "26.2.1"


def test_privileged_steps_run_a_root_owned_copy_and_the_build_runs_as_the_user(tmp_path):
    checkout = tmp_path / "upstream"
    install = build_radv_async_command("install", checkout)
    assert RADV_ASYNC_REVIEWED_COMMIT in install
    assert "bash " + str(SCRIPT) + " deps" in install
    assert f"build --source {checkout}" in install
    assert 'sudo install -m 0755' in install and 'sudo bash "$bc250_root_script" install --stage' in install
    assert "sudo bash " + str(SCRIPT) not in install
    assert "sudo -v" in install  # asked once, kept through the build
    for action in ("enable", "disable", "uninstall"):
        command = build_radv_async_command(action, checkout)
        assert f'sudo bash "$bc250_root_script" {action}' in command
    assert "sudo" not in build_radv_async_command("status", checkout)
    assert "bc250cc-async-compute test" in build_radv_async_command("test", checkout)
    with pytest.raises(ValueError):
        build_radv_async_command("rm -rf /", checkout)


def test_the_script_and_the_module_pin_the_same_mesa():
    text = SCRIPT.read_text(encoding="utf-8")
    assert f"MESA_VERSION={RADV_ASYNC_MESA_VERSION}\n" in text
    assert re.search(r"MESA_SHA256=[0-9a-f]{64}\n", text)
    assert 'sha256sum -c -' in text
    # The ICD manifest must point at the final prefix, or the loader finds nothing.
    assert "the ICD manifest does not point at" in text
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


def test_arch_dependencies_are_asked_through_pacman_deptest():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'pacman -T "${wanted[@]}"' in text
    assert "shaderc" in text and "vulkan-headers" in text


def _generator(tmp_path: Path) -> Path:
    """The generator exactly as install writes it, with the script's values."""
    text = SCRIPT.read_text(encoding="utf-8")
    body = re.search(r"<<GEN\n(.*?)\nGEN\n", text, re.S).group(1)
    values = {
        name: re.search(rf"^{name}=(.*)$", text, re.M).group(1).strip('"')
        for name in ("MARKER", "CONF_DIR", "PREFIX_ROOT", "MIN_MAJOR", "MIN_MINOR")
    }
    assignments = "".join(f"{name}={value!r}\n" for name, value in values.items())
    target = tmp_path / "61-bc250cc-radv"
    subprocess.run(
        ["bash", "-c", f"{assignments}cat > {target} <<GEN\n{body}\nGEN\n"],
        check=True,
    )
    return target


@pytest.fixture
def fake_session(tmp_path):
    root = tmp_path / "root"
    icd = root / f"opt/bc250cc-radv/{RADV_ASYNC_MESA_VERSION}/share/vulkan/icd.d/radeon_icd.x86_64.json"
    icd.parent.mkdir(parents=True)
    icd.write_text("{}", encoding="utf-8")
    for name in ("radeon_icd.i686.json", "lvp_icd.x86_64.json"):
        target = root / "usr/share/vulkan/icd.d" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    (root / "etc/bc250cc-radv").mkdir(parents=True)
    (root / "etc/bc250cc-radv/active.env").write_text(f"VERSION={RADV_ASYNC_MESA_VERSION}\n", encoding="utf-8")
    (root / "etc/bc250cc-radv/enabled").write_text("", encoding="utf-8")
    (root / "proc").mkdir()
    (root / "proc/cmdline").write_text("root=UUID=x rw quiet\n", encoding="utf-8")
    (root / "sys/module/amdgpu").mkdir(parents=True)
    generator = _generator(tmp_path)

    def run(kernel: str = "7.2.7-1-cachyos") -> str:
        env = {**os.environ, "BC250CC_TEST_ROOT": str(root), "BC250CC_TEST_KERNEL": kernel}
        return subprocess.run(["sh", str(generator)], env=env, text=True, capture_output=True, check=True).stdout

    return root, run


def test_a_session_gets_the_patched_driver_with_the_system_32_bit_one_and_llvmpipe(fake_session):
    _root, run = fake_session
    output = run()
    expected = (
        f"/opt/bc250cc-radv/{RADV_ASYNC_MESA_VERSION}/share/vulkan/icd.d/radeon_icd.x86_64.json"
        ":/usr/share/vulkan/icd.d/radeon_icd.i686.json:/usr/share/vulkan/icd.d/lvp_icd.x86_64.json"
    )
    assert f"VK_DRIVER_FILES={expected}\n" in output
    assert f"VK_ICD_FILENAMES={expected}\n" in output
    assert run("7.3.0-arch1-1").startswith("VK_DRIVER_FILES=")


@pytest.mark.parametrize(
    "condition",
    ["switched-off", "boot-menu", "no-amdgpu", "old-kernel", "kernel-side-fix", "no-driver", "bad-version"],
)
def test_a_session_keeps_the_system_driver_whenever_it_should(fake_session, condition):
    root, run = fake_session
    kernel = "7.2.7-1-cachyos"
    if condition == "switched-off":
        (root / "etc/bc250cc-radv/enabled").unlink()
    elif condition == "boot-menu":
        (root / "proc/cmdline").write_text("root=UUID=x rw bc250.async=0\n", encoding="utf-8")
    elif condition == "no-amdgpu":
        (root / "sys/module/amdgpu").rmdir()
    elif condition == "old-kernel":
        kernel = "7.1.9-arch1-1"
    elif condition == "kernel-side-fix":
        (root / "run/bc250cc-gfx1013").mkdir(parents=True)
        (root / "run/bc250cc-gfx1013/loaded").write_text("patched\n", encoding="utf-8")
    elif condition == "no-driver":
        next(root.glob("opt/bc250cc-radv/*/share/vulkan/icd.d/radeon_icd.x86_64.json")).unlink()
    elif condition == "bad-version":
        (root / "etc/bc250cc-radv/active.env").write_text("VERSION=../../etc\n", encoding="utf-8")
    assert run(kernel) == ""


def test_the_dashboard_offers_the_build_and_the_removal_of_the_kernel_side_fix():
    from tests.infrastructure.test_upstream_preparation_presentation import _sidebar
    from tests.infrastructure.test_upstream_preparation_presentation import (
        _state as sidebar_state,
    )

    sidebar = _sidebar()
    state = sidebar_state("cachyos", {})
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "arch-family-manual-untested",
        "radv_async": {"supported": True, "state": "not-installed", "kernel": "7.2.7-1-cachyos",
                       "expected_version": RADV_ASYNC_MESA_VERSION},
        "source": {"supported": True, "installed": True, "state": "fell-back"},
    }
    sidebar.set_state(state)

    assert not sidebar.gfx_card.isHidden()
    assert sidebar.gfx_primary_button.request_payload["action"] == "radv_async_install"
    assert sidebar.gfx_quaternary_button.request_payload["action"] == "gfx1013_source_uninstall"
    assert not sidebar.gfx_quaternary_button.isHidden()
    assert RADV_ASYNC_MESA_VERSION in sidebar.gfx_card.detail.text()
