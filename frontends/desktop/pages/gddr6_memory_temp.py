from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from bc250cc.shared.failure_text import describe_failure

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import (
    ConfirmDialog,
    ControlPageHeader,
    SectionCard,
    StatusLine,
)
from ..components.responsive import configure_responsive_scroll_area
from ..components.widgets import InfoDialog
from ..core.error_diagnostics import diagnose_error
from ..i18n import tr

GDDR6_SMU_RISK_NOTICE = (
    "This tool is reverse-engineered by its author (pan-Rijovich) and is not fully "
    "verified. Reading temperatures only uses the SMU's normal Queue 3 / Message 5 "
    "path. Applying the runtime patch additionally unlocks a debug gate and writes "
    "directly into SMU memory \u2014 an incorrect SMU/UMC state, DQ mapping, timing or "
    "firmware address could interfere with GDDR6 traffic and cause memory corruption, "
    "instability or crashes. The patch lives in volatile SMU RAM only; a full power "
    "cycle restores the factory behavior."
)


class Gddr6MemoryTempPage(QWidget):
    """Experimental GDDR6 (VRAM) memory-temperature inspection page.

    Wraps the reviewed, upstream bc250-memory-temperature tool. Every
    hardware-touching action runs through the packaged root helper via
    Polkit; this page only builds commands and shows their output.
    """

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.process: QProcess | None = None
        self._last_stderr = ""
        self._background = BackgroundExecutor(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        content = QWidget()
        configure_responsive_scroll_area(scroll, content)
        outer.addWidget(scroll)
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(16)

        self.header = ControlPageHeader(
            "EXPERIMENTAL",
            "GDDR6 memory temperature",
            "Per-chip VRAM temperature via a reverse-engineered SMU/UMC interface.",
        )
        self.header.refresh_requested.connect(self.refresh)
        layout.addWidget(self.header)

        warning = SectionCard(
            "Safety warning",
            icon_name="warning_orange",
            icon_background="orange_soft",
        )
        warning_label = QLabel(tr(GDDR6_SMU_RISK_NOTICE))
        warning_label.setWordWrap(True)
        warning.root.addWidget(warning_label)
        layout.addWidget(warning)

        status_card = SectionCard(
            "Checkout status", icon_name="memory_green", icon_background="blue_soft"
        )
        self.hardware_status = StatusLine("Hardware", "--")
        self.repo_status = StatusLine("Reviewed checkout", "--")
        self.helper_status = StatusLine("Privileged helper", "--")
        for line in (self.hardware_status, self.repo_status, self.helper_status):
            status_card.root.addWidget(line)
        prepare_row = QHBoxLayout()
        self.prepare_button = QPushButton(tr("Prepare / update source"))
        self.prepare_button.clicked.connect(self._prepare)
        prepare_row.addWidget(self.prepare_button)
        prepare_row.addStretch(1)
        status_card.root.addLayout(prepare_row)
        layout.addWidget(status_card)

        actions_card = SectionCard(
            "Actions", icon_name="activity_purple", icon_background="purple_soft"
        )
        buttons_row = QHBoxLayout()
        self.read_button = QPushButton(tr("Read temperatures"))
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self._read)
        self.apply_button = QPushButton(tr("Apply SMU patch"))
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply)
        buttons_row.addWidget(self.read_button)
        buttons_row.addWidget(self.apply_button)
        buttons_row.addStretch(1)
        actions_card.root.addLayout(buttons_row)
        layout.addWidget(actions_card)

        console_card = SectionCard(
            "Output", icon_name="processes_blue", icon_background="blue_soft"
        )
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(220)
        console_card.root.addWidget(self.console)
        layout.addWidget(console_card)
        layout.addStretch(1)

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(2_000)
        self.auto_refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    def set_updates_active(self, active: bool) -> None:
        """Poll checkout/helper status while this page is visible.

        Preparing the source runs in a separate embedded-terminal workflow;
        this page has no direct signal for when that finishes, so it polls
        like the Drivers page does instead of showing a stale status.
        """
        if active:
            self.refresh()
            self.auto_refresh_timer.start()
        else:
            self.auto_refresh_timer.stop()

    # ------------------------------------------------------------ status

    def refresh(self) -> None:
        def success(status: object) -> None:
            self._apply_status(dict(status or {}))

        def failure(_message: str) -> None:
            self._apply_status({})

        self._background.start(
            "gddr6-status", self.controller.estado_gddr6_memory_temp, success, failure
        )

    def _apply_status(self, status: dict) -> None:
        self.hardware_status.set_values(
            "Detected" if status.get("hardware_detected") else "Not detected"
        )
        self.repo_status.set_values(
            "Ready" if status.get("repository_ready") else "Not prepared",
            str(status.get("repository_path", "")),
        )
        self.helper_status.set_values(
            "Installed" if status.get("helper_ready") else "Not installed"
        )
        ready = bool(status.get("repository_ready") and status.get("helper_ready"))
        self.read_button.setEnabled(ready)
        self.apply_button.setEnabled(ready and bool(status.get("payload_present")))

    # ------------------------------------------------------------ actions

    def _prepare(self) -> None:
        try:
            self.controller.comando_preparar_gddr6_memory_temp()
        except Exception as error:  # noqa: BLE001 - surfaced to the user, not swallowed
            self._show_info("Could not start preparation", str(error), tone="red")

    def _read(self) -> None:
        self._start_operation(
            self.controller.comando_leer_temperatura_vram, "Read GDDR6 temperatures"
        )

    def _apply(self) -> None:
        dialog = ConfirmDialog(
            "Apply SMU patch",
            GDDR6_SMU_RISK_NOTICE,
            summary=(
                ("Upstream", "pan-Rijovich/bc250-memory-temperature"),
                ("Persistence", "Volatile SMU RAM only — cleared on power cycle"),
                ("Risk", "Reverse-engineered; not fully verified by its own author"),
            ),
            confirm_text="Apply at my own risk",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_operation(self.controller.comando_aplicar_parche_vram, "Apply SMU patch")

    def _start_operation(self, operation, label: str) -> None:
        self.read_button.setEnabled(False)
        self.apply_button.setEnabled(False)

        def success(payload: object) -> None:
            command = list(payload or [])
            if not command:
                self._finish_operation()
                self._show_info(
                    "Could not start", "The controller returned an empty command.", tone="red"
                )
                return
            self._run_process(command, label)

        def failure(message: str) -> None:
            self._finish_operation()
            self._show_info("Could not start", message, tone="red")

        if not self._background.start("gddr6-command", operation, success, failure):
            self._show_info(
                "Operation in progress", "Wait for the current action to finish.", tone="orange"
            )

    def _run_process(self, command: list[str], label: str) -> None:
        self.process = QProcess(self)
        self._last_stderr = ""
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        stamp = datetime.now().strftime("%H:%M:%S")
        self.console.appendPlainText(f"\n[{stamp}] {tr(label)}")
        self.process.start(command[0], command[1:])

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.console.moveCursor(QTextCursor.MoveOperation.End)
            self.console.insertPlainText(data)
            self.console.ensureCursorVisible()

    def _read_stderr(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self._last_stderr = (self._last_stderr + data)[-4000:]
            self.console.appendPlainText(data.rstrip())

    def _process_error(self, _error) -> None:
        self._finish_operation()

    def _process_finished(self, exit_code: int, _status) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        if exit_code == 0:
            self.console.appendPlainText(f"[{stamp}] " + tr("Completed"))
        else:
            diagnosis = diagnose_error(
                describe_failure(exit_code, "", self._last_stderr),
                context="GDDR6 memory temperature",
            )
            self.console.appendPlainText(f"[{stamp}] " + tr(diagnosis.summary))
            self.console.appendPlainText(tr("How to fix it") + ": " + tr(diagnosis.action))
        self._finish_operation()
        self.refresh()

    def _finish_operation(self) -> None:
        self.read_button.setEnabled(True)
        self.apply_button.setEnabled(True)

    def _show_info(self, title: str, message: str, *, tone: str = "blue") -> None:
        icon_name = "info_blue" if tone == "blue" else f"warning_{tone}"
        InfoDialog(tr(title), tr(message), icon_name, self, tone=tone).exec()

    def retranslate_dynamic_copy(self) -> None:
        """No dynamic copy beyond static widget text and live status labels."""
        return None
