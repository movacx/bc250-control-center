"""One click, one outcome: the Fans page no longer stacks windows.

Reported flow: apply a manual profile, type the password, confirm a window,
then close a second window saying the fan is at 100 % — which the user could
already hear. A speed is applied on the click, the result is a toast, and
only a speed low enough to overheat the board asks first.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from frontends.desktop.pages import fans as fans_module
from frontends.desktop.pages.fans import FansPage


class _Task(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self._operation = operation

    def start(self):
        try:
            self.succeeded.emit(self._operation())
        except Exception as error:  # pragma: no cover - defensive seam
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class _Controller:
    def __init__(self):
        self.saved = []
        self.writes = []
        self.exports = []

    def save_local_config(self, payload):
        self.saved.append(payload)

    def guardar_config_local(self, payload):
        self.saved.append(payload)

    def aplicar_pwm_fan(self, pwm, raw):
        self.writes.append((pwm, raw))
        return {"pwm": pwm, "valor": raw, "verified": {"pwm": pwm, "value": raw, "enable": 1}}

    def restaurar_pwm_automatico(self, pwm):
        self.writes.append((pwm, "auto"))
        return {"pwm": pwm, "verified": {"pwm": pwm, "enable": 2}, "automatic": True}

    def exportar_perfiles_fan_decky(self, profiles):
        self.exports.append(profiles)
        return "Decky fan profiles published."


def _page(qtbot, monkeypatch):
    controller = _Controller()
    monkeypatch.setattr(fans_module, "FanTask", _Task)
    page = FansPage(controller, settings_service=controller)
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [{
            "index": 2, "label": "Pump Fan", "rpm": 1200, "pwm": 170,
            "pwm_path": "/sys/class/hwmon/hwmon0/pwm2", "pwm_user_writable": False, "pwm_root_writable": True,
        }]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()
    monkeypatch.setattr(page, "refresh", lambda *args, **kwargs: None)
    notices = {"dialogs": [], "toasts": [], "confirms": []}

    class Confirm:
        def __init__(self, title, message, **kwargs):
            notices["confirms"].append(title)

        def exec(self):
            return QDialog.DialogCode.Accepted

    class Info:
        def __init__(self, title, *args, **kwargs):
            notices["dialogs"].append(title)

        def exec(self):
            return 0

    monkeypatch.setattr(fans_module, "ConfirmDialog", Confirm)
    monkeypatch.setattr(fans_module, "InfoDialog", Info)
    monkeypatch.setattr(fans_module, "show_toast", lambda _anchor, title, message="", **_kw: notices["toasts"].append((title, message)))
    return page, controller, notices


def test_a_normal_speed_is_applied_on_the_click_and_reported_by_a_toast(qtbot, monkeypatch):
    page, controller, notices = _page(qtbot, monkeypatch)
    page._set_staged_pwm_percent(60)

    page.apply_manual_pwm()

    assert controller.writes == [(2, round(60 * 255 / 100))]
    assert notices["confirms"] == [] and notices["dialogs"] == []
    assert notices["toasts"] and notices["toasts"][-1][0] == "Fan speed applied"


def test_only_a_speed_that_can_overheat_asks_first(qtbot, monkeypatch):
    page, controller, notices = _page(qtbot, monkeypatch)
    page._set_staged_pwm_percent(fans_module.LOW_DUTY_CONFIRM_PERCENT - 5)

    page.apply_manual_pwm()

    assert notices["confirms"] == ["Apply a low fan speed"]
    assert len(controller.writes) == 1


def test_a_slider_value_is_saved_as_the_custom_preset(qtbot, monkeypatch):
    page, controller, _notices = _page(qtbot, monkeypatch)
    page._set_staged_pwm_percent(57)

    page.apply_manual_pwm()
    qtbot.waitUntil(lambda: any("fan_preset" in payload for payload in controller.saved), timeout=3000)

    preset = next(payload["fan_preset"] for payload in reversed(controller.saved) if "fan_preset" in payload)
    assert preset == {"enabled": True, "preset": "custom", "percent": 57, "pwm": 2}


def test_handing_the_fan_back_to_the_bios_needs_no_question(qtbot, monkeypatch):
    page, controller, notices = _page(qtbot, monkeypatch)

    page.restore_automatic_pwm()

    assert controller.writes == [(2, "auto")]
    assert notices["confirms"] == [] and notices["dialogs"] == []
    assert notices["toasts"][-1][0] == "Automatic fan control restored"


def test_profiles_go_to_decky_and_through_a_file(qtbot, monkeypatch, tmp_path):
    page, controller, notices = _page(qtbot, monkeypatch)

    page.export_profiles_to_decky()
    qtbot.waitUntil(lambda: bool(controller.exports), timeout=3000)
    assert [entry["key"] for entry in controller.exports[0]] == ["quiet", "balanced", "boost"]

    target = tmp_path / "profiles.json"
    monkeypatch.setattr(fans_module.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    page.export_profiles_to_file()
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["kind"] == "bc250-fan-profiles" and len(document["profiles"]) == 3

    document["profiles"][0] = {"key": "quiet", "name": "Night", "percent": 33}
    target.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(fans_module, "save_fan_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(fans_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    writes_before = list(controller.writes)
    page.import_profiles_from_file()

    card = page.manual_preset_buttons[0]
    assert (card.profile.name, card.profile.percent) == ("Night", 33)
    assert controller.writes == writes_before  # importing never touches the fan
    assert notices["toasts"][-1][0] == "Fan profiles imported"


def test_a_bad_file_is_an_error_dialog_not_a_half_import(qtbot, monkeypatch, tmp_path):
    page, _controller, notices = _page(qtbot, monkeypatch)
    target = tmp_path / "other.json"
    target.write_text(json.dumps({"kind": "something"}), encoding="utf-8")
    names = [card.profile.name for card in page.manual_preset_buttons]

    page._import_profiles(target)

    assert notices["dialogs"] == ["Could not import fan profiles"]
    assert [card.profile.name for card in page.manual_preset_buttons] == names
