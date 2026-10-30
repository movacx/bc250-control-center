from PyQt6.QtWidgets import QDialog, QLabel

from frontends.desktop.pages.remote_access import RemoteAccessPage


def test_remote_access_renders_a_local_qr_and_certificate_fingerprint(qtbot, monkeypatch):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._web_state = {"urls": ["https://192.0.2.1:8250"], "key": "TEST-PAIR", "tls_fingerprint": ":".join(["AB"] * 32)}
    seen = []

    def inspect(dialog):
        labels = dialog.findChildren(QLabel)
        images = [label.pixmap() for label in labels if label.pixmap() and not label.pixmap().isNull()]
        assert len(images) == 1
        assert images[0].width() == 300
        assert any("SHA-256" in label.text() for label in labels)
        seen.append(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", inspect)
    page._show_web_qr()
    assert seen == [True]


def test_pairing_qr_is_not_generated_for_plaintext_network_access(qtbot, monkeypatch):
    page = RemoteAccessPage()
    qtbot.addWidget(page)
    page._web_state = {"urls": ["http://192.0.2.1:8250"], "key": "TEST-PAIR", "tls": False}

    def forbidden(_dialog):
        raise AssertionError("network pairing must use HTTPS")

    monkeypatch.setattr(QDialog, "exec", forbidden)
    page._show_web_qr()
