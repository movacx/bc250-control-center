from frontends.desktop.pages.settings import RepositoriesDialog, settings_stylesheet
from frontends.desktop.theme import application_stylesheet


def test_repositories_dialog_owns_a_theme_aware_surface(qtbot):
    dialog = RepositoriesDialog()
    qtbot.addWidget(dialog)

    for mode, expected_surface in (("light", "#FFFFFF"), ("dark", "#171717")):
        application_stylesheet(mode)
        stylesheet = settings_stylesheet()
        assert "QDialog[settingsPage='true']" in stylesheet
        assert f"background:{expected_surface}" in stylesheet
