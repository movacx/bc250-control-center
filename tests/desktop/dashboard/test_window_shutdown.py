from threading import Event

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QMainWindow

from frontends.desktop.app import ControlCenterWindow


class PendingTask(QThread):
    def __init__(self, release: Event, parent=None):
        super().__init__(parent)
        self.release = release

    def run(self) -> None:
        self.release.wait()


class BareWindow(ControlCenterWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.gamepad = None
        self._gamemode_session = False


def test_close_waits_for_running_child_thread(qtbot):
    release = Event()
    window = BareWindow()
    qtbot.addWidget(window)
    window.show()

    task = PendingTask(release, window)
    task.start()
    qtbot.waitUntil(task.isRunning)

    try:
        window.close()
        assert window.isVisible()
    finally:
        release.set()
        assert task.wait(1000)

    qtbot.waitUntil(lambda: not window.isVisible())
