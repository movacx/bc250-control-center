"""Additional settings > Upscaling: a trash button takes a game off the table.

Nothing in the game changes: it is a view setting. A game with an upscaler
in it is asked about first, and Add game › Show hidden games brings every
hidden row back.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QPushButton

# dashboard_widgets first: it is what imports preparation_render in the app.
from frontends.desktop.components import (  # noqa: F401
    dashboard_widgets,
    page_widgets,
    preparation_render,
)
from tests.desktop.dashboard.test_helixsr_card import _ready, _sidebar, _state

GAMES = [
    {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
    {"appid": "2", "kind": "optiscaler", "name": "Plain", "state": "available", "files": []},
]


def _trash(sidebar, key):
    rows = [widgets for _name, widgets in sidebar.upscaling_games._rows]
    row = next(widgets for widgets in rows if any(w.isAncestorOf(sidebar.upscaling_games.controls[key][0]) for w in widgets))
    return next(button for button in row[0].findChildren(QPushButton) if button.property("gameHide"))


def _fresh(monkeypatch):
    store = {}

    class Store:
        def value(self, key, default=None):
            return store.get(key, default)

        def setValue(self, key, value):  # noqa: N802 - QSettings API
            store[key] = value

        def remove(self, key):
            store.pop(key, None)

    monkeypatch.setattr(preparation_render, "_hidden_store", Store)
    return store


def test_every_row_starts_with_a_trash_button(monkeypatch):
    _fresh(monkeypatch)
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready(GAMES)))
    for key in ("1", "2"):
        assert _trash(sidebar, key).toolTip() in {"Remove from this list", "Quitar de esta lista"}


def test_a_plain_game_leaves_at_once_and_comes_back_from_add_game(monkeypatch):
    store = _fresh(monkeypatch)
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready(GAMES)))
    _trash(sidebar, "2").click()
    assert store[preparation_render.HIDDEN_GAMES_KEY] == ["2"]
    assert "2" not in sidebar.upscaling_games.controls and "1" in sidebar.upscaling_games.controls
    sidebar._show_hidden_upscaling_games()
    assert "2" in sidebar.upscaling_games.controls


def test_a_game_with_an_upscaler_is_asked_about_first(monkeypatch):
    store = _fresh(monkeypatch)
    answers = []

    class Dialog:
        def __init__(self, *args, **kwargs):
            answers.append(args)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(page_widgets, "ConfirmDialog", Dialog)
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready(GAMES)))
    _trash(sidebar, "1").click()
    assert answers and preparation_render.HIDDEN_GAMES_KEY not in store
    assert "1" in sidebar.upscaling_games.controls
