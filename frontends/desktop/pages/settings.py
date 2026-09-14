from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import (
    QSettings,
    QSignalBlocker,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure import SystemdUserService
from bc250cc.infrastructure.governor_conflicts import normalize_governor_preference
from bc250cc.platform.init.services import detect_init_manager
from bc250cc.shared.failure_text import describe_failure
from bc250cc.shared.version import __version__

from ..components.buttons import WrappingButton as QPushButton
from ..components.dialogs import center_dialog, enable_adaptive_dialog
from ..components.page_widgets import ConfirmDialog
from ..components.responsive import (
    QT_MAX_SIZE,
    clear_grid,
    configure_responsive_scroll_area,
)
from ..components.widgets import IconBadge, InfoDialog, PillLabel, apply_shadow, icon
from ..core.external_links import open_external_url
from ..core.preferences import application_settings
from ..core.state import state_cache_for
from ..i18n import (
    LANGUAGE_OPTIONS,
    count_label,
    current_language,
    daemon_details,
    localize_widget_tree,
    project_overview,
    tr,
    tr_format,
    translate_history_event,
)
from ..theme import COLORS, application_stylesheet, scale_stylesheet

DAEMON_SERVICE = "bc250-control-centerd.service"
OFFICIAL_REPOSITORIES = (
    ("BC250 Control Center", "movacx/bc250-control-center", "https://github.com/movacx/bc250-control-center"),
    ("cyan-skillfish-governor", "filippor/cyan-skillfish-governor/tree/smu", "https://github.com/filippor/cyan-skillfish-governor/tree/smu"),
    ("Oberon Governor", "mothenjoyer69/oberon-governor", "https://gitlab.com/mothenjoyer69/oberon-governor"),
    ("bc250_smu_oc", "bc250-collective/bc250_smu_oc", "https://github.com/bc250-collective/bc250_smu_oc"),
    ("bc250-cu-live-manager (runtime workflow)", "WinnieLV/bc250-cu-live-manager", "https://github.com/WinnieLV/bc250-cu-live-manager"),
    ("bc250-cu-live-manager SteamOS (runtime workflow)", "F5GO/bc250-cu-live-manager-SteamOS", "https://github.com/F5GO/bc250-cu-live-manager-SteamOS"),
    ("bc250-40cu-unlock", "duggasco/bc250-40cu-unlock", "https://github.com/duggasco/bc250-40cu-unlock"),
    ("bc250-core-unlock (cloned upstream tool)", "rw-r-r-0644/bc250-core-unlock", "https://github.com/rw-r-r-0644/bc250-core-unlock"),
    ("bc250-steamos AMDGPU/RADV workflow", "keyboardspecialist/bc250-steamos", "https://github.com/keyboardspecialist/bc250-steamos"),
    ("GFX1013 fix (official upstream workflow)", "DryhoppedIPA/bc250-gfx1013-fix", "https://github.com/DryhoppedIPA/bc250-gfx1013-fix"),
    ("GFX1013 async compute for Bazzite", "tri3gubki-ops/bc250-async-compute-bazzite", "https://github.com/tri3gubki-ops/bc250-async-compute-bazzite"),
    ("SteamOS real toolkit reference", "rpf16rj/bc250-steamos-real-toolkit", "https://github.com/rpf16rj/bc250-steamos-real-toolkit"),
    ("BC250 toolkit reference", "redbeard1083/bc250-toolkit", "https://github.com/redbeard1083/bc250-toolkit"),
    ("BC250 patched Bazzite image reference", "62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images", "https://github.com/62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images"),
    ("Arch/CachyOS kernel + Mesa/GFX1013 (opt-in workflow)", "MastaG/linux-cachyos-bc250", "https://github.com/MastaG/linux-cachyos-bc250"),
    ("BC250 FSR4 V3 (isolated per-game workflow)", "dmorazasanchez/bc250-fsr4", "https://github.com/dmorazasanchez/bc250-fsr4"),
    ("BC250 live telemetry (VRM sensor read)", "onlinermm/BC250-Telemetry", "https://github.com/onlinermm/BC250-Telemetry"),
    ("BC250 GDDR6 memory temperature (SMU inspection workflow)", "pan-Rijovich/bc250-memory-temperature", "https://github.com/pan-Rijovich/bc250-memory-temperature"),
    ("BC250 Batocera tools reference", "tmghd272/bc250-batocera-tools", "https://github.com/tmghd272/bc250-batocera-tools"),
    ("BC250 ACPI fix", "e-tho/bc250-acpi-fix", "https://github.com/e-tho/bc250-acpi-fix"),
    ("BC250 ACPI fix updated", "mendesrr/bc250-acpi-fix-updated-8c", "https://github.com/mendesrr/bc250-acpi-fix-updated-8c"),
    ("BC250 native mesh shaders reference", "lonewolf0622/BC250-Native-Mesh-Shaders-", "https://github.com/lonewolf0622/BC250-Native-Mesh-Shaders-"),
    ("BC250 memory configuration reference", "fanoush/bc250_memcfg", "https://github.com/fanoush/bc250_memcfg"),
    ("BC250 EFI core unlock reference", "Hexxeh/bc250-efi-core-unlock", "https://github.com/Hexxeh/bc250-efi-core-unlock"),
    ("BC250 UEFI firmware menu reference", "Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script", "https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script"),
    ("nct6687d fan driver", "Fred78290/nct6687d", "https://github.com/Fred78290/nct6687d"),
    ("USB Wi-Fi compatibility reference", "morrownr/USB-WiFi", "https://github.com/morrownr/USB-WiFi"),
    ("CUPS printing reference", "OpenPrinting/cups", "https://github.com/OpenPrinting/cups"),
    ("ipp-usb printing reference", "OpenPrinting/ipp-usb", "https://github.com/OpenPrinting/ipp-usb"),
    ("system-config-printer reference", "OpenPrinting/system-config-printer", "https://github.com/OpenPrinting/system-config-printer"),
    ("foomatic-db printing reference", "OpenPrinting/foomatic-db", "https://github.com/OpenPrinting/foomatic-db"),
    ("PAPPL printing reference", "michaelrsweet/pappl", "https://github.com/michaelrsweet/pappl"),
    ("pappl-retrofit printing reference", "OpenPrinting/pappl-retrofit", "https://github.com/OpenPrinting/pappl-retrofit"),
    ("BlueZ Bluetooth reference", "bluez/bluez", "https://github.com/bluez/bluez"),
)
CONTACT_URL = "https://discord.com/channels/1315924807128449065/1526169299490836510"


def settings_stylesheet() -> str:
    """Settings-specific styling evaluated after the active palette is selected."""
    c = COLORS
    hover = c["control_hover"]
    selected = c["blue_soft"]
    control = c["control"]
    switch_off = c["control_pressed"]
    switch_border = c["border_strong"]
    table_selection = c["blue_soft"]
    return scale_stylesheet(f"""
    QDialog[settingsPage='true'] {{
        background:{c['panel']}; color:{c['text']};
    }}
    QWidget[settingsPage='true'] QFrame[settingsShell='true'] {{
        background:{c['panel']}; border:1px solid {c['border']}; border-radius:16px;
    }}
    QWidget[settingsPage='true'] QFrame[settingsNav='true'] {{
        background:{c['panel_alt']}; border:none; border-right:1px solid {c['border']};
        border-top-left-radius:16px; border-bottom-left-radius:16px;
    }}
    QWidget[settingsPage='true'] QPushButton[settingsNavButton='true'] {{
        text-align:left; padding:9px 11px; border:none; border-radius:10px;
        color:{c['text']}; font-size:12px; font-weight:650; background:transparent;
    }}
    QWidget[settingsPage='true'] QPushButton[settingsNavButton='true']:hover {{ background:{hover}; }}
    QWidget[settingsPage='true'] QPushButton[settingsNavButton='true']:checked {{
        background:{selected}; color:{c['blue']}; border-left:3px solid {c['blue']};
    }}
    QWidget[settingsPage='true'] QFrame[settingsContent='true'] {{
        background:{c['panel']}; border:none; border-top-right-radius:20px; border-bottom-right-radius:20px;
    }}
    QWidget[settingsPage='true'] QLabel[pageTitle='true'] {{
        color:{c['text']}; font-size:24px; font-weight:820;
    }}
    QWidget[settingsPage='true'] QLabel[pageSubtitle='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QWidget[settingsPage='true'] QFrame[banner='true'] {{
        background:{c['panel_alt']}; border:1px solid {c['border_soft']}; border-radius:14px;
    }}
    QWidget[settingsPage='true'] QLabel[bannerTitle='true'] {{
        color:{c['text']}; font-size:13px; font-weight:760;
    }}
    QWidget[settingsPage='true'] QLabel[bannerText='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QWidget[settingsPage='true'] QLabel[groupTitle='true'] {{
        color:{c['muted']}; font-size:10px; font-weight:780;
    }}
    QWidget[settingsPage='true'] QFrame[settingsGroup='true'] {{
        background:{c['panel_alt']}; border:1px solid {c['border_soft']}; border-radius:13px;
    }}
    QWidget[settingsPage='true'] QFrame[settingRow='true'] {{
        background:transparent; border:none; border-bottom:1px solid {c['border_soft']};
    }}
    QWidget[settingsPage='true'] QFrame[repositoryRow='true'] {{
        background:{c['panel_raised']}; border:1px solid {c['border_soft']}; border-radius:11px;
    }}
    QWidget[settingsPage='true'] QFrame[repositoryRow='true']:hover {{
        border-color:{c['border_strong']}; background:{c['control_hover']};
    }}
    QWidget[settingsPage='true'] QLabel[repositoryName='true'] {{
        color:{c['text']}; font-size:12px; font-weight:720;
    }}
    QWidget[settingsPage='true'] QLabel[repositoryAddress='true'] {{
        color:{c['muted']}; font-size:10px; font-family:'Noto Sans Mono','DejaVu Sans Mono',monospace;
    }}
    QWidget[settingsPage='true'] QLabel[repositoryIndex='true'] {{
        color:{c['muted']}; font-size:10px; font-weight:700;
    }}
    QWidget[settingsPage='true'] QLabel[rowTitle='true'] {{
        color:{c['text']}; font-size:12px; font-weight:670;
    }}
    QWidget[settingsPage='true'] QLabel[rowDescription='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QComboBox[settingsCombo='true'] {{
        min-width:190px; min-height:34px; padding:0 36px 0 11px;
        border:1px solid {c['border_strong']}; border-radius:10px;
        background-color:{c['panel_raised']}; color:{c['text']};
        font-size:12px; font-weight:620;
    }}
    QComboBox[settingsCombo='true']:hover {{
        background-color:{c['control_hover']}; border-color:{c['border_strong']};
    }}
    QComboBox[settingsCombo='true']:focus,
    QComboBox[settingsCombo='true']:on {{
        background-color:{c['control']}; border-color:{c['focus']};
    }}
    QComboBox[settingsCombo='true']:disabled {{
        background-color:{c['disabled_bg']}; color:{c['disabled_text']};
        border-color:{c['border_soft']};
    }}
    QComboBox[settingsCombo='true']::drop-down {{
        subcontrol-origin:padding; subcontrol-position:top right;
        width:34px; border:none; background:transparent;
    }}
    QComboBox[settingsCombo='true'] QAbstractItemView,
    QAbstractItemView[settingsComboPopup='true'] {{
        background-color:{c['panel_raised']}; color:{c['text']};
        border:1px solid {c['border_strong']}; border-radius:8px;
        selection-background-color:{table_selection}; selection-color:{c['text']};
        outline:0; padding:4px;
    }}
    QComboBox[settingsCombo='true'] QAbstractItemView::item,
    QAbstractItemView[settingsComboPopup='true']::item {{
        min-height:28px; padding:3px 8px; border:none; border-radius:5px;
        background-color:{c['panel_raised']}; color:{c['text']};
    }}
    QComboBox[settingsCombo='true'] QAbstractItemView::item:hover,
    QAbstractItemView[settingsComboPopup='true']::item:hover {{
        background-color:{c['control_hover']};
    }}
    QComboBox[settingsCombo='true'] QAbstractItemView::item:selected,
    QAbstractItemView[settingsComboPopup='true']::item:selected {{
        background-color:{table_selection}; color:{c['text']};
    }}
    QWidget[settingsPage='true'] QCheckBox[settingsSwitch='true'] {{ spacing:0px; }}
    QWidget[settingsPage='true'] QCheckBox[settingsSwitch='true']::indicator {{
        width:40px; height:22px; border-radius:11px; border:1px solid {switch_border}; background:{switch_off};
    }}
    QWidget[settingsPage='true'] QCheckBox[settingsSwitch='true']::indicator:checked {{
        background:{c['blue']}; border:1px solid {c['blue']};
    }}
    QWidget[settingsPage='true'] QPushButton[ghostAction='true'],
    QWidget[settingsPage='true'] QPushButton[bannerAction='true'] {{
        min-height:34px; padding:0 14px; border-radius:10px; border:1px solid {c['border']};
        background:{control}; color:{c['text']}; font-size:11px; font-weight:680;
    }}
    QWidget[settingsPage='true'] QPushButton[ghostAction='true']:hover,
    QWidget[settingsPage='true'] QPushButton[bannerAction='true']:hover {{
        background:{c['blue_soft']}; border-color:{c['blue']}; color:{c['blue']};
    }}
    QWidget[settingsPage='true'] QPushButton[primaryAction='true'] {{
        min-height:34px; padding:0 15px; border:1px solid {c['blue']}; border-radius:10px;
        background:{c['blue']}; color:{c['on_accent']}; font-size:11px; font-weight:730;
    }}
    QWidget[settingsPage='true'] QLabel[pathValue='true'],
    QWidget[settingsPage='true'] QLineEdit[pathValue='true'] {{
        color:{c['muted']}; font-size:10px; font-family:'Noto Sans Mono','DejaVu Sans Mono',monospace;
    }}
    QWidget[settingsPage='true'] QLineEdit[pathValue='true'] {{
        min-height:30px; padding:0 9px; background:{c['panel_alt']};
        border:1px solid {c['border_soft']}; border-radius:8px;
    }}
    QWidget[settingsPage='true'] QLabel[daemonState='true'] {{
        color:{c['text']}; font-size:12px; font-weight:760;
    }}
    QWidget[settingsPage='true'] QTableWidget[historyTable='true'] {{
        background:{c['panel']}; alternate-background-color:{c['panel_alt']}; color:{c['text']};
        border:1px solid {c['border']}; border-radius:12px; gridline-color:{c['border_soft']};
        selection-background-color:{table_selection}; selection-color:{c['text']}; font-size:10px;
    }}
    QWidget[settingsPage='true'] QTableWidget[historyTable='true']::item {{ padding:5px 7px; border:none; }}
    QWidget[settingsPage='true'] QHeaderView::section {{
        background:{c['panel_alt']}; color:{c['muted']}; border:none; border-bottom:1px solid {c['border']};
        padding:7px 8px; font-size:10px; font-weight:750;
    }}
    QWidget[settingsPage='true'] QPlainTextEdit[aboutText='true'] {{
        background:{c['panel_alt']}; color:{c['text']}; border:1px solid {c['border']};
        border-radius:12px; padding:10px; font-size:11px;
    }}
    QWidget[settingsPage='true'] QLabel[emptyState='true'] {{
        color:{c['muted']}; font-size:11px; padding:14px;
    }}
    QWidget[settingsPage='true'] QFrame[reportHero='true'] {{
        background:{c['panel_alt']}; border:1px solid {c['border']}; border-radius:14px;
    }}
    QWidget[settingsPage='true'] QLabel[reportHeroTitle='true'] {{
        color:{c['text']}; font-size:14px; font-weight:760;
    }}
    QWidget[settingsPage='true'] QLabel[reportHeroText='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QWidget[settingsPage='true'][compactDensity='true'] QPushButton[settingsNavButton='true'] {{
        padding:6px 9px; font-size:11px; border-radius:9px;
    }}
    QWidget[settingsPage='true'][compactDensity='true'] QPushButton[ghostAction='true'],
    QWidget[settingsPage='true'][compactDensity='true'] QPushButton[bannerAction='true'],
    QWidget[settingsPage='true'][compactDensity='true'] QPushButton[primaryAction='true'] {{
        min-height:30px; padding:0 11px;
    }}
    QWidget[settingsPage='true'][compactDensity='true'] QComboBox[settingsCombo='true'] {{
        min-height:30px; padding:0 32px 0 9px;
    }}
    QWidget[settingsPage='true'][compactDensity='true'] QLabel[pageTitle='true'] {{ font-size:20px; }}
    QWidget[settingsPage='true'][compactDensity='true'] QPlainTextEdit[aboutText='true'] {{ padding:8px; }}
    """)


class SettingsNavButton(QPushButton):
    def __init__(self, key: str, text: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("settingsNavButton", True)
        self.setMinimumHeight(40)
        self.setIcon(icon(icon_name))


class ReadOnlyPathField(QLineEdit):
    """Single-line path display that remains usable when the dialog is narrow."""

    def __init__(self, value: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setProperty("pathValue", True)
        self.setClearButtonEnabled(False)
        self.setMinimumWidth(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText(value)

    def setText(self, value: str) -> None:  # noqa: N802 - Qt API name
        text = str(value or "")
        super().setText(text)
        self.setToolTip(text)
        self.setCursorPosition(0)


class ActionGrid(QWidget):
    """Responsive action container that avoids one-line button overflow."""

    def __init__(self, parent: QWidget | None = None, columns: int = 2):
        super().__init__(parent)
        self._preferred_columns = max(1, int(columns))
        self._buttons: list[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802 - follows Qt layout vocabulary
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._buttons.append(widget)
        self._reflow()

    def set_compact(self, compact: bool) -> None:
        gap = 6 if compact else 8
        self._grid.setHorizontalSpacing(gap)
        self._grid.setVerticalSpacing(gap)

    def _column_count(self) -> int:
        width = self.width()
        if width > 0 and width < 520:
            return 1
        return self._preferred_columns

    def _reflow(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        columns = self._column_count()
        for index, widget in enumerate(self._buttons):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow()


class SettingRow(QFrame):
    """Responsive setting row: controls stack below copy before text can clip."""

    def __init__(self, title: str, description: str, control: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("settingRow", True)
        self.control = control
        self._compact = False
        self._stacked = False
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 10, 0, 10)
        self._layout.setHorizontalSpacing(14)
        self._layout.setVerticalSpacing(6)

        copy = QWidget()
        copy.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(2)
        self.title_label = QLabel(tr(title))
        self.title_label.setWordWrap(True)
        self.title_label.setProperty("rowTitle", True)
        self.description_label = QLabel(tr(description))
        self.description_label.setProperty("rowDescription", True)
        self.description_label.setWordWrap(True)
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.description_label)
        self.copy_widget = copy

        control.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(copy, 0, 0)
        self._layout.addWidget(control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._layout.setColumnStretch(0, 1)

    def set_compact(self, compact: bool) -> None:
        self._compact = bool(compact)
        vertical = 7 if compact else 10
        self._layout.setContentsMargins(0, vertical, 0, vertical)
        self._layout.setHorizontalSpacing(10 if compact else 14)
        self._layout.setVerticalSpacing(4 if compact else 6)

    def _use_stacked_layout(self) -> bool:
        control_hint = max(80, self.control.sizeHint().width())
        copy_minimum = 250
        return self.width() > 0 and self.width() < control_hint + copy_minimum + 34

    def _reflow(self) -> None:
        stacked = self._use_stacked_layout()
        if stacked == self._stacked:
            return
        self._layout.removeWidget(self.control)
        if stacked:
            self.control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._layout.addWidget(self.control, 1, 0, 1, 2)
        else:
            self.control.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            self._layout.addWidget(
                self.control,
                0,
                1,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
        self._stacked = stacked
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow()


class SettingsGroup(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        # Keep the group transparent without installing an unscoped local QSS.
        # A local "background:transparent" stylesheet propagates to children in
        # Qt and used to override every settings combo box background and border.
        self.setProperty("settingsGroup", True)
        self.rows: list[SettingRow] = []
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(14, 12, 14, 4)
        self.layout_root.setSpacing(0)
        self.title_label = QLabel(tr(title))
        self.title_label.setProperty("groupTitle", True)
        self.layout_root.addWidget(self.title_label)
        self.layout_root.addSpacing(6)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.layout_root.addLayout(self.body)

    def add_row(self, row: SettingRow) -> None:
        self.rows.append(row)
        self.body.addWidget(row)

    def set_compact(self, compact: bool) -> None:
        self.layout_root.setSpacing(0)
        for row in self.rows:
            row.set_compact(compact)


class SettingsTask(QThread):
    """Run blocking settings/backend operations outside the GUI thread."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, operation, parent: QWidget | None = None):
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation())
        except Exception as error:
            self.failed.emit(str(error))


class TextDetailsDialog(QDialog):
    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(tr(title))
        self.setStyleSheet(application_stylesheet() + settings_stylesheet())
        enable_adaptive_dialog(
            self,
            preferred_width=720,
            preferred_height=580,
            minimum_width=420,
            minimum_height=320,
        )
        self.setProperty("settingsPage", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        editor = QPlainTextEdit()
        editor.setProperty("aboutText", True)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        layout.addWidget(editor, 1)
        close = QPushButton("Close")
        close.setProperty("primaryAction", True)
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        localize_widget_tree(self)


class RepositoriesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(tr("Official repositories"))
        self.setStyleSheet(application_stylesheet() + settings_stylesheet())
        enable_adaptive_dialog(
            self,
            preferred_width=760,
            preferred_height=540,
            minimum_width=460,
            minimum_height=360,
        )
        self.setProperty("settingsPage", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(12)
        header_icon = IconBadge("github", "neutral_soft", 42, radius=12)
        header.addWidget(header_icon)
        header_copy = QVBoxLayout()
        header_copy.setContentsMargins(0, 0, 0, 0)
        header_copy.setSpacing(2)
        header_title = QLabel(tr("Official repositories"))
        header_title.setProperty("bannerTitle", True)
        header_subtitle = QLabel(tr("Build information, local paths, project scope, and official repositories."))
        header_subtitle.setProperty("bannerText", True)
        header_subtitle.setWordWrap(True)
        header_copy.addWidget(header_title)
        header_copy.addWidget(header_subtitle)
        header.addLayout(header_copy, 1)
        count = PillLabel(str(len(OFFICIAL_REPOSITORIES)), "blue")
        count.setToolTip(tr("Official repositories"))
        header.addWidget(count, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        intro = QLabel(
            tr(
                "BC250 Control Center does not own these tools. They are installed, cloned, or used as credited reference implementations according to each integration."
            )
        )
        intro.setWordWrap(True)
        intro.setProperty("bannerText", True)
        layout.addWidget(intro)

        repository_scroll = QScrollArea()
        repository_scroll.setWidgetResizable(True)
        repository_scroll.setFrameShape(QFrame.Shape.NoFrame)
        repository_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        repository_body = QWidget()
        repository_layout = QVBoxLayout(repository_body)
        repository_layout.setContentsMargins(0, 0, 0, 0)
        repository_layout.setSpacing(6)
        repository_scroll.setWidget(repository_body)
        for index, (name, repository, url) in enumerate(OFFICIAL_REPOSITORIES, start=1):
            row = QFrame()
            row.setProperty("repositoryRow", True)
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(12, 8, 10, 8)
            row_layout.setHorizontalSpacing(12)
            index_label = QLabel(f"{index:02d}")
            index_label.setProperty("repositoryIndex", True)
            index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            index_label.setFixedWidth(24)
            copy = QVBoxLayout()
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(1)
            name_label = QLabel(name)
            name_label.setProperty("repositoryName", True)
            address_label = QLabel(repository)
            address_label.setProperty("repositoryAddress", True)
            address_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            copy.addWidget(name_label)
            copy.addWidget(address_label)
            button = QPushButton("Open")
            button.setProperty("ghostAction", True)
            button.setMinimumWidth(88)
            button.clicked.connect(lambda _checked=False, target=url: self._open_repository(target))
            row_layout.addWidget(index_label, 0, 0)
            row_layout.addLayout(copy, 0, 1)
            row_layout.addWidget(button, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.setColumnStretch(1, 1)
            repository_layout.addWidget(row)
        repository_layout.addStretch(1)
        layout.addWidget(repository_scroll, 1)

        note = QLabel("If Firefox reports a locked profile when opened from a terminal, use the buttons in this window or copy the URL into the browser that is already running.")
        note.setProperty("bannerText", True)
        note.setWordWrap(True)
        layout.addWidget(note)
        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton("Close")
        close.setProperty("primaryAction", True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
        localize_widget_tree(self)

    def _open_repository(self, url: str) -> None:
        if QDesktopServices.openUrl(QUrl(url)):
            return
        InfoDialog(
            "Repository could not be opened",
            url,
            icon_name="warning_orange",
            parent=self,
            eyebrow="OFFICIAL REPOSITORY",
            notice="Copy the repository address into the browser that is already running.",
            tone="red",
        ).exec()


class SettingsPage(QWidget):
    section_requested = pyqtSignal(str)
    language_changed = pyqtSignal(str)
    appearance_changed = pyqtSignal(str, str, str)
    scale_changed = pyqtSignal(int)
    smart_alerts_changed = pyqtSignal(bool)
    desktop_notifications_changed = pyqtSignal(bool)
    diagnostics_changed = pyqtSignal(bool)
    sidebar_collapsed_changed = pyqtSignal(bool)
    gamepad_navigation_changed = pyqtSignal(bool)
    gamepad_keypad_changed = pyqtSignal(bool)
    gamepad_keypad_auto_show_changed = pyqtSignal(bool)
    embedded_terminal_changed = pyqtSignal(bool)
    console_auto_hide_changed = pyqtSignal(bool)
    tour_requested = pyqtSignal()

    def __init__(self, controller, *, settings_service, activity_service, app_settings: QSettings | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.settings_service = settings_service
        self.activity_service = activity_service
        self.app_settings = app_settings or application_settings()
        # This page no longer exposes notification controls.  Reset stale
        # values here too, so opening Settings cannot revive an old opt-in.
        self.app_settings.setValue("settings/smart_alerts", "false")
        self.app_settings.setValue("settings/desktop_notifications", "false")
        self.controls: dict[str, QWidget] = {}
        self.setProperty("settingsPage", True)
        if parent is None:
            self.setStyleSheet(settings_stylesheet())

        self._tasks: set[SettingsTask] = set()
        self._daemon_status_busy = False
        self._daemon_config_busy = False
        self._daemon_config_loaded = False
        self._history_busy = False
        self._history_loaded_at = 0.0
        self._health_busy = False
        self._applied_density: str | None = None
        self._state_cache = state_cache_for(controller)
        settings_file = Path(self.app_settings.fileName()).expanduser().resolve()
        self._cached_paths: dict[str, str] = {
            "config": str(settings_file),
            "historial": str(settings_file.parent / "history.jsonl"),
        }
        self._paths_busy = False
        self._paths_loaded = False
        self._daemon_interval_pending: int | None = None
        self._daemon_interval_timer = QTimer(self)
        self._daemon_interval_timer.setSingleShot(True)
        self._daemon_interval_timer.setInterval(250)
        self._daemon_interval_timer.timeout.connect(self._flush_daemon_interval)
        self._setting_rows: list[SettingRow] = []
        self._settings_groups: list[SettingsGroup] = []
        self._action_grids: list[ActionGrid] = []
        self._page_layouts: list[QVBoxLayout] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        shell = QFrame()
        shell.setProperty("settingsShell", True)
        shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        apply_shadow(shell, blur=20, y=4, alpha=12)
        shell_layout = QHBoxLayout(shell)
        self.shell_layout = shell_layout
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        outer.addWidget(shell, 1)

        nav = QFrame()
        nav.setProperty("settingsNav", True)
        self.nav_frame = nav
        nav.setMinimumWidth(184)
        nav.setMaximumWidth(240)
        nav.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        nav_layout = QGridLayout(nav)
        self.nav_layout = nav_layout
        nav_layout.setContentsMargins(12, 14, 12, 14)
        nav_layout.setHorizontalSpacing(6)
        nav_layout.setVerticalSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, SettingsNavButton] = {}
        self.stack = QStackedWidget()

        sections = [
            ("general", "General", "settings_blue"),
            ("appearance", "Appearance", "app_blue"),
            ("telemetry", "Telemetry", "metrics_blue"),
            ("security", "Security", "shield_green"),
            ("reports", "History & reports", "history_blue"),
            ("about", "About", "app_blue"),
        ]
        self.section_order = [key for key, _text, _icon in sections]
        for key, text, icon_name in sections:
            button = SettingsNavButton(key, text, icon_name)
            button.clicked.connect(lambda checked=False, item=key: self.select_section(item))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            nav_layout.addWidget(button, len(self.nav_buttons) - 1, 0)
        nav_layout.setRowStretch(len(sections), 1)

        content_wrap = QFrame()
        self.content_wrap = content_wrap
        content_wrap.setMinimumWidth(0)
        content_wrap.setProperty("settingsContent", True)
        wrap_layout = QVBoxLayout(content_wrap)
        self.content_layout = wrap_layout
        wrap_layout.setContentsMargins(18, 16, 18, 16)
        wrap_layout.setSpacing(10)
        wrap_layout.addWidget(self.stack)

        shell_layout.addWidget(nav)
        shell_layout.addWidget(content_wrap, 1)

        self._initialize_pages()
        self._load_paths_async()
        initial_section = str(self.app_settings.value("settings/current_section", "general"))
        # Migrate the removed System Health destination without leaving the
        # settings dialog on an empty stack page.
        if initial_section not in self.nav_buttons:
            initial_section = "general"
        self.select_section(initial_section)
        localize_widget_tree(self)
        self.apply_density(str(self.app_settings.value("settings/density", "comfortable")))
        self._reflow_shell(980)


    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow_shell(event.size().width())

    def _reflow_shell(self, width: int) -> None:
        compact = width < 760
        if compact == getattr(self, "_shell_compact", False) and self.nav_layout.count():
            return
        self._shell_compact = compact
        clear_grid(self.nav_layout, reset_columns=8, reset_rows=12)
        buttons = [self.nav_buttons[key] for key in self.section_order]
        if compact:
            self.shell_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.nav_frame.setMinimumWidth(0)
            self.nav_frame.setMaximumWidth(QT_MAX_SIZE)
            self.nav_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            # Keep translated labels readable at the minimum dialog width.
            columns = 2
            for index, button in enumerate(buttons):
                button.setMinimumWidth(0)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.nav_layout.addWidget(button, index // columns, index % columns)
            for column in range(columns):
                self.nav_layout.setColumnStretch(column, 1)
            self.content_layout.setContentsMargins(12, 10, 12, 12)
        else:
            self.shell_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.nav_frame.setMinimumWidth(208 if width >= 980 else 184)
            self.nav_frame.setMaximumWidth(240)
            self.nav_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            for index, button in enumerate(buttons):
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.nav_layout.addWidget(button, index, 0)
            self.nav_layout.setColumnStretch(0, 1)
            self.nav_layout.setRowStretch(len(buttons), 1)
            self.content_layout.setContentsMargins(18, 16, 18, 16)
        self.updateGeometry()

    @staticmethod
    def _bool_value(value: object, default: bool = False) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _coded_combo(
        self,
        options: list[tuple[str, object]],
        key: str,
        default: object,
        callback=None,
    ) -> QComboBox:
        combo = QComboBox()
        combo.setProperty("settingsCombo", True)
        popup = combo.view()
        popup.setProperty("settingsComboPopup", True)
        popup.setAutoFillBackground(True)
        popup.viewport().setAutoFillBackground(True)
        combo.setMinimumWidth(180)
        combo.setMaximumWidth(280)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for label, value in options:
            combo.addItem(tr(label), value)
        current = self.app_settings.value(key, default)
        index = combo.findData(current)
        if index < 0:
            index = combo.findData(str(current))
        combo.setCurrentIndex(max(index, 0))

        def changed(_index: int) -> None:
            value = combo.currentData()
            self.app_settings.setValue(key, value)
            if callback is not None:
                callback(value)

        combo.currentIndexChanged.connect(changed)
        self.controls[key] = combo
        return combo

    def _switch(self, key: str, default: bool, callback=None) -> QCheckBox:
        switch = QCheckBox()
        switch.setProperty("settingsSwitch", True)
        switch.setChecked(self._bool_value(self.app_settings.value(key, default), default))

        def changed(checked: bool) -> None:
            self.app_settings.setValue(key, "true" if checked else "false")
            if callback is not None:
                callback(checked)

        switch.toggled.connect(changed)
        self.controls[key] = switch
        return switch

    def _unified_gamepad_keypad_changed(self, enabled: bool) -> None:
        """Keep the legacy auto-show preference aligned with the single UI switch."""
        value = "true" if enabled else "false"
        self.app_settings.setValue("settings/gamepad_keypad_auto_show", value)
        self.gamepad_keypad_changed.emit(enabled)
        self.gamepad_keypad_auto_show_changed.emit(enabled)

    def _button(self, text: str, callback, *, primary: bool = False) -> QPushButton:
        button = QPushButton(tr(text))
        button.setProperty("primaryAction" if primary else "ghostAction", True)
        button.clicked.connect(callback)
        return button

    def _banner(self, title: str, text: str, button_text: str, callback) -> QFrame:
        card = QFrame()
        card.setProperty("banner", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(IconBadge("shield_green", COLORS["green_soft"], 38, radius=11), 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title_label = QLabel(tr(title))
        title_label.setProperty("bannerTitle", True)
        title_label.setWordWrap(True)
        title_label.setMinimumWidth(0)
        text_label = QLabel(tr(text))
        text_label.setProperty("bannerText", True)
        text_label.setWordWrap(True)
        copy.addWidget(title_label)
        copy.addWidget(text_label)
        header.addLayout(copy, 1)
        layout.addLayout(header)
        action = self._button(button_text, callback)
        action.setProperty("bannerAction", True)
        layout.addWidget(action, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_page_frame(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsSectionScroll")
        page_layout.addWidget(scroll, 1)

        body = QWidget()
        body.setObjectName("SettingsSectionBody")
        configure_responsive_scroll_area(scroll, body)
        body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)
        scroll.setWidget(body)

        title_label = QLabel(tr(title))
        title_label.setProperty("pageTitle", True)
        subtitle_label = QLabel(tr(subtitle))
        subtitle_label.setProperty("pageSubtitle", True)
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        self._page_layouts.append(layout)
        return page, layout

    def _initialize_pages(self) -> None:
        """Install lightweight placeholders; build each section on first use."""
        self._page_builders = {
            "general": self._build_general_page,
            "appearance": self._build_appearance_page,
            "telemetry": self._build_telemetry_page,
            "security": self._build_security_page,
            "reports": self._build_reports_page,
            "about": self._build_about_page,
        }
        self._built_sections: set[str] = set()
        for key in self.section_order:
            placeholder = QWidget()
            placeholder.setObjectName(f"SettingsPlaceholder_{key}")
            self.stack.addWidget(placeholder)

    def _ensure_section(self, key: str) -> QWidget | None:
        if key not in self._page_builders:
            return None
        index = self.section_order.index(key)
        if key in self._built_sections:
            return self.stack.widget(index)
        started = time.perf_counter()
        page = self._page_builders[key]()
        placeholder = self.stack.widget(index)
        self.stack.removeWidget(placeholder)
        placeholder.deleteLater()
        self.stack.insertWidget(index, page)
        self._built_sections.add(key)
        localize_widget_tree(page)
        self._apply_density_to_page(
            page,
            str(self.app_settings.value("settings/density", "comfortable")).strip().lower() == "compact",
        )
        if key == "about" and self._paths_loaded:
            self.config_path_field.setText(str(Path(self._path_for("config")).expanduser().resolve().parent))
        if str(os.environ.get("BC250_UI_PERF", "")).strip().lower() in {"1", "true", "yes", "on"}:
            logging.getLogger(__name__).info(
                "UI PERF settings section %s built in %.1f ms",
                key,
                (time.perf_counter() - started) * 1000.0,
            )
        return page

    def _build_general_page(self) -> QWidget:
        page, layout = self._build_page_frame(
            "General",
            "Configure the default behavior of the control center and how the workspace resumes between sessions.",
        )
        group = SettingsGroup("Workspace")
        group.add_row(SettingRow(
            "Start page",
            "Choose the module to open by default.",
            self._coded_combo([
                ("Dashboard", "dashboard"), ("CPU / SMU", "cpu"), ("GPU Governor", "gpu"),
                ("Compute Units", "cu"), ("Performance", "performance"), ("Fans", "fans"),
                ("Processes", "processes"), ("Settings", "settings"),
            ], "settings/start_page", "dashboard"),
        ))
        try:
            governor_preference = str(
                self.settings_service.read_local_config().get("gpu_governor", "auto")
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            governor_preference = "auto"
        self.app_settings.setValue("settings/gpu_governor", governor_preference)
        group.add_row(SettingRow(
            "GPU governor backend",
            "Only one GPU governor can be enabled at a time. Preparing another governor will ask before stopping the active one.",
            self._coded_combo(
                [
                    ("Automatic detection", "auto"),
                    ("Cyan Skillfish Governor (SMU)", "cyan-skillfish-governor-smu"),
                    ("Oberon Governor", "oberon-governor"),
                ],
                "settings/gpu_governor",
                governor_preference,
                self._gpu_governor_changed,
            ),
        ))
        group.add_row(SettingRow(
            "Reopen last module",
            "Restore the last visited module when the application starts.",
            self._switch("settings/reopen_last_module", True),
        ))
        group.add_row(SettingRow(
            "Collapsed sidebar at launch",
            "Open the main navigation in compact mode.",
            self._switch("sidebar_collapsed", False, self.sidebar_collapsed_changed.emit),
        ))
        group.add_row(SettingRow(
            "Guided tour",
            "Walk through the modules again, with each stop pointing at the control it describes.",
            self._button("Start the tour", self.tour_requested.emit),
        ))
        group.add_row(SettingRow(
            "Gamepad navigation",
            "Detect controllers automatically and show controller hints while active.",
            self._switch("settings/gamepad_navigation", True, self.gamepad_navigation_changed.emit),
        ))
        group.add_row(SettingRow(
            "Automatic gamepad keypad",
            "Show the on-screen keypad automatically when a gamepad focuses an editable field.",
            self._switch(
                "settings/gamepad_onscreen_keypad",
                True,
                self._unified_gamepad_keypad_changed,
            ),
        ))
        group.add_row(SettingRow(
            "Terminal inside the window",
            "Run workflows in a panel at the bottom of the window instead of opening a separate terminal window.",
            self._switch(
                "settings/embedded_terminal", True, self.embedded_terminal_changed.emit
            ),
        ))
        group.add_row(SettingRow(
            "Hide the terminal when a workflow finishes without errors",
            "A workflow that fails keeps the terminal open so its output can be read.",
            self._switch(
                "settings/console_auto_hide", True, self.console_auto_hide_changed.emit
            ),
        ))
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _gpu_governor_changed(self, value: object) -> None:
        normalized = normalize_governor_preference(value)
        try:
            previous = normalize_governor_preference(
                self.settings_service.read_local_config().get("gpu_governor", "auto")
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            previous = "auto"
        if normalized == previous:
            return

        def restore_previous() -> None:
            self.app_settings.setValue("settings/gpu_governor", previous)
            combo = self.controls.get("settings/gpu_governor")
            if isinstance(combo, QComboBox):
                with QSignalBlocker(combo):
                    combo.setCurrentIndex(max(0, combo.findData(previous)))

        # Automatic is only a preference: it follows current evidence and never
        # changes a service. Explicit choices use the single safe transition.
        if normalized == "auto":
            try:
                self.settings_service.save_local_config({"gpu_governor": normalized})
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                restore_previous()
                raise
            self._state_cache.invalidate("config", "tools", "gpu", "performance")
            return

        confirmation = ConfirmDialog(
            "Switch GPU governor safely",
            "Only one GPU governor can be enabled at a time. Preparing another governor will ask before stopping the active one.",
            summary=(
                ("Selected governor", normalized),
                ("Action", "Enable and start"),
            ),
            confirm_text="Disable conflict and enable service",
            tone="red",
            parent=self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            restore_previous()
            return

        combo = self.controls.get("settings/gpu_governor")

        def success(_result: object) -> None:
            try:
                self.settings_service.save_local_config({"gpu_governor": normalized})
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
                restore_previous()
                InfoDialog(
                    "Settings could not be saved",
                    str(error),
                    icon_name="warning_orange",
                    parent=self,
                    eyebrow="GPU GOVERNOR",
                    notice="The governor workflow was opened, but the selection was restored because its local setting could not be saved.",
                    tone="red",
                ).exec()
                return
            self._state_cache.invalidate("config", "tools", "gpu", "performance")

        def failure(message: str) -> None:
            restore_previous()
            InfoDialog(
                "GPU governor switch failed",
                message,
                icon_name="warning_orange",
                parent=self,
                eyebrow="GPU GOVERNOR",
                notice="The selected service was not changed by the application.",
                tone="red",
            ).exec()

        self._start_task(
            lambda: self.controller.cambiar_governor(normalized),
            success,
            failure,
            controls=(combo,) if isinstance(combo, QWidget) else (),
        )

    def _build_appearance_page(self) -> QWidget:
        # Appearance and language
        page, layout = self._build_page_frame(
            "Appearance",
            "Visual density, color, and language preferences for the interface.",
        )
        group = SettingsGroup("Interface")
        group.add_row(SettingRow(
            "Theme",
            "Follow the system theme, use the light palette, or switch to the neutral graphite dark palette.",
            self._coded_combo(
                [("System", "system"), ("Light", "light"), ("Dark", "dark")],
                "settings/appearance", "system", self._appearance_control_changed,
            ),
        ))
        group.add_row(SettingRow(
            "Density",
            "Adjust spacing and row compactness for technical panels.",
            self._coded_combo(
                [("Comfortable", "comfortable"), ("Compact", "compact")],
                "settings/density", "comfortable", self._appearance_control_changed,
            ),
        ))
        group.add_row(SettingRow(
            "Interface scale",
            "Scale fonts, controls, spacing, and technical panels from 70% to 150%.",
            self._coded_combo(
                [(f"{value}%", value) for value in range(70, 151, 10)],
                "settings/scale", 100, lambda value: self.scale_changed.emit(int(value)),
            ),
        ))
        group.add_row(SettingRow(
            "Accent color",
            "Select the main interface accent used across modules.",
            self._coded_combo(
                [("Blue", "blue"), ("Violet", "violet"), ("Cyan", "cyan"), ("Green", "green"), ("Orange", "orange")],
                "settings/accent", "blue", self._appearance_control_changed,
            ),
        ))
        group.add_row(SettingRow(
            "Language",
            "Set the interface language. The change is applied immediately to the interface and its dialogs.",
            self._coded_combo([(name, code) for code, name in LANGUAGE_OPTIONS], "settings/language", "auto", self._language_control_changed),
        ))
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_telemetry_page(self) -> QWidget:
        # Telemetry and optional daemon
        page, layout = self._build_page_frame(
            "Telemetry",
            "Sampling, refresh cadence, passive monitoring, and the optional user daemon.",
        )
        daemon_group = SettingsGroup("Optional daemon")
        self.daemon_status_label = QLabel("Checking…")
        self.daemon_status_label.setProperty("daemonState", True)
        daemon_group.add_row(SettingRow(
            "Daemon status",
            "Current user-service state for bc250-control-centerd.",
            self.daemon_status_label,
        ))
        daemon_interval = int(self.app_settings.value("settings/daemon_interval", 2) or 2)
        self.app_settings.setValue("settings/daemon_interval", daemon_interval)
        daemon_group.add_row(SettingRow(
            "Sampling interval",
            "Controls the conservative monitoring loop used while the optional service is running.",
            self._coded_combo(
                [("1 second", 1), ("2 seconds", 2), ("5 seconds", 5), ("10 seconds", 10)],
                "settings/daemon_interval", daemon_interval, self._save_daemon_interval,
            ),
        ))
        layout.addWidget(daemon_group)

        daemon_card = QFrame()
        daemon_card.setProperty("banner", True)
        daemon_layout = QVBoxLayout(daemon_card)
        daemon_layout.setContentsMargins(14, 12, 14, 12)
        daemon_layout.setSpacing(8)
        daemon_text = QLabel(
            "The optional user daemon records JSONL metrics and restores the saved fan mode after login: "
            "either an enabled automatic GPU-temperature curve or a named fixed-speed preset. "
            "The manual fan slider does not persist by itself. It never applies CPU or GPU overclock automatically."
        )
        daemon_text.setProperty("bannerText", True)
        daemon_text.setWordWrap(True)
        daemon_layout.addWidget(daemon_text)
        daemon_actions = ActionGrid(columns=2)
        self.daemon_refresh_button = self._button("Refresh status", self.refresh_daemon_status)
        self.daemon_enable_button = self._button("Enable daemon", lambda: self._change_daemon(True))
        self.daemon_disable_button = self._button("Disable daemon", lambda: self._change_daemon(False))
        daemon_actions.addWidget(self.daemon_refresh_button)
        daemon_actions.addWidget(self.daemon_enable_button)
        daemon_actions.addWidget(self.daemon_disable_button)
        daemon_actions.addWidget(self._button("View daemon details", self._show_daemon_details))
        daemon_layout.addWidget(daemon_actions)
        self._action_grids.append(daemon_actions)
        layout.addWidget(daemon_card)
        layout.addStretch(1)
        return page

    def _build_notifications_page(self) -> QWidget:
        # Kept for a future feature branch, but deliberately unreachable from
        # the navigation and incapable of re-enabling notifications.
        self.app_settings.setValue("settings/smart_alerts", "false")
        self.app_settings.setValue("settings/desktop_notifications", "false")
        page, layout = self._build_page_frame(
            "Notifications",
            "Notifications are currently disabled.",
        )
        group = SettingsGroup("Safety monitoring")
        group.add_row(SettingRow(
            "Smart safety alerts",
            "This reserved feature is disabled and cannot run.",
            PillLabel("Disabled", "gray"),
        ))
        group.add_row(SettingRow(
            "Desktop notifications",
            "Desktop notification delivery is disabled.",
            PillLabel("Disabled", "gray"),
        ))
        group.add_row(SettingRow(
            "Operation results",
            "Success, failure, and mandatory safety confirmation dialogs are always shown.",
            PillLabel("Always shown", "green"),
        ))
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_security_page(self) -> QWidget:
        # Security policies remain mandatory. The page documents the behavior
        # without presenting controls that could falsely imply safety bypasses.
        page, layout = self._build_page_frame(
            "Security",
            "Confirmation policy for privileged or hardware-impacting actions.",
        )
        diagnostic_group = SettingsGroup("Diagnostic privacy")
        diagnostic_group.add_row(SettingRow(
            "Detailed diagnostics",
            "Show complete device and configuration paths in technical diagnostic panels.",
            self._switch("settings/detailed_diagnostics", False, self.diagnostics_changed.emit),
        ))
        layout.addWidget(diagnostic_group)
        group = SettingsGroup("Protection policy")
        group.add_row(SettingRow("CPU changes", "A confirmation is required before sending CPU frequency or voltage changes.", PillLabel("Required", "orange")))
        group.add_row(SettingRow("GPU changes", "A confirmation is required before GPU ranges, service actions, or voltage curves are applied.", PillLabel("Required", "orange")))
        group.add_row(SettingRow("Fan writes", "A confirmation is required before explicit PWM writes are authorized.", PillLabel("Required", "orange")))
        group.add_row(SettingRow("Process termination", "A confirmation is required before selected workloads are closed.", PillLabel("Required", "orange")))
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_reports_page(self) -> QWidget:
        page, layout = self._build_page_frame(
            "History & reports",
            "Review application activity and export recorded performance data.",
        )

        hero = QFrame()
        hero.setProperty("reportHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 12, 14, 12)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(IconBadge("history_blue", COLORS["orange_soft"], 38, radius=11))
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(2)
        hero_title = QLabel(tr("Metrics report"))
        hero_title.setProperty("reportHeroTitle", True)
        hero_text = QLabel(tr("Export recorded samples as a spreadsheet-ready CSV file."))
        hero_text.setProperty("reportHeroText", True)
        hero_text.setWordWrap(True)
        hero_copy.addWidget(hero_title)
        hero_copy.addWidget(hero_text)
        hero_layout.addLayout(hero_copy, 1)
        self.metrics_csv_button = self._button(
            "Export metrics as CSV", lambda: self._export_runtime_metrics("csv"), primary=True
        )
        hero_layout.addWidget(self.metrics_csv_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(hero)

        history_header = QHBoxLayout()
        history_header.setSpacing(10)
        history_title = QLabel(tr("Recent activity"))
        history_title.setProperty("groupTitle", True)
        history_header.addWidget(history_title)
        self.history_count = PillLabel("0 events", "blue")
        history_header.addWidget(self.history_count)
        history_header.addStretch(1)
        layout.addLayout(history_header)
        toolbar = ActionGrid(columns=3)
        self.history_refresh_button = self._button("Refresh", lambda: self.refresh_history(force=True), primary=True)
        toolbar.addWidget(self.history_refresh_button)
        toolbar.addWidget(self._button("Clear history", self._clear_history))
        toolbar.addWidget(self._button("Open history folder", self._open_history_folder))
        layout.addWidget(toolbar)
        self._action_grids.append(toolbar)

        self.history_table = QTableWidget(0, 4)
        self.history_table.setProperty("historyTable", True)
        self.history_table.setHorizontalHeaderLabels(["Date", "Level", "Event", "Details"])
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setShowGrid(False)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.verticalHeader().setDefaultSectionSize(32)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.setMinimumHeight(330)
        layout.addWidget(self.history_table, 1)
        return page

    def _build_health_page(self) -> QWidget:
        page, layout = self._build_page_frame(
            "BC250 System Health",
            "Validate community tools, privileged helpers, services, configuration files, and distribution-specific integration.",
        )
        summary = QFrame()
        summary.setProperty("banner", True)
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(10)
        summary_layout.addWidget(IconBadge("shield_green", COLORS["green_soft"], 38, radius=11))
        summary_copy = QVBoxLayout()
        summary_copy.setSpacing(2)
        self.health_summary_title = QLabel(tr("Not checked yet"))
        self.health_summary_title.setProperty("bannerTitle", True)
        self.health_summary_detail = QLabel(tr("Run the health check to inspect this BC250 installation."))
        self.health_summary_detail.setProperty("bannerText", True)
        self.health_summary_detail.setWordWrap(True)
        summary_copy.addWidget(self.health_summary_title)
        summary_copy.addWidget(self.health_summary_detail)
        summary_layout.addLayout(summary_copy, 1)
        layout.addWidget(summary)

        actions = ActionGrid(columns=3)
        self.health_check_button = self._button("Run health check", self._run_health_check, primary=True)
        self.health_repair_button = self._button("Repair installation", self._repair_health)
        self.health_report_button = self._button("Generate diagnostic report", self._generate_diagnostic_report)
        actions.addWidget(self.health_check_button)
        actions.addWidget(self.health_repair_button)
        actions.addWidget(self.health_report_button)
        self._action_grids.append(actions)
        layout.addWidget(actions)

        recovery_group = SettingsGroup("Recovery readiness")
        recovery_actions = ActionGrid(columns=3)
        self.recovery_create_button = self._button(
            "Create snapshot", self._create_recovery_snapshot
        )
        self.recovery_inventory_button = self._button(
            "Inspect snapshots", self._inspect_recovery_snapshots
        )
        self.recovery_export_button = self._button(
            "Export latest", self._export_latest_recovery_snapshot
        )
        recovery_actions.addWidget(self.recovery_create_button)
        recovery_actions.addWidget(self.recovery_inventory_button)
        recovery_actions.addWidget(self.recovery_export_button)
        recovery_group.add_row(
            SettingRow(
                "Recovery snapshots",
                "Capture curated BC250 configuration files or inspect verified, non-executing restore plans. System restore is not enabled.",
                recovery_actions,
            )
        )
        layout.addWidget(recovery_group)
        self._action_grids.append(recovery_actions)

        self.health_table = QTableWidget(0, 4)
        self.health_table.setProperty("historyTable", True)
        self.health_table.setHorizontalHeaderLabels([
            tr("State"), tr("Component"), tr("Details"), tr("Repair guidance")
        ])
        self.health_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.health_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.health_table.setAlternatingRowColors(True)
        header = self.health_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.health_table.verticalHeader().setVisible(False)
        self.health_table.setMinimumHeight(420)
        layout.addWidget(self.health_table, 1)
        QTimer.singleShot(0, self._run_health_check)
        return page

    def _build_about_page(self) -> QWidget:
        # About
        page, layout = self._build_page_frame(
            "About",
            "Build information, local paths, project scope, and official repositories.",
        )
        group = SettingsGroup("Application")
        group.add_row(SettingRow("Application", "Product name of the current interface.", PillLabel("BC250 Control Center", "blue")))
        group.add_row(SettingRow("Version", "Exact application release identity.", PillLabel(__version__, "gray")))
        group.add_row(SettingRow("Backend", "Indicates whether the validated hardware backend is connected.", PillLabel("Connected", "green")))
        self.config_path_field = ReadOnlyPathField(str(Path(self._path_for("config")).expanduser().resolve().parent))
        group.add_row(SettingRow("Configuration folder", "Shared application configuration used by the GUI and optional daemon.", self.config_path_field))
        layout.addWidget(group)

        about_box = QFrame()
        about_box.setProperty("banner", True)
        box_layout = QVBoxLayout(about_box)
        box_layout.setContentsMargins(14, 12, 14, 12)
        box_layout.setSpacing(8)
        text = QLabel("BC250 Control Center is a graphical interface for managing, preparing, and monitoring community tools for the AMD BC-250 board.")
        text.setProperty("bannerText", True)
        text.setWordWrap(True)
        box_layout.addWidget(text)
        action_row = ActionGrid(columns=2)
        action_row.addWidget(self._button("Project overview", self._show_project_overview))
        action_row.addWidget(self._button("Official repositories", self._show_repositories))
        action_row.addWidget(self._button("Open settings folder", self._open_settings_folder))
        action_row.addWidget(self._button("Reset interface preferences", self._reset_preferences))
        action_row.addWidget(self._button("Update application", self._update_application, primary=True))
        action_row.addWidget(self._button("Report a problem / Contact", self._open_contact))
        box_layout.addWidget(action_row)
        self._action_grids.append(action_row)
        layout.addWidget(about_box)
        layout.addStretch(1)
        return page

    def has_running_tasks(self) -> bool:
        return any(task.isRunning() for task in self._tasks)

    def _appearance_values(self) -> tuple[str, str, str]:
        mode = str(self.app_settings.value("settings/appearance", "system"))
        accent = str(self.app_settings.value("settings/accent", "blue"))
        density = str(self.app_settings.value("settings/density", "comfortable"))
        return mode, accent, density

    def _appearance_control_changed(self, _value: object) -> None:
        mode, accent, density = self._appearance_values()
        self.apply_density(density)
        self.appearance_changed.emit(mode, accent, density)

    def _language_control_changed(self, value: object) -> None:
        self.language_changed.emit(str(value))

    def _load_daemon_config(self) -> None:
        if self._daemon_config_loaded or self._daemon_config_busy:
            return
        self._daemon_config_busy = True

        def operation() -> object:
            return self._state_cache.config()

        def success(payload: object) -> None:
            self._daemon_config_busy = False
            self._daemon_config_loaded = True
            config = payload if isinstance(payload, dict) else {}
            try:
                interval = max(1, int(config.get("daemon_interval_seconds", 2) or 2))
            except (TypeError, ValueError):
                interval = 2
            self.app_settings.setValue("settings/daemon_interval", interval)
            control = self.controls.get("settings/daemon_interval")
            if isinstance(control, QComboBox):
                blocker = QSignalBlocker(control)
                index = control.findData(interval)
                if index >= 0:
                    control.setCurrentIndex(index)
                del blocker

        def failure(_message: str) -> None:
            self._daemon_config_busy = False
            self._daemon_config_loaded = True

        self._start_task(operation, success, failure)

    def _save_daemon_interval(self, value: object) -> None:
        try:
            self._daemon_interval_pending = max(1, int(value))
        except (TypeError, ValueError):
            return
        self._daemon_interval_timer.start()

    def _flush_daemon_interval(self) -> None:
        interval = self._daemon_interval_pending
        self._daemon_interval_pending = None
        if interval is None:
            return

        def operation() -> object:
            self.settings_service.save_local_config({"daemon_interval_seconds": interval})
            return interval

        def success(_result: object) -> None:
            self._state_cache.invalidate("config")

        def failure(message: str) -> None:
            InfoDialog(
                "Settings could not be saved",
                message,
                icon_name="warning_orange",
                parent=self,
                eyebrow="SETTINGS",
                notice="No hardware command was executed.",
                tone="red",
            ).exec()

        self._start_task(operation, success, failure)

    def _start_task(self, operation, on_success, on_error, *, controls: tuple[QWidget, ...] = ()) -> None:
        task = SettingsTask(operation, QApplication.instance())
        self._tasks.add(task)
        for control in controls:
            control.setEnabled(False)

        def finish_controls() -> None:
            for control in controls:
                control.setEnabled(True)

        def succeeded(result: object) -> None:
            finish_controls()
            on_success(result)

        def failed(message: str) -> None:
            finish_controls()
            on_error(message)

        def cleanup() -> None:
            self._tasks.discard(task)
            task.deleteLater()

        task.succeeded.connect(succeeded)
        task.failed.connect(failed)
        task.finished.connect(cleanup)
        task.start()

    @staticmethod
    def _systemctl_state(value: str, *, active: bool) -> str:
        normalized = str(value or "").strip().lower()
        active_states = {
            "active": "Active", "inactive": "Inactive", "failed": "Failed",
            "activating": "Starting", "deactivating": "Stopping",
        }
        enabled_states = {
            "enabled": "Enabled", "enabled-runtime": "Enabled for this session",
            "disabled": "Disabled", "static": "Static", "indirect": "Indirect",
            "masked": "Masked", "masked-runtime": "Masked for this session",
            "generated": "Generated", "transient": "Transient",
            "not-found": "Not installed", "unknown": "Unknown",
        }
        return (active_states if active else enabled_states).get(normalized, "Unknown")

    def _daemon_command(self, *arguments: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
        # The optional daemon is intentionally a systemd --user service in
        # this release.  On another init host `systemctl` may still be installed,
        # but invoking it would produce a confusing bus error and offer a
        # persistence path we do not support.
        if detect_init_manager().kind != "systemd":
            raise RuntimeError(tr(
                "The optional daemon requires an active systemd user manager; live hardware monitoring in the open application remains available."
            ))
        try:
            return SystemdUserService().command(*arguments, timeout=timeout)
        except RuntimeError as error:
            raise RuntimeError(tr(str(error))) from error

    def refresh_daemon_status(self) -> None:
        if not hasattr(self, "daemon_status_label") or self._daemon_status_busy:
            return
        self._daemon_status_busy = True
        self.daemon_status_label.setText(tr("Checking…"))
        controls = tuple(
            control for control in (
                getattr(self, "daemon_refresh_button", None),
                getattr(self, "daemon_enable_button", None),
                getattr(self, "daemon_disable_button", None),
            ) if isinstance(control, QWidget)
        )

        def operation() -> dict[str, object]:
            active = self._daemon_command("is-active", DAEMON_SERVICE, timeout=5)
            enabled = self._daemon_command("is-enabled", DAEMON_SERVICE, timeout=5)
            active_raw = active.stdout.strip() or active.stderr.strip() or "unknown"
            enabled_raw = enabled.stdout.strip() or enabled.stderr.strip() or "unknown"
            return {
                "active": active_raw,
                "enabled": enabled_raw,
                "active_code": active.returncode,
                "enabled_code": enabled.returncode,
            }

        def success(payload: object) -> None:
            self._daemon_status_busy = False
            data = payload if isinstance(payload, dict) else {}
            active_raw = str(data.get("active") or "unknown")
            enabled_raw = str(data.get("enabled") or "unknown")
            active_label = self._systemctl_state(active_raw, active=True)
            enabled_label = self._systemctl_state(enabled_raw, active=False)
            self.daemon_status_label.setText(f"{tr(active_label)} · {tr(enabled_label)}")
            self.daemon_status_label.setToolTip(
                tr("{service}\nactive: {active}\nenabled: {enabled}").format(
                    service=DAEMON_SERVICE, active=active_raw, enabled=enabled_raw
                )
            )
            self.daemon_status_label.setMinimumWidth(0)

        def failure(message: str) -> None:
            self._daemon_status_busy = False
            self.daemon_status_label.setText(tr("Unavailable"))
            self.daemon_status_label.setToolTip(message)
            # This is a capability result, not a transient monitoring error:
            # do not leave OpenRC users with clickable controls that can only
            # fail through systemctl --user.
            if detect_init_manager().kind != "systemd":
                for control in controls:
                    control.setEnabled(False)

        self._start_task(operation, success, failure, controls=controls)

    def _change_daemon(self, enable: bool) -> None:
        action_text = "Enable optional daemon" if enable else "Disable optional daemon"
        message = (
            "This runs systemctl --user enable --now bc250-control-centerd.service. The daemon records telemetry and restores an enabled automatic fan curve or named fixed-speed preset after login. The manual slider is temporary and is not restored. It does not apply overclock automatically."
            if enable else
            "This stops and disables bc250-control-centerd.service for the current user. Saved configuration and history files are preserved."
        )
        dialog = ConfirmDialog(
            action_text,
            message,
            summary=(("Service", DAEMON_SERVICE), ("Scope", "Monitoring, JSONL metrics, and saved GPU fan curve")),
            confirm_text=action_text,
            tone="blue" if enable else "orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        arguments = ("enable", "--now", DAEMON_SERVICE) if enable else ("disable", "--now", DAEMON_SERVICE)
        controls = tuple(
            control for control in (
                getattr(self, "daemon_refresh_button", None),
                getattr(self, "daemon_enable_button", None),
                getattr(self, "daemon_disable_button", None),
            ) if isinstance(control, QWidget)
        )
        self.daemon_status_label.setText(tr("Working"))

        def operation() -> str:
            result = self._daemon_command(*arguments, timeout=25)
            output = (result.stdout or result.stderr or "").strip()
            if result.returncode != 0:
                raise RuntimeError(describe_failure(result.returncode, output, ""))
            return output

        def success(payload: object) -> None:
            self.refresh_daemon_status()
            output = str(payload or "")
            InfoDialog(
                "Command completed",
                output or ("The optional daemon is enabled." if enable else "The optional daemon is disabled."),
                icon_name="shield_green",
                parent=self,
                eyebrow="OPTIONAL DAEMON",
                notice="No CPU or GPU overclock was applied.",
                tone="green",
            ).exec()

        def failure(message_text: str) -> None:
            self.refresh_daemon_status()
            InfoDialog(
                "Command failed",
                message_text,
                icon_name="warning_orange",
                parent=self,
                eyebrow="OPTIONAL DAEMON",
                notice="No additional command will be attempted automatically.",
                tone="red",
            ).exec()

        self._start_task(operation, success, failure, controls=controls)

    def _show_daemon_details(self) -> None:
        TextDetailsDialog("Optional daemon", daemon_details(), self).exec()

    def _paths(self) -> dict[str, str]:
        # state_cache.paths() delegates to SettingsService once and
        # reuses the immutable path mapping for subsequent open actions.
        return dict(self._cached_paths)

    def _load_paths_async(self) -> None:
        if self._paths_busy or self._paths_loaded:
            return
        self._paths_busy = True

        def success(payload: object) -> None:
            self._paths_busy = False
            self._paths_loaded = True
            if isinstance(payload, dict):
                self._cached_paths.update({str(key): str(value) for key, value in payload.items() if value})
            if hasattr(self, "config_path_field"):
                self.config_path_field.setText(str(Path(self._path_for("config")).expanduser().resolve().parent))

        def failure(_message: str) -> None:
            self._paths_busy = False
            self._paths_loaded = True

        self._start_task(self._state_cache.paths, success, failure)

    def _path_for(self, key: str) -> str:
        value = self._paths().get(key)
        if value:
            return value
        if key == "config":
            return str(Path(self.app_settings.fileName()).resolve())
        return str(Path(self.app_settings.fileName()).resolve().parent)

    def _open_directory(self, path: Path, label: str) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
            if not opened:
                raise RuntimeError("The desktop could not open this folder.")
            self.app_settings.setValue("settings/last_opened_folder", str(path.resolve()))
        except Exception as error:
            InfoDialog(
                "Folder could not be opened",
                f"{tr(label)}: {error}",
                icon_name="warning_orange",
                parent=self,
                eyebrow="LOCAL PATH",
                notice="No hardware command was executed.",
                tone="red",
            ).exec()

    def _show_local_paths(self) -> None:
        paths = self._paths()
        if not paths:
            InfoDialog(
                "Local paths unavailable",
                "The application backend did not return its shared configuration paths.",
                icon_name="warning_orange",
                parent=self,
                eyebrow="LOCAL PATH",
                notice="No hardware command was executed.",
                tone="red",
            ).exec()
            return
        preferred = ("config", "perfiles", "historial", "estabilidad", "metricas_runtime", "tools", "data", "resource_tools")
        labels = {
            "config": "Configuration", "perfiles": "Profiles", "historial": "History",
            "estabilidad": "Stability data", "metricas_runtime": "Runtime metrics",
            "tools": "Installed tools", "data": "Application data", "resource_tools": "Bundled tool sources",
        }
        lines: list[str] = []
        for key in preferred:
            value = paths.get(key)
            if value:
                lines.append(f"{tr(labels.get(key, key))}:\n{value}")
        for key in sorted(set(paths) - set(preferred)):
            lines.append(f"{key}:\n{paths[key]}")
        TextDetailsDialog("Local paths", "\n\n".join(lines), self).exec()

    @staticmethod
    def _format_bytes(value: object) -> str:
        try:
            amount = max(0, int(value))
        except Exception:
            return "--"
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        number = float(amount)
        unit = units[0]
        for candidate in units:
            unit = candidate
            if number < 1024 or candidate == units[-1]:
                break
            number /= 1024
        return f"{number:.1f} {unit}"

    def _evaluate_memory_pressure(self) -> None:
        button = getattr(self, "memory_pressure_button", None)
        if isinstance(button, QPushButton):
            button.setText(tr("Evaluating…"))

        def operation() -> object:
            return self.controller.proteccion_memoria(aplicar=False) or {}

        def success(payload: object) -> None:
            if isinstance(button, QPushButton):
                button.setText(tr("Evaluate memory pressure"))
            result = payload if isinstance(payload, dict) else {}
            state = result.get("estado") or {}
            candidates = list(result.get("candidatos") or [])
            games = list(state.get("juegos_detectados") or [])
            level = str(state.get("nivel") or "unknown").capitalize()
            lines = [
                f"{tr('Level')}: {tr(level)}",
                f"{tr('RAM used')}: {float(state.get('ram_percent') or 0):.1f} %",
                f"{tr('RAM available')}: {self._format_bytes(state.get('ram_available'))}",
                f"{tr('Swap used')}: {float(state.get('swap_percent') or 0):.1f} %",
                f"{tr('Detected games')}: {len(games)}",
                f"{tr('Suggested applications')}: {len(candidates)}",
                "",
                tr("This evaluation is read-only. No process was closed and no cache command was executed."),
            ]
            if candidates:
                lines.extend(("", tr("Largest suggested applications:")))
                for item in candidates[:8]:
                    name = item.get("nombre") or tr("Process")
                    lines.append(
                        f"• {name} · {float(item.get('memoria_mb') or 0):.1f} MiB · PID {item.get('pid', '--')}"
                    )
            TextDetailsDialog("Memory pressure", "\n".join(lines), self).exec()

        def failure(message: str) -> None:
            if isinstance(button, QPushButton):
                button.setText(tr("Evaluate memory pressure"))
            InfoDialog(
                "Memory evaluation failed",
                message,
                icon_name="warning_orange",
                parent=self,
                eyebrow="MEMORY",
                notice="No process was closed and no cache command was executed.",
                tone="red",
            ).exec()

        controls = (button,) if isinstance(button, QWidget) else ()
        self._start_task(operation, success, failure, controls=controls)

    def _open_settings_folder(self) -> None:
        self._open_directory(Path(self._path_for("config")).expanduser().resolve().parent, tr("Settings folder"))

    def _open_history_folder(self) -> None:
        self._open_directory(Path(self._path_for("historial")).expanduser().resolve().parent, tr("History folder"))

    def _portable_start_directory(self) -> str:
        return str(Path(self._path_for("config")).expanduser().resolve().parent)

    def _export_profile_bundle(self) -> None:
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("Export settings and profiles"),
            str(Path(self._portable_start_directory()) / "bc250-settings-profiles.json"),
            tr("BC250 profile bundle (*.json)"),
        )
        if not destination:
            return

        def success(result: object) -> None:
            InfoDialog(
                "Export completed",
                tr_format("Portable settings and profiles were saved to {path}.", path=result),
                icon_name="check_green",
                parent=self,
                eyebrow="DATA PORTABILITY",
                notice="No hardware or system setting was changed.",
                tone="green",
            ).exec()

        def failure(message: str) -> None:
            InfoDialog(
                "Export failed", message, icon_name="warning_orange", parent=self,
                eyebrow="DATA PORTABILITY",
                notice="No hardware or system setting was changed.", tone="red",
            ).exec()

        self._start_task(
            lambda: self.settings_service.export_profile_bundle(destination),
            success,
            failure,
            controls=(self.profile_export_button,),
        )

    def _import_profile_bundle(self) -> None:
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("Import settings and profiles"),
            self._portable_start_directory(),
            tr("BC250 profile bundle (*.json)"),
        )
        if not source:
            return

        def preview_ready(payload: object) -> None:
            preview = payload if isinstance(payload, dict) else {}
            config_count = len(preview.get("config_keys") or ())
            profile_count = len(preview.get("profile_sections") or ())
            dialog = ConfirmDialog(
                "Import portable settings and profiles",
                "The bundle checksum is valid. Current user settings and profiles will be backed up before the transactional import. Nothing is applied to live hardware.",
                summary=(
                    ("File", source),
                    ("Configuration keys", str(config_count)),
                    ("Profile sections", str(profile_count)),
                ),
                confirm_text="Import bundle",
                eyebrow="CONFIRM USER DATA IMPORT",
                tone="orange",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            def imported(result: object) -> None:
                InfoDialog(
                    "Import completed",
                    tr_format("Settings and profiles were imported. Backup: {path}", path=result),
                    icon_name="check_green",
                    parent=self,
                    eyebrow="DATA PORTABILITY",
                    notice="Reopen Settings to refresh visible preferences. No hardware value was applied.",
                    tone="green",
                ).exec()

            self._start_task(
                lambda: self.settings_service.import_profile_bundle(source),
                imported,
                lambda message: InfoDialog(
                    "Import failed", message, icon_name="warning_orange", parent=self,
                    eyebrow="DATA PORTABILITY",
                    notice="The transaction attempted to restore the previous user configuration.",
                    tone="red",
                ).exec(),
                controls=(self.profile_import_button,),
            )

        self._start_task(
            lambda: self.settings_service.preview_profile_bundle(source),
            preview_ready,
            lambda message: InfoDialog(
                "Bundle validation failed", message, icon_name="warning_orange", parent=self,
                eyebrow="DATA PORTABILITY",
                notice="The selected file was not imported.", tone="red",
            ).exec(),
            controls=(self.profile_import_button,),
        )

    def _export_runtime_metrics(self, format_name: str) -> None:
        # Settings intentionally exposes one interoperable report format.
        format_name = "csv"
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr_format("Export metrics as {format}", format=format_name.upper()),
            str(Path(self._portable_start_directory()) / f"bc250-metrics.{format_name}"),
            tr_format("Metrics file (*.{extension})", extension=format_name),
        )
        if not destination:
            return
        destination_path = Path(destination).expanduser()
        if destination_path.suffix.lower() != ".csv":
            destination_path = destination_path.with_suffix(".csv")
        destination = str(destination_path)

        def success(result: object) -> None:
            InfoDialog(
                "Metrics export completed",
                tr_format("Recorded metrics were saved to {path}.", path=result),
                icon_name="check_green", parent=self, eyebrow="REPORTS",
                notice="The CSV contains recorded samples and can be opened in a spreadsheet.", tone="green",
            ).exec()

        self._start_task(
            lambda: self.settings_service.export_runtime_metrics(destination, format_name),
            success,
            lambda message: InfoDialog(
                "Metrics export failed", message, icon_name="warning_orange", parent=self,
                eyebrow="REPORTS",
                notice="No incomplete export was kept.", tone="red",
            ).exec(),
            controls=(self.metrics_csv_button,),
        )

    def refresh_history(self, force: bool = False) -> None:
        # state_cache.events() delegates to the injected activity service in a
        # worker and caches the JSONL result briefly between settings tabs.
        if not hasattr(self, "history_table") or self._history_busy:
            return
        now = time.monotonic()
        if not force and self._history_loaded_at and now - self._history_loaded_at < 2.0:
            return
        if force:
            self._state_cache.invalidate("events:100")
        self._history_busy = True
        refresh_button = getattr(self, "history_refresh_button", None)

        def operation() -> object:
            return self._state_cache.events(100)

        def success(payload: object) -> None:
            self._history_busy = False
            self._history_loaded_at = time.monotonic()
            self.history_table.setToolTip("")
            self._apply_history_events(list(payload or []))

        def failure(message: str) -> None:
            self._history_busy = False
            self.history_table.setToolTip(message)
            self._apply_history_events([])

        controls = (refresh_button,) if isinstance(refresh_button, QWidget) else ()
        self._start_task(operation, success, failure, controls=controls)

    def _apply_history_events(self, events: list[object]) -> None:
        self.history_table.setUpdatesEnabled(False)
        self.history_table.setSortingEnabled(False)
        try:
            self.history_table.setRowCount(len(events))
            level_tones = {"error": "red", "warning": "orange", "warn": "orange", "success": "green", "info": "blue"}
            for row, raw_event in enumerate(events):
                event = raw_event if isinstance(raw_event, dict) else {"detalle": str(raw_event)}
                translated_title, translated_detail = translate_history_event(event)
                values = (
                    str(event.get("fecha") or "--"),
                    tr(str(event.get("nivel") or "info").capitalize()),
                    translated_title,
                    translated_detail,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 1:
                        item.setData(Qt.ItemDataRole.UserRole, level_tones.get(str(event.get("nivel", "info")).lower(), "blue"))
                    self.history_table.setItem(row, column, item)
        finally:
            self.history_table.setSortingEnabled(True)
            self.history_table.setUpdatesEnabled(True)
        self.history_count.setText(count_label(len(events), "event"))

    def _clear_history(self) -> None:
        dialog = ConfirmDialog(
            "Clear local history",
            "The JSONL history file will be emptied. This cannot be undone.",
            summary=(("File", self._path_for("historial")),),
            confirm_text="Clear history",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def operation() -> object:
            self.activity_service.clear()
            return True

        def success(_result: object) -> None:
            self._state_cache.invalidate("events:100")
            self._history_loaded_at = 0.0
            self.refresh_history(force=True)

        def failure(message: str) -> None:
            InfoDialog(
                "History could not be cleared",
                message,
                icon_name="warning_orange",
                parent=self,
                eyebrow="HISTORY",
                notice="No hardware command was executed.",
                tone="red",
            ).exec()

        self._start_task(operation, success, failure)

    def _show_project_overview(self) -> None:
        TextDetailsDialog("About", project_overview(), self).exec()

    @staticmethod
    def _localized_health_field(check: dict, field: str, default: str) -> str:
        key = str(check.get(f"{field}_key") or "")
        values = check.get(f"{field}_values")
        values = values if isinstance(values, dict) else {}
        localized_values = {
            name: tr(value) if name in {"state", "mode", "boot_sync"} else value
            for name, value in values.items()
        }
        if key:
            return tr_format(key, **localized_values)
        return tr(str(check.get(field) or default))

    def _populate_health_row(self, row: int, check: dict, status_title: str) -> None:
        status = str(check.get("status") or "warning").lower()
        values = (
            tr(status_title),
            tr(str(check.get("title") or "Component")),
            self._localized_health_field(check, "detail", ""),
            self._localized_health_field(check, "repair", "No action required."),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            item.setData(Qt.ItemDataRole.UserRole, status)
            self.health_table.setItem(row, column, item)

    def _apply_health_result(self, payload: object) -> None:
        result = payload if isinstance(payload, dict) else {}
        checks = list(result.get("checks") or [])
        counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
        overall = str(result.get("overall") or "warning").lower()
        titles = {
            "healthy": "Healthy",
            "warning": "Warning",
            "error": "Error",
        }
        self.health_summary_title.setText(tr(titles.get(overall, "Warning")))
        self.health_summary_detail.setText(tr_format(
            "{healthy} healthy · {warnings} warnings · {errors} errors · {distribution} · kernel {kernel}",
            healthy=int(counts.get("healthy") or 0),
            warnings=int(counts.get("warning") or 0),
            errors=int(counts.get("error") or 0),
            distribution=str(result.get("distribution") or "Linux"),
            kernel=str(result.get("kernel") or "--"),
        ))
        self.health_table.setUpdatesEnabled(False)
        try:
            self.health_table.setRowCount(len(checks))
            for row, check in enumerate(checks):
                status = str(check.get("status") or "warning").lower()
                self._populate_health_row(row, check, titles.get(status, "Warning"))
            self.health_table.resizeRowsToContents()
        finally:
            self.health_table.setUpdatesEnabled(True)

    def _run_health_check(self) -> None:
        if self._health_busy or not hasattr(self, "health_table"):
            return
        self._health_busy = True
        self.health_check_button.setText(tr("Checking…"))

        def success(result: object) -> None:
            self._health_busy = False
            self.health_check_button.setText(tr("Run health check"))
            self._apply_health_result(result)

        def failure(message: str) -> None:
            self._health_busy = False
            self.health_check_button.setText(tr("Run health check"))
            InfoDialog(
                "Health check failed", message, icon_name="warning_orange", parent=self,
                eyebrow="SYSTEM HEALTH", notice="No repair action was executed.", tone="red",
            ).exec()

        self._start_task(
            self.controller.health_check,
            success,
            failure,
            controls=(self.health_repair_button, self.health_report_button),
        )

    def _repair_health(self) -> None:
        dialog = ConfirmDialog(
            "Repair BC250 installation",
            "Only missing or broken application components will be repaired. Existing hardware profiles, "
            "fan curves, CPU settings, governor settings, and Compute Unit layouts are preserved. "
            "Kernel patches and hardware state changes are never applied silently.",
            summary=(
                ("Repositories", "Clone missing or fast-forward existing official sources"),
                ("Services and helpers", "Repair only when missing or failed"),
                ("User configuration", "Preserved"),
            ),
            confirm_text="Start repair",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def success(payload: object) -> None:
            result = payload if isinstance(payload, dict) else {}
            self._apply_health_result(result.get("health") or {})
            InfoDialog(
                "Repair result",
                str(result.get("message") or "Repair workflow completed."),
                icon_name="shield_green" if result.get("started") else "info_blue",
                parent=self,
                eyebrow="SYSTEM HEALTH",
                notice="Run the health check again after any terminal workflow finishes.",
                tone="green" if result.get("started") else "blue",
            ).exec()

        def failure(message: str) -> None:
            InfoDialog(
                "Repair could not start", message, icon_name="warning_orange", parent=self,
                eyebrow="SYSTEM HEALTH", notice="No automatic hardware repair was attempted.", tone="red",
            ).exec()

        self._start_task(
            self.controller.repair_installation,
            success,
            failure,
            controls=(self.health_check_button, self.health_repair_button, self.health_report_button),
        )

    def _generate_diagnostic_report(self) -> None:
        def success(payload: object) -> None:
            result = payload if isinstance(payload, dict) else {}
            path = str(result.get("path") or "")
            report = str(result.get("report") or "")
            TextDetailsDialog(
                "BC250 diagnostic report",
                f"{tr('Saved to')}: {path}\n\n{report}",
                self,
            ).exec()

        def failure(message: str) -> None:
            InfoDialog(
                "Diagnostic report failed", message, icon_name="warning_orange", parent=self,
                eyebrow="DIAGNOSTICS", notice="No system configuration was changed.", tone="red",
            ).exec()

        self._start_task(
            self.controller.generate_diagnostic_report,
            success,
            failure,
            controls=(self.health_check_button, self.health_repair_button, self.health_report_button),
        )

    def _inspect_recovery_snapshots(self) -> None:
        def success(payload: object) -> None:
            result = payload if isinstance(payload, dict) else {}
            snapshots = result.get("snapshots") if isinstance(result.get("snapshots"), list) else []
            lines = [f"{tr('Storage')}: {result.get('root') or '--'}", ""]
            if not snapshots:
                lines.append(tr("No recovery snapshots are stored."))
            for item in snapshots:
                if not isinstance(item, dict):
                    continue
                state = tr("Verified") if item.get("verified") else tr("Invalid")
                access = tr("Manual review required") if item.get("blocked") else tr("Plan available")
                lines.extend(
                    (
                        f"{item.get('label') or item.get('id')}: {state} · {access}",
                        f"ID: {item.get('id')} · {tr('Actions')}: {item.get('actions', 0)}",
                        "",
                    )
                )
            lines.append(tr("Restore execution is disabled; this view does not change the system."))
            TextDetailsDialog(
                "Recovery snapshot inventory", "\n".join(lines).rstrip(), self
            ).exec()

        def failure(message: str) -> None:
            InfoDialog(
                "Recovery inventory failed",
                message,
                icon_name="warning_orange",
                parent=self,
                eyebrow="RECOVERY",
                notice="No system configuration was changed.",
                tone="red",
            ).exec()

        self._start_task(
            self.controller.recovery_inventory,
            success,
            failure,
            controls=(self.recovery_inventory_button, self.recovery_export_button),
        )

    def _create_recovery_snapshot(self) -> None:
        def success(payload: object) -> None:
            result = payload if isinstance(payload, dict) else {}
            states = result.get("states") if isinstance(result.get("states"), dict) else {}
            lines = [
                f"{tr('Storage')}: {result.get('path') or '--'}",
                f"{tr('Entries')}: {result.get('entries', 0)}",
                f"{tr('Captured')}: {states.get('captured', 0)}",
                f"{tr('Missing')}: {states.get('missing', 0)}",
                f"{tr('Unreadable')}: {states.get('unreadable', 0)}",
                f"{tr('Boot-critical entries')}: {result.get('boot_critical', 0)}",
                "",
                tr("The snapshot is verified. Restore execution remains disabled."),
            ]
            TextDetailsDialog(
                "Recovery snapshot created", "\n".join(lines), self
            ).exec()

        def failure(message: str) -> None:
            InfoDialog(
                "Recovery snapshot failed", message, icon_name="warning_orange",
                parent=self, eyebrow="RECOVERY",
                notice="No system configuration was changed.", tone="red",
            ).exec()

        self._start_task(
            lambda: self.controller.create_recovery_snapshot(
                "manual-before-change"
            ),
            success,
            failure,
            controls=(
                self.recovery_create_button,
                self.recovery_inventory_button,
                self.recovery_export_button,
            ),
        )

    def _export_latest_recovery_snapshot(self) -> None:
        def inventory_ready(payload: object) -> None:
            result = payload if isinstance(payload, dict) else {}
            snapshots = result.get("snapshots") if isinstance(result.get("snapshots"), list) else []
            selected = next(
                (
                    item for item in snapshots
                    if isinstance(item, dict) and item.get("verified") and item.get("id")
                ),
                None,
            )
            if selected is None:
                InfoDialog(
                    "Recovery export unavailable",
                    tr("No verified recovery snapshot is available to export."),
                    icon_name="warning_orange",
                    parent=self,
                    eyebrow="RECOVERY",
                    notice="Create and verify a snapshot before exporting evidence.",
                    tone="orange",
                ).exec()
                return
            snapshot_id = str(selected["id"])
            destination, _selected_filter = QFileDialog.getSaveFileName(
                self,
                tr("Export portable recovery evidence"),
                str(Path(self._portable_start_directory()) / f"bc250-recovery-{snapshot_id}.zip"),
                tr("BC250 recovery evidence (*.zip)"),
            )
            if not destination:
                return

            def exported(export_payload: object) -> None:
                export = export_payload if isinstance(export_payload, dict) else {}
                InfoDialog(
                    "Recovery evidence exported",
                    tr_format(
                        "Verified recovery evidence was saved to {path}. SHA-256: {sha256}",
                        path=export.get("path") or destination,
                        sha256=export.get("sha256") or "--",
                    ),
                    icon_name="check_green",
                    parent=self,
                    eyebrow="RECOVERY",
                    notice="The archive contains no automatic restore executable and did not change the system.",
                    tone="green",
                ).exec()

            self._start_task(
                lambda: self.controller.export_recovery_snapshot(snapshot_id, destination),
                exported,
                lambda message: InfoDialog(
                    "Recovery export failed", message, icon_name="warning_orange",
                    parent=self, eyebrow="RECOVERY",
                    notice="No existing file or system setting was changed.", tone="red",
                ).exec(),
                controls=(
                    self.recovery_create_button,
                    self.recovery_inventory_button,
                    self.recovery_export_button,
                ),
            )

        self._start_task(
            self.controller.recovery_inventory,
            inventory_ready,
            lambda message: InfoDialog(
                "Recovery inventory failed", message, icon_name="warning_orange",
                parent=self, eyebrow="RECOVERY",
                notice="No system configuration was changed.", tone="red",
            ).exec(),
            controls=(
                self.recovery_create_button,
                self.recovery_inventory_button,
                self.recovery_export_button,
            ),
        )

    def _show_repositories(self) -> None:
        RepositoriesDialog(self).exec()

    def _open_contact(self) -> None:
        opened, message = open_external_url(CONTACT_URL)
        if opened:
            return
        InfoDialog(
            "Contact link could not be opened",
            message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="CONTACT",
            notice=tr_format("Copy this address manually: {url}", url=CONTACT_URL),
            tone="orange",
        ).exec()

    def _update_application(self) -> None:
        dialog = ConfirmDialog(
            "Update BC250 Control Center",
            "The official source will be updated in place. User settings, Compute Unit layouts, "
            "fan curves, governor configuration, CPU settings, installed services, and community "
            "tool repositories are preserved.",
            summary=(
                ("Source", "Official movacx/bc250-control-center repository"),
                ("Existing checkout", "Reused with a fast-forward-only update"),
                ("Hardware configuration", "Preserved"),
            ),
            confirm_text="Open updater",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.controller.actualizar_aplicacion_local()
        except Exception as error:
            InfoDialog(
                "Application update could not start",
                str(error),
                icon_name="warning_orange",
                parent=self,
                eyebrow="UPDATE",
                notice="No application files or settings were changed.",
                tone="red",
            ).exec()

    def gamepad_cycle_section(self, delta: int) -> None:
        current = next((key for key, button in self.nav_buttons.items() if button.isChecked()), self.section_order[0])
        target = self.section_order[(self.section_order.index(current) + (1 if delta > 0 else -1)) % len(self.section_order)]
        self.select_section(target)

    def gamepad_focus_scope(self) -> QWidget:
        return self.stack.currentWidget() or self

    def select_section(self, key: str) -> None:
        if key not in self.nav_buttons:
            return
        index = self.section_order.index(key)
        self._ensure_section(key)
        self.stack.setCurrentIndex(index)
        for section_key, button in self.nav_buttons.items():
            button.setChecked(section_key == key)
        self.app_settings.setValue("settings/current_section", key)
        if key == "reports":
            self.refresh_history()
        elif key == "telemetry":
            self._load_daemon_config()
            self.refresh_daemon_status()
        self.section_requested.emit(key)

    @staticmethod
    def _apply_density_to_page(page: QWidget, compact: bool) -> None:
        for group in page.findChildren(SettingsGroup):
            group.set_compact(compact)
        for action_grid in page.findChildren(ActionGrid):
            action_grid.set_compact(compact)
        history_table = getattr(page, "history_table", None)
        if isinstance(history_table, QTableWidget):
            history_table.verticalHeader().setDefaultSectionSize(27 if compact else 32)
            history_table.setMinimumHeight(260 if compact else 330)

    def apply_density(self, density: str) -> None:
        normalized = str(density).strip().lower()
        if normalized == self._applied_density:
            return
        self._applied_density = normalized
        compact = normalized == "compact"
        content_margin = 14 if compact else 18
        top_margin = 12 if compact else 16
        self.content_layout.setContentsMargins(content_margin, top_margin, content_margin, top_margin)
        self.content_layout.setSpacing(7 if compact else 10)
        for layout in self._page_layouts:
            layout.setSpacing(7 if compact else 10)
        for key in self._built_sections:
            page = self.stack.widget(self.section_order.index(key))
            if page is not None:
                self._apply_density_to_page(page, compact)
        if hasattr(self, "history_table"):
            self.history_table.verticalHeader().setDefaultSectionSize(27 if compact else 32)
            self.history_table.setMinimumHeight(260 if compact else 330)
        for button in self.findChildren(SettingsNavButton):
            button.setMinimumHeight(34 if compact else 40)
        self.setProperty("compactDensity", compact)
        self.style().unpolish(self)
        self.style().polish(self)
        self.updateGeometry()

    def refresh_appearance(self) -> None:
        if self.parent() is None:
            self.setStyleSheet(settings_stylesheet())
        self._applied_density = None
        self.apply_density(str(self.app_settings.value("settings/density", "comfortable")))

    def _set_control_value(self, key: str, value: object) -> None:
        control = self.controls.get(key)
        if isinstance(control, QComboBox):
            index = control.findData(value)
            if index >= 0:
                control.setCurrentIndex(index)
        elif isinstance(control, QCheckBox):
            control.setChecked(self._bool_value(value))

    def _reset_preferences(self) -> None:
        dialog = ConfirmDialog(
            "Reset interface preferences",
            "Restore language, theme, density, accent, startup behavior, and sidebar preferences to their defaults? Hardware profiles and history are preserved.",
            summary=(("Preserved", "Hardware profiles, voltage limits, commands, and history"),),
            confirm_text="Reset preferences",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        defaults = {
            "settings/start_page": "dashboard",
            "settings/reopen_last_module": "true",
            "sidebar_collapsed": "false",
            "settings/gamepad_navigation": "true",
            "settings/gamepad_onscreen_keypad": "true",
            "settings/gamepad_keypad_auto_show": "true",
            "settings/appearance": "system",
            "settings/density": "comfortable",
            "settings/scale": 100,
            "settings/accent": "blue",
            "settings/language": "auto",
            "settings/smart_alerts": "false",
            "settings/desktop_notifications": "false",
            "settings/detailed_diagnostics": "false",
        }
        blockers: list[QSignalBlocker] = []
        try:
            for control in self.controls.values():
                blockers.append(QSignalBlocker(control))
            for key, value in defaults.items():
                self.app_settings.setValue(key, value)
                self._set_control_value(key, value)
        finally:
            blockers.clear()
        self.app_settings.sync()
        self.apply_density("comfortable")
        self.language_changed.emit("auto")
        self.appearance_changed.emit("system", "blue", "comfortable")
        self.scale_changed.emit(100)
        self.smart_alerts_changed.emit(False)
        self.desktop_notifications_changed.emit(False)
        self.diagnostics_changed.emit(False)
        self.sidebar_collapsed_changed.emit(False)
        self.gamepad_navigation_changed.emit(True)
        self.gamepad_keypad_changed.emit(True)
        self.gamepad_keypad_auto_show_changed.emit(True)
        InfoDialog(
            "Preferences restored",
            "Interface preferences were restored. Hardware profiles, limits, commands, and history were not changed.",
            icon_name="shield_green",
            parent=self,
            eyebrow="SETTINGS",
            notice="No hardware command was executed.",
            tone="green",
        ).exec()


class SettingsDialog(QDialog):
    language_changed = pyqtSignal(str)
    appearance_changed = pyqtSignal(str, str, str)
    scale_changed = pyqtSignal(int)
    smart_alerts_changed = pyqtSignal(bool)
    desktop_notifications_changed = pyqtSignal(bool)
    diagnostics_changed = pyqtSignal(bool)
    sidebar_collapsed_changed = pyqtSignal(bool)
    gamepad_navigation_changed = pyqtSignal(bool)
    gamepad_keypad_changed = pyqtSignal(bool)
    gamepad_keypad_auto_show_changed = pyqtSignal(bool)
    embedded_terminal_changed = pyqtSignal(bool)
    console_auto_hide_changed = pyqtSignal(bool)
    tour_requested = pyqtSignal()

    def __init__(self, controller, *, settings_service, activity_service, app_settings: QSettings | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Settings")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet() + settings_stylesheet())
        enable_adaptive_dialog(
            self,
            # This is the exact content size the previous nested settings
            # shell occupied.  The dialog now ends at that shell instead of
            # wrapping it in a second, larger dark card.
            preferred_width=920,
            preferred_height=628,
            minimum_width=620,
            minimum_height=460,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.page = SettingsPage(
            controller,
            settings_service=settings_service,
            activity_service=activity_service,
            app_settings=app_settings,
            parent=self,
        )
        self.page.setMinimumHeight(0)
        self.page.language_changed.connect(self.language_changed.emit)
        self.page.appearance_changed.connect(self.appearance_changed.emit)
        self.page.scale_changed.connect(self.scale_changed.emit)
        self.page.smart_alerts_changed.connect(self.smart_alerts_changed.emit)
        self.page.desktop_notifications_changed.connect(self.desktop_notifications_changed.emit)
        self.page.diagnostics_changed.connect(self.diagnostics_changed.emit)
        self.page.sidebar_collapsed_changed.connect(self.sidebar_collapsed_changed.emit)
        self.page.tour_requested.connect(self.tour_requested.emit)
        self.page.gamepad_navigation_changed.connect(self.gamepad_navigation_changed.emit)
        self.page.gamepad_keypad_changed.connect(self.gamepad_keypad_changed.emit)
        self.page.gamepad_keypad_auto_show_changed.connect(self.gamepad_keypad_auto_show_changed.emit)
        self.page.embedded_terminal_changed.connect(self.embedded_terminal_changed.emit)
        self.page.console_auto_hide_changed.connect(self.console_auto_hide_changed.emit)
        outer.addWidget(self.page, 1)

        # Frameless dialogs still need an obvious exit.  Keep it inside the
        # settings shell so it no longer creates a separate header/margin.
        self.close_button = QPushButton(self)
        self.close_button.setObjectName("DialogClose")
        self.close_button.setIcon(icon("close_gray"))
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("Close")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self._request_close)
        self.close_button.raise_()
        self._localized_language = current_language()
        localize_widget_tree(self)

    def _request_close(self) -> None:
        if self.page.has_running_tasks():
            InfoDialog(
                "Operation still running",
                "Wait for the current settings operation to finish before closing this window.",
                icon_name="info_blue",
                parent=self,
                eyebrow="SETTINGS",
                notice="The operation has a bounded timeout and will return control automatically.",
                tone="blue",
            ).exec()
            return
        super().reject()

    def reject(self) -> None:
        self._request_close()

    def select_section(self, key: str) -> None:
        self.page.select_section(key)

    def gamepad_cycle_section(self, delta: int) -> None:
        self.page.gamepad_cycle_section(delta)

    def gamepad_focus_scope(self) -> QWidget:
        return self.page.gamepad_focus_scope()

    def refresh_appearance(self) -> None:
        self.setStyleSheet(application_stylesheet() + settings_stylesheet())
        self.page.refresh_appearance()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self.close_button.move(max(0, self.width() - self.close_button.width() - 8), 8)
        self.close_button.raise_()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        language = current_language()
        if language != self._localized_language:
            localize_widget_tree(self)
            self._localized_language = language
        self.fit_to_content()
        center_dialog(self)
