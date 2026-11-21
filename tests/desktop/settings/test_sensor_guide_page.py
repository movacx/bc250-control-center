"""Settings › Telemetry › Board sensors guide.

The I2C wiring guide and both kernel drivers, as a page of Settings: a link
under Sensor sources opens it, it says where this board stands, and its
buttons run the same flows as the rows above it.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog

from frontends.desktop.components.i2c_guide import _Photo
from frontends.desktop.pages import dashboard
from frontends.desktop.pages import settings as settings_module
from frontends.desktop.pages.settings import LinkRow, SettingsPage


class _Service:
    def read_local_config(self):
        return {}


class _Activity:
    def clear(self):
        return None


class _Controller:
    def __init__(self):
        self.calls = []

    def gestionar_apu_telemetry(self, action):
        self.calls.append(action)
        return "opened"


def _page(qtbot, tmp_path, monkeypatch, *, service=None, drivers=None, kernel=False):
    monkeypatch.setattr(settings_module, "board_bios_version", lambda: "P3.00")
    monkeypatch.setattr(settings_module, "sondear_telemetria_vrm", lambda: {"daemon": "missing"})
    monkeypatch.setattr(settings_module, "kernel_vrm_driver_present", lambda: kernel)
    monkeypatch.setattr(settings_module, "apu_telemetry_state",
                        lambda **_kw: dict(service or {"state": "not-installed", "supported": True}))
    monkeypatch.setattr(dashboard, "kernel_sensor_drivers", lambda: dict(drivers or {}))
    controller = _Controller()
    page = SettingsPage(controller, settings_service=_Service(), activity_service=_Activity(),
                        app_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(page)
    page._ensure_section("telemetry")
    return page, controller


def test_telemetry_links_to_the_guide(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch)
    telemetry = page._section_pages["telemetry"]
    links = [row for row in telemetry.findChildren(LinkRow) if "guide" in row.text().lower() or "guía" in row.text().lower()]
    assert len(links) == 1
    links[0].click()
    assert page._section_pages["telemetry_guide"].isVisibleTo(page) or page.sensor_guide is not None
    assert page.nav_buttons["telemetry"].isChecked()


def test_the_guide_opens_on_the_tab_asked_for_with_the_photos(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch)
    page.open_sensor_guide("vram")
    assert page.sensor_guide.current_tab == "vram"
    page.open_sensor_guide("i2c")
    photos = page.sensor_guide.findChildren(_Photo)
    assert len(photos) == 4 and all(not photo.pixmap().isNull() for photo in photos)


def test_the_guide_says_where_this_board_stands(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch, kernel=True, service={
        "state": "not-installed", "supported": False,
        "blocked_reason": "This kernel already reads the VRM itself (bc250_vrm).",
    }, drivers={"vrm_sensor": {"state": "active", "reading": 49.0}, "vram_sensor": {"state": "update-available"}})
    page.open_sensor_guide()
    guide = page.sensor_guide
    assert guide.status_label.text() == settings_module.tr(dashboard.VRM_HELP_KERNEL)
    assert not guide.service_button.isEnabled() and "bc250_vrm" in guide.service_label.text()
    assert "49 °C" in guide.driver_labels["vrm"].text()
    assert guide.driver_buttons["vrm"].property("guideAction") == "remove"
    assert guide.driver_buttons["vram"].property("guideAction") == "install"


def test_its_buttons_run_the_same_flows_as_the_rows(qtbot, tmp_path, monkeypatch):
    page, controller = _page(qtbot, tmp_path, monkeypatch, drivers={"vrm_sensor": {"state": "not-installed"}})
    page.open_sensor_guide("vrm")
    emitted = []
    page.driver_support_requested.connect(emitted.append)
    page.sensor_guide.driver_buttons["vrm"].click()
    assert emitted == ["vrm_sensor:install"]

    monkeypatch.setattr(settings_module.ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    page.sensor_guide.service_button.click()
    qtbot.waitUntil(lambda: controller.calls == ["install"], timeout=3000)


def test_every_reason_the_service_gives_is_translated(tmp_path):
    """Reported 2026-11-20: the guide showed "This kernel already reads the VRM
    itself…" in English on a Spanish desktop. The service states its reasons
    in English; every one must be in every catalog."""
    import json
    from pathlib import Path

    from bc250cc.infrastructure.apu_telemetry_service import (
        _BLOCKED_FAMILIES,
        apu_telemetry_supported,
    )
    from frontends.desktop.i18n.locale_catalog import COMPLETE_LOCALES, LOCALE_DIRECTORY

    module = tmp_path / "bc250_vrm"
    module.mkdir()
    reasons = {
        apu_telemetry_supported(family="arch", kernel_module=module)[1],
        apu_telemetry_supported(family="nixos", immutable=True, kernel_module=tmp_path / "none")[1],
        *_BLOCKED_FAMILIES.values(),
    }
    assert all(reasons) and len(reasons) == 3
    for code in COMPLETE_LOCALES:
        catalog = json.loads((Path(LOCALE_DIRECTORY) / f"{code}.json").read_text(encoding="utf-8"))
        assert reasons <= set(catalog), (code, reasons - set(catalog))
