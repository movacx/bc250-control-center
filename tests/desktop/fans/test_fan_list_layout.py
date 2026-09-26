"""The fan page: the fan as a list on the left, the thermal detail on the right."""

from __future__ import annotations

from dataclasses import replace

import pytest
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from frontends.desktop.pages.fans import (
    DEFAULT_FAN_PROFILES,
    FanCurvePlot,
    FanProfileCard,
    FansPage,
    load_fan_profiles,
    save_fan_profile,
)


class _Controller:
    pass


@pytest.fixture
def page(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.resize(1600, 1000)
    page.show()
    qtbot.wait(5)
    return page


def test_the_duty_is_a_number_and_a_gauge(page):
    page._show_duty(64)
    assert (page.duty_reading.value.text(), page.duty_reading.unit.text()) == ("64", "%")
    assert page.duty_reading.bar.fraction == pytest.approx(0.64)
    page._show_duty(None)
    assert page.duty_reading.bar.fraction is None


def test_the_thermal_detail_keeps_its_single_list(page):
    assert list(page.thermal_detail.readings) == [
        "gpu", "cpu", "driver", "next", "headroom", "board", "vrm", "nvme", "rpm_range", "owner",
    ]
    assert page.cooling_card.isAncestorOf(page.thermal_detail)
    assert page.cooling_card.isAncestorOf(page.system_control_panel)
    assert not hasattr(page, "history_chart")


def test_the_fan_list_opens_the_control_card(page):
    assert page.control_card.isAncestorOf(page.speed_reading)
    assert page.control_card.isAncestorOf(page.mode_reading)
    assert not page.selected_mode.isVisible()
    assert not page.selected_live_rpm.isVisible()
    # Action buttons carry words only, and the one left says what it does.
    for button in (page.restore_auto_button, page.apply_pwm_button,
                   page.save_curve_button, page.apply_curve_button):
        assert button.icon().isNull(), button.text()
    assert page.restore_auto_button.text() == "Return to BIOS control"
    assert "BIOS" in page.restore_auto_button.toolTip()
    assert not hasattr(page, "use_live_button")


def test_three_profiles_stage_their_speed_and_keep_an_edit(page, tmp_path):
    cards = page.manual_preset_buttons
    assert [card.profile.key for card in cards] == ["quiet", "balanced", "maximum"]
    cards[0].selected.emit(cards[0].profile)
    assert page._staged_pwm_percent == 45
    assert cards[0].isChecked() and not cards[1].isChecked()

    cards[0].begin_edit()
    cards[0]._name_edit.setText("Night")
    cards[0]._percent_spin.setValue(38)
    cards[0]._commit()
    # The chosen profile's new speed is what is staged now, and it is kept.
    assert page._staged_pwm_percent == 38
    assert load_fan_profiles()[0].name == "Night"
    assert load_fan_profiles()[0].percent == 38

    settings = QSettings(str(tmp_path / "ui.conf"), QSettings.Format.IniFormat)
    save_fan_profile(2, DEFAULT_FAN_PROFILES[2].__class__("maximum", "Full", 95), settings)
    assert [profile.percent for profile in load_fan_profiles(settings)] == [45, 60, 95]


def test_switching_the_curve_on_binds_it_to_the_chosen_channel(page):
    page._preferred_pwm = 4
    page._curve_target_pwm = 2
    page._fan_control_available = lambda: True
    page._curve_validation_error = lambda: ""
    page.curve_enabled.setChecked(True)
    assert page._curve_target_pwm == 4
    assert not hasattr(page, "curve_use_channel_button")
    assert not hasattr(page, "curve_target_label")


def test_the_curve_chart_numbers_its_points_and_reads_the_one_under_the_pointer(qtbot):
    plot = FanCurvePlot()
    qtbot.addWidget(plot)
    plot.set_curve([(45, 70), (60, 90), (68, 100), (73, 100), (78, 100), (83, 100), (88, 100), (93, 100)])
    plot.set_live(62.9, 90, "cpu")
    plot.set_target(4)
    plot.resize(900, 460)
    plot.show()
    qtbot.wait(5)
    assert plot.scale.minimumHeight() >= 420
    assert plot.live_text() == "PWM 4 · CPU 62.9 °C → 90%"
    positions = plot.scale._point_positions()
    assert len(positions) == 8
    assert plot.scale.point_at(positions[3]) == 3
    assert plot.scale.point_at(QPointF(positions[3].x() + 40, positions[3].y() + 60)) is None


def test_a_profile_card_opening_its_editor_gets_the_room_it_needs(page, qtbot):
    """The mode stack is pinned to its page's height to keep the slider tidy.

    It was only measured when the mode changed, so a profile card opening its
    editor was squeezed into the old height: the name field sat on the speed
    label and the speed box was cut in half. The stack now measures again
    whenever the page on screen asks for a different height.
    """
    page._set_control_mode("manual")
    qtbot.wait(20)
    card = page.manual_preset_buttons[0]
    closed_height = page.control_stack.height()

    card.begin_edit()
    qtbot.waitUntil(lambda: card.height() >= card.sizeHint().height(), timeout=2000)

    assert page.control_stack.height() > closed_height
    editor = card._editor
    for field in (card._name_edit, card._percent_spin):
        top_left = field.mapTo(editor, field.rect().topLeft())
        assert editor.rect().contains(top_left)
        assert field.height() >= field.sizeHint().height()
    # The other cards keep their compact face at the top of the row.
    others = page.manual_preset_buttons[1:]
    assert all(other.height() == other.sizeHint().height() for other in others)
    assert all(other.y() == card.y() for other in others)

    card.cancel_edit()
    qtbot.waitUntil(lambda: page.control_stack.height() == closed_height, timeout=2000)


def test_saving_a_profile_leaves_focus_on_that_profile(qtbot):
    """Hiding the focused field first used to hand focus to the next card."""
    host = QWidget()
    row = QHBoxLayout(host)
    card, neighbour = (
        FanProfileCard(replace(profile), profile) for profile in DEFAULT_FAN_PROFILES[:2]
    )
    row.addWidget(card)
    row.addWidget(neighbour)
    qtbot.addWidget(host)
    host.show()
    host.activateWindow()
    qtbot.waitUntil(host.isActiveWindow, timeout=2000)
    card.begin_edit()
    qtbot.waitUntil(card._name_edit.hasFocus, timeout=2000)

    card._commit()

    assert card.hasFocus()
    assert not neighbour.hasFocus()
