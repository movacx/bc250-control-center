"""Async compute from the patched RADV alone, on Arch-family and Fedora kernels 7.2+.

Bazzite's release runs the patched RADV on the stock amdgpu of its OGC 7.2
kernel, and the amdgpu of 7.2 is the same on CachyOS and Fedora, so there the
driver is all async compute needs. These tests pin who is offered it, what the
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
        ("fedora", "fedora", "7.2.8-200.fc44.x86_64", True),
        ("fedora", "nobara", "7.2.3-201.nobara.fc44.x86_64", True),
        # Fedora 43's kernel: DryhoppedIPA's installer keeps it.
        ("fedora", "fedora", "7.1.5-101.fc43.x86_64", False),
        ("debian", "debian", "7.2.0-1-amd64", False),
    ],
)
def test_only_arch_family_and_fedora_kernels_from_7_2_are_offered(family, distro_id, kernel, allowed):
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
    # Fedora Atomic images are detected as immutable and stay out as well.
    assert radv_async_supported(family="fedora", distro_id="fedora", kernel="7.2.8", immutable=True)[0] is False


@pytest.fixture
def installed(tmp_path, monkeypatch):
    prefix_root = tmp_path / "opt"
    conf = tmp_path / "etc"
    run = tmp_path / "run"
    monkeypatch.setattr(radv, "PREFIX_ROOT", prefix_root)
    monkeypatch.setattr(radv, "CONF_DIR", conf)
    monkeypatch.setattr(radv, "GFX1013_RUN_DIR", run)
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("root=UUID=x ro rhgb quiet\n", encoding="utf-8")
    monkeypatch.setattr(radv, "PROC_CMDLINE", cmdline)

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


def test_a_boot_of_dryhoppeds_patched_fedora_entry_defers_like_the_generator(installed):
    """That entry's own generator offers its RADV; this route steps aside."""
    install, _run = installed
    install()
    assert _state(environ={})["state"] == "relogin-required"
    radv.PROC_CMDLINE.write_text("root=UUID=x ro amdgpu.sched_policy=2 bc250.gfx1013_v33=1\n", encoding="utf-8")
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


def _function(name: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    return re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.S | re.M).group(0)


def test_fedora_dependencies_are_installed_through_dnf():
    deps = _function("deps_fedora")
    assert 'rpm -q --quiet "$package"' in deps
    assert 'sudo dnf install -y "${missing[@]}"' in deps
    # Mesa itself, then what the verification tests compile and read back with.
    for package in ("meson", "ninja-build", "python3-mako", "python3-packaging", "glslang",
                    "libdrm-devel", "spirv-tools-devel", "zlib-ng-compat-devel",
                    "glslc", "vulkan-headers", "vulkan-loader-devel", "vulkan-tools"):
        assert f" {package}" in deps or f"({package}" in deps, package
    assert "fedora) deps_fedora" in _function("deps")


@pytest.mark.parametrize(
    ("os_release", "expected"),
    [
        ('ID=fedora\nVERSION_ID=44\n', "fedora"),
        ('ID=nobara\nID_LIKE="rhel centos fedora"\n', "fedora"),
        ('ID=bazzite\nID_LIKE="fedora"\n', "bazzite"),
        ('ID=cachyos\nID_LIKE=arch\n', "arch"),
        ('ID=ubuntu\nID_LIKE=debian\n', "other"),
    ],
)
def test_the_script_names_the_family_the_way_the_application_does(tmp_path, os_release, expected):
    release = tmp_path / "os-release"
    release.write_text(os_release, encoding="utf-8")
    os_field = _function("os_field").replace("/etc/os-release", str(release))
    script = f"{os_field}{_function('family')}family\n"
    output = subprocess.run(["bash", "-c", script], text=True, capture_output=True, check=True).stdout
    assert output.strip() == expected


def test_the_script_offers_fedora_and_still_refuses_image_based_systems():
    check = _function("check_host")
    assert "fedora) die" not in check
    assert "/run/ostree-booted" in check
    # An older Fedora kernel is sent to DryhoppedIPA's installer, not the source build.
    assert "use DryhoppedIPA's installer instead" in check


def test_installed_files_get_the_selinux_types_policy_expects():
    """cp -a carried the build cache's type into /opt; restorecon replaces it."""
    # The function embeds whole scripts in heredocs, so it ends where the next one starts.
    text = SCRIPT.read_text(encoding="utf-8")
    install = text[text.index("\ninstall_release() {"):text.index("\nenable_driver() {")]
    assert 'restorecon -RF "$PREFIX_ROOT" "$LIB_DIR" "$CONF_DIR" "$HELPER" "$GENERATOR"' in install
    assert install.index('cp -a "$stage/root$prefix"') < install.index("restorecon -RF")


def test_the_installed_driver_belongs_to_root_not_to_the_user_who_built_it():
    """cp -a kept the builder's ownership: every session loaded a user-replaceable driver."""
    text = SCRIPT.read_text(encoding="utf-8")
    install = text[text.index("\ninstall_release() {"):text.index("\nenable_driver() {")]
    copy = install.index('cp -a "$stage/root$prefix" "$prefix.new"')
    assert copy < install.index('chown -R root:root "$prefix.new"') < install.index('mv -- "$prefix.new" "$prefix"')
    assert 'chmod -R go-w "$prefix.new"' in install


def test_the_status_tool_reads_the_system_mesa_on_fedora_too():
    text = SCRIPT.read_text(encoding="utf-8")
    # 64- and 32-bit packages both answer: one line each, the first one shown.
    assert "rpm -q --qf '%{VERSION}-%{RELEASE}\\n' mesa-vulkan-drivers" in text
    assert "awk 'NR == 1 {print $NF}'" in text


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
    ["switched-off", "boot-menu", "no-amdgpu", "old-kernel", "kernel-side-fix", "dryhopped-boot",
     "no-driver", "bad-version"],
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
    elif condition == "dryhopped-boot":
        (root / "proc/cmdline").write_text("root=UUID=x ro amdgpu.sched_policy=2 bc250.gfx1013_v33=1\n", encoding="utf-8")
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


def test_fedora_on_7_2_gets_this_route_instead_of_dryhoppeds_installer():
    from tests.infrastructure.test_upstream_preparation_presentation import _sidebar
    from tests.infrastructure.test_upstream_preparation_presentation import (
        _state as sidebar_state,
    )

    sidebar = _sidebar()
    state = sidebar_state("fedora", {})
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "fedora-upstream-managed",
        "dryhopped_installed": True,
        "radv_async": {"supported": True, "state": "not-installed", "kernel": "7.2.8-200.fc44.x86_64",
                       "expected_version": RADV_ASYNC_MESA_VERSION},
        "source": {"supported": False, "installed": False},
    }
    sidebar.set_state(state)

    assert not sidebar.gfx_card.isHidden()
    assert sidebar.gfx_primary_button.request_payload["action"] == "radv_async_install"
    # DryhoppedIPA's leftover install is offered for removal, never for install.
    assert sidebar.gfx_quaternary_button.request_payload["action"] == "gfx1013_fedora_uninstall"
    assert not sidebar.gfx_quaternary_button.isHidden()
    actions = {
        button.request_payload["action"]
        for button in (sidebar.gfx_primary_button, sidebar.gfx_secondary_button,
                       sidebar.gfx_tertiary_button, sidebar.gfx_quaternary_button,
                       sidebar.gfx_quinary_button)
        if not button.isHidden()
    }
    assert "gfx1013_fedora_install" not in actions
    assert "7.2.8-200.fc44.x86_64" in sidebar.gfx_card.detail.text()
    assert "Fedora" in sidebar.gfx_card.scope.text()


def test_fedora_before_7_2_keeps_dryhoppeds_installer():
    from tests.infrastructure.test_upstream_preparation_presentation import _sidebar
    from tests.infrastructure.test_upstream_preparation_presentation import (
        _state as sidebar_state,
    )

    sidebar = _sidebar()
    state = sidebar_state("fedora", {})
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "fedora-upstream-managed",
        "dryhopped_installed": False,
        "radv_async": {"supported": False, "state": "not-installed", "kernel": "7.1.5-101.fc43.x86_64"},
    }
    sidebar.set_state(state)

    assert sidebar.gfx_primary_button.request_payload["action"] == "gfx1013_fedora_install"
