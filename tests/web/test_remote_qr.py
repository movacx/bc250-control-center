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
    assert page.web_certificate_button.isEnabled()
    assert not page.web_qr_image.isHidden()


def test_pairing_qr_is_not_generated_for_plaintext_network_access(qtbot):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._apply_web({"running": True, "lan": True, "urls": ["http://192.0.2.1:8250"], "key": "TEST-PAIR", "tls": False})
    assert page.web_qr_image.pixmap().isNull()


def test_qr_carries_a_one_time_token_never_the_access_key(qtbot, monkeypatch):
    from bc250cc.application.system import web_access, web_pairing
    render = web_access.pairing_svg
    urls = []
    monkeypatch.setattr(web_access, "pairing_svg", lambda url: urls.append(url) or render(url))
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    state = {"running": True, "lan": True, "urls": ["https://192.168.0.2:8250", "https://192.168.1.2:8250"], "key": "TEST-PAIR"}
    page._apply_web(state)
    page.web_address.setCurrentIndex(1)
    assert [url.split("#pair=")[0] for url in urls] == state["urls"]
    token = urls[0].split("#pair=")[1]
    assert "TEST-PAIR" not in urls[0] and token == urls[1].split("#pair=")[1]
    assert web_pairing.consume(token) is True
    assert web_pairing.consume(token) is False
    # Once redeemed the next refresh shows a fresh code.
    page._apply_web(state)
    assert urls[-1].split("#pair=")[1] != token
