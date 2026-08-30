import json
import os
import runpy
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRIVILEGED = ROOT / "privileged" / "helpers"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_core_unlock_helper_launches_only_validated_official_upstream_script():
    helper = _text(PRIVILEGED / "bc250-core-unlock-helper")
    assert "rw-r-r-0644/bc250-core-unlock" in helper
    assert 'UPSTREAM_SCRIPT = "bc250-unlock-cores.py"' in helper
    assert '["show", f"{head}:{UPSTREAM_SCRIPT}"]' in helper
    assert "head != REVIEWED_REVISION" in helper
    assert "working_hash != REVIEWED_SCRIPT_SHA256" in helper
    assert '"rev-parse", "refs/remotes/origin/main"' not in helper
    assert 'f"/proc/self/fd/{script_fd}"' in helper
    assert "0x0115A870" not in helper
    assert "SMU_WRITE_FF_MESSAGE" not in helper
    assert '"cyan-skillfish-governor-smu.service"' in helper
    assert '"oberon-governor.service"' in helper
    assert "_stop_gpu_governors()" in helper
    # The launcher remains distribution-neutral across Debian/Ubuntu/Mint,
    # Fedora/Nobara, Arch derivatives, and SteamOS/Bazzite. Package-manager or
    # distro-specific policy belongs to dependency preparation, not the SMU write.
    assert not any(manager in helper for manager in ("apt ", "dnf ", "pacman ", "rpm-ostree"))
    assert " '-f'" not in helper and '"-f"' not in helper
    assert "command = ['/usr/bin/systemctl', 'reboot']" in helper
    assert "['rc-service', key, 'stop']" in helper


def test_local_installer_removes_archived_core_implementation():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    assert "SYSTEM_GOVERNOR_TOML_IMPLEMENTATION" in installer
    assert 'install -Dm644 "$governor_toml_source"' in installer
    assert "LEGACY_CORE_UNLOCK_IMPLEMENTATION" in installer
    assert '"$LEGACY_CORE_UNLOCK_IMPLEMENTATION"' in installer
    assert "SYSTEM_CORE_UNLOCK_IMPLEMENTATION" not in installer
    assert 'implementation_metadata' in installer
    assert '"0:644"' in installer


def test_governor_helper_and_editor_are_deployed_together_with_current_protocol():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    helper = _text(PRIVILEGED / "bc250-governor-config-helper")

    assert "BC250_GOVERNOR_CONFIG_PROTOCOL = 5" in helper
    assert "'set-cyan-metrics-fix'" in helper
    assert "'set-cyan-voltage-level', 'set-cyan-custom-voltages'" in helper
    assert 'install -Dm755 "$governor_helper_source" "$SYSTEM_GOVERNOR_CONFIG_HELPER"' in installer
    assert 'install -Dm644 "$governor_toml_source" "$SYSTEM_GOVERNOR_TOML_IMPLEMENTATION"' in installer
    assert 'cmp -s "$helper_source_path" "$helper_installed_path"' in installer


def test_local_installer_executes_dependency_commands_as_argv_arrays():
    installer = _text(ROOT / "scripts" / "install-local.sh")

    assert 'sudo "${missing_python_deps_command[@]}"' in installer
    assert '"${missing_python_deps_command[@]}"' in installer
    assert "sudo $missing_python_deps_command" not in installer


def test_local_installer_preflights_complete_source_before_copying_or_privilege():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    validator = ROOT / "scripts" / "qa" / "validate-install-source.sh"

    assert validator.is_file()
    assert installer.count('scripts/qa/validate-install-source.sh') == 2
    assert installer.index('--structure-only') < installer.index(
        '\n  prepare_steamos_pacman_install_local'
    )
    assert installer.rindex('scripts/qa/validate-install-source.sh') < installer.index('install -dm755')

    completed = subprocess.run(
        ["bash", str(validator), str(ROOT)],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "vendor checks" in completed.stdout


def test_local_install_and_uninstall_manage_headless_cli_and_isolated_prefixes():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    uninstaller = _text(ROOT / "scripts" / "uninstall-local.sh")

    assert 'scripts/entrypoints/bc250-control-center-cli" "$BIN_DIR/bc250-control-center-cli"' in installer
    assert 'remove_path "$BIN_DIR/bc250-control-center-cli"' in uninstaller
    assert '--keep-privileged' in uninstaller
    assert '"$SYSTEMD_USER_DIR" != "$expected_user_systemd_dir"' in uninstaller


def test_dependency_preparation_clones_and_credits_upstream_core_unlock():
    common = _text(
        ROOT
        / "packaging"
        / "common"
        / "os-scripts"
        / "common"
        / "common.sh"
    )
    dependencies = _text(ROOT / "src" / "bc250cc" / "infrastructure" / "dependencias_repository.py")
    workflow = _text(ROOT / "src" / "bc250cc" / "infrastructure" / "preparation_workflow.py")
    assert "rw-r-r-0644/bc250-core-unlock" in common
    assert "official repository cloned and launched by the GUI" in common
    assert "CORE_UNLOCK_REPOSITORY" in dependencies
    assert "_hardware_source_checkout_command(CORE_UNLOCK_REPOSITORY" in dependencies
    assert "build_preparation_command(context)" in dependencies
    assert "CPU core unlock repo:" in workflow
    assert "chmod 0755" in dependencies
    assert "core_unlock_script" in dependencies or "core_script" in workflow


def test_local_reimplementation_is_not_in_runtime_sources():
    # This QA branch deliberately omits package/archive payloads. The security
    # invariant is that the retired local implementation is not present in the
    # runtime tree or local installer sources.
    assert not (ROOT / "src" / "bc250cc" / "infrastructure" / "core_unlock.py").exists()
    install_sources = "\n".join(
        _text(path)
        for root in ("scripts", "packaging")
        if (ROOT / root).exists()
        for path in (ROOT / root).rglob("*")
        if path.is_file()
    )
    assert "src/bc250cc/infrastructure/core_unlock.py" not in install_sources


def test_release_source_builders_exclude_the_archived_implementation():
    builders = (
        ROOT / "packaging" / "scripts" / "build-tarball.sh",
        ROOT / "packaging" / "scripts" / "build-rpm.sh",
        ROOT / "packaging" / "scripts" / "build-local-pkg.sh",
        ROOT / "packaging" / "scripts" / "build-deb.sh",
    )

    if not all(builder.is_file() for builder in builders):
        pytest.skip("Package builders are intentionally omitted from this QA source tree.")
    for builder in builders:
        assert "--exclude 'archive'" in _text(builder), builder
        assert "--exclude 'tests'" in _text(builder), builder


def test_steamos_game_mode_helper_remains_a_separate_packaged_protocol():
    policy_path = ROOT / "privileged" / "policies" / "io.github.movacx.bc250-control-center.policy"
    assert policy_path.is_file()
    helper = _text(PRIVILEGED / "bc250-steamos-game-helper")
    installer = _text(ROOT / "scripts" / "install-local.sh")
    policy = _text(policy_path)
    assert "BC250_HELPER_PROTOCOL=20" in helper
    assert "BC250_HELPER_PROTOCOL=7" not in installer
    assert "expected_game_helper_protocol" in installer
    assert "bc250-steamos-game-helper" in installer
    assert "bc250-steamos-game-helper" in policy


def test_privileged_fan_helpers_restore_and_verify_hwmon_automatic_mode(tmp_path, monkeypatch):
    sensor = tmp_path / "hwmon-test"
    sensor.mkdir()
    (sensor / "pwm2_enable").write_text("1\n", encoding="ascii")

    desktop = runpy.run_path(str(PRIVILEGED / "bc250-fan-pwm-helper"))
    monkeypatch.setitem(desktop["restore_automatic"].__globals__, "find_sensor", lambda: sensor)
    assert desktop["restore_automatic"](2) == "OK PWM 2 AUTO"
    assert (sensor / "pwm2_enable").read_text(encoding="ascii").strip() == "2"

    (sensor / "pwm2_enable").write_text("1\n", encoding="ascii")
    game = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    monkeypatch.setitem(game["action_fan_pwm_auto"].__globals__, "find_nct_sensor", lambda: sensor)
    assert game["action_fan_pwm_auto"](["2"]) == 0
    assert (sensor / "pwm2_enable").read_text(encoding="ascii").strip() == "2"


def test_privileged_desktop_pwm_helper_retries_duty_after_nct_manual_transition(
    tmp_path, monkeypatch
):
    """The first duty write may be ignored although pwmN_enable already reads 1."""
    sensor = tmp_path / "hwmon-test"
    sensor.mkdir()
    pwm = sensor / "pwm4"
    enable = sensor / "pwm4_enable"
    pwm.write_text("127\n", encoding="ascii")
    enable.write_text("2\n", encoding="ascii")

    desktop = runpy.run_path(str(PRIVILEGED / "bc250-fan-pwm-helper"))
    globals_ = desktop["apply_pwm"].__globals__
    monkeypatch.setitem(globals_, "find_sensor", lambda: sensor)
    monkeypatch.setattr(globals_["time"], "sleep", lambda _seconds: None)

    writes = []
    duty_writes = 0

    def delayed_write(path, value):
        nonlocal duty_writes
        writes.append((path.name, value))
        if path == pwm:
            duty_writes += 1
            # Reproduce the NCT6687 race: the first duty is accepted by sysfs
            # but its register still shows the old 127 value.
            if duty_writes == 1:
                return
        path.write_text(f"{value}\n", encoding="ascii")

    monkeypatch.setitem(globals_, "write_sysfs", delayed_write)

    assert desktop["apply_pwm"](4, 178) == "OK PWM 4 178"
    assert pwm.read_text(encoding="ascii").strip() == "178"
    assert enable.read_text(encoding="ascii").strip() == "1"
    assert writes.count(("pwm4", 178)) == 2


def test_privileged_desktop_pwm_helper_restores_automatic_after_unsettled_duty(
    tmp_path, monkeypatch
):
    """A permanently stuck PWM4 is reported and not left in new manual mode."""
    sensor = tmp_path / "hwmon-test"
    sensor.mkdir()
    pwm = sensor / "pwm4"
    enable = sensor / "pwm4_enable"
    pwm.write_text("127\n", encoding="ascii")
    enable.write_text("2\n", encoding="ascii")

    desktop = runpy.run_path(str(PRIVILEGED / "bc250-fan-pwm-helper"))
    globals_ = desktop["apply_pwm"].__globals__
    monkeypatch.setitem(globals_, "find_sensor", lambda: sensor)
    monkeypatch.setattr(globals_["time"], "sleep", lambda _seconds: None)

    def stuck_duty(path, value):
        if path != pwm:
            path.write_text(f"{value}\n", encoding="ascii")

    monkeypatch.setitem(globals_, "write_sysfs", stuck_duty)

    result = desktop["apply_pwm"](4, 178)

    assert result.startswith("ERR PWM 4 duty read-back was '127' after 16 attempts")
    assert result.endswith("Previous automatic mode was restored.")
    assert enable.read_text(encoding="ascii").strip() == "2"
    assert pwm.read_text(encoding="ascii").strip() == "127"


def test_game_mode_pwm_helper_retries_only_the_same_validated_duty(monkeypatch):
    game = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    globals_ = game["wait_for_hwmon_value"].__globals__

    class DelayedDuty:
        def __init__(self):
            self.current = "127"
            self.writes = []

        def read_text(self, **_kwargs):
            return f"{self.current}\n"

        def write_text(self, payload, **_kwargs):
            self.writes.append(payload)
            self.current = payload.strip()

    target = DelayedDuty()
    monkeypatch.setattr(globals_["time"], "sleep", lambda _seconds: None)

    matched, observed, attempts, _elapsed = game["wait_for_hwmon_value"](
        target,
        "178",
        retry_payload="178\n",
        attempts=16,
        interval=0.10,
    )

    assert (matched, observed, attempts) == (True, "178", 2)
    assert target.writes == ["178\n"]


def test_game_mode_pwm_helper_recovers_when_pwm4_ignores_its_first_duty_write(
    tmp_path, monkeypatch
):
    sensor = tmp_path / "hwmon-test"
    sensor.mkdir()
    pwm = sensor / "pwm4"
    enable = sensor / "pwm4_enable"
    pwm.write_text("127\n", encoding="ascii")
    enable.write_text("2\n", encoding="ascii")

    game = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    globals_ = game["action_fan_pwm"].__globals__
    monkeypatch.setitem(globals_, "find_nct_sensor", lambda: sensor)
    monkeypatch.setattr(globals_["time"], "sleep", lambda _seconds: None)

    original_write_text = type(pwm).write_text
    first_duty = True

    def delayed_first_duty(path, payload, *args, **kwargs):
        nonlocal first_duty
        if path == pwm and payload == "178\n" and first_duty:
            first_duty = False
            return len(payload)
        return original_write_text(path, payload, *args, **kwargs)

    monkeypatch.setattr(type(pwm), "write_text", delayed_first_duty)

    assert game["action_fan_pwm"](["4", "178"]) == 0
    assert pwm.read_text(encoding="ascii").strip() == "178"
    assert enable.read_text(encoding="ascii").strip() == "1"



def test_game_mode_helper_requires_bc250_identity_and_root_owned_gpu_editor():
    helper = _text(PRIVILEGED / "bc250-steamos-game-helper")
    assert "def bc250_identity_present" in helper
    assert "AMD BC-250 hardware identity was not detected" in helper
    assert "0x13fe" in helper
    assert "GOVERNOR_TOML_EDITOR = pathlib.Path('/usr/libexec/bc250-control-center/lib/governor_toml.py')" in helper
    assert "BC250_GOVERNOR_TOML_EDITOR" in helper
    assert "Governor TOML editor is not a root-owned" in helper

def test_game_mode_logging_drops_root_authority_and_rejects_log_symlink():
    helper = _text(PRIVILEGED / "bc250-steamos-game-helper")
    assert "def _append_user_log" in helper
    assert "os.seteuid(uid)" in helper
    assert "os.setegid(account.pw_gid)" in helper
    assert "O_NOFOLLOW" in helper
    assert "log_path.open('a'" not in helper


def test_game_mode_authorization_ignores_caller_forwarded_environment(monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    monkeypatch.setitem(namespace, "read_proc_environ", lambda _pid: {})
    monkeypatch.setitem(namespace, "process_tree", lambda _pid: [])
    monkeypatch.setitem(namespace, "global_process_names", lambda: set())

    allowed, reasons, negatives = namespace["detect_game_mode"](
        1234,
        {"SteamDeck": "1", "STEAM_GAMEPADUI": "1"},
    )

    assert allowed is False
    assert not any("origin env markers" in reason for reason in reasons)
    assert any("insufficient Game Mode score" in item for item in negatives)


def test_game_mode_cpu_uses_the_root_owned_audited_helper(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    repository = tmp_path / "bc250_smu_oc"
    repository.mkdir()
    (repository / "bc250_detect.py").write_text("print('owned')\n", encoding="utf-8")
    action = namespace["action_cpu_oc"]
    cpu_helper = tmp_path / "bc250-cpu-smu-helper"
    cpu_helper.write_text("#!/bin/sh\n", encoding="utf-8")
    cpu_helper.chmod(0o755)
    monkeypatch.setitem(action.__globals__, "tools_dir", lambda: tmp_path)
    monkeypatch.setitem(action.__globals__, "CPU_SMU_HELPER", cpu_helper)
    monkeypatch.setitem(
        action.__globals__, "trusted_installed_payload", lambda path, **_kwargs: path == cpu_helper
    )
    calls = []
    monkeypatch.setitem(
        action.__globals__, "run_checked",
        lambda command, **kwargs: calls.append((command, kwargs)) or 0,
    )

    assert action(["3850", "1200", "90"]) == 0
    command, options = calls[0]
    assert command == [
        str(cpu_helper), "detect", "3850", "1200", "90",
        str(repository / "overclock.conf"),
    ]
    assert options["timeout"] == 900
    assert "bc250_detect.py" not in " ".join(command)


def test_game_mode_cpu_service_uses_no_tty_root_helper_and_validates_values(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    action = namespace["action_cpu_service"]
    cpu_helper = tmp_path / "bc250-cpu-smu-helper"
    cpu_helper.write_text("#!/bin/sh\n", encoding="utf-8")
    cpu_helper.chmod(0o755)
    monkeypatch.setitem(action.__globals__, "CPU_SMU_HELPER", cpu_helper)
    monkeypatch.setitem(
        action.__globals__, "trusted_installed_payload", lambda path, **_kwargs: path == cpu_helper
    )
    calls = []
    monkeypatch.setitem(
        action.__globals__, "run_checked",
        lambda command, **kwargs: calls.append((command, kwargs)) or 0,
    )

    assert action(["install", "3700", "-11", "90"]) == 0
    assert calls[0][0] == [str(cpu_helper), "install-boot", "3700", "-11", "90"]
    assert calls[0][1]["timeout"] == 120

    assert action(["remove"]) == 0
    assert calls[1][0] == [str(cpu_helper), "disable-boot"]

    for invalid in (
        ["install", "3700", "-51", "90"],
        ["install", "4200", "0", "90"],
        ["install", "3700", "-11", "91"],
        ["remove", "extra"],
    ):
        assert action(invalid) != 0
    assert len(calls) == 2


def test_game_mode_gpu_voltage_uses_a_root_owned_staged_script():
    helper = _text(PRIVILEGED / "bc250-steamos-game-helper")
    installer = _text(ROOT / "scripts" / "install-local.sh")
    package_stage = _text(ROOT / "packaging" / "scripts" / "stage-package-root.sh")

    assert "GPU_LAB_SCRIPT = pathlib.Path('/usr/libexec/bc250-control-center/bc250-gpu-voltage-lab.sh')" in helper
    assert "def trusted_installed_payload" in helper
    assert "GPU_LAB_SCRIPT.resolve(strict=True)" not in helper
    assert "SYSTEM_GPU_LAB_SCRIPT=" in installer
    assert 'install -Dm755 "$gpu_lab_source" "$SYSTEM_GPU_LAB_SCRIPT"' in installer
    assert "bc250-gpu-voltage-lab.sh" in package_stage
    assert "bc250-steamos-amdgpu-overlay" in package_stage
    assert "prepare-steamos-telemetry-oc-overlay.py" in package_stage


def test_cyan_frequency_overlay_preflight_is_staged_before_service_start():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    package_stage = _text(ROOT / "packaging" / "scripts" / "stage-package-root.sh")
    preflight = _text(PRIVILEGED / "bc250-cyan-overlay-preflight")

    assert "SYSTEM_CYAN_OVERLAY_PREFLIGHT=" in installer
    assert "SYSTEM_CYAN_OVERLAY_DROPIN=" in installer
    assert "ExecStartPre=$SYSTEM_CYAN_OVERLAY_PREFLIGHT" in installer
    assert "bc250-cyan-overlay-preflight" in package_stage
    assert "patched_freq_metrics" in preflight
    assert '"/usr/bin/umount", "-l"' in preflight
    assert '"/usr/bin/mount", "--bind"' in preflight
    # The hwmon target may only be created once Cyan itself starts. Do not
    # delay service start for the former 75-second probe window.
    assert "for _ in range(40):" in preflight
    assert "range(300)" not in preflight


def test_game_mode_voltage_transaction_has_one_authoritative_dbus_deadline():
    helper = _text(PRIVILEGED / "bc250-steamos-game-helper")
    script = _text(ROOT / "scripts" / "system" / "bc250-gpu-voltage-lab.sh")

    assert 'BC250_CYAN_DBUS_WAIT_ATTEMPTS:-240' in script
    assert 'if restart_governor_preserving_range; then' in script
    assert 'systemctl restart "$SERVICE" && wait_for_governor_dbus' not in script
    assert 'command, timeout=420,' in helper


def test_game_mode_governor_config_reuses_the_root_owned_config_helper(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    action = namespace["action_governor_config"]

    helper = tmp_path / "bc250-governor-config-helper"
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(0o755)
    calls = []
    monkeypatch.setitem(action.__globals__, "GOVERNOR_CONFIG_HELPER", helper)
    monkeypatch.setitem(
        action.__globals__, "trusted_installed_payload", lambda path, **_kwargs: path == helper
    )
    monkeypatch.setitem(
        action.__globals__, "run_checked",
        lambda command, **kwargs: calls.append((command, kwargs)) or 0,
    )

    assert action(["set-frequency-range", "1000", "1850"]) == 0
    assert calls[0][0] == [
        str(helper),
        "set-frequency-range", "1000", "1850",
    ]
    assert action(["set-frequency-range", "1000", "bad"]) == 92



def test_game_mode_cpu_delegates_config_opening_to_the_root_owned_helper():
    game_helper = _text(PRIVILEGED / "bc250-steamos-game-helper")
    cpu_helper = _text(PRIVILEGED / "bc250-cpu-smu-helper")

    assert "CPU_SMU_HELPER" in game_helper
    assert "'detect', str(frequency), str(vid), str(temp)" in game_helper
    assert "bc250_detect.py as root" not in game_helper
    assert "def user_detection_config_fd" in cpu_helper
    assert "O_NOFOLLOW" in cpu_helper
    assert "--config', f'/proc/self/fd/{fd}'" in cpu_helper
    assert "pass_fds=(fd,)" in cpu_helper

def test_game_mode_cu_fails_closed_for_user_owned_backend(tmp_path, monkeypatch, capsys):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    repository = tmp_path / "bc250-cu-live-manager-steamos"
    repository.mkdir()
    script = repository / "bc250-cu-live-manager-bc250.sh"
    script.write_text("#!/bin/sh\necho owned\n", encoding="utf-8")
    script.chmod(0o755)
    action = namespace["action_cu"]
    database = repository / "database"
    database.mkdir()
    (database / "cyan_skillfish.asic").write_text("cyan_skillfish test\n", encoding="utf-8")
    monkeypatch.setitem(action.__globals__, "staged_cu_runtime", lambda: (script, database))

    rc = action(["--yes", "enable", "all"])

    assert rc == 62
    assert "CU_BACKEND_UNTRUSTED" in capsys.readouterr().err


def test_game_mode_cu_batch_removes_service_before_backend_operation(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    action = namespace["action_cu"]
    calls = []
    monkeypatch.setitem(action.__globals__, "remove_cu_service", lambda: calls.append("remove") or 0)
    monkeypatch.setitem(action.__globals__, "validate_staged_cu_backend", lambda *_args: "")
    monkeypatch.setitem(action.__globals__, "cu_safe_env", lambda: {})
    monkeypatch.setitem(
        action.__globals__, "staged_cu_runtime",
        lambda: (tmp_path / "backend", tmp_path / "database"),
    )

    class Completed:
        returncode = 0
        stdout = "verified dashboard\n"
        stderr = ""

    monkeypatch.setattr(
        action.__globals__["subprocess"],
        "run",
        lambda command, **_kwargs: calls.append(tuple(command[1:])) or Completed(),
    )
    payload = json.dumps([
        ["--yes", "uninstall-service"],
        ["--yes", "stock-dispatch"],
    ])

    assert action(["batch", payload]) == 0
    assert calls == ["remove", ("--yes", "stock-dispatch"), ("status",)]


@pytest.mark.parametrize(
    ("release", "backend", "database"),
    (
        (
            "ID=steamos\n",
            "/usr/libexec/bc250-control-center/bc250-cu-live-manager",
            "/usr/libexec/bc250-control-center/bc250-cu-umr-database",
        ),
        ("ID=bazzite\n", "/var/lib/bc250-control-center/bc250-cu-live-manager", None),
        ("ID=cachyos\n", "/var/lib/bc250-control-center/bc250-cu-live-manager", None),
    ),
)
def test_game_helper_selects_the_distribution_specific_cu_backend(
    release, backend, database, monkeypatch
):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    selector = namespace["staged_cu_runtime"]
    monkeypatch.setitem(selector.__globals__, "read_os_release", lambda: release.lower())

    selected_backend, selected_database = selector()

    assert str(selected_backend) == backend
    assert (str(selected_database) if selected_database is not None else None) == database


def test_steamos_daemon_helper_requires_exact_user_service_identity(monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    validate = namespace["validate_fan_daemon_identity"]

    assert validate(
        "0::/user.slice/user-1000.slice/user@1000.service/app.slice/bc250-control-centerd.service",
        "/usr/bin/python3 -m bc250cc.infrastructure.daemon",
        {"BC250_CONTROL_CENTER_DAEMON": "1"},
        1000,
        1000,
    ) == ""
    assert "not inside" in validate(
        "0::/user.slice/user-1000.slice/session.scope",
        "/usr/bin/python3 -m bc250cc.infrastructure.daemon",
        {"BC250_CONTROL_CENTER_DAEMON": "1"},
        1000,
        1000,
    )
    assert "marker" in validate(
        "0::/bc250-control-centerd.service",
        "/usr/bin/bc250-control-centerd",
        {},
        1000,
        1000,
    )


def test_forwarded_uid_cannot_overwrite_polkit_caller(monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-steamos-game-helper"))
    monkeypatch.setenv("PKEXEC_UID", "1000")

    parsed = namespace["_parse_invocation"]([
        "helper", "--origin-pid", "123", "--origin-uid", "2000", "--",
        "fan-daemon-pwm", "2", "170",
    ])

    assert parsed[0:2] == (123, 2000)
    assert parsed[3:] == ("fan-daemon-pwm", ["2", "170"])
    assert os.environ["PKEXEC_UID"] == "1000"


def test_user_daemon_unit_marks_the_dedicated_privileged_context():
    service_path = ROOT / "packaging/common/bc250-control-centerd.service"
    assert service_path.is_file()
    service = _text(service_path)
    assert "Environment=BC250_CONTROL_CENTER_DAEMON=1" in service


def test_steamos_daemon_polkit_path_never_requires_an_unavailable_gui_prompt():
    policy_path = ROOT / "privileged" / "policies" / "io.github.movacx.bc250-control-center.policy"
    assert policy_path.is_file()
    policy = _text(policy_path)
    action = policy.split(
        '<action id="io.github.movacx.bc250-control-center.steamos-game-helper">',
        1,
    )[1].split("</action>", 1)[0]

    assert "<allow_any>no</allow_any>" in action
    assert "<allow_inactive>no</allow_inactive>" in action
    assert "<allow_active>yes</allow_active>" in action
    assert "auth_admin" not in action


def test_cpu_smu_helper_uses_root_owned_audited_vendor_payload():
    import zipfile

    helper_path = PRIVILEGED / "bc250-cpu-smu-helper"
    vendor_path = ROOT / "privileged" / "lib" / "bc250_smu_oc_vendor.zip"
    assert helper_path.is_file()
    assert vendor_path.is_file()

    helper = _text(helper_path)
    assert "bc250_smu_oc_vendor.zip" in helper
    assert "EXPECTED_VENDOR_COMMIT = '43d6b4c6e38c57bc9ec8908c44675ce7d5fd3d2f'" in helper
    assert "EXPECTED_VENDOR_SHA256 = 'c9b0c9d18058e1ef20b88db098c975449eaea8fa940c1c23e39888723e128afd'" in helper
    assert "hashlib.sha256(VENDOR_ZIP.read_bytes()).hexdigest()" in helper
    assert "apply-live" in helper
    assert "install-boot" in helper
    assert "Type=oneshot" in helper
    assert "bc250_identity_present" in helper
    assert "O_NOFOLLOW" in helper
    assert "pass_fds" in helper

    with zipfile.ZipFile(vendor_path) as archive:
        names = set(archive.namelist())
        assert archive.read("UPSTREAM_COMMIT").decode().strip() == "43d6b4c6e38c57bc9ec8908c44675ce7d5fd3d2f"
        assert "LICENSE" in names
        assert "bc250_detect.py" in names
        assert "bc250_apply.py" in names
        assert "bc250_smu/api_q3.py" in names
        assert not any(".git/" in name or "__pycache__" in name for name in names)


def test_local_installer_stages_cpu_smu_helper_and_vendor_as_root_owned_files():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    uninstaller = _text(ROOT / "scripts" / "uninstall-local.sh")

    assert "SYSTEM_CPU_SMU_HELPER" in installer
    assert "SYSTEM_CPU_SMU_VENDOR" in installer
    assert 'install -Dm755 "$cpu_smu_helper_source" "$SYSTEM_CPU_SMU_HELPER"' in installer
    assert 'install -Dm644 "$cpu_smu_vendor_source" "$SYSTEM_CPU_SMU_VENDOR"' in installer
    assert 'privileged helper must be root-owned mode 0755' in installer
    assert 'privileged implementation must be root-owned mode 0644' in installer
    assert "SYSTEM_CPU_SMU_HELPER" in uninstaller
    assert "SYSTEM_CPU_SMU_VENDOR" in uninstaller


def test_steamos_amdgpu_overlay_is_packaged_and_uninstalled_with_its_staged_runtime():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    uninstaller = _text(ROOT / "scripts" / "uninstall-local.sh")

    assert "SYSTEM_STEAMOS_AMDGPU_OVERLAY" in installer
    assert 'install -Dm755 "$steamos_amdgpu_overlay_source" "$SYSTEM_STEAMOS_AMDGPU_OVERLAY"' in installer
    assert "SYSTEM_STEAMOS_AMDGPU_OVERLAY" in uninstaller
    assert "SYSTEM_STEAMOS_AMDGPU_BACKEND_DIR" in uninstaller
    assert 'remove_path "$SYSTEM_STEAMOS_AMDGPU_BACKEND_DIR"' in uninstaller


def test_uninstaller_removes_every_local_privileged_helper_and_reloads_a_removed_cyan_dropin():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    uninstaller = _text(ROOT / "scripts" / "uninstall-local.sh")

    for token in (
        "SYSTEM_OPENRC_SERVICE_HELPER",
        "SYSTEM_GPU_LAB_SCRIPT",
        "SYSTEM_CYAN_OVERLAY_PREFLIGHT",
        "SYSTEM_CYAN_OVERLAY_DROPIN",
    ):
        assert token in installer
        assert token in uninstaller
        assert f'"${token}"' in uninstaller
    assert "reload_systemd_after_overlay_removal" in uninstaller
    assert "[[ -d /run/systemd/system ]] || return 0" in uninstaller
    assert "remove_managed_privileged_file" in uninstaller
    assert "keeping unverified privileged file" in uninstaller
    assert 'cmp -s -- "$source" "$target"' in uninstaller
    assert "remove_managed_cyan_dropin" in uninstaller


def test_cpu_smu_helper_validates_scale_as_voltage_curve_not_mv():
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-cpu-smu-helper"))
    validate = namespace["validate_values"]
    estimated_vid = namespace["estimated_vid"]

    assert validate(3850, -30, 90) == (3850, -30, 90)
    with pytest.raises(ValueError, match="1325 mV"):
        validate(4200, 0, 90)
    with pytest.raises(ValueError, match="Scale"):
        validate(3850, -51, 90)
    with pytest.raises(ValueError, match="must be integers"):
        validate(3850.5, -30, 90)
    with pytest.raises(TypeError, match="must be integers"):
        estimated_vid(3850.5, -30)


def test_cpu_smu_helper_publishes_only_public_non_authorizing_qam_state(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-cpu-smu-helper"))
    publish = namespace["_publish_qam_state"]
    runtime_root = tmp_path / "run" / "bc250-control-center"
    runtime_root.mkdir(parents=True)
    evidence = runtime_root / "private" / "cpu-qam-manual.json"
    evidence.parent.mkdir()
    evidence.write_text("{}\n", encoding="utf-8")
    destination = runtime_root / "cpu-live-state.json"
    monkeypatch.setitem(publish.__globals__, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setitem(publish.__globals__, "QAM_PUBLIC_STATE", destination)
    monkeypatch.setitem(publish.__globals__, "QAM_MANUAL_EVIDENCE", evidence)
    monkeypatch.setitem(publish.__globals__, "ensure_private_runtime", lambda: evidence.parent)
    monkeypatch.setitem(publish.__globals__, "_trusted_root_file", lambda path, **_kwargs: path == evidence)
    monkeypatch.setitem(publish.__globals__, "_current_boot_id", lambda: "12345678-1234-1234-1234-123456789abc")
    monkeypatch.setitem(publish.__globals__, "_fsync_directory", lambda _path: None)
    active = {
        "mode": "manual", "frequency": 3700, "scale": -30,
        "temperature": 90, "estimated_vid": namespace["estimated_vid"](3700, -30),
        "reference_scale": -34, "observed_at": 1000, "persistable": True,
    }

    assert publish({"active_profile": active}) is True
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["active_profile"] == active
    assert payload["producer"] == "bc250-cpu-smu-helper"
    assert "config_sha256" not in destination.read_text(encoding="utf-8")
    assert destination.stat().st_mode & 0o777 == 0o644


def test_uninstaller_disables_service_that_depends_on_cpu_helper_before_removal():
    uninstaller = _text(ROOT / "scripts" / "uninstall-local.sh")
    assert "disable_managed_cpu_service" in uninstaller
    assert 'grep -Fq "$SYSTEM_CPU_SMU_HELPER apply-config"' in uninstaller
    assert "disable --now bc250-smu-oc.service" in uninstaller


def test_cpu_smu_boot_install_rolls_back_files_if_systemctl_enable_fails(tmp_path, monkeypatch):
    import subprocess as subprocess_module
    from types import SimpleNamespace

    namespace = runpy.run_path(str(PRIVILEGED / "bc250-cpu-smu-helper"))
    boot = tmp_path / "bc250-smu-oc.conf"
    service = tmp_path / "bc250-smu-oc.service"
    boot.write_text("old-config\n", encoding="utf-8")
    service.write_text("old-service\n", encoding="utf-8")
    action = namespace["action_install_boot"]
    monkeypatch.setitem(action.__globals__, "BOOT_CONFIG", boot)
    monkeypatch.setitem(action.__globals__, "SERVICE_PATH", service)

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["systemctl", "is-enabled"]:
            return SimpleNamespace(returncode=1)
        if argv[:2] == ["systemctl", "enable"] and kwargs.get("check") is True:
            raise subprocess_module.CalledProcessError(1, argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(namespace["subprocess"], "run", fake_run)

    with pytest.raises(subprocess_module.CalledProcessError):
        action(["3850", "-30", "90"])

    assert boot.read_text(encoding="utf-8") == "old-config\n"
    assert service.read_text(encoding="utf-8") == "old-service\n"
    assert ["systemctl", "daemon-reload"] in calls
    assert ["systemctl", "disable", "bc250-smu-oc.service"] in calls


def test_cpu_smu_boot_config_is_root_readable_for_unprivileged_validation(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from bc250cc.infrastructure.cpu_repository import CPURepository

    namespace = runpy.run_path(str(PRIVILEGED / "bc250-cpu-smu-helper"))
    boot = tmp_path / "bc250-smu-oc.conf"
    service = tmp_path / "bc250-smu-oc.service"
    action_install_boot = namespace["action_install_boot"]
    action_install_boot.__globals__["BOOT_CONFIG"] = boot
    action_install_boot.__globals__["SERVICE_PATH"] = service

    def fake_run(argv, **kwargs):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(namespace["subprocess"], "run", fake_run)
    assert action_install_boot(["3850", "-30", "90"]) == 0

    import stat
    assert stat.S_IMODE(boot.stat().st_mode) == 0o644
    parsed = CPURepository._read_cpu_oc_config(boot)
    assert parsed["valid"] is True
    assert parsed["frequency"] == 3850
    assert parsed["scale"] == -30


def test_local_installer_migrates_legacy_private_cpu_boot_config_to_readable_root_owned_mode():
    installer = _text(ROOT / "scripts" / "install-local.sh")
    assert 'SYSTEM_CPU_SMU_CONFIG="/etc/bc250-smu-oc.conf"' in installer
    assert 'config_owner=' in installer
    assert 'config_type=' in installer
    assert 'chmod 0644 "$SYSTEM_CPU_SMU_CONFIG"' in installer


def _qam_cpu_helper(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(PRIVILEGED / "bc250-cpu-smu-helper"))
    action = namespace["action_detect_qam"]
    scope = action.__globals__
    runtime = tmp_path / "run" / "bc250-control-center"
    private = runtime / "private"
    boot_id = tmp_path / "boot_id"
    boot_id.write_text("boot-a\n", encoding="ascii")
    monkeypatch.setitem(scope, "RUNTIME_ROOT", runtime)
    monkeypatch.setitem(scope, "PRIVATE_RUNTIME", private)
    monkeypatch.setitem(scope, "QAM_CONFIG", private / "cpu-qam-detected.conf")
    monkeypatch.setitem(scope, "QAM_EVIDENCE", private / "cpu-qam-detection.json")
    monkeypatch.setitem(scope, "QAM_MANUAL_CONFIG", private / "cpu-qam-manual.conf")
    monkeypatch.setitem(scope, "QAM_MANUAL_EVIDENCE", private / "cpu-qam-manual.json")
    monkeypatch.setitem(scope, "BOOT_ID_PATH", boot_id)
    monkeypatch.setitem(scope, "_trusted_root_directory", lambda path: path.is_dir() and not path.is_symlink())
    monkeypatch.setitem(
        scope,
        "_trusted_root_file",
        lambda path, maximum_size=64 * 1024: path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum_size,
    )
    monkeypatch.setattr(namespace["shutil"], "which", lambda *_args, **_kwargs: "/usr/bin/stress")
    return namespace, scope, boot_id


def test_qam_cpu_detector_uses_vid_then_applies_exact_generated_config(tmp_path, monkeypatch, capsys):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)
    calls = []

    def fake_vendor(module, args, *, pass_fds=()):
        calls.append((module, list(args), tuple(pass_fds)))
        if module == "bc250_detect":
            assert "--keep" not in args
            descriptor = pass_fds[0]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[overclock]\nfrequency = 3700\nscale = -30\nmax_temperature = 90\n")
        return 0

    monkeypatch.setitem(scope, "run_vendor_module", fake_vendor)

    assert namespace["action_detect_qam"](["3700", "1200", "90"]) == 0
    assert [call[0] for call in calls] == ["bc250_detect", "bc250_apply"]
    assert calls[1][1][0] == "--apply"
    assert calls[1][1][1].endswith(".conf")
    assert scope["QAM_CONFIG"].is_file()
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["ready"] is True
    assert payload["requested_frequency"] == 3700
    assert payload["requested_vid"] == 1200
    assert payload["frequency"] == 3700
    assert payload["scale"] == -30


def test_qam_cpu_detector_preserves_a_lower_safe_result_for_a_higher_request(
    tmp_path, monkeypatch, capsys
):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)

    def fake_vendor(module, args, *, pass_fds=()):
        if module == "bc250_detect":
            descriptor = pass_fds[0]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[overclock]\nfrequency = 3700\nscale = -11\nmax_temperature = 90\n")
        return 0

    monkeypatch.setitem(scope, "run_vendor_module", fake_vendor)

    assert namespace["action_detect_qam"](["4000", "1275", "90"]) == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["requested_frequency"] == 4000
    assert payload["requested_vid"] == 1275
    assert payload["frequency"] == 3700
    assert payload["scale"] == -11


def test_qam_cpu_detector_failure_publishes_no_installable_evidence(tmp_path, monkeypatch):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)
    monkeypatch.setitem(scope, "run_vendor_module", lambda *_args, **_kwargs: 9)

    assert namespace["action_detect_qam"](["3700", "1200", "90"]) == 9
    assert not scope["QAM_CONFIG"].exists()
    assert not scope["QAM_EVIDENCE"].exists()


def test_qam_cpu_install_uses_only_same_boot_detector_result(tmp_path, monkeypatch):
    namespace, scope, boot_id = _qam_cpu_helper(tmp_path, monkeypatch)

    def fake_vendor(module, _args, *, pass_fds=()):
        if module == "bc250_detect":
            descriptor = pass_fds[0]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[overclock]\nfrequency = 3650\nscale = -34\nmax_temperature = 90\n")
        return 0

    monkeypatch.setitem(scope, "run_vendor_module", fake_vendor)
    assert namespace["action_detect_qam"](["3700", "1175", "90"]) == 0

    installed = []
    monkeypatch.setitem(scope, "action_install_boot", lambda args: installed.append(list(args)) or 0)
    assert namespace["action_install_qam"]([]) == 0
    assert installed == [["3650", "-34", "90"]]

    boot_id.write_text("boot-b\n", encoding="ascii")
    assert namespace["action_install_qam"]([]) == 90
    assert installed == [["3650", "-34", "90"]]


def test_qam_cpu_manual_scale_is_bound_to_detection_and_becomes_install_candidate(
    tmp_path, monkeypatch, capsys
):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)
    calls = []

    def fake_vendor(module, args, *, pass_fds=()):
        calls.append((module, list(args)))
        if module == "bc250_detect":
            descriptor = pass_fds[0]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[overclock]\nfrequency = 3700\nscale = -34\nmax_temperature = 90\n")
        return 0

    monkeypatch.setitem(scope, "run_vendor_module", fake_vendor)
    assert namespace["action_detect_qam"](["3700", "1200", "90"]) == 0
    capsys.readouterr()

    assert namespace["action_apply_qam_scale"](["3700", "-30", "90"]) == 0
    active = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert active["mode"] == "manual"
    assert active["frequency"] == 3700
    assert active["scale"] == -30
    assert active["reference_scale"] == -34
    assert active["persistable"] is True
    assert scope["QAM_CONFIG"].read_text(encoding="utf-8").find("-34") >= 0
    assert scope["QAM_MANUAL_CONFIG"].read_text(encoding="utf-8").find("-30") >= 0

    installed = []
    monkeypatch.setitem(scope, "action_install_boot", lambda args: installed.append(list(args)) or 0)
    assert namespace["action_install_qam"]([]) == 0
    assert installed == [["3700", "-30", "90"]]
    assert [module for module, _args in calls] == ["bc250_detect", "bc250_apply", "bc250_apply"]


def test_qam_cpu_manual_scale_rejects_frequency_not_proven_by_detector(
    tmp_path, monkeypatch
):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)

    def fake_vendor(module, _args, *, pass_fds=()):
        if module == "bc250_detect":
            descriptor = pass_fds[0]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[overclock]\nfrequency = 3650\nscale = -34\nmax_temperature = 90\n")
        return 0

    monkeypatch.setitem(scope, "run_vendor_module", fake_vendor)
    assert namespace["action_detect_qam"](["3700", "1200", "90"]) == 0
    assert namespace["action_apply_qam_scale"](["3700", "-30", "90"]) == 93
    assert not scope["QAM_MANUAL_CONFIG"].exists()
    assert not scope["QAM_MANUAL_EVIDENCE"].exists()


def test_qam_cpu_manual_scale_failure_leaves_no_installable_manual_evidence(
    tmp_path, monkeypatch
):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)

    def detect_then_fail_apply(module, _args, *, pass_fds=()):
        if module == "bc250_detect":
            descriptor = pass_fds[0]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[overclock]\nfrequency = 3700\nscale = -34\nmax_temperature = 90\n")
            return 0
        return 0

    monkeypatch.setitem(scope, "run_vendor_module", detect_then_fail_apply)
    assert namespace["action_detect_qam"](["3700", "1200", "90"]) == 0

    monkeypatch.setitem(scope, "run_vendor_module", lambda *_args, **_kwargs: 9)
    assert namespace["action_apply_qam_scale"](["3700", "-30", "90"]) == 9
    assert not scope["QAM_MANUAL_CONFIG"].exists()
    assert not scope["QAM_MANUAL_EVIDENCE"].exists()


def test_cpu_private_runtime_does_not_hide_public_cu_snapshot_directory(tmp_path, monkeypatch):
    namespace, scope, _boot_id = _qam_cpu_helper(tmp_path, monkeypatch)
    config = namespace["root_temp_config"](3500, -30, 90)
    try:
        assert scope["RUNTIME_ROOT"].stat().st_mode & 0o777 == 0o755
        assert scope["PRIVATE_RUNTIME"].stat().st_mode & 0o777 == 0o700
        assert config.parent == scope["PRIVATE_RUNTIME"]
    finally:
        config.unlink(missing_ok=True)


def test_decky_installer_updates_cpu_detector_and_vendor_in_same_transaction():
    installer = _text(ROOT / "scripts" / "install-decky-quick-access.sh")
    assert "CPU_HELPER_SOURCE" in installer
    assert "CPU_VENDOR_SOURCE" in installer
    assert 'sudo install -Dm755 "$CPU_HELPER_SOURCE" "$CPU_HELPER_DEST"' in installer
    assert 'sudo install -Dm644 "$CPU_VENDOR_SOURCE" "$CPU_VENDOR_DEST"' in installer
    assert "previous-cpu-helper" in installer
    assert "previous-cpu-vendor" in installer
