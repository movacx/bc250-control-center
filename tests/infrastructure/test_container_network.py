"""Rootless containers cannot start while the governor's gpu_metrics overlay is mounted over /sys."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import container_network, vaapi_video
from bc250cc.infrastructure.accessories import hdmi_cec
from bc250cc.infrastructure.apu_telemetry_service import _container_build


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


def test_the_cyan_installer_no_longer_builds_in_a_container():
    """Bazzite gets upstream's release binary since 1.21.2: no podman build."""
    script = Path("packaging/common/os-scripts/common/install-cyan-upstream-release.sh").read_text()
    assert "podman" not in script


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


# --- R-32e499fb: rootless Podman without subordinate IDs -----------------------

PODMAN_SUBID_LOG = (
    "Copying blob 09fd9ebf9e18 done   |\n"
    'Error: unable to copy from source docker://registry.fedoraproject.org/fedora:44: copying system image '
    'from manifest list: writing blob: adding layer with blob "sha256:09fd9ebf9e1815ef0a844b9164af48617a6feb66570e0bf8338a7eebc474f0f8"'
    '/""/"sha256:0d0e313cf6e6ca5713bd2e59cdb00ec8972efc043311ae69a46d4640740aa5e0": unpacking failed '
    "(error: exit status 1; output: potentially insufficient UIDs or GIDs available in user namespace "
    '(requested 0:12 for /var/spool/mail): Check /etc/subuid and /etc/subgid if configured locally and run '
    '"podman system migrate": lchown /var/spool/mail: invalid argument)'
)


def _subids(tmp_path, *, uid_map, gid_map=None, listed=False, podman="podman", unshare_fails=False):
    """Run the subordinate-ID check with a stand-in ``podman``, ``id`` and subid files."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "podman").write_text(
        "#!/bin/bash\n"
        '[ "$UNSHARE_FAILS" = 1 ] && exit 125\n'
        'case "$3" in */uid_map) printf "%b" "$UID_MAP";; */gid_map) printf "%b" "$GID_MAP";; esac\n'
    )
    (bin_dir / "id").write_text('#!/bin/bash\n[ "$1" = -un ] && echo ana || echo 1000\n')
    for tool in ("podman", "id"):
        (bin_dir / tool).chmod(0o755)
    etc = tmp_path / "etc"
    etc.mkdir(exist_ok=True)
    for name in ("subuid", "subgid"):
        (etc / name).write_text(("ana:100000:65536\n" if listed else "") + "otro:165536:65536\n")
    function = container_network.SUBID_FUNCTION.replace("/etc/subuid", str(etc / "subuid")).replace(
        "/etc/subgid", str(etc / "subgid"))
    result = subprocess.run(
        ["/bin/bash", "-c", function + f'\nbc250_podman_subids "{podman}"; echo "status=$?"'],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "UID_MAP": uid_map,
             "GID_MAP": gid_map if gid_map is not None else uid_map,
             "UNSHARE_FAILS": "1" if unshare_fails else "0"},
        capture_output=True, text=True,
    )
    return result.stdout


def test_a_user_with_a_full_range_passes(tmp_path):
    out = _subids(tmp_path, uid_map=r"         0       1000          1\n         1     100000      65536\n")
    assert out.strip() == "status=0"


def test_a_user_with_no_range_gets_the_commands_that_add_one(tmp_path):
    out = _subids(tmp_path, uid_map=r"         0       1000          1\n")
    assert "status=1" in out
    assert "has no subordinate user and group IDs for ana" in out
    # A free range after every existing one, so no other user's IDs are reused.
    assert "sudo usermod --add-subuids 231072-296607 --add-subgids 231072-296607 ana" in out
    assert "podman system migrate" in out


def test_a_range_podman_has_not_picked_up_needs_only_the_migration(tmp_path):
    out = _subids(tmp_path, uid_map=r"0 1000 1\n1 100000 65536\n", gid_map=r"0 1000 1\n", listed=True)
    assert "status=1" in out
    assert "podman system migrate" in out and "usermod" not in out


@pytest.mark.parametrize("kwargs", [
    {"podman": "sudo podman"},     # rootful Podman maps every ID itself
    {"unshare_fails": True},       # Podman cannot even start: it reports that itself
])
def test_the_check_stays_out_of_the_way_when_it_does_not_apply(tmp_path, kwargs):
    assert _subids(tmp_path, uid_map=r"0 1000 1\n", **kwargs).strip() == "status=0"


def test_a_small_range_is_left_to_podman(tmp_path):
    """It may be enough for the image; if not, Podman's own error is diagnosed."""
    assert _subids(tmp_path, uid_map=r"0 1000 1\n1 100000 1000\n").strip() == "status=0"


def test_every_container_build_checks_before_it_downloads_an_image():
    for command in (
        vaapi_video.build_vaapi_command("install", family="arch"),
        "\n".join(hdmi_cec._container_lines("arch")),
        "\n".join(_container_build("'/src'")[0]),
    ):
        assert "bc250_podman_subids()" in command
        assert "|| exit 1;" in command


def test_the_report_log_and_the_early_stop_name_the_container_code(tmp_path):
    from bc250cc.infrastructure.terminal_plan import workflow_wrapper
    from bc250cc.shared import error_catalog
    from frontends.desktop.core.error_diagnostics import diagnose_error

    early = ("ERROR: Rootless Podman has no subordinate user and group IDs for ana, so it cannot unpack "
             "container images (insufficient UIDs or GIDs available in user namespace).")
    for text in (PODMAN_SUBID_LOG, early):
        assert error_catalog.for_marker(text).code == "BC250-CONTAINER-001"
        assert diagnose_error(text, context="Hardware video · build and install").code == "BC250-CONTAINER-001"
        wrapped = workflow_wrapper(f"printf '%s\\n' {shlex.quote(text)}; exit 125",
                                   tmp_path / "status", tmp_path / "log", hold=False)
        shown = subprocess.run(["bash", "-c", wrapped], input="", text=True, capture_output=True,
                               timeout=30, check=False).stdout
        assert "Diagnostic code: BC250-CONTAINER-001" in shown, shown[-600:]
