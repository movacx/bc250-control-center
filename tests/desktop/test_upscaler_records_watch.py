"""A game OptiScaler Client or HelixSR changes shows on the Upscaling tab at once.

The client is a program of its own; its game list and records were noticed
only on the next poll, after two caches ran out. They are watched instead.
"""

from __future__ import annotations

import json

from PyQt6.QtWidgets import QStackedWidget, QWidget

from frontends.desktop.app import ControlCenterWindow


class _Owner(QWidget):
    """Just what the watch needs of the main window."""

    _watch_upscaler_records = ControlCenterWindow._watch_upscaler_records
    _upscaler_records_changed = ControlCenterWindow._upscaler_records_changed

    def __init__(self) -> None:
        super().__init__()
        self.stack = QStackedWidget(self)
        self.extras_page = QWidget()
        self.stack.addWidget(self.extras_page)
        self.refreshes = 0

    def _tools_changed(self) -> None:
        self.refreshes += 1


def test_a_change_by_the_client_reads_the_tools_again(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    records = tmp_path / "config" / "OptiscalerClient-BC250"
    (records / "BC250" / "games").mkdir(parents=True)
    (records / "games.json").write_text("[]")
    owner = _Owner()
    qtbot.addWidget(owner)

    owner._watch_upscaler_records()
    (records / "BC250" / "games" / ("a" * 64)).mkdir()
    qtbot.waitUntil(lambda: owner.refreshes == 1, timeout=3000)

    # The new game's folder is watched now, and the list stays watched
    # after the client replaces it in one go.
    (records / "BC250" / "games" / ("a" * 64) / "receipt.json").write_text("{}")
    qtbot.waitUntil(lambda: owner.refreshes == 2, timeout=3000)
    staged = records / "games.json.tmp"
    staged.write_text(json.dumps([{"Name": "x"}]))
    staged.replace(records / "games.json")
    qtbot.waitUntil(lambda: owner.refreshes == 3, timeout=3000)


def test_nothing_is_read_while_another_page_is_on_screen(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    records = tmp_path / "config" / "OptiscalerClient-BC250"
    records.mkdir(parents=True)
    (records / "games.json").write_text("[]")
    owner = _Owner()
    qtbot.addWidget(owner)
    other = QWidget()
    owner.stack.addWidget(other)
    owner.stack.setCurrentWidget(other)

    owner._watch_upscaler_records()
    (records / "games.json").write_text("[1]")
    qtbot.wait(900)
    assert owner.refreshes == 0
