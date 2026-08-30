import stat
from pathlib import Path

import bc250cc.infrastructure.health_repository as health_module
from bc250cc.infrastructure.health_repository import HealthRepository
from frontends.desktop.i18n import tr


def test_cu_boot_mask_parser_rejects_malformed_or_out_of_range_values():
    assert HealthRepository._parse_cu_service_masks("BC250_WGP_MASKS=0x07,0x1f,3,4\n") == [7, 31, 3, 4]
    assert HealthRepository._parse_cu_service_masks("BC250_WGP_MASKS=0x07,0x20,3,4\n") is None
    assert HealthRepository._parse_cu_service_masks("BC250_WGP_MASKS=0x07,3,4\n") is None


def test_repository_version_uses_local_git_description(tmp_path):
    repository = object.__new__(HealthRepository)
    checkout = tmp_path / "tool"
    (checkout / ".git").mkdir(parents=True)
    repository._ejecutar = lambda command, timeout=5: (0, "v1.2.3-4-gabc123\n", "")

    assert repository._repository_version(checkout) == "v1.2.3-4-gabc123"


def test_repository_health_rejects_a_valid_origin_at_an_unreviewed_revision(tmp_path):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    checkout = tmp_path / "tool"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "payload.py").write_text("# reviewed payload\n", encoding="utf-8")

    def execute(command, timeout=5):
        operation = tuple(command[-3:])
        if "describe" in command:
            return 0, "unreviewed\n", ""
        if operation == ("remote", "get-url", "origin"):
            return 0, "https://example.test/tool\n", ""
        if "fsck" in command:
            return 0, "", ""
        if operation[-2:] == ("rev-parse", "HEAD"):
            return 0, "b" * 40 + "\n", ""
        if operation[-2:] == ("status", "--porcelain"):
            return 0, "", ""
        raise AssertionError(command)

    repository._ejecutar = execute
    result = repository._repository_health(
        "tool", "https://example.test/tool", "payload.py", "a" * 40
    )

    assert result["status"] == "error"
    assert result["data"]["revision"] == "b" * 40
    assert result["data"]["expected_revision"] == "a" * 40


def test_repository_health_accepts_only_the_reviewed_clean_checkout(tmp_path):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    checkout = tmp_path / "tool"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "payload.py").write_text("# reviewed payload\n", encoding="utf-8")
    reviewed = "a" * 40

    def execute(command, timeout=5):
        if "describe" in command:
            return 0, reviewed[:12] + "\n", ""
        if tuple(command[-3:]) == ("remote", "get-url", "origin"):
            return 0, "https://example.test/tool\n", ""
        if "fsck" in command:
            return 0, "", ""
        if tuple(command[-2:]) == ("rev-parse", "HEAD"):
            return 0, reviewed + "\n", ""
        if tuple(command[-2:]) == ("status", "--porcelain"):
            return 0, "", ""
        raise AssertionError(command)

    repository._ejecutar = execute
    result = repository._repository_health(
        "tool", "https://example.test/tool", "payload.py", reviewed
    )

    assert result["status"] == "healthy"
    assert result["data"]["revision"] == reviewed


def test_repository_health_requires_exact_revision_evidence_for_archives(tmp_path):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    checkout = tmp_path / "tool"
    checkout.mkdir()
    (checkout / "payload.py").write_text("# reviewed payload\n", encoding="utf-8")
    (checkout / ".bc250-source-url").write_text(
        "https://example.test/tool\n", encoding="utf-8"
    )
    reviewed = "a" * 40

    missing = repository._repository_health(
        "tool", "https://example.test/tool", "payload.py", reviewed
    )
    assert missing["status"] == "error"
    assert missing["data"]["expected_revision"] == reviewed

    (checkout / ".bc250-source-revision").write_text(reviewed + "\n", encoding="utf-8")
    verified = repository._repository_health(
        "tool", "https://example.test/tool", "payload.py", reviewed
    )
    assert verified["status"] == "healthy"
    assert verified["data"]["revision"] == reviewed


def test_health_detects_broken_relevant_symlink(tmp_path):
    broken = tmp_path / "bc250-cu-live-manager"
    broken.symlink_to(tmp_path / "missing-target")
    repository = object.__new__(HealthRepository)
    repository._RELEVANT_LAUNCHERS = (broken,)

    checks = repository._relevant_launcher_health()

    assert checks[0]["status"] == "error"
    assert checks[0]["data"]["symlink"] is True


def test_corrupt_fan_json_is_repairable(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{broken", encoding="utf-8")

    class Settings:
        def config_path(self):
            return config_path

    repository = object.__new__(HealthRepository)
    repository.configuracion = Settings()

    result = repository._fan_config_health()

    assert result["status"] == "error"
    assert result["data"]["repair_action"] == "regenerate-fan-config"


def test_cu_repair_routes_broken_table_to_factory_repair():
    calls = []
    repository = object.__new__(HealthRepository)
    health = {"checks": [{
        "id": "installation:compute-units",
        "status": "error",
        "data": {"repair_action": "factory-repair-cu"},
    }]}
    repository.ejecutar_accion_cu_grafica = lambda action: calls.append(action)

    result = repository._repair_cu_installation(health)

    assert result["started"] is True
    assert calls == ["factory_repair"]


def test_health_check_accepts_and_migrates_legacy_three_point_fan_curve():
    repository = object.__new__(HealthRepository)
    repository.leer_config_local = lambda: {
        "fan_curve": {
            "enabled": True,
            "t1": 45, "s1": 40,
            "t2": 60, "s2": 65,
            "t3": 75, "s3": 100,
        }
    }

    result = repository._fan_config_health()

    assert result["status"] == "healthy"
    assert "3-point" in result["detail"]


def test_repair_uses_format_preserving_governor_action_for_mixed_range(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "bc250cc.infrastructure.health_repository.detect_init_manager",
        lambda: type("Init", (), {"kind": "systemd", "persistence_supported": True, "display_name": "systemd"})(),
    )
    repository = object.__new__(HealthRepository)
    repository.health_check = lambda: {
        "checks": [{
            "id": "config:governor",
            "status": "error",
            "data": {"repair_action": "clear-frequency-range"},
        }]
    }
    repository._abrir_terminal = lambda command, title: calls.append((command, title)) or True

    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda self: True if self.name == "bc250-governor-config-helper" else original_is_file(self),
    )
    result = repository.repair_installation()

    assert result["started"] is True
    assert "clear-frequency-range" in calls[0][0]
    assert "restore-default" not in calls[0][0]


def test_metrics_overlay_repair_uses_range_preserving_gpu_contract():
    repository = object.__new__(HealthRepository)
    repository.health_check = lambda: {
        "checks": [{
            "id": "config:governor",
            "status": "warning",
            "data": {"repair_action": "disable-cyan-metrics-fix"},
        }]
    }
    calls = []
    repository.desactivar_fix_metricas_gpu_cyan = (
        lambda: calls.append("range-preserving-repair") or "range preserved"
    )

    result = repository.repair_installation()

    assert result["started"] is True
    assert result["message"] == "range preserved"
    assert calls == ["range-preserving-repair"]


def test_health_repair_never_starts_steamos_kernel_repair_from_a_warning():
    calls = []
    repository = object.__new__(HealthRepository)
    repository.health_check = lambda: {
        "checks": [{"id": "steamos:patches", "status": "warning", "data": {}}]
    }
    repository._steamos_compatibility_stage_command = lambda: "validated-steamos-repair"
    repository._abrir_terminal = lambda command, title: calls.append((command, title)) or True

    result = repository.repair_installation()

    assert result["started"] is False
    assert calls == []
    assert "explicit Prepare SteamOS compatibility action" in result["message"]


def test_steamos_patch_health_returns_a_real_check_for_ready_and_missing_states(tmp_path, monkeypatch):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (True, "fixture protected backend")
    repository._running_kernel_cmdline = lambda: "quiet amdgpu.sched_policy=2"
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.platform.release", lambda: "6.18-test")

    repository._ejecutar = lambda command, timeout=20: (
        0,
        ("[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)\n"
        "[bc250-amdgpu] state: installed\n"),
        "",
    )
    ready = repository._steamos_patch_health()
    assert ready["id"] == "steamos:patches"
    assert ready["status"] == "healthy"
    assert ready["data"]["installed_for_running_kernel"] is True
    assert ready["data"]["scheduler_policy_active"] is True
    assert ready["data"]["scheduler_policy_runtime_conflict"] is False

    repository._ejecutar = lambda command, timeout=20: (1, "", "module not installed")
    missing = repository._steamos_patch_health()
    assert missing["status"] == "warning"
    assert missing["data"]["installed_for_running_kernel"] is False


def test_steamos_patch_health_never_executes_a_mutable_resourcetools_checkout(tmp_path):
    mutable = tmp_path / "bc250-steamos" / "bc250-audio-fix" / "patch-driver.sh"
    mutable.parent.mkdir(parents=True)
    mutable.write_text("#!/bin/bash\necho unsafe\n", encoding="utf-8")
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (False, "revision mismatch")
    repository._ejecutar = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("mutable toolkit status must not run")
    )

    result = repository._steamos_patch_health()

    assert result["status"] == "warning"
    assert result["data"]["decision"] == "protected-backend-required"
    assert result["data"]["backend_reason"] == "revision mismatch"
    assert "stage the reviewed backend" in result["repair"]
    assert result["detail_key"]
    assert result["repair_key"]
    assert tr(result["detail_key"], "es") != result["detail_key"]
    assert tr(result["repair_key"], "pl") != result["repair_key"]


def test_steamos_patch_health_localizes_missing_kernel_evidence(tmp_path, monkeypatch):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (True, "fixture protected backend")
    repository._running_kernel_cmdline = lambda: "quiet amdgpu.sched_policy=2"
    repository._steamos_efi_policy_readable = lambda: True
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.platform.release", lambda: "")
    repository._ejecutar = lambda command, timeout=20: (
        0,
        ("[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)\n"
        "[bc250-amdgpu] state: installed\n"),
        "",
    )

    result = repository._steamos_patch_health()

    assert result["data"]["decision"] == "kernel-status-required"
    assert result["detail_key"] == result["detail"]
    assert result["repair_key"] == result["repair"]
    assert tr(result["detail_key"], "es") != result["detail_key"]
    assert tr(result["repair_key"], "de") != result["repair_key"]


def test_steamos_patch_health_reports_verified_reboot_pending_without_reinstall(tmp_path, monkeypatch):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (True, "fixture protected backend")
    repository._running_kernel_cmdline = lambda: ""
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.platform.release", lambda: "6.18-test")
    repository._ejecutar = lambda command, timeout=20: (
        1,
        ("[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)\n"
        "[bc250-amdgpu] state: installed\n"),
        "",
    )

    result = repository._steamos_patch_health()

    assert result["status"] == "warning"
    assert result["data"]["decision"] == "reboot-pending"
    assert result["data"]["installed_for_running_kernel"] is True
    assert result["data"]["scheduler_policy_verified"] is True
    assert result["data"]["scheduler_policy_active"] is False
    assert "do not reinstall or rebuild" in result["repair"]


def test_steamos_patch_health_distinguishes_unreadable_efi_from_known_policy_repair(
    tmp_path, monkeypatch
):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (True, "fixture protected backend")
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.platform.release", lambda: "6.18-test")
    repository._ejecutar = lambda command, timeout=20: (
        1,
        ("[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] state: incomplete\n"),
        "",
    )

    repository._steamos_efi_policy_readable = lambda: False
    repository._running_kernel_cmdline = lambda: "quiet"
    unreadable = repository._steamos_patch_health()
    assert unreadable["data"]["decision"] == "privileged-check"
    assert unreadable["data"]["efi_policy_readable"] is False
    assert unreadable["data"]["status_privileged"] is False

    repository._steamos_efi_policy_readable = lambda: True
    readable = repository._steamos_patch_health()
    assert readable["data"]["decision"] == "repair-policy"
    assert readable["data"]["efi_policy_readable"] is True


def test_steamos_patch_health_reports_active_cmdline_without_claiming_persistence(
    tmp_path, monkeypatch
):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (True, "fixture protected backend")
    repository._steamos_efi_policy_readable = lambda: False
    repository._running_kernel_cmdline = lambda: "quiet amdgpu.sched_policy=2 splash"
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.platform.release", lambda: "6.18-test")
    repository._ejecutar = lambda command, timeout=20: (
        1,
        ("[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: incomplete or unrecognized\n"
        "[bc250-amdgpu] state: incomplete\n"),
        "",
    )

    result = repository._steamos_patch_health()

    assert result["status"] == "warning"
    assert result["data"]["decision"] == "privileged-check"
    assert result["data"]["scheduler_policy_active"] is True
    assert "active in the running kernel" in result["detail"]
    assert "do not reinstall or rebuild" in result["repair"]


def test_steamos_patch_health_exposes_conflicting_live_scheduler_evidence(tmp_path, monkeypatch):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path
    repository._steamos_amdgpu_backend_status = lambda: (True, "fixture protected backend")
    repository._steamos_efi_policy_readable = lambda: True
    repository._running_kernel_cmdline = lambda: "quiet amdgpu.sched_policy=1 splash"
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.platform.release", lambda: "6.18-test")
    repository._ejecutar = lambda command, timeout=20: (
        0,
        ("[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)\n"
        "[bc250-amdgpu] state: installed\n"),
        "",
    )

    result = repository._steamos_patch_health()

    assert result["status"] == "warning"
    assert result["data"]["decision"] == "repair-policy"
    assert result["data"]["scheduler_policy_runtime_conflict"] is True
    assert result["data"]["scheduler_policy_active"] is False


def test_optional_nct_source_is_warning_and_repair_prepares_pwm(tmp_path):
    repository = object.__new__(HealthRepository)
    repository._tool_dir = lambda: tmp_path

    checks = repository._repository_health_checks("fedora")
    nct = next(item for item in checks if item["id"] == "repository:nct6687d")

    assert nct["status"] == "warning"
    assert nct["data"]["repair_action"] == "prepare-fan-pwm"

    repository.health_check = lambda: {"checks": [nct]}
    repository.preparar_nct6687_control_pwm = lambda: True
    result = repository.repair_installation()
    assert result["started"] is True
    assert result["message"] == "Fan PWM driver repair started."


def test_diagnostic_report_is_private_and_contains_required_sections(tmp_path, monkeypatch):
    class Repository(HealthRepository):
        def health_check(self):
            return {
                "generated_at": "2026-08-08T12:00:00-06:00",
                "distribution": "Test Linux",
                "kernel": "test-kernel",
                "checks": [],
                "counts": {"healthy": 0, "warning": 0, "error": 0},
                "overall": "healthy",
            }

        def config_paths(self):
            return {"config": str(tmp_path / "config.json")}

        def _ejecutar(self, command, timeout=8):
            return 0, "test output for " + command[0], ""

        def obtener_estado_cu_cache(self):
            return {"mode": "Factory 24 CUs"}

        def estado_fans_bc250(self):
            return {"driver_control": True}

        configuracion = object()

    monkeypatch.setattr(
        health_module,
        "activity_journal",
        lambda _configuration: type("Journal", (), {"listar": lambda self, _limit: [{"nivel": "info", "titulo": "test"}]})(),
    )

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    result = Repository().generate_diagnostic_report()
    report_path = Path(result["path"])

    assert report_path.is_file()
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert "## Compute Unit status" in result["report"]
    assert "## Fan hardware status" in result["report"]
    assert "## Governor configuration" in result["report"]


def test_settings_does_not_expose_system_health_module():
    source = Path("frontends/desktop/pages/settings.py").read_text(encoding="utf-8")

    sections_source = source[source.index("sections = ["):source.index("self.section_order")]
    assert '"health", "System health"' not in sections_source


def test_cpu_oc_oneshot_inactive_dead_is_healthy_after_success():
    repository = object.__new__(HealthRepository)

    def execute(command, timeout=4):
        if "is-enabled" in command:
            return 0, "enabled\n", ""
        if "is-active" in command:
            return 3, "inactive\n", ""
        if "show" in command:
            return (
                0,
                ("Type=oneshot\nActiveState=inactive\nSubState=dead\n"
                "Result=success\nExecMainStatus=0\nExecMainCode=exited\n"),
                "",
            )
        raise AssertionError(command)

    repository._ejecutar = execute
    item = repository._service_health("bc250-smu-oc.service", optional=True)

    assert item["status"] == "healthy"
    assert "inactive (dead) is expected" in item["detail"]
    assert item["data"]["systemd_Result"] == "success"


def test_cachyos_health_warns_on_deckify_without_replacing_kernel(monkeypatch):
    repository = object.__new__(HealthRepository)
    repository._ejecutar = lambda command, timeout=6: (1, "", "not installed")
    monkeypatch.setattr(
        "bc250cc.infrastructure.health_repository.platform.release",
        lambda: "7.1.6-1-cachyos-deckify",
    )

    item = repository._cachyos_compatibility_health()

    assert item["status"] == "warning"
    assert item["data"]["deckify"] is True
    assert item["data"]["automatic_kernel_replacement"] is False
    assert "does not explicitly list CachyOS" in item["detail"]


def test_cyan_health_accepts_explicit_disabled_fix_profile(monkeypatch, tmp_path):
    import bc250cc.infrastructure.health_repository as health_module
    from bc250cc.infrastructure.health_repository import HealthRepository

    config = tmp_path / "config.toml"
    config.write_text(
        '[gpu-usage]\n'
        'fix-metrics = true\n'
        'fix-freq = false\n'
        'method = "kernel"\n\n'
        '[frequency-range]\n'
        'min = 500\n'
        'max = 1850\n\n'
        '[[safe-points]]\n'
        'frequency = 500\n'
        'voltage = 700\n',
        encoding="utf-8",
    )
    repo = HealthRepository()
    repo._health_governor_context = lambda: {"selected": "cyan-skillfish-governor-smu"}
    monkeypatch.setitem(
        health_module.GOVERNOR_SPECS["cyan-skillfish-governor-smu"],
        "config_path",
        str(config),
    )
    monkeypatch.setattr(health_module.os, "cpu_count", lambda: 12)
    monkeypatch.setattr(
        health_module,
        "detect_cyan_frequency_fix_runtime",
        lambda _repo: {"supports_frequency_fix": True},
    )

    result = repo._governor_config_health()

    assert result["status"] == "healthy"
    assert result["data"]["telemetry"]["method"] == "kernel"
