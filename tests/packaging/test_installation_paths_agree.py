"""What a local install sets up, a packaged install must set up too.

The two paths are written in different files by different people at different
times, and nothing compared them. One divergence had already shipped: both
installed ``bc250-cyan-overlay-preflight``, but only the local installer wrote
the systemd drop-in that makes systemd run it before Cyan starts. On every
distribution installed from a package the helper sat there unused, and the
stale bind-mount failure it exists to prevent kept happening — the same failure
that blocks a clean governor restart.

The helper is invisible when it works, which is exactly why nobody noticed it
was never being called.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALL_LOCAL = ROOT / "scripts" / "install-local.sh"
UNINSTALL_LOCAL = ROOT / "scripts" / "uninstall-local.sh"
STAGE_PACKAGE = ROOT / "packaging" / "scripts" / "stage-package-root.sh"
DROPIN = ROOT / "packaging" / "common" / "91-bc250-control-center-overlay-preflight.conf"
PREFLIGHT = "/usr/libexec/bc250-control-center/bc250-cyan-overlay-preflight"


def _text(path: Path) -> str:
    if not path.is_file():  # pragma: no cover - packaging layouts without scripts
        pytest.skip(f"{path.name} is not present in this checkout")
    return path.read_text(encoding="utf-8")


def test_the_drop_in_exists_as_a_file_both_installers_can_use():
    assert DROPIN.is_file(), DROPIN


def test_the_drop_in_runs_the_preflight_before_cyan_starts():
    content = _text(DROPIN)
    assert "[Service]" in content
    assert f"ExecStartPre={PREFLIGHT}" in content


def test_the_drop_in_says_who_manages_it():
    """An unexplained file in a third-party unit's directory is a trap."""
    assert "BC250 Control Center" in _text(DROPIN)


def test_the_local_installer_installs_the_drop_in():
    text = _text(INSTALL_LOCAL)
    assert "91-bc250-control-center-overlay-preflight.conf" in text
    assert "SYSTEM_CYAN_OVERLAY_DROPIN" in text


def test_the_packaged_installer_installs_the_drop_in_too():
    """The divergence this whole file exists for."""
    text = _text(STAGE_PACKAGE)
    assert "91-bc250-control-center-overlay-preflight.conf" in text, (
        "packaged installs ship the preflight helper with nothing that runs it"
    )
    assert "cyan-skillfish-governor-smu.service.d" in text


def test_the_package_uses_the_vendor_directory_not_the_administrator_one():
    """/etc belongs to whoever runs the machine; a package writes under /usr."""
    text = _text(STAGE_PACKAGE)
    match = re.search(
        r"\$DESTDIR(/[\w/.-]*systemd/system/cyan-skillfish-governor-smu\.service\.d/[\w.-]+)",
        text,
    )
    assert match, "the drop-in destination could not be found"
    assert match.group(1).startswith("/usr/lib/systemd/system/"), match.group(1)


def test_neither_installer_writes_the_drop_in_by_hand():
    """Two copies of the same three lines is how they drifted the first time."""
    for path in (INSTALL_LOCAL, STAGE_PACKAGE):
        text = _text(path)
        assert f"'ExecStartPre={PREFLIGHT}'" not in text
        assert '"ExecStartPre=$SYSTEM_CYAN_OVERLAY_PREFLIGHT"' not in text, path.name


def test_the_uninstaller_knows_about_the_drop_in():
    """Anything an installer creates, an uninstaller has to be able to remove."""
    text = _text(UNINSTALL_LOCAL)
    assert "91-bc250-control-center-overlay-preflight.conf" in text


def test_every_helper_the_package_ships_is_one_that_exists():
    text = _text(STAGE_PACKAGE)
    block = text[text.index("for helper in") : text.index("do", text.index("for helper in"))]
    named = {
        line.strip().rstrip("\\").strip().rstrip(";").strip()
        for line in block.splitlines()[1:]
        if line.strip().rstrip("\\").strip().rstrip(";").strip()
    }
    present = {
        path.name
        for path in (ROOT / "privileged" / "helpers").iterdir()
        if path.is_file() and path.name != "README.md"
    }
    assert named <= present, sorted(named - present)


def test_the_package_ships_every_helper_that_exists():
    """A helper the local install has and the package lacks is the same class
    of divergence as the drop-in, one step earlier."""
    text = _text(STAGE_PACKAGE)
    present = {
        path.name
        for path in (ROOT / "privileged" / "helpers").iterdir()
        if path.is_file() and path.name != "README.md"
    }
    missing = sorted(name for name in present if name not in text)
    assert missing == [], f"these helpers are never packaged: {missing}"


def test_the_local_installer_installs_every_helper_that_exists():
    """The counterpart the packaging check never had.

    ``test_the_package_ships_every_helper_that_exists`` above pins the package.
    Nothing pinned the local installer, so ``bc250-quick-access-helper`` was
    installed only by the Decky installer — while ``uninstall-local.sh`` removed
    it unconditionally. A local install followed by a local uninstall therefore
    deleted a root helper this installer had never placed.
    """
    text = _text(INSTALL_LOCAL)
    present = {
        path.name
        for path in (ROOT / "privileged" / "helpers").iterdir()
        if path.is_file() and path.name != "README.md"
    }
    missing = sorted(name for name in present if name not in text)
    assert missing == [], f"the local installer never installs these: {missing}"


def test_whatever_the_local_installer_places_the_uninstaller_removes():
    install = _text(INSTALL_LOCAL)
    uninstall = _text(UNINSTALL_LOCAL)
    present = {
        path.name
        for path in (ROOT / "privileged" / "helpers").iterdir()
        if path.is_file() and path.name != "README.md"
    }
    orphans = sorted(
        name for name in present if name in install and name not in uninstall
    )
    assert orphans == [], f"installed but never removed: {orphans}"


def test_the_openrc_governor_service_runs_the_same_preflight_as_systemd():
    """The drop-in above only teaches systemd about the preflight.

    On an OpenRC host the helper was installed and never called, so the stale
    Cyan bind mount it exists to clear kept racing the governor start — the
    same class of gap this file was written for, one layer down.
    """
    helper = ROOT / "privileged" / "helpers" / "bc250-openrc-service-helper"
    if not helper.is_file():  # pragma: no cover - packaging layouts
        pytest.skip("the OpenRC helper is not present in this checkout")
    text = helper.read_text(encoding="utf-8")
    assert "start_pre()" in text
    assert PREFLIGHT in text, "the OpenRC service never runs the Cyan preflight"


# --------------------------------------------------- telling the desktop

# A desktop reads icons through a cache, so writing the files is only half of
# installing them. The uninstaller refreshed that cache and the installer did
# not, which made a reinstall the one case that went wrong: uninstalling
# rebuilt the cache *after* deleting the icons, installing then wrote new ones
# and told nobody, and every launcher kept showing the previous artwork from a
# cache that was older than the files it described.
CACHE_REFRESHERS = ("update-desktop-database", "gtk-update-icon-cache")


@pytest.mark.parametrize("tool", CACHE_REFRESHERS)
def test_the_installer_refreshes_the_desktop_caches(tool):
    assert tool in _text(INSTALL_LOCAL), (
        f"{tool} is never run after installing, so the desktop keeps the old icon"
    )


@pytest.mark.parametrize("tool", CACHE_REFRESHERS)
def test_the_uninstaller_refreshes_them_too(tool):
    assert tool in _text(UNINSTALL_LOCAL)


def test_the_icon_cache_refresh_survives_a_missing_theme_index():
    """A per-user hicolor directory has no index.theme of its own.

    Without ``-t`` (``--ignore-theme-index``) gtk-update-icon-cache refuses,
    and because the call is advisory the stale cache quietly survives.
    """
    text = _text(INSTALL_LOCAL)
    invocation = next(
        candidate.strip()
        for candidate in text.splitlines()
        if '"$icon_cache_tool"' in candidate and not candidate.strip().startswith(("#", "if ", "for "))
    )
    assert " -t " in invocation, invocation


def test_no_cache_refresh_can_fail_the_install():
    """They are advisory: a headless host has none of these tools."""
    text = _text(INSTALL_LOCAL)
    for line in text.splitlines():
        stripped = line.strip()
        if not any(tool in stripped for tool in CACHE_REFRESHERS + ("kbuildsycoca", "xdg-desktop-menu")):
            continue
        if stripped.startswith(("#", "if command -v", "for ", "elif")):
            continue
        assert "|| true" in stripped, f"this could abort the install: {stripped}"


def test_every_icon_size_that_is_installed_is_also_removed():
    """A size added to one loop and not the other leaves a file behind."""
    import re

    def sizes(text: str) -> list[str]:
        match = re.search(r"for size in ([0-9 ]+); do", text)
        assert match, "the icon size loop could not be found"
        return match.group(1).split()

    assert sizes(_text(INSTALL_LOCAL)) == sizes(_text(UNINSTALL_LOCAL))


def test_the_icons_the_installer_names_exist():
    import re

    text = _text(INSTALL_LOCAL)
    match = re.search(r"for size in ([0-9 ]+); do", text)
    assert match
    for size in match.group(1).split():
        icon = ROOT / "assets" / "icons" / f"bc250-control-center-{size}.png"
        assert icon.is_file(), f"the installer asks for {icon.name} and it is not there"
        assert icon.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{icon.name} is not a PNG"


def test_every_libexec_file_the_local_install_writes_is_also_removed():
    """A leftover here breaks every later package install, not just this one.

    ``pacman`` refuses to overwrite a file no package owns, so one module the
    uninstaller forgot is enough to block the AUR package from ever installing
    again — which is exactly what ``lib/bc250_contract.py`` did. It is shared
    by the system-setup and quick-access helpers, so it was not covered by the
    loop that removes the system-setup modules, and nothing compared the two
    lists.
    """
    installed = set(re.findall(r"/usr/libexec/bc250-control-center/lib/(\S+?\.(?:py|zip))", _text(INSTALL_LOCAL)))
    installed |= {
        f"{module}"
        for line in _text(INSTALL_LOCAL).splitlines()
        if "for setup_module in" in line
        for module in re.findall(r"(\w+\.py)", line)
    }
    removed = _text(UNINSTALL_LOCAL)
    missing = sorted(module for module in installed if module not in removed)
    assert missing == [], missing
