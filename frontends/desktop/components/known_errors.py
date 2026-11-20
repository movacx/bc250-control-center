"""Searchable support articles with distribution-specific commands."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bc250cc.platform.packages.strategies.detector import detect_os_info
from bc250cc.shared import known_errors
from bc250cc.shared.version import __version__

from ..i18n import current_language, tr, tr_format
from .buttons import WrappingButton as QPushButton
from .wheel_guard import GuardedComboBox
from .widgets import command_box

DISTRO_LABELS = {
    "arch": "Arch / CachyOS / Manjaro", "steamos": "SteamOS",
    "bazzite": "Bazzite / Fedora Atomic", "fedora": "Fedora / Nobara",
    "ubuntu": "Ubuntu / Mint", "debian": "Debian", "other": "Other distributions",
}
STATUS_LABELS = {
    "fixed": "Resolved", "fixed-dev": "Fixed in development", "user": "User steps",
    "pending": "Pending", "expected": "Expected behavior", "analysis": "Under investigation",
}


def _label(text: str, property_name: str = "guideBody", *, literal: bool = False) -> QLabel:
    label = QLabel(text)
    label.setProperty(property_name, True)
    label.setProperty("i18nLiteral", literal)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _clear(column: QVBoxLayout) -> None:
    while column.count():
        item = column.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().deleteLater()


class DistributionContext(QObject):
    """Keep a manual choice when moving between the index and a guide."""
    changed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.selection = "auto"
        try:
            info = detect_os_info()
            self.detected_family = known_errors.family_for(info.family)
            self.detected_name = getattr(info, "label", "") or DISTRO_LABELS[self.detected_family]
        except OSError:
            self.detected_family, self.detected_name = "other", "Other distributions"

    @property
    def family(self) -> str:
        return self.detected_family if self.selection == "auto" else self.selection

    def select(self, selection: str) -> None:
        if selection in ("auto", *known_errors.FAMILIES) and selection != self.selection:
            self.selection = selection
            self.changed.emit(selection)


class DistributionSelector(QWidget):
    def __init__(self, context: DistributionContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        label = _label(tr("Distribution"), "guideFieldLabel")
        row.addWidget(label)
        self.combo = GuardedComboBox()
        self.combo.setProperty("settingsCombo", True)
        self.combo.setProperty("narrowCombo", True)
        self.combo.setMaximumWidth(340)
        self.combo.setMinimumWidth(160)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setAccessibleName(tr("Distribution"))
        label.setBuddy(self.combo)
        row.addWidget(self.combo, 1)
        row.addStretch(1)
        self.refresh_language()
        self.combo.currentIndexChanged.connect(lambda: self.context.select(str(self.combo.currentData())))
        context.changed.connect(self._sync)

    def refresh_language(self) -> None:
        with QSignalBlocker(self.combo):
            self.combo.clear()
            self.combo.addItem(tr("Automatic") + " · " + tr(self.context.detected_name), "auto")
            for family in known_errors.FAMILIES:
                self.combo.addItem(tr(DISTRO_LABELS[family]), family)
            self.combo.setCurrentIndex(max(0, self.combo.findData(self.context.selection)))

    def _sync(self, selection: str) -> None:
        with QSignalBlocker(self.combo):
            self.combo.setCurrentIndex(self.combo.findData(selection))


class KnownErrorsList(QWidget):
    entry_requested = pyqtSignal(str)
    report_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.language = current_language()
        self.module = ""
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        filters = QHBoxLayout()
        filters.setSpacing(12)
        self.search_field = QLineEdit()
        self.search_field.setProperty("guideSearch", True)
        self.search_field.setPlaceholderText(tr("Search by code, message or keyword"))
        self.search_field.setAccessibleName(tr("Search by code, message or keyword"))
        self.search_field.setClearButtonEnabled(True)
        filters.addWidget(self.search_field, 3)
        self.module_metadata = {module["id"]: module for module in known_errors.modules()}
        self.module_combo = GuardedComboBox()
        self.module_combo.setProperty("settingsCombo", True)
        self.module_combo.setProperty("narrowCombo", True)
        self.module_combo.setMinimumWidth(120)
        self.module_combo.setMaximumWidth(240)
        self.module_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.module_combo.setAccessibleName(tr("Modules"))
        self.module_combo.addItem(tr("All modules"), "")
        for key, module in self.module_metadata.items():
            self.module_combo.addItem(tr(module["label"]), key)
        filters.addWidget(self.module_combo, 2)
        layout.addLayout(filters)
        self.table = QWidget()
        self.rows_layout = QVBoxLayout(self.table)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        self.rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rows, self.titles, self.subtitles, self.view_buttons = {}, {}, {}, {}
        for index, entry in enumerate(known_errors.load(), start=1):
            row = QFrame()
            row.setProperty("repositoryRow", True)
            row.setProperty("guideRow", True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(18, 16, 18, 16)
            row_layout.setSpacing(16)
            number = _label(f"{index:02d}", "repositoryIndex", literal=True)
            number.setFixedWidth(25)
            row_layout.addWidget(number)
            copy = QVBoxLayout()
            copy.setSpacing(7)
            title = _label("", "guideRowTitle", literal=True)
            subtitle = _label("", "guideMeta", literal=True)
            copy.addWidget(title)
            copy.addWidget(subtitle)
            self.titles[entry["id"]], self.subtitles[entry["id"]] = title, subtitle
            row_layout.addLayout(copy, 1)
            view = QPushButton(tr("Open guide"))
            view.setProperty("ghostAction", True)
            view.setFixedHeight(36)
            view.setAccessibleName(tr("Open guide") + " " + entry["id"])
            view.clicked.connect(lambda _checked=False, identity=entry["id"]: self.entry_requested.emit(identity))
            row_layout.addWidget(view, 0, Qt.AlignmentFlag.AlignVCenter)
            self.view_buttons[entry["id"]] = view
            self.rows_layout.addWidget(row)
            self.rows[entry["id"]] = row
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(0, 8, 0, 0)
        empty_layout.setSpacing(12)
        empty_layout.addWidget(_label(tr("No results"), "guideLead"))
        empty_layout.addWidget(_label(tr("Try another search or select a module."), "guideMeta"))
        self.suggestion_buttons = []
        for _ in range(3):
            button = QPushButton()
            button.setProperty("ghostAction", True)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, item=button: self._suggested_query(item.property("query")))
            empty_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            self.suggestion_buttons.append(button)
        self.module_suggestions = []
        for _ in range(3):
            button = QPushButton()
            button.setProperty("ghostAction", True)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, item=button: self._suggested_module(item.property("module")))
            empty_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            self.module_suggestions.append(button)
        self.report_button = QPushButton(tr("Report a problem"))
        self.report_button.setProperty("ghostAction", True)
        self.report_button.setAutoDefault(False)
        self.report_button.clicked.connect(lambda: self.report_requested.emit(self.search_field.text()))
        empty_layout.addWidget(self.report_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.rows_layout.addWidget(self.empty)
        layout.addWidget(self.table)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(150)
        self.search_timer.timeout.connect(self._filter)
        self.search_field.textChanged.connect(lambda: self.search_timer.start())
        self.search_field.returnPressed.connect(self._filter)
        self.module_combo.currentIndexChanged.connect(self._module_changed)
        self.refresh_language()

    def refresh_language(self) -> None:
        self.language = current_language()
        for entry in known_errors.load():
            self.titles[entry["id"]].setText(known_errors.localized(entry["guide"]["title"], self.language))
            module = tr(self.module_metadata[entry["module"]]["label"])
            self.subtitles[entry["id"]].setText(f"{module}  ·  {entry['id']}")
        self._filter()

    def _module_changed(self) -> None:
        self.module = str(self.module_combo.currentData())
        self._filter()

    def _suggested_module(self, module: str) -> None:
        self.search_field.clear()
        self.module_combo.setCurrentIndex(self.module_combo.findData(module))
        self._filter()

    def set_query(self, query: str) -> None:
        self.module_combo.setCurrentIndex(0)
        self._suggested_query(query)

    def _suggested_query(self, query: str) -> None:
        self.search_field.setText(query)
        self._filter()

    def _filter(self, *_args) -> None:
        self.search_timer.stop()
        query = self.search_field.text()
        matches = known_errors.search_matches(query, module=self.module)
        visible = {match.entry["id"] for match in matches}
        for identity, row in self.rows.items():
            row.setVisible(identity in visible)
        for position, match in enumerate(matches):
            entry = match.entry
            module = tr(self.module_metadata[entry["module"]]["label"])
            metadata = f"{module}  ·  {entry['id']}"
            if match.kind:
                term = (tr(self.module_metadata[match.term]["label"])
                        if match.kind == "module" else match.term)
                reason = (tr("Error code") + ": " + term if match.kind == "code"
                          else tr_format("Matches: {term}", term=term))
                metadata += "  ·  " + reason
            self.subtitles[entry["id"]].setText(metadata)
            self.rows_layout.insertWidget(position, self.rows[entry["id"]])
        self.empty.setVisible(not matches)
        suggestions = known_errors.search_suggestions(query, module=self.module) if not matches else ()
        for index, button in enumerate(self.suggestion_buttons):
            button.setVisible(index < len(suggestions))
            if index < len(suggestions):
                button.setText(tr_format("Did you mean: {term}?", term=suggestions[index]))
                button.setProperty("query", suggestions[index])
        from bc250cc.shared.known_errors_search import suggested_modules

        modules = suggested_modules(query) if not matches else ()
        for index, button in enumerate(self.module_suggestions):
            button.setVisible(index < len(modules))
            if index < len(modules):
                button.setText(tr(self.module_metadata[modules[index]]["label"]))
                button.setProperty("module", modules[index])


class KnownErrorDetail(QWidget):
    update_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, context: DistributionContext | None = None):
        super().__init__(parent)
        self.context = context or DistributionContext(self)
        self.identity, self.distro, self.active_tab = "", self.context.family, "solution"
        self.column = QVBoxLayout(self)
        self.column.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(20)
        self.column.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.distribution_selector = DistributionSelector(self.context)
        self.column.addWidget(self.distribution_selector)
        self.distribution_selector.hide()
        self.article = QWidget()
        self.article_column = QVBoxLayout(self.article)
        self.article_column.setContentsMargins(0, 0, 0, 0)
        self.article_column.setSpacing(14)
        self.article_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.column.addWidget(self.article)
        self.context.changed.connect(self._distribution_changed)
        self.tab_buttons, self.tab_pages = {}, {}

    def _distribution_changed(self, _selection: str) -> None:
        if self.identity:
            self.show_entry(self.identity)

    def _section(self, column: QVBoxLayout, heading: str, text: str) -> None:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(_label(tr(heading), "guideSectionTitle"))
        layout.addWidget(_label(text, literal=True))
        column.addWidget(group)

    def show_entry(self, identity: str) -> bool:
        entry = known_errors.for_id(identity)
        if entry is None:
            return False
        if self.identity != entry["id"]:
            self.active_tab = "solution"
        self.identity, self.distro = entry["id"], self.context.family
        language = current_language()
        self.distribution_selector.refresh_language()
        _clear(self.article_column)
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        title_host = QWidget()
        title_row = QHBoxLayout(title_host)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        self.title = _label(known_errors.localized(entry["guide"]["title"], language), "guideTitle", literal=True)
        title_row.addWidget(self.title, 1)
        identifier = _label(entry["id"], "guideMeta", literal=True)
        identifier.setWordWrap(False)
        identifier.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        title_row.addWidget(identifier, 0, Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(title_host)
        header_layout.addWidget(_label(known_errors.localized(entry["guide"]["summary"], language), "guideLead", literal=True))
        header_layout.addWidget(self._facts(entry))
        if entry["owner"] == "expected":
            header_layout.addWidget(_label(tr("A protection, not an error"), "guideNotice"))
        if known_errors.needs_update(entry, __version__):
            update = QPushButton(tr_format("Update to {version}", version=entry["fixed_in"]))
            update.setProperty("primaryAction", True)
            update.clicked.connect(self.update_requested.emit)
            header_layout.addWidget(update, 0, Qt.AlignmentFlag.AlignLeft)
        self.article_column.addWidget(header)
        tab_host = QWidget()
        tabs = QHBoxLayout(tab_host)
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(2)
        self.tab_group = QButtonGroup(tab_host)
        self.tab_group.setExclusive(True)
        self.tab_buttons, self.tab_pages = {}, {}
        for key, text in (("solution", "Solution"), ("developer", "Developer notes")):
            tab = QPushButton(tr(text))
            tab.setProperty("supportTab", True)
            tab.setCheckable(True)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(tab)
            tabs.addWidget(tab)
            tab.clicked.connect(lambda _checked=False, name=key: self.select_tab(name))
            self.tab_buttons[key] = tab
        tabs.addStretch(1)
        self.article_column.addWidget(tab_host)
        for key in self.tab_buttons:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(18)
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.article_column.addWidget(page)
            self.tab_pages[key] = page
        self._build_solution(entry, language, self.tab_pages["solution"].layout())
        developer = self.tab_pages["developer"].layout()
        self._section(developer, "Status", " · ".join(tr(STATUS_LABELS[flag]) for flag in entry["status_flags"]))
        self._section(developer, "Developer notes", known_errors.localized(entry["developer"], language))
        self.select_tab(self.active_tab)
        return True

    def _facts(self, entry: dict) -> QFrame:
        """Code, status and where it was reported, read at a glance."""
        box = QFrame()
        box.setProperty("supportTable", True)
        row = QHBoxLayout(box)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(28)
        seen = ", ".join((entry.get("distros") or {}).get("reported") or ()) or "—"
        facts = (
            ("Code", ", ".join(entry["codes"]) or "—", True),
            ("Status", " · ".join(tr(STATUS_LABELS[flag]) for flag in entry["status_flags"]), False),
            ("Seen on", seen, True),
        )
        for heading, value, literal in facts:
            cell = QVBoxLayout()
            cell.setSpacing(3)
            cell.addWidget(_label(tr(heading).upper(), "supportSummaryHeading"))
            fact = _label(value, "supportFact", literal=literal)
            # A code broken at its hyphen no longer reads as a code.
            fact.setWordWrap(heading != "Code")
            cell.addWidget(fact)
            row.addLayout(cell)
        row.addStretch(1)
        return box

    def _build_solution(self, entry: dict, language: str, column: QVBoxLayout) -> None:
        # Already on screen: the title and the summary under it.
        shown = {
            known_errors.localized(entry["title"], language).strip(),
            known_errors.localized(entry["guide"]["summary"], language).strip(),
        }
        for heading, field in (("What you see", "symptom"), ("Why it happens", "cause")):
            text = known_errors.localized(entry.get(field) or {}, language).strip()
            if text and text not in shown:
                self._section(column, heading, text)
        fixes = QWidget()
        steps = QVBoxLayout(fixes)
        steps.setContentsMargins(0, 0, 0, 0)
        steps.setSpacing(12)
        steps.addWidget(_label(tr("How to fix it"), "guideSectionTitle"))
        column.addWidget(fixes)
        fix = known_errors.fix_for(entry, self.distro)
        if fix is None:
            steps.addWidget(_label(tr("Not applicable"), "guideNotice"))
            return
        steps.addWidget(_label(
            tr_format("Steps for {distribution}", distribution=tr(DISTRO_LABELS[known_errors.family_for(self.distro)])),
            "guideMeta",
        ))
        if fix["scope"] == "equivalent":
            steps.addWidget(_label(tr("Equivalent issue"), "guideNotice"))
        for block in fix["article"]:
            steps.addWidget(_label(known_errors.localized(block["text"], language), literal=True))
            for command in block["commands"]:
                steps.addWidget(command_box(command))

    def select_tab(self, key: str) -> None:
        self.active_tab = key
        for name, page in self.tab_pages.items():
            page.setVisible(name == key)
            self.tab_buttons[name].setChecked(name == key)
        self.updateGeometry()
