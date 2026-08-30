from PyQt6.QtWidgets import QLabel

from bc250cc.platform.init.services import InitManagerState
from frontends.desktop.pages import fans


def _dialog_text(dialog) -> str:
    return "\n".join(label.text() for label in dialog.findChildren(QLabel))


def test_paths_dialog_reports_only_paths_from_the_sensor_snapshot(qtbot, monkeypatch):
    monkeypatch.setattr(
        fans,
        "detect_init_manager",
        lambda: InitManagerState("openrc", True, "OpenRC runlevel management is available."),
    )
    state = {
        "sensores": {
            "chip": "nct6687",
            "path": "/sys/class/hwmon/hwmon7",
            "pwms": [{"path": "/sys/class/hwmon/hwmon7/pwm2"}],
            "fans": [{"pwm_path": "/sys/class/hwmon/hwmon7/pwm3"}],
        },
        "modulos": {"nct6683": False, "nct6687": True},
    }

    dialog = fans.PwmPathsDialog(state)
    qtbot.addWidget(dialog)
    text = _dialog_text(dialog)

    assert "/sys/class/hwmon/hwmon7" in text
    assert "/sys/class/hwmon/hwmon7/pwm2" in text
    assert "/sys/class/hwmon/hwmon7/pwm3" in text
    assert "hwmonX" not in text
    assert "pwm1" not in text


def test_paths_dialog_uses_openrc_guidance_without_systemctl(qtbot, monkeypatch):
    monkeypatch.setattr(
        fans,
        "detect_init_manager",
        lambda: InitManagerState("openrc", True, "OpenRC runlevel management is available."),
    )

    dialog = fans.PwmPathsDialog({"sensores": {}, "modulos": {}})
    qtbot.addWidget(dialog)
    text = _dialog_text(dialog)

    assert "OpenRC" in text
    assert "rc-service nct6687-load status" in text
    assert "rc-update show default" in text
    assert "systemctl" not in text


def test_paths_dialog_uses_systemd_guidance_only_when_systemd_is_active(qtbot, monkeypatch):
    monkeypatch.setattr(
        fans,
        "detect_init_manager",
        lambda: InitManagerState("systemd", True, "systemd unit management is available."),
    )

    dialog = fans.PwmPathsDialog({"sensores": {}, "modulos": {}})
    qtbot.addWidget(dialog)
    text = _dialog_text(dialog)

    assert "systemctl status nct6687-load.service --no-pager" in text
    assert "journalctl -b -u nct6687-load.service --no-pager" in text
    assert "rc-service nct6687-load status" not in text
