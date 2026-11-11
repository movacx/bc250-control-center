"""DirectMesh: pinned upstream installer, releases, state and commands."""

from __future__ import annotations

import json
import subprocess

import pytest

from bc250cc.infrastructure import directmesh, upscaler_releases

REVIEWED = directmesh.DIRECTMESH_REVIEWED["directmesh-v1.4"]["installer_sha256"]
NEW_DIGEST = "b" * 64


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "data"


def _release(tag, *, digest=NEW_DIGEST, prerelease=False, draft=False, installer=True):
    assets = [{"name": "SHA256SUMS", "size": 10, "digest": "sha256:" + "c" * 64}]
    if installer:
        assets.append({"name": "install.sh", "size": 9000, "digest": "sha256:" + digest})
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease, "assets": assets}


def _save_list(*entries):
    path = directmesh.directmesh_root() / "releases.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"time": 1, "releases": list(entries)}), encoding="utf-8")


def _install_driver(tag="directmesh-v1.4"):
    prefix = directmesh.directmesh_prefix()
    library = prefix / "lib" / "libvulkan_radeon.so"
    library.parent.mkdir(parents=True)
    library.write_bytes(b"\x7fELF")
    icd = directmesh.directmesh_icd()
    icd.parent.mkdir(parents=True)
    icd.write_text(json.dumps({"ICD": {"library_path": str(library)}}), encoding="utf-8")
    root = directmesh.directmesh_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "installed.json").write_text(json.dumps({"tag": tag}), encoding="utf-8")


def test_reviewed_release_is_offered_without_a_list():
    releases = directmesh.directmesh_releases()
    assert [r["tag"] for r in releases] == ["directmesh-v1.4"]
    assert releases[0]["reviewed"] and releases[0]["default"]
    assert releases[0]["installer_sha256"] == REVIEWED


def test_withdrawn_old_and_installerless_releases_are_never_offered():
    _save_list(
        _release("directmesh-v1.4", digest=REVIEWED),
        _release("directmesh-v1.4.1", prerelease=True),
        _release("directmesh-v1.3.1", installer=False),
        _release("directmesh-v131-auto-rdna1-975ec91", prerelease=True, installer=False),
        _release("directmesh-v1.5", draft=True),
    )
    assert [r["tag"] for r in directmesh.directmesh_releases()] == ["directmesh-v1.4"]


def test_newer_release_uses_githubs_digest_and_reviewed_keeps_its_own():
    _save_list(
        _release("directmesh-v1.5"),
        _release("directmesh-v1.4", digest="d" * 64),
    )
    releases = {r["tag"]: r for r in directmesh.directmesh_releases()}
    assert releases["directmesh-v1.5"]["installer_sha256"] == NEW_DIGEST
    assert not releases["directmesh-v1.5"]["reviewed"]
    assert releases["directmesh-v1.4"]["installer_sha256"] == REVIEWED


def test_selection_rejects_unknown_tags_and_falls_back_to_default():
    with pytest.raises(ValueError):
        directmesh.select_directmesh_release("directmesh-v1.4.1")
    _save_list(_release("directmesh-v1.5"), _release("directmesh-v1.4", digest=REVIEWED))
    directmesh.select_directmesh_release("directmesh-v1.5")
    assert directmesh.directmesh_release()["tag"] == "directmesh-v1.5"
    _save_list(_release("directmesh-v1.4", digest=REVIEWED))
    assert directmesh.directmesh_release()["tag"] == "directmesh-v1.4"


@pytest.mark.parametrize(
    ("family", "distro_id", "version_id", "platform"),
    [
        ("arch", "cachyos", "", "host"),
        ("arch", "arch", "", "host"),
        ("arch", "manjaro", "", "host"),
        ("bazzite", "bazzite", "44", "container"),
        ("bazzite", "bazzite", "", ""),
        ("steamos", "steamos", "3.7", ""),
        ("fedora", "fedora", "44", ""),
    ],
)
def test_platform(family, distro_id, version_id, platform):
    found, reason = directmesh.directmesh_platform(
        family=family, distro_id=distro_id, version_id=version_id
    )
    assert found == platform
    assert bool(reason) == (not platform)


def test_state_not_installed():
    state = directmesh.directmesh_state(family="arch", distro_id="cachyos")
    assert state["supported"] and not state["installed"]
    assert state["launch_option"] == "" and state["newer"] is None
    assert state["selected_tag"] == "directmesh-v1.4"


def test_state_installed_reports_launch_option_and_newer_release():
    _install_driver()
    _save_list(
        _release("directmesh-v1.6", prerelease=True),
        _release("directmesh-v1.5"),
        _release("directmesh-v1.4", digest=REVIEWED),
    )
    state = directmesh.directmesh_state(family="bazzite", distro_id="bazzite", version_id="44")
    assert state["installed"] and state["experimental"]
    assert state["installed_version"] == "1.4"
    assert state["launch_option"].startswith("VK_DRIVER_FILES=")
    assert str(directmesh.directmesh_icd()) in state["launch_option"]
    assert state["launch_option"].endswith(" %command%")
    assert state["newer"] == {"tag": "directmesh-v1.5", "version": "1.5", "prerelease": False, "reviewed": False}


def test_broken_manifest_is_not_installed():
    _install_driver()
    (directmesh.directmesh_prefix() / "lib" / "libvulkan_radeon.so").unlink()
    assert not directmesh.directmesh_state(family="arch", distro_id="arch")["installed"]


def _bash_syntax(command: str) -> None:
    subprocess.run(["bash", "-n"], input=command, text=True, check=True)


def test_install_command_verifies_the_installer_before_running_it():
    command = directmesh.build_directmesh_install_command(family="arch", distro_id="cachyos")
    _bash_syntax(command)
    assert "releases/download/directmesh-v1.4/install.sh" in command
    assert REVIEWED in command
    assert command.index("sha256sum") < command.index('bash "$bc250_installer"')
    assert "--global" not in command
    assert "DIRECTMESH_VERSION=directmesh-v1.4" in command
    assert "distrobox" not in command


def test_install_command_on_bazzite_runs_in_a_matching_container():
    command = directmesh.build_directmesh_install_command(
        family="bazzite", distro_id="bazzite", version_id="44"
    )
    _bash_syntax(command)
    assert "fedora-toolbox:44" in command
    assert "distrobox enter bc250-directmesh" in command
    assert "toolbox run --container bc250-directmesh" in command
    assert "ldd" in command


def test_install_command_refuses_unsupported_systems():
    with pytest.raises(RuntimeError):
        directmesh.build_directmesh_install_command(family="steamos", distro_id="steamos")


def test_check_and_uninstall_commands():
    with pytest.raises(RuntimeError):
        directmesh.build_directmesh_check_command()
    _install_driver()
    check = directmesh.build_directmesh_check_command()
    _bash_syntax(check)
    assert "meshShader" in check
    remove = directmesh.build_directmesh_uninstall_command(family="bazzite", distro_id="bazzite")
    _bash_syntax(remove)
    assert "--uninstall" in remove and "distrobox rm --force bc250-directmesh" in remove
    _bash_syntax(directmesh.build_directmesh_releases_command())


def test_background_release_check_includes_directmesh_once_set_up():
    names = [name for name, *_ in upscaler_releases._sources()]
    assert "directmesh" not in names
    directmesh.directmesh_root().mkdir(parents=True)
    names = [name for name, *_ in upscaler_releases._sources()]
    assert "directmesh" in names


def test_a_release_github_no_longer_lists_is_not_offered_or_installed():
    _save_list(_release("directmesh-v1.5"))
    assert [r["tag"] for r in directmesh.directmesh_releases()] == ["directmesh-v1.5"]
    assert directmesh.directmesh_release()["tag"] == "directmesh-v1.5"
    _save_list(_release("directmesh-v1.4.1", prerelease=True))  # only the withdrawn one is listed
    assert directmesh.directmesh_releases() == []
    with pytest.raises(RuntimeError, match="No DirectMesh release"):
        directmesh.build_directmesh_install_command(family="arch", distro_id="cachyos")


def test_install_paths_never_reach_shell_source_unquoted(data_home):
    command = directmesh.build_directmesh_install_command(family="arch", distro_id="cachyos")
    assert "bc250_icd=" in command
    assert 'ERROR: the installer finished but {' not in command
    assert '"$bc250_icd"' in command


def test_failed_update_restores_driver_runner_and_record(tmp_path, monkeypatch):
    import hashlib
    import os

    monkeypatch.setenv("HOME", str(tmp_path))
    _install_driver()
    prefix = directmesh.directmesh_prefix()
    driver = prefix / "lib/libvulkan_radeon.so"
    previous = (directmesh.directmesh_root() / "installed.json").read_bytes()
    runner = tmp_path / ".local/bin/directmesh-run"
    runner.parent.mkdir(parents=True)
    runner.write_text("old runner")
    installer = tmp_path / "installer"
    installer.write_text('rm -rf "$DIRECTMESH_PREFIX"; echo partial > "$HOME/.local/bin/directmesh-run"; exit 27')
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    monkeypatch.setattr(directmesh, "directmesh_release", lambda: {"tag": "directmesh-v1.5", "installer_sha256": digest})
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name, script in {"vulkaninfo": "exit 1", "curl": 'while [ "$1" != -o ]; do shift; done; cp "$INSTALLER" "$2"'}.items():
        executable = fake_bin / name
        executable.write_text("#!/bin/sh\n" + script)
        executable.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", directmesh.build_directmesh_install_command(family="arch", distro_id="arch")],
        env=os.environ | {"INSTALLER": str(installer), "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 27, result.stderr
    assert driver.read_bytes() == b"\x7fELF"
    assert runner.read_text() == "old runner"
    assert (directmesh.directmesh_root() / "installed.json").read_bytes() == previous


def test_matching_container_is_required_before_upstream_installer_runs(tmp_path, monkeypatch):
    import os

    commands = tmp_path / "container-commands"
    distrobox = tmp_path / "distrobox"
    distrobox.write_text("""#!/bin/sh
case "$1" in
    list) echo '123 | bc250-directmesh | running' ;;
    enter)
        shift 3
        case "$1" in
            sh) echo "43" ;;
            *) echo "$*" >> "$COMMANDS" ;;
        esac ;;
    *) exit 1 ;;
esac
""")
    distrobox.chmod(0o755)
    result = subprocess.run(["bash", "-ec", directmesh._container_lines("44", "")],
                            env=os.environ | {"PATH": f"{tmp_path}:{os.environ['PATH']}", "COMMANDS": str(commands)},
                            text=True, capture_output=True)
    assert result.returncode == 69
    assert "Fedora 43; Fedora 44 is required" in result.stdout
    assert not commands.exists()


# Upstream wraps each package list over two lines and runs it with eval, so the
# second line ran as a program ("libxshmfence-devel: command not found",
# "systemd-libs: command not found", R-006daa34 and R-a51b4e18).
WRAPPED_INSTALLER = '''PKG_ARCH="base-devel cmake python curl tar xz glslang libx11 libxcb libxshmfence xcb-util-keysyms wayland wayland-protocols
          systemd-libs expat zlib zstd libelf"
PKG_FED="gcc gcc-c++ cmake pkgconf-pkg-config python3 python3-pip curl tar xz glslang libX11-devel libxcb-devel
         libxshmfence-devel xcb-util-keysyms-devel wayland-devel wayland-protocols-devel systemd-devel expat-devel
         zlib-devel libzstd-devel elfutils-libelf-devel"
'''


def _packages(tmp_path, installer_text, variable):
    installer = tmp_path / "installer.sh"
    installer.write_text(installer_text, encoding="utf-8")
    snippet = directmesh._PACKAGE_LIST + f'\nbc250_installer={installer}\nbc250_packages {variable}\n'
    return subprocess.run(["bash", "-ec", snippet], capture_output=True, text=True)


@pytest.mark.parametrize("variable, first, second", [
    ("PKG_ARCH", "wayland-protocols", "systemd-libs"),
    ("PKG_FED", "libxcb-devel", "libxshmfence-devel"),
])
def test_the_package_list_is_read_whole_across_the_wrapped_line(tmp_path, variable, first, second):
    result = _packages(tmp_path, WRAPPED_INSTALLER, variable)
    assert result.returncode == 0, result.stderr
    assert "\n" not in result.stdout.strip()
    names = result.stdout.split()
    assert first in names and second in names
    assert names.index(second) == names.index(first) + 1


@pytest.mark.parametrize("text", [
    "",
    'PKG_ARCH=""\n',
    'PKG_ARCH="gcc $(touch /tmp/owned) make"\n',
    'PKG_ARCH="gcc; rm -rf ~ make"\n',
    'PKG_ARCH="-S --overwrite=* make"\n',
])
def test_an_unreadable_or_suspicious_package_list_is_not_used(tmp_path, text):
    result = _packages(tmp_path, text, "PKG_ARCH")
    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_install_commands_install_the_packages_before_upstream_runs():
    host = directmesh.build_directmesh_install_command(family="arch", distro_id="cachyos")
    _bash_syntax(host)
    assert "bc250_packages PKG_ARCH" in host and "sudo pacman -S --needed $bc250_absent" in host
    assert host.index("sudo pacman -S --needed") < host.index('bash "$bc250_installer"')
    container = directmesh.build_directmesh_install_command(
        family="bazzite", distro_id="bazzite", version_id="45"
    )
    _bash_syntax(container)
    assert "bc250_packages PKG_FED" in container and "sudo dnf install $bc250_absent" in container
    assert container.index("sudo dnf install") < container.rindex('bash "$bc250_installer"')


def test_missing_packages_are_installed_whole_before_the_installer_runs(tmp_path, monkeypatch):
    import hashlib
    import os

    monkeypatch.setenv("HOME", str(tmp_path))
    log = tmp_path / "order.log"
    installer = tmp_path / "installer"
    installer.write_text(WRAPPED_INSTALLER + 'echo "installer ran" >> "$ORDER"; exit 27\n')
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    monkeypatch.setattr(directmesh, "directmesh_release", lambda: {"tag": "directmesh-v1.5", "installer_sha256": digest})
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    scripts = {
        "vulkaninfo": "exit 1",
        "curl": 'while [ "$1" != -o ]; do shift; done; cp "$INSTALLER" "$2"',
        # pacman -T reports what is missing; sudo only records what it was asked to run.
        "pacman": 'echo "systemd-libs libxshmfence"',
        "sudo": 'echo "sudo $*" >> "$ORDER"',
    }
    for name, script in scripts.items():
        executable = fake_bin / name
        executable.write_text("#!/bin/sh\n" + script)
        executable.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", directmesh.build_directmesh_install_command(family="arch", distro_id="arch")],
        env=os.environ | {"INSTALLER": str(installer), "ORDER": str(log),
                          "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 27, result.stdout + result.stderr
    assert log.read_text().splitlines() == [
        "sudo pacman -S --needed systemd-libs libxshmfence",
        "installer ran",
    ]
