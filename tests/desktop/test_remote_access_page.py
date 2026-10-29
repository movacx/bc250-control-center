from __future__ import annotations

from bc250cc.infrastructure import remote_access
from frontends.desktop.pages.remote_access import RemoteAccessPage


def _state(**changes):
    state = {"systemd": True, "unit": "sshd.service", "active": False, "enabled": False,
             "port": 22, "user": "deck", "addresses": ["192.168.1.40"]}
    return {**state, **changes}


def test_the_page_offers_the_switch_and_the_command_to_type(qtbot):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._apply(_state())
    assert page.switch_button.text() == "Turn on remote access" and not page.switch_button.isHidden()
    assert page.command_box.text() == "ssh deck@192.168.1.40"
    page._apply(_state(active=True, port=2222))
    assert page.switch_button.text() == "Turn off remote access"
    assert page.command_box.text() == "ssh -p 2222 deck@192.168.1.40"


def test_without_a_server_or_systemd_there_is_no_switch(qtbot):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._apply(_state(unit=""))
    assert page.switch_button.isHidden()
    page._apply(_state(systemd=False))
    assert page.switch_button.isHidden()


def test_addresses_skip_container_and_loopback_links(monkeypatch):
    listing = (
        "2: enp5s0    inet 192.168.1.40/24 brd 192.168.1.255 scope global dynamic enp5s0\n"
        "3: docker0    inet 172.17.0.1/16 scope global docker0\n"
        "4: virbr0    inet 192.168.122.1/24 scope global virbr0\n"
    )
    monkeypatch.setattr(
        remote_access.subprocess, "run",
        lambda *a, **k: type("R", (), {"stdout": listing, "returncode": 0})(),
    )
    assert remote_access.addresses() == ["192.168.1.40"]


def test_turning_it_on_asks_polkit_for_one_systemctl_enable(monkeypatch):
    seen = []
    monkeypatch.setattr(remote_access, "_unit", lambda: "ssh.service")
    monkeypatch.setattr(remote_access, "pkexec_argv", lambda *args: list(args))
    monkeypatch.setattr(
        remote_access.subprocess, "run",
        lambda command, **k: seen.append(command) or type("R", (), {"returncode": 0, "stderr": ""})(),
    )
    remote_access.set_enabled(True)
    assert seen[0][0] == "pkexec" and seen[0][2:] == ["enable", "--now", "ssh.service"]


def test_turning_it_on_without_a_server_says_what_to_install(monkeypatch):
    import pytest

    monkeypatch.setattr(remote_access, "_unit", lambda: "")
    with pytest.raises(RuntimeError, match="not installed"):
        remote_access.set_enabled(True)


def test_the_page_has_no_status_pill_and_previews_every_screenshot(qtbot):
    from frontends.desktop.components.tui_preview_dialog import SCREENSHOTS, SHOTS, TuiPreviewDialog

    page = RemoteAccessPage()
    qtbot.addWidget(page)
    assert page.card.status is None
    assert all((SCREENSHOTS / name).exists() for name, _caption in SHOTS)
    dialog = TuiPreviewDialog()
    qtbot.addWidget(dialog)
    dialog.next.click()
    assert "2/5" in dialog.caption.text()
    dialog.previous.click()
    dialog.previous.click()
    assert "5/5" in dialog.caption.text()
