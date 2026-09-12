from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.platform.init.services import InitManagerState


def test_cyan_service_state_uses_runtime_state_instead_of_enablement(monkeypatch):
    repo = object.__new__(GPURepository)
    commands = []

    def execute(command, timeout=5):
        commands.append((command, timeout))
        if "is-active" in command:
            return 3, "inactive\n", ""
        return 0, "enabled\n", ""

    repo._ejecutar = execute
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )

    assert repo._service_is_active("cyan-skillfish-governor-smu.service") is False
    assert [command for command, _timeout in commands] == [
        ["systemctl", "is-active", "cyan-skillfish-governor-smu.service"],
        ["systemctl", "is-enabled", "cyan-skillfish-governor-smu.service"],
    ]


def test_cyan_service_state_reports_running_disabled_unit_as_active(monkeypatch):
    repo = object.__new__(GPURepository)

    def execute(command, timeout=5):
        if "is-active" in command:
            return 0, "active\n", ""
        return 1, "disabled\n", ""

    repo._ejecutar = execute
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )

    assert repo._service_is_active("cyan-skillfish-governor-smu.service") is True


def _repository_for_telemetry_test(*, fix_frequency=False):
    repo = object.__new__(GPURepository)
    calls = []
    repo._editar_governor_toml = lambda action, flag: calls.append((action, flag)) or "updated"
    repo._restart_governor_if_active = lambda _service: False
    repo._cyan_configuration_state = lambda: (
        None, {}, {}, {}, {"fix_frequency": fix_frequency}
    )
    repo.estado_bc250_cache = object()
    return repo, calls


def test_cyan_telemetry_validation_preserves_disabled_fix_on_stock_six_cores(monkeypatch):
    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.os.cpu_count", lambda: 12)
    repo, calls = _repository_for_telemetry_test()

    result = repo.asegurar_telemetria_gpu_cyan()

    assert calls == [("ensure-cyan-telemetry", False)]
    assert result == "updated"


def test_cyan_telemetry_validation_preserves_enabled_fix_on_unlocked_eight_cores(monkeypatch):
    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.os.cpu_count", lambda: 16)
    repo, calls = _repository_for_telemetry_test(fix_frequency=True)

    result = repo.asegurar_telemetria_gpu_cyan()

    assert calls == [("ensure-cyan-telemetry", True)]
    assert result == "updated"


def test_cyan_policy_does_not_toggle_fix_freq_when_core_count_changes(monkeypatch):
    repo, calls = _repository_for_telemetry_test(fix_frequency=False)
    core_counts = iter((12, 16, 12))
    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.os.cpu_count", lambda: next(core_counts))

    repo.asegurar_telemetria_gpu_cyan()
    repo.asegurar_telemetria_gpu_cyan()
    repo.asegurar_telemetria_gpu_cyan()

    assert calls == [("ensure-cyan-telemetry", False)] * 3


def test_disabling_optional_cyan_metrics_preserves_live_range():
    repo = object.__new__(GPURepository)
    calls = []
    repo._ejecutar = lambda command, timeout=5: (0, "", "")
    repo._service_is_active = lambda _service: True
    repo._leer_rango_governor = lambda _property: (1000, 1850)
    repo._editar_governor_toml = (
        lambda action, flag: calls.append((action, flag)) or "updated"
    )
    repo._restart_governor_if_active = lambda _service: True
    repo._restaurar_rango_governor = lambda previous: calls.append(("restore", previous)) or previous
    repo.estado_bc250_cache = object()

    result = repo.desactivar_fix_metricas_gpu_cyan()

    assert calls == [
        ("set-cyan-metrics-fix", False),
        ("restore", (1000, 1850)),
    ]
    assert "1000-1850 MHz" in result
    assert repo.estado_bc250_cache is None


def test_disabling_optional_cyan_metrics_aborts_before_edit_without_live_range():
    repo = object.__new__(GPURepository)
    calls = []
    repo._ejecutar = lambda command, timeout=5: (0, "", "")
    repo._service_is_active = lambda _service: True
    repo._leer_rango_governor = lambda _property: None
    repo._editar_governor_toml = lambda *args: calls.append(args)

    try:
        repo.desactivar_fix_metricas_gpu_cyan()
    except RuntimeError as error:
        assert "could not be read" in str(error)
    else:
        raise AssertionError("live-range guard did not reject the restart")
    assert calls == []


def test_cyan_always_ready_user_messages_are_translated_in_all_supported_languages():
    from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
    from frontends.desktop.i18n.interface_catalog import INTERFACE_TRANSLATIONS

    keys = (
        "Install or update all required BC250 components. With Cyan selected, the GPU frequency-reporting fix is prepared now and remains ready if you later switch between 6C/12T and 8C/16T.",
        "Cyan GPU frequency reporting is not fully prepared because the active service binary does not provide fix-freq. Run Prepare everything to install and verify the official Cyan SMU runtime before changing core count.",
        "The TOML requests Cyan fix-freq, but the service binary does not contain the upstream GPU frequency reporting fix.",
        "Cyan telemetry repair is disabled or incomplete. Control Center keeps GPU frequency reporting enabled; the optional metrics overlay may remain disabled when the active runtime rejects it.",
        "Cyan's optional GPU usage metrics overlay is failing on the active runtime. GPU frequency reporting remains independent.",
        "Disable only fix-metrics, preserve fix-freq, then restart Cyan and verify recent service logs.",
    )
    for key in keys:
        assert key in INTERFACE_TRANSLATIONS, key
        for language in SUPPORTED_LANGUAGES:
            assert tr(key, language).strip(), (key, language)
            if language != "en":
                assert tr(key, language) != key, (key, language)


def test_six_core_cyan_health_is_healthy_when_fix_freq_is_already_enabled(tmp_path, monkeypatch):
    import bc250cc.infrastructure.health_repository as health_module
    from bc250cc.infrastructure.governor_conflicts import CYAN_GOVERNOR, GOVERNOR_SPECS
    from bc250cc.infrastructure.health_repository import HealthRepository

    config = tmp_path / "config.toml"
    config.write_text(
        '[gpu-usage]\n'
        'fix-metrics = true\n'
        'fix-freq = true\n'
        'method = "kernel"\n\n'
        '[frequency-range]\nmin = 500\nmax = 1850\n\n'
        '[[safe-points]]\nfrequency = 500\nvoltage = 700\n',
        encoding="utf-8",
    )
    monkeypatch.setitem(GOVERNOR_SPECS[CYAN_GOVERNOR], "config_path", str(config))
    monkeypatch.setattr(
        health_module,
        "detect_cyan_frequency_fix_runtime",
        lambda _repo: {"supports_frequency_fix": True},
    )
    monkeypatch.setattr(health_module.os, "cpu_count", lambda: 12)

    result = HealthRepository()._governor_config_health()

    assert result["status"] == "healthy"
    assert result["data"]["telemetry"]["fix_frequency"] is True
    assert result["data"]["telemetry"]["method"] == "kernel"


def test_inactive_cyan_saves_requested_fix_metrics_for_a_later_boot():
    repo = object.__new__(GPURepository)
    edits = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, False)
    repo._cyan_metrics_overlay_available = lambda: False
    repo._cyan_kernel_usage_available = lambda: True
    repo._service_is_active = lambda _service: False
    repo._editar_governor_toml = lambda *args: edits.append(args) or "updated"

    result = repo.configurar_compatibilidad_gpu_cyan(
        "smu", "busy-flag", True, False
    )

    assert edits == [
        ("set-cyan-compatibility", "smu", "busy-flag", True, False)
    ]
    assert "inactive" in result


def test_cyan_compatibility_applies_four_explicit_switches_without_policy_override():
    repo = object.__new__(GPURepository)
    calls = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, True)
    repo._cyan_metrics_overlay_available = lambda: True
    repo._cyan_kernel_usage_available = lambda: True
    repo._cyan_kernel_set_method_available = lambda: True
    repo._service_is_active = lambda _service: True
    repo._leer_rango_governor = lambda _property: (1000, 2000)
    repo._editar_governor_toml = (
        lambda *args: calls.append(("edit", args)) or "updated"
    )
    repo._restart_governor_if_active = lambda service: calls.append(("restart", service)) or True
    repo._restaurar_rango_governor = (
        lambda previous: calls.append(("restore", previous)) or previous
    )
    repo.estado_bc250_cache = object()

    result = repo.configurar_compatibilidad_gpu_cyan(
        "kernel", "kernel", False, False
    )

    assert calls[0] == (
        "edit",
        ("set-cyan-compatibility", "kernel", "kernel", False, False),
    )
    assert calls[1][0] == "restart"
    assert calls[2] == ("restore", (1000, 2000))
    assert "1000-2000 MHz" in result
    assert repo.estado_bc250_cache is None


def test_inactive_cyan_saves_kernel_usage_method_for_a_later_boot():
    repo = object.__new__(GPURepository)
    edits = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, False)
    repo._cyan_metrics_overlay_available = lambda: True
    repo._cyan_kernel_usage_available = lambda: False
    repo._cyan_kernel_set_method_available = lambda: True
    repo._service_is_active = lambda _service: False
    repo._editar_governor_toml = lambda *args: edits.append(args) or "updated"

    result = repo.configurar_compatibilidad_gpu_cyan(
        "kernel", "kernel", False, False
    )

    assert edits == [
        ("set-cyan-compatibility", "kernel", "kernel", False, False)
    ]
    assert "inactive" in result


def test_inactive_cyan_saves_kernel_set_method_for_a_later_boot():
    repo = object.__new__(GPURepository)
    edits = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, False)
    repo._cyan_metrics_overlay_available = lambda: True
    repo._cyan_kernel_usage_available = lambda: True
    repo._cyan_kernel_set_method_available = lambda: False
    repo._service_is_active = lambda _service: False
    repo._editar_governor_toml = lambda *args: edits.append(args) or "updated"

    result = repo.configurar_compatibilidad_gpu_cyan(
        "kernel", "busy-flag", False, False
    )

    assert edits == [
        ("set-cyan-compatibility", "kernel", "busy-flag", False, False)
    ]
    assert "inactive" in result


def test_active_cyan_rejects_a_missing_kernel_usage_interface():
    repo = object.__new__(GPURepository)
    edits = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, False)
    repo._service_is_active = lambda _service: True
    repo._cyan_metrics_overlay_available = lambda: True
    repo._cyan_kernel_usage_available = lambda: False
    repo._cyan_kernel_set_method_available = lambda: True
    repo._editar_governor_toml = lambda *args: edits.append(args)

    try:
        repo.configurar_compatibilidad_gpu_cyan(
            "kernel", "kernel", False, False
        )
    except RuntimeError as error:
        assert "gpu_busy_percent" in str(error)
        assert "Nothing was changed" in str(error)
    else:
        raise AssertionError("an active governor accepted an unavailable load source")

    assert edits == []


def test_active_cyan_rejects_an_unavailable_metrics_overlay():
    repo = object.__new__(GPURepository)
    edits = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", False, False)
    repo._service_is_active = lambda _service: True
    repo._cyan_metrics_overlay_available = lambda: False
    repo._editar_governor_toml = lambda *args: edits.append(args)

    try:
        repo.configurar_compatibilidad_gpu_cyan(
            "smu", "busy-flag", True, False
        )
    except RuntimeError as error:
        assert "fix-metrics was requested" in str(error)
        assert "Nothing was changed" in str(error)
    else:
        raise AssertionError("an active governor accepted an unavailable overlay")

    assert edits == []


def test_active_cyan_rejects_missing_kernel_frequency_interfaces():
    repo = object.__new__(GPURepository)
    edits = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, False)
    repo._service_is_active = lambda _service: True
    repo._cyan_metrics_overlay_available = lambda: True
    repo._cyan_kernel_usage_available = lambda: True
    repo._cyan_kernel_set_method_available = lambda: False
    repo._editar_governor_toml = lambda *args: edits.append(args)

    try:
        repo.configurar_compatibilidad_gpu_cyan(
            "kernel", "busy-flag", False, False
        )
    except RuntimeError as error:
        assert "pp_od_clk_voltage" in str(error)
        assert "pp_dpm_sclk" in str(error)
        assert "Nothing was changed" in str(error)
    else:
        raise AssertionError(
            "an active governor accepted unavailable frequency interfaces"
        )

    assert edits == []


def test_cyan_kernel_set_method_probe_accepts_the_kernel_reported_range(tmp_path):
    repo = object.__new__(GPURepository)
    repo._gpu_device_path = lambda: tmp_path
    voltage = tmp_path / "pp_od_clk_voltage"
    clocks = tmp_path / "pp_dpm_sclk"
    clocks.write_text("0: 1000Mhz *\n", encoding="ascii")

    voltage.write_text(
        "SCLK:    1000Mhz       2000Mhz\nVDDC: 700mV 1129mV\n",
        encoding="ascii",
    )
    assert repo._cyan_kernel_set_method_available() is True

    voltage.write_text(
        "SCLK:     350Mhz       2230Mhz\nVDDC: 700mV 1129mV\n",
        encoding="ascii",
    )
    assert repo._cyan_kernel_set_method_available() is True


def test_cyan_kernel_set_method_probe_requires_an_active_dpm_clock(tmp_path):
    repo = object.__new__(GPURepository)
    repo._gpu_device_path = lambda: tmp_path
    (tmp_path / "pp_od_clk_voltage").write_text("OD_SCLK:\n", encoding="ascii")
    clocks = tmp_path / "pp_dpm_sclk"

    clocks.write_text("0: 1000Mhz\n", encoding="ascii")
    assert repo._cyan_kernel_set_method_available() is False

    clocks.write_text("0: unavailable *\n", encoding="ascii")
    assert repo._cyan_kernel_set_method_available() is False


def test_failed_cyan_compatibility_restart_restores_previous_settings_and_range():
    repo = object.__new__(GPURepository)
    calls = []
    repo._current_cyan_compatibility = lambda: ("smu", "busy-flag", True, True)
    repo._cyan_metrics_overlay_available = lambda: True
    repo._cyan_kernel_usage_available = lambda: True
    repo._cyan_kernel_set_method_available = lambda: True
    repo._service_is_active = lambda _service: True
    repo._leer_rango_governor = lambda _property: (1000, 1850)
    repo._editar_governor_toml = (
        lambda *args: calls.append(("edit", args)) or "updated"
    )
    repo._restart_governor_if_active = lambda _service: (_ for _ in ()).throw(
        RuntimeError("kernel load source failed")
    )
    repo._restart_governor = lambda service: calls.append(("rollback-restart", service))
    repo._restaurar_rango_governor = (
        lambda previous: calls.append(("restore", previous)) or previous
    )
    repo.estado_bc250_cache = object()

    try:
        repo.configurar_compatibilidad_gpu_cyan(
            "kernel", "kernel", False, False
        )
    except RuntimeError as error:
        assert "previous configuration and runtime range were restored" in str(error)
    else:
        raise AssertionError("failed Cyan restart was reported as successful")

    assert calls[0] == (
        "edit",
        ("set-cyan-compatibility", "kernel", "kernel", False, False),
    )
    assert calls[1] == (
        "edit",
        ("set-cyan-compatibility", "smu", "busy-flag", True, True),
    )
    assert calls[2][0] == "rollback-restart"
    assert calls[3] == ("restore", (1000, 1850))


def test_cyan_startup_guard_never_rewrites_fix_metrics_behind_user_choice():
    repo = object.__new__(GPURepository)
    command = repo._cyan_metrics_overlay_preflight_command()

    assert "fix-metrics" in command
    assert "gpu_metrics" in command
    assert "Nothing was changed" in command
    assert "Disable fix-metrics explicitly" in command
    assert "set-cyan-metrics-fix" not in command
    assert "sed -i" not in command
    assert "fix-metrics = false" not in command
