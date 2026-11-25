"""Keep remote ownership and SSH tests isolated from the owner's actual session."""
from copy import deepcopy

import pytest


@pytest.fixture(autouse=True)
def isolated_remote_access(monkeypatch):
    from bc250cc.application.system import remote_access, web_access

    web = {"running": False, "key": "TEST-TEST", "port": 8250, "lan": False,
           "local_url": "https://127.0.0.1:8250", "devices": [], "autostart": {"supported": False}}
    ssh = {"active": False, "enabled": False, "supported": False, "unit": "", "addresses": []}
    monkeypatch.setattr(web_access, "status", lambda: deepcopy(web))
    monkeypatch.setattr(remote_access, "status", lambda: deepcopy(ssh))
    for name in ("start", "stop", "configure", "set_autostart", "set_control", "revoke", "revoke_all", "set_lifetime"):
        monkeypatch.setattr(web_access, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(web_access, "access_key", lambda **kwargs: "TEST-TEST")
    monkeypatch.setattr(remote_access, "configure", lambda **kwargs: None)
    return web, ssh


@pytest.fixture(autouse=True)
def english_again():
    """A test that switches the interface language leaves the next one in English."""
    from frontends.tui.i18n import set_language

    set_language("en")
    yield
    set_language("en")


@pytest.fixture(autouse=True)
def never_the_real_sudo(monkeypatch):
    """No test may reach this machine's sudo: a wrong password there locks the owner's account.

    A test about authorization puts a stand-in first in PATH and starts its own terminal.
    """
    from frontends.tui import console

    terminal = console.SudoTerminal()
    real_start = terminal._start

    def start(for_console):
        import shutil

        found = shutil.which("sudo") or ""
        if not found or found.startswith(("/usr/", "/bin/", "/sbin/", "/run/")):
            return False
        return real_start(for_console)

    monkeypatch.setattr(terminal, "_start", start)
    monkeypatch.setattr(console, "SUDO", terminal)
    yield terminal
    terminal.stop()


@pytest.fixture(autouse=True)
def never_a_real_report(monkeypatch):
    """No test may send a report, nor read this machine's logs for one."""
    from bc250cc.application.system.feedback import reports as form

    def refuse(*_args, **_kwargs):
        raise form.ReportError("No test sends a report.")

    monkeypatch.setattr(form, "submit", refuse)
    monkeypatch.setattr(form, "earlier_report", lambda *a, **k: None)
    monkeypatch.setattr("frontends.desktop.core.report_facts.read_report_facts", lambda attachments=True: {})


@pytest.fixture(autouse=True)
def a_failure_asks_nothing(monkeypatch):
    """A failed action's question waits for a key no scripted test sends; its own tests put it back."""
    from frontends.tui.screen import Screen

    monkeypatch.setattr(Screen, "_asks_to_report", lambda *_args: False)
