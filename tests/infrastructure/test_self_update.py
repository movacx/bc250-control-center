"""Updating from the latest release: the right package, proven, installed once.

The updater downloads a file that ends up installed as root, so what it may
download and run is narrow: https only, a SHA-256 GitHub published, the
package for this installation's own channel, and one command built here.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.install_source import InstallSource, UpdateChannel
from bc250cc.infrastructure.self_update import (
    ReleaseAsset,
    ReleaseInfo,
    UpdateError,
    UpdatePlan,
    clean_release_notes,
    discard_update,
    download_asset,
    install_command,
    parse_release,
    plan_update,
    prune_updates,
)

BODY = """## Highlights

- New dashboard.
- Faster sensors.

## Packages

- **Arch / CachyOS / Manjaro:** `.pkg.tar.zst`
- **Ubuntu / Debian:** `.deb`

## BC250 Quick Access

<img width="1890" height="1019" alt="decky" src="https://github.com/user-attachments/assets/x" />

## NOTE

Read this.
"""


def _payload(**overrides):
    payload = {
        "tag_name": "v1.20.0",
        "name": "BC250 Control Center 1.20.0",
        "published_at": "2026-09-25T10:00:00Z",
        "html_url": "https://github.com/movacx/bc250-control-center/releases/tag/v1.20.0",
        "body": BODY,
        "assets": [
            {"name": "bc250-control-center-1.20.0-1-any.pkg.tar.zst", "size": 10,
             "browser_download_url": "https://github.com/x/a.pkg.tar.zst", "digest": "sha256:" + "a" * 64},
            {"name": "bc250-control-center-1.20.0-1.fc44.noarch.rpm", "size": 10,
             "browser_download_url": "https://github.com/x/a.rpm", "digest": "sha256:" + "b" * 64},
            {"name": "bc250-control-center_1.20.0-1_all.deb", "size": 10,
             "browser_download_url": "https://github.com/x/a.deb", "digest": "sha256:" + "c" * 64},
            {"name": "bc250-control-center-1.20.0.tar.gz", "size": 10,
             "browser_download_url": "https://github.com/x/a.tar.gz", "digest": "sha256:" + "d" * 64},
            {"name": "evil.deb", "size": 10, "browser_download_url": "http://insecure/a.deb"},
        ],
    }
    payload.update(overrides)
    return payload


def test_release_notes_keep_the_text_and_drop_packages_and_pictures():
    notes = clean_release_notes(BODY)
    assert "## Highlights" in notes and "- Faster sensors." in notes
    assert "## NOTE" in notes and "Read this." in notes
    assert "Packages" not in notes and ".pkg.tar.zst" not in notes
    assert "<img" not in notes


def test_release_notes_drop_html_and_the_screenshot_carousel():
    """1.20.3 pasted the README's carousel; the dialog printed its raw table."""
    body = """## Fixes in 1.20.3

- **SteamOS**: fixed the `BC250-RANGE-001` error.
- Kernel &amp; Mesa &lt;7.2&gt; <b>matched</b>.

## Screenshots

<table>
  <tr>
    <td width="7%" align="center"><a href="https://x/#prev" aria-label="Previous"><kbd>&#10094;</kbd></a></td>
  </tr>
</table>

## Notes

<!-- internal -->
Flashing a BIOS is at your own risk.
"""
    notes = clean_release_notes(body)
    assert re.search(r"</?[A-Za-z]", notes) is None, "no markup is left"
    assert "&#" not in notes and "&amp;" not in notes
    assert "Screenshots" not in notes and "Previous" not in notes
    # Escaped text is text: it comes back as the characters it stood for.
    assert "Kernel & Mesa <7.2> matched." in notes
    assert "## Notes" in notes and "Flashing a BIOS is at your own risk." in notes
    assert "internal" not in notes


def test_a_release_is_read_with_its_checksums_and_only_https_assets():
    release = parse_release(_payload())
    assert release.version == "1.20.0" and release.tag == "v1.20.0"
    assert len(release.assets) == 4
    assert all(asset.url.startswith("https://") for asset in release.assets)
    assert release.assets[0].sha256 == "a" * 64


def test_a_release_without_a_tag_is_refused():
    with pytest.raises(UpdateError):
        parse_release({"name": "x"})


def _root(tmp_path) -> Path:
    root = tmp_path / "install"
    root.mkdir()
    return root


@pytest.mark.parametrize(
    ("manager", "atomic", "suffix", "installer"),
    [
        ("pacman", False, ".pkg.tar.zst", "pacman"),
        ("rpm", False, ".rpm", "dnf"),
        ("rpm", True, ".rpm", "rpm-ostree"),
        ("dpkg", False, ".deb", "apt"),
    ],
)
def test_each_package_channel_gets_its_own_package(tmp_path, manager, atomic, suffix, installer):
    release = parse_release(_payload())
    source = InstallSource(UpdateChannel.PACKAGE, package="bc250-control-center", manager=manager)
    plan = plan_update(release, source, atomic=atomic, project_root=_root(tmp_path))
    assert plan.kind == "package"
    assert plan.asset.name.endswith(suffix)
    assert plan.manager == installer
    assert plan.reboot_required is (installer == "rpm-ostree")


def test_an_aur_install_is_rebuilt_by_its_helper(tmp_path):
    release = parse_release(_payload())
    source = InstallSource(UpdateChannel.AUR, package="bc250-control-center-git", manager="pacman", helper="paru")
    plan = plan_update(release, source, project_root=_root(tmp_path))
    assert plan.kind == "aur" and not plan.downloads
    assert install_command(plan) == "paru -S --noconfirm --skipreview bc250-control-center-git"


def test_a_script_install_uses_the_source_archive(tmp_path):
    release = parse_release(_payload())
    plan = plan_update(release, InstallSource(UpdateChannel.RELEASE), project_root=_root(tmp_path))
    assert plan.kind == "source" and plan.asset.name.endswith(".tar.gz")
    command = install_command(plan, tmp_path / "bc250-control-center-1.20.0.tar.gz")
    assert "sha256sum -c -" in command and "scripts/install-local.sh" in command


@pytest.mark.parametrize(
    "case",
    ["git-checkout", "no-checksum", "no-package", "aur-without-helper"],
)
def test_what_cannot_be_done_safely_goes_to_the_release_page(tmp_path, case):
    root = _root(tmp_path)
    payload = _payload()
    source = InstallSource(UpdateChannel.PACKAGE, package="bc250-control-center", manager="pacman")
    family = ""
    if case == "git-checkout":
        (root / ".git").mkdir()
    elif case == "no-checksum":
        for asset in payload["assets"]:
            asset.pop("digest", None)
    elif case == "no-package":
        payload["assets"] = []
    elif case == "aur-without-helper":
        source = InstallSource(UpdateChannel.AUR, package="bc250-control-center-git", manager="pacman")
    plan = plan_update(parse_release(payload), source, os_family=family, project_root=root)
    assert plan.kind == "manual" and plan.reason


def test_the_install_command_checks_the_file_again_and_quotes_it(tmp_path):
    asset = ReleaseAsset("bc250-control-center-1.20.0-1-any.pkg.tar.zst", 10, "https://x", "a" * 64)
    plan = UpdatePlan("package", asset=asset, manager="pacman")
    path = tmp_path / "odd name; rm -rf ~" / asset.name
    command = install_command(plan, path)
    last = command.splitlines()[-1]
    verify, _sep, install = last.partition(" && ")
    assert verify.endswith("| sha256sum -c -") and "a" * 64 in verify
    assert install.startswith("bc250_admin pacman -U --noconfirm -- ")
    assert "'" + str(path) + "'" in command
    assert "BC250_GRAPHICAL_AUTH=0" in command


@pytest.mark.parametrize(("manager", "program"), [("pacman", "pacman"), ("dnf", "dnf"), ("apt", "apt")])
def test_a_desktop_asks_in_a_window_and_the_terminal_stays_the_fallback(tmp_path, manager, program):
    """A password typed into the terminal was the only route, and nobody on a sofa typed it."""
    asset = ReleaseAsset("bc250-control-center-pkg", 10, "https://x", "a" * 64)
    plan = UpdatePlan("package", asset=asset, manager=manager)
    command = install_command(plan, tmp_path / asset.name, graphical=True)
    assert "BC250_GRAPHICAL_AUTH=1" in command
    assert 'pkexec "$@"' in command and 'sudo "$@"' in command
    assert f"bc250_admin {program} " in command


def test_a_dismissed_authorization_never_tries_a_second_password_prompt(tmp_path):
    data = b"test package"
    package = tmp_path / "test.pkg.tar.zst"
    package.write_bytes(data)
    asset = ReleaseAsset(package.name, len(data), "https://x", hashlib.sha256(data).hexdigest())
    plan = UpdatePlan("package", asset=asset, manager="pacman")
    command = (
        'pkexec() { printf "%s\\n" "$*"; return 126; }\n'
        'sudo() { echo "unexpected fallback"; return 7; }\n'
        + install_command(plan, package, graphical=True)
    )
    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=False)
    assert result.returncode == 130
    assert "LC_ALL=C.UTF-8 LANGUAGE=C pacman" in result.stdout
    assert "unexpected fallback" not in result.stdout


def _fake_rpm_ostree(
    tmp_path: Path, status_json: str, *, busy_polls: int = 0, deny: bool = False, dismiss: bool = False,
) -> Path:
    """A stand-in rpm-ostree that records its calls and answers ``status``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    polls = tmp_path / "polls"
    polls.write_text(str(busy_polls))
    (bin_dir / "rpm-ostree").write_text(f"""#!/usr/bin/env bash
if [ "$1" = status ]; then
  left=$(cat {polls})
  if [ "$left" -gt 0 ]; then echo $((left - 1)) > {polls}; echo '{{"transaction": ["upgrade"], "deployments": []}}'; exit 0; fi
  cat <<'JSON'
{status_json}
JSON
  exit 0
fi
echo "rpm-ostree $*" >> {calls}
if [ {int(dismiss)} = 1 ]; then echo "error: Authorization failed: Request dismissed"; exit 1; fi
if [ {1 if deny else 0} = 1 ] && [ "$(id -un)" != root ] && [ -z "${{BC250_FAKE_SUDO:-}}" ]; then echo "error: Authorization required"; exit 1; fi
echo "Staging deployment...done"
""")
    (bin_dir / "sudo").write_text(f"""#!/usr/bin/env bash
echo "sudo $*" >> {calls}
BC250_FAKE_SUDO=1 exec env "$@"
""")
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    return bin_dir


def _run_rpm_ostree_update(tmp_path: Path, status_json: str, **fake) -> tuple[int, str, str]:
    data = b"rpm bytes"
    package = tmp_path / "bc250-control-center-1.20.4.noarch.rpm"
    package.write_bytes(data)
    asset = ReleaseAsset(package.name, len(data), "https://x", hashlib.sha256(data).hexdigest())
    plan = UpdatePlan("package", asset=asset, manager="rpm-ostree", reboot_required=True)
    bin_dir = _fake_rpm_ostree(tmp_path, status_json, **fake)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    result = subprocess.run(
        ["bash", "-c", install_command(plan, package)], env=env, capture_output=True, text=True, timeout=30
    )
    calls = (tmp_path / "calls.log").read_text() if (tmp_path / "calls.log").exists() else ""
    return result.returncode, calls, result.stdout


def test_rpm_ostree_replaces_the_layered_version_in_one_transaction(tmp_path):
    """A plain install next to a layered 1.19 fails with "cannot install both"."""
    status = '{"transaction": null, "deployments": [{"requested-local-packages": ["bc250-control-center-1.19.0-1.fc44.noarch"], "requested-packages": ["htop"]}]}'
    code, calls, _out = _run_rpm_ostree_update(tmp_path, status)
    assert code == 0
    assert calls.splitlines() == [
        f"rpm-ostree uninstall bc250-control-center-1.19.0-1.fc44.noarch --install {tmp_path}/bc250-control-center-1.20.4.noarch.rpm"
    ]
    assert "sudo" not in calls  # Polkit asks in a window; sudo is only the fallback


def test_rpm_ostree_installs_fresh_when_nothing_is_layered(tmp_path):
    status = '{"transaction": null, "deployments": [{"requested-local-packages": [], "requested-packages": []}]}'
    code, calls, _out = _run_rpm_ostree_update(tmp_path, status)
    assert code == 0
    assert calls.splitlines() == [f"rpm-ostree install {tmp_path}/bc250-control-center-1.20.4.noarch.rpm"]


def test_rpm_ostree_waits_for_an_automatic_system_update(tmp_path):
    status = '{"transaction": null, "deployments": [{}]}'
    code, calls, out = _run_rpm_ostree_update(tmp_path, status, busy_polls=2)
    assert code == 0
    assert "waiting for it to finish" in out
    assert calls.splitlines() == [f"rpm-ostree install {tmp_path}/bc250-control-center-1.20.4.noarch.rpm"]


def test_rpm_ostree_falls_back_to_sudo_when_polkit_cannot_ask(tmp_path):
    status = '{"transaction": null, "deployments": [{}]}'
    code, calls, out = _run_rpm_ostree_update(tmp_path, status, deny=True)
    assert code == 0
    assert "asking for the password in this terminal" in out
    lines = calls.splitlines()
    assert lines[0].startswith("rpm-ostree install ")
    assert lines[1].startswith("sudo rpm-ostree install ")


def test_rpm_ostree_keeps_a_polkit_dismissal_cancelled(tmp_path):
    status = '{"transaction": null, "deployments": [{}]}'
    code, calls, _out = _run_rpm_ostree_update(tmp_path, status, dismiss=True)
    assert code == 130
    assert "sudo " not in calls


def test_rpm_ostree_refuses_a_package_that_changed_in_the_cache(tmp_path):
    status = '{"transaction": null, "deployments": [{}]}'
    data = b"rpm bytes"
    package = tmp_path / "bc250-control-center-1.20.4.noarch.rpm"
    package.write_bytes(data)
    asset = ReleaseAsset(package.name, len(data), "https://x", "0" * 64)
    plan = UpdatePlan("package", asset=asset, manager="rpm-ostree")
    bin_dir = _fake_rpm_ostree(tmp_path, status)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    result = subprocess.run(["bash", "-c", install_command(plan, package)], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert not (tmp_path / "calls.log").exists()


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _Opener:
    def __init__(self, data: bytes):
        self.data = data

    def open(self, request, timeout=None):
        assert request.full_url.startswith("https://")
        return _Response(self.data)


def test_a_download_that_matches_its_checksum_is_kept(tmp_path):
    data = b"package bytes" * 1000
    asset = ReleaseAsset("bc250-control-center-1.pkg.tar.zst", len(data), "https://x", hashlib.sha256(data).hexdigest())
    seen = []
    path = download_asset(asset, tmp_path, progress=lambda done, total: seen.append((done, total)), opener=_Opener(data))
    assert path.read_bytes() == data
    assert seen[-1] == (len(data), len(data))
    assert not (tmp_path / f"{asset.name}.part").exists()


def test_a_verified_package_is_reused_instead_of_downloaded_again(tmp_path):
    """A retry after a password timeout must not fetch the package twice."""
    data = b"package bytes" * 1000
    asset = ReleaseAsset("bc250-control-center-1.pkg.tar.zst", len(data), "https://x", hashlib.sha256(data).hexdigest())
    (tmp_path / asset.name).write_bytes(data)

    class _NoNetwork:
        def open(self, request, timeout=None):  # pragma: no cover - must not be reached
            raise AssertionError("a verified package must not be downloaded again")

    seen = []
    path = download_asset(asset, tmp_path, progress=lambda done, total: seen.append((done, total)), opener=_NoNetwork())
    assert path.read_bytes() == data
    assert seen == [(len(data), len(data))]


def test_a_cached_package_that_no_longer_matches_is_downloaded_again(tmp_path):
    data = b"package bytes" * 1000
    asset = ReleaseAsset("bc250-control-center-1.pkg.tar.zst", len(data), "https://x", hashlib.sha256(data).hexdigest())
    (tmp_path / asset.name).write_bytes(b"tampered" + data[8:])
    path = download_asset(asset, tmp_path, opener=_Opener(data))
    assert path.read_bytes() == data


def test_old_versions_and_crash_leftovers_leave_the_cache(tmp_path):
    for name in ("bc250-control-center-1.19.0.rpm", "bc250-control-center-1.20.0.rpm.part", "bc250-control-center-1.20.3.rpm"):
        (tmp_path / name).write_bytes(b"x")
    prune_updates(tmp_path, keep="bc250-control-center-1.20.3.rpm")
    assert [entry.name for entry in tmp_path.iterdir()] == ["bc250-control-center-1.20.3.rpm"]
    discard_update(tmp_path / "bc250-control-center-1.20.3.rpm")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("problem", ["checksum", "short", "long", "cancel", "no-checksum", "http", "path"])
def test_a_download_that_is_not_the_published_file_is_thrown_away(tmp_path, problem):
    data = b"package bytes" * 100
    digest = hashlib.sha256(data).hexdigest()
    size = len(data)
    name = "bc250-control-center-1.pkg.tar.zst"
    url = "https://x"
    served = data
    cancelled = None
    if problem == "checksum":
        digest = "0" * 64
    elif problem == "short":
        served = data[:-5]
    elif problem == "long":
        served = data + b"extra"
    elif problem == "cancel":
        cancelled = lambda: True  # noqa: E731
    elif problem == "no-checksum":
        digest = ""
    elif problem == "http":
        url = "http://x"
    elif problem == "path":
        name = "../escape.pkg.tar.zst"
    asset = ReleaseAsset(name, size, url, digest)
    with pytest.raises(UpdateError):
        download_asset(asset, tmp_path, cancelled=cancelled, opener=_Opener(served))
    assert list(tmp_path.iterdir()) == []


def test_the_service_only_installs_from_the_updates_folder(tmp_path, monkeypatch):
    from bc250cc.infrastructure import self_update
    from bc250cc.infrastructure.system_service import SistemaService

    updates = tmp_path / "updates"
    updates.mkdir()
    monkeypatch.setattr(self_update, "updates_directory", lambda: updates)
    launched = []

    class Repo:
        def _abrir_terminal(self, command, title):
            launched.append((command, title))
            return "launched"

    from bc250cc.infrastructure import system_service

    monkeypatch.setattr(system_service, "_graphical_authorization", lambda: False)
    service = SistemaService(Repo())
    asset = ReleaseAsset("bc250-control-center.pkg.tar.zst", 3, "https://x", "a" * 64)
    plan = UpdatePlan("package", asset=asset, manager="pacman")
    outside = tmp_path / "bc250-control-center.pkg.tar.zst"
    outside.write_bytes(b"abc")
    with pytest.raises(UpdateError):
        service.instalar_actualizacion(plan, str(outside))
    inside = updates / "bc250-control-center.pkg.tar.zst"
    inside.write_bytes(b"abc")
    assert service.instalar_actualizacion(plan, str(inside)) == "launched"
    assert launched[0][0].endswith(f"bc250_admin pacman -U --noconfirm -- {inside}")


def test_release_info_is_hashable_data():
    info = ReleaseInfo("1", "v1", "t", "", "", "https://x")
    assert info.assets == ()


def _installed_copy(prefix: Path) -> Path:
    root = prefix / "share" / "bc250-control-center"
    root.mkdir(parents=True)
    return root


def test_a_script_install_is_updated_under_its_own_prefix(tmp_path):
    release = parse_release(_payload())
    plan = plan_update(release, InstallSource(UpdateChannel.RELEASE), project_root=_root(tmp_path))
    package = tmp_path / "bc250-control-center-1.20.0.tar.gz"
    user_copy = _installed_copy(tmp_path / "home" / ".local")
    command = install_command(plan, package, install_root=user_copy)
    assert command.endswith(f"&& env PREFIX={tmp_path / 'home' / '.local'} bash scripts/install-local.sh")


def test_a_copy_installed_with_sudo_is_updated_with_sudo_in_place(tmp_path):
    release = parse_release(_payload())
    plan = plan_update(release, InstallSource(UpdateChannel.RELEASE), project_root=_root(tmp_path))
    system_copy = _installed_copy(tmp_path / "usr" / "local")
    system_copy.chmod(0o555)
    try:
        command = install_command(plan, tmp_path / "pkg.tar.gz", install_root=system_copy)
    finally:
        system_copy.chmod(0o755)
    if os.geteuid() == 0:
        pytest.skip("root can write anywhere")
    assert command.endswith(f"&& sudo env PREFIX={tmp_path / 'usr' / 'local'} bash scripts/install-local.sh")


def test_an_unrecognised_layout_keeps_the_installer_default(tmp_path):
    release = parse_release(_payload())
    plan = plan_update(release, InstallSource(UpdateChannel.RELEASE), project_root=_root(tmp_path))
    command = install_command(plan, tmp_path / "pkg.tar.gz", install_root=tmp_path / "bc250-control-center-1.20.3")
    assert command.endswith("&& bash scripts/install-local.sh")
