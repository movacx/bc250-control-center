"""The screen the application opens on the first time it is ever run.

Every desktop that respects its users asks four questions before it hands the
keys over — Plasma and Fedora both do it — and this application had been
answering all four on the user's behalf: a language guessed from the locale, a
theme guessed from the desktop, a rail width guessed from the window, and a
set of modules nobody had been introduced to.

So it asks. Four steps, each with a real preview rather than a word, each
applied to the live application the moment it is chosen. The shell behind is
frosted rather than hidden, because the thing being configured is the thing
you should be looking at — and frosted rather than merely dimmed, because a
legible interface behind a panel invites a click that will not land.

Nothing here is mandatory: every step can be skipped, and every choice made in
it can be remade later in Settings.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
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
from ..i18n import LANGUAGE_OPTIONS, language_name, system_language, tr, tr_format
from .components import ComponentPicker, component_specs
from .glass import frosted
from .mini_console import MiniConsole
from .previews import AccentDot, SidebarPreview, ThemePreview
from .script import tour_stops

#: The card never grows past this, however wide the window is. Past roughly
#: this width a line of body copy stops being one eye movement.
CARD_MAXIMUM = QSize(920, 620)
#: How dark the glass is over the frosted shell, per mode. Glassmorphism wants
#: a translucent white; on a dark palette that reads as fog, so the dark side
#: gets a translucent black and the card carries the light edge instead.
SCRIM_ALPHA = {"light": 118, "dark": 150}
FADE_MS = 260


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
    """A frosted, four-step first run laid over the whole window."""

    language_chosen = pyqtSignal(str)
    appearance_chosen = pyqtSignal(str, str, str)
    sidebar_chosen = pyqtSignal(bool)
    #: The user pressed the button that installs the chosen components.
    prepare_requested = pyqtSignal()
    #: The dependencies step has been opened; a good moment to ask the board
    #: what is already on it.
    dependencies_reached = pyqtSignal()
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
        system_mode: str = "light",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingOverlay")
        self.setAutoFillBackground(False)
        # Opaque to the mouse on purpose: the shell behind is frosted, and a
        # click that reached it would act on a control nobody can read.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._language = str(language)
        self._mode = str(mode)
        self._accent = str(accent)
        self._density = str(density)
        self._collapsed = bool(collapsed)
        # What "System" resolves to on this desktop. Fixed for the life of the
        # panel: it describes the desktop, not the choice being made in here,
        # so picking Light must not repaint the System card as light.
        self._system_mode = str(system_mode)
        self._backdrop = QPixmap()
        self._backdrop_source: QWidget | None = None
        self._refreshing = False
        # Coalesced: a window drag emits a resize per frame, and each one
        # would otherwise grab and blur the whole shell.
        self._regrab = QTimer(self)
        self._regrab.setSingleShot(True)
        self._regrab.setInterval(90)
        self._regrab.timeout.connect(self.refresh_backdrop)
        self._step = 0
        self._fade: QPropertyAnimation | None = None

        self._build()
        self._sync_rail()

    # ------------------------------------------------------------- structure

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # The card takes the room it can up to its own maximum; the spacers
        # only centre what is left. Equal stretches would have pinned it to a
        # third of the window whatever its maximum said.
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)

        self.card = QFrame(self)
        self.card.setObjectName("onboardingCard")
        self.card.setMaximumSize(CARD_MAXIMUM)
        self.card.setMinimumWidth(560)
        # Wide as it can be, tall as its tallest step. Stretching the height
        # too left every step but the first with an empty lower half, and an
        # empty half reads as a panel that has not finished loading.
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 18)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.card.setGraphicsEffect(shadow)
        row.addWidget(self.card, 14)

        row.addStretch(1)
        outer.addLayout(row, 0)
        outer.addStretch(1)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addWidget(self._build_rail())
        card_layout.addWidget(self._build_content(), 1)

    def _build_rail(self) -> QWidget:
        rail = QWidget(self.card)
        rail.setObjectName("onboardingRail")
        rail.setFixedWidth(238)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(22, 26, 18, 22)
        layout.setSpacing(6)

        self.brand = QLabel("BC250 Control Center", rail)
        self.brand.setObjectName("onboardingBrand")
        self.brand.setWordWrap(True)
        layout.addWidget(self.brand)
        self.brand_note = QLabel(tr("First steps"), rail)
        self.brand_note.setObjectName("onboardingBrandNote")
        layout.addWidget(self.brand_note)
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
            tr("Language"), tr("Appearance"), tr("Sidebar"),
            tr("Dependencies"), tr("Guided tour"),
        )

    def _build_content(self) -> QWidget:
        content = QWidget(self.card)
        content.setObjectName("onboardingContent")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(34, 30, 34, 24)
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

        layout.addSpacing(18)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
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
        # Thirty-one entries. The minimum makes it read as a choice rather
        # than a dropdown that lost its arrow; the maximum is what stops the
        # whole card being sized for the one step that scrolls, which left
        # every other step with an empty lower half.
        area.setMinimumHeight(300)
        area.setMaximumHeight(350)
        area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.language_scrollbar = area.verticalScrollBar()
        self._dress_scrollbar()
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 12, 0)
        grid.setSpacing(8)

        self.language_chips: dict[str, _LanguageChip] = {}
        self._language_group = QButtonGroup(page)
        self._language_group.setExclusive(True)
        for position, (code, native) in enumerate(LANGUAGE_OPTIONS):
            label = self._automatic_label() if code == "auto" else native
            chip = _LanguageChip(code, label, holder)
            chip.clicked.connect(lambda _checked=False, value=code: self._choose_language(value))
            self._language_group.addButton(chip)
            self.language_chips[code] = chip
            grid.addWidget(chip, position // 3, position % 3)
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
        for bar in (self.language_scrollbar, getattr(self, "picker_scrollbar", None)):
            if bar is not None:
                bar.setStyleSheet(sheet)

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
        ):
            card = ThemePreview(value, preview_mode, self._accent, page)
            card.setMinimumHeight(188)
            card.chosen.connect(self._choose_mode)
            self.theme_cards[value] = card
            themes.addWidget(card, 1)
        layout.addLayout(themes)

        labels = QHBoxLayout()
        labels.setSpacing(10)
        self.theme_labels: dict[str, QLabel] = {}
        for value, text in (("system", tr("System")), ("light", tr("Light")), ("dark", tr("Dark"))):
            label = QLabel(text, page)
            label.setObjectName("onboardingCaption")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.theme_labels[value] = label
            labels.addWidget(label, 1)
        layout.addLayout(labels)

        # Accent and density sit side by side. Stacked, they left the lower
        # half of the step empty, and an empty half reads as a step that is
        # still loading.
        below = QHBoxLayout()
        below.setSpacing(26)

        accent_column = QVBoxLayout()
        accent_column.setSpacing(8)
        self.accent_heading = QLabel(tr("Accent color"), page)
        self.accent_heading.setObjectName("onboardingSectionLabel")
        accent_column.addWidget(self.accent_heading)
        accents = QHBoxLayout()
        accents.setSpacing(6)
        self.accent_dots: dict[str, AccentDot] = {}
        for name in theme_module.ACCENTS:
            dot = AccentDot(name, page)
            dot.chosen.connect(self._choose_accent)
            self.accent_dots[name] = dot
            accents.addWidget(dot)
        accents.addStretch(1)
        accent_column.addLayout(accents)
        below.addLayout(accent_column)

        density_column = QVBoxLayout()
        density_column.setSpacing(8)
        self.density_heading = QLabel(tr("Density"), page)
        self.density_heading.setObjectName("onboardingSectionLabel")
        density_column.addWidget(self.density_heading)
        density = QHBoxLayout()
        density.setSpacing(8)
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
        density_column.addLayout(density)
        below.addLayout(density_column)
        below.addStretch(1)
        layout.addLayout(below)
        layout.addStretch(1)
        return page

    def _build_sidebar_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.sidebar_cards: dict[str, SidebarPreview] = {}
        for value, collapsed in (("expanded", False), ("collapsed", True)):
            card = SidebarPreview(value, collapsed, page)
            card.setMinimumHeight(296)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.chosen.connect(self._choose_sidebar)
            self.sidebar_cards[value] = card
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        captions = QHBoxLayout()
        captions.setSpacing(12)
        self.sidebar_labels: dict[str, QLabel] = {}
        for value, text in (("expanded", tr("Expanded")), ("collapsed", tr("Collapsed"))):
            label = QLabel(text, page)
            label.setObjectName("onboardingCaption")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.sidebar_labels[value] = label
            captions.addWidget(label, 1)
        layout.addLayout(captions)
        layout.addStretch(1)
        return page

    def _build_dependencies_step(self) -> QWidget:
        """Two faces: what to install, then watching it install.

        A picker and a terminal cannot both fit in a panel this size, and they
        are not wanted at the same moment anyway. The step shows one, then the
        other.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.dependency_faces = QStackedWidget(page)
        self.dependency_faces.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        picker_face = QWidget()
        picker_layout = QVBoxLayout(picker_face)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.setSpacing(0)
        area = QScrollArea(picker_face)
        area.setObjectName("onboardingScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setMinimumHeight(300)
        area.setMaximumHeight(350)
        area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.picker = ComponentPicker(component_specs())
        self.picker.selection_changed.connect(self._sync_prepare_button)
        area.setWidget(self.picker)
        picker_layout.addWidget(self.picker.header)
        picker_layout.addSpacing(8)
        self.picker_scrollbar = area.verticalScrollBar()
        picker_layout.addWidget(area, 1)
        self.dependency_faces.addWidget(picker_face)

        console_face = QWidget()
        console_layout = QVBoxLayout(console_face)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)
        self.console = MiniConsole(console_face)
        self.console.setMinimumHeight(300)
        self.console.workflow_started.connect(self._preparation_started)
        self.console.workflow_finished.connect(self._preparation_finished)
        console_layout.addWidget(self.console, 1)
        self.dependency_faces.addWidget(console_face)
        layout.addWidget(self.dependency_faces, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.prepare_note = QLabel("", page)
        self.prepare_note.setObjectName("onboardingHint")
        self.prepare_note.setWordWrap(True)
        row.addWidget(self.prepare_note, 1)
        self.prepare_button = QPushButton(tr("Install the basics"), page)
        self.prepare_button.setObjectName("onboardingPrimary")
        self.prepare_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prepare_button.clicked.connect(self.prepare_requested)
        row.addWidget(self.prepare_button)
        layout.addLayout(row)
        return page

    def show_dependency_face(self, name: str) -> None:
        """Swap between the picker and the terminal, with a short fade.

        Qt has no transition on a stack, and a hard cut between two panels
        this size reads as a glitch rather than a change of view.
        """
        index = 1 if name == "console" else 0
        if self.dependency_faces.currentIndex() == index:
            return
        face = self.dependency_faces.widget(index)
        effect = QGraphicsOpacityEffect(face)
        face.setGraphicsEffect(effect)
        self.dependency_faces.setCurrentIndex(index)
        self._face_fade = QPropertyAnimation(effect, b"opacity", self)
        self._face_fade.setDuration(FADE_MS)
        self._face_fade.setStartValue(0.0)
        self._face_fade.setEndValue(1.0)
        self._face_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._face_fade.finished.connect(lambda: face.setGraphicsEffect(None))
        self._face_fade.start()

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
        self.show_dependency_face("console")
        self.prepare_button.setEnabled(False)
        self.prepare_button.setText(tr("Installing…"))
        self._sync_copy()

    def _preparation_finished(self, code: int) -> None:
        self.prepare_button.setEnabled(True)
        if code:
            # Something failed. Back to the picker so it can be tried again,
            # with the terminal a keystroke away on the same step.
            self.show_dependency_face("picker")
        self._sync_prepare_button()
        self._sync_copy()

    def preparation_failed(self, message: str) -> None:
        """Say why the install never started, where the terminal would have been."""
        self.show_dependency_face("picker")
        self._sync_prepare_button()
        self.prepare_note.setText(message)

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

    def _fill_stop_grid(self, page: QWidget) -> None:
        for chip in self.stop_chips:
            self.stop_grid.removeWidget(chip)
            chip.deleteLater()
        self.stop_chips = []
        for position, stop in enumerate(tour_stops()):
            chip = QLabel(f"{position + 1}    {stop.title}", page)
            chip.setObjectName("onboardingStopChip")
            self.stop_chips.append(chip)
            self.stop_grid.addWidget(chip, position // 2, position % 2)

    # ------------------------------------------------------------- choosing

    def _choose_language(self, code: str) -> None:
        self._language = str(code)
        self._sync_language()
        self.language_chosen.emit(self._language)

    def _choose_mode(self, mode: str) -> None:
        self._mode = str(mode)
        self._sync_appearance()
        self.appearance_chosen.emit(self._mode, self._accent, self._density)

    def _choose_accent(self, accent: str) -> None:
        self._accent = str(accent)
        self._sync_appearance()
        self.appearance_chosen.emit(self._mode, self._accent, self._density)

    def _choose_density(self, density: str) -> None:
        self._density = str(density)
        self._sync_appearance()
        self.appearance_chosen.emit(self._mode, self._accent, self._density)

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
             tr("Every choice is applied to the application behind this panel as you make it.")),
            (tr("Choose the sidebar"),
             tr("Wide names every module. Narrow gives the width back to the page.")),
            (tr("Install what the rest of it needs"),
             tr("Most of this application cannot touch the board until a few "
                "tools are in place. This installs them.")),
            (tr("Take the guided tour?"),
             tr("A short walk through the modules, pointing at the real controls.")),
        )
        title, subtitle = headings[self._step]
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.tour_note.setText(
            tr("It stops at each module, says what it is for and what it changes on "
               "the board. You can leave it at any point, and start it again from "
               "Settings whenever you like.")
        )
        self.prepare_note.setText(
            tr("Needs an internet connection and your password. It runs in a "
               "terminal right here, so you can watch exactly what it does. "
               "Kernel and graphics-stack replacements are not in this list; "
               "those stay on the dashboard.")
        )

    def _sync_language(self) -> None:
        for chip in self.language_chips.values():
            chip.setChecked(chip.code == self._language)

    def _sync_appearance(self) -> None:
        for value, card in self.theme_cards.items():
            card.set_selected(value == self._mode)
            card.set_accent(self._accent)
        for name, dot in self.accent_dots.items():
            dot.set_selected(name == self._accent)
            dot.update()
        for value, button in self.density_buttons.items():
            button.setChecked(value == self._density)

    def _sync_sidebar(self) -> None:
        for value, card in self.sidebar_cards.items():
            card.set_selected((value == "collapsed") == self._collapsed)
            card.update()

    # -------------------------------------------------------------- the glass

    def set_backdrop_source(self, source: QWidget | None) -> None:
        """Name the widget whose frosted portrait this panel floats over."""
        self._backdrop_source = source
        self.refresh_backdrop()

    def refresh_backdrop(self) -> None:
        """Re-take the portrait, because the palette underneath just moved.

        Called after every appearance change: the whole point of applying a
        theme live is that the glass shows it.
        """
        self._dress_scrollbar()
        source = self._backdrop_source
        if source is None or source.width() <= 0 or source.height() <= 0:
            self._backdrop = QPixmap()
            self.update()
            return
        if self._refreshing:
            # Grabbing the shell flushes its pending layout, and that comes
            # back here as a resize of this panel. Without this guard the two
            # call each other until the stack runs out.
            return
        self._refreshing = True
        was_enabled = source.isEnabled()
        # A disabled shell grabs as a greyed-out shell, and the user never saw
        # that state — it is an artefact of this panel being up.
        source.setEnabled(True)
        try:
            shot = source.grab()
        finally:
            source.setEnabled(was_enabled)
            self._refreshing = False
        self._backdrop = frosted(shot)
        self.update()

    def retranslate(self) -> None:
        self.brand_note.setText(tr("First steps"))
        for row, label in zip(self.step_rows, self._step_labels()):
            row.set_label(label)
        chip = self.language_chips.get("auto")
        if chip is not None:
            chip.setText(self._automatic_label())
        for value, text in (("system", tr("System")), ("light", tr("Light")), ("dark", tr("Dark"))):
            self.theme_labels[value].setText(text)
        self.accent_heading.setText(tr("Accent color"))
        self.density_heading.setText(tr("Density"))
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
        """Cover the parent and fade in over the frosted shell."""
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        # windowOpacity belongs to windows; this is a child covering one, so
        # the fade goes through an opacity effect and is taken off again at the
        # end, to leave the panel on the plain painting path.
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(lambda: self.setGraphicsEffect(None))
        self._fade.start()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        # The portrait is the size of the window it was taken from, so a resize
        # makes it the wrong one — but only once the resize has settled.
        self._regrab.start()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() == Qt.Key.Key_Escape:
            self._leave(tour=False)
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = theme_module.COLORS
        if self._backdrop.isNull():
            painter.fillRect(self.rect(), QColor(colors["window"]))
        else:
            painter.drawPixmap(self.rect(), self._backdrop)
        scrim = QColor("#0B0F17" if theme_module.ACTIVE_MODE == "dark" else "#F7F9FC")
        scrim.setAlpha(SCRIM_ALPHA.get(theme_module.ACTIVE_MODE, 130))
        painter.fillRect(self.rect(), scrim)
        painter.end()
