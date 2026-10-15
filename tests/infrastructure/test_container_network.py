"""Rootless containers cannot start while the governor's gpu_metrics overlay is mounted over /sys."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import container_network, vaapi_video
from bc250cc.infrastructure.accessories import hdmi_cec
from bc250cc.infrastructure.apu_telemetry_service import _container_build
from bc250cc.infrastructure.bc250_fsr4 import build_fsr4_v3_bazzite_install_command


def _network(tmp_path, *, podman="podman", mount_fails=False, userns_works=True, with_unshare=True):
    """Run the shell function with a stand-in ``unshare`` and return what it prints."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if with_unshare:
        (bin_dir / "unshare").write_text(
            "#!/bin/bash\n"
            'case "$*" in\n'
            '  *"mount -t sysfs"*) [ "$MOUNT_FAILS" = 1 ] && exit 1; exit 0;;\n'
            '  *) [ "$USERNS" = 1 ]; exit $?;;\n'
            "esac\n"
        )
        (bin_dir / "unshare").chmod(0o755)
    script = tmp_path / "run.sh"
    script.write_text(container_network.FUNCTION + f'\nbc250_container_network "{podman}"\n')
    result = subprocess.run(
        ["/bin/bash", str(script)],
        env={
            "PATH": f"{bin_dir}:/usr/bin" if with_unshare else str(bin_dir) + ":/nonexistent",
            "MOUNT_FAILS": "1" if mount_fails else "0", "USERNS": "1" if userns_works else "0",
        },
        capture_output=True, text=True,
    )
    return result


def test_the_host_network_is_chosen_only_when_the_kernel_refuses_a_new_sysfs(tmp_path):
    refused = _network(tmp_path, mount_fails=True)
    assert refused.stdout.strip() == "--network=host"
    assert "mounted over /sys" in refused.stderr
    assert _network(tmp_path).stdout.strip() == ""


@pytest.mark.parametrize("kwargs", [
    {"podman": "sudo podman", "mount_fails": True},   # rootful Podman is not subject to the check
    {"mount_fails": True, "userns_works": False},     # no user namespaces: Podman says so itself
])
def test_no_option_is_added_when_the_check_does_not_apply(tmp_path, kwargs):
    assert _network(tmp_path, **kwargs).stdout.strip() == ""


def test_the_function_is_valid_shell():
    assert subprocess.run(["bash", "-n"], input=container_network.FUNCTION, text=True).returncode == 0


def _before(command: str, definition: str, use: str) -> None:
    assert definition in command, "the function is defined"
    assert use in command, "the option is used"
    assert command.index(definition) < command.index(use), "and defined before it is used"


@pytest.mark.parametrize("family", ["arch", "bazzite", "steamos"])
def test_the_video_driver_builds_use_it(family):
    for action in ("install", "install32"):
        if action == "install32" and family == "bazzite":
            continue
        command = vaapi_video.build_vaapi_command(action, family=family)
        _before(command, "bc250_container_network()", '$bc250_podman run --rm $bc250_net --pull=missing')


def test_the_cec_build_uses_it():
    command = "\n".join(hdmi_cec._container_lines("arch"))
    assert "bc250_container_network()" in command
    assert "$bc250_podman run --rm $bc250_net --pull=missing" in command


def test_the_telemetry_build_stays_isolated_unless_the_overlay_leaves_no_other_way():
    preflight, build = _container_build("'/src'")
    assert any("bc250_container_network()" in line for line in preflight)
    assert "${bc250_net:---network=none}" in build[0]


def test_the_fsr4_build_uses_it_for_the_image_and_both_runs(tmp_path, monkeypatch):
    from bc250cc.infrastructure import bc250_fsr4

    monkeypatch.setattr(bc250_fsr4, "clone_or_update_commit", lambda *_args: "git -C x checkout")
    command = build_fsr4_v3_bazzite_install_command(tmp_path / "fsr4")
    assert command.count("$bc250_net") >= 4
    assert "podman build --tag" not in command and "podman run --rm \\\n" not in command


def test_every_bash_flow_that_runs_podman_asks_the_kernel_first():
    script = Path("packaging/common/os-scripts/common/install-cyan-upstream-release.sh").read_text()
    assert script.index("unshare -Urmn mount -t sysfs") < script.index("podman run --rm $container_network")


def test_the_oberon_build_on_bazzite_uses_it_and_is_valid_shell(tmp_path):
    from types import SimpleNamespace

    from bc250cc.infrastructure.governor_install_shell import oberon_install_command

    command = oberon_install_command(
        SimpleNamespace(info=SimpleNamespace(family="bazzite", label="Bazzite")),
        destination=tmp_path / "oberon",
        checkout_command="true",
        yaml_cpp_revision="0" * 40,
    )
    _before(command, "bc250_container_network()", "podman run --rm $bc250_net -v ")
    assert subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True).returncode == 0
