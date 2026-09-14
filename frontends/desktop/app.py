from __future__ import annotations

import logging
import os
import shlex
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, QThreadPool, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .components.async_tools import BackgroundExecutor, pending_background_tasks
from .components.sidebar import Sidebar
from .components.widgets import InfoDialog
from .console import ConsoleHost, ConsolePanel
from .core.alerts import SmartAlertMonitor
from .core.gamepad import GamepadNavigationController
from .core.preferences import UiPreferences
from .core.state import state_cache_for
from .i18n import (
    localize_top_levels,
    localize_widget_tree,
    normalize_language,
    set_language,
    tr,
    tr_format,
)
from .theme import application_stylesheet, configure_theme

if TYPE_CHECKING:
    from .pages.settings import SettingsDialog


logger = logging.getLogger(__name__)


def _ui_perf_enabled() -> bool:
    return str(os.environ.get("BC250_UI_PERF", "")).strip().lower() in {"1", "true", "yes", "on"}


def _is_steamos_gamemode_session() -> bool:
    markers = {
        str(os.environ.get("XDG_CURRENT_DESKTOP", "")).strip().lower(),
        str(os.environ.get("XDG_SESSION_DESKTOP", "")).strip().lower(),
        str(os.environ.get("DESKTOP_SESSION", "")).strip().lower(),
    }
    if any("gamescope" in value for value in markers if value):
        return True
    if str(os.environ.get("GAMESCOPE_WAYLAND_DISPLAY", "")).strip():
        return True
    if str(os.environ.get("SteamGamepadUI", "")).strip() == "1":
        return True
    if str(os.environ.get("SteamTenfoot", "")).strip() == "1":
        return True
    return False


class ControlCenterWindow(QMainWindow):
    """Definitive BC250 interface backed by the application controller."""

    # How long a close request will wait for work it did not start itself, and
    # how long the final drain blocks once the window has decided to go.  Both
    # are generous next to a normal refresh (tens of milliseconds) and short
    # enough that a wedged backend cannot hold the window open.
    BACKGROUND_WAIT_MS = 4000
    BACKGROUND_DRAIN_MS = 3000

    def __init__(self, controller, *, settings_service=None, activity_service=None):
        super().__init__()
        self.controller = controller
        self.settings_service = settings_service
        self.activity_service = activity_service
        self.preferences = UiPreferences()
        self.settings = self.preferences.settings
        migration = self.preferences.initialize()
        self._background = BackgroundExecutor(self)
        self._state_cache = state_cache_for(
            controller,
            activity_service=activity_service,
            settings_service=settings_service,
        )
        self._gamemode_session = _is_steamos_gamemode_session()
        self._missing_backend_language = migration.missing_backend_language
        self._missing_backend_appearance = migration.missing_backend_appearance
        self._apply_language(str(self.settings.value("settings/language", "auto")), persist=False)
        self._apply_appearance(
            str(self.settings.value("settings/appearance", "system")),
            str(self.settings.value("settings/accent", "blue")),
            str(self.settings.value("settings/density", "comfortable")),
            persist=False,
        )

        self.setWindowTitle("BC250 Control Center")
        app_icon = Path(__file__).resolve().parents[2] / "assets" / "icons" / "bc250-control-center.png"
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))
        self.resize(1460, 880)
        # 720×520 is the smallest useful shell. Below this point the pages still
        # remain intact through vertical scrolling, while the desktop window
        # manager retains a realistic resize target.
        self.setMinimumSize(720, 520)
        if self._gamemode_session:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        root = QWidget()
        root.setObjectName("ApplicationRoot")
        layout = QHBoxLayout(root)
        self.root_layout = layout
        if self._gamemode_session:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(10)
        else:
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(16)

        # The shell stacks the pages over the console, so the console spans the
        # full width the way a docked terminal does and the pages give up only
        # the height it actually occupies.
        shell = QWidget()
        shell.setObjectName("ApplicationShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(root, 1)
        self.setCentralWidget(shell)

        # Every page uses an 8 px top inset before its first visible card.
        # The sidebar and page cards share the same top alignment.
        self.sidebar_host = QWidget()
        self.sidebar_host.setObjectName("SidebarHost")
        self.sidebar_host.setMinimumWidth(0)
        self.sidebar_host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        sidebar_layout = QVBoxLayout(self.sidebar_host)
        sidebar_layout.setContentsMargins(0, 0 if self._gamemode_session else 8, 0, 0)
        sidebar_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigation_requested.connect(self.navigate)
        collapsed = self.preferences.bool_value("sidebar_collapsed", False)
        self._sidebar_user_collapsed = collapsed
        self._sidebar_auto_collapsed = False
        self._sidebar_change_is_automatic = False
        self.sidebar.set_collapsed(collapsed)
        self.sidebar.collapsed_changed.connect(self._save_sidebar_state)
        sidebar_layout.addWidget(self.sidebar)
        layout.addWidget(self.sidebar_host)

        # Import modules only after the selected palette is configured. Their
        # existing functional widgets therefore keep the correct initial colors.
        from .pages.compute_units import ComputeUnitsPage
        from .pages.cpu_smu import CpuSmuPage
        from .pages.dashboard import DashboardPage
        from .pages.fans import FansPage
        from .pages.gpu_governor import GpuGovernorPage
        from .pages.performance import PerformancePage
        from .pages.processes import ProcessesPage

        self.stack = QStackedWidget()
        self.stack.setMinimumSize(0, 0)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.dashboard = DashboardPage(controller)
        self.cpu_page = CpuSmuPage(
            controller,
            activity_service=activity_service,
            settings_service=settings_service,
        )
        self.gpu_page = GpuGovernorPage(controller, settings_service=settings_service)
        self.cu_page = ComputeUnitsPage(controller, activity_service=activity_service)
        self.fans_page = FansPage(
            controller,
            activity_service=activity_service,
            settings_service=settings_service,
        )
        self.fans_page.settings_requested.connect(self._open_settings_dialog)
        self.processes_page = ProcessesPage(
            controller,
            activity_service=activity_service,
        )
        self.performance_page = PerformancePage(controller)
        self.settings_dialog: SettingsDialog | None = None
        self.current_page_key = "dashboard"
        self._gamepad_navigation_history: list[str] = []
        self._gamepad_suppress_history = False
        self.pages = {
            "dashboard": self.dashboard,
            "cpu": self.cpu_page,
            "gpu": self.gpu_page,
            "cu": self.cu_page,
            "performance": self.performance_page,
            "fans": self.fans_page,
            "processes": self.processes_page,
        }
        self.dashboard.module_requested.connect(self.navigate)
        self.dashboard.action_requested.connect(self._dashboard_action)
        self.dashboard.dependency_action_requested.connect(
            self._dashboard_dependency_action
        )
        self.dashboard.driver_support_requested.connect(
            self._dashboard_driver_support
        )
        for page in self.pages.values():
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self._build_console(shell_layout)

        self.gamepad = GamepadNavigationController(self)
        self._follow_controller_into_the_console()
        self.alert_monitor = SmartAlertMonitor(
            controller,
            self.settings,
            activity_service=activity_service,
            parent=self,
        )
        self.alert_monitor.alert_triggered.connect(self._show_safety_alert)
        self._gamepad_navigation_enabled = self.preferences.bool_value("settings/gamepad_navigation", True)
        keypad_enabled = self.preferences.bool_value("settings/gamepad_onscreen_keypad", True)
        self.gamepad.set_onscreen_keypad_enabled(keypad_enabled)
        self.gamepad.set_onscreen_keypad_auto_show(keypad_enabled)
        self._set_detailed_diagnostics(self.preferences.bool_value("settings/detailed_diagnostics", False))
        self._retranslate_interface()
        self._restore_start_page()
        self._migrate_backend_preferences_async()
        self._set_gamepad_navigation_enabled(self._gamepad_navigation_enabled)

    def _build_console(self, shell_layout) -> None:
        """Attach the in-application terminal and offer it to the repositories.

        Every workflow keeps writing the same log and status files, so nothing
        that waits on a terminal result changes. When the console declines a
        workflow — because one is already running, or because the user turned
        it off — the repositories fall back to the desktop terminal emulators
        exactly as before.
        """
        self.console: ConsolePanel | None = None
        self.console_host: ConsoleHost | None = None
        try:
            panel = ConsolePanel(self)
        except Exception:
            logger.exception("The embedded console could not be created")
            return
        shell_layout.addWidget(panel)
        # Game Mode runs on a handheld panel where 280 px is a third of the
        # screen; the console still has to leave the page it covers usable.
        default_height = 200 if self._gamemode_session else 280
        panel.set_panel_height(self.preferences.int_value("console/height", default_height))
        panel.set_auto_hide(self.preferences.bool_value("settings/console_auto_hide", True))
        panel.external_terminal_requested.connect(self._open_workflow_in_terminal)
        panel.visibility_changed.connect(self._console_visibility_changed)
        self.console = panel
        host = ConsoleHost(panel, self)
        host.set_enabled(self.preferences.bool_value("settings/embedded_terminal", True))
        host.install()
        self.console_host = host

    def _follow_controller_into_the_console(self) -> None:
        """Tell the console whether a controller is driving.

        The console is built before the navigation controller, because the
        pages it serves are built before both. So the connection is made here,
        after the controller exists, and primed with the current answer — a
        controller that was already plugged in when the window opened emits
        nothing to announce itself.
        """
        console = getattr(self, "console", None)
        if console is None:
            return
        self.gamepad.connection_changed.connect(
            lambda connected, _name: console.set_gamepad_present(connected)
        )
        console.set_gamepad_present(self.gamepad.connected)

    def _console_visibility_changed(self, visible: bool) -> None:
        if not visible and self.console is not None:
            self.preferences.settings.setValue("console/height", self.console.panel_height())

    def set_embedded_terminal_enabled(self, enabled: bool) -> None:
        """Live switch between the docked console and a terminal window."""
        self.preferences.settings.setValue("settings/embedded_terminal", bool(enabled))
        if self.console_host is not None:
            self.console_host.set_enabled(bool(enabled))
        if not enabled and self.console is not None and not self.console.busy:
            self.console.slide_out()

    def set_console_auto_hide(self, enabled: bool) -> None:
        self.preferences.settings.setValue("settings/console_auto_hide", bool(enabled))
        if self.console is not None:
            self.console.set_auto_hide(bool(enabled))

    def _open_workflow_in_terminal(self, launch_path: str) -> None:
        """Re-open the running workflow's script in a real terminal window."""
        from bc250cc.infrastructure.terminal_plan import terminal_candidates
        from bc250cc.infrastructure.terminal_repository import TerminalRepository

        if not launch_path:
            return
        candidates = terminal_candidates(
            f"exec bash {shlex.quote(launch_path)}",
            "BC250 Control Center",
            terminal_env=os.environ.get("TERMINAL", ""),
            home=Path.home(),
        )
        terminal, _pid, _errors = TerminalRepository._launch_terminal_candidates(candidates)
        if not terminal:
            self._show_safety_alert(
                tr("Open terminal"),
                tr_format(
                    "No graphical terminal was found. Run it manually with: bash {path}",
                    path=launch_path,
                ),
                "warning",
            )

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Synchronize the active page after the window manager places it.

        KDE and some other Linux window managers can apply a restored or
        maximized geometry immediately after ``show()``.  Child scroll-area
        viewports settle one layout pass later, so perform one immediate and
        one short delayed synchronization.  The layout already starts in its
        desktop form, therefore these passes do not introduce a visible jump;
        they only prevent a stale compact mode from surviving first paint.
        """

        super().showEvent(event)
        if self._gamemode_session:
            QTimer.singleShot(0, self._apply_gamemode_window_mode)
        QTimer.singleShot(0, self._sync_current_page_layout)
        QTimer.singleShot(80, self._sync_current_page_layout)

    def _apply_gamemode_window_mode(self) -> None:
        if not self._gamemode_session:
            return
        screen = self.screen()
        if screen is None and self.windowHandle() is not None:
            screen = self.windowHandle().screen()
        if screen is not None:
            geometry = screen.availableGeometry()
            self.setGeometry(geometry)
        if not self.isFullScreen():
            self.showFullScreen()

    def _sync_current_page_layout(self) -> None:
        if not hasattr(self, "stack"):
            return
        page = self.stack.currentWidget()
        if page is None:
            return
        reflow = getattr(page, "_reflow", None)
        if not callable(reflow):
            return
        width = max(1, page.contentsRect().width())
        reflow(width)
        page.updateGeometry()

    def _migrate_backend_preferences_async(self) -> None:
        if not (self._missing_backend_language or self._missing_backend_appearance):
            return

        def success(payload: object) -> None:
            local = payload if isinstance(payload, dict) else {}
            if self._missing_backend_language:
                language = normalize_language(local.get("idioma", "auto"))
                self.settings.setValue("settings/language", language)
                self._apply_language(language, persist=False)
                self._missing_backend_language = False
            if self._missing_backend_appearance:
                old_theme = str(local.get("tema", "system")).strip().lower()
                mode = old_theme if old_theme in {"light", "dark"} else "system"
                self.settings.setValue("settings/appearance", mode)
                self._apply_appearance(
                    mode,
                    str(self.settings.value("settings/accent", "blue")),
                    str(self.settings.value("settings/density", "comfortable")),
                    persist=False,
                )
                self._missing_backend_appearance = False

        self._background.start(
            "settings-migration",
            self._state_cache.config,
            success,
        )

    def _save_backend_preference(self, key: str, value: object) -> None:
        def operation() -> object:
            if self.settings_service is None:
                raise RuntimeError("Desktop requires a settings service to save preferences")
            self.settings_service.save_local_config({key: value})
            return True

        self._background.start(
            f"save-preference:{key}",
            operation,
            lambda _result: self._state_cache.invalidate("config"),
        )

    def _system_theme(self) -> str:
        app = QApplication.instance()
        if app is None:
            return "light"
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
            if scheme == Qt.ColorScheme.Light:
                return "light"
        except (AttributeError, RuntimeError):
            logger.debug("Qt did not expose the current platform color scheme", exc_info=True)
        try:
            return "dark" if app.palette().window().color().lightness() < 128 else "light"
        except Exception:
            return "light"

    def _apply_language(self, language: str, *, persist: bool = True) -> None:
        requested = normalize_language(language)
        resolved = set_language(requested)
        if persist:
            self.settings.setValue("settings/language", requested)
            self._save_backend_preference("idioma", resolved)
        if hasattr(self, "sidebar"):
            self._retranslate_interface()

    def _apply_appearance(self, mode: str, accent: str, density: str, *, persist: bool = True) -> None:
        requested_mode = self.preferences.normalize_theme(mode)
        accent = self.preferences.normalize_accent(accent)
        density = self.preferences.normalize_density(density)
        resolved_mode = self._system_theme() if requested_mode == "system" else requested_mode
        scale = self.preferences.scale()
        configure_theme(resolved_mode, accent, density, scale)
        self.setStyleSheet(application_stylesheet())
        if hasattr(self, "root_layout"):
            margin = 12 if density == "compact" else 16
            self.root_layout.setContentsMargins(margin, margin, margin, margin)
            self.root_layout.setSpacing(12 if density == "compact" else 16)
        if hasattr(self, "sidebar_host"):
            sidebar_layout = self.sidebar_host.layout()
            if sidebar_layout is not None:
                sidebar_layout.setContentsMargins(0, 6 if density == "compact" else 8, 0, 0)
        if persist:
            self.settings.setValue("settings/appearance", requested_mode)
            self.settings.setValue("settings/accent", accent)
            self.settings.setValue("settings/density", density)
            self._save_backend_preference("tema", resolved_mode)
        if hasattr(self, "sidebar"):
            self.sidebar.apply_appearance()
        if hasattr(self, "pages"):
            for page in self.pages.values():
                apply = getattr(page, "apply_appearance", None)
                if callable(apply):
                    apply()
        settings_dialog = getattr(self, "settings_dialog", None)
        if settings_dialog is not None:
            settings_dialog.refresh_appearance()
        self._refresh_theme_aware_widgets()
        gamepad = getattr(self, "gamepad", None)
        if gamepad is not None:
            gamepad.refresh_appearance()


    def _apply_scale(self, scale: int) -> None:
        normalized = max(70, min(150, round(int(scale) / 10) * 10))
        self.settings.setValue("settings/scale", normalized)
        self._apply_appearance(
            str(self.settings.value("settings/appearance", "system")),
            str(self.settings.value("settings/accent", "blue")),
            str(self.settings.value("settings/density", "comfortable")),
            persist=False,
        )

    def _set_detailed_diagnostics(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.setValue("settings/detailed_diagnostics", "true" if enabled else "false")
        for page in getattr(self, "pages", {}).values():
            setter = getattr(page, "set_detailed_diagnostics", None)
            if callable(setter):
                setter(enabled)

    def _show_safety_alert(self, title: str, message: str, level: str) -> None:
        tone = "red" if level == "critical" else "orange"
        InfoDialog(
            title,
            message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="SAFETY ALERT",
            notice="This warning was recorded in local history. No hardware command was executed.",
            tone=tone,
        ).open()

    def _refresh_theme_aware_widgets(self) -> None:
        """Refresh widgets whose palette is stored in an inline stylesheet.

        The global QSS cannot override an inline background reliably.  Calling a
        small opt-in hook keeps badges, status pills, charts and value chips in
        sync after a live light/dark or accent switch without recreating pages.
        """
        root = self.centralWidget()
        if root is None:
            return
        for widget in (root, *root.findChildren(QWidget)):
            refresh = getattr(widget, "_refresh_palette", None)
            if callable(refresh):
                refresh()
        console = getattr(self, "console", None)
        if console is not None:
            # The terminal paints its own grid, so it reads the palette
            # directly instead of through the stylesheet.
            console.apply_theme()

    def _retranslate_interface(self) -> None:
        if hasattr(self, "sidebar"):
            self.sidebar.retranslate()
        localize_top_levels()
        # Most pages are made of literal labels and are covered by the shared
        # widget-tree pass.  A small number also render live formatted values
        # (for example fan duty presets and curve summaries); let those pages
        # rebuild their display-only copy after the language has changed.
        for page in getattr(self, "pages", {}).values():
            # Pages live inside the central stack and are not top-level Qt
            # widgets, so explicitly walk them on every live language change.
            localize_widget_tree(page)
            retranslate_dynamic_copy = getattr(page, "retranslate_dynamic_copy", None)
            if callable(retranslate_dynamic_copy):
                retranslate_dynamic_copy()
        gamepad = getattr(self, "gamepad", None)
        if gamepad is not None:
            gamepad.retranslate()
        console = getattr(self, "console", None)
        if console is not None:
            console.retranslate()

    def _restore_start_page(self) -> None:
        start = str(self.settings.value("settings/start_page", "dashboard"))
        if self.preferences.bool_value("settings/reopen_last_module", True):
            start = str(self.settings.value("settings/last_module", start))
        if start in self.pages:
            self.navigate(start)
        else:
            self.navigate("dashboard")
            if start == "settings":
                QTimer.singleShot(0, lambda: self._open_settings_dialog("general"))

    def _save_sidebar_state(self, collapsed: bool) -> None:
        if getattr(self, "_sidebar_change_is_automatic", False):
            return
        self._sidebar_user_collapsed = bool(collapsed)
        self.settings.setValue("sidebar_collapsed", "true" if collapsed else "false")

    def _set_sidebar_collapsed_automatically(self, collapsed: bool) -> None:
        if self.sidebar.collapsed == bool(collapsed):
            return
        self._sidebar_change_is_automatic = True
        try:
            self.sidebar.set_collapsed(bool(collapsed))
        finally:
            self._sidebar_change_is_automatic = False

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        if not hasattr(self, "sidebar") or not hasattr(self, "root_layout"):
            return
        width = event.size().width()
        # Hysteresis avoids a visible open/close loop while the user drags near
        # the breakpoint. A manually collapsed sidebar always stays collapsed.
        if width < 900 and not self.sidebar.collapsed:
            self._sidebar_auto_collapsed = True
            self._set_sidebar_collapsed_automatically(True)
        elif width > 980 and self._sidebar_auto_collapsed:
            self._sidebar_auto_collapsed = False
            self._set_sidebar_collapsed_automatically(self._sidebar_user_collapsed)

        compact_shell = width < 820
        margin = 8 if compact_shell else 12 if self.preferences.normalize_density(
            str(self.settings.value("settings/density", "comfortable"))
        ) == "compact" else 16
        spacing = 8 if compact_shell else 12 if margin == 12 else 16
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(spacing)

    @staticmethod
    def _set_page_updates(page: QWidget | None, active: bool) -> None:
        if page is None:
            return
        setter = getattr(page, "set_updates_active", None)
        if callable(setter):
            setter(bool(active))

    def _remember_current_module(self) -> None:
        """Persist the open module for the next launch, off the click path."""
        self.settings.setValue("settings/last_module", self.current_page_key)

    def navigate(self, key: str) -> None:
        started = time.perf_counter()
        if key in self.pages:
            page = self.pages[key]
            if key in self.sidebar.buttons:
                self.sidebar.buttons[key].setChecked(True)
            if key == self.current_page_key and self.stack.currentWidget() is page:
                self._set_page_updates(page, True)
                QTimer.singleShot(0, self._sync_current_page_layout)
                return
            previous = self.stack.currentWidget()
            previous_key = self.current_page_key
            if (
                not self._gamepad_suppress_history
                and previous_key in self.pages
                and previous_key != key
            ):
                if not self._gamepad_navigation_history or self._gamepad_navigation_history[-1] != previous_key:
                    self._gamepad_navigation_history.append(previous_key)
                    del self._gamepad_navigation_history[:-24]
            self._set_page_updates(previous, False)
            self.stack.setCurrentWidget(page)
            self.current_page_key = key
            # Remembering the module is for the *next* launch, so it has no
            # business inside the frame that has to paint the page the user
            # just clicked. Write it once the transition is on screen.
            QTimer.singleShot(0, self._remember_current_module)
            self._set_page_updates(page, True)
            # Hidden QStackedWidget pages may retain the geometry from their
            # construction pass.  Reflow only after the selected page owns the
            # real stack area, preserving desktop layouts on wide windows.
            QTimer.singleShot(0, self._sync_current_page_layout)
            gamepad = getattr(self, "gamepad", None)
            if gamepad is not None:
                gamepad.defer_focus_current_scope()
            if _ui_perf_enabled():
                QTimer.singleShot(
                    0,
                    lambda section=key, began=started: logger.info(
                        "UI PERF navigation %s painted in %.1f ms",
                        section,
                        (time.perf_counter() - began) * 1000.0,
                    ),
                )
            return

        if key in {"history", "settings"}:
            section = "reports" if key == "history" else "general"
            self._open_settings_dialog(section)
            return

        if key in self.sidebar.buttons:
            self.sidebar.buttons[key].setChecked(True)
        InfoDialog(
            "Module not available",
            "This module is not available in this installation.",
            icon_name="info_blue",
            parent=self,
            eyebrow="MODULE",
            button_text="Back to Dashboard",
            notice="No hardware command was executed.",
            tone="blue",
        ).exec()
        self.sidebar.buttons[self.current_page_key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[self.current_page_key])

    def _open_settings_dialog(self, section: str = "general") -> None:
        previous_key = self.current_page_key if self.current_page_key in self.sidebar.buttons else "dashboard"
        previous_page = self.pages.get(previous_key)
        self._set_page_updates(previous_page, False)
        if "settings" in self.sidebar.buttons:
            self.sidebar.buttons["settings"].setChecked(True)
        if self.settings_dialog is None:
            # Settings is a large, rarely used module.  Import it on demand so
            # normal startup and page navigation do not parse/build its widget
            # graph before the user opens the dialog.
            from .pages.settings import SettingsDialog

            build_started = time.perf_counter()
            dialog = SettingsDialog(
                self.controller,
                settings_service=self.settings_service,
                activity_service=self.activity_service,
                app_settings=self.settings,
                parent=self,
            )
            if _ui_perf_enabled():
                logger.info(
                    "UI PERF settings dialog shell built in %.1f ms",
                    (time.perf_counter() - build_started) * 1000.0,
                )
            dialog.language_changed.connect(self._apply_language)
            dialog.appearance_changed.connect(self._apply_appearance)
            dialog.scale_changed.connect(self._apply_scale)
            dialog.smart_alerts_changed.connect(self.alert_monitor.set_enabled)
            dialog.diagnostics_changed.connect(self._set_detailed_diagnostics)
            dialog.sidebar_collapsed_changed.connect(self.sidebar.set_collapsed)
            dialog.gamepad_navigation_changed.connect(self._set_gamepad_navigation_enabled)
            dialog.gamepad_keypad_changed.connect(self.gamepad.set_onscreen_keypad_enabled)
            dialog.gamepad_keypad_auto_show_changed.connect(self.gamepad.set_onscreen_keypad_auto_show)
            dialog.embedded_terminal_changed.connect(self.set_embedded_terminal_enabled)
            dialog.console_auto_hide_changed.connect(self.set_console_auto_hide)
            self.settings_dialog = dialog
        dialog = self.settings_dialog
        dialog.select_section(section)
        dialog.exec()
        if previous_key in self.sidebar.buttons:
            self.sidebar.buttons[previous_key].setChecked(True)
        if previous_page is not None:
            self.stack.setCurrentWidget(previous_page)
            self._set_page_updates(previous_page, True)

    def gamepad_bottom_inset(self) -> int:
        """Height the controller legend must stay clear of at the bottom.

        The legend floats over the window at a fixed offset from its bottom
        edge. The console docks there too, so with a workflow running the
        legend sat on top of the answer row and covered the Send button — the
        one control a person needs at exactly that moment.
        """
        console = getattr(self, "console", None)
        if console is None or not console.is_open:
            return 0
        try:
            return max(0, console.height())
        except RuntimeError:
            return 0

    def gamepad_focus_scope(self) -> QWidget:
        """Return the active page as the preferred first-focus area."""
        console = getattr(self, "console", None)
        if console is not None and console.is_open:
            # A workflow on screen is the thing being waited on; entering the
            # page behind it would leave its prompt unreachable.
            scope = console.gamepad_focus_scope()
            if isinstance(scope, QWidget):
                return scope
        page = self.stack.currentWidget()
        provider = getattr(page, "gamepad_focus_scope", None)
        if callable(provider):
            scope = provider()
            if isinstance(scope, QWidget):
                return scope
        return page or self

    def gamepad_back(self) -> None:
        """Steam-style B behavior: visit history, then fall back to Dashboard."""
        console = getattr(self, "console", None)
        if console is not None and console.is_open and not console.busy:
            # In Game Mode there is no pointer, and the console's header
            # buttons are deliberately unfocusable so that typing reaches the
            # workflow instead of them. Without this, a workflow that failed —
            # which is exactly the one that stays on screen — could not be
            # dismissed with a controller at all. A workflow still running is
            # left alone: the panel is where it reports.
            console.slide_out()
            return
        page = self.stack.currentWidget()
        handler = getattr(page, "gamepad_back", None)
        if callable(handler) and bool(handler()):
            return
        target = self._gamepad_navigation_history.pop() if self._gamepad_navigation_history else "dashboard"
        if target == self.current_page_key:
            target = "dashboard"
        self._gamepad_suppress_history = True
        try:
            self.navigate(target if target in self.pages else "dashboard")
        finally:
            self._gamepad_suppress_history = False

    def gamepad_cycle_section(self, delta: int) -> None:
        """Cycle the sidebar with LB/RB without replacing mouse navigation."""
        order = [key for key in self.sidebar.buttons if key in self.pages or key == "settings"]
        if not order:
            return
        current = self.current_page_key if self.current_page_key in order else order[0]
        target = order[(order.index(current) + (1 if delta > 0 else -1)) % len(order)]
        self.navigate(target)

    def gamepad_toggle_sidebar(self) -> None:
        """Toggle the sidebar from the controller Menu/Start button."""
        if not hasattr(self, "sidebar"):
            return
        self._sidebar_auto_collapsed = False
        self.sidebar.set_collapsed(not self.sidebar.collapsed)

    def gamepad_open_settings(self) -> None:
        """Open layout/preferences from the controller View/Select button."""
        self._open_settings_dialog("general")

    def gamepad_go_dashboard(self) -> None:
        """Jump directly to the Dashboard from the controller guide/home button."""
        if self.current_page_key != "dashboard":
            self.navigate("dashboard")
        else:
            gamepad = getattr(self, "gamepad", None)
            if gamepad is not None:
                gamepad.defer_focus_current_scope()

    def _set_gamepad_navigation_enabled(self, enabled: bool) -> None:
        self._gamepad_navigation_enabled = bool(enabled)
        if self._gamepad_navigation_enabled:
            self.gamepad.start()
        else:
            self.gamepad.stop()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        gamepad = getattr(self, "gamepad", None)
        if gamepad is not None:
            gamepad.stop()

        console = getattr(self, "console", None)
        if console is not None and console.busy and not getattr(self, "_close_pending", False):
            # A privileged workflow is mid-flight. Closing the window would
            # kill it between two system changes, which is the worst moment.
            if not self._confirm_closing_a_running_workflow():
                event.ignore()
                return

        outstanding = self._outstanding_background_work()
        if outstanding and not self._waited_long_enough_to_close():
            event.ignore()
            if not getattr(self, "_close_pending", False):
                self._close_pending = True
                logger.info("Waiting for %s before closing", outstanding)
                QTimer.singleShot(50, self._close_when_idle)
            return

        self._close_pending = False
        host = getattr(self, "console_host", None)
        if host is not None:
            host.uninstall()
        if console is not None:
            console.shutdown()
        # Last chance to let a pool worker leave ``operation()`` while Python is
        # still alive.  Past this point the interpreter starts finalizing, and a
        # worker that calls back into it aborts the whole process.
        QThreadPool.globalInstance().waitForDone(self.BACKGROUND_DRAIN_MS)
        super().closeEvent(event)

    def _confirm_closing_a_running_workflow(self) -> bool:
        from PyQt6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            tr("Terminal"),
            tr("A workflow is still running in the terminal. Closing now stops it."),
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Close

    def _outstanding_background_work(self) -> str:
        """Describe what is still running, or return an empty string.

        Two different mechanisms do work off the GUI thread and only one of
        them is reachable from the widget tree.  The gamepad monitor is a
        ``QThread`` child, so ``findChildren`` finds it; every page refresh is a
        ``QRunnable`` on the global pool, whose worker threads are owned by Qt
        and parented to nothing.  Looking only at ``QThread`` children — which
        is what this did — meant the window never waited for a single backend
        read, and closing during one aborted the process on the way out.
        """
        threads = [thread for thread in self.findChildren(QThread) if thread.isRunning()]
        reads = pending_background_tasks()
        parts = []
        if threads:
            parts.append(f"{len(threads)} monitor thread(s)")
        if reads:
            parts.append(f"{reads} backend read(s)")
        return " and ".join(parts)

    def _waited_long_enough_to_close(self) -> bool:
        """A wait with no deadline is a window that will not close.

        A backend read can block on hardware that never answers.  After this
        long the close proceeds and the bounded drain below absorbs whatever is
        left.
        """
        started = getattr(self, "_close_requested_at", None)
        if started is None:
            self._close_requested_at = time.monotonic()
            return False
        return (time.monotonic() - started) * 1000.0 >= self.BACKGROUND_WAIT_MS

    def _close_when_idle(self) -> None:
        if self._outstanding_background_work() and not self._waited_long_enough_to_close():
            QTimer.singleShot(50, self._close_when_idle)
            return
        self.close()

    def _dashboard_action(self, action: str) -> None:
        if action in {"cpu_configuration", "cpu_overview"}:
            self.navigate("cpu")
            self.cpu_page._select_workspace(action.removeprefix("cpu_"))
            return
        if action in {"fans_manual", "fans_curve"}:
            self.navigate("fans")
            self.fans_page._set_control_mode(action.removeprefix("fans_"))
            self.fans_page.scroll.verticalScrollBar().setValue(0)
            return
        if action == "repositories":
            from .pages.settings import RepositoriesDialog

            RepositoriesDialog(self).exec()
            return
        if action == "apply_profile":
            self.navigate("cpu")
            return
        if action == "prepare_pwm":
            # Dashboard quick actions execute their workflow in place.  The
            # Fans page owns the validated confirmation and asynchronous
            # terminal launcher, but it does not need to become visible.
            self.fans_page.prepare_pwm_driver(dialog_parent=self)
            return
        if action == "open_logs":
            self._open_settings_dialog("reports")
            return
        if action != "prepare_dependencies":
            return
        # Keep the Dashboard selected while reusing the governor page's
        # conflict-aware dependency preparation dialog and terminal workflow.
        # The shared Dashboard refresh already warmed this cache; forwarding
        # it prevents a never-opened GPU page from missing conflict detection.
        try:
            cached_tools = dict(self._state_cache.tools() or {})
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            cached_tools = {}
        if cached_tools:
            self.gpu_page.current_state = {
                **dict(getattr(self.gpu_page, "current_state", {}) or {}),
                "tools": cached_tools,
            }
        self.gpu_page.prepare_dependencies(dialog_parent=self)

    def _dashboard_dependency_action(self, request: object) -> None:
        """Run the compact sidebar selection through the governor safety flow."""
        payload = dict(request) if isinstance(request, dict) else {}
        try:
            cached_tools = dict(self._state_cache.tools() or {})
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            cached_tools = {}
        if cached_tools:
            self.gpu_page.current_state = {
                **dict(getattr(self.gpu_page, "current_state", {}) or {}),
                "tools": cached_tools,
            }
        options = {
            "action": str(payload.get("action") or "prepare"),
            "preference": str(payload.get("governor") or "auto"),
            "selected_components": set(payload.get("selected_components") or ()),
            "dialog_parent": self,
        }
        if options["action"] in {"memory_swap", "memory_ttm"}:
            options.update(
                memory_policy=str(payload.get("memory_policy") or "current"),
                memory_ttm_gib=int(payload.get("memory_ttm_gib") or 0),
            )
        self.gpu_page.execute_dependency_action(
            **options,
        )

    def _dashboard_driver_support(self, component: str) -> None:
        """Launch a reviewed distribution-native support route from Dashboard."""
        if component not in {"connectivity", "printing"}:
            return
        try:
            self.controller.install_driver_support(component)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            InfoDialog(
                "Support unavailable",
                str(error),
                icon_name="warning_orange",
                parent=self,
                eyebrow="Hardware",
                notice="No changes were made.",
                tone="orange",
            ).open()
