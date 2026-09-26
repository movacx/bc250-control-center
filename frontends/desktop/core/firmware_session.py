"""The firmware page's moving parts: USB discovery and the preparation job.

``UsbDriveWatcher`` notices drives the moment udev adds or removes their
/dev/disk entries, and polls as a fallback, but only while the page is on
screen: an idle window has no business spawning lsblk every few seconds.

``UsbPreparationJob`` runs the preparation on its own thread and reports each
step back to the interface. It can be cancelled until the drive is touched,
and says so: ``can_cancel`` turns false the moment the erase begins.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, pyqtSignal

from bc250cc.domain.firmware.usb import UsbDrive
from bc250cc.domain.firmware.usb_kit import KitPlan
from bc250cc.infrastructure.firmware.preparation import (
    PreparationCancelled,
    PreparationError,
    UsbPreparation,
)
from bc250cc.infrastructure.firmware.usb_devices import list_usb_drives

from ..components.async_tools import BackgroundExecutor

#: udev keeps one symlink per disk here, so a stick plugged in or pulled out
#: changes the directory straight away.
WATCHED_DIRECTORIES = ("/dev/disk/by-id", "/dev/disk/by-path", "/dev/disk")
#: Fallback for systems without those links, and for the moment udev takes to
#: finish probing a new stick after its node appears.
POLL_MS = 3000
#: Plugging a stick in fires several events within a few hundred ms.
SETTLE_MS = 450
#: Steps after which the drive has been changed and cannot be left halfway.
DESTRUCTIVE_STEPS = frozenset({"erase", "format", "copy", "verify", "eject"})


class UsbDriveWatcher(QObject):
    """The USB drives attached now, re-read whenever that may have changed."""

    drives_changed = pyqtSignal(object)

    def __init__(
        self,
        list_drives: Callable[[], list[UsbDrive]] = list_usb_drives,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._list_drives = list_drives
        self._drives: tuple[UsbDrive, ...] = ()
        self._known = False
        self._active = False
        self._background = BackgroundExecutor(self)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self.refresh)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self.refresh)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _path: self._settle.start())

    @property
    def drives(self) -> tuple[UsbDrive, ...]:
        return self._drives

    @property
    def known(self) -> bool:
        """At least one enumeration has finished."""
        return self._known

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        existing = [path for path in WATCHED_DIRECTORIES if Path(path).is_dir()]
        if existing:
            self._watcher.addPaths(existing)
        self._poll.start()
        self.refresh()

    def stop(self) -> None:
        self._active = False
        self._poll.stop()
        self._settle.stop()
        paths = self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)

    def refresh(self) -> None:
        if not self._active:
            return
        self._background.start("usb-drives", self._list_drives, self._apply)

    def _apply(self, drives: object) -> None:
        current = tuple(drives or ())
        changed = not self._known or current != self._drives
        self._drives = current
        self._known = True
        if changed:
            self.drives_changed.emit(current)


class UsbPreparationJob(QThread):
    """One preparation, off the interface thread."""

    #: step, fraction of that step, detail
    progressed = pyqtSignal(str, float, str)
    succeeded = pyqtSignal(object)
    #: step, message
    failed = pyqtSignal(str, str)
    stopped = pyqtSignal()

    def __init__(
        self,
        preparation: UsbPreparation,
        plan: KitPlan,
        drive: UsbDrive,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._preparation = preparation
        self._plan = plan
        self._drive = drive
        self._cancel = threading.Event()
        self._step = ""
        self._lock = threading.Lock()

    @property
    def step(self) -> str:
        with self._lock:
            return self._step

    @property
    def can_cancel(self) -> bool:
        return self.isRunning() and self.step not in DESTRUCTIVE_STEPS

    def cancel(self) -> None:
        self._cancel.set()

    def _progress(self, step: str, fraction: float, detail: str) -> None:
        with self._lock:
            self._step = step
        self.progressed.emit(step, float(fraction), detail)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            report = self._preparation.run(
                self._plan,
                self._drive,
                progress=self._progress,
                cancelled=self._cancel.is_set,
            )
        except PreparationCancelled:
            self.stopped.emit()
        except PreparationError as error:
            self.failed.emit(error.step, str(error))
        except Exception as error:  # noqa: BLE001 - the thread must report, not die
            self.failed.emit(self.step, str(error))
        else:
            self.succeeded.emit(report)
