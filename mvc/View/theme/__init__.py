from __future__ import annotations

from copy import deepcopy
import re


LIGHT_COLORS = {
    "window": "#F4F6F8",
    "panel": "#FFFFFF",
    "panel_alt": "#F7F8FA",
    "panel_raised": "#FFFFFF",
    "control": "#FFFFFF",
    "control_hover": "#F0F3F6",
    "control_pressed": "#E7EBF0",
    "border": "#D4DBE4",
    "border_soft": "#E7EBF0",
    "border_strong": "#B8C2CF",
    "text": "#111827",
    "muted": "#667085",
    "subtle": "#98A2B3",
    "disabled_bg": "#E9EDF2",
    "disabled_text": "#98A2B3",
    "focus": "#8DB4FF",
    "selection": "#E7F0FF",
    "scrollbar": "#C4CCD7",
    "scrollbar_hover": "#A7B2C1",
    "progress_track": "#E9EDF2",
    "chart_surface": "#FCFDFE",
    "chart_grid": "#E8EDF3",
    "chart_axis": "#C8D1DC",
    "neutral_soft": "#EFF2F5",
    "neutral_border": "#DCE2E9",
    "icon_border": "#FFFFFF",
    "on_accent": "#FFFFFF",
    "console_bg": "#0E1728",
    "console_text": "#DCE6F6",
    "console_border": "#26344A",
    "blue": "#2563EB",
    "blue_soft": "#EAF2FF",
    "purple": "#7657E8",
    "purple_soft": "#F1EDFF",
    "orange": "#E96912",
    "orange_soft": "#FFF1E8",
    "cyan": "#0799B3",
    "cyan_soft": "#E7F8FB",
    "green": "#079669",
    "green_soft": "#E8F8F2",
    "red": "#D92D20",
    "red_soft": "#FDEDEC",
}

# Neutral graphite palette modeled after ChatGPT/Codex desktop surfaces.  The
# hierarchy comes from small luminance steps instead of bright borders, so the
# interface remains readable without looking like a light theme with black paint.
DARK_COLORS = {
    "window": "#0F0F0F",
    "panel": "#171717",
    "panel_alt": "#1F1F1F",
    "panel_raised": "#242424",
    "control": "#242424",
    "control_hover": "#2C2C2C",
    "control_pressed": "#333333",
    "border": "#343434",
    "border_soft": "#292929",
    "border_strong": "#4A4A4A",
    "text": "#F2F2F2",
    "muted": "#B4B4B4",
    "subtle": "#8E8E8E",
    "disabled_bg": "#292929",
    "disabled_text": "#707070",
    "focus": "#6E9FFF",
    "selection": "#24354F",
    "scrollbar": "#424242",
    "scrollbar_hover": "#5A5A5A",
    "progress_track": "#2A2A2A",
    "chart_surface": "#151515",
    "chart_grid": "#2D2D2D",
    "chart_axis": "#4A4A4A",
    "neutral_soft": "#242424",
    "neutral_border": "#363636",
    "icon_border": "#353535",
    "on_accent": "#FFFFFF",
    "console_bg": "#0A0A0A",
    "console_text": "#E6E6E6",
    "console_border": "#333333",
    "blue": "#5B8DEF",
    "blue_soft": "#1D2A3D",
    "purple": "#B39DFF",
    "purple_soft": "#2B2440",
    "orange": "#F0A45D",
    "orange_soft": "#38291D",
    "cyan": "#56C7D4",
    "cyan_soft": "#183137",
    "green": "#5CBF78",
    "green_soft": "#1B3224",
    "red": "#FF6B64",
    "red_soft": "#3A2020",
}


ACCENTS = {
    "blue": ("#2563EB", "#EAF2FF", "#5B8DEF", "#1D2A3D"),
    "violet": ("#7657E8", "#F1EDFF", "#B39DFF", "#2B2440"),
    "cyan": ("#0799B3", "#E7F8FB", "#56C7D4", "#183137"),
    "green": ("#079669", "#E8F8F2", "#5CBF78", "#1B3224"),
    "orange": ("#E96912", "#FFF1E8", "#F0A45D", "#38291D"),
}

ACTIVE_MODE = "light"
ACTIVE_ACCENT = "blue"
ACTIVE_DENSITY = "comfortable"
ACTIVE_SCALE = 100
COLORS = deepcopy(LIGHT_COLORS)
_STYLESHEET_CACHE: dict[tuple[str, str, str, int], str] = {}


def _blend(base: str, overlay: str, amount: float) -> str:
    """Blend two #RRGGBB colors without depending on Qt."""
    amount = max(0.0, min(1.0, float(amount)))
    try:
        left = tuple(int(base[index:index + 2], 16) for index in (1, 3, 5))
        right = tuple(int(overlay[index:index + 2], 16) for index in (1, 3, 5))
    except (TypeError, ValueError):
        return str(base)
    mixed = tuple(round(a * (1.0 - amount) + b * amount) for a, b in zip(left, right))
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def _finish_palette(palette: dict[str, str], mode: str) -> dict[str, str]:
    for tone in ("blue", "purple", "orange", "cyan", "green", "red"):
        palette[f"{tone}_border"] = _blend(
            palette[tone], palette["panel"], 0.58 if mode == "dark" else 0.72
        )
    palette["blue_hover"] = _blend(
        palette["blue"], "#FFFFFF" if mode == "dark" else "#000000", 0.10
    )
    palette["blue_pressed"] = _blend(
        palette["blue"], "#FFFFFF" if mode == "dark" else "#000000", 0.18
    )
    palette["orange_hover"] = _blend(
        palette["orange"], "#FFFFFF" if mode == "dark" else "#000000", 0.10
    )
    palette["red_hover"] = _blend(
        palette["red"], "#FFFFFF" if mode == "dark" else "#000000", 0.10
    )
    return palette


def semantic_color_key(value: object, preferred: str | None = None) -> str | None:
    """Resolve a previously stored palette color back to a semantic token.

    Widgets created before a live theme switch may hold the old hexadecimal
    value.  Looking through both palettes lets them refresh without rebuilding
    the page.  ``preferred`` disambiguates accent colors that intentionally
    share a value.
    """
    text = str(value or "").strip()
    if text in COLORS:
        return text
    normalized = text.upper()
    candidates: list[str] = []
    palettes = (COLORS, LIGHT_COLORS, DARK_COLORS)
    for palette in palettes:
        for key, color in palette.items():
            if str(color).upper() == normalized and key not in candidates:
                candidates.append(key)
    for _name, values in ACCENTS.items():
        for key, color in (("blue", values[0]), ("blue_soft", values[1]), ("blue", values[2]), ("blue_soft", values[3])):
            if color.upper() == normalized and key not in candidates:
                candidates.append(key)
    aliases = {
        "#EEF3F9": "neutral_soft", "#EEF2F7": "neutral_soft", "#F0F4F8": "neutral_soft",
        "#EFF2F6": "neutral_soft", "#F2F5F8": "neutral_soft",
    }
    alias = aliases.get(normalized)
    if alias and alias not in candidates:
        candidates.append(alias)
    if preferred and preferred in candidates:
        return preferred
    priority = (
        "neutral_soft", "blue_soft", "purple_soft", "orange_soft", "cyan_soft", "green_soft", "red_soft",
        "blue", "purple", "orange", "cyan", "green", "red", "panel_alt", "panel", "text", "muted", "subtle",
    )
    return next((key for key in priority if key in candidates), candidates[0] if candidates else None)


def palette_color(value: object, preferred: str | None = None) -> str:
    key = semantic_color_key(value, preferred)
    return COLORS.get(key, str(value or COLORS["neutral_soft"]))


COLORS.clear()
COLORS.update(_finish_palette(deepcopy(LIGHT_COLORS), "light"))


def configure_theme(mode: str = "light", accent: str = "blue", density: str = "comfortable", scale: int = 100) -> dict[str, str]:
    global ACTIVE_MODE, ACTIVE_ACCENT, ACTIVE_DENSITY, ACTIVE_SCALE
    mode = str(mode or "light").lower()
    if mode not in {"light", "dark"}:
        mode = "light"
    accent = str(accent or "blue").lower()
    if accent not in ACCENTS:
        accent = "blue"
    density = str(density or "comfortable").lower()
    if density not in {"comfortable", "compact"}:
        density = "comfortable"
    try:
        scale = int(round(float(scale) / 10.0) * 10)
    except (TypeError, ValueError, OverflowError):
        scale = 100
    scale = max(70, min(150, scale))
    if (mode, accent, density, scale) == (ACTIVE_MODE, ACTIVE_ACCENT, ACTIVE_DENSITY, ACTIVE_SCALE):
        return COLORS
    palette = deepcopy(DARK_COLORS if mode == "dark" else LIGHT_COLORS)
    light_value, light_soft, dark_value, dark_soft = ACCENTS[accent]
    palette["blue"] = dark_value if mode == "dark" else light_value
    palette["blue_soft"] = dark_soft if mode == "dark" else light_soft
    _finish_palette(palette, mode)
    COLORS.clear()
    COLORS.update(palette)
    ACTIVE_MODE = mode
    ACTIVE_ACCENT = accent
    ACTIVE_DENSITY = density
    ACTIVE_SCALE = scale
    return COLORS


def scale_stylesheet(stylesheet: str, scale: int | None = None) -> str:
    factor = (ACTIVE_SCALE if scale is None else max(70, min(150, int(scale)))) / 100.0
    if abs(factor - 1.0) < 0.001:
        return stylesheet

    def replace(match: re.Match[str]) -> str:
        value = float(match.group(1))
        scaled = max(1.0, value * factor)
        rendered = str(int(round(scaled))) if scaled >= 1 else f"{scaled:.1f}"
        return rendered + "px"

    return re.sub(r"(?<![A-Za-z0-9_#.-])(\d+(?:\.\d+)?)px", replace, stylesheet)


def application_stylesheet(mode: str | None = None, accent: str | None = None, density: str | None = None, scale: int | None = None) -> str:
    if mode is not None or accent is not None or density is not None or scale is not None:
        configure_theme(mode or ACTIVE_MODE, accent or ACTIVE_ACCENT, density or ACTIVE_DENSITY, ACTIVE_SCALE if scale is None else scale)
    cache_key = (ACTIVE_MODE, ACTIVE_ACCENT, ACTIVE_DENSITY, ACTIVE_SCALE)
    cached = _STYLESHEET_CACHE.get(cache_key)
    if cached is not None:
        return cached
    c = COLORS
    base = f"""
    * {{
        font-family: Inter, 'Noto Sans', 'Segoe UI', sans-serif;
        color: {c['text']};
    }}
    QMainWindow, QWidget#ApplicationRoot {{
        background: {c['window']};
    }}
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 1px 4px 1px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['scrollbar']};
        border-radius: 4px;
        min-height: 44px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['scrollbar_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QFrame#Sidebar {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 16px;
    }}
    QLabel#BrandTitle {{
        font-size: 18px;
        font-weight: 820;
        color: {c['text']};
    }}
    QLabel#BrandSubtitle {{
        font-size: 11px;
        font-weight: 600;
        color: {c['muted']};
    }}
    QFrame#SidebarDivider, QFrame#CardDivider, QFrame#ListDivider {{
        background: {c['border_soft']};
        border: none;
    }}
    QPushButton#SidebarToggle {{
        background: transparent;
        border: 0px;
        border-radius: 8px;
        padding: 8px;
        color: {c['text']};
        font-size: 18px;
        font-weight: 760;
    }}
    QPushButton#SidebarToggle:hover {{
        background: {c['panel_alt']};
    }}
    QPushButton[nav='true'] {{
        background: transparent;
        border: 0px;
        border-radius: 10px;
        padding: 9px 10px;
        text-align: left;
        font-size: 12px;
        font-weight: 700;
        color: {c['text']};
    }}
    QPushButton[nav='true']:hover {{
        background: {c['panel_alt']};
    }}
    QPushButton[nav='true']:checked {{
        background: {c['blue_soft']};
        color: {c['blue']};
    }}
    QPushButton[nav='true'][collapsed='true'] {{
        padding: 0px;
        text-align: center;
        min-width: 42px;
        max-width: 42px;
        min-height: 42px;
        max-height: 42px;
    }}
    QFrame#SidebarStatus {{
        background: {c['blue_soft']};
        border: 1px solid {c['blue']};
        border-radius: 12px;
    }}
    QLabel#SidebarStatusTitle {{
        color: {c['text']};
        font-size: 11px;
        font-weight: 800;
    }}
    QLabel#SidebarStatusDetail {{
        color: {c['muted']};
        font-size: 9px;
        font-weight: 650;
    }}
    QLabel#PageEyebrow {{
        color: {c['blue']};
        font-size: 9px;
        font-weight: 850;
        letter-spacing: 1.2px;
    }}
    QLabel#PageTitle {{
        font-size: 31px;
        font-weight: 830;
        color: {c['text']};
    }}
    QLabel#PageSubtitle {{
        font-size: 13px;
        color: {c['muted']};
        line-height: 1.3em;
    }}
    QFrame#HeaderStatus {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QLabel#HeaderStatusText {{
        color: {c['muted']};
        font-size: 11px;
        font-weight: 750;
    }}
    QPushButton#RefreshButton {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 12px;
        padding: 10px 15px;
        font-weight: 730;
    }}
    QPushButton#RefreshButton:hover {{
        background: {c['blue_soft']};
        border-color: {c['blue_border']};
        color: {c['blue']};
    }}
    QFrame[card='true'], QFrame[sectionCard='true'], QFrame[moduleCard='true'] {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 20px;
    }}
    QLabel[cardTitle='true'] {{
        font-size: 15px;
        font-weight: 780;
        color: {c['text']};
    }}
    QLabel[sectionSubtitle='true'] {{
        color: {c['muted']};
        font-size: 11px;
    }}
    QLabel[metricLabel='true'] {{
        color: {c['muted']};
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel[metricValue='true'] {{
        font-size: 20px;
        font-weight: 830;
        color: {c['text']};
    }}
    QLabel[pill='true'] {{
        border-radius: 8px;
        padding: 4px 9px;
        font-size: 10px;
        font-weight: 780;
    }}
    QPushButton[cardAction='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border']};
        border-radius: 12px;
        padding: 10px 13px;
        font-weight: 720;
        color: {c['text']};
    }}
    QPushButton[cardAction='true']:hover {{
        background: {c['control_hover']};
        border-color: {c['blue_border']};
        color: {c['blue']};
    }}
    QPushButton[compactAction='true'] {{
        background: {c['panel_raised']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 11px;
        font-weight: 700;
        color: {c['muted']};
    }}
    QPushButton[compactAction='true']:hover {{
        background: {c['control_hover']};
        border-color: {c['border']};
    }}
    QFrame[quickActionRow='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 11px;
    }}
    QFrame[quickActionRow='true'][hovered='true'] {{
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
    }}
    QLabel[actionTitle='true'] {{
        font-size: 12px;
        font-weight: 760;
        color: {c['text']};
    }}
    QLabel[actionSubtitle='true'] {{
        color: {c['muted']};
        font-size: 10px;
    }}
    QFrame#ReadinessMarker {{
        background: {c['green_soft']};
        border: 1px solid {c['green_border']};
        border-radius: 8px;
    }}
    QLabel[rowLabel='true'], QLabel[activityText='true'] {{
        color: {c['muted']};
        font-size: 11px;
    }}
    QLabel[activityTime='true'] {{
        color: {c['subtle']};
        font-size: 10px;
    }}
    QLabel#ReadinessSubtitle {{
        font-size: 11px;
    }}
    QProgressBar {{
        background: {c['progress_track']};
        border: none;
        border-radius: 4px;
        min-height: 7px;
        max-height: 7px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {c['orange']};
        border-radius: 4px;
    }}
    QFrame#SystemSummaryBar {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 18px;
    }}
    QLabel#SummaryLabel {{
        color: {c['muted']};
        font-size: 10px;
        font-weight: 700;
    }}
    QLabel#SummaryValue {{
        color: {c['text']};
        font-size: 14px;
        font-weight: 830;
    }}
    QFrame#SummaryDivider {{
        background: {c['border_soft']};
        border: none;
        min-width: 1px;
        max-width: 1px;
    }}
    QDialog#InfoDialog {{
        background: transparent;
    }}
    QFrame#ControlDialogCard {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 18px;
    }}
    QLabel#DialogEyebrow {{
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#DialogTitle {{
        color: {c['text']};
        font-size: 19px;
        font-weight: 800;
    }}
    QLabel#DialogBody {{
        color: {c['muted']};
        font-size: 13px;
    }}
    QFrame#DialogNotice {{
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        border-radius: 10px;
    }}
    QLabel#DialogNoticeText {{
        color: {c['muted']};
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#DialogClose {{
        background: transparent;
        border: none;
        border-radius: 9px;
        padding: 5px;
    }}
    QPushButton#DialogClose:hover {{
        background: {c['control_hover']};
    }}
    QPushButton#DialogClose:pressed {{
        background: {c['control_pressed']};
    }}
    QPushButton#DialogPrimary {{
        background: {c['blue']};
        color: {c['on_accent']};
        border: 1px solid {c['blue']};
        border-radius: 9px;
        padding: 10px 18px;
        font-weight: 750;
    }}
    QPushButton#DialogPrimary:hover {{
        background: {c['blue_hover']};
        border-color: {c['blue_hover']};
    }}
    QPushButton#DialogPrimary:pressed {{
        background: {c['blue_pressed']};
        border-color: {c['blue_pressed']};
    }}
    QPushButton#DialogDanger {{
        background: {c['orange']};
        color: {c['on_accent']};
        border: 1px solid {c['orange']};
        border-radius: 9px;
        padding: 10px 18px;
        font-weight: 750;
    }}
    QPushButton#DialogDanger:hover {{
        background: {c['orange_hover']};
        border-color: {c['orange_hover']};
    }}
    QPushButton#PrimaryAction, QPushButton[primaryAction='true'] {{
        background: {c['blue']};
        color: {c['on_accent']};
        border: 1px solid {c['blue']};
        border-radius: 11px;
        padding: 10px 16px;
        font-weight: 780;
    }}
    QPushButton#PrimaryAction:hover, QPushButton[primaryAction='true']:hover {{
        background: {c['blue_hover']};
        border-color: {c['blue_hover']};
    }}
    QPushButton#PrimaryAction:disabled, QPushButton[primaryAction='true']:disabled {{
        background: {c['disabled_bg']};
        border-color: {c['disabled_bg']};
        color: {c['on_accent']};
    }}
    QPushButton[dangerAction='true'] {{
        background: {c['red_soft']};
        color: {c['red']};
        border: 1px solid {c['red_border']};
        border-radius: 10px;
        padding: 8px 13px;
        font-weight: 760;
    }}
    QPushButton[dangerAction='true']:hover {{
        background: {c['red_soft']};
        border-color: {c['red_border']};
    }}
    QFrame[pageCard='true'] {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 20px;
    }}
    QFrame[metricTile='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QLabel[metricTileLabel='true'] {{
        color: {c['muted']};
        font-size: 10px;
        font-weight: 700;
    }}
    QLabel[metricTileValue='true'] {{
        color: {c['text']};
        font-size: 19px;
        font-weight: 830;
    }}
    QLabel[metricTileDetail='true'] {{
        color: {c['subtle']};
        font-size: 9px;
    }}
    QFrame[profileCard='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QFrame[profileCard='true']:hover {{
        background: {c['panel']};
        border-color: {c['border_strong']};
    }}
    QLabel[profileTitle='true'] {{
        color: {c['text']};
        font-size: 13px;
        font-weight: 780;
    }}
    QLabel[profileDescription='true'] {{
        color: {c['muted']};
        font-size: 10px;
    }}
    QLabel[valueChip='true'] {{
        color: {c['muted']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
        padding: 4px 7px;
        font-size: 9px;
        font-weight: 700;
    }}
    QLabel[fieldLabel='true'] {{
        color: {c['muted']};
        font-size: 10px;
        font-weight: 760;
    }}
    QLabel[fieldHint='true'] {{
        color: {c['subtle']};
        font-size: 9px;
    }}
    QSpinBox, QComboBox, QLineEdit {{
        background: {c['control']};
        border: 1px solid {c['border']};
        border-radius: 11px;
        padding: 9px 11px;
        min-height: 20px;
        font-weight: 710;
        selection-background-color: {c['blue_soft']};
    }}
    QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
        border-color: {c['focus']};
    }}
    QPlainTextEdit#OperationConsole {{
        background: {c['console_bg']};
        color: {c['console_text']};
        border: 1px solid {c['console_border']};
        border-radius: 11px;
        padding: 10px;
        font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
        font-size: 10px;
        selection-background-color: {c['selection']};
    }}
    QFrame[safetyNotice='orange'] {{
        background: {c['orange_soft']};
        border: 1px solid {c['orange_border']};
        border-radius: 11px;
    }}
    QFrame[safetyNotice='blue'] {{
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        border-radius: 11px;
    }}
    QLabel[noticeTitle='true'] {{
        color: {c['orange']};
        font-size: 11px;
        font-weight: 800;
    }}
    QLabel[noticeBody='true'] {{
        color: {c['muted']};
        font-size: 10px;
    }}
    QFrame[safetyNotice='blue'] QLabel[noticeTitle='true'] {{
        color: {c['blue']};
    }}
    QFrame[safetyNotice='blue'] QLabel[noticeBody='true'] {{
        color: {c['muted']};
    }}
    QFrame[confirmSummary='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
    }}
    QLabel[confirmLabel='true'] {{
        color: {c['muted']};
        font-size: 10px;
        font-weight: 650;
    }}
    QLabel[confirmValue='true'] {{
        color: {c['text']};
        font-size: 11px;
        font-weight: 780;
    }}
    QTableWidget {{
        background: {c['panel']};
        alternate-background-color: {c['panel_alt']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        gridline-color: {c['border_soft']};
        selection-background-color: {c['blue_soft']};
        selection-color: {c['text']};
    }}
    QHeaderView::section {{
        background: {c['panel_alt']};
        color: {c['muted']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 8px;
        font-size: 10px;
        font-weight: 750;
    }}
    QLabel[pageMode='true'] {{
        color: {c['green']};
        font-size: 9px;
        font-weight: 800;
    }}
    QFrame[heroTelemetry='true'] {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 22px;
    }}
    QFrame[heroTelemetry='true'][tone='blue'] {{
        border-left: 4px solid {c['blue']};
    }}
    QFrame[heroTelemetry='true'][tone='purple'] {{
        border-left: 4px solid {c['purple']};
    }}
    QFrame#HeroDivider {{
        background: {c['border_soft']};
        border: none;
    }}
    QLabel[heroTitle='true'] {{
        color: {c['text']};
        font-size: 14px;
        font-weight: 800;
    }}
    QLabel[heroPrimaryLabel='true'] {{
        color: {c['muted']};
        font-size: 10px;
        font-weight: 750;
    }}
    QLabel[heroPrimaryValue='true'] {{
        color: {c['text']};
        font-size: 36px;
        font-weight: 860;
    }}
    QLabel[heroPrimaryDetail='true'] {{
        color: {c['subtle']};
        font-size: 10px;
    }}
    QLabel[heroStatLabel='true'] {{
        color: {c['muted']};
        font-size: 9px;
        font-weight: 750;
    }}
    QLabel[heroStatValue='true'] {{
        color: {c['text']};
        font-size: 17px;
        font-weight: 820;
    }}
    QLabel[heroStatDetail='true'] {{
        color: {c['subtle']};
        font-size: 9px;
    }}
    QFrame[gpuSummaryStrip='true'] {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 18px;
    }}
    QFrame[gpuSummaryItem='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 14px;
    }}
    QFrame[gpuSummaryItem='true']:hover {{
        background: {c['panel_raised']};
        border-color: {c['border_strong']};
    }}
    QLabel[gpuSummaryLabel='true'] {{
        color: {c['muted']};
        font-size: 8px;
        font-weight: 760;
    }}
    QLabel[gpuSummaryValue='true'] {{
        color: {c['text']};
        font-size: 15px;
        font-weight: 830;
    }}
    QLabel[gpuSummaryDetail='true'] {{
        color: {c['subtle']};
        font-size: 8px;
    }}
    QFrame[compactVoltageSummaryItem='true'] QLabel[gpuSummaryLabel='true'] {{
        font-size: 9px;
    }}
    QFrame[compactVoltageSummaryItem='true'] QLabel[gpuSummaryValue='true'] {{
        font-size: 14px;
    }}
    QFrame[compactVoltageSummaryItem='true'] QLabel[gpuSummaryDetail='true'] {{
        font-size: 8px;
    }}
    QFrame[frequencyField='true'], QFrame[compactPanel='true'], QFrame[runtimeStatCard='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 14px;
    }}
    QFrame[frequencyField='true']:hover, QFrame[compactPanel='true']:hover, QFrame[runtimeStatCard='true']:hover {{
        background: {c['panel']};
        border-color: {c['border_strong']};
    }}
    QLineEdit[frequencyInput='true'] {{
        min-height: 20px;
        padding: 7px 9px;
        font-size: 12px;
        font-weight: 800;
    }}
    QLabel[frequencyUnit='true'] {{
        color: {c['muted']};
        font-size: 10px;
        font-weight: 750;
    }}
    QLabel[runtimeStatLabel='true'] {{
        color: {c['muted']};
        font-size: 9px;
        font-weight: 760;
    }}
    QLabel[runtimeStatValue='true'] {{
        color: {c['text']};
        font-size: 13px;
        font-weight: 830;
    }}
    QLabel[runtimeStatDetail='true'] {{
        color: {c['subtle']};
        font-size: 8px;
    }}
    QFrame[frequencySelect='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 11px;
    }}
    QFrame[frequencySelect='true']:hover {{
        background: {c['panel']};
        border-color: {c['border_strong']};
    }}
    QFrame[sliderControl='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QLabel[sliderLabel='true'] {{
        color: {c['text']};
        font-size: 11px;
        font-weight: 780;
    }}
    QLabel[sliderLimit='true'] {{
        color: {c['subtle']};
        font-size: 8px;
        font-weight: 700;
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {c['border_soft']};
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{
        background: {c['blue']};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {c['panel']};
        border: 2px solid {c['blue']};
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QPushButton[presetButton='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 14px;
        padding: 12px 14px;
        text-align: left;
        color: {c['muted']};
        font-size: 10px;
        font-weight: 690;
    }}
    QPushButton[presetButton='true']:hover {{
        background: {c['panel']};
        border-color: {c['border_strong']};
    }}
    QPushButton[presetButton='true']:checked {{
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        color: {c['blue']};
    }}
    QPushButton[presetButton='true']:disabled {{
        color: {c['disabled_text']};
        background: {c['panel_alt']};
        border-color: {c['border_soft']};
    }}
    QWidget[cpuSmuPage='true'] QPushButton[cpuFrequencyPreset='true'] {{
        min-height: 40px;
        padding: 11px 14px;
        font-size: 11px;
        font-weight: 740;
    }}
    QWidget[cpuSmuPage='true'] QLineEdit[frequencyInput='true'] {{
        min-height: 22px;
        font-size: 13px;
        font-weight: 820;
    }}
    QWidget[gpuGovernorPage='true'] QPushButton[gpuFrequencyPreset='true'] {{
        min-height: 40px;
        padding: 11px 14px;
        font-size: 11px;
        font-weight: 740;
    }}
    QWidget[gpuGovernorPage='true'] QPushButton[gpuFrequencyAction='true'] {{
        min-height: 20px;
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 800;
    }}
    QWidget[gpuGovernorPage='true'] QLineEdit[frequencyInput='true'] {{
        min-height: 22px;
        font-size: 13px;
        font-weight: 820;
    }}
    QFrame[dependencyActionTile='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QFrame[dependencyActionTile='true']:hover {{
        background: {c['panel_raised']};
        border-color: {c['border_strong']};
    }}
    QPushButton[dependencyPrepareButton='true'] {{
        min-height: 20px;
        padding: 6px 13px;
        border-radius: 9px;
        background: {c['blue']};
        color: {c['on_accent']};
        border: 1px solid {c['blue']};
        font-size: 11px;
        font-weight: 800;
        text-align: center;
    }}
    QPushButton[dependencyPrepareButton='true']:hover {{
        background: {c['blue_hover']};
        border-color: {c['blue_hover']};
    }}
    QPushButton[dependencyPrepareButton='true']:disabled {{
        background: {c['disabled_bg']};
        border-color: {c['disabled_bg']};
        color: {c['on_accent']};
    }}
    QFrame[voltageLabToolbar='true'] {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 16px;
    }}
    QLabel[voltageToolbarTitle='true'] {{
        color: {c['text']};
        font-size: 16px;
        font-weight: 850;
    }}
    QPushButton[voltageToolbarButton='true'] {{
        padding: 6px 13px;
        font-size: 11px;
        font-weight: 790;
    }}
    QLabel[voltageToolbarSubtitle='true'] {{
        color: {c['muted']};
        font-size: 9px;
        font-weight: 620;
    }}
    QWidget[voltageLabPage='true'] QFrame[pageCard='true'] {{
        border-radius: 14px;
    }}
    QWidget[voltageLabPage='true'] QFrame[compactPageCard='true'] QLabel[cardTitle='true'] {{
        font-size: 14px;
        font-weight: 830;
    }}
    QWidget[voltageLabPage='true'] QFrame[compactPageCard='true'] QLabel[sectionSubtitle='true'] {{
        font-size: 9px;
        font-weight: 620;
    }}
    QFrame[compactPageCard='true'] QFrame#CardDivider {{
        margin-top: 0px;
        margin-bottom: 0px;
    }}
    QPushButton[voltageProfileButton='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
        padding: 8px 11px;
        text-align: left;
        color: {c['text']};
        font-size: 11px;
        font-weight: 760;
    }}
    QPushButton[voltageProfileButton='true']:hover {{
        background: {c['panel_raised']};
        border-color: {c['border_strong']};
    }}
    QPushButton[voltageProfileButton='true']:checked {{
        background: {c['blue_soft']};
        border: 2px solid {c['blue']};
        color: {c['blue']};
    }}
    QPushButton[voltageProfileButton='true'][profileTone='green']:checked {{
        background: {c['green_soft']};
        border-color: {c['green_border']};
        color: {c['green']};
    }}
    QPushButton[voltageProfileButton='true'][profileTone='orange']:checked {{
        background: {c['orange_soft']};
        border-color: {c['orange_border']};
        color: {c['orange']};
    }}
    QPushButton[voltageProfileButton='true'][profileTone='purple']:checked {{
        background: {c['purple_soft']};
        border-color: {c['purple_border']};
        color: {c['purple']};
    }}
    QLabel[voltageProfileDetail='true'] {{
        color: {c['muted']};
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 9px;
        padding: 7px 10px;
        font-size: 10px;
        font-weight: 640;
    }}
    QFrame[voltageCurveGrid='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 11px;
    }}
    QFrame[voltageGridHeader='true'] {{
        background: {c['neutral_soft']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
    }}
    QLabel[voltageGridHeaderTitle='true'] {{
        color: {c['text']};
        background: transparent;
        border: none;
        font-size: 11px;
        font-weight: 830;
    }}
    QLabel[voltageGridHeaderDetail='true'] {{
        color: {c['subtle']};
        background: transparent;
        border: none;
        font-size: 9px;
        font-weight: 680;
    }}
    QFrame[voltageGridCell='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
    }}
    QFrame[voltageGridCell='true'][cellRole='frequency'] {{
        background: {c['blue_soft']};
        border-color: {c['blue_border']};
    }}
    QFrame[voltageGridCell='true'][cellRole='proposed'] {{
        background: {c['cyan_soft']};
        border-color: {c['cyan_border']};
    }}
    QFrame[voltageGridCell='true'][cellRole='safe'] {{
        background: {c['green_soft']};
        border-color: {c['green_border']};
    }}
    QFrame[voltageGridCell='true'][cellRole='positive'] {{
        background: {c['green_soft']};
        border-color: {c['green_border']};
    }}
    QFrame[voltageGridCell='true'][cellRole='warning'] {{
        background: {c['orange_soft']};
        border-color: {c['orange_border']};
    }}
    QFrame[voltageGridCell='true'][cellRole='custom'] {{
        background: {c['purple_soft']};
        border-color: {c['purple_border']};
    }}
    QFrame[voltageGridCell='true'][cellRole='muted'] {{
        background: {c['neutral_soft']};
        border-color: {c['border_soft']};
    }}
    QLabel[voltageGridValue='true'] {{
        color: {c['text']};
        background: transparent;
        border: none;
        font-size: 12px;
        font-weight: 830;
    }}
    QLabel[voltageGridDetail='true'] {{
        color: {c['subtle']};
        background: transparent;
        border: none;
        font-size: 9px;
        font-weight: 650;
    }}
    QSpinBox[voltageEditor='true'] {{
        min-width: 116px;
        padding: 4px 8px;
        border: 1px solid {c['purple_border']};
        border-radius: 8px;
        background: {c['panel_raised']};
        color: {c['purple']};
        font-size: 11px;
        font-weight: 820;
    }}
    QSpinBox[voltageEditor='true']:disabled {{
        background: {c['purple_soft']};
        color: {c['disabled_text']};
        border-color: {c['purple_border']};
    }}
    QFrame[voltageWorkflowPanel='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
    }}
    QFrame[voltageStepItem='true'] {{
        background: {c['panel_raised']};
        border: 1px solid {c['border_soft']};
        border-radius: 8px;
    }}
    QLabel[voltageStepBadge='true'] {{
        color: {c['blue']};
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        border-radius: 10px;
        font-size: 8px;
        font-weight: 850;
    }}
    QLabel[voltageStepText='true'] {{
        color: {c['text']};
        font-size: 10px;
        font-weight: 700;
    }}
    QPushButton[voltageApplyButton='true'] {{
        padding: 7px 14px;
        font-size: 11px;
        font-weight: 820;
    }}
    QFrame[compactStatusLine='true'] QLabel[statusLineLabel='true'] {{
        font-size: 9px;
    }}
    QFrame[compactStatusLine='true'] QLabel[statusLineDetail='true'] {{
        font-size: 8px;
    }}
    QFrame[compactStatusLine='true'] QLabel[statusLineValue='true'] {{
        font-size: 9px;
    }}
    QFrame[compactSafetyNotice='true'] QLabel[noticeTitle='true'] {{
        font-size: 10px;
    }}
    QFrame[compactSafetyNotice='true'] QLabel[noticeBody='true'] {{
        font-size: 8px;
    }}
    QFrame[statusLine='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
    }}
    QLabel[statusLineLabel='true'] {{
        color: {c['text']};
        font-size: 10px;
        font-weight: 760;
    }}
    QLabel[statusLineDetail='true'] {{
        color: {c['subtle']};
        font-size: 9px;
    }}
    QLabel[statusLineValue='true'] {{
        color: {c['blue']};
        font-size: 11px;
        font-weight: 800;
    }}

    QProgressBar[cuProgress='true'] {{
        min-height: 6px;
        max-height: 6px;
        margin-top: 4px;
    }}
    QFrame[cuTopologyTable='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 15px;
    }}
    QFrame[cuTableHeaderCell='true'] {{
        background: {c['neutral_soft']};
        border: 1px solid {c['border_soft']};
        border-radius: 9px;
    }}
    QLabel[cuTableHeaderTitle='true'] {{
        color: {c['text']};
        background: transparent;
        border: none;
        font-size: 9px;
        font-weight: 830;
    }}
    QLabel[cuTableHeaderDetail='true'] {{
        color: {c['subtle']};
        background: transparent;
        border: none;
        font-size: 8px;
        font-weight: 680;
    }}
    QLabel[cuTableRowLabel='true'] {{
        color: {c['text']};
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
        padding: 0 8px;
        font-size: 10px;
        font-weight: 830;
    }}
    QPushButton[wgpToggle='true'] {{
        background: {c['panel_alt']};
        color: {c['subtle']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 6px 5px;
        font-size: 9px;
        font-weight: 830;
    }}
    QPushButton[wgpToggle='true']:hover {{
        border-color: {c['border_strong']};
        background: {c['panel_raised']};
    }}
    QPushButton[wgpToggle='true'][routeState='driver_on'] {{
        background: {c['green_soft']};
        color: {c['green']};
        border: 1px solid {c['green_border']};
    }}
    QPushButton[wgpToggle='true'][routeState='driver_on']:hover {{
        background: {c['green_soft']};
        border-color: {c['green_border']};
    }}
    QPushButton[wgpToggle='true'][routeState='extra_on'] {{
        background: {c['cyan_soft']};
        color: {c['cyan']};
        border: 1px solid {c['cyan_border']};
    }}
    QPushButton[wgpToggle='true'][routeState='extra_on']:hover {{
        background: {c['cyan_soft']};
        border-color: {c['cyan_border']};
    }}
    QPushButton[wgpToggle='true'][routeState='driver_off'] {{
        background: {c['red_soft']};
        color: {c['red']};
        border: 1px solid {c['red_border']};
    }}
    QPushButton[wgpToggle='true'][routeState='driver_off']:hover {{
        background: {c['red_soft']};
        border-color: {c['red_border']};
    }}
    QPushButton[wgpToggle='true'][routeState='off'] {{
        background: {c['panel_alt']};
        color: {c['disabled_text']};
        border: 1px solid {c['border_soft']};
    }}
    QPushButton[wgpToggle='true']:disabled {{
        background: {c['neutral_soft']};
        color: {c['disabled_text']};
        border-color: {c['border_soft']};
    }}
    QLabel[cuCountValue='true'] {{
        color: {c['blue']};
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        border-radius: 10px;
        padding: 0 7px;
        font-size: 10px;
        font-weight: 850;
    }}
    QFrame[cuLegendBar='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 11px;
    }}
    QWidget[cuLegendItem='true'] {{
        background: transparent;
        border: none;
    }}
    QLabel[cuLegendToken='true'] {{
        border-radius: 6px;
        padding: 3px 5px;
        font-size: 8px;
        font-weight: 850;
    }}
    QLabel[cuLegendToken='true'][routeState='driver_on'] {{
        background: {c['green_soft']};
        color: {c['green']};
        border: 1px solid {c['green_border']};
    }}
    QLabel[cuLegendToken='true'][routeState='extra_on'] {{
        background: {c['cyan_soft']};
        color: {c['cyan']};
        border: 1px solid {c['cyan_border']};
    }}
    QLabel[cuLegendToken='true'][routeState='driver_off'] {{
        background: {c['red_soft']};
        color: {c['red']};
        border: 1px solid {c['red_border']};
    }}
    QLabel[cuLegendToken='true'][routeState='off'] {{
        background: {c['neutral_soft']};
        color: {c['subtle']};
        border: 1px solid {c['border_soft']};
    }}
    QLabel[cuLegendText='true'] {{
        color: {c['muted']};
        font-size: 8px;
        font-weight: 690;
    }}
    QPushButton[registerToggle='true'] {{
        min-height: 28px;
        padding: 5px 9px;
    }}
    QFrame[cuAdvancedRegisters='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QLabel[cuAdvancedTitle='true'] {{
        color: {c['text']};
        font-size: 10px;
        font-weight: 820;
    }}
    QLabel[cuAdvancedSubtitle='true'] {{
        color: {c['subtle']};
        font-size: 8px;
    }}
    QLabel[cuAdvancedHeader='true'] {{
        color: {c['muted']};
        background: {c['neutral_soft']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
        padding: 0 6px;
        font-size: 8px;
        font-weight: 790;
    }}
    QLabel[cuAdvancedRow='true'] {{
        color: {c['text']};
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
        padding: 0 6px;
        font-size: 9px;
        font-weight: 800;
    }}
    QLabel[cuAdvancedValue='true'] {{
        color: {c['muted']};
        background: {c['panel_raised']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
        padding: 0 6px;
        font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
        font-size: 9px;
        font-weight: 720;
    }}
    QLabel[cuAdvancedValue='true'][pending='true'] {{
        color: {c['orange']};
        background: {c['orange_soft']};
        border-color: {c['orange_border']};
    }}
    QFrame[cuSelectionPanel='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QLabel[cuSelectionTitle='true'] {{
        color: {c['text']};
        font-size: 12px;
        font-weight: 820;
    }}
    QLabel[cuSelectionDetail='true'] {{
        color: {c['muted']};
        font-size: 9px;
    }}
    QLabel[cuProfileNote='true'] {{
        color: {c['muted']};
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        border-radius: 9px;
        padding: 8px 10px;
        font-size: 9px;
        font-weight: 760;
    }}
    QFrame[cuActivityDot='true'] {{
        background: {c['green']};
        border: none;
        border-radius: 4px;
    }}
    QFrame[cuActivityDot='true'][tone='blue'] {{ background: {c['blue']}; }}
    QFrame[cuActivityDot='true'][tone='purple'] {{ background: {c['purple']}; }}
    QFrame[cuActivityDot='true'][tone='red'] {{ background: {c['red']}; }}
    QFrame[cuActivityDot='true'][tone='gray'] {{ background: {c['subtle']}; }}
    QLabel[cuActivityTitle='true'] {{
        color: {c['text']};
        font-size: 10px;
        font-weight: 760;
    }}
    QLabel[cuActivityDetail='true'] {{
        color: {c['muted']};
        font-size: 9px;
    }}
    QWidget[computeUnitsPage='true'] QPushButton[compactAction='true']:disabled, QWidget[computeUnitsPage='true'] QPushButton[dangerAction='true']:disabled {{
        background: {c['neutral_soft']};
        color: {c['disabled_text']};
        border-color: {c['border_soft']};
    }}

    QFrame[curvePoint='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 14px;
    }}
    QFrame[curvePoint='true']:hover {{
        background: {c['panel_raised']};
        border-color: {c['border_strong']};
    }}
    QLabel[curvePointTitle='true'] {{
        color: {c['text']};
        font-size: 11px;
        font-weight: 800;
    }}
    QLabel[curvePointBadge='true'] {{
        color: {c['purple']};
        background: {c['purple_soft']};
        border: 1px solid {c['purple_border']};
        border-radius: 7px;
        padding: 3px 7px;
        font-size: 8px;
        font-weight: 800;
    }}
    QFrame[fanChannelRow='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 12px;
    }}
    QFrame[fanChannelRow='true']:hover {{
        background: {c['panel_raised']};
        border-color: {c['border_strong']};
    }}
    QLabel[fanChannelTitle='true'] {{
        color: {c['text']};
        font-size: 11px;
        font-weight: 800;
    }}
    QLabel[fanChannelDetail='true'] {{
        color: {c['subtle']};
        font-size: 9px;
    }}
    QLabel[fanChannelValue='true'] {{
        color: {c['text']};
        font-size: 10px;
        font-weight: 780;
    }}
    QLabel[fanChannelHeader='true'] {{
        color: {c['muted']};
        font-size: 8px;
        font-weight: 800;
        padding: 0 8px;
    }}
    QLabel[fanAccess='write'] {{
        color: {c['green']};
        background: {c['green_soft']};
        border: 1px solid {c['green_border']};
        border-radius: 8px;
        padding: 5px 7px;
        font-size: 8px;
        font-weight: 800;
    }}
    QLabel[fanAccess='admin'] {{
        color: {c['blue']};
        background: {c['blue_soft']};
        border: 1px solid {c['blue_border']};
        border-radius: 8px;
        padding: 5px 7px;
        font-size: 8px;
        font-weight: 800;
    }}
    QLabel[fanAccess='read'] {{
        color: {c['orange']};
        background: {c['orange_soft']};
        border: 1px solid {c['orange_border']};
        border-radius: 8px;
        padding: 5px 7px;
        font-size: 8px;
        font-weight: 800;
    }}
    QLabel[fanAccess='off'] {{
        color: {c['muted']};
        background: {c['neutral_soft']};
        border: 1px solid {c['border_soft']};
        border-radius: 8px;
        padding: 5px 7px;
        font-size: 8px;
        font-weight: 800;
    }}
    QFrame[pathsNavigation='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 13px;
    }}
    QPushButton[pathsNavButton='true'] {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 10px 11px;
        text-align: left;
        color: {c['muted']};
        font-size: 10px;
        font-weight: 720;
    }}
    QPushButton[pathsNavButton='true']:hover {{
        background: {c['panel']};
        color: {c['text']};
    }}
    QPushButton[pathsNavButton='true']:checked {{
        background: {c['blue_soft']};
        border-color: {c['blue']};
        color: {c['blue']};
        font-weight: 800;
    }}
    QFrame[pathsSection='true'] {{
        background: {c['panel_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 13px;
    }}
    QLabel[pathsSectionTitle='true'] {{
        color: {c['text']};
        font-size: 12px;
        font-weight: 820;
    }}
    QLabel[pathsSectionDescription='true'] {{
        color: {c['muted']};
        font-size: 9px;
    }}
    QFrame[pathEntry='true'] {{
        background: {c['panel']};
        border: 1px solid {c['border_soft']};
        border-radius: 9px;
    }}
    QLabel[pathEntryLabel='true'] {{
        color: {c['muted']};
        font-size: 9px;
        font-weight: 780;
    }}
    QLabel[pathEntryValue='true'] {{
        color: {c['text']};
        font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
        font-size: 9px;
    }}
    """
    if ACTIVE_DENSITY == "compact":
        base += """
        QPushButton[nav='true'] { padding-top:7px; padding-bottom:7px; }
        QFrame[pageCard='true'] { border-radius:16px; }
        QTableWidget::item { padding-top:2px; padding-bottom:2px; }
        """
    base = scale_stylesheet(base)
    _STYLESHEET_CACHE[cache_key] = base
    return base

