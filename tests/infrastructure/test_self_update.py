"""Updating from the latest release: the right package, proven, installed once.

The updater downloads a file that ends up installed as root, so what it may
download and run is narrow: https only, a SHA-256 GitHub published, the
package for this installation's own channel, and one command built here.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from bc250cc.infrastructure.install_source import InstallSource, UpdateChannel
from bc250cc.infrastructure.self_update import (
    ReleaseAsset,
    ReleaseInfo,
    UpdateError,
    UpdatePlan,
    clean_release_notes,
    download_asset,
    install_command,
    parse_release,
    plan_update,
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
    ["git-checkout", "steamos-package", "no-checksum", "no-package", "aur-without-helper"],
)
def test_what_cannot_be_done_safely_goes_to_the_release_page(tmp_path, case):
    root = _root(tmp_path)
    payload = _payload()
    source = InstallSource(UpdateChannel.PACKAGE, package="bc250-control-center", manager="pacman")
    family = ""
    if case == "git-checkout":
        (root / ".git").mkdir()
    elif case == "steamos-package":
        family = "steamos"
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
    verify, _sep, install = command.partition(" && ")
    assert verify.endswith("| sha256sum -c -") and "a" * 64 in verify
    assert install.startswith("sudo pacman -U --noconfirm -- ")
    assert "'" + str(path) + "'" in command


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
    assert launched[0][0].endswith(f"sudo pacman -U --noconfirm -- {inside}")


def test_release_info_is_hashable_data():
    info = ReleaseInfo("1", "v1", "t", "", "", "https://x")
    assert info.assets == ()
