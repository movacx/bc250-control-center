import importlib.util
import json
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER_SOURCE = ROOT / "privileged/helpers/bc250-quick-access-helper"


@pytest.fixture()
def helper_module():
    loader = SourceFileLoader("bc250_quick_access_helper_test", str(HELPER_SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_saved_cpu_profile_requires_validated_root_payload(helper_module, tmp_path, monkeypatch):
    config = tmp_path / "bc250-smu-oc.conf"
    cpu_helper = tmp_path / "bc250-cpu-smu-helper"
    config.write_text(
        "[overclock]\nfrequency = 3510\nscale = -30\nmax_temperature = 85\n",
        encoding="utf-8",
    )
    cpu_helper.write_text("payload", encoding="utf-8")
    monkeypatch.setattr(helper_module, "CPU_CONFIG", config)
    monkeypatch.setattr(helper_module, "CPU_HELPER", cpu_helper)
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, **_kwargs: path in {config, cpu_helper})

    assert helper_module.cpu_saved_profile() == {
        "frequency": 3510,
        "scale": -30,
        "temperature": 85,
    }

    config.write_text(
        "[overclock]\nfrequency = 3510\nscale = 2\nmax_temperature = 85\n",
        encoding="utf-8",
    )
    assert helper_module.cpu_saved_profile() is None


def test_cpu_telemetry_is_a_bounded_read_only_sample(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "cpu_frequency_mhz", lambda: 3812)
    monkeypatch.setattr(helper_module, "cpu_temperature_c", lambda: 58.25)
    monkeypatch.setattr(helper_module, "trusted_file", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(helper_module.time, "time", lambda: 123.456)

    assert helper_module.cpu_telemetry() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "protocol": helper_module.HELPER_PROTOCOL,
        "cpu_frequency_mhz": 3812,
        "cpu_temperature_c": 58.25,
        "cpu_tuning_ready": True,
        "cpu_tuning_temperature": 90,
        "observed_at": 123456,
    }


def test_memory_status_separates_zram_backing_swap_and_ttm(helper_module, tmp_path):
    swaps = tmp_path / "swaps"
    zswap = tmp_path / "zswap"
    pages = tmp_path / "pages"
    swaps.write_text(
        "Filename Type Size Used Priority\n"
        "/dev/zram0 partition 8388608 0 100\n"
        "/var/swap/swapfile file 16777216 0 -2\n",
        encoding="utf-8",
    )
    zswap.write_text("N\n", encoding="ascii")
    pages.write_text("3145728\n", encoding="ascii")

    state = helper_module.memory_runtime_state(swaps, zswap, pages)

    assert state["memory_zram_total_bytes"] == 8 * 1024 ** 3
    assert state["memory_backing_swap_total_bytes"] == 16 * 1024 ** 3
    assert state["memory_zswap_enabled"] is False
    assert state["memory_ttm_limit_bytes"] == 12 * 1024 ** 3


def test_bazzite_is_a_supported_quick_access_runtime(helper_module, monkeypatch):
    monkeypatch.setattr(helper_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper_module, "is_steamos", lambda: False)
    monkeypatch.setattr(helper_module, "is_bazzite", lambda: True)
    monkeypatch.setattr(helper_module, "bc250_present", lambda: True)

    assert helper_module.require_runtime() == ""


def test_other_non_systemd_distributions_remain_blocked_from_quick_access_controls(helper_module, monkeypatch):
    monkeypatch.setattr(helper_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper_module, "is_steamos", lambda: False)
    monkeypatch.setattr(helper_module, "is_bazzite", lambda: False)
    monkeypatch.setattr(helper_module, "is_cachyos", lambda: False)
    original_path = helper_module.pathlib.Path
    monkeypatch.setattr(
        helper_module.pathlib,
        "Path",
        lambda value: type("RuntimePath", (), {"is_dir": lambda self: False})()
        if value == "/run/systemd/system" else original_path(value),
    )

    assert "no supported systemd runtime" in helper_module.require_runtime()


def test_cachyos_is_a_supported_quick_access_runtime(helper_module, monkeypatch):
    monkeypatch.setattr(helper_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper_module, "is_steamos", lambda: False)
    monkeypatch.setattr(helper_module, "is_bazzite", lambda: False)
    monkeypatch.setattr(helper_module, "is_cachyos", lambda: True)
    monkeypatch.setattr(helper_module, "bc250_present", lambda: True)

    assert helper_module.require_runtime() == ""


def test_known_game_mode_distribution_without_systemd_is_blocked(helper_module, monkeypatch):
    monkeypatch.setattr(helper_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper_module, "is_steamos", lambda: False)
    monkeypatch.setattr(helper_module, "is_bazzite", lambda: False)
    monkeypatch.setattr(helper_module, "is_cachyos", lambda: True)
    monkeypatch.setattr(helper_module, "bc250_present", lambda: True)
    original_path = helper_module.pathlib.Path
    monkeypatch.setattr(
        helper_module.pathlib,
        "Path",
        lambda value: type("RuntimePath", (), {"is_dir": lambda self: False, "is_file": lambda self: False})()
        if value in {"/run/systemd/system", "/usr/bin/systemctl"} else original_path(value),
    )

    assert "no supported systemd runtime" in helper_module.require_runtime()


def test_system_fan_preset_only_writes_system_bank_and_reads_back(helper_module, tmp_path, monkeypatch, capsys):
    sensor = tmp_path / "hwmon7"
    sensor.mkdir()
    for channel in (3, 4):
        (sensor / f"pwm{channel}").write_text("214\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("2\n", encoding="ascii")
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)

    assert helper_module.fan_system_preset("balanced") == 0
    assert (sensor / "pwm3").read_text(encoding="ascii").strip() == "153"
    assert (sensor / "pwm4").read_text(encoding="ascii").strip() == "153"
    assert (sensor / "pwm3_enable").read_text(encoding="ascii").strip() == "1"
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["preset"] == "balanced"
    assert [(entry["channel"], entry["mode_attempts"], entry["duty_attempts"]) for entry in payload["pwm_verification"]] == [(3, 1, 1), (4, 1, 1)]
    assert all(entry["duty_settle_ms"] >= 0 for entry in payload["pwm_verification"])

    assert helper_module.fan_system_preset("automatic") == 0
    assert (sensor / "pwm3_enable").read_text(encoding="ascii").strip() == "2"


def test_qam_sensor_selection_prefers_the_richest_selectable_nct_surface(helper_module, tmp_path):
    hwmon = tmp_path / "hwmon"
    sparse = hwmon / "hwmon1"
    rich = hwmon / "hwmon8"
    sparse.mkdir(parents=True)
    rich.mkdir()
    for sensor in (sparse, rich):
        (sensor / "name").write_text("nct6687\n", encoding="ascii")
    # A lexical-first choice would select hwmon1 despite it not implementing
    # the QAM contract.  The selected surface needs PWM2 plus the other
    # bounded QAM channels and a live fan input.
    (sparse / "pwm1").write_text("100\n", encoding="ascii")
    for channel in (2, 3, 4, 5):
        (rich / f"pwm{channel}").write_text("100\n", encoding="ascii")
        (rich / f"pwm{channel}_enable").write_text("2\n", encoding="ascii")
    (rich / "fan2_input").write_text("1500\n", encoding="ascii")

    assert helper_module.nct_sensor(hwmon) == rich


def test_pwm_verification_retries_duty_after_mode_transition(helper_module, monkeypatch):
    class DelayedPWM:
        def __init__(self):
            self.observations = iter(("127\n", "127\n", "153\n"))

        def read_text(self, **_kwargs):
            return next(self.observations)

    sleeps = []
    rewrites = []
    clock = iter((10.0, 10.101))
    monkeypatch.setattr(helper_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(helper_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(helper_module, "write_sysfs", lambda path, payload: rewrites.append((path, payload)))
    pwm = DelayedPWM()

    matched, observed, attempts, elapsed_ms = helper_module.wait_for_sysfs_value(
        pwm,
        "153",
        retry_payload="153\n",
    )

    assert matched is True
    assert observed == "153"
    assert attempts == 3
    assert elapsed_ms == pytest.approx(101.0)
    assert sleeps == [0.1, 0.1]
    assert rewrites == [(pwm, "153\n"), (pwm, "153\n")]


def test_pwm_verification_remains_bounded_when_hardware_never_settles(helper_module, monkeypatch):
    class StuckPWM:
        def read_text(self, **_kwargs):
            return "127\n"

    sleeps = []
    rewrites = []
    clock = iter((20.0, 20.25))
    monkeypatch.setattr(helper_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(helper_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(helper_module, "write_sysfs", lambda path, payload: rewrites.append((path, payload)))

    matched, observed, attempts, elapsed_ms = helper_module.wait_for_sysfs_value(
        StuckPWM(),
        "153",
        retry_payload="153\n",
        attempts=3,
        interval=0.05,
    )

    assert matched is False
    assert observed == "127"
    assert attempts == 3
    assert elapsed_ms == pytest.approx(250.0)
    assert sleeps == [0.05, 0.05]
    assert len(rewrites) == 2


def test_system_fan_preset_ignores_unwired_zero_pwm_channels(helper_module, tmp_path, monkeypatch, capsys):
    sensor = tmp_path / "hwmon9"
    sensor.mkdir()
    for channel, duty in ((3, 214), (4, 214), (6, 0), (7, 0)):
        (sensor / f"pwm{channel}").write_text(f"{duty}\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("2\n", encoding="ascii")
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)

    assert helper_module.system_fan_channels(sensor) == [3, 4]
    assert helper_module.fan_system_preset("quiet") == 0
    assert (sensor / "pwm3").read_text(encoding="ascii").strip() == "102"
    assert (sensor / "pwm4").read_text(encoding="ascii").strip() == "102"
    assert (sensor / "pwm6").read_text(encoding="ascii").strip() == "0"
    assert "[3, 4]" in capsys.readouterr().out


def test_system_fan_failure_requests_automatic_fallback_for_entire_bank(
    helper_module, tmp_path, monkeypatch, capsys
):
    sensor = tmp_path / "hwmon10"
    sensor.mkdir()
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)
    monkeypatch.setattr(helper_module, "system_fan_channels", lambda _sensor: [3, 4, 5])
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)
    writes = []
    monkeypatch.setattr(
        helper_module,
        "write_sysfs",
        lambda path, payload: writes.append((path.name, payload)),
    )
    reads = iter(
        (
            (True, "1", 1, 0.0),
            (True, "1", 1, 0.0),
            (True, "1", 1, 0.0),
            (True, "153", 1, 0.0),
            (False, "204", 16, 1500.0),
        )
    )
    monkeypatch.setattr(helper_module, "wait_for_sysfs_value", lambda *_args, **_kwargs: next(reads))

    assert helper_module.fan_system_preset("balanced") == 48
    assert writes[-3:] == [
        ("pwm3_enable", "2\n"),
        ("pwm4_enable", "2\n"),
        ("pwm5_enable", "2\n"),
    ]
    assert "Automatic fallback requested for PWM [3, 4, 5]" in capsys.readouterr().err


def test_system_fan_state_reports_a_named_manual_preset(helper_module, tmp_path, monkeypatch):
    sensor = tmp_path / "hwmon11"
    sensor.mkdir()
    for channel in (3, 4):
        (sensor / f"pwm{channel}").write_text("153\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("1\n", encoding="ascii")
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)

    assert helper_module.system_fan_preset_state(sensor) == ("balanced", 153)


def test_gpu_profile_resets_adaptive_mode_when_cyan_bounds_already_match(helper_module, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(helper_module, "run", lambda command, **_kwargs: calls.append(command) or type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(helper_module, "cyan_range", lambda: (1000, 1850))
    monkeypatch.setattr(helper_module, "cyan_performance_enabled", lambda: False)
    monkeypatch.setattr(helper_module, "cyan_allowed_range", lambda: (500, 2400))
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "cyan")

    assert helper_module.gpu_profile("gaming") == 0
    assert sum("SetRange" in command for command in calls) == 1
    assert '"gpu_performance_enabled": false' in capsys.readouterr().out


def test_decky_reads_cyan_after_all_four_desktop_compatibility_controls_change(
    helper_module, tmp_path, monkeypatch
):
    from bc250cc.infrastructure.gpu.governor_toml import GovernorTomlEditor

    config = tmp_path / "config.toml"
    config.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = true\n"
        'method = "busy-flag"\n\n'
        "[gpu]\n"
        'set-method = "smu"\n\n'
        "[[safe-points]]\n"
        "frequency = 2000\n"
        "voltage = 990\n\n"
        "[[safe-points]]\n"
        "frequency = 2050\n"
        "voltage = 1010\n",
        encoding="utf-8",
    )
    GovernorTomlEditor(config).set_cyan_compatibility(
        set_method="kernel",
        usage_method="kernel",
        fix_metrics=False,
        fix_frequency=False,
    )
    monkeypatch.setattr(helper_module, "trusted_directory", lambda *_args: True)
    monkeypatch.setattr(helper_module, "trusted_file", lambda *_args, **_kwargs: True)

    assert helper_module.cyan_set_method(config) == "kernel"
    assert helper_module.cyan_safe_point_ceilings(config) == (
        {"frequency": 2050, "voltage": 1010},
    )


def test_same_range_leaves_fixed_mode_instead_of_false_noop(helper_module, monkeypatch):
    calls = []
    monkeypatch.setattr(helper_module, "cyan_range", lambda: (1000, 1850))
    monkeypatch.setattr(helper_module, "cyan_performance_enabled", lambda: True)
    monkeypatch.setattr(helper_module, "cyan_allowed_range", lambda: (500, 2400))
    monkeypatch.setattr(helper_module, "run", lambda command, **kw: calls.append(command) or subprocess.CompletedProcess(command, 0, "", ""))
    assert helper_module.set_cyan_range((1000, 1850)) == 0
    assert any("SetRange" in command for command in calls)


def test_oberon_idle_benchmark_can_return_to_lower_profile(helper_module, monkeypatch):
    from bc250cc.domain.gpu.oberon import (
        OBERON_IDLE_MAX_BUSY_PERCENT,
        OBERON_IDLE_MAX_CLOCK_MHZ,
    )

    assert helper_module.OBERON_IDLE_MAX_BUSY_PERCENT == OBERON_IDLE_MAX_BUSY_PERCENT
    assert helper_module.OBERON_IDLE_MAX_CLOCK_MHZ == OBERON_IDLE_MAX_CLOCK_MHZ
    monkeypatch.setattr(helper_module, "gpu_busy_percent", lambda: 0)
    monkeypatch.setattr(helper_module, "gpu_core_mhz", lambda: 2000)
    monkeypatch.setattr(helper_module.time, "sleep", lambda seconds: None)
    assert helper_module.oberon_idle_transition_ready()[0]
    monkeypatch.setattr(helper_module, "gpu_busy_percent", lambda: 99)
    assert not helper_module.oberon_idle_transition_ready()[0]


def test_gpu_profile_waits_for_the_verified_cyan_range(helper_module, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **_kwargs: calls.append(command) or type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    ranges = iter(((500, 1500), (1000, 2000)))
    monkeypatch.setattr(helper_module, "cyan_range", lambda: next(ranges))
    monkeypatch.setattr(helper_module, "cyan_allowed_range", lambda: (500, 2000))
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "cyan")
    monkeypatch.setattr(helper_module, "cyan_set_method", lambda: "kernel")
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)

    assert helper_module.gpu_profile("benchmark") == 0
    assert any(command[:3] == ["/usr/bin/busctl", "--system", "call"] for command in calls)
    assert '"gpu_range": [1000, 2000]' in capsys.readouterr().out


def test_quick_access_uses_live_allowed_range_for_smu(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "cyan_range", lambda: (1000, 1850))
    monkeypatch.setattr(helper_module, "cyan_allowed_range", lambda: (500, 2400))
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "cyan")
    monkeypatch.setattr(helper_module, "run", lambda *_args, **_kwargs: type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    ranges = iter(((1000, 1850), (1000, 2000)))
    monkeypatch.setattr(helper_module, "cyan_range", lambda: next(ranges))

    assert helper_module.set_cyan_range((1000, 2000)) == 0


def test_cyan_recovery_profile_was_removed(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "cyan")
    assert helper_module.gpu_profile("recovery") == 20
    assert "unknown profile" in capsys.readouterr().err


def test_cyan_high_ceilings_require_active_level_three_curve(helper_module, tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[[safe-points]]
frequency = 2000
voltage = 990
[[safe-points]]
frequency = 2050
voltage = 1010
[[safe-points]]
frequency = 2100
voltage = 1029
# [[safe-points]]
# frequency = 2400
# voltage = 1210
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(helper_module, "trusted_directory", lambda path: path == tmp_path)
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, **_kwargs: path == config)

    assert helper_module.cyan_safe_point_ceilings(config) == (
        {"frequency": 2050, "voltage": 1010},
    )


def test_gpu_toml_safe_point_rejects_unadvertised_frequency(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "cyan")
    monkeypatch.setattr(
        helper_module,
        "cyan_safe_point_ceilings",
        lambda: ({"frequency": 2050, "voltage": 1040},),
    )

    assert helper_module.gpu_safe_point("2400") == 20
    assert "not available" in capsys.readouterr().err


def test_gpu_toml_safe_point_uses_desktop_floor_and_verified_profile_path(
    helper_module, monkeypatch
):
    monkeypatch.setattr(
        helper_module,
        "cyan_safe_point_ceilings",
        lambda: ({"frequency": 2050, "voltage": 1040},),
    )
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "cyan")
    observed = []
    monkeypatch.setattr(
        helper_module,
        "apply_gpu_range",
        lambda requested: observed.append(requested) or 0,
    )

    assert helper_module.gpu_safe_point("2050") == 0
    assert observed == [(1000, 2050)]


def test_active_gpu_governor_fails_closed_on_conflict(helper_module, monkeypatch):
    states = {helper_module.CYAN_SERVICE: True, helper_module.OBERON_SERVICE: True}
    monkeypatch.setattr(helper_module, "service_active", lambda service: states[service])
    assert helper_module.active_gpu_governor() == "conflict"


def test_oberon_state_accepts_upstream_sequence_layout(helper_module, tmp_path, monkeypatch):
    config = tmp_path / "oberon-config.yaml"
    config.write_text(
        "opps:\n"
        "  - frequency:\n"
        "    - min: 1000\n"
        "    - max: 2200\n"
        "  - voltage:\n"
        "    - min: 920\n"
        "    - max: 1050\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(helper_module, "trusted_directory", lambda path: path == tmp_path)
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, **_kwargs: path == config)
    assert helper_module.oberon_state(config) == {
        "frequency_min": 1000,
        "frequency_max": 2200,
        "voltage_min": 920,
        "voltage_max": 1050,
    }


def test_oberon_profile_uses_protected_editor_restarts_and_verifies(
    helper_module, monkeypatch, capsys
):
    before = {
        "frequency_min": 500, "frequency_max": 1500,
        "voltage_min": 920, "voltage_max": 920,
    }
    expected = {
        "frequency_min": 1000, "frequency_max": 1850,
        "voltage_min": 1000, "voltage_max": 1000,
    }
    states = iter((before, expected, expected))
    monkeypatch.setattr(helper_module, "oberon_state", lambda: next(states))
    monkeypatch.setattr(helper_module, "trusted_file", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(helper_module, "oberon_idle_transition_ready", lambda: (True, "idle"))
    monkeypatch.setattr(helper_module, "service_active", lambda service: service == helper_module.OBERON_SERVICE)
    calls = []
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **_kwargs: calls.append(command) or type(
            "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )(),
    )

    assert helper_module.set_oberon_range((1000, 1850)) == 0
    assert calls[0] == [
        str(helper_module.GOVERNOR_CONFIG_HELPER), "set-oberon-operating-points",
        "1000", "1850", "1000", "1000",
    ]
    assert calls[1] == ["/usr/bin/systemctl", "restart", helper_module.OBERON_SERVICE]
    assert '"gpu_governor": "oberon"' in capsys.readouterr().out


def test_oberon_qam_rejects_ranges_outside_its_three_conservative_profiles(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "trusted_file", lambda *_args, **_kwargs: True)
    assert helper_module.set_oberon_range((1000, 2200)) == 22
    assert "only 1000-1500, 1000-1850 or 1000-2000 MHz" in capsys.readouterr().err


def test_oberon_has_no_advanced_safe_points_in_quick_access(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "oberon")
    assert helper_module.gpu_safe_point("2200") == 20
    assert "does not expose advanced TOML frequencies" in capsys.readouterr().err


def test_oberon_named_profiles_include_the_conservative_benchmark_profile(helper_module, monkeypatch):
    observed = []
    monkeypatch.setattr(helper_module, "active_gpu_governor", lambda: "oberon")
    monkeypatch.setattr(helper_module, "apply_gpu_range", lambda requested: observed.append(requested) or 0)
    assert helper_module.gpu_profile("oberon-1500") == 0
    assert helper_module.gpu_profile("oberon-1850") == 0
    assert helper_module.gpu_profile("oberon-2000") == 0
    assert observed == [(1000, 1500), (1000, 1850), (1000, 2000)]


def test_oberon_change_is_blocked_before_any_write_when_gpu_is_active(helper_module, monkeypatch, capsys):
    before = {
        "frequency_min": 1000, "frequency_max": 2000,
        "voltage_min": 920, "voltage_max": 960,
    }
    monkeypatch.setattr(helper_module, "trusted_file", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(helper_module, "oberon_state", lambda: before)
    monkeypatch.setattr(helper_module, "oberon_idle_transition_ready", lambda: (False, "GPU is active (87% load, 1850 MHz)"))
    monkeypatch.setattr(helper_module, "run", lambda *_args, **_kwargs: pytest.fail("active Oberon must not be rewritten"))
    assert helper_module.set_oberon_range((1000, 1850)) == 25
    assert "return to 1000 MHz" in capsys.readouterr().err


def test_oberon_idle_gate_requires_clock_load_and_multiple_clean_samples(helper_module, monkeypatch):
    loads = iter((2, 1, 0))
    clocks = iter((1000, 1000, 1000))
    monkeypatch.setattr(helper_module, "gpu_busy_percent", lambda: next(loads))
    monkeypatch.setattr(helper_module, "gpu_core_mhz", lambda: next(clocks))
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)
    assert helper_module.oberon_idle_transition_ready() == (True, "GPU remained idle across 3 samples")


def test_oberon_idle_gate_uses_exact_idle_clock_when_busy_metric_is_missing(helper_module, monkeypatch):
    clocks = iter((1000, 1000, 1000))
    monkeypatch.setattr(helper_module, "gpu_busy_percent", lambda: None)
    monkeypatch.setattr(helper_module, "gpu_core_mhz", lambda: next(clocks))
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)
    ready, detail = helper_module.oberon_idle_transition_ready()
    assert ready is True
    assert detail == "GPU remained idle across 3 samples"


def test_gpu_dashboard_metrics_are_read_from_the_amd_device(helper_module, tmp_path):
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n", encoding="ascii")
    (device / "pp_dpm_mclk").write_text(
        "0: 96Mhz\n1: 800Mhz *\n",
        encoding="ascii",
    )
    (device / "gpu_busy_percent").write_text("37\n", encoding="ascii")
    (device / "mem_info_vram_used").write_text(str(1536 * 1048576), encoding="ascii")
    (device / "mem_info_vram_total").write_text(str(16384 * 1048576), encoding="ascii")

    assert helper_module.gpu_memory_clock_mhz(tmp_path) == 800
    assert helper_module.gpu_busy_percent(tmp_path) == 37
    assert helper_module.gpu_vram_usage_mib(tmp_path) == (1536, 16384)


def test_cu_dashboard_parser_requires_one_valid_authoritative_total(helper_module):
    assert helper_module.parse_cu_dashboard_count("\n CUs active & routed : 40/40\n") == (40, 40)
    assert helper_module.parse_cu_dashboard_count("CUs active & routed : 24/40\nCUs active & routed : 24/40") is None
    assert helper_module.parse_cu_dashboard_count("CUs active & routed : 41/40") is None


def cu_dashboard(masks):
    rows = []
    total = 0
    for row, mask in enumerate(masks):
        se, sh = divmod(row, 2)
        tokens = ["D+" if mask & (1 << wgp) else "--" for wgp in range(5)]
        cus = int(mask).bit_count() * 2
        total += cus
        rows.append(
            f"| SE{se}.SH{sh} | " + " | ".join(tokens)
            + f" | 0x{mask:02x} | 0xffe00000 | {cus}/10 |"
        )
    return "\n".join((*rows, f"CUs active & routed : {total}/40"))


def test_cu_topology_parser_requires_complete_consistent_rows(helper_module):
    topology = helper_module.parse_cu_topology(cu_dashboard((0x07,) * 4))

    assert topology is not None
    assert topology["masks"] == (0x07, 0x07, 0x07, 0x07)
    assert topology["active_cus"] == 24

    wrong_total = cu_dashboard((0x07,) * 4).replace("24/40", "40/40")
    assert helper_module.parse_cu_topology(wrong_total) is None
    wrong_spi = cu_dashboard((0x07,) * 4).replace("0x07", "0x1f", 1)
    assert helper_module.parse_cu_topology(wrong_spi) is None
    missing_row = "\n".join(cu_dashboard((0x07,) * 4).splitlines()[1:])
    assert helper_module.parse_cu_topology(missing_row) is None


def test_cu_topology_parser_preserves_desktop_driver_and_spi_semantics(helper_module):
    rows = "\n".join(
        f"| SE{se}.SH{sh} | D+ | D+ | D+ | S+ | S+ | 0x1f | 0xffe00000 | 10/10 |"
        for se in range(2) for sh in range(2)
    )
    topology = helper_module.parse_cu_topology(
        rows + "\nCUs active & routed : 40/40"
    )

    assert topology is not None
    assert topology["masks"] == (0x1F, 0x1F, 0x1F, 0x1F)
    assert topology["driver_masks"] == (0x07, 0x07, 0x07, 0x07)
    assert topology["tokens"][0] == ("D+", "D+", "D+", "S+", "S+")


def test_cu_live_snapshot_is_atomic_schema_versioned_and_contains_verified_state(
    helper_module, tmp_path
):
    raw_dashboard = cu_dashboard((0x0F, 0x07, 0x07, 0x07))
    topology = helper_module.parse_cu_topology(raw_dashboard)
    assert topology is not None
    boot_id = tmp_path / "boot_id"
    boot_id.write_text("01234567-89ab-cdef-0123-456789abcdef\n", encoding="ascii")
    destination = tmp_path / "run" / "bc250-control-center" / "cu-live-state.json"
    persistence = {
        "cu_service_installed": True,
        "cu_service_enabled": True,
        "cu_service_active": False,
        "cu_boot_saved": True,
        "cu_saved_masks": [15, 7, 7, 7],
    }

    published, warning = helper_module.publish_cu_live_state(
        topology,
        persistence,
        raw_dashboard=raw_dashboard,
        path=destination,
        boot_id_path=boot_id,
    )

    assert published is True
    assert warning == ""
    snapshot = json.loads(destination.read_text(encoding="utf-8"))
    assert snapshot == {
        "schema": 1,
        "producer": "bc250-quick-access-helper",
            "helper_protocol": 13,
        "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
        "observed_at_unix_ms": snapshot["observed_at_unix_ms"],
        "raw_dashboard": raw_dashboard,
        "cu_masks": [15, 7, 7, 7],
        "cu_driver_masks": [15, 7, 7, 7],
        "cu_tokens": [
            ["D+", "D+", "D+", "D+", "--"],
            ["D+", "D+", "D+", "--", "--"],
            ["D+", "D+", "D+", "--", "--"],
            ["D+", "D+", "D+", "--", "--"],
        ],
        "cu_active_cus": 26,
        "cu_total_cus": 40,
        "cu_saved_masks": [15, 7, 7, 7],
        "cu_service_installed": True,
        "cu_service_enabled": True,
        "cu_service_active": False,
        "cu_boot_saved": True,
    }
    assert type(snapshot["observed_at_unix_ms"]) is int
    assert destination.parent.stat().st_mode & 0o777 == 0o755
    assert destination.stat().st_mode & 0o777 == 0o644
    assert not list(destination.parent.glob(".cu-live-state-*"))


def test_cu_live_snapshot_rejects_an_existing_symlink_without_touching_target(
    helper_module, tmp_path
):
    raw_dashboard = cu_dashboard((0x07,) * 4)
    topology = helper_module.parse_cu_topology(raw_dashboard)
    assert topology is not None
    boot_id = tmp_path / "boot_id"
    boot_id.write_text("01234567-89ab-cdef-0123-456789abcdef\n", encoding="ascii")
    destination = tmp_path / "run" / "bc250-control-center" / "cu-live-state.json"
    destination.parent.mkdir(parents=True, mode=0o755)
    destination.parent.chmod(0o755)
    target = tmp_path / "untrusted-target.json"
    target.write_text("do not replace", encoding="utf-8")
    destination.symlink_to(target)

    published, warning = helper_module.publish_cu_live_state(
        topology,
        {
            "cu_service_installed": False,
            "cu_service_enabled": False,
            "cu_service_active": False,
            "cu_boot_saved": False,
            "cu_saved_masks": None,
        },
        raw_dashboard=raw_dashboard,
        path=destination,
        boot_id_path=boot_id,
    )

    assert published is False
    assert "existing output is not protected" in warning
    assert target.read_text(encoding="utf-8") == "do not replace"


def test_cu_live_snapshot_rejects_raw_dashboard_that_does_not_match_verified_masks(
    helper_module, tmp_path
):
    raw_dashboard = cu_dashboard((0x0F, 0x07, 0x07, 0x07))
    topology = helper_module.parse_cu_topology(raw_dashboard)
    assert topology is not None
    boot_id = tmp_path / "boot_id"
    boot_id.write_text("01234567-89ab-cdef-0123-456789abcdef\n", encoding="ascii")
    destination = tmp_path / "run" / "bc250-control-center" / "cu-live-state.json"
    persistence = {
        "cu_service_installed": False,
        "cu_service_enabled": False,
        "cu_service_active": False,
        "cu_boot_saved": False,
        "cu_saved_masks": None,
    }

    published, warning = helper_module.publish_cu_live_state(
        topology,
        persistence,
        raw_dashboard=cu_dashboard((0x1F, 0x07, 0x07, 0x07)),
        path=destination,
        boot_id_path=boot_id,
    )

    assert published is False
    assert "does not match" in warning
    assert not destination.exists()


def test_canonical_cu_targets_are_distributed_across_rows(helper_module):
    assert helper_module.canonical_cu_masks(24) == (0x07, 0x07, 0x07, 0x07)
    assert helper_module.canonical_cu_masks(26) == (0x0F, 0x07, 0x07, 0x07)
    assert helper_module.canonical_cu_masks(32) == (0x0F, 0x0F, 0x0F, 0x0F)
    assert helper_module.canonical_cu_masks(34) == (0x1F, 0x0F, 0x0F, 0x0F)
    assert helper_module.canonical_cu_masks(40) == (0x1F, 0x1F, 0x1F, 0x1F)


def test_run_merges_explicit_environment_into_minimal_trusted_base(helper_module, monkeypatch):
    captured = {}

    def fake_subprocess_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(helper_module.subprocess, "run", fake_subprocess_run)

    helper_module.run(
        ["/usr/bin/example"],
        extra_env={"UMR_DATABASE_PATH": "/trusted/database"},
    )

    assert captured["env"] == {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "UMR_DATABASE_PATH": "/trusted/database",
    }


def test_cu_dashboard_uses_staged_database_environment(helper_module, monkeypatch):
    calls = []
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output = cu_dashboard((0x07,) * 4)
        return type("Result", (), {"returncode": 0, "stdout": output, "stderr": ""})()

    monkeypatch.setattr(helper_module, "run", fake_run)

    assert helper_module.cu_dashboard_state() == (24, 40)
    assert calls == [
        (
            [str(helper_module.CU_BACKEND), "status"],
            {
                "timeout": 45,
                "extra_env": {},
            },
        )
    ]


def test_cu_mode_applies_a_complete_table_and_verifies_all_four_masks(
    helper_module, monkeypatch, capsys
):
    before_masks = (0x07, 0x0F, 0x1F, 0x07)
    requested_masks = (0x0F,) * 4
    outputs = iter((cu_dashboard(before_masks), "", "", cu_dashboard(requested_masks)))
    calls = []
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    monkeypatch.setattr(helper_module, "cu_service_state", dict)
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or type("Result", (), {"returncode": 0, "stdout": next(outputs), "stderr": ""})(),
    )

    assert helper_module.cu_mode("32") == 0
    expected_environment = {}
    assert calls == [
        ([str(helper_module.CU_BACKEND), "status"], {"timeout": 45, "extra_env": expected_environment}),
        (
            [
                str(helper_module.CU_BACKEND), "--yes", "disable-wgp",
                "1.0.4",
            ],
            {"timeout": 180, "extra_env": expected_environment},
        ),
        (
            [
                str(helper_module.CU_BACKEND), "--yes", "enable-wgp",
                "0.0.3", "1.1.3",
            ],
            {"timeout": 180, "extra_env": expected_environment},
        ),
        ([str(helper_module.CU_BACKEND), "status"], {"timeout": 45, "extra_env": expected_environment}),
    ]
    assert '"cu_active_cus": 32' in capsys.readouterr().out


def test_cu_mode_is_a_true_noop_when_target_is_already_active(helper_module, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    monkeypatch.setattr(helper_module, "cu_service_state", dict)
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or type("Result", (), {
            "returncode": 0,
            "stdout": cu_dashboard((0x1F, 0x1F, 0x1F, 0x0F)),
            "stderr": "",
        })(),
    )
    assert helper_module.cu_mode("38") == 0
    assert len(calls) == 1
    assert '"unchanged": true' in capsys.readouterr().out


def test_verified_cu_table_surfaces_snapshot_failure_without_failing_hardware(
    helper_module, monkeypatch, capsys
):
    before_masks = (0x07, 0x07, 0x07, 0x07)
    requested = (0x0F, 0x07, 0x07, 0x07)
    outputs = iter((cu_dashboard(before_masks), "", cu_dashboard(requested)))
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    monkeypatch.setattr(
        helper_module,
        "cu_service_state",
        lambda: {
            "cu_service_installed": False,
            "cu_service_enabled": False,
            "cu_service_active": False,
            "cu_boot_saved": False,
            "cu_saved_masks": None,
        },
    )
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda _command, **_kwargs: type(
            "Result", (), {"returncode": 0, "stdout": next(outputs), "stderr": ""}
        )(),
    )
    monkeypatch.setattr(
        helper_module,
        "publish_cu_live_state",
        lambda *_args, **_kwargs: (False, "runtime snapshot temporarily unavailable"),
    )

    assert helper_module.cu_table(requested) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cu_masks"] == [15, 7, 7, 7]
    assert payload["cu_snapshot_published"] is False
    assert payload["cu_snapshot_warning"] == "runtime snapshot temporarily unavailable"
    assert type(payload["observed_at_unix_ms"]) is int


def test_cu_mode_does_not_accept_a_matching_summary_with_wrong_rows(
    helper_module, monkeypatch, capsys
):
    inconsistent = cu_dashboard((0x1F,) * 4).replace("40/40", "32/40")
    calls = []
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    monkeypatch.setattr(helper_module, "cu_service_state", dict)
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **kwargs: calls.append(command)
        or type("Result", (), {"returncode": 0, "stdout": inconsistent, "stderr": ""})(),
    )

    assert helper_module.cu_mode("32") == 32
    assert len(calls) == 1
    assert "complete internally consistent live topology" in capsys.readouterr().err


def test_cu_save_applies_then_verifies_exact_root_owned_boot_masks(
    helper_module, monkeypatch, capsys
):
    before_masks = (0x07, 0x0F, 0x1F, 0x07)
    requested = (0x0F,) * 4
    outputs = iter((cu_dashboard(before_masks), "", "", cu_dashboard(requested), ""))
    calls = []
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    monkeypatch.setattr(helper_module, "saved_cu_masks", lambda: requested)
    monkeypatch.setattr(
        helper_module,
        "cu_service_state",
        lambda: {
            "cu_service_installed": True,
            "cu_service_enabled": True,
            "cu_service_active": True,
            "cu_boot_saved": True,
            "cu_saved_masks": list(requested),
        },
    )
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or type("Result", (), {"returncode": 0, "stdout": next(outputs), "stderr": ""})(),
    )

    assert helper_module.cu_save([str(mask) for mask in requested]) == 0
    assert calls[-1][0] == [
        str(helper_module.CU_BACKEND), "--yes", "write-service-table",
    ]
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["cu_masks"] == list(requested)
    assert payload["cu_saved_masks"] == list(requested)
    assert payload["cu_saved"] is True


def test_cu_install_service_requires_saved_profile_and_verifies_unit(
    helper_module, monkeypatch, capsys
):
    requested = (0x0F,) * 4
    topology = helper_module.parse_cu_topology(cu_dashboard(requested))
    assert topology is not None
    topology["raw_dashboard"] = cu_dashboard(requested)
    service_state = {
        "cu_service_installed": True,
        "cu_service_enabled": True,
        "cu_service_active": False,
        "cu_boot_saved": True,
        "cu_saved_masks": list(requested),
    }
    monkeypatch.setattr(helper_module, "saved_cu_masks", lambda: requested)
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    monkeypatch.setattr(helper_module, "trusted_file", lambda _path, **_kwargs: True)
    monkeypatch.setattr(helper_module, "cu_service_state", lambda: service_state)
    monkeypatch.setattr(helper_module, "cu_dashboard_topology", lambda: topology)
    calls = []
    published = []
    monkeypatch.setattr(
        helper_module,
        "attach_cu_live_state",
        lambda payload, observed: published.append((payload, observed)) or payload,
    )
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    assert helper_module.cu_install_service() == 0
    assert calls == [
        (
            [str(helper_module.CU_BACKEND), "--yes", "install-service"],
            {"timeout": 180, "extra_env": {}},
        )
    ]
    assert __import__("json").loads(capsys.readouterr().out)["cu_service_action"] == "installed"
    assert len(published) == 1
    assert published[0][1] is topology


def test_cu_remove_service_deletes_only_persistence_and_preserves_live_masks(
    helper_module, monkeypatch, tmp_path, capsys
):
    requested = (0x0F,) * 4
    topology = helper_module.parse_cu_topology(cu_dashboard(requested))
    assert topology is not None
    topology["raw_dashboard"] = cu_dashboard(requested)
    unit = tmp_path / "bc250-cu-live-manager.service"
    config = tmp_path / "bc250-cu-live-manager.conf"
    binary = tmp_path / "bc250-cu-live-manager"
    for path in (unit, config, binary):
        path.write_text("known", encoding="utf-8")
    monkeypatch.setattr(helper_module, "CU_SERVICE_UNIT", unit)
    monkeypatch.setattr(helper_module, "CU_SERVICE_CONFIG", config)
    monkeypatch.setattr(helper_module, "CU_SERVICE_BINARIES", (binary,))
    monkeypatch.setattr(helper_module, "cu_dashboard_topology", lambda: topology)
    monkeypatch.setattr(
        helper_module,
        "cu_service_state",
        lambda: {
            "cu_service_installed": False,
            "cu_service_enabled": False,
            "cu_service_active": False,
            "cu_boot_saved": False,
            "cu_saved_masks": None,
        },
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[1:] == ["--yes", "uninstall-service"]:
            for path in (unit, config, binary):
                path.unlink(missing_ok=True)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(
        helper_module,
        "run",
        fake_run,
    )
    monkeypatch.setattr(helper_module, "cu_backend_ready", lambda: True)
    published = []
    monkeypatch.setattr(
        helper_module,
        "attach_cu_live_state",
        lambda payload, observed: published.append((payload, observed)) or payload,
    )

    assert helper_module.cu_remove_service() == 0
    assert all(not path.exists() for path in (unit, config, binary))
    assert calls[0] == (
        [str(helper_module.CU_BACKEND), "--yes", "uninstall-service"],
        {"timeout": 180, "extra_env": {}},
    )
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["cu_live_unchanged"] is True
    assert payload["cu_masks"] == list(requested)
    assert len(published) == 1
    assert published[0][1] is topology


def test_gpu_core_mhz_reads_only_the_marked_amd_dpm_level(helper_module, tmp_path):
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n", encoding="ascii")
    (device / "pp_dpm_sclk").write_text("0: 500Mhz\n1: 2200Mhz *\n", encoding="ascii")
    assert helper_module.gpu_core_mhz(tmp_path) == 2200


def test_gpu_voltage_reads_only_the_labelled_amd_vddgfx_sensor(helper_module, tmp_path):
    device = tmp_path / "card0" / "device"
    sensor = device / "hwmon" / "hwmon3"
    sensor.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n", encoding="ascii")
    (sensor / "in0_label").write_text("vddgfx\n", encoding="ascii")
    (sensor / "in0_input").write_text("960000\n", encoding="ascii")
    (sensor / "in1_label").write_text("vddnb\n", encoding="ascii")
    (sensor / "in1_input").write_text("1100\n", encoding="ascii")
    assert helper_module.gpu_voltage_mv(tmp_path) == 960


def test_gpu_temperature_reads_only_amd_hwmon_edge_temperature(helper_module, tmp_path):
    device = tmp_path / "card0" / "device"
    sensor = device / "hwmon" / "hwmon3"
    sensor.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n", encoding="ascii")
    (sensor / "temp1_input").write_text("63500\n", encoding="ascii")
    assert helper_module.gpu_temperature_c(tmp_path) == 63.5


def test_status_skips_cyan_dbus_reads_when_service_is_inactive(helper_module, monkeypatch, capsys):
    monkeypatch.setattr(helper_module, "cu_dashboard_topology", lambda: None)
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: None)
    monkeypatch.setattr(helper_module, "cpu_saved_profile", lambda: None)
    monkeypatch.setattr(helper_module, "gpu_core_mhz", lambda: None)
    monkeypatch.setattr(helper_module, "gpu_temperature_c", lambda: None)
    monkeypatch.setattr(helper_module, "cpu_frequency_mhz", lambda: None)
    monkeypatch.setattr(helper_module, "cpu_temperature_c", lambda: None)
    monkeypatch.setattr(helper_module, "cyan_range", lambda: pytest.fail("Cyan D-Bus must not be read while inactive"))
    monkeypatch.setattr(helper_module, "cyan_allowed_range", lambda: pytest.fail("Cyan allowed range must not be read while inactive"))
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda _command, **_kwargs: type("Result", (), {"returncode": 3, "stdout": "", "stderr": ""})(),
    )

    assert helper_module.status() == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["cyan_active"] is False
    assert payload["gpu_range"] is None
    assert payload["gpu_allowed_range"] is None


def test_status_exports_only_verified_complete_cu_masks(helper_module, monkeypatch, capsys):
    topology = {
        "masks": (0x0F, 0x07, 0x07, 0x07),
        "driver_masks": (0x07, 0x07, 0x07, 0x07),
        "tokens": (("D+", "D+", "D+", "S+", "--"),) + (("D+", "D+", "D+", "--", "--"),) * 3,
        "active_cus": 26,
        "total_cus": 40,
    }
    topology["raw_dashboard"] = cu_dashboard((0x0F, 0x07, 0x07, 0x07))
    monkeypatch.setattr(helper_module, "cu_dashboard_topology", lambda: topology)
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: None)
    monkeypatch.setattr(helper_module, "cpu_saved_profile", lambda: None)
    monkeypatch.setattr(helper_module, "gpu_core_mhz", lambda: None)
    monkeypatch.setattr(helper_module, "gpu_temperature_c", lambda: None)
    monkeypatch.setattr(helper_module, "cpu_frequency_mhz", lambda: None)
    monkeypatch.setattr(helper_module, "cpu_temperature_c", lambda: None)
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda _command, **_kwargs: type("Result", (), {"returncode": 3, "stdout": "", "stderr": ""})(),
    )
    published = []
    monkeypatch.setattr(
        helper_module,
        "attach_cu_live_state",
        lambda payload, observed: published.append((payload, observed)) or payload,
    )

    assert helper_module.status() == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["cu_active_cus"] == 26
    assert payload["cu_masks"] == [15, 7, 7, 7]
    assert payload["cu_driver_masks"] == [7, 7, 7, 7]
    assert payload["cu_tokens"][0] == ["D+", "D+", "D+", "S+", "--"]
    assert len(published) == 1
    assert published[0][1] is topology


def test_fan_auto_accepts_explicit_pwm2_and_touches_no_other_channel(
    helper_module, tmp_path, monkeypatch, capsys
):
    sensor = tmp_path / "hwmon8"
    sensor.mkdir()
    for channel in (2, 3):
        (sensor / f"pwm{channel}").write_text("153\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("1\n", encoding="ascii")
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)

    assert helper_module.fan_auto("2") == 0
    assert (sensor / "pwm2_enable").read_text(encoding="ascii").strip() == "2"
    assert (sensor / "pwm3_enable").read_text(encoding="ascii").strip() == "1"
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["fan_channel"] == 2
    assert payload["wiring_warning"]


def test_fan_channel_manual_percentage_is_bounded_verified_and_isolated(
    helper_module, tmp_path, monkeypatch, capsys
):
    sensor = tmp_path / "hwmon12"
    sensor.mkdir()
    for channel, duty in ((2, 127), (3, 204)):
        (sensor / f"pwm{channel}").write_text(f"{duty}\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("2\n", encoding="ascii")
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)

    assert helper_module.fan_channel_control("2", "60") == 0
    assert (sensor / "pwm2").read_text(encoding="ascii").strip() == "153"
    assert (sensor / "pwm2_enable").read_text(encoding="ascii").strip() == "1"
    assert (sensor / "pwm3").read_text(encoding="ascii").strip() == "204"
    assert (sensor / "pwm3_enable").read_text(encoding="ascii").strip() == "2"
    payload = __import__("json").loads(capsys.readouterr().out)
    assert (payload["fan_channel"], payload["percent"], payload["duty"]) == (2, 60, 153)
    assert payload["pwm_verification"]["duty_attempts"] == 1


@pytest.mark.parametrize(
    ("channel", "target"),
    [("1", "60"), ("6", "60"), ("2", "0"), ("2", "19"), ("2", "101"), ("2", "50.0"), ("2;id", "60")],
)
def test_fan_channel_rejects_values_outside_closed_protocol(
    helper_module, monkeypatch, channel, target
):
    monkeypatch.setattr(
        helper_module,
        "nct_sensor",
        lambda: pytest.fail("invalid request must not discover or write hardware"),
    )
    assert helper_module.fan_channel_control(channel, target) == 40


def test_fan_channel_failure_restores_only_selected_channel_to_automatic(
    helper_module, tmp_path, monkeypatch, capsys
):
    sensor = tmp_path / "hwmon13"
    sensor.mkdir()
    for channel in (2, 3):
        (sensor / f"pwm{channel}").write_text("204\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("2\n", encoding="ascii")
    monkeypatch.setattr(helper_module, "nct_sensor", lambda: sensor)
    monkeypatch.setattr(helper_module.time, "sleep", lambda _seconds: None)
    writes = []
    monkeypatch.setattr(
        helper_module,
        "write_sysfs",
        lambda path, payload: writes.append((path.name, payload)),
    )
    reads = iter(
        (
            (True, "1", 1, 0.0),
            (False, "204", 16, 1500.0),
            (True, "2", 1, 0.0),
        )
    )
    monkeypatch.setattr(helper_module, "wait_for_sysfs_value", lambda *_args, **_kwargs: next(reads))

    assert helper_module.fan_channel_control("2", "60") == 48
    assert all(name.startswith("pwm2") for name, _payload in writes)
    assert writes[-1] == ("pwm2_enable", "2\n")
    assert '"verified":true' in capsys.readouterr().err


def test_qam_fan_state_reports_pwm2_wiring_uncertainty(helper_module, tmp_path):
    sensor = tmp_path / "hwmon14"
    sensor.mkdir()
    (sensor / "pwm2").write_text("127\n", encoding="ascii")
    (sensor / "pwm2_enable").write_text("2\n", encoding="ascii")

    states = helper_module.qam_fan_channel_state(sensor)

    assert [state["channel"] for state in states] == [2, 3, 4, 5]
    assert states[0]["available"] is True
    assert states[0]["mode"] == "automatic"
    assert states[0]["percent"] == 50
    assert states[0]["wiring_uncertain"] is True
    assert all(state["available"] is False for state in states[1:])


def test_qam_pwm_writer_completes_a_partial_sysfs_write(helper_module, monkeypatch, tmp_path):
    target = tmp_path / "pwm2"
    calls = []

    monkeypatch.setattr(helper_module.os, "open", lambda *_args: 71)
    monkeypatch.setattr(helper_module.os, "close", lambda descriptor: calls.append(("close", descriptor)))

    def partial_write(descriptor, payload):
        calls.append(("write", descriptor, payload))
        return 1

    monkeypatch.setattr(helper_module.os, "write", partial_write)
    helper_module.write_sysfs(target, "153\n")

    writes = [item[2] for item in calls if item[0] == "write"]
    assert writes == [b"153\n", b"53\n", b"3\n", b"\n"]
    assert calls[-1] == ("close", 71)


def test_main_accepts_only_closed_cpu_operations(helper_module, monkeypatch):
    calls = []
    monkeypatch.setattr(helper_module, "require_runtime", lambda: "")
    monkeypatch.setattr(helper_module, "cpu_apply_saved_profile", lambda: calls.append(("saved",)) or 0)
    monkeypatch.setattr(helper_module, "cpu_detect_tuning", lambda frequency, vid: calls.append(("detect", frequency, vid)) or 0)
    monkeypatch.setattr(helper_module, "cpu_apply_manual_scale", lambda frequency, scale: calls.append(("scale", frequency, scale)) or 0)
    monkeypatch.setattr(helper_module, "cpu_install_service", lambda: calls.append(("install",)) or 0)
    monkeypatch.setattr(helper_module, "cpu_remove_service", lambda: calls.append(("remove",)) or 0)

    assert helper_module.main(["helper", "cpu-apply-saved"]) == 0
    assert helper_module.main(["helper", "cpu-detect", "3700", "1200"]) == 0
    assert helper_module.main(["helper", "cpu-scale", "3700", "-30"]) == 0
    assert helper_module.main(["helper", "cpu-service", "install"]) == 0
    assert helper_module.main(["helper", "cpu-service", "remove"]) == 0
    assert calls == [
        ("saved",),
        ("detect", "3700", "1200"),
        ("scale", "3700", "-30"),
        ("install",),
        ("remove",),
    ]
    assert helper_module.main(["helper", "cpu-apply-saved", "unexpected"]) == 2
    assert helper_module.main(["helper", "cpu-detect", "3700"]) == 2
    assert helper_module.main(["helper", "cpu-scale", "3700"]) == 2
    assert helper_module.main(["helper", "cpu-service", "install", "3700"]) == 2


def test_guarded_main_hides_a_missing_protected_component_traceback(
    helper_module, monkeypatch, capsys
):
    monkeypatch.setattr(
        helper_module,
        "main",
        lambda _argv: (_ for _ in ()).throw(
            FileNotFoundError("missing helper payload")
        ),
    )

    assert helper_module.guarded_main(["helper", "status"]) == 70

    error = capsys.readouterr().err
    assert "QUICK_ACCESS_COMPONENT_MISSING" in error
    assert "Reinstall or repair BC250 Control Center" in error
    assert "Traceback" not in error


def test_guarded_main_keeps_expected_runtime_error_actionable(
    helper_module, monkeypatch, capsys
):
    monkeypatch.setattr(
        helper_module,
        "main",
        lambda _argv: (_ for _ in ()).throw(RuntimeError("CPU detector unavailable")),
    )

    assert helper_module.guarded_main(["helper", "status"]) == 71
    assert "QUICK_ACCESS_OPERATION_FAILED: CPU detector unavailable" in capsys.readouterr().err


def test_cpu_detection_candidate_uses_real_frequency_vid_inputs(helper_module, monkeypatch):
    monkeypatch.setattr(helper_module, "cpu_tuning_context", lambda: {"cpu_tuning_ready": True})

    candidate = helper_module.cpu_detection_candidate("3700", "1200")
    assert candidate == {
        "frequency": 3700,
        "vid": 1200,
        "temperature": 90,
    }

    for frequency, vid in (
        ("3499", "1200"),
        ("4201", "1200"),
        ("3725", "1200"),
        ("3700", "949"),
        ("3700", "1326"),
        ("3700", "1201"),
        ("03700", "1200"),
    ):
        with pytest.raises(ValueError):
            helper_module.cpu_detection_candidate(frequency, vid)


def test_cpu_manual_scale_candidate_requires_same_boot_detection_and_exact_frequency(
    helper_module, monkeypatch
):
    detected = {
        "ready": True,
        "frequency": 3700,
        "scale": -34,
        "manual_scale_ready": True,
    }
    monkeypatch.setattr(helper_module, "cpu_qam_detection_state", lambda: detected)

    candidate = helper_module.cpu_scale_candidate("3700", "-30")
    assert candidate == {
        "frequency": 3700,
        "scale": -30,
        "temperature": 90,
        "estimated_vid": helper_module.cpu_estimated_vid(3700, -30),
    }
    for frequency, scale in (("3650", "-30"), ("3700", "-51"), ("3700", "1"), ("3700", "-030")):
        with pytest.raises(ValueError):
            helper_module.cpu_scale_candidate(frequency, scale)

    monkeypatch.setattr(helper_module, "cpu_qam_detection_state", lambda: None)
    with pytest.raises(ValueError, match="automatic CPU detection"):
        helper_module.cpu_scale_candidate("3700", "-30")


def test_cpu_tuning_context_requires_stress_and_never_authorizes_estimated_scale(
    helper_module, monkeypatch
):
    monkeypatch.setattr(
        helper_module,
        "trusted_file",
        lambda path, **_kwargs: path == helper_module.CPU_HELPER or path in helper_module.CPU_STRESS_PATHS,
    )

    assert helper_module.cpu_tuning_context() == {
        "cpu_tuning_ready": True,
        "cpu_tuning_temperature": 90,
        "cpu_tuning_source": "detector-required",
        "cpu_detected_profile": None,
        "cpu_active_profile": None,
        "cpu_manual_scale_ready": False,
        "cpu_tuning_error": None,
    }
    with pytest.raises(ValueError):
        helper_module.cpu_detection_candidate("3700", "-30")


def test_cpu_detection_invokes_only_audited_helper_and_verifies_evidence(
    helper_module, monkeypatch, capsys
):
    candidate = {
        "frequency": 3700,
        "vid": 1200,
        "temperature": 90,
    }
    detected = {
        "ready": True, "same_boot": True, "applied_live": True,
        "requested_frequency": 3700, "requested_vid": 1200,
        "requested_temperature": 90, "frequency": 3700,
        "scale": -30, "temperature": 90,
    }
    calls = []
    monkeypatch.setattr(helper_module, "cpu_detection_candidate", lambda *_args: candidate)
    monkeypatch.setattr(helper_module, "cpu_qam_detection_state", lambda: detected)
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda argv, **kwargs: calls.append((argv, kwargs))
        or subprocess.CompletedProcess(argv, 0, "ok", ""),
    )
    monkeypatch.setattr(
        helper_module,
        "cpu_service_state",
        lambda: {
            "cpu_service_installed": False,
            "cpu_service_enabled": False,
            "cpu_service_active": False,
        },
    )

    assert helper_module.cpu_detect_tuning("3700", "1200") == 0
    assert calls == [
        (
            [str(helper_module.CPU_HELPER), "detect-qam", "3700", "1200", "90"],
            {"timeout": 900},
        )
    ]
    assert json.loads(capsys.readouterr().out)["cpu_applied_profile"] == {
        "frequency": 3700, "scale": -30, "temperature": 90,
    }


def test_cpu_manual_scale_invokes_only_audited_helper_and_verifies_active_evidence(
    helper_module, monkeypatch, capsys
):
    candidate = {
        "frequency": 3700,
        "scale": -30,
        "temperature": 90,
        "estimated_vid": helper_module.cpu_estimated_vid(3700, -30),
    }
    active = {
        "mode": "manual",
        "frequency": 3700,
        "scale": -30,
        "temperature": 90,
        "estimated_vid": candidate["estimated_vid"],
        "persistable": True,
    }
    detected = {"ready": True, "active_profile": active}
    calls = []
    monkeypatch.setattr(helper_module, "cpu_scale_candidate", lambda *_args: candidate)
    monkeypatch.setattr(helper_module, "cpu_qam_detection_state", lambda: detected)
    monkeypatch.setattr(
        helper_module,
        "run",
        lambda argv, **kwargs: calls.append((argv, kwargs))
        or subprocess.CompletedProcess(argv, 0, "ok", ""),
    )
    monkeypatch.setattr(
        helper_module,
        "cpu_service_state",
        lambda: {
            "cpu_service_installed": False,
            "cpu_service_enabled": False,
            "cpu_service_active": False,
        },
    )

    assert helper_module.cpu_apply_manual_scale("3700", "-30") == 0
    assert calls == [
        (
            [str(helper_module.CPU_HELPER), "apply-qam-scale", "3700", "-30", "90"],
            {"timeout": 180},
        )
    ]
    assert json.loads(capsys.readouterr().out)["cpu_active_profile"] == active


def test_main_accepts_only_exact_fan_channel_arity(helper_module, monkeypatch):
    calls = []
    monkeypatch.setattr(helper_module, "require_runtime", lambda: "")
    monkeypatch.setattr(
        helper_module,
        "fan_channel_control",
        lambda channel, target: calls.append((channel, target)) or 0,
    )

    assert helper_module.main(["helper", "fan-channel", "2", "60"]) == 0
    assert calls == [("2", "60")]
    assert helper_module.main(["helper", "fan-channel", "2"]) == 2
    assert helper_module.main(["helper", "fan-channel", "2", "60", "extra"]) == 2


def test_main_accepts_only_four_bounded_cu_table_masks(helper_module, monkeypatch):
    observed = []
    monkeypatch.setattr(helper_module, "require_runtime", lambda: "")
    monkeypatch.setattr(
        helper_module,
        "cu_table",
        lambda masks: observed.append(tuple(masks)) or 0,
    )

    assert helper_module.main(["helper", "cu-table", "15", "15", "7", "7"]) == 0
    assert observed == [("15", "15", "7", "7")]
    assert helper_module.main(["helper", "cu-table", "15", "15", "7"]) == 2
    assert helper_module.main(["helper", "cu-table", "15", "15", "7", "7", "7"]) == 2


def test_main_accepts_only_closed_cu_persistence_actions(helper_module, monkeypatch):
    calls = []
    monkeypatch.setattr(helper_module, "require_runtime", lambda: "")
    monkeypatch.setattr(
        helper_module,
        "cu_save",
        lambda masks: calls.append(("save", tuple(masks))) or 0,
    )
    monkeypatch.setattr(
        helper_module,
        "cu_install_service",
        lambda: calls.append(("service", "install")) or 0,
    )
    monkeypatch.setattr(
        helper_module,
        "cu_remove_service",
        lambda: calls.append(("service", "remove")) or 0,
    )

    assert helper_module.main(["helper", "cu-save", "15", "15", "7", "7"]) == 0
    assert helper_module.main(["helper", "cu-service", "install"]) == 0
    assert helper_module.main(["helper", "cu-service", "remove"]) == 0
    assert calls == [
        ("save", ("15", "15", "7", "7")),
        ("service", "install"),
        ("service", "remove"),
    ]
    assert helper_module.main(["helper", "cu-service", "restart"]) == 2
    assert helper_module.main(["helper", "cu-save", "15", "15", "7"]) == 2
