"""Additional settings: the Dashboard's preparation tabs, minus Components.

Compatibility, Memory & Swap, Decky and Drivers are the same panel the
Dashboard shows under "Prepare BC250 system", built from the same class and
fed the same tools snapshot. Components (dependency preparation) stays on the
Dashboard only.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..components.dashboard_widgets import DashboardScrollArea, PreparationSidebar
from ..components.responsive import configure_responsive_scroll_area
from ..components.style_state import offscreen_in_shown_window


class AdditionalSettingsPage(QWidget):
    dependency_action_requested = pyqtSignal(object)
    driver_support_requested = pyqtSignal(str)

    def __init__(
        self,
        *,
        state_feed: Callable[[bool], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state_feed = state_feed
        self.panel = PreparationSidebar(standalone=True)
        self.panel.prepare_requested.connect(self.dependency_action_requested)
        self.panel.dependency_action_requested.connect(self.dependency_action_requested)
        self.panel.driver_support_requested.connect(self.driver_support_requested)

        self.scroll = DashboardScrollArea()
        # The panel keeps its own height. Handed the whole viewport, it spread
        # the header, the tab row and the cards apart.
        host = QWidget()
        configure_responsive_scroll_area(self.scroll, host)
        host_layout = QVBoxLayout(host)
        # The page inset every workspace shares (Dashboard, CPU / SMU, ...).
        host_layout.setContentsMargins(18, 8, 18, 24)
        host_layout.setSpacing(0)
        host_layout.addWidget(self.panel)
        host_layout.addStretch(1)
        self.scroll.setWidget(host)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

    def apply_state(self, state) -> None:
        # The Dashboard hands over every state it applies, and this page is
        # rarely the one on screen: only the latest is kept, and drawn when
        # the page is shown. Drawing every one of them made each switch
        # between the other pages wait for this panel.
        self._pending_state = state
        if not offscreen_in_shown_window(self):
            self._render_pending_state()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self._render_pending_state()

    def _render_pending_state(self) -> None:
        state = getattr(self, "_pending_state", None)
        self._pending_state = None
        if state is not None:
            self.panel.set_state(state)

    def set_updates_active(self, active: bool) -> None:
        if self._state_feed is not None:
            self._state_feed(bool(active))

    def retranslate_dynamic_copy(self) -> None:
        self.panel.retranslate_dynamic_copy()
