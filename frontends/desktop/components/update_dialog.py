"""The update window: what is new, then the update itself on one bar.

The dashboard says a newer version exists. This window reads that release,
shows its notes the way they were written, and on one click downloads the
package for this system, proves it against its published SHA-256 and
installs it through the terminal workflow every other privileged change
uses. The bar follows each stage — the download byte by byte, the package
manager by the phases it prints — so the terminal is there for whoever
wants it, not something to watch.
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure.self_update import (
    ReleaseInfo,
    UpdateError,
    UpdatePlan,
    download_asset,
    fetch_latest_release,
    plan_update,
)
from bc250cc.shared.version import application_version

from ..core.workflow_watch import EMBEDDED_TERMINAL_NAME
from ..i18n import localize_widget_tree, tr, tr_format
from ..theme import COLORS, application_stylesheet
from .async_tools import BackgroundExecutor
from .busy_spinner import BusySpinner
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .widgets import icon

#: Where each stage's share of the bar starts and ends.
STAGE_SPANS = {
    "download": (0.0, 0.55),
    "verify": (0.55, 0.60),
    "install": (0.60, 1.0),
}

#: What package managers print on the way through, and how far along that
#: is. Matched case-insensitively against each new line of the workflow log;
#: the bar only ever moves forward.
INSTALL_PHASES = {
    "pacman": (
        ("checking keys", 0.15), ("checking package integrity", 0.25),
        ("loading package files", 0.35), ("checking for file conflicts", 0.45),
        ("checking available disk space", 0.55), ("upgrading", 0.7), ("installing", 0.7),
        ("running post-transaction hooks", 0.9),
    ),
    "dnf": (
        ("dependencies resolved", 0.2), ("running transaction check", 0.35),
        ("transaction test succeeded", 0.45), ("running transaction", 0.55),
        ("preparing", 0.6), ("upgrading", 0.7), ("installing", 0.7), ("cleanup", 0.8),
        ("verifying", 0.9), ("complete!", 1.0),
    ),
    "apt": (
        ("reading package lists", 0.15), ("building dependency tree", 0.25),
        ("preparing to unpack", 0.45), ("unpacking", 0.6), ("setting up", 0.8),
        ("processing triggers", 0.9),
    ),
    "rpm-ostree": (
        ("checking out tree", 0.2), ("importing", 0.35), ("resolving dependencies", 0.45),
        ("downloading", 0.55), ("writing", 0.7), ("staging deployment", 0.85),
        ("systemctl reboot", 1.0),
    ),
    "aur": (
        ("cloning", 0.12), ("fetching", 0.12), ("making package", 0.3), ("starting build()", 0.45),
        ("finished making", 0.75), ("loading packages", 0.8), ("installing", 0.9), ("upgrading", 0.9),
    ),
    "install-local.sh": (
        (": ok", 0.1), ("installing", 0.4), ("helpers", 0.6), ("desktop entry", 0.85),
    ),
}


def install_progress(manager: str, lines, current: float) -> float:
    """Where the install stands (0-1), from the lines printed so far."""
    phases = INSTALL_PHASES.get(manager, ())
    reached = current
    for line in lines:
        lowered = str(line).lower()
        for marker, share in phases:
            if marker in lowered and share > reached:
                reached = share
    return reached


def _format_size(value: float) -> str:
    value = max(0.0, float(value))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def _published_date(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return moment.strftime("%Y-%m-%d")


APP_ICON = Path(__file__).resolve().parents[3] / "assets" / "icons" / "bc250-control-center-128.png"


class ProgressRail(QWidget):
    """A thin determinate bar, eased forward and never back.

    While work has started but nothing is measured yet, a short segment
    slides along the track; after that the fill says exactly how far along
    it is, with nothing decorative on top.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._value = 0.0
        self._shown = 0.0
        self._tone = "blue"
        self._phase = 0.0
        self._working = False
        self._ease = QVariantAnimation(self)
        self._ease.setDuration(360)
        self._ease.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._ease.valueChanged.connect(self._eased)
        self._slide = QTimer(self)
        self._slide.setInterval(33)
        self._slide.timeout.connect(self._advance)

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value < self._value:
            # A bar that goes backwards is a bar nobody trusts.
            return
        self._value = value
        self._ease.stop()
        self._ease.setStartValue(self._shown)
        self._ease.setEndValue(value)
        self._ease.start()

    def set_working(self, working: bool) -> None:
        self._working = bool(working)
        if self._working:
            self._slide.start()
        else:
            self._slide.stop()
        self.update()

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self.update()

    def _eased(self, value) -> None:
        self._shown = float(value)
        if self._shown > 0.01:
            self._slide.stop()
        self.update()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.02) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(self.rect())
        radius = track.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["progress_track"]))
        painter.drawRoundedRect(track, radius, radius)
        color = QColor(COLORS.get(self._tone, COLORS["blue"]))
        painter.setBrush(color)
        if self._shown > 0.01:
            fill = QRectF(track.left(), track.top(), max(track.height(), track.width() * self._shown), track.height())
            painter.drawRoundedRect(fill, radius, radius)
        elif self._working:
            width = track.width() * 0.22
            left = track.left() - width + (track.width() + width) * self._phase
            segment = QRectF(left, track.top(), width, track.height()).intersected(track)
            if segment.width() > 0:
                painter.drawRoundedRect(segment, radius, radius)


class _StepDot(QWidget):
    """The mark of one step: an outline to come, a ring while it runs,
    filled with a tick when done, red with a cross when it failed."""

    SIZE = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.state = "pending"
        self.spinner = BusySpinner(self.SIZE, "blue", self)
        self.spinner.move(0, 0)

    def set_state(self, state: str) -> None:
        self.state = state
        self.spinner.set_running(state == "running")
        self.update()

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        if self.state == "running":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.state in {"pending", "skipped"}:
            painter.setPen(QPen(QColor(COLORS["border_strong"]), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(box)
            if self.state == "skipped":
                painter.drawLine(QPointF(box.left() + 4, box.center().y()), QPointF(box.right() - 4, box.center().y()))
            return
        fill = QColor(COLORS["red"] if self.state == "failed" else COLORS["blue"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(box)
        pen = QPen(QColor(COLORS["on_blue"]), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        c = box.center()
        if self.state == "failed":
            painter.drawLine(QPointF(c.x() - 3, c.y() - 3), QPointF(c.x() + 3, c.y() + 3))
            painter.drawLine(QPointF(c.x() + 3, c.y() - 3), QPointF(c.x() - 3, c.y() + 3))
        else:
            tick = QPainterPath(QPointF(c.x() - 3.4, c.y() + 0.2))
            tick.lineTo(c.x() - 0.9, c.y() + 2.6)
            tick.lineTo(c.x() + 3.6, c.y() - 2.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)


class _StageRow(QWidget):
    """One step of the update in the stepper: its mark and its name.

    What the step is doing right now goes in the window's status line; the
    detail is kept here for it and as the step's tooltip.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = "pending"
        self.source_title = title
        self.on_change = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        self.dot = _StepDot(self)
        row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel(tr(title))
        self.title.setProperty("updateStepTitle", True)
        row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        self.detail = QLabel("")
        self.detail.setProperty("i18nLiteral", True)
        self.detail.hide()
        self.set_state("pending")

    def set_state(self, state: str, detail: str | None = None) -> None:
        self.state = state
        self.dot.set_state(state)
        self.title.setProperty("state", state)
        style = self.title.style()
        if style is not None:
            style.unpolish(self.title)
            style.polish(self.title)
        if detail is not None:
            self.detail.setText(detail)
            self.setToolTip(detail)
        if self.on_change is not None:
            self.on_change()


def release_notes_html(markdown: str) -> str:
    """The release notes as HTML with the few elements they use.

    Qt's own Markdown import sized a "## Highlights" heading like a page
    title. Converting the handful of constructs release notes contain --
    headings, lists, paragraphs, bold, code and links -- lets the window set
    its own, quieter type.
    """

    def inline(text: str) -> str:
        text = html.escape(text, quote=False)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)

    out: list[str] = []
    paragraph: list[str] = []
    list_tag = ""

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = ""

    for raw in str(markdown or "").splitlines():
        line = raw.strip()
        heading = re.match(r"^#{1,6}\s+(.*)$", line)
        bullet = re.match(r"^[-*+]\s+(.*)$", line)
        numbered = re.match(r"^\d+[.)]\s+(.*)$", line)
        if not line:
            flush_paragraph()
            continue
        if heading:
            flush_paragraph()
            close_list()
            # A bold paragraph at text size: Qt sizes <h3> by its own
            # relative scale and ignores a pixel size given for it.
            top = 0 if not out else 12
            out.append(
                f'<p style="font-weight:700; margin-top:{top}px; margin-bottom:6px;">'
                f"{inline(heading.group(1))}</p>"
            )
        elif bullet or numbered:
            flush_paragraph()
            tag = "ul" if bullet else "ol"
            if list_tag != tag:
                close_list()
                out.append(f"<{tag}>")
                list_tag = tag
            out.append(f"<li>{inline((bullet or numbered).group(1))}</li>")
        elif list_tag and raw.startswith((" ", "\t")) and out and out[-1].endswith("</li>"):
            out[-1] = out[-1][: -len("</li>")] + " " + inline(line) + "</li>"
        else:
            close_list()
            paragraph.append(line)
    flush_paragraph()
    close_list()
    return "\n".join(out)


def _notes_stylesheet() -> str:
    c = COLORS
    return (
        f"p {{ color: {c['text']}; margin-top: 0px; margin-bottom: 8px; line-height: 130%; }}"
        f"ul, ol {{ margin-top: 0px; margin-bottom: 6px; margin-left: 0px; -qt-list-indent: 1; }}"
        f"li {{ color: {c['text']}; margin-bottom: 3px; line-height: 130%; }}"
        f"code {{ font-family: monospace; color: {c['text']}; background-color: {c['panel_raised']}; }}"
        f"a {{ color: {c['blue']}; text-decoration: none; }}"
    )


class _DownloadThread(QThread):
    progressed = pyqtSignal(int, int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, asset, parent=None) -> None:
        super().__init__(parent)
        self._asset = asset
        self._cancel = False
        self._last = 0.0

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        def progress(done: int, total: int) -> None:
            now = time.monotonic()
            if now - self._last >= 0.08 or (total and done >= total):
                self._last = now
                self.progressed.emit(done, total)

        try:
            path = download_asset(self._asset, progress=progress, cancelled=lambda: self._cancel)
        except UpdateError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:  # noqa: BLE001 - reported in the dialog
            self.failed.emit(str(error) or error.__class__.__name__)
            return
        self.completed.emit(str(path))


class UpdateDialog(QDialog):
    """Read the release, then update to it, in one window."""

    restart_requested = pyqtSignal()

    def __init__(self, window, *, installed: str | None = None, source=None, os_family: str = "") -> None:
        super().__init__(window)
        self._window = window
        self._installed = installed or application_version()
        self._source = source
        self._os_family = os_family
        self._release: ReleaseInfo | None = None
        self._plan: UpdatePlan | None = None
        self._download: _DownloadThread | None = None
        self._downloaded: Path | None = None
        self._launch = None
        self._install_share = 0.0
        self._install_started = 0.0
        self._log_offset = 0
        self._background = BackgroundExecutor(self)

        self.setObjectName("InfoDialog")
        self.setWindowTitle(tr("Update BC250 Control Center"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Not modal: the terminal under it must stay usable for the password.
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setStyleSheet(application_stylesheet() + _update_stylesheet())
        enable_adaptive_dialog(self, preferred_width=720, preferred_height=640, minimum_width=460, minimum_height=420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame()
        card.setObjectName("ControlDialogCard")
        card.setProperty("updateCard", True)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # --- The release: which version, how it relates to this one.
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(14)
        self.logo = QLabel()
        self.logo.setFixedSize(52, 52)
        logo = QPixmap(str(APP_ICON))
        if not logo.isNull():
            ratio = self.devicePixelRatioF()
            logo = logo.scaled(round(52 * ratio), round(52 * ratio), Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            logo.setDevicePixelRatio(ratio)
            self.logo.setPixmap(logo)
        header.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        self.title = QLabel("BC250 Control Center")
        self.title.setProperty("updateTitle", True)
        self.title.setProperty("i18nLiteral", True)
        self.title.setWordWrap(True)
        # One plain sentence says where things stand; it changes as the
        # update moves on.
        self.eyebrow = QLabel(tr("Reading the latest release…"))
        self.eyebrow.setProperty("updateLead", True)
        self.eyebrow.setProperty("i18nLiteral", True)
        self.eyebrow.setWordWrap(True)
        self.versions = QLabel("")
        self.versions.setProperty("updateVersions", True)
        self.versions.setProperty("i18nLiteral", True)
        heading.addWidget(self.title)
        heading.addWidget(self.eyebrow)
        heading.addWidget(self.versions)
        header.addLayout(heading, 1)
        self.close_button = QPushButton()
        self.close_button.setObjectName("DialogClose")
        self.close_button.setIcon(icon("close_gray"))
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip(tr("Close"))
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        section = QLabel(tr("What's new"))
        section.setProperty("updateSection", True)
        layout.addWidget(section)
        self.notes = QTextBrowser()
        self.notes.setObjectName("updateNotes")
        self.notes.setOpenExternalLinks(True)
        self.notes.setOpenLinks(True)
        self.notes.document().setDefaultStyleSheet(_notes_stylesheet())
        self.notes.document().setDocumentMargin(2)
        layout.addWidget(self.notes, 1)
        self.package_line = QLabel("")
        self.package_line.setProperty("updatePackage", True)
        self.package_line.setProperty("i18nLiteral", True)
        self.package_line.setWordWrap(True)
        layout.addWidget(self.package_line)
        card_layout.addWidget(body, 1)

        # --- The footer: the actions, and while updating, the progress.
        footer_frame = QFrame()
        footer_frame.setObjectName("updateFooter")
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(24, 14, 24, 16)
        footer_layout.setSpacing(12)

        self.progress_block = QWidget()
        progress_layout = QVBoxLayout(self.progress_block)
        progress_layout.setContentsMargins(0, 0, 0, 2)
        progress_layout.setSpacing(8)
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self.status_line = QLabel("")
        self.status_line.setProperty("updateStatus", True)
        self.status_line.setProperty("i18nLiteral", True)
        self.status_line.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        status_row.addWidget(self.status_line, 1)
        self.percent = QLabel("0 %")
        self.percent.setProperty("updatePercent", True)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.percent)
        progress_layout.addLayout(status_row)
        self.rail = ProgressRail()
        progress_layout.addWidget(self.rail)
        steps = QHBoxLayout()
        steps.setContentsMargins(0, 4, 0, 0)
        steps.setSpacing(10)
        self.stages = {
            "download": _StageRow("Download"),
            "verify": _StageRow("Verify"),
            "install": _StageRow("Install"),
            "finish": _StageRow("Finish"),
        }
        self._step_lines: list[QFrame] = []
        for index, stage in enumerate(self.stages.values()):
            if index:
                line = QFrame()
                line.setProperty("updateStepLine", True)
                line.setFixedHeight(2)
                line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                steps.addWidget(line, 1, Qt.AlignmentFlag.AlignVCenter)
                self._step_lines.append(line)
            stage.on_change = self._sync_status
            steps.addWidget(stage, 0)
        progress_layout.addLayout(steps)
        self.progress_block.hide()
        footer_layout.addWidget(self.progress_block)

        self.notice = QLabel("")
        self.notice.setProperty("updateNotice", True)
        self.notice.setProperty("i18nLiteral", True)
        self.notice.setWordWrap(True)
        self.notice.hide()
        footer_layout.addWidget(self.notice)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.release_button = QPushButton(tr("Release page") + "  ↗")
        self.release_button.setProperty("updateLink", True)
        self.release_button.setProperty("i18nLiteral", True)
        self.release_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.release_button.clicked.connect(self._open_release_page)
        footer.addWidget(self.release_button)
        self.terminal_button = QPushButton(tr("Show terminal"))
        self.terminal_button.setProperty("updateSecondary", True)
        self.terminal_button.clicked.connect(self._show_terminal)
        self.terminal_button.hide()
        footer.addWidget(self.terminal_button)
        footer.addStretch(1)
        self.later_button = QPushButton(tr("Later"))
        self.later_button.setProperty("updateSecondary", True)
        self.later_button.setProperty("gamepadCancel", True)
        self.later_button.clicked.connect(self.close)
        footer.addWidget(self.later_button)
        self.primary = QPushButton(tr("Update now"))
        self.primary.setObjectName("DialogPrimary")
        self.primary.setProperty("updatePrimary", True)
        self.primary.setDefault(True)
        self.primary.setEnabled(False)
        self.primary.clicked.connect(self._primary_clicked)
        footer.addWidget(self.primary)
        footer_layout.addLayout(footer)
        card_layout.addWidget(footer_frame)

        self._poll = QTimer(self)
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._follow_install)
        watch = getattr(window, "workflow_watch", None)
        if watch is not None:
            watch.finished.connect(self._workflow_finished)

        localize_widget_tree(self)
        self._background.start("update-release", fetch_latest_release, self._release_ready, self._release_failed)

    # ---------------------------------------------------------------- phase 1

    def _release_ready(self, release: ReleaseInfo) -> None:
        self._release = release
        self.title.setText(f"BC250 Control Center {release.version}")
        published = _published_date(release.published_at)
        versions = tr_format("You have {installed}", installed=self._installed)
        if published:
            versions = f"{tr_format('Published {date}', date=published)} · {versions}"
        self.versions.setText(versions)
        self.notes.setHtml(release_notes_html(release.notes) or f"<p>{html.escape(tr('This release has no notes.'))}</p>")
        self.eyebrow.setText(tr("A new version is available."))
        try:
            self._plan = plan_update(release, self._source, os_family=self._os_family)
        except Exception as error:  # noqa: BLE001 - shown instead of a plan
            self._plan = UpdatePlan("manual", reason=str(error))
        plan = self._plan
        if plan.kind == "manual":
            self.package_line.setText(tr(plan.reason))
            self.primary.setText(tr("Open the release page"))
            # The primary button already goes there.
            self.release_button.hide()
        elif plan.kind == "aur":
            self.package_line.setText(tr_format("{helper} rebuilds the AUR package in the terminal.", helper=plan.helper))
        else:
            asset = plan.asset
            line = tr_format(
                "Package for this system: {name} · {size} · SHA-256 checked",
                name=asset.name, size=_format_size(asset.size),
            )
            if plan.reboot_required:
                line += " · " + tr("a restart of the computer finishes it")
            self.package_line.setText(line)
        if release.version.strip() == str(self._installed).strip():
            self.eyebrow.setText(tr("You have the latest version."))
            self.primary.setText(tr("Reinstall") if plan.kind != "manual" else tr("Open the release page"))
        self.primary.setEnabled(True)

    def _release_failed(self, message: str) -> None:
        self.title.setText(tr("The latest release could not be read"))
        self.eyebrow.setText("")
        self.notes.setPlainText(message)
        self.primary.setText(tr("Open the release page"))
        self.release_button.hide()
        self._plan = UpdatePlan("manual", reason=message)
        self.primary.setEnabled(True)

    def _primary_clicked(self) -> None:
        state = getattr(self, "_state", "notes")
        if state == "done":
            self.restart_requested.emit()
            return
        if state == "failed":
            self._show_terminal()
            return
        plan = self._plan
        if plan is None or plan.kind == "manual":
            self._open_release_page()
            return
        self._start_update()

    # ---------------------------------------------------------------- phase 2

    def _start_update(self) -> None:
        self._state = "running"
        self.progress_block.show()
        self.package_line.hide()
        self.eyebrow.setText(tr_format("Updating to {version}", version=self._release.version))
        self.primary.setEnabled(False)
        self.primary.setText(tr("Updating…"))
        self.release_button.hide()
        self.later_button.setText(tr("Cancel"))
        self.rail.set_working(True)
        plan = self._plan
        if plan.downloads:
            self.stages["download"].set_state("running", _format_size(0))
            thread = _DownloadThread(plan.asset, self)
            thread.progressed.connect(self._downloading)
            thread.completed.connect(self._downloaded_ready)
            thread.failed.connect(lambda message: self._fail("download", message))
            self._download = thread
            self._download_started = time.monotonic()
            thread.start()
        else:
            self.stages["download"].set_state("skipped", tr("Built from source by the AUR helper"))
            self.stages["verify"].set_state("skipped", tr("The AUR helper checks the sources"))
            self._set_share("verify", 1.0)
            self._install(None)

    def _sync_status(self) -> None:
        """The status line names the step at work and what it is doing."""
        stages = list(getattr(self, "stages", {}).values())
        current = (
            next((stage for stage in stages if stage.state == "failed"), None)
            or next((stage for stage in stages if stage.state == "running"), None)
            or next((stage for stage in reversed(stages) if stage.state == "done"), None)
        )
        for line, stage in zip(getattr(self, "_step_lines", ()), stages):
            finished = stage.state in {"done", "skipped"}
            if bool(line.property("done")) != finished:
                line.setProperty("done", finished)
                line.style().unpolish(line)
                line.style().polish(line)
        if current is None:
            self.status_line.setText("")
            return
        detail = current.detail.text().strip()
        text = f"{tr(current.source_title)} · {detail}" if detail else tr(current.source_title)
        metrics = self.status_line.fontMetrics()
        width = max(120, self.status_line.width() or 480)
        self.status_line.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, width))
        self.status_line.setToolTip(text)
        self.status_line.setProperty("state", current.state)
        self.status_line.style().unpolish(self.status_line)
        self.status_line.style().polish(self.status_line)

    def _set_share(self, stage: str, share: float) -> None:
        start, end = STAGE_SPANS[stage]
        value = start + (end - start) * max(0.0, min(1.0, share))
        self.rail.set_value(value)
        self.percent.setText(f"{round(self.rail.value * 100)} %")

    def _downloading(self, done: int, total: int) -> None:
        elapsed = max(0.001, time.monotonic() - getattr(self, "_download_started", time.monotonic()))
        speed = done / elapsed
        detail = f"{_format_size(done)} / {_format_size(total)} · {_format_size(speed)}/s" if total else _format_size(done)
        self.stages["download"].set_state("running", detail)
        self._set_share("download", done / total if total else 0.0)

    def _downloaded_ready(self, path: str) -> None:
        self._downloaded = Path(path)
        size = self._downloaded.stat().st_size if self._downloaded.exists() else 0
        self.stages["download"].set_state("done", _format_size(size))
        self._set_share("download", 1.0)
        # download_asset refuses anything whose SHA-256 differs.
        self.stages["verify"].set_state("done", tr_format("SHA-256 matches {digest}…", digest=self._plan.asset.sha256[:16]))
        self._set_share("verify", 1.0)
        self._install(self._downloaded)

    def _install(self, package: Path | None) -> None:
        controller = getattr(self._window, "controller", None)
        installer = getattr(controller, "instalar_actualizacion", None)
        if not callable(installer):
            self._fail("install", tr("This backend cannot install updates."))
            return
        self.stages["install"].set_state("running", tr("Starting the installer…"))
        self.later_button.setText(tr("Hide"))
        self._install_started = time.monotonic()

        def run():
            return installer(self._plan, str(package) if package else None)

        self._background.start("update-install", run, self._install_launched, lambda message: self._fail("install", message))

    def _install_launched(self, result) -> None:
        self._launch = result
        embedded = getattr(result, "terminal", "") == EMBEDDED_TERMINAL_NAME
        self.terminal_button.setVisible(embedded)
        self.stages["install"].set_state("running", tr("Installing…"))
        self._poll.start()

    def _follow_install(self) -> None:
        """New log lines move the bar; a password prompt brings the terminal up."""
        launch = self._launch
        if launch is None:
            return
        lines = self._new_log_lines(getattr(launch, "log_file", ""))
        manager = "aur" if self._plan.kind == "aur" else self._plan.manager
        share = install_progress(manager, lines, self._install_share)
        # Between the phases a package manager prints, the bar still creeps a
        # little, never past the next phase it could reach.
        elapsed = time.monotonic() - self._install_started
        share = max(share, min(self._install_share + 0.004, 0.08 + 0.5 * (1 - 1 / (1 + elapsed / 60))))
        self._install_share = min(0.97, share)
        self._set_share("install", self._install_share)
        last = next((line.strip() for line in reversed(lines) if line.strip()), "")
        if last:
            self.stages["install"].set_state("running", last[:160])
        if self._password_requested():
            self.notice.setText(tr("The installer is asking for your administrator password: type it in the terminal below."))
            self.notice.show()
            self._show_terminal()
        else:
            self.notice.hide()

    def _new_log_lines(self, path: str) -> list[str]:
        if not path:
            return []
        try:
            with open(path, "rb") as handle:
                handle.seek(self._log_offset)
                chunk = handle.read(256 * 1024)
                self._log_offset += len(chunk)
        except OSError:
            return []
        text = chunk.decode("utf-8", "replace")
        # Progress redraws with carriage returns; each redraw is a line here.
        return [part for part in text.replace("\r", "\n").split("\n")]

    def _password_requested(self) -> bool:
        console = getattr(self._window, "console", None)
        if console is None or self._launch is None:
            return False
        for tab in getattr(console, "_tabs", ()):
            if getattr(tab, "log_file", "") == getattr(self._launch, "log_file", None):
                return bool(tab.running and tab.input_is_masked())
        return False

    def _workflow_finished(self, result, code: int) -> None:
        if self._launch is None or getattr(result, "status_file", None) != getattr(self._launch, "status_file", None):
            return
        self._poll.stop()
        self._follow_install_tail()
        if code != 0:
            self._fail("install", tr_format("The installer ended with code {code}. The terminal shows why.", code=code))
            return
        self.rail.set_working(False)
        self.rail.set_tone("green")
        self._set_share("install", 1.0)
        self.stages["install"].set_state("done", tr("Installed"))
        self._state = "done"
        self.notice.hide()
        self.eyebrow.setText(tr("The update is installed."))
        if self._plan.reboot_required:
            self.stages["finish"].set_state("done", tr("Restart the computer to boot into the new version."))
            self.primary.hide()
            self.later_button.setText(tr("Close"))
        else:
            self.stages["finish"].set_state("done", tr_format("Restart BC250 Control Center to use {version}.", version=self._release.version))
            self.primary.setText(tr("Restart BC250 Control Center"))
            self.primary.setEnabled(True)
            self.later_button.setText(tr("Later"))

    def _follow_install_tail(self) -> None:
        if self._launch is not None:
            self._new_log_lines(getattr(self._launch, "log_file", ""))

    def _fail(self, stage: str, message: str) -> None:
        self._state = "failed"
        self._poll.stop()
        self.rail.set_working(False)
        self.rail.set_tone("red")
        self.stages[stage].set_state("failed", tr(message))
        self.eyebrow.setText(tr("The update did not finish."))
        self.release_button.show()
        self.later_button.setText(tr("Close"))
        embedded = getattr(self._launch, "terminal", "") == EMBEDDED_TERMINAL_NAME
        self.primary.setVisible(embedded)
        self.primary.setText(tr("Show terminal"))
        self.primary.setEnabled(embedded)

    # ------------------------------------------------------------------ misc

    def _show_terminal(self) -> None:
        console = getattr(self._window, "console", None)
        if console is not None and not console.shown:
            console.slide_in()

    def _open_release_page(self) -> None:
        from ..core.external_links import open_external_url

        url = self._release.page_url if self._release is not None else ""
        from bc250cc.infrastructure.release_check import RELEASES_PAGE_URL

        open_external_url(url or RELEASES_PAGE_URL)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._download is not None and self._download.isRunning():
            self._download.cancel()
            self._download.wait(3000)
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        center_dialog(self)


def _update_stylesheet() -> str:
    c = COLORS
    return f"""
    QFrame#ControlDialogCard[updateCard='true'] {{ border-radius: 12px; }}
    QLabel[updateTitle='true'] {{ color: {c['text']}; font-size: 17px; font-weight: 760; }}
    QLabel[updateLead='true'] {{ color: {c['text']}; font-size: 13px; font-weight: 560; }}
    QLabel[updateVersions='true'] {{ color: {c['muted']}; font-size: 12px; }}
    QLabel[updateSection='true'] {{ color: {c['muted']}; font-size: 12px; font-weight: 700; }}
    QTextBrowser#updateNotes {{
        background: {c['panel_alt']}; color: {c['text']};
        border: 1px solid {c['border_soft']}; border-radius: 8px;
        padding: 10px 14px; font-size: 13px;
    }}
    QLabel[updatePackage='true'] {{ color: {c['muted']}; font-size: 11px; }}
    QFrame#updateFooter {{
        background: {c['panel_alt']}; border: none; border-top: 1px solid {c['border_soft']};
        border-bottom-left-radius: 11px; border-bottom-right-radius: 11px;
    }}
    QLabel[updateStatus='true'] {{ color: {c['text']}; font-size: 12px; font-weight: 600; }}
    QLabel[updateStatus='true'][state='failed'] {{ color: {c['red']}; }}
    QLabel[updatePercent='true'] {{ color: {c['muted']}; font-size: 12px; font-weight: 700; }}
    QLabel[updateStepTitle='true'] {{ color: {c['muted']}; font-size: 11px; font-weight: 650; }}
    QLabel[updateStepTitle='true'][state='running'],
    QLabel[updateStepTitle='true'][state='done'] {{ color: {c['text']}; }}
    QLabel[updateStepTitle='true'][state='failed'] {{ color: {c['red']}; }}
    QFrame[updateStepLine='true'] {{ background: {c['border']}; border: none; border-radius: 1px; }}
    QFrame[updateStepLine='true'][done='true'] {{ background: {c['blue']}; }}
    QLabel[updateNotice='true'] {{
        color: {c['orange']}; background: {c['orange_soft']};
        border: 1px solid {c['orange_border']}; border-radius: 6px; padding: 8px 10px;
        font-size: 12px; font-weight: 600;
    }}
    QPushButton[updateLink='true'] {{
        background: transparent; border: none; padding: 6px 2px; color: {c['blue']};
        font-size: 12px; font-weight: 650; text-align: left;
    }}
    QPushButton[updateLink='true']:hover {{ color: {c['blue_hover']}; text-decoration: underline; }}
    QPushButton[updateSecondary='true'] {{
        background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
        border-radius: 6px; padding: 7px 14px; font-size: 12px; font-weight: 650;
    }}
    QPushButton[updateSecondary='true']:hover {{ background: {c['control_hover']}; }}
    QPushButton#DialogPrimary[updatePrimary='true'] {{
        border-radius: 6px; padding: 7px 16px; font-size: 12px; font-weight: 700;
    }}
    QPushButton#DialogPrimary[updatePrimary='true']:disabled {{
        background: {c['control_hover']}; border-color: {c['border']}; color: {c['muted']};
    }}
    """
