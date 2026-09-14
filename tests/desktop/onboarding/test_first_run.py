"""When the welcome screen is owed, and when it has been paid.

The flag records that the offer was made, not that it was taken: skipping the
whole thing still counts, because a panel that came back every launch until it
was filled in would be a gate rather than a welcome.
"""

from PyQt6.QtCore import QSettings

from frontends.desktop.onboarding import (
    ONBOARDING_VERSION,
    SETTINGS_KEY,
    completed_version,
    first_run_pending,
    mark_first_run_done,
)


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


def test_a_fresh_install_is_owed_the_welcome(tmp_path):
    assert first_run_pending(_settings(tmp_path))


def test_marking_it_done_settles_the_debt(tmp_path):
    settings = _settings(tmp_path)

    mark_first_run_done(settings)

    assert not first_run_pending(settings)
    assert completed_version(settings) == ONBOARDING_VERSION


def test_an_older_answer_is_asked_again(tmp_path):
    """Bumping the version is how a changed set of questions gets asked."""
    settings = _settings(tmp_path)
    settings.setValue(SETTINGS_KEY, ONBOARDING_VERSION - 1)

    assert first_run_pending(settings)


def test_a_corrupted_flag_is_read_as_never_answered(tmp_path):
    """QSettings hands back whatever is in the file, including nonsense."""
    settings = _settings(tmp_path)
    settings.setValue(SETTINGS_KEY, "sí")

    assert completed_version(settings) == 0
    assert first_run_pending(settings)
