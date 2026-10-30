from __future__ import annotations

from bc250cc.infrastructure import remote_access
from frontends.desktop.pages.remote_access import RemoteAccessPage


def test_remote_access_is_one_web_workspace(qtbot):
    from PyQt6.QtWidgets import QPushButton

    from frontends.desktop.components.page_widgets import SectionCard
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    assert len(page.findChildren(SectionCard)) == 1
    assert not hasattr(page, "command_box")
    assert not any("SSH" in button.text() or "terminal" in button.text().lower() for button in page.findChildren(QPushButton))
    assert not hasattr(page, "web_qr_button")


def test_web_controls_stay_visible_when_stopped(qtbot):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._apply_web({"running": False, "key": "ABCD-EFGH", "tls": True})
    assert not page.web_qr_image.isHidden()
    assert page.web_qr_image.pixmap().isNull()
    assert page.web_switch_button.text() == "Start web access"
    assert page.web_pin_box.text() == "ABCD-EFGH"


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


def test_device_control_and_revocation_are_owner_actions(qtbot, monkeypatch):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    calls = []
    monkeypatch.setattr(page, "_run", lambda _name, work: work())
    monkeypatch.setattr("frontends.desktop.pages.remote_access.web_access.set_control", lambda d, a: calls.append((d, a)))
    monkeypatch.setattr("frontends.desktop.pages.remote_access.web_access.revoke", lambda d: calls.append(d))
    page._apply_web({"devices": [{"id": "device", "address": "192.168.0.22", "agent": "Phone", "control": False}]})
    page.device_table.selectRow(0)
    from PyQt6.QtWidgets import QPushButton
    buttons = page.findChildren(QPushButton)
    next(b for b in buttons if b.text() == "Allow hardware control").click()
    next(b for b in buttons if b.text() == "Disconnect").click()
    assert calls == [("device", True), "device"]


def test_device_table_is_read_only_and_tracks_the_selected_identity_across_refresh(qtbot):
    from PyQt6.QtWidgets import QAbstractItemView
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    first = {"id": "aaaaaaaa11", "address": "192.168.0.22", "agent": "Android Chrome/123", "control": False, "seen": 100000}
    other = {"id": "bbbbbbbb22", "address": "192.168.0.23", "agent": "iPhone Safari/123", "control": True, "seen": 100001}
    page._apply_web({"devices": [first, other]})
    table = page.device_table
    assert table.columnCount() == 7 and table.rowCount() == 2
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert not page.device_control_button.isEnabled()
    table.selectRow(0)
    assert page._selected_device()["id"] == first["id"]
    assert page.device_control_button.text() == "Allow hardware control"
    before = table.item(0, 5).text()
    page._apply_web({"devices": [other, {**first, "seen": 100100, "control": True}]})
    assert page._selected_device()["id"] == first["id"]
    assert table.currentRow() == 1
    assert table.item(1, 1).text() == first["address"]
    assert table.item(1, 2).text() == "aaaaaaaa"
    assert table.item(1, 5).text() != before
    assert page.device_control_button.text() == "Monitoring only"
    page._apply_web({"devices": [other]})
    assert page._selected_device() is None
    assert not page.device_control_button.isEnabled()
    assert not page.device_disconnect_button.isEnabled()
