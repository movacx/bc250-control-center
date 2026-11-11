from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QEvent,
    QRect,
    QSettings,
    QSize,
    QSignalBlocker,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure import SystemdUserService
from bc250cc.infrastructure.apu_telemetry_service import apu_telemetry_state
from bc250cc.infrastructure.gddr6_memory_temp_repository import (
    board_bios_version,
    gddr6_firmware_supported,
)
from bc250cc.infrastructure.governor_conflicts import normalize_governor_preference
from bc250cc.infrastructure.system_snapshot import system_snapshot
from bc250cc.infrastructure.vrm_telemetry_reader import (
    kernel_vrm_driver_present,
    sondear_telemetria_vrm,
)
from bc250cc.platform.init.services import detect_init_manager
from bc250cc.platform.packages.strategies.detector import detect_os_info
from bc250cc.shared.failure_text import describe_failure
from bc250cc.shared.version import __version__

from PyQt6.QtWidgets import QPushButton as _PlainButton

from ..components.buttons import WrappingButton as QPushButton
from ..components.density import apply_layout_density
from ..components.dialogs import center_dialog, enable_adaptive_dialog
from ..components.page_widgets import ConfirmDialog
from ..components.responsive import (
    QT_MAX_SIZE,
    clear_grid,
    configure_responsive_scroll_area,
)
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.wheel_guard import GuardedComboBox
from ..components.widgets import InfoDialog, PillLabel, icon
from ..core.diagnostic_history import (
    clear_history,
    current_wording,
    diagnostic_report,
    history_entries,
)
from ..core.external_links import open_external_url
from ..core.preferences import REPORT_GLOW_KEY, application_settings
from ..core.raw_errors import remember
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
from .. import theme as _theme

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
    ("BC250 VA-API driver (hardware video)", "simpmix/bc250-encoding-decoding-fix", "https://github.com/simpmix/bc250-encoding-decoding-fix"),
    ("BC250 ACPI fix updated", "mendesrr/bc250-acpi-fix-updated-8c", "https://github.com/mendesrr/bc250-acpi-fix-updated-8c"),
    ("BC250 native mesh shaders reference", "lonewolf0622/BC250-Native-Mesh-Shaders-", "https://github.com/lonewolf0622/BC250-Native-Mesh-Shaders-"),
    ("BC250 memory configuration reference", "fanoush/bc250_memcfg", "https://github.com/fanoush/bc250_memcfg"),
    ("BC250 EFI core unlock reference", "Hexxeh/bc250-efi-core-unlock", "https://github.com/Hexxeh/bc250-efi-core-unlock"),
    ("BC250 UEFI shell and MeiMeiDXE firmware", "Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script", "https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script"),
    ("BC250 stock and Chipset Menu BIOS", "TuxThePenguin0/bc250-bios", "https://gitlab.com/TuxThePenguin0/bc250-bios"),
    ("ASRock BIOS update kit mirror", "kenavru/BC-250", "https://github.com/kenavru/BC-250"),
    ("BC250 custom boot logo reference", "tmghd272/bc250-custom-bios-logo", "https://github.com/tmghd272/bc250-custom-bios-logo"),
    ("nct6687d fan driver", "Fred78290/nct6687d", "https://github.com/Fred78290/nct6687d"),
    ("cecd HDMI-CEC daemon (Valve)", "holo/linux-cec", "https://gitlab.steamos.cloud/holo/linux-cec"),
    ("USB Wi-Fi compatibility reference", "morrownr/USB-WiFi", "https://github.com/morrownr/USB-WiFi"),
    ("CUPS printing reference", "OpenPrinting/cups", "https://github.com/OpenPrinting/cups"),
    ("ipp-usb printing reference", "OpenPrinting/ipp-usb", "https://github.com/OpenPrinting/ipp-usb"),
    ("system-config-printer reference", "OpenPrinting/system-config-printer", "https://github.com/OpenPrinting/system-config-printer"),
    ("foomatic-db printing reference", "OpenPrinting/foomatic-db", "https://github.com/OpenPrinting/foomatic-db"),
    ("PAPPL printing reference", "michaelrsweet/pappl", "https://github.com/michaelrsweet/pappl"),
    ("pappl-retrofit printing reference", "OpenPrinting/pappl-retrofit", "https://github.com/OpenPrinting/pappl-retrofit"),
    ("BlueZ Bluetooth reference", "bluez/bluez", "https://github.com/bluez/bluez"),
)
#: Repositories whose owner has archived them: still the reference for what they were, no longer updated.
ARCHIVED_REPOSITORIES = frozenset({"duggasco/bc250-40cu-unlock"})
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
    # The rail of the first-run panel, so the two read as one family.
    rail = _theme._blend(c["panel_alt"], c["border_strong"], 0.20) if _theme.ACTIVE_MODE == "light" else c["panel_alt"]
    # A step between the sidebar and the page, and descriptions a little
    # nearer the text than the plain muted grey, so nothing reads washed out.
    nav_ground = c["window"] if _theme.ACTIVE_MODE != "light" else c["panel_alt"]
    row_note = _theme._blend(c["muted"], c["text"], 0.30)
    # The tabs and the footer sit on a band a shade off the page, so the
    # window reads as a frame around the settings rather than one flat sheet.
    band = c["panel"] if _theme.ACTIVE_MODE == "light" else _theme._blend(c["window"], c["panel"], 0.55)
    return scale_stylesheet(f"""
    QDialog[settingsPage='true'] {{
        background:{c['panel']}; color:{c['text']};
    }}
    QWidget[settingsPage='true'] QFrame[settingsShell='true'] {{
        background:{c['panel']}; border:1px solid {c['border_strong']}; border-radius:12px;
    }}
    QWidget[settingsPage='true'] QFrame[settingsTitleBar='true'] {{
        background:transparent; border:none; border-bottom:1px solid {c['border']};
    }}
    QWidget[settingsPage='true'] QLabel[titleBarText='true'] {{
        color:{c['text']}; font-size:13px; font-weight:600;
    }}
    QWidget[settingsPage='true'] QFrame[settingsNav='true'] {{
        background:{nav_ground}; border:none; border-right:1px solid {c['border']};
        border-bottom-left-radius:12px;
    }}
    QWidget[settingsPage='true'] QLineEdit[navSearch='true'] {{
        min-height:30px; padding:0 8px; border-radius:8px; font-size:12px;
        background:{c['panel_raised']}; border:1px solid {c['border_strong']}; color:{c['text']};
    }}
    QWidget[settingsPage='true'] QLineEdit[navSearch='true']:focus {{ border-color:{c['border_strong']}; }}
    QWidget[settingsPage='true'] QLabel[navCaption='true'] {{
        color:{c['muted']}; font-size:11px; font-weight:650; padding:14px 8px 6px 8px;
    }}
    QWidget[settingsPage='true'] QPushButton[settingsNavButton='true'] {{
        text-align:left; padding:6px 8px; border:none; border-radius:8px;
        color:{c['text']}; font-size:12px; font-weight:600; background:transparent;
    }}
    QWidget[settingsPage='true'] QPushButton[settingsNavButton='true']:hover {{ background:{hover}; }}
    QWidget[settingsPage='true'] QPushButton[settingsNavButton='true']:checked {{
        background:{c['control_pressed']}; color:{c['text']};
    }}
    QWidget[settingsPage='true'] QLabel[sectionHeading='true'] {{
        color:{c['text']}; font-size:17px; font-weight:700; padding-bottom:2px;
    }}
    QWidget[settingsPage='true'] QFrame[settingsContent='true'] {{
        background:transparent; border:none;
    }}
    QWidget[settingsPage='true'] QFrame[settingsHeader='true'] {{
        background:transparent; border:none; border-bottom:1px solid {c['border']};
    }}
    QWidget[settingsPage='true'] QLabel[pageTitle='true'] {{
        color:{c['text']}; font-size:21px; font-weight:800; letter-spacing:-0.4px;
    }}
    QWidget[settingsPage='true'] QLabel[pageSubtitle='true'] {{
        color:{c['muted']}; font-size:11px;
    }}
    QWidget[settingsPage='true'] QFrame[settingsCard='true'] {{
        background:transparent; border:none;
    }}
    QWidget[settingsPage='true'] QFrame[settingsFooter='true'] {{
        background:{band}; border:none; border-top:1px solid {c['border']};
        border-bottom-left-radius:12px; border-bottom-right-radius:12px;
    }}
    QWidget[settingsPage='true'] QLabel[settingsFooterNote='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QWidget[settingsPage='true'] QPushButton[footerLink='true'] {{
        background:transparent; border:none; padding:2px 0; color:{c['blue']};
        font-size:11px; font-weight:680;
    }}
    QWidget[settingsPage='true'] QPushButton[footerLink='true']:hover {{ color:{c['blue_hover']}; }}
    QWidget[settingsPage='true'] QPushButton[segment='true'] {{
        background:{c['panel_alt']}; border:1px solid {c['border']}; border-radius:7px;
        padding:6px 12px; color:{c['text']}; font-size:11px; font-weight:650; min-height:16px;
    }}
    QWidget[settingsPage='true'] QPushButton[segment='true']:hover {{
        background:{hover}; border-color:{c['border_strong']};
    }}
    QWidget[settingsPage='true'] QPushButton[segment='true']:checked {{
        background:{c['blue']}; border-color:{c['blue']}; color:{c['on_accent']};
    }}
    QWidget[settingsPage='true'] QLabel[themeCaption='true'] {{
        color:{c['text']}; font-size:11px; font-weight:650;
    }}
    QWidget[settingsPage='true'] QPushButton[linkRow='true'] {{
        background:transparent; border:none; border-bottom:1px solid {c['border_soft']};
        border-radius:0px; padding:13px 0; text-align:left; color:{c['text']};
        font-size:12px; font-weight:620;
    }}
    QWidget[settingsPage='true'] QPushButton[linkRow='true']:hover {{ color:{c['blue']}; }}
    QWidget[settingsPage='true'] QPushButton[linkRow='true'][lastRow='true'] {{ border-bottom:none; }}
    QWidget[settingsPage='true'] QLabel[statusValue] {{ font-size:11px; font-weight:680; }}
    QWidget[settingsPage='true'] QLabel[statusValue='green'] {{ color:{c['green']}; }}
    QWidget[settingsPage='true'] QLabel[statusValue='orange'] {{ color:{c['orange']}; }}
    QWidget[settingsPage='true'] QLabel[statusValue='gray'] {{ color:{c['muted']}; }}
    QWidget[settingsPage='true'] QLabel[aboutName='true'] {{
        color:{c['text']}; font-size:18px; font-weight:800; letter-spacing:-0.3px;
    }}
    QWidget[settingsPage='true'] QLabel[aboutVersion='true'] {{
        color:{c['muted']}; font-size:11px; font-weight:600;
    }}
    QWidget[settingsPage='true'] QLineEdit[settingsSearch='true'] {{
        min-height:40px; padding:0 14px; border-radius:10px; font-size:13px; font-weight:500;
        background:{c['panel']}; border:1px solid {c['border_strong']}; color:{c['text']};
    }}
    QWidget[settingsPage='true'] QLineEdit[settingsSearch='true']:focus {{ border-color:{c['blue']}; }}
    QWidget[settingsPage='true'] QFrame[settingsTabs='true'] {{
        background:{band}; border:none; border-bottom:1px solid {c['border']};
        border-top-left-radius:12px; border-top-right-radius:12px;
    }}
    QWidget[settingsPage='true'] QPushButton[backLink='true'] {{
        background:transparent; border:none; padding:2px 0; color:{c['blue']};
        font-size:11px; font-weight:700;
    }}
    QWidget[settingsPage='true'] QPushButton[backLink='true']:hover {{ color:{c['blue_hover']}; }}
    QWidget[settingsPage='true'] QLabel[subpageTitle='true'] {{
        color:{c['text']}; font-size:18px; font-weight:800; letter-spacing:-0.3px; padding-top:6px;
    }}
    QWidget[settingsPage='true'] QLabel[overviewLead='true'] {{ color:{c['text']}; font-size:12px; }}
    QWidget[settingsPage='true'] QLabel[overviewItem='true'] {{ color:{c['text']}; font-size:11px; }}
    QWidget[settingsPage='true'] QFrame[sectionBlock='true'] {{ background:transparent; border:none; }}
    QWidget[settingsPage='true'] QPushButton[toolbarAction='true'] {{
        min-height:26px; padding:0 11px; border-radius:7px; border:1px solid {c['border']};
        background:{c['panel']}; color:{c['text']}; font-size:10px; font-weight:650;
    }}
    QWidget[settingsPage='true'] QPushButton[toolbarAction='true']:hover {{
        border-color:{c['border_strong']}; background:{hover};
    }}
    QWidget[settingsPage='true'] QFrame[banner='true'] {{
        background:{c['panel_alt']}; border:none; border-radius:9px;
    }}
    QWidget[settingsPage='true'] QLabel[bannerTitle='true'] {{
        color:{c['text']}; font-size:13px; font-weight:760;
    }}
    QWidget[settingsPage='true'] QLabel[bannerText='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QWidget[settingsPage='true'] QLabel[groupTitle='true'] {{
        color:{c['text']}; font-size:14px; font-weight:600;
    }}
    QWidget[settingsPage='true'] QFrame[settingsGroup='true'] {{
        background:transparent; border:none;
    }}
    QWidget[settingsPage='true'] QFrame[settingRow='true'] {{
        background:transparent; border:none; border-bottom:1px solid {c['border']};
    }}
    QWidget[settingsPage='true'] QFrame[settingRow='true'][lastRow='true'] {{
        border-bottom:none;
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
        color:{c['text']}; font-size:12px; font-weight:650;
    }}
    QWidget[settingsPage='true'] QLabel[rowDescription='true'] {{
        color:{row_note}; font-size:11px; line-height:135%;
    }}
    QComboBox[settingsCombo='true'] {{
        min-width:190px; min-height:34px; padding:0 36px 0 11px;
        border:1px solid {c['border_strong']}; border-radius:10px;
        background-color:{c['panel_raised']}; color:{c['text']};
        font-size:12px; font-weight:620;
    }}
    QComboBox[settingsCombo='true'][narrowCombo='true'] {{ min-width:96px; }}
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
        min-height:32px; padding:0 14px; border-radius:9px; border:1px solid {c['border_strong']};
        background:transparent; color:{c['text']}; font-size:11px; font-weight:680;
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
        border:1px solid {c['border']}; border-radius:10px; gridline-color:{c['border_soft']};
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
        background:transparent; border:none; border-bottom:1px solid {c['border']}; border-radius:0px;
    }}
    QWidget[settingsPage='true'] QLabel[reportHeroTitle='true'] {{
        color:{c['text']}; font-size:14px; font-weight:760;
    }}
    QWidget[settingsPage='true'] QLabel[reportHeroText='true'] {{
        color:{c['muted']}; font-size:10px;
    }}
    QWidget[settingsPage='true'][compactDensity='true'] QPushButton[settingsNavButton='true'] {{
        padding:4px 8px;
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



#: The BC-250 kernel reads the regulator itself; a service installed earlier
#: can no longer open the bus.
VRM_SERVICE_REDUNDANT = (
    "This kernel reads the regulator itself (bc250_vrm), so the BC250-Telemetry service "
    "is not needed and cannot open the bus. Remove it here."
)

class SettingsNavButton(QPushButton):
    def __init__(self, key: str, text: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("settingsNavButton", True)
        self.setMinimumHeight(34)
        self.icon_name = icon_name
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Drawn as the main sidebar draws its rows: sharp at every screen
        scale, muted at rest, the accent once selected."""
        from ..components.sidebar import EXPANDED_ICON, _nav_icon

        self.setIcon(_nav_icon(self.icon_name, "blue"))
        self.setIconSize(EXPANDED_ICON)


#: A magnifier for the search field, drawn like the other glyphs.
SEARCH_GLYPH = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="#000" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/>'
    '<path d="M16 16l4.5 4.5"/></svg>'
)


def tinted_icon(name: str, color: str) -> QIcon:
    """One of the line glyphs, recoloured: they ship in a single accent."""
    import re

    path = Path(__file__).resolve().parents[1] / "theme" / "icons" / f"{name}.svg"
    try:
        svg = SEARCH_GLYPH if name == "search" else path.read_text(encoding="utf-8")
    except OSError:
        return QIcon()
    svg = re.sub(r'stroke="#[0-9A-Fa-f]{3,8}"', f'stroke="{color}"', svg)
    svg = re.sub(r'fill="#[0-9A-Fa-f]{3,8}"', f'fill="{color}"', svg)
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    return QIcon(pixmap)


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


class WrappedLabel(QLabel):
    """A word-wrapped label whose height is exactly what its text needs.

    ``QLabel.heightForWidth`` can answer one line too many for a paragraph that
    wraps at the edge of its width: a two-line text then gets the height of
    three and, centred in it, floats in a gap above and below. The height is
    measured here with ``QFontMetrics``, the measurement the text is painted
    with, and the text is anchored to the top.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def _is_rich(self) -> bool:
        mode = self.textFormat()
        return mode == Qt.TextFormat.RichText or (
            mode == Qt.TextFormat.AutoText and Qt.mightBeRichText(self.text())
        )

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API name
        if self._is_rich():
            return super().heightForWidth(width)
        margins = self.contentsMargins()
        pad = 2 * self.margin()
        inner = max(1, width - margins.left() - margins.right() - pad)
        rect = self.fontMetrics().boundingRect(
            QRect(0, 0, inner, 100000), int(Qt.TextFlag.TextWordWrap), self.text()
        )
        return rect.height() + margins.top() + margins.bottom() + pad

    def _fit_height(self) -> None:
        width = self.width()
        if width <= 0:
            return
        height = self.heightForWidth(width)
        if height > 0 and self.height() != height:
            self.setFixedHeight(height)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(text)
        self._fit_height()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._fit_height()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit_height()


class ActionGrid(QWidget):
    """Responsive action container that avoids one-line button overflow.

    ``fit_content`` keeps every button on one row, each as wide as its own
    label asks, when they all fit, and wraps into ``columns`` columns when
    they do not, so one row stays one row in a language whose labels are short
    and becomes a grid in one whose labels are long.
    """

    def __init__(self, parent: QWidget | None = None, columns: int = 2, *, fit_content: bool = False):
        super().__init__(parent)
        self._preferred_columns = max(1, int(columns))
        self._fit_content = bool(fit_content)
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
        """Spacing follows the window-wide density pass (components/density.py)."""

    def _column_count(self) -> int:
        width = self.width()
        if self._fit_content and width > 0 and self._buttons and self._fits_one_row(width):
            return len(self._buttons)
        if width > 0 and width < 520:
            return 1
        return self._preferred_columns

    def _fits_one_row(self, width: int) -> bool:
        spacing = self._grid.horizontalSpacing()
        needed = sum(button.sizeHint().width() for button in self._buttons)
        return needed + spacing * (len(self._buttons) - 1) <= width

    def _reflow(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        columns = self._column_count()
        single_row = self._fit_content and columns == len(self._buttons) and columns > self._preferred_columns
        for index, widget in enumerate(self._buttons):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            # A single row shares the spare width in proportion to each label.
            weight = self._buttons[column].sizeHint().width() if single_row else 1
            self._grid.setColumnStretch(column, max(1, weight))

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
        self._layout.setContentsMargins(0, 12, 0, 12)
        self._layout.setHorizontalSpacing(18)
        self._layout.setVerticalSpacing(6)

        copy = QWidget()
        copy.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(2)
        self.title_label = WrappedLabel(tr(title))
        self.title_label.setProperty("rowTitle", True)
        self.description_label = WrappedLabel(tr(description))
        self.description_label.setProperty("rowDescription", True)
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.description_label)
        self.description_label.setVisible(bool(description))
        # Any height the row has beyond its copy goes under the description,
        # not between the title and the line that explains it.
        copy_layout.addStretch(1)
        self.copy_widget = copy

        control.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(copy, 0, 0)
        self._layout.addWidget(control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._layout.setColumnStretch(0, 1)

    def set_compact(self, compact: bool) -> None:
        # Margins and spacing follow the window-wide density pass
        # (components/density.py); tightening them here as well shrank a
        # compact row twice.
        self._compact = bool(compact)

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
    """A caption over an inset card of rows, as in a system preferences pane."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        # Keep the group transparent without installing an unscoped local QSS.
        # A local "background:transparent" stylesheet propagates to children in
        # Qt and used to override every settings combo box background and border.
        self.setProperty("settingsGroup", True)
        self.rows: list[SettingRow] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 30, 0, 0)
        outer.setSpacing(4)
        self.title_label = QLabel(tr(title))
        self.title_label.setProperty("groupTitle", True)
        self.title_label.setVisible(bool(title))
        outer.addWidget(self.title_label)
        self.card = QFrame()
        self.card.setProperty("settingsCard", True)
        outer.addWidget(self.card)
        # Everything a section adds to its group lands inside the card.
        self.layout_root = QVBoxLayout(self.card)
        self.layout_root.setContentsMargins(0, 0, 0, 0)
        self.layout_root.setSpacing(0)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.layout_root.addLayout(self.body)

    def add_row(self, row: SettingRow) -> None:
        # Rows are separated by a line under each one; the last row of a group
        # must not end in a stray line against the card's own border.
        if self.rows:
            self._mark_last(self.rows[-1], False)
        self.rows.append(row)
        self._mark_last(row, True)
        self.body.addWidget(row)

    @staticmethod
    def _mark_last(row: SettingRow, last: bool) -> None:
        row.setProperty("lastRow", last)
        style = row.style()
        style.unpolish(row)
        style.polish(row)

    def set_compact(self, compact: bool) -> None:
        for row in self.rows:
            row.set_compact(compact)


class LinkRow(QPushButton):
    """A row that is itself the action: a label and a chevron, in a card."""

    def __init__(self, text: str, callback, parent: QWidget | None = None):
        super().__init__(tr(text) + "   \u203a", parent)
        self.setProperty("linkRow", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)


class TerminalThemeCard(QFrame):
    """A built-in terminal theme as a miniature of the terminal it gives.

    A small window: a title bar, a few lines of a real workflow in the
    theme's own colours, the cursor, and its eight base colours as swatches;
    the name under it, with a check once it is the one in use.
    """

    chosen = pyqtSignal(str)

    SAMPLE = (
        (("text", "$ "), ("text", "pacman -S mesa")),
        ((4, "info "), ("text", "resolving deps")),
        ((2, "\u2713 "), ("text", "mesa installed")),
        ((3, "! "), ("muted", "reboot required")),
        ((1, "\u2717 "), ("text", "1 conflict")),
    )
    CAPTION = 30

    def __init__(self, key: str, name: str, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self.key = key
        self.name = name
        self.selected = False
        self.hovered = False
        #: Smaller, for the welcome panel: two sample lines, no extra width.
        self.compact = compact
        self.sample = self.SAMPLE[:2] if compact else self.SAMPLE
        if compact:
            self.CAPTION = 26
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(122 if compact else 196)
        self.setMinimumWidth(80 if compact else 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def _colors(self) -> tuple[str, str, str, str, tuple[str, ...]]:
        from ..console.palette import BASE_16

        theme = _theme.TERMINAL_THEMES.get(self.key)
        if theme is None:
            return (COLORS["console_bg"], COLORS["console_text"], COLORS["console_muted"],
                    COLORS["blue"], BASE_16)
        return theme["bg"], theme["text"], theme["muted"], theme["accent"], theme["ansi"]

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        from PyQt6.QtCore import QPointF, QRectF
        from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

        background, text, muted, accent, ansi = self._colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        window = QRectF(2, 2, self.width() - 4, self.height() - self.CAPTION - 4)

        # The window, clipped to its rounded corners.
        clip = QPainterPath()
        clip.addRoundedRect(window, 9, 9)
        painter.save()
        painter.setClipPath(clip)
        painter.fillRect(window, QColor(background))
        # Its title bar, one shade off the ground, with the shell's name.
        bar = QRectF(window.left(), window.top(), window.width(), 22)
        ground = QColor(background)
        shade = ground.darker(112) if ground.lightness() > 128 else ground.lighter(135)
        painter.fillRect(bar, shade)
        painter.setPen(QPen(QColor(muted)))
        small = QFont(self.font())
        small.setPointSizeF(max(6.5, self.font().pointSizeF() - 2.0))
        painter.setFont(small)
        painter.drawText(bar.adjusted(10, 0, -10, 0),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "bash")
        # The lines, in a monospace that fits the card without cutting a word.
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSizeF(self.font().pointSizeF() + 0.5)
        painter.setFont(mono)
        metrics = painter.fontMetrics()
        widest = max(sum(metrics.horizontalAdvance(part) for _c, part in line) for line in self.sample)
        room = window.width() - 28
        if widest > room:
            mono.setPointSizeF(mono.pointSizeF() * room / widest)
            painter.setFont(mono)
            metrics = painter.fontMetrics()
        y = bar.bottom() + 10 + metrics.ascent()
        x = 0.0
        for row, line in enumerate(self.sample):
            x = window.left() + 14
            for color, part in line:
                ink = text if color == "text" else muted if color == "muted" else ansi[color]
                painter.setPen(QColor(ink))
                painter.drawText(QPointF(x, y), part)
                x += metrics.horizontalAdvance(part)
            if row == 0:
                prompt_end = (x, y)
            y += metrics.height() + 3
        # The cursor after the command, in the theme's accent.
        cursor = QRectF(prompt_end[0] + 3, prompt_end[1] - metrics.ascent() + 1,
                        metrics.horizontalAdvance("m") * 0.8, metrics.ascent())
        painter.fillRect(cursor, QColor(accent))
        # The eight base colours, as a strip along the bottom of the window.
        swatch = 10.0
        gap = 5.0
        left = window.left() + 14
        top = window.bottom() - swatch - 11
        for index in range(8):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ansi[index if index else 8]))
            painter.drawRoundedRect(QRectF(left + index * (swatch + gap), top, swatch, swatch), 2.5, 2.5)
        painter.restore()

        # The frame: the accent once chosen, a step stronger on hover.
        if self.selected:
            pen = QPen(QColor(COLORS["blue"]), 2)
        else:
            pen = QPen(QColor(COLORS["border_strong" if self.hovered else "border"]), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(window, 9, 9)

        # The name under the window, with a check for the one in use.
        caption = QRectF(4, self.height() - self.CAPTION + 4, self.width() - 8, self.CAPTION - 8)
        name_font = QFont(self.font())
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QColor(COLORS["blue"] if self.selected else COLORS["text"]))
        label = ("\u2713  " if self.selected else "") + self.name
        painter.drawText(caption, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(self.key)
        super().mousePressEvent(event)


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
            remember(error)
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


class RepositoryList(QWidget):
    """The official repositories, a search over them and an Open button each."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search repositories"))
        self.search.setAccessibleName(tr("Search repositories"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.rows_host = QWidget()
        repository_layout = QVBoxLayout(self.rows_host)
        repository_layout.setContentsMargins(0, 0, 0, 0)
        repository_layout.setSpacing(4)
        self._rows: list[tuple[QFrame, str]] = []
        for index, (name, repository, url) in enumerate(OFFICIAL_REPOSITORIES, start=1):
            row = QFrame()
            row.setProperty("repositoryRow", True)
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(10, 5, 8, 5)
            row_layout.setHorizontalSpacing(10)
            index_label = QLabel(f"{index:02d}")
            index_label.setProperty("repositoryIndex", True)
            index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            index_label.setFixedWidth(24)
            copy = QVBoxLayout()
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(1)
            name_label = QLabel(name)
            name_label.setProperty("repositoryName", True)
            archived = repository in ARCHIVED_REPOSITORIES
            address_label = QLabel(repository)
            address_label.setProperty("repositoryAddress", True)
            address_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if archived:
                title_row = QHBoxLayout()
                title_row.setSpacing(8)
                title_row.addWidget(name_label)
                title_row.addWidget(PillLabel(tr("Archived"), "gray"))
                title_row.addStretch(1)
                copy.addLayout(title_row)
            else:
                copy.addWidget(name_label)
            copy.addWidget(address_label)
            button = QPushButton("Open")
            button.setProperty("ghostAction", True)
            button.setMinimumWidth(72)
            button.setFixedHeight(28)
            button.clicked.connect(lambda _checked=False, target=url: self._open_repository(target))
            row_layout.addWidget(index_label, 0, 0)
            row_layout.addLayout(copy, 0, 1)
            row_layout.addWidget(button, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.setColumnStretch(1, 1)
            repository_layout.addWidget(row)
            tags = " archived" if archived else ""
            self._rows.append((row, f"{name} {repository} {url}{tags}".casefold()))
        self._no_match = QLabel(tr("No repository matches the search."))
        self._no_match.setProperty("bannerText", True)
        self._no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_match.hide()
        repository_layout.addWidget(self._no_match)
        layout.addWidget(self.rows_host)

    def _filter(self, text: str) -> None:
        """Show the repositories whose name, address or URL has every word typed."""
        words = text.casefold().split()
        shown = 0
        for row, haystack in self._rows:
            match = all(word in haystack for word in words)
            row.setVisible(match)
            shown += match
        self._no_match.setVisible(shown == 0)

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


class RepositoriesDialog(QDialog):
    """The repository list on its own, for the places outside Settings."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(tr("Official repositories"))
        self.setStyleSheet(application_stylesheet() + settings_stylesheet())
        enable_adaptive_dialog(
            self,
            preferred_width=640,
            preferred_height=500,
            minimum_width=420,
            minimum_height=320,
        )
        self.setProperty("settingsPage", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        header_title = QLabel(tr("Official repositories"))
        header_title.setProperty("bannerTitle", True)
        layout.addWidget(header_title)
        repository_scroll = QScrollArea()
        repository_scroll.setWidgetResizable(True)
        repository_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # 39 rows must not size the dialog: the list scrolls inside whatever
        # height is left, instead of stretching the window to the screen.
        repository_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        repository_scroll.setMinimumHeight(160)
        repository_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.repositories = RepositoryList()
        repository_scroll.setWidget(self.repositories)
        layout.addWidget(repository_scroll, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton("Close")
        close.setProperty("primaryAction", True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
        localize_widget_tree(self)


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
    report_glow_changed = pyqtSignal(bool)
    gamepad_keypad_changed = pyqtSignal(bool)
    gamepad_keypad_auto_show_changed = pyqtSignal(bool)
    embedded_terminal_changed = pyqtSignal(bool)
    console_auto_hide_changed = pyqtSignal(bool)
    console_theme_changed = pyqtSignal(str)
    gddr6_manual_changed = pyqtSignal(bool)
    vrm_manual_changed = pyqtSignal(bool)
    tour_requested = pyqtSignal()
    update_requested = pyqtSignal()

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
        self.shell = shell
        shell_column = QVBoxLayout(shell)
        shell_column.setContentsMargins(0, 0, 0, 0)
        shell_column.setSpacing(0)
        title_bar = QFrame()
        title_bar.setProperty("settingsTitleBar", True)
        title_bar.setFixedHeight(46)
        title_row = QHBoxLayout(title_bar)
        # The dialog's close button sits at the right end of this bar.
        title_row.setContentsMargins(18, 0, 56, 0)
        title_text = QLabel(tr("Settings"))
        title_text.setProperty("titleBarText", True)
        title_row.addWidget(title_text)
        title_row.addStretch(1)
        shell_column.addWidget(title_bar)
        body_host = QWidget()
        shell_layout = QHBoxLayout(body_host)
        self.shell_layout = shell_layout
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_column.addWidget(body_host, 1)
        outer.addWidget(shell, 1)

        nav = QFrame()
        nav.setProperty("settingsNav", True)
        self.nav_frame = nav
        nav.setMinimumWidth(200)
        nav.setMaximumWidth(220)
        nav.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        nav_column = QVBoxLayout(nav)
        nav_column.setContentsMargins(12, 12, 10, 12)
        nav_column.setSpacing(0)
        self.search_field = QLineEdit()
        self.search_field.setProperty("navSearch", True)
        self.search_field.setPlaceholderText(tr("Search"))
        self.search_field.setClearButtonEnabled(True)
        self._search_action = self.search_field.addAction(
            tinted_icon("search", COLORS["muted"]), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_field.textChanged.connect(self._filter_nav)
        nav_column.addWidget(self.search_field)
        nav_buttons_host = QWidget()
        nav_layout = QGridLayout(nav_buttons_host)
        self.nav_layout = nav_layout
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setHorizontalSpacing(6)
        nav_layout.setVerticalSpacing(4)
        nav_column.addWidget(nav_buttons_host)
        nav_column.addStretch(1)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, SettingsNavButton] = {}

        # One subject per section, in the order a user looks for them: how the
        # application starts and looks, then the hardware backend, then the
        # terminal and controller, then monitoring, privacy, records and the
        # project itself. The keys of the sections that already existed are
        # unchanged, so saved positions and links from other pages still land.
        sections = [
            ("general", "General", "settings_blue"),
            ("appearance", "Appearance", "dashboard_blue"),
            ("console", "Terminal and controls", "terminal_window_gray"),
            ("hardware", "GPU governor", "gpu_blue"),
            ("telemetry", "Telemetry", "metrics_blue"),
            # "and", never "&": a push button reads "&" as a keyboard
            # mnemonic, and "History & reports" rendered as "History _reports".
            ("diagnostics", "Diagnostics", "logs_gray"),
            ("reports", "History and reports", "history_blue"),
            ("about", "About", "info_blue"),
        ]
        self.section_order = [key for key, _text, _icon in sections]
        for key, text, icon_name in sections:
            button = SettingsNavButton(key, text, icon_name)
            button.clicked.connect(lambda checked=False, item=key: self.select_section(item))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            nav_layout.addWidget(button, len(self.nav_buttons) - 1, 0)
        nav_layout.setRowStretch(len(sections), 1)
        # Captions over the sections, as a preferences window groups them.
        self.nav_groups = (
            ("Interface", ("general", "appearance", "console")),
            ("Hardware", ("hardware", "telemetry")),
            ("Data", ("diagnostics", "reports")),
            ("Application", ("about",)),
        )
        self.nav_captions: list[QLabel] = []
        for caption, _keys in self.nav_groups:
            label = QLabel(tr(caption))
            label.setProperty("navCaption", True)
            self.nav_captions.append(label)

        content_wrap = QFrame()
        self.content_wrap = content_wrap
        content_wrap.setMinimumWidth(0)
        content_wrap.setProperty("settingsContent", True)
        wrap_layout = QVBoxLayout(content_wrap)
        self.content_layout = wrap_layout
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(0)
        self._section_titles = {key: text for key, text, _icon in sections}
        self.scroll = QScrollArea()
        self.scroll.setObjectName("SettingsSectionScroll")
        body = QWidget()
        body.setObjectName("SettingsSectionBody")
        configure_responsive_scroll_area(self.scroll, body)
        body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.scroll_body = body
        centring = QHBoxLayout(body)
        centring.setContentsMargins(28, 22, 22, 28)
        centring.setSpacing(0)
        column = QWidget()
        column.setMaximumWidth(self.CONTENT_MAX_WIDTH)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.sections_layout = QVBoxLayout(column)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(0)
        centring.addWidget(column, 1)
        self.scroll.setWidget(body)
        wrap_layout.addWidget(self.scroll, 1)
        shell_layout.addWidget(nav)
        shell_layout.addWidget(content_wrap, 1)

        self._initialize_pages()
        self._load_paths_async()
        initial_section = str(self.app_settings.value("settings/current_section", "general"))
        # Migrate the removed System Health destination without leaving the
        # settings dialog on an empty stack page.
        if initial_section not in self.nav_buttons:
            initial_section = "general"
        self._last_section = initial_section
        self.sections_layout.addStretch(1)
        self.select_section("home")
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
            for caption in self.nav_captions:
                caption.hide()
            self.content_layout.setContentsMargins(0, 0, 0, 0)
        else:
            self.shell_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.nav_frame.setMinimumWidth(200)
            self.nav_frame.setMaximumWidth(220)
            self.nav_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            row = 0
            for caption, (_title, keys) in zip(self.nav_captions, self.nav_groups):
                caption.show()
                self.nav_layout.addWidget(caption, row, 0)
                row += 1
                for key in keys:
                    button = self.nav_buttons[key]
                    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    self.nav_layout.addWidget(button, row, 0)
                    row += 1
            self.nav_layout.setColumnStretch(0, 1)
            self.nav_layout.setRowStretch(row, 1)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
        # The margins above are the comfortable ones; Compact tightens them
        # again after every change of form, like any other layout.
        apply_layout_density(self)
        self._filter_nav(self.search_field.text())
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
        combo = GuardedComboBox()
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
        switch = ToggleSwitch()
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

    def _small_button(self, text: str, callback) -> QPushButton:
        # Never wrapped: a short action is as wide as its label, on one line.
        button = _PlainButton(tr(text))
        button.setProperty("toolbarAction", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _remember(self, name: str, widget: QWidget) -> QWidget:
        setattr(self, name, widget)
        return widget

    def _register_count(self, name: str, text: str) -> QLabel:
        label = PillLabel(text, "blue")
        setattr(self, name, label)
        return label

    @staticmethod
    def _table_header(title: str, count: QWidget | None, actions) -> QWidget:
        """A table's caption: its name and count, its own actions at the right."""
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 22, 0, 8)
        row.setSpacing(8)
        label = QLabel(tr(title))
        label.setProperty("groupTitle", True)
        row.addWidget(label)
        if count is not None:
            row.addWidget(count)
        row.addStretch(1)
        for action in actions:
            row.addWidget(action)
        return host

    def _button(self, text: str, callback, *, primary: bool = False) -> QPushButton:
        button = QPushButton(tr(text))
        button.setProperty("primaryAction" if primary else "ghostAction", True)
        button.clicked.connect(callback)
        return button

    #: The column of settings stops growing here; wider dialogs centre it.
    CONTENT_MAX_WIDTH = 900

    def _build_page_frame(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        """One section: its name, then its groups of rows."""
        del subtitle
        block = QFrame()
        block.setProperty("sectionBlock", True)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if title:
            heading = QLabel(tr(title))
            heading.setProperty("sectionHeading", True)
            layout.addWidget(heading)
        self._page_layouts.append(layout)
        return block, layout

    def _filter_nav(self, text: str) -> None:
        """Keep the sections whose name or any setting holds what was typed."""
        query = text.strip().casefold()
        shown: list[str] = []
        for key in self.section_order:
            visible = True
            if query:
                page = self._ensure_section(key)
                visible = query in tr(self._section_titles[key]).casefold() or any(
                    query in f"{row.title_label.text()} {row.description_label.text()}".casefold()
                    for row in (page.findChildren(SettingRow) if page is not None else ())
                )
            self.nav_buttons[key].setVisible(visible)
            if visible:
                shown.append(key)
        compact = getattr(self, "_shell_compact", False)
        for caption, (_title, keys) in zip(self.nav_captions, self.nav_groups):
            caption.setVisible(not compact and any(key in shown for key in keys))
        current = next((key for key, button in self.nav_buttons.items() if button.isChecked()), None)
        if query and shown and current not in shown:
            self.select_section(shown[0])

    #: Pages opened from a section, shown under its tab with a way back.    #: Pages opened from a section, shown under its tab with a way back.
    SUBPAGES = {"overview": "about", "repositories": "about"}

    def _show_section(self, key: str) -> None:
        owner = self.SUBPAGES.get(key, key)
        for section_key, button in self.nav_buttons.items():
            button.setChecked(section_key == owner)
        self._ensure_section(key)
        for section_key, page in self._section_pages.items():
            page.setVisible(section_key == key)
        self.scroll.verticalScrollBar().setValue(0)
        self._section_shown(key)

    def _section_shown(self, key: str) -> None:
        """Fetch what a section shows, now that it is on screen."""
        if key == "reports":
            self.refresh_history()
        elif key == "diagnostics":
            self._refresh_diagnostics()
        elif key == "telemetry":
            self._load_daemon_config()
            self.refresh_daemon_status()
            self.refresh_vrm_detection()

    def _initialize_pages(self) -> None:
        """Install lightweight placeholders; build each section on first use."""
        self._page_builders = {
            "general": self._build_general_page,
            "appearance": self._build_appearance_page,
            "hardware": self._build_hardware_page,
            "console": self._build_console_page,
            "telemetry": self._build_telemetry_page,
            "reports": self._build_reports_page,
            "diagnostics": self._build_diagnostics_page,
            "about": self._build_about_page,
            "overview": self._build_overview_page,
            "repositories": self._build_repositories_page,
        }
        self._built_sections: set[str] = set()
        self._section_pages: dict[str, QWidget] = {}
        for key in (*self.section_order, *self.SUBPAGES):
            placeholder = QWidget()
            placeholder.setObjectName(f"SettingsPlaceholder_{key}")
            placeholder.hide()
            self.sections_layout.addWidget(placeholder)
            self._section_pages[key] = placeholder

    def _ensure_section(self, key: str) -> QWidget | None:
        if key not in self._page_builders:
            return None
        if key in self._built_sections:
            return self._section_pages[key]
        started = time.perf_counter()
        page = self._page_builders[key]()
        placeholder = self._section_pages[key]
        index = self.sections_layout.indexOf(placeholder)
        self.sections_layout.removeWidget(placeholder)
        placeholder.deleteLater()
        page.hide()
        self.sections_layout.insertWidget(index, page)
        self._section_pages[key] = page
        self._built_sections.add(key)
        localize_widget_tree(page)
        compact = str(self.app_settings.value("settings/density", "comfortable")).strip().lower() == "compact"
        self._apply_density_to_page(page, compact)
        apply_layout_density(page, compact)
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
        language = SettingsGroup("Language")
        language.add_row(SettingRow(
            "Language",
            "Set the interface language. The change is applied immediately to the interface and its dialogs.",
            self._coded_combo([(name, code) for code, name in LANGUAGE_OPTIONS], "settings/language", "auto", self._language_control_changed),
        ))
        layout.addWidget(language)

        startup = SettingsGroup("Startup")
        startup.add_row(SettingRow(
            "Start page",
            "Choose the module to open by default.",
            self._coded_combo([
                ("Dashboard", "dashboard"), ("CPU / SMU", "cpu"), ("GPU Governor", "gpu"),
                ("Compute Units", "cu"), ("Performance", "performance"), ("Fans", "fans"),
                ("Processes", "processes"), ("Settings", "settings"),
            ], "settings/start_page", "dashboard"),
        ))
        startup.add_row(SettingRow(
            "Reopen last module",
            "Restore the last visited module when the application starts.",
            self._switch("settings/reopen_last_module", True),
        ))
        startup.add_row(SettingRow(
            "Collapsed sidebar at launch",
            "Open the main navigation in compact mode.",
            self._switch("sidebar_collapsed", False, self.sidebar_collapsed_changed.emit),
        ))
        layout.addWidget(startup)

        help_group = SettingsGroup("Help")
        help_group.add_row(SettingRow(
            "Guided tour",
            "Walk through the modules again, with each stop pointing at the control it describes.",
            self._button("Start the tour", self.tour_requested.emit),
        ))
        help_group.add_row(SettingRow(
            "Highlight the report button",
            "A soft glow every few seconds around the dashboard's button for reporting a problem or suggesting an idea.",
            self._switch(REPORT_GLOW_KEY, True, self.report_glow_changed.emit),
        ))
        help_group.add_row(SettingRow(
            "Reset interface preferences",
            "",
            self._button("Reset preferences", self._reset_preferences),
        ))
        layout.addWidget(help_group)
        layout.addStretch(1)
        return page

    def _build_hardware_page(self) -> QWidget:
        page, layout = self._build_page_frame(
            "Hardware",
            "Backends the hardware modules rely on. Frequencies, voltages and fan curves are set in each module.",
        )
        try:
            governor_preference = str(
                self.settings_service.read_local_config().get("gpu_governor", "auto")
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            governor_preference = "auto"
        self.app_settings.setValue("settings/gpu_governor", governor_preference)
        group = SettingsGroup("GPU governor")
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
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_console_page(self) -> QWidget:
        page, layout = self._build_page_frame(
            "Terminal and controls",
            "The built-in terminal where workflows run, and how a game controller drives the interface.",
        )
        terminal = SettingsGroup("Built-in terminal")
        terminal.add_row(SettingRow(
            "Terminal inside the window",
            "Run workflows in a panel at the bottom of the window instead of opening a separate terminal window.",
            self._switch(
                "settings/embedded_terminal", True, self.embedded_terminal_changed.emit
            ),
        ))
        terminal.add_row(SettingRow(
            "Hide the terminal when a workflow finishes without errors",
            "A workflow that fails keeps the terminal open so its output can be read.",
            self._switch(
                "settings/console_auto_hide", False, self.console_auto_hide_changed.emit
            ),
        ))
        shortcut = PillLabel("F4", "gray")
        shortcut.setProperty("keycap", True)
        terminal.add_row(SettingRow(
            "Show or hide the terminal",
            "Press F4 anywhere in the window, as in Dolphin. An empty terminal opens your own shell, without administrator rights.",
            shortcut,
        ))
        layout.addWidget(terminal)
        layout.addWidget(self._terminal_theme_group())

        controller = SettingsGroup("Game controller")
        controller.add_row(SettingRow(
            "Gamepad navigation",
            "Detect controllers automatically and show controller hints while active.",
            self._switch("settings/gamepad_navigation", False, self.gamepad_navigation_changed.emit),
        ))
        controller.add_row(SettingRow(
            "Automatic gamepad keypad",
            "Show the on-screen keypad automatically when a gamepad focuses an editable field.",
            self._switch(
                "settings/gamepad_onscreen_keypad",
                True,
                self._unified_gamepad_keypad_changed,
            ),
        ))
        layout.addWidget(controller)
        layout.addStretch(1)
        return page

    def _terminal_theme_group(self) -> QWidget:
        """The built-in terminal's colours, each shown as the terminal it gives."""
        group = SettingsGroup("Terminal theme")
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 10, 0, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        current = str(self.app_settings.value("settings/console_theme", "app") or "app")
        choices = [("app", tr("Same as the application"))] + [
            (key, theme["name"]) for key, theme in _theme.TERMINAL_THEMES.items()
        ]
        self.terminal_theme_cards: dict[str, TerminalThemeCard] = {}
        for index, (key, name) in enumerate(choices):
            card = TerminalThemeCard(key, name, host)
            card.selected = key == current
            card.chosen.connect(self._terminal_theme_chosen)
            grid.addWidget(card, index // 3, index % 3)
            self.terminal_theme_cards[key] = card
        for column in range(3):
            grid.setColumnStretch(column, 1)
        group.body.addWidget(host)
        return group

    def _terminal_theme_chosen(self, key: str) -> None:
        self.app_settings.setValue("settings/console_theme", key)
        for name, card in self.terminal_theme_cards.items():
            card.selected = name == key
            card.update()
        self.console_theme_changed.emit(key)

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

    def _segmented(self, combo: QComboBox, labels: list[str] | None = None) -> QWidget:
        """Buttons for a short list, bound to the stored combo they replace.

        The combo stays the record: it saves the value, runs the callback and
        is what a reset writes to. The buttons only show it and set it.
        """
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        group = QButtonGroup(host)
        group.setExclusive(True)
        buttons: list[QPushButton] = []
        for index in range(combo.count()):
            text = labels[index] if labels else combo.itemText(index)
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, item=index: combo.setCurrentIndex(item))
            group.addButton(button)
            row.addWidget(button)
            buttons.append(button)

        def sync(current: int) -> None:
            for index, button in enumerate(buttons):
                button.setChecked(index == current)

        combo.currentIndexChanged.connect(sync)
        sync(combo.currentIndex())
        host.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        return host

    @staticmethod
    def _stored(combo: QComboBox, page: QWidget) -> QComboBox:
        combo.setParent(page)
        combo.hide()
        return combo

    def _build_appearance_page(self) -> QWidget:
        from ..onboarding.previews import AccentDot, ThemePreview

        page, layout = self._build_page_frame(
            "Appearance",
            "Visual density, color, and language preferences for the interface.",
        )
        theme_combo = self._stored(self._coded_combo(
            [("System", "system"), ("Light", "light"), ("Dark", "dark"), ("Night blue", "midnight")],
            "settings/appearance", "system", self._appearance_control_changed,
        ), page)
        style_combo = self._stored(self._coded_combo(
            [("Standard", "standard"), ("Formal", "formal")],
            "settings/style", "formal", self._appearance_control_changed,
        ), page)
        accent_combo = self._stored(self._coded_combo(
            [(name.capitalize(), name) for name in _theme.ACCENTS],
            "settings/accent", "blue", self._appearance_control_changed,
        ), page)

        # Theme: the same miniatures as the welcome panel.
        theme_group = SettingsGroup("Theme and color")
        cards_host = QWidget()
        cards = QGridLayout(cards_host)
        cards.setContentsMargins(0, 8, 0, 10)
        cards.setHorizontalSpacing(10)
        cards.setVerticalSpacing(6)
        system_mode = "light" if _theme.ACTIVE_MODE == "light" else "dark"
        self.theme_cards: dict[str, ThemePreview] = {}
        for column, (value, label) in enumerate(
            (("system", "System"), ("light", "Light"), ("dark", "Dark"), ("midnight", "Night blue"))
        ):
            card = ThemePreview(
                value, system_mode if value == "system" else value,
                str(accent_combo.currentData()), cards_host, style=str(style_combo.currentData()),
            )
            card.setMinimumHeight(88)
            card.chosen.connect(lambda item, combo=theme_combo: combo.setCurrentIndex(combo.findData(item)))
            caption = QLabel(tr(label))
            caption.setProperty("themeCaption", True)
            caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cards.addWidget(card, 0, column)
            cards.addWidget(caption, 1, column)
            cards.setColumnStretch(column, 1)
            self.theme_cards[value] = card
        theme_group.body.addWidget(cards_host)
        accent_group = theme_group
        # Style as two buttons, the accents as the colours themselves.
        accent_group.add_row(SettingRow(
            "Style",
            "The register, in any theme. Standard keeps the rounded, lively look. Formal uses deeper, quieter colours, squarer corners and flat cards.",
            self._segmented(style_combo),
        ))
        dots_host = QWidget()
        dots = QHBoxLayout(dots_host)
        dots.setContentsMargins(0, 0, 0, 0)
        dots.setSpacing(4)
        self.accent_dots: dict[str, AccentDot] = {}
        for name in _theme.ACCENTS:
            dot = AccentDot(name, dots_host, style=str(style_combo.currentData()))
            dot.chosen.connect(lambda item, combo=accent_combo: combo.setCurrentIndex(combo.findData(item)))
            dots.addWidget(dot)
            self.accent_dots[name] = dot
        dots_host.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        accent_group.add_row(SettingRow("Accent color", "Select the main interface accent used across modules.", dots_host))
        layout.addWidget(accent_group)

        def sync_previews(_index: int = 0) -> None:
            mode, accent, style = theme_combo.currentData(), accent_combo.currentData(), style_combo.currentData()
            for value, card in self.theme_cards.items():
                card.set_selected(value == mode)
                card.set_accent(str(accent))
                card.set_style(str(style))
            for name, dot in self.accent_dots.items():
                dot._style = str(style)
                dot.set_selected(name == accent)
                dot.update()

        for combo in (theme_combo, style_combo, accent_combo):
            combo.currentIndexChanged.connect(sync_previews)
        sync_previews()
        self._sync_appearance_previews = sync_previews

        sizing = SettingsGroup("Layout")
        sizing.add_row(SettingRow(
            "Density",
            "Comfortable keeps generous spacing. Compact tightens margins, rows and buttons in every module so more fits on screen; text keeps its size.",
            self._segmented(self._stored(self._coded_combo(
                [("Comfortable", "comfortable"), ("Compact", "compact")],
                "settings/density", "comfortable", self._appearance_control_changed,
            ), page)),
        ))
        scale_combo = self._coded_combo(
            [(f"{value}%", value) for value in range(70, 151, 10)],
            "settings/scale", 100, lambda value: self.scale_changed.emit(int(value)),
        )
        scale_combo.setProperty("narrowCombo", True)
        scale_combo.setMinimumWidth(110)
        scale_combo.setMaximumWidth(130)
        sizing.add_row(SettingRow(
            "Interface scale",
            "Scale fonts, controls, spacing, and technical panels from 70% to 150%.",
            scale_combo,
        ))
        layout.addWidget(sizing)
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
        # What the daemon does and its buttons belong to the daemon, so they sit
        # inside its group instead of in a second, unrelated card below.
        daemon_group.layout_root.addSpacing(8)
        daemon_actions = ActionGrid(columns=2, fit_content=True)
        self.daemon_enable_button = self._button("Enable daemon", lambda: self._change_daemon(True))
        self.daemon_disable_button = self._button("Disable daemon", lambda: self._change_daemon(False))
        daemon_actions.addWidget(self.daemon_enable_button)
        daemon_actions.addWidget(self.daemon_disable_button)
        daemon_actions.addWidget(self._button("View daemon details", self._show_daemon_details))
        daemon_group.layout_root.addWidget(daemon_actions)
        daemon_group.layout_root.addSpacing(8)
        self._action_grids.append(daemon_actions)
        # Everyday monitoring first; the readings that need hardware or carry
        # a warning come after it.
        layout.addWidget(daemon_group)
        layout.addWidget(self._build_vrm_manual_group())
        layout.addWidget(self._build_gddr6_manual_group())
        layout.addStretch(1)
        return page

    #: The plain-language account shown under the switch, one idea a line.
    GDDR6_MANUAL_EXPLANATION = (
        (
            "Why there is a check",
            "Memory temperatures are asked of the SMU, a small chip on the board that "
            "also takes orders from Cyan, the GPU frequency service, and from CPU "
            "overclocking. "
            "It has a single mailbox. If two programs write to it at the same moment, "
            "the messages get mixed, the SMU stops answering and the board freezes "
            "until it is switched off at the plug.",
        ),
        (
            "When it makes you wait",
            "While Cyan is starting or restarting, which is when it writes to that "
            "mailbox, and while BC250-Telemetry's memory service holds it without "
            "publishing readings. If Cyan keeps restarting (for example Fix metrics "
            "on a kernel without gpu_metrics), the wait never ends.",
        ),
        (
            "What manual mode changes",
            "The Live button starts anyway. The locks between programs still apply, "
            "a board whose firmware is not P3 is still refused, and so is a board "
            "where BC250-Telemetry was interrupted halfway through a change.",
        ),
        (
            "If the board freezes",
            "Hold the power button, unplug it for ten seconds and start it again. The "
            "runtime SMU patch is lost with the power, nothing is written to the BIOS.",
        ),
    )

    def _build_gddr6_manual_group(self) -> QWidget:
        """GDDR6 monitoring without the SMU channel check, for those who ask."""
        group = SettingsGroup("GDDR6 memory temperature")
        self.gddr6_manual_switch = self._switch(
            "settings/gddr6_manual_override", False, self._gddr6_manual_toggled
        )
        group.add_row(SettingRow(
            "Manual GDDR6 monitoring",
            "Enable the memory temperature button even when the SMU channel check "
            "says to wait. It can make the board unstable or freeze it.",
            self.gddr6_manual_switch,
        ))
        # Manual mode lifts only the channel check. On a board that is not on
        # P3.00 the button stays grey whatever this switch says, and the one
        # place that was never said was right here, next to the switch.
        version = board_bios_version()
        self.gddr6_firmware_note = QLabel(
            tr_format(
                "This board runs BIOS {version}: live readings need P3.00 (stock, "
                "Chipset Menu or MeiMeiDXE), so the button stays off even in manual mode.",
                version=version,
            )
            if version
            else ""
        )
        self.gddr6_firmware_note.setProperty("fieldHint", True)
        self.gddr6_firmware_note.setWordWrap(True)
        self.gddr6_firmware_note.setVisible(bool(version) and not gddr6_firmware_supported(version))
        group.layout_root.addWidget(self.gddr6_firmware_note)
        group.layout_root.addSpacing(6)
        explanation = QFrame()
        self.gddr6_help_panel = explanation
        explanation.setProperty("banner", True)
        explanation_layout = QVBoxLayout(explanation)
        explanation_layout.setContentsMargins(14, 12, 14, 14)
        explanation_layout.setSpacing(0)
        for index, (heading, text) in enumerate(self.GDDR6_MANUAL_EXPLANATION):
            if index:
                explanation_layout.addSpacing(14)
            title = WrappedLabel(tr(heading))
            title.setProperty("bannerTitle", True)
            body = WrappedLabel(tr(text))
            body.setProperty("bannerText", True)
            explanation_layout.addWidget(title)
            explanation_layout.addSpacing(4)
            explanation_layout.addWidget(body)
        # Four long paragraphs under a single switch buried the controls, so
        # they fold away until asked for. The choice is remembered.
        self.gddr6_help_toggle = QPushButton("")
        self.gddr6_help_toggle.setProperty("ghostAction", True)
        self.gddr6_help_toggle.setCheckable(True)
        self.gddr6_help_toggle.setCursor(Qt.CursorShape.PointingHandCursor)

        def show_help(opened: bool) -> None:
            explanation.setVisible(opened)
            self.gddr6_help_toggle.setText(("\u25be  " if opened else "\u25b8  ") + tr("Details"))

        def help_toggled(opened: bool) -> None:
            self.app_settings.setValue("settings/gddr6_help_open", "true" if opened else "false")
            show_help(opened)

        opened = self._bool_value(self.app_settings.value("settings/gddr6_help_open", False), False)
        self.gddr6_help_toggle.setChecked(opened)
        show_help(opened)
        self.gddr6_help_toggle.toggled.connect(help_toggled)
        toggle_row = QWidget()
        toggle_layout = QHBoxLayout(toggle_row)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.addWidget(self.gddr6_help_toggle)
        toggle_layout.addStretch(1)
        # One container, so the gap between the button and the panel exists
        # only while the panel is open instead of lingering when it is folded.
        help_block = QWidget()
        help_layout = QVBoxLayout(help_block)
        help_layout.setContentsMargins(0, 4, 0, 0)
        help_layout.setSpacing(8)
        help_layout.addWidget(toggle_row)
        help_layout.addWidget(explanation)
        group.layout_root.addWidget(help_block)
        group.layout_root.addSpacing(10)
        return group

    def _build_vrm_manual_group(self) -> QWidget:
        """Power delivery shown by hand, for a mod being wired or tested."""
        group = SettingsGroup("Power delivery (I2C mod)")
        self.vrm_manual_switch = self._switch(
            "settings/vrm_manual", False, self.vrm_manual_changed.emit
        )
        group.add_row(SettingRow(
            "Manual power delivery readings",
            "Show the Power delivery band on the dashboard even when automatic detection "
            "finds no I2C modification. It shows everything BC250-Telemetry reports, "
            "invalid readings included and marked, which is what you need while testing "
            "the wiring. Nothing is written to the board.",
            self.vrm_manual_switch,
        ))
        self.vrm_detection_label = QLabel("")
        self.vrm_detection_label.setProperty("daemonState", True)
        self.vrm_detection_label.setWordWrap(True)
        group.add_row(SettingRow(
            "Automatic detection",
            "What the dashboard finds right now in BC250-Telemetry's snapshot.",
            self.vrm_detection_label,
        ))
        self.apu_telemetry_button = QPushButton("")
        self.apu_telemetry_button.setProperty("ghostAction", True)
        self.apu_telemetry_button.clicked.connect(self._apu_telemetry_clicked)
        group.add_row(SettingRow(
            "BC250-Telemetry service",
            "Installs the daemon that publishes the power delivery readings. Control "
            "Center builds the reviewed version and installs only that service. It "
            "needs the physical I2C modification on the board.",
            self.apu_telemetry_button,
        ))
        self.refresh_vrm_detection()
        return group

    def _apu_telemetry_state(self) -> dict:
        try:
            info = detect_os_info(has_rpm_ostree=bool(shutil.which("rpm-ostree")))
            return apu_telemetry_state(
                family=info.family, distro_id=info.distro_id, immutable=info.immutable
            )
        except (OSError, RuntimeError, ValueError):
            return {"state": "not-installed", "supported": False, "blocked_reason": ""}

    def refresh_apu_telemetry_button(self) -> None:
        button = getattr(self, "apu_telemetry_button", None)
        if button is None:
            return
        state = self._apu_telemetry_state()
        kind = state.get("state")
        button.setToolTip("")
        if kind == "external":
            button.setText(tr("Installed separately"))
            button.setEnabled(False)
            button.setToolTip(tr(
                "apu-telemetry.service was installed by BC250-Telemetry itself, so "
                "Control Center leaves it alone."
            ))
        elif state.get("managed"):
            button.setText(tr("Remove service"))
            button.setEnabled(True)
            if kernel_vrm_driver_present():
                # Installed before booting the BC-250 kernel: harmless (the
                # driver refuses it the bus, so nothing is read twice) but
                # useless, and it retries forever.
                button.setToolTip(tr(VRM_SERVICE_REDUNDANT))
        else:
            button.setText(tr("Install service"))
            supported = bool(state.get("supported"))
            button.setEnabled(supported)
            if not supported and state.get("blocked_reason"):
                button.setToolTip(str(state["blocked_reason"]))

    def install_apu_telemetry(self) -> None:
        """Start the install from elsewhere (the power delivery guide).

        Only when the button here would install: a service already managed or
        installed separately is left as it is.
        """
        button = getattr(self, "apu_telemetry_button", None)
        state = self._apu_telemetry_state()
        if button is None or not button.isEnabled() or state.get("managed") or state.get("state") == "external":
            return
        self._apu_telemetry_clicked()

    def _apu_telemetry_clicked(self) -> None:
        action = "uninstall" if self._apu_telemetry_state().get("managed") else "install"
        if action == "install":
            confirmation = ConfirmDialog(
                "Install the BC250-Telemetry service?",
                "Control Center builds the daemon from the reviewed upstream source and "
                "installs it as a root service that reads the voltage regulators over "
                "I2C. Without the physical I2C modification it finds nothing and only "
                "keeps retrying. Building needs your password and an internet connection.",
                summary=(
                    ("Source", "github.com/onlinermm/BC250-Telemetry"),
                    ("Installs", "apu-telemetry.service"),
                    ("Not installed", "Web server, fan module and memory collector"),
                    ("Writes to the board", "One PMBus page-select register; no regulator setting"),
                ),
                confirm_text="Build and install",
                tone="orange",
                parent=self,
            )
        else:
            confirmation = ConfirmDialog(
                "Remove the BC250-Telemetry service?",
                "Stops and removes the service and its binary. The power delivery "
                "readings stop until it is installed again.",
                confirm_text="Remove",
                tone="orange",
                parent=self,
            )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return

        def success(_result: object) -> None:
            self._state_cache.invalidate("tools")
            self.refresh_apu_telemetry_button()

        def failure(message: str) -> None:
            InfoDialog(
                "Could not run the BC250-Telemetry workflow",
                message,
                icon_name="warning_orange",
                parent=self,
                tone="red",
            ).exec()

        self._start_task(
            lambda: self.controller.gestionar_apu_telemetry(action),
            success,
            failure,
            controls=(self.apu_telemetry_button,),
        )

    @staticmethod
    def describe_vrm_detection(probe: dict) -> str:
        daemon = str(probe.get("daemon") or "missing")
        rails = probe.get("rails") if isinstance(probe.get("rails"), dict) else {}
        if daemon == "kernel":
            if any(isinstance(rail, dict) and rail.get("valid") for rail in rails.values()):
                return tr("Detected: the kernel driver (bc250_vrm) reads the regulator")
            return tr("Not detected: the kernel driver (bc250_vrm) gets no answer from the regulator")
        if daemon == "missing":
            if kernel_vrm_driver_present():
                return tr("Not detected: the kernel driver (bc250_vrm) gets no answer from the regulator")
            return tr("Not detected: BC250-Telemetry is not running")
        if daemon == "unreadable":
            return tr("Not detected: its snapshot could not be read")
        if daemon == "stale":
            return tr_format(
                "Not detected: its snapshot is {age} s old",
                age=f"{float(probe.get('age_s') or 0):.0f}",
            )
        if any(isinstance(rail, dict) and rail.get("valid") for rail in rails.values()):
            return tr("Detected: the PMIC answers over I2C")
        return tr("Not detected: BC250-Telemetry gets no answer from the PMIC")

    def refresh_vrm_detection(self) -> None:
        label = getattr(self, "vrm_detection_label", None)
        if label is not None:
            text = self.describe_vrm_detection(sondear_telemetria_vrm())
            if kernel_vrm_driver_present() and self._apu_telemetry_state().get("managed"):
                text = f"{text}\n{tr(VRM_SERVICE_REDUNDANT)}"
            label.setText(text)
        self.refresh_apu_telemetry_button()

    def _gddr6_manual_toggled(self, enabled: bool) -> None:
        if enabled and not self._confirm_gddr6_manual():
            switch = self.gddr6_manual_switch
            blocked = switch.blockSignals(True)
            switch.setChecked(False)
            switch.blockSignals(blocked)
            self.app_settings.setValue("settings/gddr6_manual_override", "false")
            return
        self.gddr6_manual_changed.emit(bool(enabled))

    def _confirm_gddr6_manual(self) -> bool:
        dialog = ConfirmDialog(
            "Turn off the SMU channel check?",
            "Memory temperature readings will start even while Cyan may be writing "
            "to the same SMU mailbox. That is exactly how these readings used "
            "to freeze boards. Use it only if you understand the risk.",
            summary=(
                ("Still enforced", "Locks between programs, P3 firmware, interrupted-operation guard"),
                ("If it freezes", "Hold power, unplug for ten seconds"),
            ),
            confirm_text="Enable manual monitoring",
            eyebrow="GDDR6 MEMORY TEMPERATURE",
            tone="red",
            parent=self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _build_reports_page(self) -> QWidget:
        # No page title: the sidebar names it, and the table is the page.
        page, layout = self._build_page_frame("", "")
        self.metrics_csv_button = self._small_button(
            "Export metrics as CSV", lambda: self._export_runtime_metrics("csv")
        )
        # Still written by the history code, never shown: the table says how
        # many events there are, and it refreshes each time it is opened.
        count = self._register_count("history_count", "0 events")
        refresh = self._remember("history_refresh_button", self._small_button("Refresh", lambda: self.refresh_history(force=True)))
        for hidden in (count, refresh):
            hidden.setParent(page)
            hidden.hide()
        header = self._table_header(
            "Recent activity",
            None,
            (
                self.metrics_csv_button,
                self._small_button("Open history folder", self._open_history_folder),
                self._small_button("Clear history", self._clear_history),
            ),
        )
        header.layout().setContentsMargins(0, 4, 0, 10)
        layout.addWidget(header)
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

    def _build_diagnostics_page(self) -> QWidget:
        page, layout = self._build_page_frame(
            "Diagnostics",
            "This system at a glance and every error Control Center explained, ready to paste into a problem report.",
        )
        support = SettingsGroup("Help")
        self.diagnostics_send_button = self._button("Send a report", self._send_problem_report, primary=True)
        self.diagnostics_copy_button = self._small_button("Copy for a problem report", self._copy_diagnostic_report)
        actions = QWidget()
        actions_row = QHBoxLayout(actions)
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)
        actions_row.addWidget(self.diagnostics_copy_button)
        actions_row.addWidget(self.diagnostics_send_button)
        support.add_row(SettingRow(
            "Send a report",
            "This system at a glance and every error Control Center explained, ready to paste into a problem report.",
            actions,
        ))
        support.add_row(SettingRow(
            "Detailed diagnostics",
            "Show complete device and configuration paths in technical diagnostic panels.",
            self._switch("settings/detailed_diagnostics", False, self.diagnostics_changed.emit),
        ))
        layout.addWidget(support)

        layout.addWidget(self._table_header("System", None, ()))
        # A sheet, not a list: every fact in its own cell, so a screenshot of
        # it answers what a support thread asks first.
        self.system_table = self._sheet(("Item", "Value"))
        self.system_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.system_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.system_table.setWordWrap(True)
        layout.addWidget(self.system_table)

        self.diagnostics_refresh_button = self._small_button("Refresh", self._refresh_diagnostics)
        self.diagnostics_clear_button = self._small_button("Clear history", self._clear_diagnostic_history)
        layout.addWidget(self._table_header(
            "Diagnostic history",
            self._register_count("diagnostics_count", "0 entries"),
            (self.diagnostics_clear_button, self.diagnostics_refresh_button),
        ))

        self.diagnostics_table = self._sheet(("Date and time", "Code", "Where", "What happened", "Likely cause"))
        header = self.diagnostics_table.horizontalHeader()
        for column in (0, 1, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.diagnostics_table.itemSelectionChanged.connect(self._show_diagnostic_detail)
        layout.addWidget(self.diagnostics_table)
        self.diagnostics_empty = QLabel(tr(
            "No errors recorded. Every error Control Center explains, in a window or in the terminal, appears here."
        ))
        self.diagnostics_empty.setProperty("emptyState", True)
        self.diagnostics_empty.setWordWrap(True)
        layout.addWidget(self.diagnostics_empty)

        self.diagnostics_detail = QPlainTextEdit()
        self.diagnostics_detail.setProperty("aboutText", True)
        self.diagnostics_detail.setReadOnly(True)
        self.diagnostics_detail.setMinimumHeight(150)
        self.diagnostics_detail.setPlaceholderText(tr("Select a row to see how to fix it and the technical detail."))
        layout.addWidget(self.diagnostics_detail)
        self._diagnostic_entries: list = []
        self._system_rows: list[tuple[str, str]] = []
        return page

    @staticmethod
    def _sheet(columns: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(columns))
        table.setProperty("historyTable", True)
        table.setProperty("sheetTable", True)
        table.setHorizontalHeaderLabels([tr(column) for column in columns])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(30)
        return table

    def _build_about_page(self) -> QWidget:
        # About
        page, layout = self._build_page_frame(
            "About",
            "Build information, local paths, project scope, and official repositories.",
        )
        identity = QFrame()
        identity.setProperty("aboutIdentity", True)
        identity_layout = QHBoxLayout(identity)
        identity_layout.setContentsMargins(0, 18, 0, 0)
        identity_layout.setSpacing(16)
        mark = QLabel()
        app_icon = Path(__file__).resolve().parents[3] / "assets" / "icons" / "bc250-control-center-128.png"
        mark.setPixmap(QPixmap(str(app_icon)).scaled(
            48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        mark.setFixedSize(52, 52)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity_layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        name = QLabel("BC250 Control Center")
        name.setProperty("aboutName", True)
        version = QLabel(f"{tr('Version')} {__version__}")
        version.setProperty("aboutVersion", True)
        text = QLabel("BC250 Control Center is a graphical interface for managing, preparing, and monitoring community tools for the AMD BC-250 board.")
        text.setProperty("rowDescription", True)
        text.setWordWrap(True)
        copy.addWidget(name)
        copy.addWidget(version)
        copy.addSpacing(4)
        copy.addWidget(text)
        identity_layout.addLayout(copy, 1)
        # As wide as its label: the wrapping button folded it into two lines.
        update = _PlainButton(tr("Update application"))
        update.setProperty("primaryAction", True)
        update.setCursor(Qt.CursorShape.PointingHandCursor)
        update.clicked.connect(self._update_application)
        update.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._update_button = update
        identity_layout.addWidget(update, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(identity)

        group = SettingsGroup("Application")
        self.config_path_field = ReadOnlyPathField(str(Path(self._path_for("config")).expanduser().resolve().parent))
        folder = QWidget()
        folder_row = QHBoxLayout(folder)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(8)
        folder_row.addWidget(self.config_path_field, 1)
        folder_row.addWidget(self._small_button("Open", self._open_settings_folder))
        group.add_row(SettingRow("Configuration folder", "Shared application configuration used by the GUI and optional daemon.", folder))
        layout.addWidget(group)

        links = SettingsGroup("Help")
        for text, callback in (
            ("Project overview", self._show_project_overview),
            ("Official repositories", self._show_repositories),
            ("Report a problem / Contact", self._open_contact),
        ):
            link = LinkRow(text, callback)
            links.layout_root.addWidget(link)
        link.setProperty("lastRow", True)
        layout.addWidget(links)
        layout.addStretch(1)
        return page

    def _back_link(self, layout: QVBoxLayout, title: str) -> None:
        """A way back to About, then the page's title."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 18, 0, 0)
        back = QPushButton("\u2039  " + tr("About"))
        back.setProperty("backLink", True)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self.select_section("about"))
        row.addWidget(back)
        row.addStretch(1)
        layout.addLayout(row)
        heading = QLabel(tr(title))
        heading.setProperty("subpageTitle", True)
        layout.addWidget(heading)

    def _build_overview_page(self) -> QWidget:
        page, layout = self._build_page_frame("", "")
        self._back_link(layout, "Project overview")
        # The overview is a lead paragraph, then "Heading:" blocks of bullets.
        blocks = [block.strip() for block in project_overview().split("\n\n") if block.strip()]
        if blocks:
            lead = QLabel(blocks[0])
            lead.setWordWrap(True)
            lead.setProperty("overviewLead", True)
            layout.addSpacing(6)
            layout.addWidget(lead)
        for block in blocks[1:]:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            heading = lines[0].rstrip(":") if lines and not lines[0].startswith("\u2022") else ""
            group = SettingsGroup(heading)
            group.layout_root.setContentsMargins(16, 10, 16, 12)
            group.layout_root.setSpacing(8)
            for line in lines[1 if heading else 0:]:
                item = WrappedLabel(line)
                item.setProperty("overviewItem", True)
                group.layout_root.addWidget(item)
            layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_repositories_page(self) -> QWidget:
        page, layout = self._build_page_frame("", "")
        self._back_link(layout, "Official repositories")
        intro = QLabel(tr(
            "BC250 Control Center does not own these tools. They are installed, cloned, or used as credited reference implementations according to each integration."
        ))
        intro.setWordWrap(True)
        intro.setProperty("rowDescription", True)
        layout.addSpacing(4)
        layout.addWidget(intro)
        layout.addSpacing(12)
        layout.addWidget(RepositoryList())
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
            "This runs systemctl --user enable --now bc250-control-centerd.service. The daemon records telemetry and restores the saved fan mode after login: an enabled automatic curve, a named preset or the last manual speed. It does not apply overclock automatically."
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
            show_toast(
                self,
                "The optional daemon is enabled." if enable else "The optional daemon is disabled.",
                tone="green",
            )

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

    def _open_settings_folder(self) -> None:
        self._open_directory(Path(self._path_for("config")).expanduser().resolve().parent, tr("Settings folder"))

    def _open_history_folder(self) -> None:
        self._open_directory(Path(self._path_for("historial")).expanduser().resolve().parent, tr("History folder"))

    def _portable_start_directory(self) -> str:
        return str(Path(self._path_for("config")).expanduser().resolve().parent)

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
            show_toast(
                self,
                "Metrics export completed",
                tr_format("Recorded metrics were saved to {path}.", path=result),
                tone="green",
            )

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
        self._show_section("overview")

    def _refresh_diagnostics(self) -> None:
        """Read the history now and the system facts in the background."""
        if not hasattr(self, "diagnostics_table"):
            return
        self._apply_diagnostic_history(history_entries())

        def success(rows: object) -> None:
            self._apply_system_rows(list(rows) if isinstance(rows, list) else [])

        self._start_task(system_snapshot, success, lambda _message: None,
                         controls=(self.diagnostics_refresh_button,))

    def _apply_system_rows(self, rows: list[tuple[str, str]]) -> None:
        self._system_rows = rows
        table = self.system_table
        table.setRowCount(len(rows))
        for row, (label, value) in enumerate(rows):
            name = QTableWidgetItem(tr(label))
            # Values are data; the few fixed words among them still translate.
            cell = QTableWidgetItem(tr(value))
            cell.setToolTip(tr(value))
            table.setItem(row, 0, name)
            table.setItem(row, 1, cell)
        table.resizeRowsToContents()
        # Every row on screen: the sheet is short and scrolling it hid facts.
        height = table.horizontalHeader().sizeHint().height() + 2
        height += sum(table.rowHeight(row) for row in range(table.rowCount()))
        table.setFixedHeight(height)

    def _apply_diagnostic_history(self, entries: list) -> None:
        self._diagnostic_entries = entries
        table = self.diagnostics_table
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                values = (
                    datetime.fromtimestamp(entry.at).strftime("%Y-%m-%d %H:%M:%S"),
                    entry.code,
                    {"terminal": tr("Terminal"), "decky": tr("Decky Quick Access")}.get(entry.source, tr("Window")),
                    tr(current_wording(entry).summary),
                    tr(current_wording(entry).cause),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    if column == 1:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    table.setItem(row, column, item)
        finally:
            table.setUpdatesEnabled(True)
        # As tall as its rows, up to a dozen; past that it scrolls.
        shown = min(max(len(entries), 3), 12)
        table.setFixedHeight(table.horizontalHeader().sizeHint().height() + 2 + shown * table.verticalHeader().defaultSectionSize())
        self.diagnostics_count.setText(tr_format("{count} entries", count=len(entries)))
        table.setVisible(bool(entries))
        self.diagnostics_empty.setVisible(not entries)
        self.diagnostics_detail.setVisible(bool(entries))
        self.diagnostics_detail.clear()
        self.diagnostics_clear_button.setEnabled(bool(entries))

    def _show_diagnostic_detail(self) -> None:
        rows = self.diagnostics_table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._diagnostic_entries):
            self.diagnostics_detail.clear()
            return
        entry = self._diagnostic_entries[rows[0].row()]
        parts = [
            f"{entry.code} · {tr(entry.title)}",
            f"{tr('How to fix it')}\n{tr(current_wording(entry).action)}",
        ]
        if entry.detail:
            parts.append(f"{tr('Technical detail')}\n{entry.detail}")
        self.diagnostics_detail.setPlainText("\n\n".join(parts))

    def _send_problem_report(self) -> None:
        from ..components.feedback_dialog import FeedbackDialog

        # The report carries the recent errors; which one it is about is the
        # owner's to say, so no code is guessed here.
        FeedbackDialog(self, opened_from="Settings › Diagnostics").exec()

    def _copy_diagnostic_report(self) -> None:
        report = diagnostic_report(self._system_rows, self._diagnostic_entries)
        QApplication.clipboard().setText(report)
        show_toast(self, "Copied", "Paste it into your problem report.", tone="green")

    def _clear_diagnostic_history(self) -> None:
        clear_history()
        self._apply_diagnostic_history([])
        show_toast(self, "Diagnostic history cleared", tone="blue")

    def _show_repositories(self) -> None:
        self._show_section("repositories")

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
        # The same updater as the dashboard: it picks the route for how this
        # copy was installed (package, AUR or source). The in-place script
        # this button used to run ships only with install-local.sh, so every
        # packaged install answered "the in-place updater is not installed".
        self.update_requested.emit()

    def gamepad_cycle_section(self, delta: int) -> None:
        current = next((key for key, button in self.nav_buttons.items() if button.isChecked()), self.section_order[0])
        target = self.section_order[(self.section_order.index(current) + (1 if delta > 0 else -1)) % len(self.section_order)]
        self.select_section(target)

    def gamepad_focus_scope(self) -> QWidget:
        return self.scroll

    def select_section(self, key: str) -> None:
        if key in self.SUBPAGES:
            # A page opened from a section (About › Official repositories).
            self._show_section(key)
            return
        if key == "home":
            # Settings opens on the section last used.
            self._show_section(self._last_section)
            return
        if key not in self.nav_buttons:
            return
        self._last_section = key
        for section_key, button in self.nav_buttons.items():
            button.setChecked(section_key == key)
        self.app_settings.setValue("settings/current_section", key)
        self._show_section(key)
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
        for key in self._built_sections:
            self._apply_density_to_page(self._section_pages[key], compact)
        if hasattr(self, "history_table"):
            self.history_table.verticalHeader().setDefaultSectionSize(27 if compact else 32)
            self.history_table.setMinimumHeight(260 if compact else 330)
        for button in self.findChildren(SettingsNavButton):
            button.setMinimumHeight(32 if compact else 40)
        self.setProperty("compactDensity", compact)
        self.style().unpolish(self)
        self.style().polish(self)
        apply_layout_density(self, compact)
        self.updateGeometry()

    def refresh_appearance(self) -> None:
        if self.parent() is None:
            self.setStyleSheet(settings_stylesheet())
        self._applied_density = None
        self.apply_density(str(self.app_settings.value("settings/density", "comfortable")))
        for button in self.nav_buttons.values():
            button.refresh_icon()
        self._search_action.setIcon(tinted_icon("search", COLORS["muted"]))
        sync = getattr(self, "_sync_appearance_previews", None)
        if sync is not None:
            # The miniatures paint the live palette themselves.
            sync()
            for card in self.theme_cards.values():
                card.update()

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
            "settings/gamepad_navigation": "false",
            REPORT_GLOW_KEY: "true",
            "settings/gamepad_onscreen_keypad": "true",
            "settings/gamepad_keypad_auto_show": "true",
            "settings/appearance": "system",
            "settings/density": "comfortable",
            "settings/scale": 100,
            "settings/accent": "blue",
            "settings/style": "formal",
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
        self.gamepad_navigation_changed.emit(False)
        self.report_glow_changed.emit(True)
        self.gamepad_keypad_changed.emit(True)
        self.gamepad_keypad_auto_show_changed.emit(True)
        show_toast(
            self,
            "Preferences restored",
            "Interface preferences were restored. Hardware profiles, limits, commands, and history were not changed.",
            tone="green",
        )


class SettingsDialog(QDialog):
    #: The controller's Menu button opens Settings and closes them again.
    gamepad_closes_with_menu = True

    language_changed = pyqtSignal(str)
    appearance_changed = pyqtSignal(str, str, str)
    scale_changed = pyqtSignal(int)
    smart_alerts_changed = pyqtSignal(bool)
    desktop_notifications_changed = pyqtSignal(bool)
    diagnostics_changed = pyqtSignal(bool)
    sidebar_collapsed_changed = pyqtSignal(bool)
    gamepad_navigation_changed = pyqtSignal(bool)
    report_glow_changed = pyqtSignal(bool)
    gamepad_keypad_changed = pyqtSignal(bool)
    gamepad_keypad_auto_show_changed = pyqtSignal(bool)
    embedded_terminal_changed = pyqtSignal(bool)
    console_auto_hide_changed = pyqtSignal(bool)
    console_theme_changed = pyqtSignal(str)
    gddr6_manual_changed = pyqtSignal(bool)
    vrm_manual_changed = pyqtSignal(bool)
    tour_requested = pyqtSignal()
    update_requested = pyqtSignal()

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
            # Wide enough for the side navigation at every scale up to 110 %:
            # below 760 px the sections fold into a two-column grid above the
            # content, which cost a third of the height before any setting.
            preferred_width=1180,
            preferred_height=780,
            minimum_width=620,
            minimum_height=460,
        )

        outer = QVBoxLayout(self)
        # Room for the shadow, so the window floats over the application.
        outer.setContentsMargins(self.SHADOW_MARGIN, self.SHADOW_MARGIN - 4, self.SHADOW_MARGIN, self.SHADOW_MARGIN + 4)
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
        self.page.update_requested.connect(self.update_requested.emit)
        self.page.gamepad_navigation_changed.connect(self.gamepad_navigation_changed.emit)
        self.page.report_glow_changed.connect(self.report_glow_changed.emit)
        self.page.gamepad_keypad_changed.connect(self.gamepad_keypad_changed.emit)
        self.page.gamepad_keypad_auto_show_changed.connect(self.gamepad_keypad_auto_show_changed.emit)
        self.page.embedded_terminal_changed.connect(self.embedded_terminal_changed.emit)
        self.page.console_auto_hide_changed.connect(self.console_auto_hide_changed.emit)
        self.page.console_theme_changed.connect(self.console_theme_changed.emit)
        self.page.gddr6_manual_changed.connect(self.gddr6_manual_changed.emit)
        self.page.vrm_manual_changed.connect(self.vrm_manual_changed.emit)
        outer.addWidget(self.page, 1)
        self._lift_window()

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

    SHADOW_MARGIN = 18

    def _lift_window(self) -> None:
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect

        shadow = self.page.shell.graphicsEffect()
        if not isinstance(shadow, QGraphicsDropShadowEffect):
            shadow = QGraphicsDropShadowEffect(self.page.shell)
            self.page.shell.setGraphicsEffect(shadow)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 150 if _theme.ACTIVE_MODE != "light" else 60))

    def _request_close(self) -> None:
        if self.page.has_running_tasks():
            show_toast(
                self,
                "Operation still running",
                "Wait for the current settings operation to finish before closing this window.",
                tone="blue",
            )
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
        self._lift_window()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        # Clear of the section's scrollbar, level with the section title.
        # Level with the tabs, inside the shadow's margin.
        self.close_button.move(
            max(0, self.width() - self.close_button.width() - 12 - self.SHADOW_MARGIN), self.SHADOW_MARGIN - 4 + 8
        )
        self.close_button.raise_()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        language = current_language()
        if language != self._localized_language:
            localize_widget_tree(self)
            self._localized_language = language
        self.fit_to_content()
        center_dialog(self)
