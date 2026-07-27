from __future__ import annotations

from pathlib import Path
import logging
import os
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .core.alerts import SmartAlertMonitor
from .core.gamepad import GamepadNavigationController
from .core.preferences import UiPreferences
from .components.async_tools import BackgroundExecutor
from .i18n import localize_top_levels, normalize_language, set_language
from .components.page_widgets import ConfirmDialog
from .core.state import state_cache_for
from .components.sidebar import Sidebar
from .theme import application_stylesheet, configure_theme
from .components.widgets import InfoDialog

if TYPE_CHECKING:
    from .pages.settings import SettingsDialog


logger = logging.getLogger(__name__)


def _ui_perf_enabled() -> bool:
    return str(os.environ.get("BC250_UI_PERF", "")).strip().lower() in {"1", "true", "yes", "on"}


class ControlCenterWindow(QMainWindow):
    """Definitive BC250 interface backed by the application controller."""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.preferences = UiPreferences()
        self.settings = self.preferences.settings
        migration = self.preferences.initialize()
        self._background = BackgroundExecutor(self)
        self._state_cache = state_cache_for(controller)
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
        app_icon = Path(__file__).resolve().parents[1] / "Resources" / "icons" / "bc250-control-center.png"
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))
        self.resize(1460, 880)
        # 720×520 is the smallest useful shell. Below this point the pages still
        # remain intact through vertical scrolling, while the desktop window
        # manager retains a realistic resize target.
        self.setMinimumSize(720, 520)

        root = QWidget()
        root.setObjectName("ApplicationRoot")
        layout = QHBoxLayout(root)
        self.root_layout = layout
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        self.setCentralWidget(root)

        # Every page uses an 8 px top inset before its first visible card.
        # The sidebar and page cards share the same top alignment.
        self.sidebar_host = QWidget()
        self.sidebar_host.setObjectName("SidebarHost")
        self.sidebar_host.setMinimumWidth(0)
        self.sidebar_host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        sidebar_layout = QVBoxLayout(self.sidebar_host)
        sidebar_layout.setContentsMargins(0, 8, 0, 0)
        sidebar_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigation_requested.connect(self.navigate)
        collapsed = self.preferences.bool_value("sidebar_collapsed", False)
        self._sidebar_user_collapsed = collapsed
        self._sidebar_auto_collapsed = False
        self._sidebar_change_is_automatic = False
        self.sidebar.set_collapsed(collapsed)
        self.sidebar.set_status_card_enabled(self.preferences.bool_value("settings/show_status_card", True))
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
        self.cpu_page = CpuSmuPage(controller)
        self.gpu_page = GpuGovernorPage(controller)
        self.cu_page = ComputeUnitsPage(controller)
        self.fans_page = FansPage(controller)
        self.processes_page = ProcessesPage(controller)
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
        for page in self.pages.values():
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self.gamepad = GamepadNavigationController(self)
        self.alert_monitor = SmartAlertMonitor(controller, self.settings, self)
        self.alert_monitor.alert_triggered.connect(self._show_safety_alert)
        self._gamepad_navigation_enabled = self.preferences.bool_value("settings/gamepad_navigation", True)
        self.gamepad.set_onscreen_keypad_enabled(self.preferences.bool_value("settings/gamepad_onscreen_keypad", True))
        self.gamepad.set_onscreen_keypad_auto_show(self.preferences.bool_value("settings/gamepad_keypad_auto_show", False))
        self._set_detailed_diagnostics(self.preferences.bool_value("settings/detailed_diagnostics", False))
        self._retranslate_interface()
        self._restore_start_page()
        self._migrate_backend_preferences_async()
        self._set_gamepad_navigation_enabled(self._gamepad_navigation_enabled)

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
        QTimer.singleShot(0, self._sync_current_page_layout)
        QTimer.singleShot(80, self._sync_current_page_layout)

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
            self.controller.guardar_config_local({key: value})
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

    def _retranslate_interface(self) -> None:
        if hasattr(self, "sidebar"):
            self.sidebar.retranslate()
        localize_top_levels()
        gamepad = getattr(self, "gamepad", None)
        if gamepad is not None:
            gamepad.retranslate()

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

    def _set_sidebar_status_visible(self, visible: bool) -> None:
        self.sidebar.set_status_card_enabled(visible)

    @staticmethod
    def _set_page_updates(page: QWidget | None, active: bool) -> None:
        if page is None:
            return
        setter = getattr(page, "set_updates_active", None)
        if callable(setter):
            setter(bool(active))

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
            self.settings.setValue("settings/last_module", key)
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
            dialog = SettingsDialog(self.controller, app_settings=self.settings, parent=self)
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
            dialog.sidebar_status_changed.connect(self._set_sidebar_status_visible)
            dialog.sidebar_collapsed_changed.connect(self.sidebar.set_collapsed)
            dialog.gamepad_navigation_changed.connect(self._set_gamepad_navigation_enabled)
            dialog.gamepad_keypad_changed.connect(self.gamepad.set_onscreen_keypad_enabled)
            dialog.gamepad_keypad_auto_show_changed.connect(self.gamepad.set_onscreen_keypad_auto_show)
            self.settings_dialog = dialog
        dialog = self.settings_dialog
        dialog.select_section(section)
        dialog.exec()
        if previous_key in self.sidebar.buttons:
            self.sidebar.buttons[previous_key].setChecked(True)
        if previous_page is not None:
            self.stack.setCurrentWidget(previous_page)
            self._set_page_updates(previous_page, True)

    def gamepad_focus_scope(self) -> QWidget:
        """Return the active page as the preferred first-focus area."""
        return self.stack.currentWidget() or self

    def gamepad_back(self) -> None:
        """Steam-style B behavior: visit history, then fall back to Dashboard."""
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
        super().closeEvent(event)

    def _dashboard_action(self, action: str) -> None:
        if action == "apply_profile":
            self.navigate("cpu")
            return
        if action == "prepare_pwm":
            self.navigate("fans")
            return
        if action == "open_logs":
            self._open_settings_dialog("reports")
            return
        if action != "prepare_dependencies":
            return
        dialog = ConfirmDialog(
            "Prepare BC250 dependencies",
            "This reuses the existing distribution-specific R64 workflow in a visible terminal. It may install packages or stage an immutable-system reboot.",
            summary=(("Scope", "Governor, CPU tools, UMR, 40CU manager"), ("Backend", "Existing R64 OS repositories")),
            confirm_text="Open preparation workflow",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def operation() -> object:
            return self.controller.instalar_dependencias_bc250()

        def failure(message: str) -> None:
            InfoDialog(
                "Dependency preparation failed",
                message,
                icon_name="warning_orange",
                parent=self,
                eyebrow="SYSTEM READINESS",
                button_text="Close",
                notice="No additional command will be attempted automatically.",
                tone="red",
            ).exec()

        self._background.start(
            "dashboard-dependency-preparation",
            operation,
            lambda _result: self._state_cache.invalidate("tools"),
            failure,
        )
