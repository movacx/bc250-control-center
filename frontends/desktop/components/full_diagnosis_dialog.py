"""The full diagnosis, readable inside the application.

A problem report attaches the whole diagnosis: kernel, previous boot, black
box, sensors, GPU, services, configuration, packages, logs. Until now it could
only be read on the report service's admin page, after sending it, or from the
terminal. This window shows the very same sections (the ones a report would
carry, with the machine's name, user, addresses and ids already hidden), each one
expandable, sorted into tabs, searchable, and copyable or savable as a file.

Collecting it reads journals and may ask for the password once, to read a
kernel log the system keeps private; it runs in the background.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import COLORS, application_stylesheet, scale_stylesheet
from .async_tools import BackgroundExecutor
from .buttons import WrappingButton as QPushButton
from .dialogs import enable_adaptive_dialog
from .toast import show_toast
from ..i18n import tr, tr_format

#: (key, label) of the tabs, in order. "all" shows every section.
TABS = (("all", "All"), ("hardware", "Hardware"), ("system", "System"), ("logs", "Logs"))
#: Sections about the board itself, as the report's hardware diagnosis names them.
HARDWARE_TITLES = frozenset({
    "kernel", "previous boot", "black box", "modules", "sensors (hwmon)", "sensors", "gpu", "gpu device",
    "graphics stack", "system setup helper", "steamos", "services",
})


def section_group(title: str) -> str:
    """Which tab a section belongs to: logs, hardware, or the rest of the system."""
    lowered = str(title).lower()
    if "log" in lowered or "journal" in lowered:
        return "logs"
    return "hardware" if lowered in HARDWARE_TITLES else "system"


def size_kb(text: str) -> int:
    return max(1, round(len(text) / 1024))


def as_text(sections: list[tuple[str, str]]) -> str:
    """The whole diagnosis as one plain-text document, the way a report reads."""
    return "\n\n".join(f"== {title} ==\n{body}" for title, body in sections)


def _stylesheet() -> str:
    c = COLORS
    return scale_stylesheet(f"""
QWidget[fullDiagnosis='true'] QLabel[diagHeading='true'] {{
    color: {c['muted']}; font-size: 11px; font-weight: 800; letter-spacing: 1px;
}}
QWidget[fullDiagnosis='true'] QLabel[diagIntro='true'] {{ color: {c['muted']}; font-size: 11px; }}
QWidget[fullDiagnosis='true'] QFrame[diagSection='true'] {{
    background: transparent; border: none; border-bottom: 1px solid {c['border_soft']};
}}
QWidget[fullDiagnosis='true'] QPushButton[diagToggle='true'] {{
    background: transparent; border: none; border-radius: 0px; min-height: 0px;
    padding: 9px 2px; text-align: left; color: {c['text']}; font-size: 12px; font-weight: 700;
}}
QWidget[fullDiagnosis='true'] QPushButton[diagToggle='true']:hover {{ color: {c['blue']}; }}
QWidget[fullDiagnosis='true'] QPushButton[diagTab='true'] {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0px; min-height: 0px; padding: 7px 2px 6px 2px;
    color: {c['muted']}; font-size: 12px; font-weight: 700;
}}
QWidget[fullDiagnosis='true'] QPushButton[diagTab='true']:hover {{ color: {c['text']}; }}
QWidget[fullDiagnosis='true'] QPushButton[diagTab='true']:checked {{
    color: {c['text']}; border-bottom: 2px solid {c['blue']};
}}
QWidget[fullDiagnosis='true'] QPushButton[diagButton='true'] {{
    background: transparent; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 8px; min-height: 0px; padding: 6px 14px; font-size: 11px; font-weight: 650;
}}
QWidget[fullDiagnosis='true'] QPushButton[diagButton='true']:hover {{
    background: {c['control_hover']}; border-color: {c['border_strong']};
}}
QWidget[fullDiagnosis='true'] QPushButton[diagButton='true']:disabled {{
    color: {c['disabled_text']}; border-color: {c['border_soft']}; background: transparent;
}}
QWidget[fullDiagnosis='true'] QLineEdit[diagSearch='true'] {{
    min-height: 30px; background: transparent; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 0 11px; font-size: 11px;
    selection-background-color: {c['blue']}; selection-color: {c['on_accent']};
}}
QWidget[fullDiagnosis='true'] QLineEdit[diagSearch='true']:focus {{ border-color: {c['blue']}; }}
QWidget[fullDiagnosis='true'] QScrollBar:vertical {{ background: transparent; border: none; width: 10px; margin: 0; }}
QWidget[fullDiagnosis='true'] QScrollBar::handle:vertical {{
    background: {c['border_strong']}; border-radius: 4px; min-height: 28px; margin: 1px;
}}
QWidget[fullDiagnosis='true'] QScrollBar::add-line:vertical,
QWidget[fullDiagnosis='true'] QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: none; }}
QWidget[fullDiagnosis='true'] QScrollBar::add-page:vertical,
QWidget[fullDiagnosis='true'] QScrollBar::sub-page:vertical {{ background: transparent; }}
QWidget[fullDiagnosis='true'] QPlainTextEdit[diagBody='true'] {{
    background: {c['control']}; color: {c['text']}; border: 1px solid {c['border_soft']};
    border-radius: 8px; padding: 6px 8px; font-size: 11px;
}}
""")


#: A section's text box starts at DEFAULT_HEIGHT and can be dragged between these.
DEFAULT_HEIGHT = 220
MIN_HEIGHT = 90
MAX_HEIGHT = 3000


class ResizeGrip(QFrame):
    """A bar under a text box: drag it down to make the box taller, up to shorten it.

    Double-click fits the box to its text (and back). It reports where the
    mouse is relative to where it was pressed; the section decides the height.
    """

    pressed = pyqtSignal()
    dragged = pyqtSignal(int)
    double_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("diagGrip", True)
        self.setFixedHeight(14)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip(tr("Drag to resize. Double-click to fit the text."))
        self._press_y = 0

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_y = round(event.globalPosition().y())
            self.pressed.emit()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.dragged.emit(round(event.globalPosition().y()) - self._press_y)
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["muted"]))
        centre_x, centre_y = self.width() // 2, self.height() // 2
        for offset in (-10, 0, 10):
            painter.drawEllipse(centre_x + offset - 2, centre_y - 1, 4, 4)


class _StatusLine(QLabel):
    """A line that exists only while it says something, so an empty one leaves no gap."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("", parent)
        self.setProperty("diagIntro", True)
        self.setWordWrap(True)
        self.hide()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(text)
        self.setVisible(bool(text))


class DiagnosisSection(QFrame):
    """One section: its title and size, and its text when opened."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title, self.text, self.group = title, text, section_group(title)
        self.setProperty("diagSection", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toggle = QPushButton("")
        self.toggle.setProperty("diagToggle", True)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self.set_open)
        layout.addWidget(self.toggle)
        self.body = QPlainTextEdit(text)
        self.body.setProperty("diagBody", True)
        self.body.setReadOnly(True)
        self.body.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body.setFixedHeight(DEFAULT_HEIGHT)
        self.body.hide()
        layout.addWidget(self.body)
        self.grip = ResizeGrip()
        self.grip.hide()
        self._start_height = DEFAULT_HEIGHT
        self.grip.pressed.connect(lambda: setattr(self, "_start_height", self.body.height()))
        self.grip.dragged.connect(lambda delta: self.set_body_height(self._start_height + delta))
        self.grip.double_clicked.connect(self.toggle_fit)
        layout.addWidget(self.grip)
        layout.addSpacing(4)
        self._relabel()

    def set_body_height(self, height: int) -> None:
        self.body.setFixedHeight(max(MIN_HEIGHT, min(MAX_HEIGHT, int(height))))

    def fit_height(self) -> int:
        """The height that shows the whole text without scrolling."""
        lines = max(1, self.body.document().blockCount())
        chrome = 2 * self.body.frameWidth() + 2 * round(self.body.document().documentMargin()) + 16
        return max(MIN_HEIGHT, min(MAX_HEIGHT, lines * self.body.fontMetrics().lineSpacing() + chrome))

    def toggle_fit(self) -> None:
        """Fit the box to its text; again, back to the usual height."""
        fit = self.fit_height()
        self.set_body_height(DEFAULT_HEIGHT if abs(self.body.height() - fit) <= 2 else fit)

    def _relabel(self) -> None:
        arrow = "▼" if self.body.isVisible() or self.toggle.isChecked() else "▶"
        # The report names its sections in English: the same words here and on the maintainer's page.
        self.toggle.setText(f"{arrow} {self.title} ({size_kb(self.text)} KB)")

    def set_open(self, opened: bool) -> None:
        self.body.setVisible(bool(opened))
        self.grip.setVisible(bool(opened))
        if self.toggle.isChecked() != bool(opened):
            self.toggle.setChecked(bool(opened))
        self._relabel()

    def matches(self, query: str) -> bool:
        query = query.strip().lower()
        return not query or query in self.title.lower() or query in self.text.lower()


class FullDiagnosisView(QWidget):
    """Every section of the diagnosis a report carries, readable in place.

    A widget, not a window: Settings puts it in a dialog and the Black box page
    puts it where the recording's table is.
    """

    def __init__(self, parent: QWidget | None = None, *, collect: Callable[[], list[tuple[str, str]]]):
        super().__init__(parent)
        self._collect = collect
        self._background = BackgroundExecutor(self)
        self._sections: list[DiagnosisSection] = []
        self._tab = "all"
        self.setProperty("fullDiagnosis", True)
        self.setStyleSheet(_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # No title and no explanation line: the window or the button already names it. What they
        # said (how many sections, what is hidden) is the search box's tooltip.
        self.summary = ""

        tabs = QHBoxLayout()
        tabs.setSpacing(18)
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, label in TABS:
            button = QPushButton(tr(label))
            button.setProperty("diagTab", True)
            button.setCheckable(True)
            button.setChecked(key == self._tab)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, tab=key: self._select_tab(tab))
            tabs.addWidget(button)
            self.tab_buttons[key] = button
        tabs.addStretch(1)
        layout.addLayout(tabs)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search the diagnosis"))
        self.search.setAccessibleName(tr("Search the diagnosis"))
        self.search.setProperty("diagSearch", True)
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(self._explanation())
        self.search.textChanged.connect(self._apply_filter)
        tools.addWidget(self.search, 1)
        self.expand_button = self._button("Expand all", lambda: self._expand(True))
        self.collapse_button = self._button("Collapse all", lambda: self._expand(False))
        tools.addWidget(self.expand_button)
        tools.addWidget(self.collapse_button)
        layout.addLayout(tools)

        self.status = _StatusLine()
        layout.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.scroll.setMinimumHeight(160)
        self.holder = QWidget()
        self.sections_layout = QVBoxLayout(self.holder)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(0)
        self.sections_layout.addStretch(1)
        self.scroll.setWidget(self.holder)
        layout.addWidget(self.scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.refresh_button = self._button("Refresh", self.load)
        self.copy_button = self._button("Copy all", self._copy_all)
        self.save_button = self._button("Save as file…", self._save)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        self.actions = actions
        layout.addLayout(actions)
        self._set_ready(False)
        self.load()

    def apply_appearance(self) -> None:
        """Colours again after a light/dark or accent switch: the sheet holds them as text."""
        self.setStyleSheet(_stylesheet())
        for section in self._sections:
            section.grip.update()

    # -- construction --------------------------------------------------------

    def _explanation(self) -> str:
        said = tr(
            "This is what a problem report attaches, with your device name, user name, IP and MAC address hidden. "
            "Reading the kernel log may ask for your password once."
        )
        # Redaction cannot know everything about its owner: say so, where it will be read.
        warning = tr(
            "Serial numbers, disk and machine ids, e-mail addresses and Steam ids are hidden too. "
            "Read it before sharing it in public: only you know what else could point to you."
        )
        return "\n".join(part for part in (self.summary, said, warning) if part)

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(tr(text))
        # Its own look: "ghostAction" is styled only inside Settings, and anywhere else a
        # button took the system palette (dark text on a dark button over a light page).
        button.setProperty("diagButton", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False: slot())
        return button

    def _set_ready(self, ready: bool) -> None:
        for widget in (self.copy_button, self.save_button, self.expand_button, self.collapse_button, self.search):
            widget.setEnabled(ready)

    # -- loading -------------------------------------------------------------

    def load(self) -> None:
        """Collect the diagnosis again, in the background."""
        self.refresh_button.setEnabled(False)
        self._set_ready(False)
        self.status.setText(tr("Collecting the diagnosis… This can take a few seconds."))
        self._background.start(
            "collect", self._collect,
            on_success=self._loaded, on_error=self._failed,
            on_finished=lambda: self.refresh_button.setEnabled(True),
        )

    def _loaded(self, sections: list[tuple[str, str]]) -> None:
        for section in self._sections:
            section.setParent(None)
            section.deleteLater()
        self._sections = []
        for title, text in sections:
            section = DiagnosisSection(str(title), str(text))
            self._sections.append(section)
            self.sections_layout.insertWidget(self.sections_layout.count() - 1, section)
        total = sum(len(section.text) for section in self._sections)
        self.summary = tr_format(
            "Diagnosis · {count} sections · {size} KB", count=len(self._sections), size=max(1, round(total / 1024))
        )
        self.search.setToolTip(self._explanation())
        self.status.setText("")
        self._set_ready(bool(self._sections))
        self._apply_filter()

    def _failed(self, message: str) -> None:
        self.status.setText(tr_format("Could not collect the diagnosis: {reason}", reason=message))
        self._set_ready(False)

    # -- showing -------------------------------------------------------------

    def _select_tab(self, tab: str) -> None:
        self._tab = tab
        for key, button in self.tab_buttons.items():
            button.setChecked(key == tab)
        self._apply_filter()

    def visible_sections(self) -> list[DiagnosisSection]:
        query = self.search.text()
        return [
            section for section in self._sections
            if (self._tab == "all" or section.group == self._tab) and section.matches(query)
        ]

    def _apply_filter(self) -> None:
        shown = set(map(id, self.visible_sections()))
        searching = bool(self.search.text().strip())
        for section in self._sections:
            section.setVisible(id(section) in shown)
            # A search opens what it found, so the match is in front of the reader.
            if searching and id(section) in shown:
                section.set_open(True)
        if self._sections and not shown:
            self.status.setText(tr("No section matches your search."))
        elif self._sections:
            self.status.setText("")

    def _expand(self, opened: bool) -> None:
        for section in self.visible_sections():
            section.set_open(opened)

    # -- output --------------------------------------------------------------

    def text(self) -> str:
        return as_text([(section.title, section.text) for section in self._sections])

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self.text())
        show_toast(self, tr("Copied"), tr("Paste it into your problem report."), tone="green")

    def _save(self) -> None:
        suggestion = f"bc250-diagnosis-{datetime.now():%Y%m%d-%H%M}.txt"
        chosen, _filter = QFileDialog.getSaveFileName(
            self, tr("Save as file…"), str(Path.home() / suggestion), "Text (*.txt)"
        )
        if not chosen:
            return
        try:
            Path(chosen).write_text(self.text(), encoding="utf-8")
        except OSError as error:
            self.status.setText(tr_format("Could not save the file: {reason}", reason=str(error)))
            return
        show_toast(self, tr("Saved"), chosen, tone="green")
