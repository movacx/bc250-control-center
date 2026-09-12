"""Arch development regressions: passive sensors and finite CU privilege."""

import json
import runpy
import stat
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

from bc250cc.infrastructure.cu_repository import CURepository
from bc250cc.infrastructure.gpu_live_clock import read_hwmon_clock_mhz
from frontends.desktop.components.buttons import WrappingButton
from frontends.desktop.components.dashboard_widgets import PreparationSidebar
from frontends.desktop.core.compute_units_presenter import present_compute_units_state
from frontends.desktop.core.state import DashboardState
from frontends.desktop.i18n import localize_widget_tree, tr
from frontends.desktop.pages.dashboard import DashboardPage
from frontends.desktop.pages.gpu_governor import GpuGovernorPage

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("label", (None, "sclk", "gfxclk"))
def test_live_clock_uses_hz_and_supports_unlabelled_amdgpu(tmp_path, label):
    sensor = tmp_path / "hwmon/hwmon2"
    sensor.mkdir(parents=True)
    (sensor / "name").write_text("amdgpu\n")
    (sensor / "freq1_input").write_text("1000000000\n")
    if label:
        (sensor / "freq1_label").write_text(label)
    assert read_hwmon_clock_mhz(tmp_path) == 1000
    (sensor / "freq1_input").write_text("1850000000\n")
    assert read_hwmon_clock_mhz(tmp_path) == 1850


@pytest.mark.parametrize("name,label,value", (
    ("amdgpu", "mclk", "1850000000"),
    ("nct6687", "sclk", "1850000000"),
    ("amdgpu", "sclk", "4"),
    ("amdgpu", "sclk", "not available"),
))
def test_live_clock_does_not_invent_readings(tmp_path, name, label, value):
    sensor = tmp_path / "hwmon/hwmon0"
    sensor.mkdir(parents=True)
    for filename, text in {"name": name, "freq1_label": label, "freq1_input": value}.items():
        (sensor / filename).write_text(text)
    assert read_hwmon_clock_mhz(tmp_path) is None


def test_live_snapshot_preserves_limits_and_zero_utilization():
    old = DashboardState(governor_max_mhz=1850, governor_frequency_mhz=1600, gpu_utilization_percent=95)
    new = old.with_live_metrics({"gpu": {"frequency_mhz": 1000, "usage_percent": 0}})
    assert (new.governor_frequency_mhz, new.governor_max_mhz, new.gpu_utilization_percent) == (1000, 1850, 0)
    assert new.with_live_metrics({}).governor_frequency_mhz == 0
    assert new.with_live_metrics({"gpu": {"frequency_mhz": float("nan")}}).governor_frequency_mhz == 0


def test_dashboard_live_lane_is_passive_and_pauses_when_hidden(qtbot):
    calls = []
    controller = SimpleNamespace(metricas_tiempo_real=lambda: calls.append("sensors") or {"gpu": {"frequency_mhz": 1000}})
    page = DashboardPage(controller)
    qtbot.addWidget(page)
    page.set_updates_active(True)
    qtbot.waitUntil(lambda: page.state.governor_frequency_mhz == 1000)
    assert page.live_timer.interval() == 1000
    page.set_updates_active(False)
    assert not page.live_timer.isActive()
    assert not page._live_refresher._active
    assert calls
    page._apply_live_sample((time.monotonic() - 10, {"gpu": {"frequency_mhz": 2000}}))
    assert page.state.governor_frequency_mhz == 0


def test_saved_table_does_not_imply_enabled_boot_persistence():
    base = {"boot_sync_key": "saved", "service_enabled": False}
    assert present_compute_units_state(base, live_masks=[]).persistence_status == "Disabled"
    base["service_enabled"] = True
    assert present_compute_units_state(base, live_masks=[]).persistence_status == "Enabled"


def test_desktop_cu_uses_one_fixed_polkit_entrypoint(monkeypatch):
    import bc250cc.infrastructure.cu_repository as module

    helper = SimpleNamespace(lstat=lambda: SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o755))
    monkeypatch.setattr(module, "DESKTOP_CU_HELPER", helper)
    repository = CURepository()
    repository.estado_herramientas_bc250 = lambda: {"cu_privileged_backend_ready": True}
    repository._command_path = lambda _: "/usr/bin/pkexec"
    calls = []
    repository._ejecutar = lambda argv, **kw: calls.append(argv) or (0, "", "")
    payload = json.dumps([["--yes", "disable-wgp", "0.0.4"], ["--yes", "write-service-table"]])
    repository._ejecutar_cu_accion_pkexec(["batch", payload])
    assert calls == [[
        "/usr/bin/pkexec", "--disable-internal-agent", str(helper), "batch", payload
    ]]


@pytest.mark.parametrize("payload", ([None], ["status"], [["status"], ["bash", "-c", "id"]]))
def test_cu_executor_validates_whole_batch_before_execution(monkeypatch, payload):
    module = runpy.run_path(str(ROOT / "privileged/helpers/bc250-steamos-game-helper"))
    action = module["action_cu"]
    monkeypatch.setitem(action.__globals__, "staged_cu_runtime", lambda: pytest.fail("must reject before accessing backend"))
    assert action(["batch", json.dumps(payload)]) == 2


def test_cu_batch_emits_only_final_verification_on_stdout(monkeypatch, capsys):
    module = runpy.run_path(str(ROOT / "privileged/helpers/bc250-steamos-game-helper"))
    action = module["action_cu"]
    monkeypatch.setitem(action.__globals__, "staged_cu_runtime", lambda: (Path("/fake/backend"), None))
    monkeypatch.setitem(action.__globals__, "validate_staged_cu_backend", lambda *_: "")
    monkeypatch.setitem(action.__globals__, "cu_safe_env", lambda: {})
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stderr="", stdout="final\n" if argv[-1] == "status" else "intermediate\n")

    monkeypatch.setattr(action.__globals__["subprocess"], "run", run)
    assert action(["batch", json.dumps([["--yes", "enable-wgp", "0.0.0"], ["--yes", "write-service-table"]])]) == 0
    output = capsys.readouterr()
    assert output.out == "final\n"
    assert output.err.count("intermediate") == 2
    assert calls[-1] == ["/fake/backend", "status"]


def test_repopulated_combo_roundtrips_without_restoring_obsolete_items(qtbot):
    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItem("Apply", "apply")
    localize_widget_tree(combo, "es")
    combo.clear()
    combo.addItem(tr("Cancel", "es"), "cancel")
    localize_widget_tree(combo, "de")
    assert combo.currentText() == tr("Cancel", "de")
    assert combo.currentData() == "cancel"
    localize_widget_tree(combo, "en")
    assert combo.currentText() == "Cancel"


def test_localization_does_not_emit_configuration_signals(qtbot):
    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItem("Apply", "apply")
    signals = []
    combo.currentTextChanged.connect(signals.append)
    localize_widget_tree(combo, "es")
    assert signals == []


def test_preparation_card_is_clickable_without_hitting_the_checkbox(qtbot):
    panel = PreparationSidebar()
    qtbot.addWidget(panel)
    panel.resize(1200, 650)
    panel.show()
    card = panel.component_cards["cpu_oc"]
    assert card.checkbox.isChecked()
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert not card.checkbox.isChecked()
    assert card.checkbox.accessibleName()
    panel.set_state(DashboardState(preparation_tools={"unrelated": True}))
    assert panel.system_status.text() == tr("Not detected")


@pytest.mark.parametrize("backend", ("oberon-governor", "cyan-skillfish-governor-smu"))
def test_gpu_top_cards_share_both_edges(qtbot, backend):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state["governor_backend"] = backend
    page.resize(1440, 1000)
    page.show()
    qtbot.wait(20)
    assert page.configuration_card.geometry().top() == page.metrics_card.geometry().top()
    assert page.configuration_card.geometry().bottom() == page.metrics_card.geometry().bottom()


def test_gpu_configuration_footer_matches_untouched_telemetry_footer(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state["governor_backend"] = "cyan-skillfish-governor-smu"
    page.resize(1440, 1000)
    page.show()
    qtbot.wait(20)

    configuration_bottom = page.range_footer.mapTo(
        page.content, page.range_footer.rect().bottomLeft()
    ).y()
    telemetry_bottom = page.runtime_controls_panel.mapTo(
        page.content, page.runtime_controls_panel.rect().bottomLeft()
    ).y()
    assert abs(configuration_bottom - telemetry_bottom) <= 1
    assert abs(page.cyan_set_method.width() - page.cyan_usage_method.width()) <= 1


def test_cu_authorization_is_cached_only_for_the_fixed_helper():
    import xml.etree.ElementTree as ET

    policy = ET.parse(ROOT / "privileged/policies/io.github.movacx.bc250-control-center.policy")
    action = policy.find(".//action[@id='io.github.movacx.bc250-control-center.compute-units']")
    assert action.findtext("defaults/allow_active") == "auth_admin_keep"
    assert action.findtext("defaults/allow_inactive") == "no"
    assert action.findtext("annotate[@key='org.freedesktop.policykit.exec.path']") == "/usr/libexec/bc250-control-center/bc250-cu-helper"


def test_cu_desktop_entrypoint_rejects_untrusted_executor(tmp_path, monkeypatch):
    module = runpy.run_path(str(ROOT / "privileged/helpers/bc250-cu-helper"))
    target = tmp_path / "user-owned-helper"
    target.write_text("raise RuntimeError('must never execute')")
    target.chmod(0o777)
    assert module["protected_file"](target) is False
    action = module["main"]
    monkeypatch.setattr(action.__globals__["os"], "geteuid", lambda: 0)
    monkeypatch.setitem(action.__globals__, "EXECUTOR", target)
    with pytest.raises(RuntimeError, match="untrusted"):
        action(["status"])


def test_wrapping_button_grows_without_changing_label_or_font(qtbot):
    button = WrappingButton("Apply configuration and automatic scale")
    qtbot.addWidget(button)
    button.ensurePolished()
    font = button.font()
    button.resize(130, 30)
    button.show()
    qtbot.wait(20)
    assert button.height() >= button.heightForWidth(130)
    assert button.height() > 30
    assert button.font() == font
    assert button.text() == "Apply configuration and automatic scale"
