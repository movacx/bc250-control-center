"""Press every button of every module on the real window, with nothing allowed to act.

This lives in ``zz_click_through`` so it runs after everything else: it opens the
whole window, and what it leaves for Qt to reap must not meet another test.

A page can build fine and still raise the moment one of its buttons is pressed
(a renamed attribute, a missing translation key, a signal wired to a method
that no longer exists). This opens the production window, visits each module
and clicks every enabled button, with dialogs, processes and the network
replaced so the click reaches the handler and goes no further. An exception
raised in any handler fails the test and names the button.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QProcess, QThreadPool
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
    QStackedWidget,
)

from bc250cc.application.container import ApplicationContainer
from frontends.desktop.app import ControlCenterWindow

#: Buttons that end the session or hand control to something outside the app.
SKIP_TEXT = ("quit", "exit", "restart", "reboot", "close")


class _Done(subprocess.CompletedProcess):
    def __init__(self, *args, **kwargs):
        super().__init__(args=args, returncode=1, stdout="", stderr="blocked by the click-through test")


#: Commands that only read; with these allowed the pages see this machine's real
#: state, so buttons that stay disabled without hardware become enabled.
READ_ONLY = frozenset({"lspci", "lsmod", "uname", "cat", "ls", "uptime", "which", "getconf", "id", "stat", "findmnt", "df", "free", "nproc", "lscpu", "sensors", "dmidecode_never"})
READ_ONLY_SYSTEMCTL = frozenset({"is-active", "is-enabled", "is-failed", "status", "show", "list-units", "list-unit-files", "cat"})


def _read_only(argv) -> bool:
    if isinstance(argv, str) or not argv:
        return False
    name = os.path.basename(str(argv[0]))
    if name == "systemctl":
        words = [str(a) for a in argv[1:] if not str(a).startswith("-")]
        return bool(words) and words[0] in READ_ONLY_SYSTEMCTL
    return name in READ_ONLY


@pytest.fixture(params=("blocked", "read-only-probes"))
def isolated(request, monkeypatch, tmp_path):
    for variable in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    real_run, real_popen, real_check_output = subprocess.run, subprocess.Popen, subprocess.check_output
    probes = request.param == "read-only-probes"

    def run(argv, *a, **k):
        if probes and _read_only(argv):
            return real_run(argv, *a, **k)
        return _Done(argv)

    def popen(argv, *a, **k):
        if probes and _read_only(argv):
            return real_popen(argv, *a, **k)
        raise OSError("blocked")

    def check_output(argv, *a, **k):
        if probes and _read_only(argv):
            return real_check_output(argv, *a, **k)
        raise OSError("blocked")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "check_output", check_output)
    request.node.probes = probes
    monkeypatch.setattr(QProcess, "start", lambda *a, **k: None)
    monkeypatch.setattr(QProcess, "startDetached", lambda *a, **k: False, raising=False)
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QDialog, "open", lambda self: None)
    for name in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
    for name in ("getOpenFileName", "getSaveFileName", "getExistingDirectory", "getOpenFileNames"):
        monkeypatch.setattr(QFileDialog, name, staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(sys, "exit", lambda *a: None)
    # The built-in terminal forks a real shell; nothing may run in this test.
    for name in ("fork", "forkpty", "execv", "execvp", "system", "posix_spawn"):
        monkeypatch.setattr(os, name, lambda *a, **k: (_ for _ in ()).throw(OSError("blocked")), raising=False)


def test_every_button_of_every_module_can_be_pressed(qtbot, isolated):
    container = ApplicationContainer.production()
    window = ControlCenterWindow(
        container.system_service,
        settings_service=container.settings_service,
        activity_service=container.activity_service,
    )
    qtbot.addWidget(window)
    window._first_run_pending = False  # the welcome panel would disable the whole shell
    window.show()
    pressed: list[str] = []
    seen: set[int] = set()

    def visible_buttons(page):
        found = []
        for button in page.findChildren(QAbstractButton):
            label = (button.text() or button.objectName() or button.toolTip()).strip()
            if (
                label
                and button.isEnabled()
                and button.isVisibleTo(page)
                and not button.isCheckable()
                and not any(word in label.lower() for word in SKIP_TEXT)
            ):
                found.append((label, button))
        return found

    def press_new(key):
        page = window.pages[key]
        for label, button in visible_buttons(page):
            if id(button) in seen or sip.isdeleted(button):
                continue
            seen.add(id(button))
            window.navigate(key)
            if not button.isEnabled() or not button.isVisibleTo(page):
                continue
            button.click()
            QApplication.processEvents()
            pressed.append(f"{key}: {label}")

    with qtbot.capture_exceptions() as errors:
        for key in list(window.pages):
            window.navigate(key)
            qtbot.wait(1500)  # the page reads its state in the background; buttons wake up afterwards
            press_new(key)
            if key != "processes":  # a selection there means real tasks to end
                # Choosing something (a WGP, a fan, a profile) is what enables Apply, Save or Reset.
                for button in window.pages[key].findChildren(QAbstractButton):
                    if button.isCheckable() and button.isEnabled() and button.isVisibleTo(window.pages[key]) and id(button) not in seen:
                        seen.add(id(button))
                        button.click()
                        QApplication.processEvents()
                        pressed.append(f"{key}: (choose) {button.text() or button.objectName()}")
                qtbot.wait(300)
                press_new(key)
            # Tabs and stacked views hide buttons that only exist when their page is shown.
            for stack in window.pages[key].findChildren(QStackedWidget):
                for index in range(stack.count()):
                    if sip.isdeleted(stack):
                        break
                    window.navigate(key)
                    stack.setCurrentIndex(index)
                    qtbot.wait(200)
                    press_new(key)

    # Leave nothing behind for the next test: windows opened by a click, the
    # performance recording and the page refreshers are all stopped here.
    window.performance_page.stop_recording() if hasattr(window.performance_page, "stop_recording") else None
    for widget in QApplication.topLevelWidgets():
        if widget is not window:
            widget.hide()
            widget.deleteLater()
    QThreadPool.globalInstance().waitForDone(3000)
    window.close()
    qtbot.wait(300)
    print(f"pressed {len(pressed)} buttons")
    assert len(pressed) > 100, f"only {len(pressed)} buttons were pressed"
    assert not errors, "\n".join(f"{type(e[1]).__name__}: {e[1]}" for e in errors)
