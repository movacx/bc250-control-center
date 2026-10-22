"""The problem report form, answered inside the app.

The same questions as the maintainer's Google Form, already filled with what
the app knows (version, distribution, installation, the diagnostic report),
sent with one press. Opened from the dashboard footer, from Settings ›
Diagnostics and from every red error window, which passes its code along.
"""

from __future__ import annotations

import re
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.system.feedback import form
from bc250cc.shared.error_origins import redact
from bc250cc.shared.version import application_version

from ..core.diagnostic_history import (
    diagnostic_report,
    history_entries,
    recent_errors_text,
    record_diagnosis,
    system_sheet_text,
)
from ..core.error_diagnostics import diagnose_error
from ..core.external_links import open_external_url
from ..i18n import current_language, localize_widget_tree, tr, tr_format
from ..theme import COLORS, application_stylesheet
from .async_tools import BackgroundExecutor
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .wheel_guard import GuardedComboBox
from .widgets import IconBadge, dialog_card, dialog_header

#: Shown in a choice box before anything is picked; never sent.
UNANSWERED = "Choose…"


def _read_report() -> dict[str, object]:
    """Everything the automatic report carries, read off the UI thread.

    Every read fails to a blank rather than raising: a system without one of
    the files still sends the rest.
    """
    from bc250cc.application.system.feedback import (
        collect_diagnostics,
        os_release,
        system_snapshot,
    )

    rows = system_snapshot()
    facts = dict(rows)
    cores = 0
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            cores = len({
                line.split(":", 1)[1].strip()
                for line in handle if line.startswith("core id")
            })
    except OSError:
        pass
    entries = history_entries()
    return {
        "report": diagnostic_report(rows, entries),
        "specs": system_sheet_text(rows),
        "recent": recent_errors_text(entries),
        "hardware": collect_diagnostics(),
        "session": str(facts.get("Session", "")),
        "version": str(facts.get("Control Center", "")),
        "install": form.suggested_install(str(facts.get("Installation", ""))),
        "distribution": form.suggested_distribution(os_release()),
        "cores": form.suggested_cores(cores),
    }


class _Choice(GuardedComboBox):
    """A form choice: the English label is the data, the text is translated."""

    def __init__(self, choices: tuple[str, ...], *, editable: bool = False):
        super().__init__()
        self.setEditable(editable)
        # Sized by the form's columns, not by the longest choice: a translated
        # "CPU (frequencies, profiles, core unlock)" pushed the right column
        # past the edge of the dialog.
        self.setSizeAdjustPolicy(GuardedComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
        self.addItem(tr(UNANSWERED), "")
        for label in choices:
            self.addItem(tr(label), label)
        if editable and self.lineEdit() is not None:
            self.lineEdit().setPlaceholderText(tr(UNANSWERED))
            self.setCurrentIndex(-1)

    def value(self) -> str:
        if self.isEditable():
            text = self.currentText().strip()
            index = self.findText(text)
            return str(self.itemData(index) or "") if index >= 0 else text
        return str(self.currentData() or "")

    def set_value(self, label: str) -> None:
        index = self.findData(label)
        if index >= 0:
            self.setCurrentIndex(index)
        elif self.isEditable() and label:
            self.setEditText(label)


class _Checks(QWidget):
    def __init__(self, choices: tuple[str, ...], columns: int = 2):
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        self.boxes: list[tuple[str, QCheckBox]] = []
        for index, label in enumerate(choices):
            box = QCheckBox(tr(label))
            box.setProperty("feedbackCheck", True)
            grid.addWidget(box, index // columns, index % columns)
            self.boxes.append((label, box))
        for column in range(columns):
            grid.setColumnStretch(column, 1)

    def values(self) -> list[str]:
        return [label for label, box in self.boxes if box.isChecked()]

    def check(self, label: str) -> None:
        for name, box in self.boxes:
            if name == label:
                box.setChecked(True)


def _field(label: str, widget: QWidget, *, hint: str = "", required: bool = False) -> QWidget:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(5)
    title = QLabel(tr(label) + (" *" if required else ""))
    title.setProperty("feedbackLabel", True)
    column.addWidget(title)
    if hint:
        note = QLabel(tr(hint))
        note.setProperty("feedbackHint", True)
        note.setWordWrap(True)
        column.addWidget(note)
    column.addWidget(widget)
    return holder


def _text_box(placeholder: str, height: int) -> QPlainTextEdit:
    box = QPlainTextEdit()
    box.setProperty("feedbackText", True)
    box.setPlaceholderText(tr(placeholder))
    box.setTabChangesFocus(True)
    box.setFixedHeight(height)
    return box


def _line(placeholder: str = "") -> QLineEdit:
    line = QLineEdit()
    line.setPlaceholderText(tr(placeholder))
    line.setMaxLength(form.MAX_SHORT_TEXT)
    return line


def _row(*widgets: QWidget) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(14)
    for widget in widgets:
        row.addWidget(widget, 1)
    return holder


def _group(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("feedbackGroup", True)
    column = QVBoxLayout(frame)
    column.setContentsMargins(16, 14, 16, 16)
    column.setSpacing(12)
    heading = QLabel(tr(title))
    heading.setProperty("feedbackGroupTitle", True)
    column.addWidget(heading)
    return frame, column


def _breakable(text: str) -> str:
    """Let long paths and function names wrap.

    An origin such as ``gpu_governor_state.py:1053 · ...report_failure`` has no
    space to break at, so the label claimed its whole width and pushed the
    form under the scroll bar. A zero-width space after each separator gives
    Qt a place to wrap without changing what is shown.
    """
    return re.sub(r"([._/:<>])", "\\1\u200b", str(text))


def _scrolled(page: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("DialogContentScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
    scroll.setWidget(page)
    return scroll


class FeedbackDialog(QDialog):
    """Report a problem or send an idea, without leaving the app."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        idea: bool = False,
        code: str = "",
        summary: str = "",
        context: str = "",
        area_hint: str = "",
        terminal: str = "",
        reference: str = "",
        where: str = "",
        raw: str = "",
        opened_from: str = "",
        read_report=_read_report,
        submit=form.submit,
    ):
        super().__init__(parent)
        self._submit = submit
        self._diagnostics = ""
        self._facts: dict[str, object] = {}
        # From the error window that opened the form, when one did.
        self._reference = reference.strip()
        self._where = where.strip()
        self._raw = raw.strip()
        self._opened_from = opened_from or ("Error window" if reference else "Report button")
        self._executor = BackgroundExecutor(self)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(tr("Report a problem or suggest an idea"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        enable_adaptive_dialog(self, preferred_width=680, preferred_height=760, minimum_width=420, minimum_height=420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = dialog_card(self)
        card.setProperty("feedbackForm", True)
        outer.addWidget(card)

        frame = QVBoxLayout(card)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        frame.addWidget(dialog_header(
            self,
            tr("Report a problem or suggest an idea"),
            tr("Goes to the developer's Google Form. Only the developer sees it."),
            "report_amber",
            COLORS["orange_soft"],
        ))
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(22, 16, 22, 14)
        layout.setSpacing(14)
        frame.addWidget(body, 1)

        self.kind_problem = QPushButton(tr("Report a problem"))
        self.kind_idea = QPushButton(tr("Suggest an idea"))
        kinds = QHBoxLayout()
        kinds.setSpacing(0)
        self._kinds = QButtonGroup(self)
        for position, button in (("first", self.kind_problem), ("last", self.kind_idea)):
            button.setCheckable(True)
            button.setProperty("feedbackKind", position)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._kinds.addButton(button)
            kinds.addWidget(button, 1)
        layout.addLayout(kinds)

        # Each form scrolls on its own: in one shared scroll area the short
        # idea page took the height of the long problem page.
        self.pages = QStackedWidget()
        self.scroll = _scrolled(self._problem_page())
        self.pages.addWidget(self.scroll)
        self.pages.addWidget(_scrolled(self._idea_page()))
        self.pages.addWidget(self._sent_page())
        layout.addWidget(self.pages, 1)

        self.status = QLabel()
        self.status.setProperty("feedbackStatus", "info")
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)
        frame.addWidget(self._footer())

        self.kind_problem.toggled.connect(self._kind_changed)
        (self.kind_idea if idea else self.kind_problem).setChecked(True)
        self._kind_changed()
        self._prefill(code=code, summary=summary, context=context, area_hint=area_hint, terminal=terminal)
        self._show_captured()
        localize_widget_tree(self)
        # Sending waits for the automatic report: a quick press used to post
        # it with no specifications and no recent errors.
        self._reading = True
        self.send_button.setEnabled(False)
        self.send_button.setToolTip(tr("Still reading this system…"))
        self._executor.start("report", read_report, self._report_ready, lambda _message: self._report_ready({}))

    # --- Layout -------------------------------------------------------------------

    def _problem_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 14, 0)
        column.setSpacing(14)

        self.summary = _line('Example: "GPU governor stops after a few seconds"')
        column.addWidget(_field("What went wrong?", self.summary, required=True))
        self.area = _Choice(form.AREAS, editable=True)
        self.code = _line("BC250-…")
        column.addWidget(_row(_field("Which part of the app?", self.area), _field("Error code", self.code)))
        self.frequency = _Choice(form.FREQUENCIES)
        self.worked_before = _Choice(form.WORKED_BEFORE)
        column.addWidget(_row(
            _field("How often does it happen?", self.frequency),
            _field("Did it work before?", self.worked_before),
        ))
        self.seen = _Checks(form.SEEN, columns=1)
        column.addWidget(_field("What did you see?", self.seen))
        self.steps = _text_box("1. Open …  2. Press …  3. …", 84)
        column.addWidget(_field("Steps to reproduce", self.steps))

        system, rows = _group("Your system")
        note = QLabel(tr("Filled in from this system. Change anything that is wrong."))
        note.setProperty("feedbackHint", True)
        note.setWordWrap(True)
        rows.addWidget(note)
        self.distribution = _Choice(form.DISTRIBUTIONS, editable=True)
        self.version = _line()
        rows.addWidget(_row(_field("Distribution", self.distribution), _field("Control Center version", self.version)))
        self.install = _Choice(form.INSTALLS)
        self.bios = _Choice(form.BIOSES)
        rows.addWidget(_row(_field("How did you install it?", self.install), _field("BIOS", self.bios)))
        self.cores = _Choice(form.CORES)
        self.cus = _Choice(form.CUS)
        rows.addWidget(_row(_field("CPU cores", self.cores), _field("GPU compute units", self.cus)))
        self.other_tools = _Checks(form.OTHER_TOOLS, columns=1)
        rows.addWidget(_field("Other BC-250 tools you used on this system", self.other_tools))
        column.addWidget(system)

        logs, rows = _group("Logs")
        self.terminal = _text_box("Paste terminal output here, if there is any.", 84)
        rows.addWidget(_field("Terminal output", self.terminal))
        self.media = _line("https://…")
        rows.addWidget(_field("Screenshot or video link", self.media))
        column.addWidget(logs)

        # What the app captured by itself: shown, never typed, and one click
        # away from the exact text that leaves the machine.
        automatic, rows = _group("Automatic report")
        note = QLabel(tr("Captured by Control Center. Nothing here needs to be written by you."))
        note.setProperty("feedbackHint", True)
        note.setWordWrap(True)
        rows.addWidget(note)
        self.captured = QFrame()
        self.captured.setObjectName("DialogIdentity")
        self._captured_grid = QGridLayout(self.captured)
        self._captured_grid.setContentsMargins(14, 11, 14, 11)
        self._captured_grid.setHorizontalSpacing(16)
        self._captured_grid.setVerticalSpacing(6)
        self._captured_grid.setColumnStretch(1, 1)
        rows.addWidget(self.captured)
        attach = QHBoxLayout()
        attach.setSpacing(10)
        self.attach = QCheckBox(tr("Send the automatic report"))
        self.attach.setProperty("feedbackCheck", True)
        self.attach.setChecked(True)
        self.attach.setToolTip(tr("The error, where it happened, this system's specifications and the recent errors."))
        self.preview = QPushButton(tr("See what is sent"))
        self.preview.setProperty("dialogLink", True)
        self.preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview.clicked.connect(self._show_report)
        attach.addWidget(self.attach)
        attach.addWidget(self.preview)
        attach.addStretch(1)
        rows.addLayout(attach)
        column.addWidget(automatic)

        self.problem_contact = _line("@name")
        self.problem_ideas = _text_box("Anything else you would like to add.", 64)
        contact, rows = _group("Contact and ideas")
        rows.addWidget(_field(
            "Telegram or Discord username", self.problem_contact,
            hint="Optional. Only if you want an answer.",
        ))
        rows.addWidget(_field("Suggestions and ideas", self.problem_ideas))
        column.addWidget(contact)
        column.addStretch(1)
        return page

    def _idea_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 14, 0)
        column.setSpacing(14)
        self.ideas = _text_box("What would make Control Center better for you?", 180)
        column.addWidget(_field("Suggestions and ideas", self.ideas, required=True))
        self.idea_contact = _line("@name")
        column.addWidget(_field(
            "Telegram or Discord username", self.idea_contact,
            hint="Optional. Only if you want an answer.",
        ))
        column.addStretch(1)
        return page

    def _sent_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(24, 0, 24, 0)
        column.setSpacing(10)
        column.addStretch(1)
        column.addWidget(IconBadge("check_green", COLORS["green_soft"], 52), 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel(tr("Thanks, it was sent"))
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body = QLabel(tr("The developer reads every report. If you left a username, the answer arrives there."))
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(title)
        column.addWidget(body)
        column.addStretch(2)
        return page

    def _footer(self) -> QFrame:
        footer_frame = QFrame()
        footer_frame.setObjectName("DialogFooter")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(22, 12, 22, 12)
        footer.setSpacing(8)
        footer.addStretch(1)
        self.browser_button = QPushButton(tr("Open in the browser"))
        self.browser_button.setObjectName("DialogSecondary")
        self.browser_button.clicked.connect(self._open_in_browser)
        self.browser_button.hide()
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setObjectName("DialogSecondary")
        self.cancel_button.setProperty("gamepadCancel", True)
        self.cancel_button.clicked.connect(self.reject)
        self.send_button = QPushButton(tr("Send"))
        self.send_button.setObjectName("DialogPrimary")
        self.send_button.setMinimumWidth(96)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._send)
        for button in (self.browser_button, self.cancel_button, self.send_button):
            footer.addWidget(button)
        return footer_frame

    # --- Behaviour ----------------------------------------------------------------

    def _prefill(self, *, code: str, summary: str, context: str, area_hint: str = "", terminal: str = "") -> None:
        self.version.setText(application_version())
        if code:
            self.code.setText(code)
            self.seen.check(form.SEEN[0])
        if summary:
            self.summary.setText(summary)
        # The section the error came from is exact; the window's words a guess.
        area = form.AREA_BY_SECTION.get(area_hint) or form.suggested_area(context)
        if area:
            self.area.set_value(area)
        if terminal:
            self.terminal.setPlainText(terminal)

    def _report_ready(self, facts: object) -> None:
        facts = facts if isinstance(facts, dict) else {}
        self._facts = facts
        self._reading = False
        if self.send_button.text() == tr("Send"):
            self.send_button.setEnabled(True)
            self.send_button.setToolTip("")
        self._diagnostics = str(facts.get("report") or "")
        if not self.version.text():
            self.version.setText(str(facts.get("version") or ""))
        for choice, key in ((self.install, "install"), (self.cores, "cores"), (self.distribution, "distribution")):
            if not choice.value() and facts.get(key):
                choice.set_value(str(facts[key]))
        self._show_captured()

    def _kind_changed(self, *_args) -> None:
        if self.pages.currentIndex() == 2:
            return
        self.pages.setCurrentIndex(0 if self.kind_problem.isChecked() else 1)
        self._set_status("")

    def report(self) -> form.FeedbackReport:
        if not self.kind_problem.isChecked():
            return form.FeedbackReport(
                kind=form.KIND_IDEA,
                ideas=self.ideas.toPlainText(),
                contact=self.idea_contact.text(),
            )
        return form.FeedbackReport(
            kind=form.KIND_PROBLEM,
            summary=self.summary.text(),
            # The pasted-report field is for the browser; the app fills the
            # automatic page, one answer per column.
            diagnostics="",
            area=self.area.value(),
            seen=self.seen.values(),
            code=self.code.text(),
            frequency=self.frequency.value(),
            worked_before=self.worked_before.value(),
            steps=self.steps.toPlainText(),
            distribution=self.distribution.value(),
            version=self.version.text(),
            install=self.install.value(),
            bios=self.bios.value(),
            cores=self.cores.value(),
            cus=self.cus.value(),
            other_tools=self.other_tools.values(),
            terminal=self.terminal.toPlainText(),
            media=self.media.text(),
            contact=self.problem_contact.text(),
            ideas=self.problem_ideas.toPlainText(),
            **self._automatic(),
        )

    def _automatic(self) -> dict[str, str]:
        """The "Automatic report" answers, or none when the owner unticked it."""
        if not self.attach.isChecked():
            return {}
        values = {
            "reference": self._reference,
            "where": self._where,
            "raw": self._raw,
            "specs": str(self._facts.get("specs") or ""),
            "recent_errors": str(self._facts.get("recent") or ""),
            "details": self._details(),
            "hardware": str(self._facts.get("hardware") or ""),
        }
        # The preview shows exactly what is sent: home folders already ~.
        return {key: redact(value) for key, value in values.items()}

    def _details(self) -> str:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        version = str(self._facts.get("version") or application_version())
        lines = [
            f"Sent from: Control Center {version}, in-app form",
            f"Opened from: {self._opened_from}",
            f"Interface language: {current_language()}",
            f"Session: {self._facts.get('session') or '—'}",
            f"Sent at: {stamp}",
        ]
        return "\n".join(lines)

    def _show_captured(self) -> None:
        rows = []
        if self._reference:
            rows.append(("Error reference", self._reference))
        for line in self._where.splitlines():
            label, _, value = line.partition(": ")
            rows.append((label, value or line))
        if self._raw:
            rows.append(("Raw error", self._raw.strip().splitlines()[-1]))
        rows.append(("System specifications", tr("Included") if self._facts.get("specs") else "…"))
        rows.append(("Hardware diagnostics", tr("Included") if self._facts.get("hardware") else "…"))
        recent = str(self._facts.get("recent") or "")
        count = sum(1 for line in recent.splitlines() if line and not line.startswith(" "))
        if not self._facts:
            rows.append(("Recent errors", "…"))
        elif recent and recent != "None recorded.":
            rows.append(("Recent errors", str(count)))
        else:
            rows.append(("Recent errors", tr("None recorded")))
        grid = self._captured_grid
        while grid.count():
            item = grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for row, (label, value) in enumerate(rows):
            name = QLabel(tr(label))
            name.setObjectName("DialogIdentityLabel")
            data = QLabel(_breakable(value))
            data.setObjectName("DialogIdentityValue")
            data.setWordWrap(True)
            data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(data, row, 1)

    def _set_status(self, text: str, tone: str = "info") -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))
        self.status.setProperty("feedbackStatus", tone)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _send(self) -> None:
        report = self.report()
        missing = report.missing()
        if missing:
            self._set_status(tr_format("Answer this first: {question}", question=tr(missing)), "warning")
            (self.summary if report.is_problem else self.ideas).setFocus()
            return
        self.send_button.setEnabled(False)
        self.send_button.setText(tr("Sending…"))
        self._sending = True
        self.cancel_button.setEnabled(False)
        self.browser_button.hide()
        self._set_status("")
        self._executor.start(
            "send",
            lambda: self._submit(report),
            lambda _result: self._sent(),
            self._failed,
        )

    def reject(self) -> None:  # noqa: D401 - Qt API
        # A report on its way cannot be called back: closing would only hide
        # that it was still sent.
        if getattr(self, "_sending", False):
            return
        super().reject()

    def _sent(self) -> None:
        self._sending = False
        self.pages.setCurrentIndex(2)
        for widget in (self.kind_problem, self.kind_idea, self.cancel_button, self.browser_button):
            widget.hide()
        self.send_button.setEnabled(True)
        self.send_button.setText(tr("Close"))
        self.send_button.clicked.disconnect()
        self.send_button.clicked.connect(self.accept)
        self._set_status("")

    def _failed(self, message: str) -> None:
        # Kept in Settings › Diagnostics like any other failure, with its code.
        record_diagnosis(diagnose_error(message), source="window", title="Report form", detail=message)
        self._sending = False
        self.cancel_button.setEnabled(True)
        self.send_button.setEnabled(True)
        self.send_button.setText(tr("Send"))
        self._set_status(
            tr_format("It was not sent: {reason}. What you wrote is still here.", reason=tr(message).rstrip(".")),
            "error",
        )
        self.browser_button.show()

    def _open_in_browser(self) -> None:
        """The same answers in the browser; long texts go to the clipboard."""
        report = self.report()
        long_texts = [
            (tr("Suggestions and ideas"), report.ideas),
            (tr("Steps to reproduce"), report.steps),
            (tr("Terminal output"), report.terminal),
            (tr("Where it happened"), report.where),
            (tr("Raw error"), report.raw),
            (tr("System specifications"), report.specs),
            (tr("Recent errors"), report.recent_errors),
            (tr("Report details"), report.details),
            (tr("Hardware diagnostics"), report.hardware),
        ]
        # The same rule as the POST: no home folder leaves through the clipboard either.
        clipboard = "\n\n".join(
            f"== {title} ==\n{redact(text).strip()}" for title, text in long_texts if text.strip()
        )
        if clipboard and QApplication.clipboard() is not None:
            QApplication.clipboard().setText(clipboard)
        opened, _message = open_external_url(form.prefill_url(report))
        if not opened:
            self._set_status(tr_format("Copy this address manually: {url}", url=form.FORM_URL), "error")
            return
        if clipboard:
            self._set_status(tr("The long answers were copied. Paste them into the form in the browser."), "info")

    def preview_text(self) -> str:
        """Exactly what the automatic page sends, under the form's own headings."""
        values = self._automatic() or {
            key: "" for key in ("reference", "where", "raw", "specs", "recent_errors", "details", "hardware")
        }
        sections = (
            ("Error reference", values["reference"]),
            ("Where it happened", values["where"]),
            ("Raw error", values["raw"]),
            ("System specifications", values["specs"]),
            ("Recent errors", values["recent_errors"]),
            ("Report details", values["details"]),
            ("Hardware diagnostics", values["hardware"]),
        )
        return "\n\n".join(f"== {title} ==\n{text or '—'}" for title, text in sections) + "\n"

    def _show_report(self) -> None:
        from ..pages.settings import TextDetailsDialog

        TextDetailsDialog("See what is sent", self.preview_text(), self).exec()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        center_dialog(self)


def open_feedback(parent: QWidget | None = None, **kwargs) -> int:
    return FeedbackDialog(parent, **kwargs).exec()
