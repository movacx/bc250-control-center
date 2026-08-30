from PyQt6.QtCore import QSettings

from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
from frontends.desktop.i18n.locale_catalog import load_locale_catalog
from frontends.desktop.pages.settings import SettingsPage


class Controller:
    def __init__(self):
        self.calls = 0

    def recovery_inventory(self):
        self.calls += 1
        return {
            "root": "/state/recovery",
            "restore_available": False,
            "snapshots": [
                {
                    "id": "123-before",
                    "label": "before",
                    "verified": True,
                    "blocked": False,
                    "actions": 1,
                }
            ],
        }

    def create_recovery_snapshot(self, label):
        self.calls += 1
        return {
            "path": "/state/recovery/123-before",
            "verified": True,
            "entries": 3,
            "states": {"captured": 2, "missing": 1},
            "boot_critical": 1,
            "label": label,
        }

    def config_paths(self):
        return {}


class SettingsService:
    pass


class ActivityService:
    def clear(self):
        return True


def test_health_page_is_not_exposed_in_settings(qtbot, tmp_path):
    controller = Controller()
    ui_settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    page = SettingsPage(controller, settings_service=SettingsService(), activity_service=ActivityService(), app_settings=ui_settings)
    qtbot.addWidget(page)
    assert "health" not in page.section_order
    assert "health" not in page.nav_buttons
    assert page._ensure_section("health") is None


def test_notifications_are_hidden_and_forced_off(qtbot, tmp_path):
    controller = Controller()
    ui_settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    ui_settings.setValue("settings/smart_alerts", "true")
    ui_settings.setValue("settings/desktop_notifications", "true")
    page = SettingsPage(
        controller,
        settings_service=SettingsService(),
        activity_service=ActivityService(),
        app_settings=ui_settings,
    )
    qtbot.addWidget(page)

    assert "notifications" not in page.section_order
    assert "notifications" not in page.nav_buttons
    assert ui_settings.value("settings/smart_alerts") == "false"
    assert ui_settings.value("settings/desktop_notifications") == "false"


def test_recovery_interface_copy_is_translated_in_every_language():
    sources = (
        "Recovery readiness",
        "Inspect snapshots",
        "Create snapshot",
        "Recovery snapshots",
        "Inspect verified snapshots and non-executing restore plans. System restore is not enabled.",
        "Capture curated BC250 configuration files or inspect verified, non-executing restore plans. System restore is not enabled.",
        "Entries",
        "Captured",
        "Missing",
        "Unreadable",
        "Boot-critical entries",
        "The snapshot is verified. Restore execution remains disabled.",
        "Recovery snapshot created",
        "Recovery snapshot failed",
        "No recovery snapshots are stored.",
        "Verified",
        "Invalid",
        "Manual review required",
        "Plan available",
        "Actions",
        "Storage",
        "Restore execution is disabled; this view does not change the system.",
        "Recovery snapshot inventory",
        "Recovery inventory failed",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language).strip() for source in sources), language
        assert all(source in load_locale_catalog(language) for source in sources), language
