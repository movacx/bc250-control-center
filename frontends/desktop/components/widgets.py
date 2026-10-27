from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bc250cc.shared.error_origins import caller_origin
from bc250cc.shared.errors import ActionNeeded

from .. import theme as theme_module
from ..core.diagnostic_history import (
    failure_section,
    origin_text,
    record_window_error,
    window_diagnosis,
)
from ..core.error_diagnostics import (
    error_sections,
    format_error_for_user,
    umr_repair_command,
)
from ..core.preferences import report_glow_enabled
from ..core.raw_errors import find as find_raw_error
from ..i18n import canonical_source, localize_widget_tree, tr
from ..theme import COLORS, application_stylesheet, palette_color, semantic_color_key
from .busy_spinner import BusySpinner
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .outline_glow import REPORT_AMBER, OutlineGlow

ICON_DIR = Path(__file__).resolve().parents[1] / "theme" / "icons"


def icon(name: str) -> QIcon:
    return QIcon(str(ICON_DIR / f"{name}.svg"))


def readable_text_on(color: QColor) -> QColor:
    """Near-black or white, whichever reads better on ``color`` (a chart tag's fill)."""

    def channel(value: int) -> float:
        value /= 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())
    return QColor("#111111") if luminance > 0.2 else QColor("#FFFFFF")


def apply_shadow(widget: QWidget, *, blur: int = 26, y: int = 6, alpha: int = 18) -> None:
    """Apply one restrained enterprise-style elevation effect."""
    if theme_module.ACTIVE_STYLE == "formal":
        # The formal style lays cards flat on their hairline: a trace of
        # depth, not a lift.
        blur, y, alpha = max(6, blur // 3), min(y, 1), max(6, alpha // 2)
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(0, 0, 0, min(90, alpha * 2) if theme_module.ACTIVE_MODE == "dark" else alpha))
    widget.setGraphicsEffect(shadow)


class IconBadge(QFrame):
    def __init__(
        self,
        icon_name: str,
        background: str,
        size: int = 42,
        parent: QWidget | None = None,
        *,
        radius: int | None = None,
    ):
        super().__init__(parent)
        self._icon_name = icon_name
        self._background_source = background
        self._preferred_color = self._infer_color_key(icon_name, background)
        self._corner_radius = size // 2 if radius is None else radius
        self.setFixedSize(size, size)
        layout = QHBoxLayout(self)
        inset = max(8, round(size * 0.22))
        layout.setContentsMargins(inset, inset, inset, inset)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(icon(icon_name).pixmap(size - (inset * 2), size - (inset * 2)))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        self._refresh_palette()

    @staticmethod
    def _infer_color_key(icon_name: str, background: object) -> str:
        explicit = semantic_color_key(background)
        if explicit and explicit.endswith("_soft"):
            return explicit
        name = str(icon_name or "").lower()
        for tone in ("purple", "orange", "green", "cyan", "red", "blue"):
            if tone in name:
                return f"{tone}_soft"
        if any(token in name for token in ("gray", "grey", "vram", "power", "refresh", "logs")):
            return "neutral_soft"
        return explicit or "blue_soft"

    def _refresh_palette(self) -> None:
        background = palette_color(self._background_source, self._preferred_color)
        self.setStyleSheet(
            f"background:{background}; border:1px solid {COLORS['icon_border']}; "
            f"border-radius:{self._corner_radius}px;"
        )


class PillLabel(QLabel):
    def __init__(self, text: str, tone: str = "green", parent: QWidget | None = None):
        super().__init__(tr(text), parent)
        self._tone = tone
        self.setProperty("pill", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._refresh_palette()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(tr(text))

    def set_tone(self, tone: str) -> None:
        if tone == self._tone:
            return
        self._tone = tone
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        tone = self._tone if self._tone in {"green", "blue", "purple", "orange", "red", "cyan"} else "gray"
        if tone == "gray":
            foreground, background, border = COLORS["muted"], COLORS["neutral_soft"], COLORS["neutral_border"]
        else:
            foreground = COLORS[tone]
            background = COLORS[f"{tone}_soft"]
            border = COLORS[f"{tone}_border"]
        # Selector-scoped: a bare declaration list also reaches child windows,
        # and this pill's tooltip is one — it took on the pill's colours.
        self.setStyleSheet(
            f"PillLabel {{ color:{foreground}; background:{background}; border:1px solid {border}; }}"
        )


def dialog_card(dialog: QDialog) -> QFrame:
    """The dialog's single surface, with a soft shadow under it."""
    card = QFrame()
    card.setObjectName("ControlDialogCard")
    shadow = QGraphicsDropShadowEffect(card)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 8)
    shadow.setColor(QColor(10, 18, 36, 70))
    card.setGraphicsEffect(shadow)
    return card


def dialog_header(dialog: QDialog, title: str, subtitle: str, icon_name: str, soft: str) -> QFrame:
    """Icon, title and a quiet subtitle, with the close button; a rule under it."""
    header = QFrame()
    header.setObjectName("DialogHeader")
    row = QHBoxLayout(header)
    row.setContentsMargins(22, 18, 14, 16)
    row.setSpacing(12)
    row.addWidget(IconBadge(icon_name, soft, 36, radius=9), 0, Qt.AlignmentFlag.AlignTop)
    heading = QVBoxLayout()
    heading.setSpacing(1)
    title_label = QLabel(title)
    title_label.setObjectName("DialogTitle")
    title_label.setWordWrap(True)
    title_label.setProperty("naturalHeight", True)
    heading.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("DialogSubtitle")
        subtitle_label.setWordWrap(True)
        subtitle_label.setProperty("naturalHeight", True)
        subtitle_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        heading.addWidget(subtitle_label)
    heading.addStretch(1)
    row.addLayout(heading, 1)
    close_button = QPushButton()
    close_button.setObjectName("DialogClose")
    close_button.setIcon(icon("close_gray"))
    close_button.setFixedSize(30, 30)
    close_button.setToolTip(tr("Close"))
    close_button.setCursor(Qt.CursorShape.PointingHandCursor)
    close_button.clicked.connect(dialog.reject)
    row.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
    return header


def _dialog_section(heading: str, text: str, *, detail: bool = False) -> QWidget:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)
    label = QLabel(heading)
    label.setObjectName("DialogSectionLabel")
    column.addWidget(label)
    body = QLabel(text)
    body.setObjectName("DialogDetailText" if detail else "DialogBody")
    body.setWordWrap(True)
    # Qt's own height for the final width: a minimum measured earlier, at a
    # narrower width, left uneven gaps between the sections.
    body.setProperty("naturalHeight", True)
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if detail:
        frame = QFrame()
        frame.setObjectName("DialogDetail")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.addWidget(body)
        column.addWidget(frame)
    else:
        column.addWidget(body)
    return holder


class ReportButton(QPushButton):
    """An error window's way to the report form, glowing like the dashboard's.

    Same amber outline, same rhythm, and the same switch in Settings >
    General. It stops for good once pressed: by then it has done its job.
    """

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._outline = OutlineGlow(self)
        self._outline.set_enabled(report_glow_enabled())
        self.clicked.connect(lambda: self._outline.set_enabled(False))

    def glowing(self) -> bool:
        return self._outline.glowing()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self._outline.shown()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().hideEvent(event)
        self._outline.hidden()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        # The button's own corner: 8 px in the stylesheet, halved by formal.
        radius = 8.0 * (theme_module.FORMAL_RADIUS_FACTOR if theme_module.ACTIVE_STYLE == "formal" else 1.0)
        self._outline.paint(REPORT_AMBER, radius * theme_module.ACTIVE_SCALE / 100)


def tighten_dialog(dialog: QDialog, scroll: QScrollArea) -> None:
    """Drop the empty band under a dialog's text once its real width is known.

    The scroll area sizes itself from a hint taken at a guessed width, which
    left a gap above the footer; the content's height for its final width is
    exact.
    """
    try:
        content = scroll.widget()
        # Measured as if the scrollbar were there: at that width the text
        # needs the most room, so the scrollbar never has to appear.
        width = scroll.width() - scroll.verticalScrollBar().sizeHint().width()
        if content is None or content.layout() is None or width <= 1:
            return
        # Word-wrapped labels can under-report their height for a width; the
        # content's own hint is the floor, or a short notice showed two lines
        # behind a scrollbar.
        needed = content.layout().totalHeightForWidth(width)
        for label in content.findChildren(QLabel):
            if label.wordWrap() and label.isVisible():
                # A wrapped label's own answer for its real width.
                needed = max(needed, label.heightForWidth(label.width()) + content.layout().contentsMargins().top()
                             + content.layout().contentsMargins().bottom())
        needed += 2
        cap = int(dialog.property("contentCap") or 440)
        # Fixed, not only capped: QScrollArea's own size hint stops at 24 text
        # lines, which cut a long error short with room left on the screen.
        scroll.setFixedHeight(max(60, min(cap, needed)))
        keep = dialog.width()
        dialog.adjustSize()
        layout = dialog.layout()
        height = (
            layout.totalHeightForWidth(keep)
            if layout is not None and layout.hasHeightForWidth()
            else dialog.sizeHint().height()
        )
        dialog.resize(keep, max(dialog.minimumHeight(), height))
    except RuntimeError:
        return


def _error_identity(code: str, origin, raw, at: float) -> QFrame:
    """Code, origin, raise site and time, in a compact sheet."""
    frame = QFrame()
    frame.setObjectName("DialogIdentity")
    grid = QGridLayout(frame)
    grid.setContentsMargins(14, 11, 14, 11)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(6)
    rows = [("Code", code)]
    if origin is not None:
        rows.append(("Origin", f"{origin.code} · {origin.place}"))
    site = getattr(raw, "site", None)
    if site is not None:
        rows.append(("Raised in", f"{site.code} · {site.place}"))
    rows.append(("Time", datetime.fromtimestamp(at).strftime("%H:%M:%S")))
    for row, (label, value) in enumerate(rows):
        name = QLabel(tr(label))
        name.setObjectName("DialogIdentityLabel")
        data = QLabel(value)
        data.setObjectName("DialogIdentityValue")
        data.setWordWrap(True)
        data.setProperty("naturalHeight", True)
        data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(data, row, 1)
    grid.setColumnStretch(1, 1)
    return frame


def _raw_error_block(detail: str, raw) -> QWidget:
    """The error exactly as it was raised; the traceback one click away."""
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(6)
    head = QHBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    label = QLabel(tr("Raw error"))
    label.setObjectName("DialogSectionLabel")
    head.addWidget(label)
    head.addStretch(1)
    column.addLayout(head)
    frame = QFrame()
    frame.setObjectName("DialogDetail")
    inner = QVBoxLayout(frame)
    inner.setContentsMargins(12, 10, 12, 10)
    inner.setSpacing(8)
    first = f"{raw.kind}: {raw.message}" if raw is not None and raw.message else (detail or "").strip()
    text = QLabel(first or tr("No exception was raised; this is the message the operation returned."))
    text.setObjectName("DialogDetailText")
    text.setWordWrap(True)
    text.setProperty("naturalHeight", True)
    text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    inner.addWidget(text)
    if raw is not None and raw.text and raw.text.strip() != first:
        trace = QPlainTextEdit(raw.text)
        trace.setObjectName("DialogTrace")
        trace.setReadOnly(True)
        trace.setFixedHeight(170)
        trace.hide()
        toggle = QPushButton(tr("Show traceback"))
        toggle.setProperty("dialogLink", True)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)

        def flip() -> None:
            trace.setVisible(not trace.isVisible())
            toggle.setText(tr("Hide traceback") if trace.isVisible() else tr("Show traceback"))
            dialog = holder.window()
            scroll = getattr(dialog, "_content_scroll", None)
            if scroll is not None:
                tighten_dialog(dialog, scroll)

        toggle.clicked.connect(flip)
        head.addWidget(toggle)
        inner.addWidget(trace)
    column.addWidget(frame)
    return holder


def _asks_for_an_action(message: object) -> bool:
    raw = find_raw_error(message)
    return raw is not None and (raw.asks_for_action or raw.kind == ActionNeeded.__name__)


class InfoDialog(QDialog):
    """Compact frameless modal used by the control center.

    The dialog deliberately avoids the native KDE title bar and the nested
    panel-within-a-window appearance.
    """

    def __init__(
        self,
        title: str,
        message: str,
        icon_name: str = "info_blue",
        parent: QWidget | None = None,
        *,
        eyebrow: str = "CONTROL CENTER",
        button_text: str = "Close",
        notice: str = "",
        tone: str = "blue",
        copy_text: str = "",
        copy_button_text: str = "Copy command",
        busy: bool = False,
    ):
        raw_title = str(title)
        raw_eyebrow = str(eyebrow)
        # The message as it came, in English, before it is explained and
        # translated: that is what a report must carry as the raw error.
        raw_message = str(message or "").strip()
        context = f"{raw_eyebrow} {raw_title}"
        umr_command = ""
        report_code = ""
        sections: tuple[tuple[str, str], ...] = ()
        #: Where it happened and what raised it, for the window and the report.
        self.origin = None
        self.raw_error = None
        self.opened_at = time.time()
        if tone == "red" and _asks_for_an_action(message):
            # Refused before anything changed until the user does one thing
            # (close Steam, prepare dependencies): say what to do, without an
            # error code that invites a problem report.
            tone, icon_name = "orange", "warning_orange"
        if tone == "red":
            self.origin = caller_origin()
            self.raw_error = find_raw_error(message)
            record_window_error(
                message, context=context, title=raw_title, origin=self.origin, raw=self.raw_error,
            )
            section = failure_section(self.origin, self.raw_error)
            # The rules read English; a page may have translated the message.
            english = self.raw_error.message if self.raw_error is not None else canonical_source(message)
            report_code = window_diagnosis(english, context=context, section=section).code
            # A broken UMR gets its reinstall command on a footer button: the
            # steps point at it, so it must not hide under the scrolled detail.
            if not copy_text:
                umr_command = umr_repair_command(message, context=context)
            explained = error_sections(message, context=context, translate=tr, section=section, classify=english)
            if explained is not None:
                sections, report_code = explained
            message = format_error_for_user(message, context=context, translate=tr, section=section, classify=english)
        title = tr(title)
        message = tr(message)
        eyebrow = tr(eyebrow)
        button_text = tr(button_text)
        notice = tr(notice) if notice else ""
        copy_button_text = tr(copy_button_text)
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        # An error carries more (identity, three answers, the raw error): wider,
        # and taller before it scrolls.
        enable_adaptive_dialog(
            self, preferred_width=640 if tone == "red" else 560, minimum_width=380, minimum_height=200,
        )
        self.setProperty("contentCap", 600 if tone == "red" else 440)

        tones = {
            "blue": COLORS["blue_soft"],
            "purple": COLORS["purple_soft"],
            "orange": COLORS["orange_soft"],
            "green": COLORS["green_soft"],
            "red": COLORS["red_soft"],
            "gray": COLORS["neutral_soft"],
        }
        soft = tones.get(tone, tones["blue"])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = dialog_card(self)
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.report_code = report_code
        # Who is speaking: the area of the app that showed the window.
        subtitle = eyebrow
        if self.origin is not None:
            section = tr(self.origin.section_name)
            subtitle = section if section.casefold() == eyebrow.casefold() else f"{section} · {eyebrow}"
        header_icon = "warning_orange" if tone == "red" else icon_name
        layout.addWidget(dialog_header(self, title, subtitle, header_icon, soft))

        content_scroll = QScrollArea()
        content_scroll.setObjectName("DialogContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        content_scroll.setMinimumHeight(60)
        content_scroll.setMaximumHeight(int(self.property("contentCap")))
        content = QWidget()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 20)
        content_layout.setSpacing(14)

        self.spinner: BusySpinner | None = None
        if tone == "red":
            # First the identity of the failure: what kind (code), which screen
            # action showed it (origin) and which function raised it.
            content_layout.addWidget(_error_identity(report_code, self.origin, self.raw_error, self.opened_at))
        if sections:
            # Then three plain answers, and the evidence last, raw.
            *answers, (_detail_heading, detail_text) = sections
            for heading, text in answers:
                content_layout.addWidget(_dialog_section(heading, text))
            content_layout.addWidget(_raw_error_block(detail_text, self.raw_error))
        else:
            body = QLabel(message)
            body.setObjectName("DialogBody")
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if busy:
                # Something is still running: the ring says so, and whoever
                # opened the dialog closes it the moment that work ends.
                busy_row = QHBoxLayout()
                busy_row.setContentsMargins(0, 0, 0, 0)
                busy_row.setSpacing(10)
                self.spinner = BusySpinner(18, "cyan" if tone != "red" else "red")
                busy_row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignVCenter)
                busy_row.addWidget(body, 1)
                content_layout.addLayout(busy_row)
                self.spinner.start()
            else:
                content_layout.addWidget(body)

        if copy_text:
            copy_frame = QFrame()
            copy_frame.setObjectName("DialogDetail")
            copy_layout = QHBoxLayout(copy_frame)
            copy_layout.setContentsMargins(12, 9, 9, 9)
            copy_layout.setSpacing(10)
            command = QLabel(str(copy_text))
            command.setObjectName("DialogDetailText")
            command.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            command.setWordWrap(True)
            copy_layout.addWidget(command, 1)
            copy_button = QPushButton(copy_button_text)
            copy_button.setObjectName("DialogSecondary")
            copy_button.setCursor(Qt.CursorShape.PointingHandCursor)

            def copy_to_clipboard() -> None:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(str(copy_text))
                copy_button.setText(tr("Copied"))

            copy_button.clicked.connect(copy_to_clipboard)
            copy_layout.addWidget(copy_button, 0, Qt.AlignmentFlag.AlignTop)
            content_layout.addWidget(copy_frame)

        if notice:
            notice_text = QLabel(notice)
            notice_text.setObjectName("DialogNoticeText")
            notice_text.setWordWrap(True)
            content_layout.addWidget(notice_text)

        content_layout.addStretch(1)
        content_scroll.setWidget(content)
        layout.addWidget(content_scroll)
        self._content_scroll = content_scroll

        footer_frame = QFrame()
        footer_frame.setObjectName("DialogFooter")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(22, 12, 22, 12)
        footer.setSpacing(8)
        if tone == "red":
            # Every error window can go straight to the report form, with its
            # code and the part of the app it came from already filled in.
            report = ReportButton(tr("Report this problem"))
            report.setObjectName("DialogReport")
            report.setIcon(icon("report_amber"))
            report.setCursor(Qt.CursorShape.PointingHandCursor)
            report.setToolTip(tr("Opens the report form with this error already filled in."))
            self.report_button = report

            def open_report() -> None:
                from bc250cc.application.system.feedback import reports as form

                from .feedback_dialog import FeedbackDialog

                FeedbackDialog(
                    self,
                    code=self.report_code,
                    # In English whatever the interface language: a page
                    # that translated its title first sent it in German.
                    summary=canonical_source(raw_title),
                    context=context,
                    # Where it failed names the part better than the page
                    # that showed it: HelixSR fails on the GPU governor page.
                    area_hint=form.area_section(getattr(self.raw_error, "site", None), self.origin),
                    reference=self.reference(),
                    where=self.where(),
                    raw=self.raw_error.text if self.raw_error is not None else canonical_source(raw_message),
                    opened_from=f"Error window: {canonical_source(raw_title)}",
                ).exec()

            report.clicked.connect(open_report)
            footer.addWidget(report)
        footer.addStretch(1)
        if sections:
            details = QPushButton(tr("Copy details"))
            details.setObjectName("DialogSecondary")
            details.setCursor(Qt.CursorShape.PointingHandCursor)

            def copy_details() -> None:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(f"{raw_title}\n\n{message}\n\n{self.evidence()}".strip() + "\n")
                details.setText(tr("Copied"))

            details.clicked.connect(copy_details)
            footer.addWidget(details)
        if umr_command:
            umr_copy = QPushButton(tr("Copy command"))
            umr_copy.setObjectName("DialogSecondary")
            umr_copy.setCursor(Qt.CursorShape.PointingHandCursor)

            def copy_umr_command() -> None:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(umr_command)
                umr_copy.setText(tr("Copied"))

            umr_copy.clicked.connect(copy_umr_command)
            footer.addWidget(umr_copy)
        primary = QPushButton(button_text)
        primary.setObjectName("DialogPrimary")
        primary.setMinimumWidth(96)
        primary.setDefault(True)
        primary.setAutoDefault(True)
        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        primary.clicked.connect(self.accept)
        footer.addWidget(primary)
        layout.addWidget(footer_frame)

        localize_widget_tree(self)
        self.fit_to_content()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self.fit_to_content()
        self._tighten()
        center_dialog(self)
        QTimer.singleShot(0, self._tighten)

    def _tighten(self) -> None:
        tighten_dialog(self, self._content_scroll)

    def reference(self) -> str:
        """``BC250-UPSCALE-001 @ GPU-0142``: the code a report quotes."""
        if self.origin is None:
            return self.report_code
        return f"{self.report_code} @ {self.origin.code}"

    def where(self) -> str:
        """The screen action and the raising function, one per line."""
        lines = []
        if self.origin is not None:
            lines.append(f"Origin: {origin_text(self.origin)} ({self.origin.section_name})")
        site = getattr(self.raw_error, "site", None)
        if site is not None:
            lines.append(f"Raised in: {origin_text(site)} ({site.section_name})")
        return "\n".join(lines)

    def evidence(self) -> str:
        """Origin, raise site and the raw exception, as plain English text."""
        lines = []
        if self.origin is not None:
            lines.append(f"Origin: {origin_text(self.origin)}")
        raw = self.raw_error
        if raw is not None:
            if raw.site is not None:
                lines.append(f"Raised in: {origin_text(raw.site)}")
            lines += ["", raw.text]
        return "\n".join(lines).strip()
