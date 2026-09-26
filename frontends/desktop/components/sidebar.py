from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..theme import COLORS
from .widgets import ICON_DIR

APP_LOGO = Path(__file__).resolve().parents[3] / "assets" / "icons" / "bc250-control-center-64.png"

#: Logical size of a row glyph, and the canvas it sits on when the row is
#: expanded: the transparent strip to its right is the gap before the label,
#: which Qt otherwise fixes at four pixels.
GLYPH = 18
EXPANDED_ICON = QSize(26, GLYPH)
COLLAPSED_ICON = QSize(20, 20)


def _pixel_ratios() -> tuple[float, ...]:
    """1x, 2x and every connected screen's own scale (1.25, 1.5...).

    A glyph drawn for the exact ratio is shown pixel for pixel; one scaled
    from another size comes out soft, which is how a thin line icon looks
    blurred at 125 %.
    """
    ratios = {1.0, 2.0}
    app = QGuiApplication.instance()
    if app is not None:
        ratios.update(round(screen.devicePixelRatio(), 2) for screen in QGuiApplication.screens())
    return tuple(sorted(ratio for ratio in ratios if ratio > 0))


def _tinted_glyph(icon_name: str, color: str, canvas: QSize, glyph: int, ratio: float = 1.0) -> QPixmap:
    """The line icon in one flat colour, left-aligned and vertically centred."""
    pixmap = QPixmap(round(canvas.width() * ratio), round(canvas.height() * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    # Rendered from the SVG at this ratio, not scaled from a larger bitmap.
    source = QIcon(str(ICON_DIR / f"{icon_name}.svg")).pixmap(QSize(glyph, glyph), ratio)
    painter = QPainter(pixmap)
    top = (canvas.height() - glyph) // 2
    left = 0 if canvas.width() > canvas.height() else (canvas.width() - glyph) // 2
    painter.drawPixmap(QPointF(left, top), source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(QRectF(0, 0, canvas.width(), canvas.height()), QColor(color))
    painter.end()
    return pixmap


def _tinted_icon(icon_name: str, states: dict[tuple[QIcon.Mode, QIcon.State], str], canvas: QSize, glyph: int) -> QIcon:
    icon = QIcon()
    for ratio in _pixel_ratios():
        for (mode, state), color in states.items():
            icon.addPixmap(_tinted_glyph(icon_name, color, canvas, glyph, ratio), mode, state)
    return icon


def _nav_icon(icon_name: str, tone: str, *, collapsed: bool = False) -> QIcon:
    """Muted at rest, the module's own colour once selected."""
    return _tinted_icon(
        icon_name,
        {
            (QIcon.Mode.Normal, QIcon.State.Off): COLORS["muted"],
            (QIcon.Mode.Active, QIcon.State.Off): COLORS["text"],
            (QIcon.Mode.Normal, QIcon.State.On): COLORS[tone],
            (QIcon.Mode.Active, QIcon.State.On): COLORS[tone],
        },
        COLLAPSED_ICON if collapsed else EXPANDED_ICON,
        GLYPH,
    )


def _control_center_name() -> str:
    """"Control Center" in the interface language, from the full product name.

    Every locale already translates "BC250 Control Center" and keeps "BC250"
    in it, so the second line of the brand needs no string of its own.
    """
    words = tr("BC250 Control Center").replace("BC250", "").strip()
    return (words[:1].upper() + words[1:]) if words else "Control Center"


class SidebarButton(QPushButton):
    """Navigation row for the definitive control-center modules."""

    def __init__(
        self,
        key: str,
        text: str,
        icon_name: str,
        icon_background_key: str,
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self.key = key
        self.source_text = text
        self.full_text = tr(text)
        self.setObjectName("SidebarNavButton")
        self.setCheckable(True)
        self.setProperty("nav", True)
        # The rail translates its own rows (see retranslate): the shared
        # widget-tree pass would put back the whole label over an elided one.
        self.setProperty("i18nLiteral", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._icon_name = icon_name
        # Every module wears the accent chosen in Appearance once selected.
        # Each used to keep a colour of its own (purple for the GPU, orange
        # for the compute units...), so choosing an accent changed the rail
        # for three modules out of eight. ``blue`` is the palette's accent
        # slot, whatever colour the user picked.
        del icon_background_key
        self._tone = "blue"
        self.setProperty("navTone", self._tone)
        self.setIcon(_nav_icon(icon_name, self._tone))
        self.setIconSize(EXPANDED_ICON)
        self.setToolTip(self.full_text)

    def retranslate(self) -> None:
        self.full_text = tr(self.source_text)
        self.setToolTip(self.full_text)
        self._refresh_text()

    def _shown_text(self) -> str:
        """The label as it fits the row: whole, or elided when a translation is too long.

        The rail keeps one width for every language so pages stay aligned, and a
        few translations of "Compute Units" do not fit it. Qt would clip them
        mid-letter; eliding says there is more, and the tooltip holds the rest.
        """
        if bool(self.property("collapsed")):
            return ""
        if not self.isVisible():
            return self.full_text
        option = QStyleOptionButton()
        self.initStyleOption(option)
        contents = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)
        available = contents.width() - self.iconSize().width() - 4
        metrics = self.fontMetrics()
        if available <= 0 or metrics.horizontalAdvance(self.full_text) <= available:
            return self.full_text
        return metrics.elidedText(self.full_text, Qt.TextElideMode.ElideRight, available)

    def _refresh_text(self) -> None:
        text = self._shown_text()
        if text != self.text():
            self.setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._refresh_text()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh_text()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)
        if event.type() in (event.Type.FontChange, event.Type.StyleChange):
            self._refresh_text()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        if not self.isChecked():
            return
        # The selected row carries a short rounded marker on its leading edge.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS[self._tone]))
        height = min(18.0, self.height() - 16.0)
        painter.drawRoundedRect(QRectF(0.0, (self.height() - height) / 2.0, 3.0, height), 1.5, 1.5)
        painter.end()

    def apply_appearance(self) -> None:
        self.setIcon(_nav_icon(self._icon_name, self._tone, collapsed=bool(self.property("collapsed"))))

    def set_collapsed(self, collapsed: bool) -> None:
        self.setProperty("collapsed", collapsed)
        self.setIcon(_nav_icon(self._icon_name, self._tone, collapsed=collapsed))
        self.setIconSize(COLLAPSED_ICON if collapsed else EXPANDED_ICON)
        self.style().unpolish(self)
        self.style().polish(self)
        # Sizes go after the restyle: leaving the collapsed rule makes the
        # style sheet put back the sizes it found before it applied, which
        # dropped every row to its 20 px text height once expanded again.
        if collapsed:
            self.setFixedSize(42, 42)
        else:
            self.setMinimumSize(0, 40)
            self.setMaximumSize(16_777_215, 40)
        self._refresh_text()


class SidebarSection(QWidget):
    """A group caption; a short rule in its place once the rail is collapsed."""

    def __init__(self, source_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.source_text = source_text
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 4)
        layout.setSpacing(0)
        self.label = QLabel(tr(source_text).upper())
        self.label.setObjectName("SidebarSection")
        self.label.setProperty("i18nLiteral", True)
        layout.addWidget(self.label)
        self.rule = QFrame()
        self.rule.setObjectName("SidebarDivider")
        self.rule.setFixedSize(22, 1)
        self.rule.hide()
        layout.addWidget(self.rule, 0, Qt.AlignmentFlag.AlignHCenter)

    def retranslate(self) -> None:
        self.label.setText(tr(self.source_text).upper())

    def set_collapsed(self, collapsed: bool) -> None:
        self.label.setVisible(not collapsed)
        self.rule.setVisible(collapsed)


class Sidebar(QFrame):
    navigation_requested = pyqtSignal(str)
    collapsed_changed = pyqtSignal(bool)

    # Stable dimensions keep the sidebar aligned with every page.
    EXPANDED_WIDTH = 212
    COLLAPSED_WIDTH = 66

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._collapsed = False
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._apply_width_constraints(self.EXPANDED_WIDTH)

        self.root_layout = QVBoxLayout(self)
        layout = self.root_layout
        layout.setContentsMargins(10, 14, 10, 12)
        layout.setSpacing(2)

        # Identity and the collapse control share one row: the product mark,
        # its name, and a chevron that folds the rail to its icons.
        self.brand = QWidget()
        self.brand.setObjectName("SidebarBrand")
        brand_row = QHBoxLayout(self.brand)
        brand_row.setContentsMargins(2, 0, 0, 0)
        brand_row.setSpacing(8)
        self.logo = QLabel()
        self.logo.setObjectName("SidebarLogo")
        self.logo.setFixedSize(30, 30)
        if APP_LOGO.is_file():
            logo = QPixmap(str(APP_LOGO))
            ratio = 2.0
            logo = logo.scaled(
                int(30 * ratio), int(30 * ratio),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setDevicePixelRatio(ratio)
            self.logo.setPixmap(logo)
        brand_row.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignVCenter)
        brand_copy = QVBoxLayout()
        brand_copy.setContentsMargins(0, 0, 0, 0)
        brand_copy.setSpacing(0)
        self.brand_title = QLabel("BC250")
        self.brand_title.setObjectName("BrandTitle")
        self.brand_title.setProperty("i18nLiteral", True)
        self.brand_subtitle = QLabel(_control_center_name())
        self.brand_subtitle.setObjectName("BrandSubtitle")
        self.brand_subtitle.setProperty("i18nLiteral", True)
        # A few languages name it longer than the rail is wide ("Център за
        # управление"); those take a second line rather than lose letters.
        self.brand_subtitle.setWordWrap(True)
        brand_copy.addWidget(self.brand_title)
        brand_copy.addWidget(self.brand_subtitle)
        brand_row.addLayout(brand_copy, 1)

        self.toggle = QPushButton()
        self.toggle.setObjectName("SidebarToggle")
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setToolTip(tr("Collapse sidebar"))
        self.toggle.setFixedSize(24, 28)
        self.toggle.clicked.connect(self.toggle_collapsed)
        brand_row.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.brand)
        layout.addSpacing(12)

        # Shared row geometry for every application module. The order is the
        # one LB/RB cycles through; captions only group what is already there.
        nav_items = [
            ("dashboard", "Dashboard", "nav_dashboard", "blue_soft"),
            ("cpu", "CPU / SMU", "nav_cpu", "blue_soft"),
            ("gpu", "GPU Governor", "nav_gpu", "purple_soft"),
            ("cu", "Compute Units", "nav_compute", "orange_soft"),
            ("performance", "Performance", "nav_performance", "purple_soft"),
            ("fans", "Fans", "nav_fans", "cyan_soft"),
            ("processes", "Processes", "nav_processes", "blue_soft"),
            ("firmware", "Firmware (BIOS)", "nav_firmware", "orange_soft"),
            ("settings", "Settings", "nav_settings", "blue_soft"),
        ]
        section_before = {"cpu": "Hardware", "performance": "Monitoring"}
        self.sections: list[SidebarSection] = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, SidebarButton] = {}
        for key, text, icon_name, icon_background in nav_items:
            button = SidebarButton(key, text, icon_name, icon_background)
            button.clicked.connect(lambda checked=False, item=key: self.navigation_requested.emit(item))
            self.group.addButton(button)
            self.buttons[key] = button
            if key in section_before:
                section = SidebarSection(section_before[key])
                self.sections.append(section)
                layout.addWidget(section)
            if key == "firmware":
                # Something done once in a board's life, not every day: it
                # waits at the bottom, just above the rule, apart from the
                # modules that are opened all the time.
                layout.addStretch(1)
            if key == "settings":
                # Settings closes the rail from the bottom, under a rule.
                self.footer_rule = QFrame()
                self.footer_rule.setObjectName("SidebarDivider")
                self.footer_rule.setFixedHeight(1)
                layout.addWidget(self.footer_rule)
                layout.addSpacing(6)
            layout.addWidget(button)
        self.buttons["dashboard"].setChecked(True)
        self._refresh_toggle()

    def retranslate(self) -> None:
        self.brand_subtitle.setText(_control_center_name())
        self.toggle.setToolTip(tr("Expand sidebar" if self._collapsed else "Collapse sidebar"))
        for section in self.sections:
            section.retranslate()
        for button in self.buttons.values():
            button.retranslate()

    def _refresh_toggle(self) -> None:
        glyph = "expand_gray" if self._collapsed else "collapse_gray"
        size = QSize(18, 18)
        self.toggle.setIcon(_tinted_icon(glyph, {(QIcon.Mode.Normal, QIcon.State.Off): COLORS["muted"]}, size, 18))
        self.toggle.setIconSize(size)

    def apply_appearance(self) -> None:
        for button in self.buttons.values():
            button.apply_appearance()
        self._refresh_toggle()
        self.style().unpolish(self)
        self.style().polish(self)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _apply_width_constraints(self, width: int) -> None:
        width = max(48, int(width))
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)
        self.resize(width, max(1, self.height()))

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        self._apply_width_constraints(self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH)
        side = 12 if collapsed else 10
        self.root_layout.setContentsMargins(side, 14, side, 12)

        # Folded, the rail is too narrow for the mark and the chevron side by
        # side; the chevron stays, centred, as the way back.
        self.logo.setVisible(not collapsed)
        self.brand_title.setVisible(not collapsed)
        self.brand_subtitle.setVisible(not collapsed)
        brand_row = self.brand.layout()
        brand_row.setContentsMargins(0 if collapsed else 2, 0, 0, 0)
        brand_row.setAlignment(
            self.toggle,
            Qt.AlignmentFlag.AlignCenter if collapsed else Qt.AlignmentFlag.AlignVCenter,
        )
        if collapsed:
            self.toggle.setFixedSize(42, 32)
            self.toggle.setToolTip(tr("Expand sidebar"))
        else:
            self.toggle.setFixedSize(24, 28)
            self.toggle.setToolTip(tr("Collapse sidebar"))
        self._refresh_toggle()

        for section in self.sections:
            section.set_collapsed(collapsed)
        for button in self.buttons.values():
            button.set_collapsed(collapsed)
        self.collapsed_changed.emit(collapsed)
