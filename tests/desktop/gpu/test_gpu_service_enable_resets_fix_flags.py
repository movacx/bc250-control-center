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

    def _service_action(self, action, **options):
        self.backend_actions.append((action, options))


def _page(**telemetry):
    base = {"set_method": "smu", "method": "busy-flag", "fix_metrics": True, "fix_frequency": True}
    # Both flags start on, which is the state that breaks a stock kernel.
    base.update(telemetry)
    return _Page(**base)


def test_enabling_asks_the_terminal_to_reset_the_fix_flags_without_a_polkit_step():
    """The reset was a pkexec call before the terminal: the password twice."""
    page = _page()
    integration._service_action(page, "enable")
    assert page.backend_actions == [("activar", {"reset_cyan_fix_flags": True})]
    assert page.controller.compatibility_calls == []


def test_both_fix_flags_default_to_off():
    """Neither bind mount survives a stock BC-250 kernel, so neither comes back on.

    fix-metrics is refused outright by the startup guard, and a leftover
    fix-freq mount makes the next start fail with exit status 32.
    """
    assert integration.FACTORY_FIX_METRICS is False
    assert integration.FACTORY_FIX_FREQUENCY is False


@pytest.mark.parametrize("action", ("restart", "disable"))
def test_only_enabling_touches_the_flags(action):
    page = _page()
    integration._service_action(page, action)
    assert page.controller.compatibility_calls == []
    assert page.backend_actions == [(integration._SERVICE_ACTIONS[action], {})]


HELPER = "/usr/libexec/bc250-control-center/bc250-governor-config-helper"


def _activation_command(monkeypatch, compatibility, *, reset=True):
    from bc250cc.infrastructure.gpu_repository import GPURepository
    from bc250cc.platform.init.services import InitManagerState

    captured = {}

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _command_path(self, _name):
            return "/usr/local/bin/cyan-skillfish-governor-smu"

        def _current_cyan_compatibility(self):
            if isinstance(compatibility, Exception):
                raise compatibility
            return compatibility

        def _governor_config_helper_path(self):
            return HELPER

        def _abrir_terminal(self, command, title):
            captured.update(command=command)
            return "terminal"

    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.ensure_no_incompatible_governors",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )
    Repository().controlar_governor("activar", reset_cyan_fix_flags=reset)
    return captured["command"]


def test_the_reset_is_a_sudo_step_of_the_start_terminal(monkeypatch):
    command = _activation_command(monkeypatch, ("smu", "busy-flag", True, True))
    reset = f"sudo {HELPER} set-cyan-compatibility smu busy-flag 0 0"
    assert reset in command
    assert command.index(reset) < command.index("systemctl enable --now")
    assert "pkexec" not in command


def test_a_kernel_set_method_survives_the_reset(monkeypatch):
    command = _activation_command(monkeypatch, ("kernel", "process", False, True))
    assert f"sudo {HELPER} set-cyan-compatibility kernel process 0 0" in command


def test_nothing_is_rewritten_when_the_flags_are_already_at_factory(monkeypatch):
    command = _activation_command(
        monkeypatch,
        ("smu", "busy-flag", integration.FACTORY_FIX_METRICS, integration.FACTORY_FIX_FREQUENCY),
    )
    assert "set-cyan-compatibility" not in command
    assert "systemctl enable --now" in command


def test_a_failed_reset_still_lets_the_service_start(monkeypatch):
    """Unreadable flags skip the step; a failing write only warns."""
    unreadable = _activation_command(monkeypatch, RuntimeError("config.toml is invalid"))
    assert "set-cyan-compatibility" not in unreadable
    assert "systemctl enable --now" in unreadable
    command = _activation_command(monkeypatch, ("smu", "busy-flag", True, False))
    step = command[: command.index("set -e;")]
    assert "set-cyan-compatibility" in step and "starting anyway" in step


def test_an_activation_that_does_not_ask_for_it_resets_nothing(monkeypatch):
    command = _activation_command(monkeypatch, ("smu", "busy-flag", True, True), reset=False)
    assert "set-cyan-compatibility" not in command


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
