from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..i18n import tr
from ..theme import COLORS
from .widgets import ICON_DIR




def _nav_icon(icon_name: str, background: str) -> QIcon:
    """Compose the vector glyph inside the sidebar navigation tile."""
    canvas_size = 96
    pixmap = QPixmap(canvas_size, canvas_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(background))
    painter.drawRoundedRect(10, 10, 76, 76, 20, 20)

    glyph = QIcon(str(ICON_DIR / f"{icon_name}.svg")).pixmap(QSize(50, 50))
    painter.drawPixmap(23, 23, glyph)
    painter.end()
    return QIcon(pixmap)


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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._icon_name = icon_name
        self._icon_background_key = icon_background_key
        self.setIcon(_nav_icon(icon_name, COLORS[icon_background_key]))
        self.setIconSize(QSize(24, 24))
        self.setToolTip(self.full_text)

    def retranslate(self) -> None:
        self.full_text = tr(self.source_text)
        self.setToolTip(self.full_text)
        self.setText("" if bool(self.property("collapsed")) else self.full_text)

    def apply_appearance(self) -> None:
        self.setIcon(_nav_icon(self._icon_name, COLORS[self._icon_background_key]))

    def set_collapsed(self, collapsed: bool) -> None:
        self.setText("" if collapsed else self.full_text)
        self.setProperty("collapsed", collapsed)
        self.setIconSize(QSize(28, 28) if collapsed else QSize(24, 24))
        if collapsed:
            self.setFixedSize(42, 42)
        else:
            self.setMinimumSize(0, 42)
            self.setMaximumSize(16_777_215, 42)
        self.style().unpolish(self)
        self.style().polish(self)


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
        self._status_card_enabled = True
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._apply_width_constraints(self.EXPANDED_WIDTH)

        self.root_layout = QVBoxLayout(self)
        layout = self.root_layout
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(6)

        # Product identity and navigation controls share one stable hierarchy.
        self.toggle = QPushButton("☰")
        self.toggle.setObjectName("SidebarToggle")
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setToolTip(tr("Collapse sidebar"))
        self.toggle.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self.brand_title = QLabel("BC250 Control\nCenter")
        self.brand_title.setObjectName("BrandTitle")
        self.brand_title.setWordWrap(True)
        self.brand_title.setMinimumHeight(44)
        layout.addWidget(self.brand_title)

        self.brand_subtitle = QLabel("Task Manager")
        self.brand_subtitle.setObjectName("BrandSubtitle")
        layout.addWidget(self.brand_subtitle)
        layout.addSpacing(14)

        # Shared row geometry for every application module.
        nav_items = [
            ("dashboard", "Dashboard", "dashboard_blue", "blue_soft"),
            ("cpu", "CPU / SMU", "cpu_blue", "blue_soft"),
            ("gpu", "GPU Governor", "gpu_purple", "purple_soft"),
            ("cu", "Compute Units", "compute_orange", "orange_soft"),
            ("performance", "Performance", "activity_purple", "purple_soft"),
            ("fans", "Fans", "fan_cyan", "cyan_soft"),
            ("processes", "Processes", "processes_blue", "blue_soft"),
            ("settings", "Settings", "settings_blue", "blue_soft"),
        ]
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, SidebarButton] = {}
        for key, text, icon_name, icon_background in nav_items:
            button = SidebarButton(key, text, icon_name, icon_background)
            button.clicked.connect(lambda checked=False, item=key: self.navigation_requested.emit(item))
            self.group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button)
        self.buttons["dashboard"].setChecked(True)
        layout.addStretch(1)

        self.status_card = QFrame()
        self.status_card.setObjectName("SidebarStatus")
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(10, 9, 10, 9)
        status_layout.setSpacing(2)
        self.status_title = QLabel("System protected")
        self.status_title.setObjectName("SidebarStatusTitle")
        self.status_detail = QLabel("BC250 services ready")
        self.status_detail.setObjectName("SidebarStatusDetail")
        status_layout.addWidget(self.status_title)
        status_layout.addWidget(self.status_detail)
        layout.addWidget(self.status_card)

    def set_status_card_enabled(self, enabled: bool) -> None:
        self._status_card_enabled = bool(enabled)
        self.status_card.setVisible(self._status_card_enabled and not self._collapsed)

    def retranslate(self) -> None:
        self.brand_subtitle.setText(tr("Task Manager"))
        self.status_title.setText(tr("System protected"))
        self.status_detail.setText(tr("BC250 services ready"))
        self.toggle.setToolTip(tr("Expand sidebar" if self._collapsed else "Collapse sidebar"))
        for button in self.buttons.values():
            button.retranslate()

    def apply_appearance(self) -> None:
        for button in self.buttons.values():
            button.apply_appearance()
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
        self.root_layout.setContentsMargins(12, 14, 12, 14)

        self.brand_title.setVisible(not collapsed)
        self.brand_subtitle.setVisible(not collapsed)
        self.status_card.setVisible((not collapsed) and self._status_card_enabled)

        if collapsed:
            self.toggle.setFixedSize(42, 42)
            self.toggle.setText("☰")
            self.toggle.setToolTip(tr("Expand sidebar"))
        else:
            self.toggle.setMinimumSize(0, 0)
            self.toggle.setMaximumSize(16_777_215, 16_777_215)
            self.toggle.setText("☰")
            self.toggle.setToolTip(tr("Collapse sidebar"))

        for button in self.buttons.values():
            button.set_collapsed(collapsed)
        self.collapsed_changed.emit(collapsed)
