from PyQt6.QtWidgets import QDialog

from frontends.desktop.pages.remote_access import RemoteAccessPage


def test_remote_access_displays_qr_inline_without_opening_a_dialog(qtbot, monkeypatch):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    monkeypatch.setattr(QDialog, "exec", lambda _: (_ for _ in ()).throw(AssertionError("QR must be inline")))
    page._apply_web({"running": True, "lan": True, "urls": ["https://192.0.2.1:8250"],
                     "key": "TEST-PAIR", "trust_fingerprint": ":".join(["AB"] * 32)})
    assert not page.web_qr_image.pixmap().isNull()
    assert page.web_qr_image.pixmap().size() == page.web_qr_image.size()
    assert page.web_qr_image.width() >= 192
    assert "SHA-256" in page.web_fingerprint_box.text()
    assert not page.web_qr_image.isHidden()


def test_pairing_qr_is_not_generated_for_plaintext_network_access(qtbot):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._apply_web({"running": True, "lan": True, "urls": ["http://192.0.2.1:8250"], "key": "TEST-PAIR", "tls": False})
    assert page.web_qr_image.pixmap().isNull()


def test_visible_qr_updates_when_address_or_key_changes(qtbot, monkeypatch):
    from bc250cc.application.system import web_access
    render = web_access.pairing_svg
    urls = []
    monkeypatch.setattr(web_access, "pairing_svg", lambda url: urls.append(url) or render(url))
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    state = {"running": True, "lan": True, "urls": ["https://192.168.0.2:8250", "https://192.168.1.2:8250"], "key": "TEST-PAIR"}
    page._apply_web(state)
    page.web_address.setCurrentIndex(1)
    page._apply_web({**state, "key": "NEXT-PAIR"})
    assert urls == [state["urls"][0] + "#pair=TEST-PAIR", state["urls"][1] + "#pair=TEST-PAIR", state["urls"][1] + "#pair=NEXT-PAIR"]
