from PyQt6.QtWidgets import QLabel

from frontends.desktop.components.sidebar import Sidebar
from frontends.desktop.i18n import COMPLETE_LOCALES, set_language, tr
from frontends.desktop.pages.drivers import DriversPage


class _Controller:
    def driver_inventory(self):
        return {}

    def install_driver_support(self, component):
        raise AssertionError(f"unexpected install: {component}")


def _snapshot():
    return {
        "distribution": "Artix Linux",
        "family": "arch",
        "init_manager": "openrc",
        "supported_components": ("connectivity", "printing"),
        "network": (
            {"name": "wlan0", "kind": "wifi", "driver": "mt7921u", "state": "up"},
        ),
        "bluetooth_controllers": (),
        "usb_printers": (),
        "printing": {"cups_tools": True, "ipp_usb": True, "gui": False, "queues": ()},
        "aic8800": {
            "loaded": False,
            "candidate_detected": False,
            "posture": "reference-only",
        },
    }


def test_sidebar_keeps_drivers_inside_system_preparation(qtbot):
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    assert "drivers" not in sidebar.buttons


def test_drivers_page_renders_runtime_driver_without_service_assumptions(qtbot):
    page = DriversPage(_Controller())
    qtbot.addWidget(page)
    page._apply_snapshot(_snapshot())
    text = "\n".join(label.text() for label in page.findChildren(QLabel))
    assert "wlan0" in text
    assert "mt7921u" in text
    assert "40" not in text
    assert page.connectivity_button.isEnabled()
    assert page.printing_button.isEnabled()
    assert not page.printer_settings_button.isEnabled()


def test_embedded_drivers_page_uses_automatic_refresh_and_compact_actions(qtbot):
    page = DriversPage(_Controller(), embedded=True)
    qtbot.addWidget(page)

    assert page.header is None
    assert page.auto_refresh_timer.interval() == 2_000
    assert page.printer_settings_button.text() == ""
    assert page.printer_settings_button.toolTip() == tr("Open settings")
    assert page.connectivity_button.property("headerActionWidth") == 176
    assert page.printing_button.property("headerActionWidth") == 176
    assert page.network_card.status is None
    assert page.printing_card.status is None

    page.set_updates_active(True)
    assert page.auto_refresh_timer.isActive()
    page.set_updates_active(False)
    assert not page.auto_refresh_timer.isActive()


def test_every_complete_locale_translates_new_drivers_page_copy():
    sources = (
        "Drivers",
        "Printing",
        "External drivers",
        "Install support",
        "SteamOS-specific; Wi-Fi only. Never installed automatically.",
        "This opens a terminal with reviewed distribution packages. No external kernel driver is downloaded.",
    )
    try:
        for locale in COMPLETE_LOCALES:
            set_language(locale)
            for source in sources:
                translated = tr(source)
                assert translated.strip()
                if locale != "en" and len(source.split()) >= 4:
                    assert translated != source, (locale, source)
    finally:
        set_language("en")
