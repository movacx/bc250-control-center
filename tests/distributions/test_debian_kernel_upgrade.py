"""Debian 13 cannot drive the BC-250 GPU: backports (kernel and Mesa) is the way out."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bc250cc.infrastructure.debian_kernel_upgrade import (
    MESA_PACKAGES,
    build_debian_kernel_command,
    debian_kernel_upgrade_state,
    os_release_codename,
)

STOCK_MESA = "25.0.7-2+deb13u1"
BACKPORTS_MESA = "26.1.6-1~bpo13+1"
#: A stock Debian 13: the 6.12 kernel, and a Mesa that is already the backports one
#: so that each test below changes only the thing it is about.
DEBIAN_13 = {
    "family": "debian", "distro_id": "debian", "kernel": "6.12.111+deb13-amd64",
    "codename": "trixie", "mesa_version": BACKPORTS_MESA,
}
NEW_KERNEL = "7.1.13+bpo-amd64"


def _boot(tmp_path, *names):
    for name in names:
        (tmp_path / f"vmlinuz-{name}").write_text("")
    return tmp_path


def test_debian_13_on_the_stock_kernel_is_offered_the_backports_kernel(tmp_path):
    state = debian_kernel_upgrade_state(**DEBIAN_13, boot_dir=_boot(tmp_path, "6.12.111+deb13-amd64"))
    assert state["offered"] is True
    assert state["state"] == "available"
    assert state["codename"] == "trixie"
    assert state["install_kernel"] is True
    assert state["install_mesa"] is False


def test_an_installed_newer_kernel_waits_for_a_restart(tmp_path):
    boot = _boot(tmp_path, "6.12.111+deb13-amd64", "7.1.13+bpo-amd64")
    state = debian_kernel_upgrade_state(**DEBIAN_13, boot_dir=boot)
    assert state["offered"] is True
    assert state["state"] == "reboot-required"
    assert (state["install_kernel"], state["install_mesa"]) == (False, False)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"kernel": "7.1.13+bpo-amd64"}, "already new enough"),
        ({"kernel": "6.14.0-1-amd64"}, "already new enough"),
        ({"codename": "bookworm"}, "no backports kernel"),
        ({"codename": "bookworm", "kernel": NEW_KERNEL, "mesa_version": "22.3.6-1+deb12u1"}, "already new enough"),
        ({"distro_id": "ubuntu", "family": "debian"}, "Only Debian"),
        ({"distro_id": "linuxmint", "family": "debian"}, "Only Debian"),
        ({"family": "fedora", "distro_id": "fedora"}, "Only Debian"),
        ({"kernel": "6.12.0-bc250"}, "BC-250 kernel"),
        ({"kernel": ""}, "could not be read"),
    ],
)
def test_other_systems_are_not_offered_it(tmp_path, overrides, reason):
    state = debian_kernel_upgrade_state(**{**DEBIAN_13, **overrides}, boot_dir=tmp_path)
    assert state["offered"] is False
    assert state["state"] == "not-offered"
    assert reason in state["reason"]
    assert (state["install_kernel"], state["install_mesa"]) == (False, False)


def test_image_based_systems_are_not_offered_it(tmp_path):
    state = debian_kernel_upgrade_state(**DEBIAN_13, boot_dir=tmp_path, immutable=True)
    assert state["offered"] is False


def test_the_stock_mesa_is_offered_the_backports_one_on_a_new_kernel(tmp_path):
    """Mesa 25.0 does not know the GPU whatever the kernel is: checked on a real BC-250."""
    state = debian_kernel_upgrade_state(
        **{**DEBIAN_13, "kernel": NEW_KERNEL, "mesa_version": STOCK_MESA}, boot_dir=tmp_path
    )
    assert state["offered"] is True
    assert state["state"] == "available"
    assert (state["install_kernel"], state["install_mesa"]) == (False, True)


def test_the_stock_kernel_and_the_stock_mesa_are_both_to_install(tmp_path):
    state = debian_kernel_upgrade_state(**{**DEBIAN_13, "mesa_version": STOCK_MESA}, boot_dir=tmp_path)
    assert (state["install_kernel"], state["install_mesa"]) == (True, True)


def test_a_waiting_kernel_does_not_hide_a_missing_mesa(tmp_path):
    boot = _boot(tmp_path, "6.12.111+deb13-amd64", "7.1.13+bpo-amd64")
    state = debian_kernel_upgrade_state(**{**DEBIAN_13, "mesa_version": STOCK_MESA}, boot_dir=boot)
    assert state["state"] == "available"
    assert (state["install_kernel"], state["install_mesa"]) == (False, True)


@pytest.mark.parametrize(
    ("mesa", "needed"),
    [
        (STOCK_MESA, True), ("25.3.1-1", True), ("26.0.8-1ubuntu0.3", True),
        ("26.1.0-1~bpo13+1", False), (BACKPORTS_MESA, False), ("", False),
    ],
)
def test_mesa_older_than_26_1_is_the_one_replaced(tmp_path, mesa, needed):
    state = debian_kernel_upgrade_state(
        **{**DEBIAN_13, "kernel": NEW_KERNEL, "mesa_version": mesa}, boot_dir=tmp_path
    )
    assert state["install_mesa"] is needed
    assert state["offered"] is needed


def test_codename_is_read_from_os_release():
    assert os_release_codename('ID=debian\nVERSION_CODENAME=trixie\n') == "trixie"
    assert os_release_codename('VERSION_CODENAME="Trixie"\n') == "trixie"
    assert os_release_codename("ID=debian\n") == ""


def test_the_command_adds_backports_and_installs_from_it(tmp_path):
    source = tmp_path / "bc250.sources"
    command = build_debian_kernel_command("install", "trixie", source=source)
    assert "Suites: trixie-backports" in command
    assert "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" in command
    assert 'packages="linux-image-amd64 linux-headers-amd64 firmware-amd-graphics"' in command
    assert f'mesa="{" ".join(MESA_PACKAGES)}"' in command
    # An older backports kernel must stop the run before anything is installed.
    assert command.index("dpkg --compare-versions") < command.index("apt-get install -y")
    # Nothing is removed and no kernel is purged.
    assert "remove" not in command and "purge" not in command


def test_the_kernel_part_and_the_mesa_part_can_each_be_left_out():
    only_kernel = build_debian_kernel_command("install", "trixie", mesa=False)
    only_mesa = build_debian_kernel_command("install", "trixie", kernel=False)
    assert "linux-image-amd64" in only_kernel and "mesa-vulkan-drivers" not in only_kernel
    assert "linux-image-amd64" not in only_mesa and "mesa-vulkan-drivers" in only_mesa
    assert 'packages=""' in only_mesa


def test_nothing_to_install_is_refused():
    with pytest.raises(ValueError):
        build_debian_kernel_command("install", "trixie", kernel=False, mesa=False)


@pytest.mark.parametrize("flags", [{}, {"mesa": False}, {"kernel": False}])
def test_the_command_is_valid_shell(flags):
    command = build_debian_kernel_command("install", "trixie", **flags)
    result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


#: ``dpkg --compare-versions`` for hosts that have no dpkg (Arch, Fedora, Manjaro):
#: the Debian version ordering (epoch, upstream, revision; ``~`` sorts before
#: everything) is the one thing the workflow asks of it.
DPKG_STUB = r'''#!PYTHON
import re
import sys


def order(ch):
    if ch.isdigit():
        return 0
    if ch.isalpha():
        return ord(ch)
    return -1 if ch == "~" else ord(ch) + 256


def compare_part(a, b):
    while a or b:
        while (a and not a[0].isdigit()) or (b and not b[0].isdigit()):
            oa = order(a[0]) if a else 0
            ob = order(b[0]) if b else 0
            if oa != ob:
                return -1 if oa < ob else 1
            a = a[1:] if a and not a[0].isdigit() else a
            b = b[1:] if b and not b[0].isdigit() else b
        na, nb = re.match(r"\d*", a).group(), re.match(r"\d*", b).group()
        a, b = a[len(na):], b[len(nb):]
        if int(na or 0) != int(nb or 0):
            return -1 if int(na or 0) < int(nb or 0) else 1
    return 0


def split(version):
    epoch, rest = version.split(":", 1) if ":" in version else ("0", version)
    upstream, revision = rest.rsplit("-", 1) if "-" in rest else (rest, "")
    return int(epoch), upstream, revision


def compare(x, y):
    (ex, ux, rx), (ey, uy, ry) = split(x), split(y)
    if ex != ey:
        return -1 if ex < ey else 1
    return compare_part(ux, uy) or compare_part(rx, ry)


_, flag, left, op, right = sys.argv
assert flag == "--compare-versions"
c = compare(left, right)
sys.exit(0 if {"lt": c < 0, "le": c <= 0, "eq": c == 0, "ne": c != 0, "ge": c >= 0, "gt": c > 0}[op] else 1)
'''.replace("PYTHON", sys.executable)

#: Pairs whose order is fixed by the Debian policy manual.
VERSION_ORDER = [
    ("7.1.13-1~bpo13+1", "6.14", "gt"),
    ("6.12.57-1~bpo12+1", "6.14", "lt"),
    ("6.14", "6.14", "eq"),
    ("6.14.0-1", "6.14", "gt"),
    ("26.1.6-1~bpo13+1", "26.1", "gt"),
    ("26.0.8-1", "26.1", "lt"),
    ("25.0.7-2+deb13u1", "26.1", "lt"),
    ("1.0~rc1", "1.0", "lt"),
    ("1.0~~", "1.0~", "lt"),
    ("1.0-1", "1.0-2", "lt"),
    ("1.0a", "1.0", "gt"),
    ("1.9", "1.10", "lt"),
    ("1:1.0", "2.0", "gt"),
    ("1.0+b1", "1.0", "gt"),
]


def _dpkg_stub(tmp_path):
    path = tmp_path / "dpkg-stub"
    path.write_text(DPKG_STUB)
    path.chmod(0o755)
    return path


def _stub_compare(stub, left, op, right):
    return subprocess.run([str(stub), "--compare-versions", left, op, right]).returncode == 0


@pytest.mark.parametrize(("left", "right", "op"), VERSION_ORDER)
def test_the_stand_in_for_dpkg_orders_versions_like_debian(tmp_path, left, right, op):
    stub = _dpkg_stub(tmp_path)
    assert _stub_compare(stub, left, op, right)
    opposite = {"gt": "le", "lt": "ge", "eq": "ne"}[op]
    assert not _stub_compare(stub, left, opposite, right)


@pytest.mark.skipif(shutil.which("dpkg") is None, reason="needs the real dpkg of a Debian host")
@pytest.mark.parametrize(("left", "right", "op"), VERSION_ORDER)
def test_the_stand_in_for_dpkg_agrees_with_the_real_one(tmp_path, left, right, op):
    stub = _dpkg_stub(tmp_path)
    for operator in ("lt", "le", "eq", "ne", "ge", "gt"):
        real = subprocess.run(["dpkg", "--compare-versions", left, operator, right]).returncode == 0
        assert _stub_compare(stub, left, operator, right) is real, (left, operator, right)


def _run_workflow(
    tmp_path, *, candidate=BACKPORTS_MESA, meta_installable=True, complete=(),
    mesa_candidate=BACKPORTS_MESA, mesa_installable=True, kernel=True, mesa=False,
):
    """Run the real script with a stubbed sudo, apt-get, apt-cache, dpkg and keyring.

    ``complete`` lists the concrete kernel versions a simulated install accepts.
    ``candidate`` is the kernel meta package backports offers, ``mesa_candidate`` Mesa's.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    stubs = {
        "sudo": 'echo "sudo $*" >> "$LOG"; if [ "${1:-}" = -v ]; then exit 0; fi; exec "$@"',
        "apt-get": (
            'if [ "$1" = install ] && [ "$2" = -s ]; then\n'
            '  case "$*" in *mesa-vulkan-drivers*) [ "$MESA_OK" = 1 ]; exit $?;; esac\n'
            '  case "$*" in *linux-image-amd64*) [ "$META" = 1 ]; exit $?;; esac\n'
            '  for v in $COMPLETE; do case "$*" in *"linux-image-$v+deb13-amd64"*) exit 0;; esac; done\n'
            "  exit 100\n"
            "fi\n"
            'echo "apt-get $*" >> "$LOG"'
        ),
        "apt-cache": (
            'case "$1" in\n'
            '  madison) case "$2" in\n'
            '    linux-image-amd64) echo "linux-image-amd64 | $CANDIDATE | http://deb.debian.org/debian trixie-backports/main amd64 Packages";;\n'
            '    libgl1-mesa-dri) [ -z "$MESA_CANDIDATE" ] || echo "libgl1-mesa-dri | $MESA_CANDIDATE | http://deb.debian.org/debian trixie-backports/main amd64 Packages";;\n'
            "  esac;;\n"
            '  pkgnames) for v in 7.1.13 7.1.8 6.12.111 6.19.14; do echo "linux-image-$v+deb13-amd64"; done;'
            ' echo linux-image-7.1.8+deb13-amd64-unsigned; echo linux-image-7.1.8+deb13-rt-amd64;;\n'
            "esac"
        ),
    }
    for name, body in stubs.items():
        (bin_dir / name).write_text(f"#!/bin/bash\n{body}\n")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "dpkg").write_text(DPKG_STUB)
    (bin_dir / "dpkg").chmod(0o755)
    command = build_debian_kernel_command(
        "install", "trixie", source=tmp_path / "bc250.sources", kernel=kernel, mesa=mesa
    )
    # The keyring is a real system file; drop that one guard for the dry run.
    command = command.replace("test -r /usr/share/keyrings/debian-archive-keyring.gpg || ", "true || ")
    # ...and the search for an existing backports source must not see this machine's.
    command = command.replace("/etc/apt/sources.list /etc/apt/sources.list.d", str(tmp_path / "apt"))
    script = tmp_path / "run.sh"
    script.write_text(command)
    log.write_text("")
    result = subprocess.run(
        ["bash", str(script)],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin", "LOG": str(log), "CANDIDATE": candidate,
            "META": "1" if meta_installable else "0", "COMPLETE": " ".join(complete),
            "MESA_CANDIDATE": mesa_candidate, "MESA_OK": "1" if mesa_installable else "0",
        },
        capture_output=True, text=True,
    )
    return result, log.read_text()


def test_the_command_stops_when_the_backports_kernel_is_too_old(tmp_path):
    result, calls = _run_workflow(tmp_path, candidate="6.12.57-1~bpo12+1")
    assert result.returncode == 29
    assert "is older than 6.14" in result.stdout
    assert "apt-get install" not in calls


def test_the_command_installs_the_meta_package_when_it_is_complete(tmp_path):
    result, calls = _run_workflow(tmp_path, candidate="7.1.13-1~bpo13+1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "apt-get install -y -t trixie-backports linux-image-amd64 linux-headers-amd64 firmware-amd-graphics" in calls
    written = (tmp_path / "bc250.sources").read_text()
    assert "Suites: trixie-backports" in written
    assert "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" in written


def test_the_command_falls_back_to_the_newest_complete_kernel(tmp_path):
    """The mirror published the meta package before its dependencies (seen in real use)."""
    result, calls = _run_workflow(
        tmp_path, candidate="7.1.13-1~bpo13+1", meta_installable=False, complete=("7.1.8", "6.19.14")
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install")]
    assert installs == [
        "apt-get install -y -t trixie-backports "
        "linux-image-7.1.8+deb13-amd64 linux-headers-7.1.8+deb13-amd64 firmware-amd-graphics"
    ]


def test_the_fallback_never_picks_a_kernel_older_than_the_minimum(tmp_path):
    result, calls = _run_workflow(
        tmp_path, candidate="7.1.13-1~bpo13+1", meta_installable=False, complete=("6.12.111",)
    )
    assert result.returncode == 29
    assert "apt-get install" not in calls
    assert "Try again later" in result.stdout


def test_the_command_stops_when_no_kernel_is_complete(tmp_path):
    result, calls = _run_workflow(tmp_path, candidate="7.1.13-1~bpo13+1", meta_installable=False)
    assert result.returncode == 29
    assert "apt-get install" not in calls


MESA = " ".join(MESA_PACKAGES)


def test_the_kernel_and_mesa_go_in_one_installation(tmp_path):
    result, calls = _run_workflow(tmp_path, mesa=True)
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install")]
    assert installs == [
        "apt-get install -y -t trixie-backports "
        f"linux-image-amd64 linux-headers-amd64 firmware-amd-graphics {MESA}"
    ]


def test_mesa_alone_installs_no_kernel(tmp_path):
    result, calls = _run_workflow(tmp_path, kernel=False, mesa=True)
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install")]
    assert installs == [f"apt-get install -y -t trixie-backports {MESA}"]


def test_mesa_follows_the_fallback_kernel(tmp_path):
    result, calls = _run_workflow(
        tmp_path, meta_installable=False, complete=("7.1.8",), mesa=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install")]
    assert installs == [
        "apt-get install -y -t trixie-backports "
        f"linux-image-7.1.8+deb13-amd64 linux-headers-7.1.8+deb13-amd64 firmware-amd-graphics {MESA}"
    ]


def test_a_mesa_that_is_not_ready_does_not_stop_the_kernel(tmp_path):
    result, calls = _run_workflow(tmp_path, mesa=True, mesa_installable=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[WARN] Mesa" in result.stdout
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install")]
    assert installs == ["apt-get install -y -t trixie-backports linux-image-amd64 linux-headers-amd64 firmware-amd-graphics"]


@pytest.mark.parametrize(
    "overrides",
    [{"mesa_installable": False}, {"mesa_candidate": ""}, {"mesa_candidate": "25.0.7-2~bpo13+1"}],
)
def test_mesa_alone_stops_when_it_cannot_be_had(tmp_path, overrides):
    result, calls = _run_workflow(tmp_path, kernel=False, mesa=True, **overrides)
    assert result.returncode == 29
    assert "Try again later" in result.stdout
    assert "apt-get install" not in calls


@pytest.mark.parametrize("action", ["", "remove", "../x"])
def test_unknown_actions_are_refused(action):
    with pytest.raises(ValueError):
        build_debian_kernel_command(action, "trixie")


def test_an_unsupported_release_is_refused():
    with pytest.raises(ValueError):
        build_debian_kernel_command("install", "bookworm")


def test_the_source_path_is_quoted():
    command = build_debian_kernel_command("install", "trixie", source=Path("/tmp/a b.sources"))
    assert "'/tmp/a b.sources'" in command


def _debian_repository(monkeypatch, tmp_path, *, kernel, mesa, boot=()):
    """A Debian 13 repository whose terminal records the workflow it is asked to open."""
    from bc250cc.infrastructure import debian_kernel_upgrade as module
    from bc250cc.infrastructure import dependencias_repository as repository_module
    from tests.infrastructure.test_upstream_preparation_routes import _repository_for

    monkeypatch.setattr(module, "os_release_codename", lambda *_: "trixie")
    monkeypatch.setattr(module, "installed_mesa_version", lambda: mesa)
    monkeypatch.setattr(module, "BOOT_DIR", _boot(tmp_path, *boot))
    monkeypatch.setattr(repository_module.platform, "release", lambda: kernel)
    calls: list[tuple[str, str]] = []
    return _repository_for("debian", calls, distro_id="debian"), calls


@pytest.mark.parametrize(
    ("kernel", "mesa", "boot", "wants_kernel", "wants_mesa"),
    [
        ("6.12.111+deb13-amd64", STOCK_MESA, (), True, True),
        ("6.12.111+deb13-amd64", BACKPORTS_MESA, (), True, False),
        (NEW_KERNEL, STOCK_MESA, (), False, True),
        ("6.12.111+deb13-amd64", STOCK_MESA, ("7.1.13+bpo-amd64",), False, True),
    ],
)
def test_the_terminal_gets_only_what_is_still_missing(
    monkeypatch, tmp_path, kernel, mesa, boot, wants_kernel, wants_mesa
):
    repository, calls = _debian_repository(monkeypatch, tmp_path, kernel=kernel, mesa=mesa, boot=boot)
    assert repository.gestionar_kernel_debian("install") == "terminal"
    command, title = calls[0]
    assert ("linux-image-amd64" in command) is wants_kernel
    assert ("mesa-vulkan-drivers" in command) is wants_mesa
    assert "Mesa" in title


def test_nothing_is_run_when_only_a_restart_is_missing(monkeypatch, tmp_path):
    repository, calls = _debian_repository(
        monkeypatch, tmp_path, kernel="6.12.111+deb13-amd64", mesa=BACKPORTS_MESA,
        boot=("7.1.13+bpo-amd64",),
    )
    with pytest.raises(ValueError):
        repository.gestionar_kernel_debian("install")
    assert calls == []
