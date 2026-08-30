from types import SimpleNamespace

import frontends.desktop.core.external_links as external_links_module
import frontends.desktop.pages.settings as settings_module
from frontends.desktop.core.external_links import open_external_url, open_local_file


def test_external_link_handler_failure_is_graceful():
    opened, message = open_external_url(
        "https://discord.com/users/719291715369959445",
        opener=lambda _url: False,
    )
    assert opened is False
    assert "No browser" in message


def test_external_link_handler_exception_is_graceful():
    def broken(_url):
        raise RuntimeError("desktop unavailable")

    opened, message = open_external_url(
        "https://discord.com/users/719291715369959445",
        opener=broken,
    )
    assert opened is False
    assert "desktop unavailable" in message


def test_settings_contact_fallback_shows_copyable_url(monkeypatch):
    shown = {}

    class FakeDialog:
        def __init__(self, title, message, **kwargs):
            shown.update(title=title, message=message, **kwargs)

        def exec(self):
            shown["executed"] = True

    monkeypatch.setattr(
        settings_module,
        "open_external_url",
        lambda _url: (False, "desktop unavailable"),
    )
    monkeypatch.setattr(settings_module, "InfoDialog", FakeDialog)

    settings_module.SettingsPage._open_contact(SimpleNamespace())

    assert shown["executed"] is True
    assert shown["message"] == "desktop unavailable"
    assert settings_module.CONTACT_URL in shown["notice"]


def test_external_link_rejects_non_https_without_calling_handler():
    opened, message = open_external_url(
        "file:///etc/passwd",
        opener=lambda _url: (_ for _ in ()).throw(AssertionError("handler must not run")),
    )
    assert opened is False
    assert "HTTPS" in message


def test_local_file_uses_the_desktop_mime_handler(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[frequency-range]\n", encoding="utf-8")
    received = []

    opened, message = open_local_file(
        path,
        opener=lambda url: received.append(url) or True,
    )

    assert opened is True
    assert message == ""
    assert len(received) == 1
    assert received[0].isLocalFile()
    assert received[0].toLocalFile() == str(path.resolve())


def test_local_file_failure_is_graceful(tmp_path):
    missing = tmp_path / "missing.toml"

    opened, message = open_local_file(
        missing,
        opener=lambda _url: (_ for _ in ()).throw(
            AssertionError("handler must not run")
        ),
    )

    assert opened is False
    assert "does not exist" in message


def test_local_file_handler_rejection_is_graceful(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")

    opened, message = open_local_file(
        path,
        opener=lambda _url: False,
        text_editor_fallback=lambda _path: (False, ""),
    )

    assert opened is False
    assert "No text editor" in message


def test_local_file_falls_back_to_the_default_text_editor(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    received = []

    opened, message = open_local_file(
        path,
        opener=lambda _url: False,
        text_editor_fallback=lambda resolved: (
            received.append(resolved) or True,
            "",
        ),
    )

    assert opened is True
    assert message == ""
    assert received == [path.resolve()]


def test_text_editor_fallback_uses_validated_desktop_entry(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "share"
    applications = data_root / "applications"
    applications.mkdir(parents=True)
    desktop_file = applications / "org.example.Editor.desktop"
    desktop_file.write_text("[Desktop Entry]\n", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    launched = []

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "user-share"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(data_root))
    monkeypatch.setattr(
        external_links_module.shutil,
        "which",
        lambda command: f"/usr/bin/{command}",
    )
    monkeypatch.setattr(
        external_links_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="org.example.Editor.desktop\n",
        ),
    )
    monkeypatch.setattr(
        external_links_module.subprocess,
        "Popen",
        lambda args, **kwargs: launched.append((args, kwargs)),
    )

    opened, message = external_links_module._launch_default_text_editor(config)

    assert opened is True
    assert message == ""
    assert launched[0][0] == [
        "/usr/bin/gio",
        "launch",
        str(desktop_file),
        config.as_uri(),
    ]


def test_text_editor_fallback_rejects_unsafe_desktop_id(
    tmp_path,
    monkeypatch,
):
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        external_links_module.shutil,
        "which",
        lambda _command: "/usr/bin/xdg-mime",
    )
    monkeypatch.setattr(
        external_links_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="../../malicious.desktop\n",
        ),
    )

    opened, message = external_links_module._launch_default_text_editor(config)

    assert opened is False
    assert "No valid" in message
