"""Shared deterministic harness and integration checks for the redesigned page."""

from copy import deepcopy

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from bc250cc.application.fan.channels import FanChannelsService
from frontends.desktop.pages import fans as fans_module


class ImmediateTask(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def start(self):
        try:
            result = self.operation()
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class Controller:
    def __init__(self, config=None):
        self.config = deepcopy(config or {})
        self.saved = []
        self.writes = []
        self.policies = []
        self.exports = []
        self.verified_value = None

    def record(self, *args):
        pass

    def read_local_config(self):
        return deepcopy(self.config)

    def save_local_config(self, payload):
        self.saved.append(deepcopy(payload))
        self.config.update(deepcopy(payload))
        return self.read_local_config()

    def aplicar_pwm_fan(self, pwm, raw):
        self.writes.append((pwm, raw))
        return {"verified": {"pwm": pwm, "value": raw if self.verified_value is None else self.verified_value, "enable": 1}}

    def restaurar_pwm_automatico(self, pwm):
        self.writes.append((pwm, "auto"))
        return {"verified": {"pwm": pwm, "enable": 2}}

    def exportar_perfiles_fan_decky(self, profiles):
        self.exports.append(deepcopy(profiles))
        return "Decky fan profiles published."

    def estado_quick_access_decky(self):
        return {"decky_detected": True, "plugin_present": True}

    def ceder_fan_a_otro_programa(self, flag):
        self.writes.append(("external", flag))
        return {"external": flag}

    def sincronizar_control_fan_sistema(self, policy):
        self.policies.append(deepcopy(policy))
        return {"salida": "OK POLICY test"}


def make_page(qtbot, monkeypatch, *, config=None, service_on=False):
    controller = Controller(config)
    notices = {"confirms": [], "dialogs": [], "toasts": [], "answer": QDialog.DialogCode.Accepted}

    class Confirm:
        def __init__(self, title, message, **kwargs):
            notices["confirms"].append((title, message))

        def exec(self):
            return notices["answer"]

    class Info:
        def __init__(self, title, message, **kwargs):
            notices["dialogs"].append((title, message))

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(fans_module, "FanTask", ImmediateTask)
    monkeypatch.setattr(fans_module, "ConfirmDialog", Confirm)
    monkeypatch.setattr(fans_module, "InfoDialog", Info)
    monkeypatch.setattr(fans_module, "show_toast", lambda _anchor, title, message="", **kw: notices["toasts"].append((title, message)))
    page = fans_module.FansPage(controller, settings_service=controller, activity_service=controller)
    qtbot.addWidget(page)
    monkeypatch.setattr(page, "refresh", lambda: None)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [
            {"index": pwm, "rpm": 1200 if pwm == 2 else 0, "pwm": 153,
             "pwm_path": f"/sys/class/hwmon/hwmon0/pwm{pwm}", "pwm_root_writable": True}
            for pwm in fans_module.BOARD_CHANNELS
        ]},
        "modulos": {"nct6687": True},
    }
    page._system_fan_control = {"enabled": service_on, "running": service_on, "available": True, "state": "active" if service_on else "disabled"}
    page._load_config()
    return page, controller, notices


def select(page, pwm, mode=None):
    page.table.selectRow(page.model.row_for(pwm))
    if mode is not None:
        page.editor.mode.setCurrentIndex(page.editor.mode.findData(mode))


def forum_config():
    return {"fan_channels": {
        **{str(pwm): {"mode": "curve", "source": "hottest", "points": [[40, 30], [60, 60], [80, 100]]} for pwm in (1, 3, 4, 5)},
        "2": {"mode": "fixed", "role": "pump", "percent": 90},
    }}


def test_apply_uses_channel_service_and_syncs_complete_forum_policy(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=forum_config(), service_on=True)
    assert isinstance(page._channels_service, FanChannelsService)
    calls = []
    original = page._channels_service.set_channel

    def set_channel(pwm, entry):
        calls.append((pwm, deepcopy(entry)))
        return original(pwm, entry)

    monkeypatch.setattr(page._channels_service, "set_channel", set_channel)
    select(page, 3, "curve")
    page.editor.points._rows[1][1].setValue(65)
    page.editor.apply_button.click()
    qtbot.waitUntil(lambda: len(controller.policies) == 1)
    assert calls[0][0] == 3
    policy = controller.policies[0]
    assert set(policy["channels"]) == {"1", "2", "3", "4", "5"}
    assert all(policy["channels"][str(pwm)]["mode"] == "curve" for pwm in (1, 3, 4, 5))
    assert policy["channels"]["3"]["points"][1] == [60, 65]
    assert policy["channels"]["2"]["role"] == "pump"
    assert policy["channels"]["2"]["percent"] == 90
    assert controller.writes == []


def test_returning_one_channel_to_firmware_keeps_pump_policy_p1_1(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=forum_config(), service_on=True)
    select(page, 3, "firmware")
    page.editor.apply_button.click()
    qtbot.waitUntil(lambda: len(controller.policies) == 1)
    channels = controller.policies[0]["channels"]
    assert channels.get("3", {}).get("mode", "firmware") == "firmware"
    assert channels["2"]["role"] == "pump" and channels["2"]["percent"] == 90
    assert all(channels[str(pwm)]["mode"] == "curve" for pwm in (1, 4, 5))
    assert controller.writes == []


@pytest.mark.parametrize("service_on", [False, True])
def test_pump_under_30_is_refused_without_save_or_write(qtbot, monkeypatch, service_on):
    page, controller, notices = make_page(qtbot, monkeypatch, config=forum_config(), service_on=service_on)
    select(page, 2)
    before = controller.read_local_config()
    page.editor.fixed_spin.setValue(29)
    page.editor.apply_button.click()
    assert page.editor.error.text()
    assert not page.editor.error.isHidden()
    assert controller.config == before
    assert controller.writes == controller.policies == []
    assert notices["confirms"] == []


def test_profile_requires_apply_and_replaces_active_set(qtbot, monkeypatch):
    config = forum_config()
    config["fan_modes"] = [{"name": "Solo", "channels": {"4": {"mode": "fixed", "percent": 70}}}]
    page, controller, _ = make_page(qtbot, monkeypatch, config=config, service_on=True)
    before = controller.read_local_config()
    page.profile_combo.setCurrentIndex(page.profile_combo.findData("Solo"))
    assert controller.config == before
    assert controller.policies == controller.writes == []
    page.profile_apply.click()
    qtbot.waitUntil(lambda: bool(controller.policies))
    assert set(controller.policies[-1]["channels"]) == {"4"}
    assert controller.config["fan_active_mode"] == "Solo"


def test_v1_status_without_channels_shows_active_for_pwm2(qtbot, monkeypatch):
    page, _, _ = make_page(qtbot, monkeypatch, config=forum_config(), service_on=True)
    page._system_fan_control["status"] = {"pwm": 2, "percent": 90, "temperature": 52, "source": "preset"}
    page._render()
    row = page.model.row_for(2)
    assert page.model.data(page.model.index(row, fans_module.STATE)) == "Active"
    assert page.model.data(page.model.index(row, fans_module.TEMPERATURE)) == "52.0"


def test_indirect_editor_and_table_labels_are_catalogued_in_every_locale():
    """The global literal scan cannot see labels passed through helper tuples."""
    import json

    from frontends.desktop.i18n import SUPPORTED_LANGUAGES
    from frontends.desktop.i18n.locale_catalog import LOCALE_DIRECTORY

    labels = {
        *(label for label, _right in fans_module.COLUMNS),
        *(label for _key, label in fans_module.MODE_LABELS),
        *(label for _key, label in fans_module.ROLE_LABELS),
        *(label for _key, label in fans_module.SOURCE_LABELS),
        "Channels", "Thermal", "Temperature °C", "Minimum PWM", "Maximum PWM",
        "Hysteresis", "Response delay", "Largest step up", "Largest step down",
        "Spin-up kick", "Name", "Function", "Speed", "Presets", "Follows",
        "{count} channels", "{count} turning", "{count} controlled", "{count} curves",
    }
    for language in SUPPORTED_LANGUAGES:
        catalog = json.loads((LOCALE_DIRECTORY / f"{language}.json").read_text())
        assert labels <= catalog.keys(), (language, labels - catalog.keys())
        assert all(catalog[label].strip() for label in labels)
