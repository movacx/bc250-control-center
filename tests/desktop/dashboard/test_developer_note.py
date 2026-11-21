"""The footer's note: support paused while the developer's board is broken.

It sits between Report a problem and Ko-fi, glows until it is read once,
and only mentions that Ko-fi is on the dashboard: it asks for nothing.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel

from frontends.desktop.components import developer_note
from frontends.desktop.components.dashboard_footer import DashboardFooter
from frontends.desktop.components.developer_note import DeveloperNoteDialog


def test_the_note_sits_between_report_and_kofi(qtbot):
    footer = DashboardFooter()
    qtbot.addWidget(footer)
    order = [footer.layout.itemAt(i).widget() for i in range(footer.layout.count())]
    assert order.index(footer.note_button) == order.index(footer.report_button) + 1
    assert order.index(footer.support_button) == order.index(footer.note_button) + 1


def test_the_note_says_why_when_and_how_to_help(qtbot):
    dialog = DeveloperNoteDialog()
    qtbot.addWidget(dialog)
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "2027" in text and "@_movacx" in text and "BC-250" in text
    dialog.copy_button.click()
    assert QApplication.clipboard().text() == "@_movacx"
    # No coffee button in the note: Ko-fi stays on the dashboard.
    assert not hasattr(dialog, "kofi_button")
    assert "Ko-fi" in text


def test_reading_the_note_stops_the_glow(monkeypatch, qtbot):
    store = {}
    monkeypatch.setattr(developer_note, "application_settings", lambda: type("S", (), {
        "value": lambda self, key, default=None: store.get(key, default),
        "setValue": lambda self, key, value: store.__setitem__(key, value),
    })())
    assert not developer_note.note_seen()
    developer_note.mark_note_seen()
    assert developer_note.note_seen()


def test_a_narrow_window_folds_telegram_and_a_wide_one_brings_it_back(qtbot):
    from frontends.desktop.pages.dashboard import DashboardPage
    from frontends.desktop.theme import application_stylesheet

    page = DashboardPage(object())
    qtbot.addWidget(page)
    try:
        page.setStyleSheet(application_stylesheet("dark", scale=150))
        page.resize(360, 800)
        page.show()
        qtbot.wait(100)
        assert page.telegram_button.isHidden() and not page.footer.note_button.isHidden()
        page.resize(1400, 800)
        qtbot.waitUntil(lambda: not page.telegram_button.isHidden(), timeout=2000)
    finally:
        application_stylesheet("light", scale=100)


def test_the_profile_button_opens_the_discord_profile(monkeypatch, qtbot):
    from frontends.desktop.core import external_links

    opened = []
    monkeypatch.setattr(external_links, "open_external_url", lambda url: (opened.append(url) or True, ""))
    dialog = DeveloperNoteDialog()
    qtbot.addWidget(dialog)
    dialog.profile_button.click()
    assert opened == ["https://discord.com/users/719291715369959445"]
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "HDMI" in text and "Caps Lock" in text


def test_the_note_reads_like_a_letter_with_a_postscript(qtbot):
    dialog = DeveloperNoteDialog()
    qtbot.addWidget(dialog)
    labels = dialog.findChildren(QLabel)
    # No section headings: just paragraphs, the Discord box and a P.S.
    assert not [label for label in labels if label.objectName() == "DialogSectionLabel"]
    paragraphs = [label.text() for label in labels if label.objectName() == "DialogBody"]
    assert paragraphs[-1].startswith("P.S.")
    assert "Cyan" in paragraphs[-1] and "Known errors" in paragraphs[-1]


def test_kofi_beats_the_note_rings_and_the_switch_stills_both(qtbot):
    from PyQt6.QtCore import QAbstractAnimation

    from frontends.desktop.components.dashboard_footer import (
        _BroadcastButton,
        _HeartbeatButton,
    )

    footer = DashboardFooter()
    qtbot.addWidget(footer)
    footer.set_report_glow(True)
    footer.show()
    qtbot.waitExposed(footer)
    note, kofi = footer.note_button, footer.support_button
    # Three different motions: the report button glows, the note rings, Ko-fi beats.
    assert isinstance(note, _BroadcastButton) and isinstance(kofi, _HeartbeatButton)
    assert not hasattr(note, "_outline") and not hasattr(kofi, "_outline")
    support = footer.report_button
    assert type(support).__name__ == "_SupportButton" and support.glowing()
    support._set("_ping", 0.5)
    assert not support.grab().isNull()
    for button in (note, kofi):
        button.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        assert button.glowing() and button.play()
        assert button.motion.state() == QAbstractAnimation.State.Running
    sizes = (note.size(), kofi.size())
    note._set("_angle", -7.0)
    note._set("_wave", 0.5)
    kofi._set("_scale", 1.22)
    assert not note.grab().isNull() and not kofi.grab().isNull()
    assert (note.size(), kofi.size()) == sizes
    footer.set_report_glow(False)
    for button in (footer.report_button, note, kofi):
        assert not button.glowing()
    for button in (note, kofi):
        assert button.motion.state() == QAbstractAnimation.State.Stopped and button._at_rest()


def _seen_store(monkeypatch, seen=False):
    store = {developer_note.SEEN_KEY: "true"} if seen else {}
    monkeypatch.setattr(developer_note, "application_settings", lambda: type("S", (), {
        "value": lambda self, key, default=None: store.get(key, default),
        "setValue": lambda self, key, value: store.__setitem__(key, value),
    })())
    return store


def test_the_note_opens_by_itself_only_once(monkeypatch, qtbot):
    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.pages.dashboard import DashboardPage

    store = _seen_store(monkeypatch)
    opened = []
    monkeypatch.setattr(DeveloperNoteDialog, "open", lambda self: opened.append(self))
    window = QWidget()
    qtbot.addWidget(window)
    page = DashboardPage(object())
    page.setParent(window)
    window.show()
    qtbot.waitExposed(window)
    page.present_developer_note_once(delay_ms=0)
    qtbot.waitUntil(lambda: len(opened) == 1, timeout=2000)
    assert store[developer_note.SEEN_KEY] == "true"
    page.present_developer_note_once(delay_ms=0)
    qtbot.wait(50)
    assert len(opened) == 1


def test_the_note_waits_for_the_welcome_screen_and_the_tour(monkeypatch, qtbot):
    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.pages.dashboard import DashboardPage

    store = _seen_store(monkeypatch)
    opened = []
    monkeypatch.setattr(DeveloperNoteDialog, "open", lambda self: opened.append(self))

    class Window(QWidget):
        touring = True

        def is_presenting_overlay(self):
            return self.touring

    window = Window()
    qtbot.addWidget(window)
    page = DashboardPage(object())
    page.setParent(window)
    window.show()
    qtbot.waitExposed(window)
    page.present_developer_note_once(delay_ms=0)
    qtbot.wait(50)
    assert not opened and developer_note.SEEN_KEY not in store
    window.touring = False
    page.present_developer_note_once(delay_ms=0)
    qtbot.waitUntil(lambda: len(opened) == 1, timeout=2000)


def test_the_animations_take_turns_at_random_one_at_a_time(qtbot):
    import random

    footer = DashboardFooter()
    qtbot.addWidget(footer)
    footer.set_report_glow(True)
    footer.show()
    qtbot.waitExposed(footer)
    footer._turns.stop()  # the test takes the turns itself
    footer._random = random.Random(7)
    animated = [footer.repositories_button, footer.contact_button, footer.telegram_button,
                footer.report_button, footer.note_button, footer.support_button]
    for button in animated:
        # Offscreen, the pointer rests on the first button and would pause it.
        button.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
    order = []
    for _ in range(60):
        chosen = footer.take_turn()
        assert chosen is not None
        # One at a time: nobody else may start while it moves.
        assert footer.take_turn() is None
        assert [button for button in animated if button.playing()] == [chosen]
        order.append(chosen)
        chosen.motion.setCurrentTime(chosen.motion.duration())  # let it finish
        qtbot.waitUntil(lambda button=chosen: not button.playing(), timeout=1000)
    assert set(order) == set(animated)
    assert all(first is not second for first, second in zip(order, order[1:]))
    assert order[:6] != animated  # not left to right any more
    # The update badge keeps its own loop and never takes a turn.
    assert footer.update_button not in order
    footer.telegram_button._set("_dx", 0.6)
    footer.contact_button._set("_sx", 1.18)
    footer.repositories_button._set("_dy", -0.26)
    for button in animated:
        assert not button.grab().isNull()
    footer.set_report_glow(False)
    assert footer.take_turn() is None
    assert all(button._at_rest() and not button.glowing() for button in animated)
