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


def test_the_search_filters_the_repositories_and_the_count(qtbot):
    from frontends.desktop.pages.settings import OFFICIAL_REPOSITORIES

    dialog = RepositoriesDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    total = len(OFFICIAL_REPOSITORIES)
    assert sum(row.isVisible() for row, _ in dialog._rows) == total
    name, repository, _url = OFFICIAL_REPOSITORIES[1]

    dialog.search.setText(repository.upper())
    assert [row.isVisible() for row, _ in dialog._rows].count(True) >= 1
    assert dialog._rows[1][0].isVisible()
    assert dialog._count.text() == str(sum(row.isVisible() for row, _ in dialog._rows))
    assert dialog._no_match.isHidden()

    dialog.search.setText("zzzz-no-such-repository")
    assert not any(row.isVisible() for row, _ in dialog._rows)
    assert dialog._count.text() == "0" and dialog._no_match.isVisible()

    dialog.search.clear()
    assert sum(row.isVisible() for row, _ in dialog._rows) == total
    assert dialog._count.text() == str(total)


def test_an_archived_repository_says_so_and_can_be_searched_for(qtbot):
    from frontends.desktop.pages.settings import (
        ARCHIVED_REPOSITORIES,
        OFFICIAL_REPOSITORIES,
    )

    assert ARCHIVED_REPOSITORIES <= {repository for _name, repository, _url in OFFICIAL_REPOSITORIES}
    dialog = RepositoriesDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.search.setText("archived")
    shown = [index for index, (row, _text) in enumerate(dialog._rows) if row.isVisible()]
    assert [OFFICIAL_REPOSITORIES[index][1] for index in shown] == sorted(ARCHIVED_REPOSITORIES)
    assert dialog._count.text() == str(len(ARCHIVED_REPOSITORIES))
