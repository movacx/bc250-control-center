"""Keys that must work, because a workflow stops dead when they do not."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from frontends.desktop.console.key_bindings import key_sequence, paste_payload

KEY = Qt.Key
MOD = Qt.KeyboardModifier
NONE = MOD.NoModifier


def press(key, modifiers=NONE, text="", **kwargs):
    return key_sequence(key, modifiers, text, **kwargs)


# ------------------------------------------------------------------ the basics


def test_enter_sends_a_carriage_return():
    """Every workflow ends on a prompt waiting for this one byte."""
    assert press(KEY.Key_Return, text="\r") == b"\r"
    assert press(KEY.Key_Enter, text="\r") == b"\r"


def test_backspace_sends_delete_like_every_linux_terminal():
    assert press(KEY.Key_Backspace) == b"\x7f"


def test_ctrl_c_sends_the_interrupt_character():
    assert press(KEY.Key_C, MOD.ControlModifier, text="\x03") == b"\x03"


def test_ctrl_d_sends_end_of_transmission():
    assert press(KEY.Key_D, MOD.ControlModifier) == b"\x04"


def test_every_control_letter_maps_to_its_own_byte():
    for offset in range(26):
        key = KEY(KEY.Key_A.value + offset)
        assert press(key, MOD.ControlModifier) == bytes([offset + 1])


def test_control_punctuation_maps_to_the_remaining_control_codes():
    assert press(KEY.Key_Space, MOD.ControlModifier) == b"\x00"
    assert press(KEY.Key_BracketLeft, MOD.ControlModifier) == b"\x1b"
    assert press(KEY.Key_Backslash, MOD.ControlModifier) == b"\x1c"
    assert press(KEY.Key_Underscore, MOD.ControlModifier) == b"\x1f"


def test_plain_text_is_sent_as_utf8():
    assert press(KEY.Key_A, NONE, "a") == b"a"
    assert press(KEY.Key_Ntilde, NONE, "ñ") == "ñ".encode()


def test_a_password_with_accents_survives_the_round_trip():
    """A sudo password is typed here; a mangled byte is a failed workflow."""
    for character in "contraseña-áéíóú-ÿ":
        assert press(KEY.Key_unknown, NONE, character) == character.encode("utf-8")


def test_tab_and_shift_tab_are_distinct():
    assert press(KEY.Key_Tab) == b"\t"
    assert press(KEY.Key_Backtab) == b"\x1b[Z"


def test_escape_is_sent_through():
    assert press(KEY.Key_Escape) == b"\x1b"


# -------------------------------------------------------------- cursor motion


@pytest.mark.parametrize(
    "key, final",
    [
        (KEY.Key_Up, b"A"),
        (KEY.Key_Down, b"B"),
        (KEY.Key_Right, b"C"),
        (KEY.Key_Left, b"D"),
        (KEY.Key_Home, b"H"),
        (KEY.Key_End, b"F"),
    ],
)
def test_cursor_keys_use_the_normal_form_by_default(key, final):
    assert press(key) == b"\x1b[" + final


@pytest.mark.parametrize(
    "key, final", [(KEY.Key_Up, b"A"), (KEY.Key_Down, b"B"), (KEY.Key_Home, b"H")]
)
def test_cursor_keys_switch_form_when_the_program_asked_for_it(key, final):
    assert press(key, application_cursor=True) == b"\x1bO" + final


def test_a_modified_cursor_key_carries_the_modifier():
    assert press(KEY.Key_Right, MOD.ControlModifier) == b"\x1b[1;5C"
    assert press(KEY.Key_Left, MOD.ShiftModifier) == b"\x1b[1;2D"
    assert press(KEY.Key_Up, MOD.AltModifier) == b"\x1b[1;3A"


def test_page_and_edit_keys_use_the_tilde_form():
    assert press(KEY.Key_PageUp) == b"\x1b[5~"
    assert press(KEY.Key_PageDown) == b"\x1b[6~"
    assert press(KEY.Key_Delete) == b"\x1b[3~"
    assert press(KEY.Key_Insert) == b"\x1b[2~"


def test_function_keys_are_covered_through_f12():
    assert press(KEY.Key_F1) == b"\x1bOP"
    assert press(KEY.Key_F4) == b"\x1bOS"
    assert press(KEY.Key_F5) == b"\x1b[15~"
    assert press(KEY.Key_F12) == b"\x1b[24~"


def test_alt_prefixes_an_escape_the_way_readline_expects():
    assert press(KEY.Key_B, MOD.AltModifier, "b") == b"\x1bb"
    assert press(KEY.Key_Backspace, MOD.AltModifier) == b"\x1b\x7f"


# ------------------------------------------------------------------- nothing


def test_a_bare_modifier_sends_nothing():
    for key in (KEY.Key_Control, KEY.Key_Shift, KEY.Key_Alt, KEY.Key_Meta):
        assert press(key) is None


def test_a_key_with_no_text_and_no_meaning_sends_nothing():
    assert press(KEY.Key_CapsLock) is None


# --------------------------------------------------------------------- paste


def test_pasted_newlines_become_carriage_returns():
    assert paste_payload("one\ntwo\r\nthree") == b"one\rtwo\rthree"


def test_bracketed_paste_wraps_the_payload_when_the_program_asked():
    payload = paste_payload("ls", bracketed=True)
    assert payload == b"\x1b[200~ls\x1b[201~"


def test_a_paste_cannot_close_its_own_bracket_early():
    """Otherwise pasted text could break out and run as if it were typed."""
    payload = paste_payload("safe\x1b[201~rm -rf /", bracketed=True)
    assert payload.count(b"\x1b[201~") == 1
    assert payload.endswith(b"\x1b[201~")
    assert b"safe" in payload


def test_paste_without_bracketing_is_plain_bytes():
    assert paste_payload("texto con ñ") == "texto con ñ".encode()
