"""A CPU card cannot save a value its steps do not allow.

The spin boxes only had a single step, so 3125 MHz or 1052 mV could be typed and
saved; Decky then dropped the exported card without a word and showed its
default. The card now rounds to the nearest 50 MHz / 5 mV step when the field is
left or the card saved.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from frontends.desktop.pages.cpu_control_view import (
    DEFAULT_CPU_PROFILES,
    CpuProfileCard,
)


@pytest.fixture
def card(qtbot):
    widget = CpuProfileCard(replace(DEFAULT_CPU_PROFILES[1]))
    qtbot.addWidget(widget)
    widget.begin_edit()
    return widget


def _type(spin, text):
    # What Qt does when the field loses focus: interpret the text, then announce it.
    spin.lineEdit().setText(text)
    spin.interpretText()
    spin.editingFinished.emit()


@pytest.mark.parametrize("typed, snapped", [
    ("3125", 3150), ("3124", 3100), ("3851", 3850), ("3874", 3850), ("3876", 3900), ("4199", 4200),
])
def test_a_typed_frequency_lands_on_a_50_mhz_step(card, typed, snapped):
    _type(card._frequency_spin, typed)

    assert card._frequency_spin.value() == snapped


@pytest.mark.parametrize("typed, snapped", [("1052", 1050), ("1053", 1055), ("1151", 1150), ("1324", 1325)])
def test_a_typed_vid_lands_on_a_5_mv_step(card, typed, snapped):
    _type(card._vid_spin, typed)

    assert card._vid_spin.value() == snapped


def test_saving_straight_from_a_field_that_never_lost_focus_still_snaps(card):
    changed = []
    card.changed.connect(changed.append)
    card._frequency_spin.lineEdit().setText("3925")
    card._vid_spin.lineEdit().setText("1177")
    card._frequency_spin.interpretText()
    card._vid_spin.interpretText()

    card._commit()

    [profile] = changed
    assert (profile.frequency_mhz, profile.vid_mv) == (3950, 1175)


def test_a_value_the_field_refuses_never_leaves_the_ranges(card):
    for spin, text in ((card._frequency_spin, "9999"), (card._vid_spin, "100"), (card._temperature_spin, "99")):
        _type(spin, text)
        assert spin.minimum() <= spin.value() <= spin.maximum()
