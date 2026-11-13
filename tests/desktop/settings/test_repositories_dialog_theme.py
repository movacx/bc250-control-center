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
    assert sum(row.isVisible() for row, _ in dialog.repositories._rows) == total
    name, repository, _url = OFFICIAL_REPOSITORIES[1]

    dialog.repositories.search.setText(repository.upper())
    assert [row.isVisible() for row, _ in dialog.repositories._rows].count(True) >= 1
    assert dialog.repositories._rows[1][0].isVisible()
    assert dialog.repositories._no_match.isHidden()

    dialog.repositories.search.setText("zzzz-no-such-repository")
    assert not any(row.isVisible() for row, _ in dialog.repositories._rows)
    assert dialog.repositories._no_match.isVisible()

    dialog.repositories.search.clear()
    assert sum(row.isVisible() for row, _ in dialog.repositories._rows) == total


def test_an_archived_repository_says_so_and_can_be_searched_for(qtbot):
    from frontends.desktop.pages.settings import (
        ARCHIVED_REPOSITORIES,
        OFFICIAL_REPOSITORIES,
    )

    assert ARCHIVED_REPOSITORIES <= {repository for _name, repository, _url in OFFICIAL_REPOSITORIES}
    dialog = RepositoriesDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.repositories.search.setText("archived")
    shown = [index for index, (row, _text) in enumerate(dialog.repositories._rows) if row.isVisible()]
    assert [OFFICIAL_REPOSITORIES[index][1] for index in shown] == sorted(ARCHIVED_REPOSITORIES)


def test_every_upstream_the_application_uses_is_credited():
    """HelixSR, DirectMesh and others were installed but not listed (Discord)."""
    import re
    from pathlib import Path

    from frontends.desktop.pages.settings import OFFICIAL_REPOSITORIES

    root = Path(__file__).resolve().parents[3]
    listed = {repository.split("/tree/")[0].lower() for _name, repository, _url in OFFICIAL_REPOSITORIES}
    # Sources the application only reads or links to, not tools it installs.
    not_tools = {"nvidia/dlss", "resurrecting-open-source-projects/stress"}
    pattern = re.compile(r"https://(?:github|gitlab)\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
    used = set()
    for folder in ("src", "privileged"):
        for path in (root / folder).rglob("*.py"):
            for slug in pattern.findall(path.read_text(encoding="utf-8", errors="replace")):
                used.add(slug.removesuffix(".git").lower())
    missing = sorted(used - listed - not_tools)
    assert not missing, missing
