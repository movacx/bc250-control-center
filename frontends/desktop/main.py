from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from bc250cc.application import ApplicationContainer
from bc250cc.infrastructure.polkit_session import ensure_graphical_polkit_agent
from bc250cc.infrastructure.terminal_plan import set_translator
from bc250cc.shared.logging_config import configure_logging
from frontends.desktop import ControlCenterWindow
from frontends.desktop.i18n import tr

#: How long after the window first shows the performance recorder starts.
PERFORMANCE_RECORDING_DELAY_MS = 2000


def build_desktop_api():
    """Build the desktop-facing application API from the composition root."""

    service = ApplicationContainer.production().system_service
    if service is None:
        raise RuntimeError("Application container did not construct the system service")
    return service


def main() -> int:
    configure_logging()
    # Text baked into the generated terminal script has to be translated here,
    # because ``src`` cannot import the frontend's catalogs.
    set_translator(tr)
    app = QApplication(sys.argv)
    app.setApplicationName("BC250 Control Center")
    app.setApplicationDisplayName("BC250 Control Center")
    app.setDesktopFileName("io.github.movacx.bc250-control-center")
    # Standalone compositors such as Hyprland do not always autostart the
    # installed Polkit prompt.  Prepare it before any page can request root.
    ensure_graphical_polkit_agent()
    container = ApplicationContainer.production()
    if (container.system_service is None or container.settings_service is None
            or container.activity_service is None):
        raise RuntimeError("Application container did not construct desktop services")
    window = ControlCenterWindow(
        container.system_service,
        settings_service=container.settings_service,
        activity_service=container.activity_service,
    )
    window.show()
    # The performance history records from launch, not from the first visit:
    # opening Monitoring should show the last two minutes, not an empty graph.
    # Deferred so the first sample does not compete with the first paint.
    QTimer.singleShot(PERFORMANCE_RECORDING_DELAY_MS, window.performance_page.start_recording)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
