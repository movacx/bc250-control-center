import subprocess
from pathlib import Path
from types import SimpleNamespace

from bc250cc.infrastructure.cyan_governor_runtime import (
    CYAN_FREQUENCY_FIX_MARKER,
    CYAN_METRICS_FIX_FAILURE_MARKER,
    binary_supports_frequency_fix,
    detect_cyan_frequency_fix_runtime,
    detect_cyan_metrics_fix_runtime,
    detect_cyan_runtime_identity,
    parse_openrc_command_args,
    parse_openrc_command_path,
    parse_systemd_exec_argv,
    parse_systemd_exec_path,
)
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.governor_conflicts import CYAN_GOVERNOR, GOVERNOR_SPECS
from bc250cc.infrastructure.health_repository import HealthRepository
from bc250cc.infrastructure.preparation_workflow import build_preparation_command


def test_binary_capability_checks_the_real_execution_branch(tmp_path):
    old = tmp_path / "old-governor"
    fixed = tmp_path / "fixed-governor"
    old.write_bytes(b"ELF\x00unrelated governor data")
    fixed.write_bytes(b"x" * (64 * 1024 - 8) + CYAN_FREQUENCY_FIX_MARKER)

    assert binary_supports_frequency_fix(old) is False
    assert binary_supports_frequency_fix(fixed) is True


def test_systemd_exec_path_is_authoritative_over_other_installed_candidates(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    old = tmp_path / "package-governor"
    fixed = tmp_path / "managed-governor"
    old.write_bytes(b"old")
    fixed.write_bytes(CYAN_FREQUENCY_FIX_MARKER)

    class Repository:
        @staticmethod
        def _ejecutar(command, timeout=4):
            assert command[:3] == [
                "systemctl",
                "show",
                "cyan-skillfish-governor-smu.service",
            ]
            return 0, f"{{ path={old} ; argv[]={old} config.toml ; }}", ""

        @staticmethod
        def _command_path(_name):
            return str(fixed)

    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.CYAN_MANAGED_BINARY", fixed
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.CYAN_PACKAGED_BINARY", old
    )
    state = detect_cyan_frequency_fix_runtime(Repository())

    assert state["service_path"] == str(old)
    assert state["supports_frequency_fix"] is False
    assert any(item["supports_frequency_fix"] for item in state["candidates"])


def test_parse_systemd_exec_path_rejects_unstructured_text():
    assert parse_systemd_exec_path("{ path=/usr/local/bin/cyan ; argv[]=... ; }") == (
        "/usr/local/bin/cyan"
    )
    assert parse_systemd_exec_path("/usr/local/bin/cyan --not-systemd-format") == ""


def test_openrc_command_path_accepts_only_the_openrc_command_assignment():
    assert (
        parse_openrc_command_path(
            '#!/sbin/openrc-run\ncommand="/usr/local/bin/cyan-skillfish-governor-smu"\n'
        )
        == "/usr/local/bin/cyan-skillfish-governor-smu"
    )
    assert parse_openrc_command_path("command_args=/etc/cyan.toml") == ""


def test_metrics_runtime_probe_only_accepts_recent_stable_failure_marker(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    calls = []

    class Repository:
        @staticmethod
        def _ejecutar(command, timeout=4):
            calls.append((command, timeout))
            return 0, f"noise\n{CYAN_METRICS_FIX_FAILURE_MARKER}: ERANGE\n", ""

    state = detect_cyan_metrics_fix_runtime(Repository(), lookback_seconds=999)

    assert state["metrics_fix_runtime_error"] is True
    assert state["metrics_fix_journal_checked"] is True
    assert calls == [
        (
            [
                "journalctl",
                "-b",
                "-u",
                "cyan-skillfish-governor-smu.service",
                "--since",
                "60 seconds ago",
                "--no-pager",
                "-o",
                "cat",
            ],
            4,
        )
    ]


def test_metrics_runtime_probe_fails_open_when_journal_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )

    class Repository:
        @staticmethod
        def _ejecutar(_command, timeout=4):
            return 1, "", "permission denied"

    state = detect_cyan_metrics_fix_runtime(Repository())

    assert state == {
        "metrics_fix_runtime_error": False,
        "metrics_fix_error": "",
        "metrics_fix_journal_checked": False,
        "metrics_fix_log_supported": True,
    }


def test_prepare_command_clones_smu_and_uses_checksummed_upstream_installer(tmp_path):
    scripts_root = Path("packaging/common/os-scripts").resolve()
    os_repository = SimpleNamespace(
        scripts_root=scripts_root,
        info=SimpleNamespace(family="fedora"),
    )
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path

    command = repository._cyan_upstream_runtime_command(os_repository)
    installer = (scripts_root / "common/install-cyan-upstream-release.sh").read_text(
        encoding="utf-8"
    )

    assert "filippor/cyan-skillfish-governor" in command
    assert "964524d74ba6b69364be39f0e8fa484eb915779e" in command
    assert "--branch smu" not in command
    assert "src/gpu_frequency_fix.rs" in command
    assert "DryhoppedIPA" not in command
    assert "REVIEWED_ARCHIVE_SHA256" in installer
    assert "latest_release_tag" not in installer
    assert "90-bc250-control-center-upstream.conf" in installer
    assert "GPU frequency fix enabled" in installer
    assert '[[ ! -f "$CONFIG" ]]' in installer
    assert 'default-config.toml" "$CONFIG"' in installer
    assert "Installing the missing official Cyan systemd service" in installer
    assert 'systemctl unmask "$SERVICE"' in installer
    assert "/usr/local/lib/systemd/system/${SERVICE}" in installer
    assert 'systemctl cat "$SERVICE"' in installer
    assert "managed-fallback-unit" in installer
    assert "preserving the selected Cyan compatibility switches" in installer
    assert "validate_compatibility_switches" in installer
    assert "ensure_frequency_fix_enabled" not in installer
    assert "rm -f /etc/cyan-skillfish-governor-smu/config.toml" not in installer


def test_debian_governor_repairs_stale_package_registration():
    script = Path(
        "packaging/common/os-scripts/debian/prepare-dependencies.sh"
    ).read_text(encoding="utf-8")

    assert "package_current=0 installation_complete=0" in script
    assert "install ok installed ${version}-" in script
    assert "systemctl cat cyan-skillfish-governor-smu.service" in script
    assert 'apt-get install --reinstall -y "$workdir/$deb"' in script


def test_cyan_uninstall_only_removes_app_managed_fallback_unit():
    source = Path("src/bc250cc/infrastructure/dependencias_repository.py").read_text(
        encoding="utf-8"
    )

    assert "cyan-governor/managed-fallback-unit" in source
    assert (
        "sudo rm -f /usr/local/lib/systemd/system/cyan-skillfish-governor-smu.service "
        in source
    )


def test_runtime_verification_restarts_only_an_already_active_service():
    command = DependenciasRepository._cyan_runtime_verification_command()

    assert "systemctl is-active --quiet cyan-skillfish-governor-smu.service" in command
    assert "sudo systemctl restart cyan-skillfish-governor-smu.service" in command
    assert "GPU frequency fix enabled" in command
    assert "selected compatibility switches" in command
    assert "bc250_cyan_previous_min" in command
    assert "bc250_cyan_previous_max" in command
    assert "SetRange uu" in command
    assert "for bc250_cyan_attempt in {1..25}" in command
    assert "bc250_cyan_restored_min" in command
    assert "bc250_cyan_restore_ok" in command
    assert "previous runtime range could not be restored" in command
    assert "systemctl enable" not in command


def test_health_check_does_not_accept_toml_flag_with_old_runtime(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = true\n"
        'method = "busy-flag"\n\n'
        "# [frequency-range]\n"
        "# min = 1000\n"
        "# max = 1850\n\n"
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(GOVERNOR_SPECS[CYAN_GOVERNOR], "config_path", str(config))
    monkeypatch.setattr("bc250cc.infrastructure.health_repository.os.cpu_count", lambda: 16)
    monkeypatch.setattr(
        "bc250cc.infrastructure.health_repository.detect_cyan_frequency_fix_runtime",
        lambda _repository: {
            "binary_path": "/usr/bin/cyan-skillfish-governor-smu",
            "supports_frequency_fix": False,
        },
    )

    item = HealthRepository()._governor_config_health()

    assert item["status"] == "warning"
    assert item["data"]["repair_action"] == "update-cyan-runtime"
    assert "service binary" in item["detail"]


def test_prepare_everything_keeps_cyan_frequency_fix_ready_in_automatic_path():
    import inspect

    facade = inspect.getsource(DependenciasRepository.instalar_dependencias_bc250)
    source = inspect.getsource(build_preparation_command)
    assert "build_preparation_command(context)" in facade
    assert "context.selected_governor == CYAN_GOVERNOR" in source
    assert "commands.append(repo._cyan_upstream_runtime_command(os_repo))" in source
    assert "commands.append(repo._cyan_runtime_verification_command())" in source


def test_cyan_upstream_installer_preserves_switches_across_core_unlock():
    script = Path(
        "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"
    ).read_text(encoding="utf-8")

    assert "if (( logical_cpus < 16 )); then" not in script
    assert "preserving the selected Cyan compatibility switches" in script
    assert "install_release" in script
    assert 'REVIEWED_RELEASE_TAG="v0.4.12"' in script
    assert 'release_tag="$REVIEWED_RELEASE_TAG"' in script


def test_cyan_runtime_verification_is_core_count_independent_and_validates_switches():
    command = DependenciasRepository._cyan_runtime_verification_command()

    assert "_NPROCESSORS_ONLN" not in command
    assert "fix-freq|fix_freq" in command
    assert "fix-freq is missing or invalid" in command
    assert "fix-metrics is missing or invalid" in command
    assert "gpu-usage.method is invalid" in command
    assert '"(busy-flag|process|kernel)"' in command
    assert "gpu.set-method is missing or invalid" in command


def test_prepare_paths_preserve_user_selected_cyan_policy():
    import inspect

    install_source = inspect.getsource(DependenciasRepository.instalar_governor)
    prepare_source = inspect.getsource(build_preparation_command)
    assert "ensure-cyan-telemetry" not in install_source
    assert "ensure-cyan-telemetry" not in prepare_source
    assert "_cyan_runtime_verification_command" in install_source
    assert "_cyan_runtime_verification_command" in prepare_source


def test_generated_cyan_runtime_verification_is_valid_bash():
    command = DependenciasRepository._cyan_runtime_verification_command()
    result = subprocess.run(
        ["bash", "-n", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_bazzite_runtime_build_rejects_dirty_or_untracked_reviewed_source():
    installer = (
        Path(__file__).resolve().parents[3]
        / "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"
    ).read_text(encoding="utf-8")

    assert "status --porcelain --untracked-files=all" in installer
    assert "contains local/untracked files before the reviewed patch" in installer


def test_systemd_runtime_identity_extracts_exact_binary_and_config(
    monkeypatch, tmp_path
):
    binary = tmp_path / "cyan"
    binary.write_bytes(b"cyan-runtime")
    config = tmp_path / "config.toml"
    config.write_text("[dbus]\nenabled = true\n", encoding="utf-8")
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )

    class Repository:
        @staticmethod
        def _ejecutar(command, timeout=4):
            if command[0] == "systemctl":
                return (
                    0,
                    (
                        f"{{ path={binary} ; argv[]={binary} {config} ; ignore_errors=no ; }}"
                    ),
                    "",
                )
            if command == [str(binary), "--version"]:
                return 0, "cyan-skillfish-governor-smu v0.4.12\n", ""
            raise AssertionError(command)

        @staticmethod
        def _command_path(_name):
            return str(binary)

    identity = detect_cyan_runtime_identity(Repository())

    assert identity["binary_path"] == str(binary)
    assert identity["config_path"] == str(config)
    assert identity["version"].endswith("v0.4.12")
    assert len(identity["binary_sha256"]) == 64
    assert identity["config_matches_managed_path"] is False


def test_exec_argument_parsers_do_not_guess_unstructured_config_paths():
    systemd = "{ path=/usr/bin/cyan ; argv[]=/usr/bin/cyan /etc/cyan/config.toml ; }"
    assert parse_systemd_exec_argv(systemd) == (
        "/usr/bin/cyan",
        "/etc/cyan/config.toml",
    )
    assert parse_systemd_exec_argv("/usr/bin/cyan /tmp/config.toml") == ()
    assert parse_openrc_command_args('command_args="/etc/cyan/config.toml"') == (
        "/etc/cyan/config.toml",
    )


def test_bazzite_runtime_fast_path_verifies_patcher_identity_and_version():
    installer = (
        Path(__file__).resolve().parents[3]
        / "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"
    ).read_text(encoding="utf-8")

    assert '[[ -r "$STATE_DIR/patcher-sha256" ]]' in installer
    assert '"$(<"$STATE_DIR/patcher-sha256")"' in installer
    assert 'managed_version="$($MANAGED_BINARY --version' in installer
    assert '[[ "$managed_version" == *"${BC250CC_RUNTIME_REVISION}"* ]]' in installer


def test_bazzite_runtime_identity_requires_binary_patcher_and_version_match(
    monkeypatch, tmp_path
):
    binary = tmp_path / "cyan-skillfish-governor-smu"
    binary.write_bytes(b"reviewed-binary")
    patcher = tmp_path / "patch-cyan.py"
    patcher.write_text("# reviewed patcher\n", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text("[dbus]\nenabled = true\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    import hashlib

    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    patcher_sha = hashlib.sha256(patcher.read_bytes()).hexdigest()
    (state_dir / "runtime-revision").write_text("bc250cc.2\n", encoding="utf-8")
    (state_dir / "upstream-commit").write_text(
        "964524d74ba6b69364be39f0e8fa484eb915779e\n", encoding="utf-8"
    )
    (state_dir / "binary-sha256").write_text(binary_sha + "\n", encoding="utf-8")
    (state_dir / "patcher-sha256").write_text(patcher_sha + "\n", encoding="utf-8")

    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.CYAN_MANAGED_BINARY", binary
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.CYAN_CONFIG", config
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.CYAN_STATE_DIR", state_dir
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.cyan_governor_runtime.CYAN_BC250CC_PATCHER", patcher
    )

    class Repository:
        @staticmethod
        def _ejecutar(command, timeout=4):
            if command[0] == "systemctl":
                return (
                    0,
                    f"{{ path={binary} ; argv[]={binary} {config} ; ignore_errors=no ; }}",
                    "",
                )
            if command == [str(binary), "--version"]:
                return 0, "cyan-skillfish-governor-smu v0.4.12-bc250cc.2\n", ""
            raise AssertionError(command)

        @staticmethod
        def _command_path(_name):
            return str(binary)

    identity = detect_cyan_runtime_identity(Repository())

    assert identity["runtime_hash_matches"] is True
    assert identity["runtime_patcher_matches"] is True
    assert identity["runtime_version_matches"] is True
    assert identity["runtime_bc250cc_verified"] is True

    (state_dir / "patcher-sha256").write_text("0" * 64 + "\n", encoding="utf-8")
    identity = detect_cyan_runtime_identity(Repository())
    assert identity["runtime_patcher_matches"] is False
    assert identity["runtime_bc250cc_verified"] is False
