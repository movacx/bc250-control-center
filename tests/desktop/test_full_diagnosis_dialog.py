"""The full diagnosis, readable in the application: sections, tabs, search, copy and save."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from frontends.desktop.components import full_diagnosis_dialog as module
from frontends.desktop.components.full_diagnosis_dialog import FullDiagnosisDialog, FullDiagnosisView, section_group

SECTIONS = [
    ("Kernel", "6.18.7-cachyos-bc250\nBC250 kernel"),
    ("Previous boot", "previous boot ended cleanly"),
    ("Black box", "[stopped normally]\n12:00:01.250 2000Mhz busy=99%"),
    ("Kernel log: GPU and crashes", "amdgpu: ring gfx_0.0.0 timeout"),
    ("Services", "cyan-skillfish-governor-smu.service active"),
    ("Boot and deployments", "ostree=/ostree/boot.1/default"),
    ("Packages", "mesa 26.2.5\nkernel 7.2.9"),
    ("Last workflow logs", "== Preparing ==\nERROR: /var has only 78 MB free"),
]


@pytest.fixture()
def dialog(qtbot):
    widget = FullDiagnosisView(None, collect=lambda: list(SECTIONS))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitUntil(lambda: len(widget._sections) == len(SECTIONS), timeout=3000)
    return widget


@pytest.mark.parametrize("title, group", [
    ("Kernel", "hardware"), ("Previous boot", "hardware"), ("Black box", "hardware"),
    ("sensors", "hardware"), ("GPU device", "hardware"), ("Services", "hardware"),
    ("Kernel log: GPU and crashes", "logs"), ("Kernel log (unfiltered)", "logs"),
    ("BC-250 services and their journals", "logs"), ("Last workflow logs", "logs"), ("Helper logs", "logs"),
    ("Packages", "system"), ("Configuration files", "system"), ("Boot and deployments", "system"),
    ("Something a future release adds", "system"),
])
def test_each_section_belongs_to_one_tab(title, group):
    assert section_group(title) == group


def test_the_dialog_wraps_the_same_view_and_can_be_closed(qtbot):
    window = FullDiagnosisDialog(None, collect=lambda: list(SECTIONS))
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: len(window.view._sections) == len(SECTIONS), timeout=3000)
    assert window.view.summary.startswith("Diagnosis · 8 sections")
    window.close_button.click()
    assert not window.isVisible()


def test_section_titles_are_the_ones_the_report_uses_in_every_language(dialog):
    """Both sides read the same words: no translated title the maintainer's page does not have."""
    from frontends.desktop.i18n import set_language

    set_language("es")
    try:
        section = type(dialog._sections[0])("Black box", "x")
        assert "Black box" in section.toggle.text() and "Caja negra" not in section.toggle.text()
    finally:
        set_language("en")


def test_the_count_and_size_are_kept_but_not_drawn_as_a_title(dialog):
    assert dialog.summary.startswith("Diagnosis · 8 sections · ") and dialog.summary.endswith(" KB")
    assert dialog.summary in dialog.search.toolTip()
    assert not hasattr(dialog, "heading")


def test_sections_start_closed_and_open_with_their_text(dialog):
    section = dialog._sections[0]
    assert section.body.isHidden()
    assert section.toggle.text().startswith("▶ Kernel (")
    section.toggle.click()
    assert not section.body.isHidden()
    assert section.toggle.text().startswith("▼ Kernel (")
    assert "BC250 kernel" in section.body.toPlainText()


def test_the_tabs_filter_the_sections(dialog):
    names = lambda: [section.title for section in dialog.visible_sections()]  # noqa: E731
    assert len(names()) == 8
    dialog.tab_buttons["logs"].click()
    assert names() == ["Kernel log: GPU and crashes", "Last workflow logs"]
    dialog.tab_buttons["hardware"].click()
    assert names() == ["Kernel", "Previous boot", "Black box", "Services"]
    dialog.tab_buttons["system"].click()
    assert names() == ["Boot and deployments", "Packages"]
    assert dialog.tab_buttons["system"].isChecked() and not dialog.tab_buttons["logs"].isChecked()


def test_search_looks_in_the_text_too_and_opens_what_it_finds(dialog):
    dialog.search.setText("78 MB free")
    found = dialog.visible_sections()
    assert [section.title for section in found] == ["Last workflow logs"]
    assert not found[0].body.isHidden()


def test_a_search_with_no_match_says_so(dialog):
    dialog.search.setText("no such text anywhere")
    assert dialog.visible_sections() == []
    assert "No section matches" in dialog.status.text()
    dialog.search.setText("")
    assert dialog.status.text() == ""


def test_expand_and_collapse_all_act_on_what_is_shown(dialog):
    dialog.tab_buttons["logs"].click()
    dialog.expand_button.click()
    assert all(not s.body.isHidden() for s in dialog.visible_sections())
    assert dialog._sections[0].body.isHidden()  # hardware, not shown: untouched
    dialog.collapse_button.click()
    assert all(s.body.isHidden() for s in dialog.visible_sections())


def test_copy_all_puts_the_whole_diagnosis_on_the_clipboard(dialog):
    dialog.copy_button.click()
    text = QApplication.clipboard().text()
    assert text.startswith("== Kernel ==\n6.18.7-cachyos-bc250")
    assert "== Packages ==" in text and "ERROR: /var has only 78 MB free" in text


def test_save_writes_the_same_text_to_the_chosen_file(dialog, tmp_path, monkeypatch):
    target = tmp_path / "diag.txt"
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "Text (*.txt)"))
    dialog.save_button.click()
    assert target.read_text(encoding="utf-8") == dialog.text()


def test_cancelling_the_save_dialog_writes_nothing(dialog, tmp_path, monkeypatch):
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    dialog.save_button.click()
    assert list(tmp_path.iterdir()) == []


def test_a_failed_collection_is_said_and_can_be_tried_again(qtbot):
    attempts = []

    def collect():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("journal unreadable")
        return list(SECTIONS)

    widget = FullDiagnosisView(None, collect=collect)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitUntil(lambda: "journal unreadable" in widget.status.text(), timeout=3000)
    assert not widget.copy_button.isEnabled()
    qtbot.waitUntil(lambda: widget.refresh_button.isEnabled(), timeout=3000)
    widget.refresh_button.click()
    qtbot.waitUntil(lambda: len(widget._sections) == len(SECTIONS), timeout=3000)
    assert widget.copy_button.isEnabled()


def test_refreshing_replaces_the_sections_instead_of_adding_to_them(dialog, qtbot):
    dialog.refresh_button.click()
    qtbot.waitUntil(lambda: dialog.refresh_button.isEnabled() and len(dialog._sections) == len(SECTIONS), timeout=3000)
    assert dialog.sections_layout.count() == len(SECTIONS) + 1  # the sections and the closing stretch


def test_settings_diagnostics_has_a_button_that_opens_it(monkeypatch):
    import inspect
    from types import SimpleNamespace

    from bc250cc.infrastructure.report_attachments import collect_attachments
    from frontends.desktop.pages import settings as settings_module

    opened = []

    class FakeDialog:
        def __init__(self, parent, *, collect):
            opened.append(collect)

        def exec(self):
            return 0

    monkeypatch.setattr("frontends.desktop.components.full_diagnosis_dialog.FullDiagnosisDialog", FakeDialog)
    settings_module.SettingsPage._view_full_diagnosis(SimpleNamespace())
    # It shows what a report attaches: the same collection, not a shorter one.
    assert opened == [collect_attachments]
    builder = inspect.getsource(settings_module.SettingsPage._build_diagnostics_page)
    assert '"View full diagnosis", self._view_full_diagnosis' in builder
    assert "self.diagnostics_full_button," in builder


def test_the_terminal_prints_the_same_sections_with_dash_dash_full(monkeypatch, capsys):
    from frontends import cli

    monkeypatch.setattr(
        "bc250cc.infrastructure.report_attachments.collect_attachments", lambda: list(SECTIONS[:2])
    )
    assert cli.main(["diagnose", "--full"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("== Kernel ==\n6.18.7-cachyos-bc250")
    assert "== Previous boot ==\nprevious boot ended cleanly" in out


# ------------------------------------------------- the text boxes can be stretched

def _drag(qtbot, grip, pixels):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    start = QPoint(grip.width() // 2, grip.height() // 2)
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(grip, start + QPoint(0, pixels))
    # QTest does not hold the button while moving: say so, as a real drag does.
    qtbot.wait(5)
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(0, pixels))


def _open_first(dialog):
    section = dialog._sections[0]
    section.set_open(True)
    return section


def test_a_section_has_a_grip_only_while_it_is_open(dialog):
    section = dialog._sections[0]
    assert section.grip.isHidden()
    section.set_open(True)
    assert not section.grip.isHidden()
    section.set_open(False)
    assert section.grip.isHidden()


def test_dragging_the_grip_down_makes_the_box_taller_and_up_shorter(dialog, qtbot):
    section = _open_first(dialog)
    start = section.body.height()
    section.grip.pressed.emit()
    section.grip.dragged.emit(140)
    assert section.body.height() == start + 140
    section.grip.dragged.emit(-60)
    assert section.body.height() == start - 60


def test_the_box_cannot_be_dragged_smaller_than_a_few_lines_or_absurdly_tall(dialog):
    from frontends.desktop.components.full_diagnosis_dialog import MAX_HEIGHT, MIN_HEIGHT

    section = _open_first(dialog)
    section.grip.pressed.emit()
    section.grip.dragged.emit(-5000)
    assert section.body.height() == MIN_HEIGHT
    section.grip.dragged.emit(100000)
    assert section.body.height() == MAX_HEIGHT


def test_a_new_drag_starts_from_where_the_box_is_now(dialog):
    section = _open_first(dialog)
    start = section.body.height()
    section.grip.pressed.emit()
    section.grip.dragged.emit(100)
    section.grip.pressed.emit()  # let go, take hold again
    section.grip.dragged.emit(50)
    assert section.body.height() == start + 150


def test_the_mouse_on_the_grip_really_drags_it(dialog, qtbot):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    dialog.resize(900, 700)
    section = _open_first(dialog)
    qtbot.wait(30)
    start = section.body.height()
    grip = section.grip
    origin = QPoint(grip.width() // 2, grip.height() // 2)
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, origin)
    event_point = origin + QPoint(0, 90)
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPointF

    move = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(event_point), QPointF(grip.mapToGlobal(event_point)),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    grip.mouseMoveEvent(move)
    assert section.body.height() == start + 90
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, event_point)


def test_double_click_fits_the_box_to_its_text_and_again_goes_back(dialog):
    from frontends.desktop.components.full_diagnosis_dialog import DEFAULT_HEIGHT

    section = _open_first(dialog)
    section.body.setPlainText("\n".join(f"line {n}" for n in range(60)))
    assert section.fit_height() > DEFAULT_HEIGHT
    section.grip.double_clicked.emit()
    assert section.body.height() == section.fit_height()
    section.grip.double_clicked.emit()
    assert section.body.height() == DEFAULT_HEIGHT


def test_a_short_text_fits_in_less_than_the_usual_box(dialog):
    from frontends.desktop.components.full_diagnosis_dialog import DEFAULT_HEIGHT

    section = _open_first(dialog)
    section.body.setPlainText("one line")
    section.grip.double_clicked.emit()
    assert section.body.height() < DEFAULT_HEIGHT


def test_each_box_has_its_own_height(dialog):
    first, second = dialog._sections[0], dialog._sections[1]
    first.set_open(True)
    second.set_open(True)
    first.set_body_height(500)
    assert second.body.height() != 500


def test_there_is_no_title_or_explanation_line_only_a_tooltip(dialog):
    from PyQt6.QtWidgets import QLabel

    assert "problem report attaches" in dialog.search.toolTip()
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not [text for text in texts if "problem report attaches" in text or "sections" in text.lower()]


def test_the_status_line_takes_no_room_while_it_has_nothing_to_say(dialog):
    assert dialog.status.text() == "" and dialog.status.isHidden()
    dialog.search.setText("no such text anywhere")
    assert not dialog.status.isHidden()
    dialog.search.setText("")
    assert dialog.status.isHidden()


def test_the_message_sits_above_the_list_not_below_it(dialog):
    layout = dialog.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget() is not None]
    assert order.index(dialog.status) < order.index(dialog.scroll)


def test_the_tooltip_says_redaction_cannot_know_everything_and_to_read_it_first(dialog):
    tip = dialog.search.toolTip()
    assert "Read it before sharing it in public" in tip
    assert "Serial numbers" in tip and "Steam ids" in tip


# ------------------------------------------------------- light and dark, and switching live

@pytest.fixture()
def theme():
    """Let a test switch the theme and always put it back."""
    from frontends.desktop.theme import ACTIVE_ACCENT, ACTIVE_DENSITY, ACTIVE_SCALE, ACTIVE_STYLE, ACTIVE_THEME, configure_theme

    saved = (ACTIVE_THEME, ACTIVE_ACCENT, ACTIVE_DENSITY, ACTIVE_SCALE, ACTIVE_STYLE)
    yield configure_theme
    configure_theme(*saved)


def test_every_control_of_the_view_has_a_look_of_its_own(dialog):
    """Not "ghostAction": that one is styled only inside Settings, so elsewhere it followed the system palette."""
    from PyQt6.QtWidgets import QLineEdit, QPushButton

    buttons = [button for button in dialog.findChildren(QPushButton)]
    assert buttons
    assert all(button.property("diagButton") for button in buttons if button.property("diagTab") is None
               and button.property("diagToggle") is None)
    assert not any(button.property("ghostAction") for button in buttons)
    assert all(edit.property("diagSearch") for edit in dialog.findChildren(QLineEdit))


def test_the_sheet_carries_the_colours_of_the_theme_it_was_made_in(theme):
    from frontends.desktop.components import full_diagnosis_dialog as module
    from frontends.desktop.theme import COLORS

    theme("dark", "blue", "comfortable", 100, "formal")
    dark = module._stylesheet()
    assert COLORS["text"].lower() in dark.lower()
    dark_text = COLORS["text"]
    theme("light", "blue", "comfortable", 100, "formal")
    light = module._stylesheet()
    assert COLORS["text"].lower() in light.lower() and COLORS["text"] != dark_text


def test_the_view_takes_the_new_colours_when_the_theme_changes_under_it(qtbot, theme):
    """The reported case: opened in dark, switched to light, pale text on a pale page."""
    from frontends.desktop.theme import COLORS

    theme("dark", "blue", "comfortable", 100, "formal")
    view = FullDiagnosisView(None, collect=lambda: list(SECTIONS))
    qtbot.addWidget(view)
    view.show()
    qtbot.waitUntil(lambda: len(view._sections) == len(SECTIONS), timeout=3000)
    dark_text = COLORS["text"]
    assert dark_text.lower() in view.styleSheet().lower()

    theme("light", "blue", "comfortable", 100, "formal")
    assert COLORS["text"] != dark_text
    assert COLORS["text"].lower() not in view.styleSheet().lower()  # still the old one
    view.apply_appearance()
    assert COLORS["text"].lower() in view.styleSheet().lower()
    assert dark_text.lower() not in view.styleSheet().lower()


def test_the_black_box_page_passes_the_theme_change_on_to_the_diagnosis(qtbot, theme):
    from frontends.desktop.pages.blackbox import BlackBoxPage
    from frontends.desktop.theme import COLORS

    class Controller:
        def blackbox_estado(self, filas=None):
            return {"supported": True, "running": False, "autostart": {"supported": False}, "directory": "/x",
                    "state": "none", "rows": []}

        def diagnostico_completo(self):
            return list(SECTIONS)

    theme("dark", "blue", "comfortable", 100, "formal")
    page = BlackBoxPage(Controller())
    qtbot.addWidget(page)
    page.show()
    page.diagnosis_button.click()
    qtbot.waitUntil(lambda: len(page.diagnosis_view._sections) == len(SECTIONS), timeout=3000)
    old = COLORS["text"]
    theme("light", "blue", "comfortable", 100, "formal")
    page.apply_appearance()
    sheet = page.diagnosis_view.styleSheet().lower()
    assert COLORS["text"].lower() in sheet and old.lower() not in sheet
