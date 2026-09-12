"""Starting the governor puts Cyan's fix flags back to known-good values.

``fix-metrics`` and ``fix-freq`` make Cyan replace two GPU sensor files with
patched copies through a bind mount that lives as long as the daemon does. A
mount left behind by an earlier run makes the next start fail outright, and
``fix-freq`` is the one that fails first. Starting the service is therefore the
moment to put both flags back, without touching the set-method or the usage
method, which are deliberate user choices.
"""

import pytest

import frontends.desktop.pages.gpu_governor_integration as integration
from frontends.desktop.core.error_diagnostics import diagnose_error

FAILING_START_LOG = """\
sep 10 13:34:55 AMDBC250 cyan-skillfish-governor-smu[1407518]: GPU frequency fix enabled
sep 10 13:34:55 AMDBC250 cyan-skillfish-governor-smu[1407518]: Error: Io(Custom { kind: Other, \
error: "mount --bind /dev/shm/patched_freq_metrics \
/sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon1/freq1_input failed: signal: 15 (SIGTERM)" })
sep 10 13:34:56 AMDBC250 cyan-skillfish-governor-smu[1407542]: mount: \
/sys/devices/pci0000:00/0000:00:08.1/0000:01:00.0/gpu_metrics: move_mount() failed: \
No such file or directory.
sep 10 13:34:56 AMDBC250 systemd[1]: cyan-skillfish-governor-smu.service: \
Failed with result 'exit-code'.
ERROR: Cyan is running but its D-Bus name is unavailable after policy repair"""


class _Controller:
    def __init__(self):
        self.compatibility_calls = []

    def configurar_compatibilidad_gpu_cyan(self, *args):
        self.compatibility_calls.append(args)
        return {}


class _Page:
    def __init__(self, **telemetry):
        self.controller = _Controller()
        self.current_state = {"cyan_telemetry": telemetry}
        self.console = []
        self.backend_actions = []

    def _append_console(self, message):
        self.console.append(str(message))

    def _service_action(self, action):
        self.backend_actions.append(action)


def _page(**telemetry):
    base = {"set_method": "smu", "method": "busy-flag", "fix_metrics": True, "fix_frequency": True}
    # Both flags start on, which is the state that breaks a stock kernel.
    base.update(telemetry)
    return _Page(**base)


def test_enabling_resets_the_fix_flags_and_keeps_the_chosen_methods():
    page = _page()
    integration._service_action(page, "enable")
    assert page.backend_actions == ["activar"]
    assert page.controller.compatibility_calls == [
        ("smu", "busy-flag", integration.FACTORY_FIX_METRICS, integration.FACTORY_FIX_FREQUENCY)
    ]


def test_both_fix_flags_default_to_off():
    """Neither bind mount survives a stock BC-250 kernel, so neither comes back on.

    fix-metrics is refused outright by the startup guard, and a leftover
    fix-freq mount makes the next start fail with exit status 32.
    """
    assert integration.FACTORY_FIX_METRICS is False
    assert integration.FACTORY_FIX_FREQUENCY is False


def test_a_kernel_set_method_survives_the_reset():
    page = _page(set_method="kernel", method="process")
    integration._service_action(page, "enable")
    assert page.controller.compatibility_calls[0][:2] == ("kernel", "process")


def test_nothing_is_rewritten_when_the_flags_are_already_at_factory():
    page = _page(fix_metrics=integration.FACTORY_FIX_METRICS,
                 fix_frequency=integration.FACTORY_FIX_FREQUENCY)
    integration._service_action(page, "enable")
    assert page.controller.compatibility_calls == []
    assert page.backend_actions == ["activar"]


@pytest.mark.parametrize("action", ("restart", "disable"))
def test_only_enabling_touches_the_flags(action):
    page = _page()
    integration._service_action(page, action)
    assert page.controller.compatibility_calls == []
    assert page.backend_actions == [integration._SERVICE_ACTIONS[action]]


def test_a_failed_reset_still_lets_the_service_start():
    page = _page()

    def explode(*_args):
        raise RuntimeError("config.toml is read-only")

    page.controller.configurar_compatibilidad_gpu_cyan = explode
    integration._service_action(page, "enable")
    assert page.backend_actions == ["activar"]
    assert any("read-only" in line for line in page.console)


def test_the_failing_start_log_is_not_reported_as_a_compute_units_problem():
    diagnosis = diagnose_error(FAILING_START_LOG, context="compute units")
    assert diagnosis.code == "BC250-GPU-005", diagnosis.code
    assert "sensor" in diagnosis.summary


def test_the_compatibility_panel_cannot_stay_out_of_sync_with_the_toml(qtbot):
    """A staged edit survives while the screen is open, and only until then.

    One click on a check box used to latch ``_compatibility_dirty`` forever, so
    every later refresh skipped the sync and the panel kept showing values
    config.toml no longer had. Applying those stale values is what sent
    ``fix-metrics = true`` back to a kernel that cannot host it.
    """
    from PyQt6.QtGui import QShowEvent

    from frontends.desktop.pages.gpu_governor_view import GpuGovernorView, GpuViewState

    on_disk = GpuViewState(
        set_method="smu", usage_method="busy-flag", fix_metrics=False, fix_frequency=False
    )
    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.apply_state(on_disk)
    assert view._metrics_toggle.isChecked() is False

    view._metrics_toggle.setChecked(True)
    for _ in range(5):
        view.apply_state(on_disk)
    assert view._metrics_toggle.isChecked() is True, "a staged edit must survive refreshes"

    view.showEvent(QShowEvent())
    assert view._metrics_toggle.isChecked() is False, "re-entering must resync with the TOML"
    assert view._compatibility_dirty is False


def test_the_panel_mirrors_every_value_the_toml_reports(qtbot):
    from frontends.desktop.pages.gpu_governor_view import GpuGovernorView, GpuViewState

    view = GpuGovernorView()
    qtbot.addWidget(view)
    for set_method, usage, metrics, frequency in (
        ("smu", "busy-flag", False, False),
        ("smu", "process", True, False),
        ("kernel", "kernel", False, True),
    ):
        view.apply_state(
            GpuViewState(
                set_method=set_method, usage_method=usage,
                fix_metrics=metrics, fix_frequency=frequency,
            )
        )
        assert view.set_method_combo.currentData() == set_method
        assert view.usage_method_combo.currentData() == usage
        assert view._metrics_toggle.isChecked() is metrics
        assert view._frequencies_toggle.isChecked() is frequency
