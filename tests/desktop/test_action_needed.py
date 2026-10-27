"""A request refused until the user does one thing is not an error.

Ten reports of the first week were such refusals (close Steam, remove
HelixSR from the games first, prepare dependencies) shown as red GPU error
windows with a code, so users reported them as bugs.
"""

from __future__ import annotations

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.shared.errors import ActionNeeded
from frontends.desktop.components import widgets
from frontends.desktop.core import raw_errors


def _window(qtbot, monkeypatch, error: Exception):
    recorded = []
    monkeypatch.setattr(widgets, "record_window_error", lambda *args, **kwargs: recorded.append(args))
    raw_errors.remember(error)
    dialog = widgets.InfoDialog("Could not change the Steam launch option", str(error), tone="red")
    qtbot.addWidget(dialog)
    return dialog, recorded


def test_a_refusal_that_asks_for_an_action_has_no_error_code(qtbot, monkeypatch):
    dialog, recorded = _window(
        qtbot, monkeypatch, ActionNeeded("Close Steam completely first (Steam > Exit), then try again.")
    )
    assert dialog.report_code == ""
    assert recorded == []


def test_a_real_failure_is_still_an_error(qtbot, monkeypatch):
    dialog, recorded = _window(qtbot, monkeypatch, RuntimeError("Cyan D-Bus range could not be read here."))
    assert dialog.report_code
    assert recorded


def test_a_native_linux_game_is_refused_before_the_bridge_runs(tmp_path):
    (tmp_path / "game.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "cs2").write_bytes(b"\x7fELF")
    with pytest.raises(ActionNeeded, match="natively on Linux"):
        helixsr._refuse_native_game(tmp_path)


def test_a_proton_game_passes_the_native_check(tmp_path):
    (tmp_path / "Binaries" / "Win64").mkdir(parents=True)
    (tmp_path / "Binaries" / "Win64" / "Game.EXE").write_bytes(b"MZ")
    helixsr._refuse_native_game(tmp_path)


def test_a_translated_notice_still_finds_its_exception(monkeypatch):
    from frontends.desktop.core import raw_errors

    raw_errors.clear()
    english = "Cyan is not installed. Press Prepare dependencies on the Dashboard, then start Cyan from the governor card."
    try:
        raise ActionNeeded(english)
    except ActionNeeded as error:
        raw_errors.remember(error)
    monkeypatch.setattr("frontends.desktop.i18n.tr", lambda text: "Cyan no está instalado." if text == english else text)
    found = raw_errors.find("No se pudo guardar: Cyan no está instalado.")
    assert found is not None and found.kind == "ActionNeeded"


def test_a_report_from_a_translated_window_is_titled_in_english(qtbot, monkeypatch):
    from frontends.desktop.i18n import set_language, tr

    opened = {}
    import frontends.desktop.components.feedback_dialog as feedback_module

    class Form:
        def __init__(self, _parent, **kwargs):
            opened.update(kwargs)

        def exec(self):
            return 0

    monkeypatch.setattr(feedback_module, "FeedbackDialog", Form)
    set_language("de")
    try:
        title = tr("Could not export profiles to Decky")
        dialog = widgets.InfoDialog(title, "RuntimeError: helper missing", tone="red")
        qtbot.addWidget(dialog)
        dialog.report_button.click()
    finally:
        set_language("en")
    assert opened["summary"] == "Could not export profiles to Decky"


def test_a_translated_error_gets_the_code_of_its_english_original(qtbot):
    from frontends.desktop.i18n import set_language, tr

    raw_errors.clear()
    english = "The privileged governor configuration helper is not installed. Reinstall BC250 Control Center locally or from its package before editing /etc."
    try:
        raise RuntimeError(english)
    except RuntimeError as error:
        raw_errors.remember(error)
    set_language("pl")
    try:
        dialog = widgets.InfoDialog("Could not update advanced safe-points", tr(english), tone="red")
        qtbot.addWidget(dialog)
    finally:
        set_language("en")
    assert dialog.report_code == "BC250-HELPER-001"


def test_a_cpu_target_above_the_voltage_ceiling_says_which_scale_fits(qtbot):
    from bc250cc.infrastructure.cpu_command_policy import (
        CpuVoltageCeiling,
        validate_scale_target,
    )

    raw_errors.clear()
    with pytest.raises(CpuVoltageCeiling) as raised:
        validate_scale_target(4000, -10, 85)
    assert isinstance(raised.value, ValueError)
    assert "Nothing was changed" in str(raised.value) and "Use scale -" in str(raised.value)
    raw_errors.remember(raised.value)
    dialog = widgets.InfoDialog("Could not enable CPU persistence", str(raised.value), tone="red")
    qtbot.addWidget(dialog)
    assert getattr(dialog, "report_button", None) is None
