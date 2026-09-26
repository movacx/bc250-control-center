from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QFrame, QLabel

from frontends.desktop.core.preferences import UiPreferences
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
from frontends.desktop.pages.settings import SettingsDialog, SettingsPage


class SettingsService:
    pass


class ActivityService:
    def clear(self):
        return True


def _settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


def test_legacy_keypad_preferences_migrate_to_one_automatic_feature(tmp_path):
    settings = _settings(tmp_path)
    settings.setValue("settings/gamepad_onscreen_keypad", "true")
    settings.setValue("settings/gamepad_keypad_auto_show", "false")

    UiPreferences(settings).initialize()

    assert settings.value("settings/gamepad_onscreen_keypad") == "true"
    assert settings.value("settings/gamepad_keypad_auto_show") == "true"


def test_settings_show_only_one_gamepad_keypad_option(qtbot, tmp_path):
    page = SettingsPage(object(), settings_service=SettingsService(), activity_service=ActivityService(), app_settings=_settings(tmp_path))
    qtbot.addWidget(page)
    # The controller options live with the terminal now, one subject per
    # section; General keeps only how the application starts.
    page._ensure_section("console")
    labels = {label.text() for label in page.findChildren(QLabel)}

    assert "Automatic gamepad keypad" in labels
    assert "On-screen keypad" not in labels
    assert "Show keypad automatically" not in labels


def test_unified_keypad_switch_updates_both_runtime_contracts(qtbot, tmp_path):
    settings = _settings(tmp_path)
    page = SettingsPage(object(), settings_service=SettingsService(), activity_service=ActivityService(), app_settings=settings)
    qtbot.addWidget(page)
    enabled_events = []
    automatic_events = []
    page.gamepad_keypad_changed.connect(enabled_events.append)
    page.gamepad_keypad_auto_show_changed.connect(automatic_events.append)

    page._unified_gamepad_keypad_changed(False)

    assert settings.value("settings/gamepad_keypad_auto_show") == "false"
    assert enabled_events == [False]
    assert automatic_events == [False]


def test_unified_keypad_copy_is_localized_in_every_language():
    sources = (
        "Automatic gamepad keypad",
        "Show the on-screen keypad automatically when a gamepad focuses an editable field.",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language) != source for source in sources), language


def test_settings_dialog_uses_the_settings_shell_as_its_window_boundary(qtbot, tmp_path):
    dialog = SettingsDialog(object(), settings_service=SettingsService(), activity_service=ActivityService(), app_settings=_settings(tmp_path))
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    assert dialog.layout().contentsMargins().left() == 0
    assert dialog.layout().contentsMargins().top() == 0
    assert dialog.page.size() == dialog.contentsRect().size()
    assert dialog.findChild(QFrame, "ControlDialogCard") is None
    assert dialog.close_button.parentWidget() is dialog
