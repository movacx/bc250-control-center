"""First-run preferences, component preparation and the guided tour."""

from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..components.toggle_switch import ToggleSwitch
from ..components.wheel_guard import GuardedComboBox
from ..i18n import LANGUAGE_OPTIONS, language_name, system_language, tr, tr_format
from .components import ComponentPicker, component_specs
from .mini_console import MiniConsole
from .previews import AccentDot, SidebarPreview, ThemePreview
from .script import tour_stops


class _StepRow(QPushButton):
    """One entry in the rail: a number, a name, and where the user is."""

    def __init__(self, index: int, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingStepRow")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._index = int(index)
        self._label = str(label)
        self.setText(f"{self._index}    {self._label}")

    def set_label(self, label: str) -> None:
        self._label = str(label)
        self.setText(f"{self._index}    {self._label}")

    def set_done(self, done: bool) -> None:
        self.setProperty("done", bool(done))
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)


class _LanguageChip(QPushButton):
    """A language in its own name, which is the only name worth showing."""

    def __init__(self, code: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("onboardingChip")
        self.code = str(code)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(36)


class WelcomeOverlay(QWidget):
    """First-run options shown over the application window."""

    language_chosen = pyqtSignal(str)
    appearance_chosen = pyqtSignal(str, str, str)
    #: "standard" or "formal": the register, independent of the theme.
    style_chosen = pyqtSignal(str)
    scale_chosen = pyqtSignal(int)
    gamepad_chosen = pyqtSignal(bool)
    sidebar_chosen = pyqtSignal(bool)
    #: A built-in terminal theme key, or "app" for the application's colours.
    terminal_theme_chosen = pyqtSignal(str)
    #: The user pressed the button that installs the chosen components.
    prepare_requested = pyqtSignal()
    #: The dependencies step has been opened; a good moment to ask the board
    #: what is already on it.
    dependencies_reached = pyqtSignal()
    #: A preparation run ended: what is installed may have changed.
    preparation_completed = pyqtSignal()
    #: True when the user asked for the guided tour on the way out.
    finished = pyqtSignal(bool)

    STEP_COUNT = 5

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        language: str = "auto",
        mode: str = "system",
        accent: str = "blue",
        density: str = "comfortable",
        collapsed: bool = False,
        gamepad_enabled: bool = False,
        system_mode: str = "light",
        style: str = "standard",
        scale: int = 100,
        terminal_theme: str = "app",
    ) -> None:
        super().__init__(parent)
        self._terminal_theme = str(terminal_theme)
        # Its own layout previews the density; the pass must not reshape it.
        self.setProperty("densityLocked", True)
        self.setObjectName("onboardingOverlay")
        self.setAutoFillBackground(False)
        # Opaque to the mouse on purpose: the shell behind is frosted, and a
        # click that reached it would act on a control nobody can read.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._language = str(language)
        self._mode = str(mode)
        self._accent = str(accent)
        self._density = str(density)
        self._style = str(style)
        self._initial_scale = scale
        self._gamepad_enabled = gamepad_enabled
        self._collapsed = bool(collapsed)
        # What "System" resolves to on this desktop. Fixed for the life of the
        # panel: it describes the desktop, not the choice being made in here,
        # so picking Light must not repaint the System card as light.
        self._system_mode = str(system_mode)
        self._step = 0

        self._build()
        self._sync_rail()

    # ------------------------------------------------------------- structure

    def _build(self) -> None:
        outer = QGridLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame(self)
        self.card.setObjectName("onboardingCard")
        self.card.setMaximumSize(1240, 760)
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(self.card, 0, 0)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addWidget(self._build_rail())
        card_layout.addWidget(self._build_content(), 1)

    def _build_rail(self) -> QWidget:
        rail = QWidget(self.card)
        rail.setObjectName("onboardingRail")
        rail.setMinimumWidth(212)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(16, 24, 16, 20)
        layout.setSpacing(6)

        self.brand = QLabel("BC250 Control Center", rail)
        self.brand.setObjectName("onboardingBrand")
        self.brand.setWordWrap(True)
        layout.addWidget(self.brand)
        layout.addSpacing(22)

        self.step_rows: list[_StepRow] = []
        self._step_group = QButtonGroup(rail)
        self._step_group.setExclusive(True)
        for index, label in enumerate(self._step_labels(), start=1):
            button = _StepRow(index, label, rail)
            button.clicked.connect(lambda _checked=False, step=index - 1: self._reach(step))
            self._step_group.addButton(button)
            self.step_rows.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        self.skip_button = QPushButton(tr("Skip setup"), rail)
        self.skip_button.setObjectName("onboardingGhost")
        self.skip_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_button.clicked.connect(lambda: self._leave(tour=False))
        layout.addWidget(self.skip_button)
        return rail

    @staticmethod
    def _step_labels() -> tuple[str, ...]:
        return (
            tr("Language"), tr("Appearance"), tr("Navigation"),
            tr("Dependencies"), tr("Guided tour"),
        )

    def _build_content(self) -> QWidget:
        content = QWidget(self.card)
        content.setObjectName("onboardingContent")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 26, 28, 18)
        layout.setSpacing(0)

        self.title = QLabel("", content)
        self.title.setObjectName("onboardingTitle")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.subtitle = QLabel("", content)
        self.subtitle.setObjectName("onboardingSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)
        layout.addSpacing(20)

        self.steps = QStackedWidget(content)
        self.steps.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.steps.addWidget(self._build_language_step())
        self.steps.addWidget(self._build_appearance_step())
        self.steps.addWidget(self._build_sidebar_step())
        self.steps.addWidget(self._build_dependencies_step())
        self.steps.addWidget(self._build_tour_step())
        layout.addWidget(self.steps, 1)

        layout.addSpacing(12)
        divider = QFrame(content)
        divider.setObjectName("onboardingDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 12, 0, 0)
        footer.setSpacing(10)
        self.progress = QLabel("", content)
        self.progress.setObjectName("onboardingProgress")
        footer.addWidget(self.progress)
        footer.addStretch(1)
        self.back_button = QPushButton(tr("Back"), content)
        self.back_button.setObjectName("onboardingSecondary")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(lambda: self._reach(self._step - 1))
        footer.addWidget(self.back_button)
        self.next_button = QPushButton(tr("Continue"), content)
        self.next_button.setObjectName("onboardingPrimary")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._advance)
        footer.addWidget(self.next_button)
        layout.addLayout(footer)
        return content

    # ------------------------------------------------------------- the steps

    def _build_language_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        area = QScrollArea(page)
        area.setObjectName("onboardingScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.language_scrollbar = area.verticalScrollBar()
        self._dress_scrollbar()
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 12, 0)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        grid.setSpacing(8)

        self.language_chips: dict[str, _LanguageChip] = {}
        self._language_group = QButtonGroup(page)
        self._language_group.setExclusive(True)
        position = 0
        for code, native in LANGUAGE_OPTIONS:
            label = self._automatic_label() if code == "auto" else native
            chip = _LanguageChip(code, label, holder)
            chip.clicked.connect(lambda _checked=False, value=code: self._choose_language(value))
            self._language_group.addButton(chip)
            self.language_chips[code] = chip
            if code == "auto":
                grid.addWidget(chip, 0, 0, 1, 3)
            else:
                grid.addWidget(chip, 1 + position // 3, position % 3)
                position += 1
        area.setWidget(holder)
        layout.addWidget(area, 1)
        return page

    @staticmethod
    def _scrollbar_sheet() -> str:
        """The scrollbar rules, as a sheet to set on the bar itself.

        The application stylesheet leaves a scrollbar's track pages unstyled,
        which the platform then paints for itself — invisible against every
        other panel, and a solid black bar down the side of a pane of glass.
        Set on the widget because a rule scoped to the scroll area did not
        reach the scrollbar at all.
        """
        colors = theme_module.COLORS
        return (
            "QScrollBar:vertical{background:transparent;width:8px;margin:2px 0 2px 0;"
            "border:none;}"
            f"QScrollBar::handle:vertical{{background:{colors['border_strong']};"
            "border-radius:4px;min-height:36px;}"
            f"QScrollBar::handle:vertical:hover{{background:{colors['subtle']};}}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;"
            "background:transparent;border:none;}"
            # An explicit colour, not "transparent" and not "none": both left
            # the track below the handle to the platform style, which painted
            # it solid black down the side of the panel. A quiet visible track
            # is a normal scrollbar; an invisible one was never worth this.
            f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{"
            f"background:{colors['border_soft']};border:none;border-radius:4px;}}"
        )

    def _dress_scrollbar(self) -> None:
        """Style the list's scrollbar on the widget itself.

        The application stylesheet leaves a scrollbar's track pages unstyled,
        which the platform then paints for itself — invisible against every
        other panel in the application, and a solid black bar down the side of
        a pane of glass. Set here rather than in the cascade because a rule
        scoped to this scroll area did not reach the scrollbar at all.
        """
        sheet = self._scrollbar_sheet()
        for bar in (self.language_scrollbar,):
            if bar is not None:
                bar.setStyleSheet(sheet)

    def refresh_appearance(self) -> None:
        """Repaint what does not come from the window's style sheet."""
        self._dress_scrollbar()
        self._sync_appearance()
        self._sync_sidebar()
        console = getattr(self, "console", None)
        if console is not None:
            console.apply_theme()
        for card in getattr(self, "terminal_cards", {}).values():
            card.update()

    @staticmethod
    def _theme_names() -> tuple[tuple[str, str], ...]:
        return (
            ("system", tr("System")), ("light", tr("Light")), ("dark", tr("Dark")),
            ("midnight", tr("Night blue")),
        )

    @staticmethod
    def _automatic_label() -> str:
        """"Automatic" is useless without saying what it resolved to."""
        return f"{tr('Automatic')} · {language_name(system_language())}"

    def _build_appearance_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        themes = QHBoxLayout()
        themes.setSpacing(10)
        self.theme_cards: dict[str, ThemePreview] = {}
        for value, preview_mode in (
            ("system", self._system_mode), ("light", "light"), ("dark", "dark"),
            ("midnight", "midnight"),
        ):
            card = ThemePreview(value, preview_mode, self._accent, page, style=self._style)
            card.setMinimumHeight(126)
            card.chosen.connect(self._choose_mode)
            self.theme_cards[value] = card
            themes.addWidget(card, 1)
        layout.addLayout(themes)

        labels = QHBoxLayout()
        labels.setSpacing(10)
        self.theme_labels: dict[str, QLabel] = {}
        for value, text in self._theme_names():
            label = QLabel(text, page)
            label.setObjectName("onboardingCaption")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.theme_labels[value] = label
            labels.addWidget(label, 1)
        layout.addLayout(labels)

        self.accent_heading = QLabel(tr("Accent color"), page)
        self.accent_heading.setObjectName("onboardingSectionLabel")
        layout.addWidget(self.accent_heading)

        palettes = QHBoxLayout()
        palettes.setSpacing(10)
        self.style_buttons: dict[str, QPushButton] = {}
        self.palette_dots: dict[str, dict[str, AccentDot]] = {}
        self._style_group = QButtonGroup(page)
        self._style_group.setExclusive(True)
        for style, title in (("standard", tr("Standard")), ("formal", tr("Formal"))):
            panel = QFrame(page)
            panel.setObjectName("onboardingOptions")
            grid = QGridLayout(panel)
            grid.setContentsMargins(10, 12, 10, 12)
            grid.setHorizontalSpacing(2)
            grid.setVerticalSpacing(6)

            button = QPushButton(title, panel)
            button.setObjectName("onboardingChip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, item=style: self._choose_style(item))
            self._style_group.addButton(button)
            self.style_buttons[style] = button
            grid.addWidget(button, 0, 0, 1, 5)

            dots = {}
            for index, name in enumerate(theme_module.ACCENTS):
                dot = AccentDot(name, panel, style=style)
                dot.chosen.connect(lambda accent, item=style: self._choose_accent(accent, item))
                dots[name] = dot
                grid.addWidget(dot, 1 + index // 5, index % 5, Qt.AlignmentFlag.AlignCenter)
            self.palette_dots[style] = dots
            palettes.addWidget(panel, 1)
        layout.addLayout(palettes)

        self.density_heading = QLabel(tr("Density"), page)
        self.density_heading.setObjectName("onboardingSectionLabel")
        density = QHBoxLayout()
        density.setSpacing(8)
        density.addWidget(self.density_heading)
        density.addSpacing(8)
        self.density_buttons: dict[str, QPushButton] = {}
        self._density_group = QButtonGroup(page)
        self._density_group.setExclusive(True)
        for value, text in (("comfortable", tr("Comfortable")), ("compact", tr("Compact"))):
            button = QPushButton(text, page)
            button.setObjectName("onboardingChip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(38)
            button.clicked.connect(lambda _checked=False, item=value: self._choose_density(item))
            self._density_group.addButton(button)
            self.density_buttons[value] = button
            density.addWidget(button)
        density.addStretch(1)
        self.scale_heading = QLabel(tr("Interface scale"), page)
        self.scale_heading.setObjectName("onboardingSectionLabel")
        self.scale_combo = GuardedComboBox(page)
        self.scale_combo.setObjectName("onboardingScale")
        for value in range(70, 151, 10):
            self.scale_combo.addItem(f"{value}%", value)
        self.scale_combo.setCurrentIndex(self.scale_combo.findData(self._initial_scale))
        self.scale_combo.currentIndexChanged.connect(
            lambda index: self.scale_chosen.emit(self.scale_combo.itemData(index))
        )
        self.scale_heading.setBuddy(self.scale_combo)
        density.addWidget(self.scale_heading)
        density.addWidget(self.scale_combo)
        layout.addLayout(density)

        # The built-in terminal's colours, each as the terminal it gives.
        from ..pages.settings import TerminalThemeCard

        self.terminal_heading = QLabel(tr("Terminal theme"), page)
        self.terminal_heading.setObjectName("onboardingSectionLabel")
        layout.addWidget(self.terminal_heading)
        # Ten small cards: two rows of five, so each still shows its colours.
        terminals = QGridLayout()
        terminals.setHorizontalSpacing(8)
        terminals.setVerticalSpacing(8)
        self.terminal_cards: dict[str, TerminalThemeCard] = {}
        choices = [("app", tr("Automatic"))] + [
            (key, entry["name"]) for key, entry in theme_module.TERMINAL_THEMES.items()
        ]
        columns = 5
        for index, (key, name) in enumerate(choices):
            card = TerminalThemeCard(key, name, page, compact=True)
            card.selected = key == self._terminal_theme
            card.chosen.connect(self._choose_terminal_theme)
            self.terminal_cards[key] = card
            terminals.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            terminals.setColumnStretch(column, 1)
        layout.addLayout(terminals)
        layout.addStretch(1)
        return page

    def _choose_terminal_theme(self, key: str) -> None:
        self._terminal_theme = str(key)
        for name, card in self.terminal_cards.items():
            card.selected = name == self._terminal_theme
            card.update()
        self.terminal_theme_chosen.emit(self._terminal_theme)

    def _build_sidebar_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        controller = QFrame(page)
        controller.setObjectName("onboardingOptions")
        navigation = QHBoxLayout(controller)
        navigation.setContentsMargins(16, 12, 16, 12)
        self.gamepad_label = QLabel(tr("Gamepad navigation"), page)
        self.gamepad_switch = ToggleSwitch()
        self.gamepad_switch.setAccessibleName(self.gamepad_label.text())
        self.gamepad_switch.setChecked(self._gamepad_enabled)
        self.gamepad_switch.toggled.connect(self.gamepad_chosen)
        labels = QVBoxLayout()
        labels.addWidget(self.gamepad_label)
        self.gamepad_hint = QLabel(tr("Detect controllers automatically and show controller hints while active."), page)
        self.gamepad_hint.setObjectName("onboardingSubtitle")
        self.gamepad_hint.setWordWrap(True)
        labels.addWidget(self.gamepad_hint)
        navigation.addLayout(labels, 1)
        navigation.addWidget(self.gamepad_switch)
        layout.addWidget(controller)
        self.sidebar_heading = QLabel(tr("Sidebar"), page)
        self.sidebar_heading.setObjectName("onboardingCaption")
        layout.addSpacing(12)
        layout.addWidget(self.sidebar_heading)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        self.sidebar_cards: dict[str, SidebarPreview] = {}
        self.sidebar_labels: dict[str, QLabel] = {}
        for value, collapsed in (("expanded", False), ("collapsed", True)):
            column = QVBoxLayout()
            column.setSpacing(6)
            card = SidebarPreview(value, collapsed, page)
            card.setMaximumWidth(210)
            card.setMinimumHeight(168)
            card.setMaximumHeight(232)
            card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            card.chosen.connect(self._choose_sidebar)
            self.sidebar_cards[value] = card
            column.addWidget(card)
            label = QLabel(tr("Collapsed") if collapsed else tr("Expanded"), page)
            label.setObjectName("onboardingCaption")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.sidebar_labels[value] = label
            column.addWidget(label)
            cards.addLayout(column)
        cards.addStretch(1)
        layout.addLayout(cards, 2)
        layout.addStretch(1)
        return page

    def _build_dependencies_step(self) -> QWidget:
        """The choice on top, the terminal under it once something runs.

        The two used to take turns in the same space, so the list vanished the
        moment the install started and the step read as a different screen.
        Now the list stays where it was (locked while the install runs) and
        the terminal opens beneath it, the way the docked console does.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.picker = ComponentPicker(component_specs())
        self.picker.selection_changed.connect(self._sync_prepare_button)
        layout.addWidget(self.picker.header)
        layout.addWidget(self.picker)
        # The install button takes the free cell beside the last row; what it
        # needs (internet, the password) is said once, under the title.
        self.prepare_button = QPushButton(tr("Install the basics"), page)
        self.prepare_button.setObjectName("onboardingPrimary")
        self.prepare_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prepare_button.clicked.connect(self.prepare_requested)
        self.picker.place_action(self.prepare_button)

        # Only for a run that never started: why, right above the terminal.
        self.prepare_note = QLabel("", page)
        self.prepare_note.setObjectName("onboardingHint")
        self.prepare_note.setWordWrap(True)
        self.prepare_note.hide()
        layout.addWidget(self.prepare_note)

        self.console = MiniConsole(page)
        self.console.setMinimumHeight(140)
        self.console.workflow_started.connect(self._preparation_started)
        self.console.workflow_finished.connect(self._preparation_finished)
        self.console.hide()
        layout.addWidget(self.console, 1)
        # Keeps the list at the top while the terminal is folded away; while it
        # is open the terminal takes all the height the step has left.
        self._dependencies_layout = layout
        self._dependencies_spacer = layout.count()
        layout.addStretch(1)
        return page

    def show_dependency_face(self, name: str) -> None:
        """Open the terminal under the list, or fold it away again."""
        opening = name == "console"
        self.picker.set_dense(opening)
        self.console.setVisible(opening)
        self._dependencies_layout.setStretch(self._dependencies_spacer, 0 if opening else 1)

    def selected_components(self) -> set[str]:
        return self.picker.selection()

    def mark_installed_components(self, installed) -> None:
        self.picker.mark_installed(installed)

    def _sync_prepare_button(self) -> None:
        if self.preparing:
            return
        count = len(self.picker.selection())
        self.prepare_button.setEnabled(count > 0)
        self.prepare_button.setText(
            tr_format("Install {count}", count=count) if count else tr("Nothing selected")
        )

    # ------------------------------------------------------ the install

    def preparation_starting(self) -> None:
        """The install has been asked for but no terminal has opened yet.

        Without this the button stays live through the second or two the
        backend spends working out what to run, and a second press would
        start the whole thing twice.
        """
        self.prepare_button.setEnabled(False)
        self.prepare_button.setText(tr("Installing…"))

    def _preparation_started(self) -> None:
        self.prepare_note.clear()
        self.prepare_note.hide()
        self.show_dependency_face("console")
        self.picker.setEnabled(False)
        self.prepare_button.setEnabled(False)
        self.prepare_button.setText(tr("Installing…"))
        self._sync_copy()

    def _preparation_finished(self, code: int) -> None:
        # The terminal stays open with its output: success or failure, the
        # last lines are what the user wants to read next. The list unlocks
        # so a failed component can be tried again.
        del code
        self.picker.setEnabled(True)
        self.prepare_button.setEnabled(True)
        self._sync_prepare_button()
        self._sync_copy()
        # Ask again what is on the machine, so what the run installed is
        # marked and no longer counted in the button.
        self.preparation_completed.emit()

    def preparation_failed(self, message: str) -> None:
        """Say why the install never started, where the note sits."""
        self.picker.setEnabled(True)
        self._sync_prepare_button()
        self.prepare_note.setText(message)
        self.prepare_note.setVisible(bool(message))

    @property
    def preparing(self) -> bool:
        return self.console.busy

    def _build_tour_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.tour_note = QLabel("", page)
        self.tour_note.setObjectName("onboardingBody")
        self.tour_note.setWordWrap(True)
        layout.addWidget(self.tour_note)

        # The itinerary, named. "A short walk through the modules" is a
        # promise; these are the stops, so the choice is made on what the tour
        # actually covers rather than on an adjective. They are the tour's own
        # titles, so the list cannot drift away from the route.
        self.stop_grid = QGridLayout()
        self.stop_grid.setContentsMargins(0, 0, 0, 0)
        self.stop_grid.setHorizontalSpacing(10)
        self.stop_grid.setVerticalSpacing(7)
        self.stop_chips: list[QLabel] = []
        layout.addLayout(self.stop_grid)
        self._fill_stop_grid(page)
        layout.addStretch(1)
        return page

    #: The tour's pages, named the way the sidebar names them.
    TOUR_SECTIONS = (
        ("dashboard", "Dashboard"),
        ("cpu", "CPU"),
        ("gpu", "GPU"),
        ("cu", "Compute units"),
        ("extras", "Additional settings"),
        ("performance", "Performance"),
        ("fans", "Fans"),
        ("firmware", "Firmware (BIOS)"),
        ("settings", "Settings"),
    )

    def _fill_stop_grid(self, page: QWidget) -> None:
        """One line per module with its stops, rather than one per stop.

        The tour grew to cover the profile cards, the voltage laboratory and
        the memory settings; listing every stop would fill the card with a
        column nobody reads. Each line names a module and what the tour shows
        in it, and the full list of titles is its tooltip.
        """
        for chip in self.stop_chips:
            self.stop_grid.removeWidget(chip)
            chip.deleteLater()
        self.stop_chips = []
        stops = tour_stops()
        dashboard_titles = [stop.title for stop in stops if stop.page == "dashboard"]
        for key, name in self.TOUR_SECTIONS:
            if key == "settings":
                # The closing stop points at Settings from the dashboard.
                titles = dashboard_titles[-1:]
            else:
                titles = [stop.title for stop in stops if stop.page == key]
            if key == "dashboard":
                titles = titles[:-1]
            if not titles:
                continue
            text = (
                tr_format("{module} · 1 stop", module=tr(name))
                if len(titles) == 1
                else tr_format("{module} · {count} stops", module=tr(name), count=len(titles))
            )
            chip = QLabel(text, page)
            chip.setObjectName("onboardingStopChip")
            chip.setToolTip("\n".join(titles))
            chip.setProperty("tourTitles", titles)
            self.stop_chips.append(chip)
            slot = len(self.stop_chips) - 1
            self.stop_grid.addWidget(chip, slot // 2, slot % 2)

    # ------------------------------------------------------------- choosing

    def _choose_language(self, code: str) -> None:
        self._language = str(code)
        self._sync_language()
        self.language_chosen.emit(self._language)

    def _choose_mode(self, mode: str) -> None:
        self._mode = str(mode)
        self._sync_appearance()
        self.appearance_chosen.emit(self._mode, self._accent, self._density)

    @property
    def accent_dots(self) -> dict[str, AccentDot]:
        return self.palette_dots[self._style]

    def _choose_accent(self, accent: str, style: str | None = None) -> None:
        self._accent = str(accent)
        if style is not None and style != self._style:
            self._style = style
            self.style_chosen.emit(style)
        self._sync_appearance()
        self.appearance_chosen.emit(self._mode, self._accent, self._density)

    def _choose_density(self, density: str) -> None:
        self._density = str(density)
        self._sync_appearance()
        self.appearance_chosen.emit(self._mode, self._accent, self._density)

    def _choose_style(self, style: str) -> None:
        self._style = str(style)
        self._sync_appearance()
        self.style_chosen.emit(self._style)

    def _choose_sidebar(self, value: str) -> None:
        self._collapsed = value == "collapsed"
        self._sync_sidebar()
        self.sidebar_chosen.emit(self._collapsed)

    # ------------------------------------------------------------- movement

    #: Which step holds the component picker, so it can be told to arrive.
    DEPENDENCY_STEP = 3

    def _reach(self, step: int) -> None:
        previous = self._step
        self._step = max(0, min(int(step), self.STEP_COUNT - 1))
        self.steps.setCurrentIndex(self._step)
        self._sync_rail()
        if self._step == self.DEPENDENCY_STEP and previous != self._step:
            # The tiles fly in when the step is reached rather than when it was
            # built, which is behind four other steps and long since over.
            self.picker.reveal()
            self.dependencies_reached.emit()

    def _advance(self) -> None:
        if self._step >= self.STEP_COUNT - 1:
            self._leave(tour=True)
            return
        self._reach(self._step + 1)

    def _leave(self, *, tour: bool) -> None:
        self.hide()
        self.finished.emit(bool(tour))

    # --------------------------------------------------------------- syncing

    def _sync_rail(self) -> None:
        for index, row in enumerate(self.step_rows):
            row.setChecked(index == self._step)
            row.set_done(index < self._step)
        self.back_button.setVisible(self._step > 0)
        last = self._step == self.STEP_COUNT - 1
        self.next_button.setText(tr("Start the tour") if last else tr("Continue"))
        self.skip_button.setText(tr("Go straight in") if last else tr("Skip setup"))
        self.progress.setText(f"{self._step + 1} / {self.STEP_COUNT}")
        self._sync_copy()
        self._sync_language()
        self._sync_appearance()
        self._sync_sidebar()

    def _sync_copy(self) -> None:
        headings = (
            (tr("Choose your language"),
             tr("The interface, its reports and its guides are all translated.")),
            (tr("Choose how it looks"),
             ""),
            (tr("Navigation"), ""),
            (tr("Prepare the board"),
             f'{tr("Tools the other modules need. Anything already installed is marked.")} '
             f'{tr("Needs internet and your password. Every command is shown in the terminal.")}'),
            (tr("Take the guided tour?"),
             tr("A short walk through the modules, pointing at the real controls.")),
        )
        title, subtitle = headings[self._step]
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.tour_note.setText(
            tr("It stops at each module, says what it is for and what it changes on "
               "the board. You can leave it at any point, and start it again from "
               "Settings whenever you like.")
        )

    def _sync_language(self) -> None:
        for chip in self.language_chips.values():
            chip.setChecked(chip.code == self._language)

    def _sync_appearance(self) -> None:
        for value, card in self.theme_cards.items():
            card.set_selected(value == self._mode)
            card.set_accent(self._accent)
            card.set_style(self._style)
        for style, dots in self.palette_dots.items():
            for name, dot in dots.items():
                dot.set_selected(style == self._style and name == self._accent)
                dot.update()
        for value, button in self.style_buttons.items():
            button.setChecked(value == self._style)
        for value, button in self.density_buttons.items():
            button.setChecked(value == self._density)

    def _sync_sidebar(self) -> None:
        for value, card in self.sidebar_cards.items():
            card.set_selected((value == "collapsed") == self._collapsed)
            card.update()

    def retranslate(self) -> None:
        self.gamepad_hint.setText(tr("Detect controllers automatically and show controller hints while active."))
        self.sidebar_heading.setText(tr("Sidebar"))
        self.gamepad_label.setText(tr("Gamepad navigation"))
        self.gamepad_switch.setAccessibleName(self.gamepad_label.text())
        for row, label in zip(self.step_rows, self._step_labels()):
            row.set_label(label)
        chip = self.language_chips.get("auto")
        if chip is not None:
            chip.setText(self._automatic_label())
        for value, text in self._theme_names():
            self.theme_labels[value].setText(text)
        self.accent_heading.setText(tr("Accent color"))
        for dots in self.palette_dots.values():
            for dot in dots.values():
                dot.retranslate()
        self.style_buttons["standard"].setText(tr("Standard"))
        self.style_buttons["formal"].setText(tr("Formal"))
        self.scale_heading.setText(tr("Interface scale"))
        self.density_heading.setText(tr("Density"))
        self.terminal_heading.setText(tr("Terminal theme"))
        self.density_buttons["comfortable"].setText(tr("Comfortable"))
        self.density_buttons["compact"].setText(tr("Compact"))
        self.sidebar_labels["expanded"].setText(tr("Expanded"))
        self.sidebar_labels["collapsed"].setText(tr("Collapsed"))
        self.console.retranslate()
        self.picker.retranslate()
        self._sync_prepare_button()
        self._fill_stop_grid(self.steps.widget(self.STEP_COUNT - 1))
        self.back_button.setText(tr("Back"))
        self._sync_rail()

    # -------------------------------------------------------------- lifecycle

    def reveal(self) -> None:
        """Cover the parent and focus the first-run panel."""
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() == Qt.Key.Key_Escape:
            self._leave(tour=False)
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(17, 25, 39, 155))
        painter.end()

    @property
    def terminal_open(self) -> bool:
        return not self.console.isHidden()
