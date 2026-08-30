import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.application.recovery import service as recovery_facade
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS
from bc250cc.infrastructure.persistence import recovery_engine
from bc250cc.infrastructure.persistence.recovery_engine import (
    RecoverySnapshotRepository,
)
from bc250cc.platform.init.services import InitManagerState
from frontends.cli import main


class Host:
    def __init__(self, root: Path):
        self.root = root

    def _os_release(self):
        return {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Test Ubuntu"}

    def _command_path(self, _name):
        return ""

    def _tool_dir(self):
        return self.root / "tools"

    def _home(self):
        return self.root


class RuntimeHost(Host):
    def _execute_readonly(self, command, timeout=2):
        assert command[:2] == ["git", "-C"]
        assert timeout == 2
        spec = EXTERNAL_TOOLS["cpu_smu_oc"]
        if tuple(command[3:]) == ("remote", "get-url", "origin"):
            return 0, spec.upstream, ""
        if tuple(command[3:]) == ("rev-parse", "--verify", "HEAD"):
            return 0, spec.reviewed_revision, ""
        if tuple(command[3:]) == ("status", "--porcelain", "--untracked-files=all"):
            return 0, "?? overclock.conf\n", ""
        return 1, "", "unsupported"


def test_system_and_component_json_are_machine_readable(tmp_path, capsys):
    assert main(["--json", "system"], host=Host(tmp_path)) == 0
    system = json.loads(capsys.readouterr().out)
    assert system["family"] == "ubuntu"
    assert main(["--json", "components"], host=Host(tmp_path)) == 0
    components = json.loads(capsys.readouterr().out)
    assert components["runtime"]["required"]


def test_dependency_defaults_to_safe_plan(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    assert main(["dependencies", "--component", "runtime"], host=Host(tmp_path), runner=runner) == 0
    assert "--mode plan" in calls[0][0][-1]


def test_apply_is_double_gated_before_runner(tmp_path):
    def forbidden_runner(*_args, **_kwargs):
        raise AssertionError("runner must not be called")

    with pytest.raises(SystemExit, match="Refusing apply"):
        main(["dependencies", "--mode", "apply"], host=Host(tmp_path), runner=forbidden_runner)


def test_explicit_apply_can_be_rendered_without_execution(tmp_path, capsys):
    assert main(
        ["--json", "dependencies", "--mode", "apply", "--render-command"],
        host=Host(tmp_path),
        runner=lambda *_args, **_kwargs: pytest.fail("must not execute"),
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "apply"
    assert "--mode apply" in payload["command"]


def test_integration_audit_is_valid_json(tmp_path, capsys):
    assert main(["--json", "integrations"], host=Host(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert "check" in payload["tools"]["core_unlock"]["lifecycle"]["actions"]
    assert payload["tools"]["gfx1013_direct"]["lifecycle"]["actions"] == [
        "check", "install", "rollback", "uninstall"
    ]
    assert payload["tools"]["gfx1013_direct"]["automated"] is True
    assert payload["tools"]["gfx1013_direct"]["payload_distribution"] == (
        "runtime-fetch-reviewed-revision"
    )


def test_runtime_integration_audit_is_filtered_and_read_only(tmp_path, capsys):
    checkout = tmp_path / "tools" / "bc250_smu_oc"
    (checkout / ".git").mkdir(parents=True)

    assert main(
        ["--json", "integrations", "--runtime", "--tool", "cpu_smu_oc"],
        host=RuntimeHost(tmp_path),
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert set(payload["tools"]) == {"cpu_smu_oc"}
    assert set(payload["runtime"]) == {"cpu_smu_oc"}
    runtime = payload["runtime"]["cpu_smu_oc"]
    assert runtime["verified"] is False
    assert runtime["source_verified"] is True
    assert runtime["tracked_dirty"] is False
    assert runtime["untracked_count"] == 1


def test_integration_filter_rejects_undeclared_tool(tmp_path):
    with pytest.raises(SystemExit, match="Unknown external integration"):
        main(["integrations", "--tool", "not-declared"], host=Host(tmp_path))


def test_quick_access_inventory_cli_is_read_only_and_machine_readable(tmp_path, capsys, monkeypatch):
    import bc250cc.infrastructure.external_tools.quick_access_inventory as inventory_module
    monkeypatch.setattr(
        inventory_module,
        "detect_init_manager",
        lambda: InitManagerState("unknown", False, "test unknown init"),
    )
    assert main(["--json", "quick-access"], host=Host(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supported"] is False
    assert payload["ready"] is False
    assert "existing Decky Loader" in payload["next_action"]


def test_profile_export_preview_and_import_confirmation(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    bundle = tmp_path / "profile.json"
    assert main(["--json", "profiles", "export", str(bundle)], host=Host(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out)["exported"] == str(bundle)
    assert main(["--json", "profiles", "preview", str(bundle)], host=Host(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == 1
    with pytest.raises(SystemExit, match="preview first"):
        main(["profiles", "import", str(bundle)], host=Host(tmp_path))


def test_profile_cli_reports_invalid_bundle_as_a_concise_error(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken", encoding="utf-8")

    with pytest.raises(SystemExit, match="^Profile bundle error:") as captured:
        main(["profiles", "preview", str(invalid)], host=Host(tmp_path))

    assert captured.value.__cause__ is not None


def test_metrics_cli_reads_existing_history_without_hardware_probe(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert main(["--json", "metrics", "list"], host=Host(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out) == {"metrics": []}


def test_recovery_inventory_is_read_only_and_machine_readable(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert main(["--json", "recovery", "list"], host=Host(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["snapshots"] == []
    assert payload["restore_available"] is False


def test_recovery_create_writes_private_user_snapshot_only(
    tmp_path, capsys, monkeypatch
):
    source_root = tmp_path / "etc"
    source_root.mkdir()
    source = source_root / "bc250.conf"
    source.write_text("safe=true\n", encoding="utf-8")
    monkeypatch.setattr(recovery_engine, "ALLOWED_SYSTEM_PREFIXES", (source_root,))
    monkeypatch.setattr(recovery_engine, "BOOT_CRITICAL_PREFIXES", ())
    monkeypatch.setattr(
        recovery_facade, "DEFAULT_RECOVERY_SOURCES", (str(source),)
    )
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    assert main(
        ["--json", "recovery", "create", "--label", "before-test"],
        host=Host(tmp_path),
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verified"] is True
    assert payload["entries"] == 1
    assert payload["restore_available"] is False
    assert Path(payload["path"]).is_dir()


def test_recovery_verify_requires_explicit_snapshot(tmp_path):
    with pytest.raises(SystemExit, match="requires a snapshot path"):
        main(["recovery", "verify"], host=Host(tmp_path))


def test_recovery_plan_reports_live_divergence_without_restore(
    tmp_path, capsys, monkeypatch
):
    source_root = tmp_path / "etc"
    source_root.mkdir()
    source = source_root / "bc250.conf"
    source.write_text("original=true\n", encoding="utf-8")
    monkeypatch.setattr(recovery_engine, "ALLOWED_SYSTEM_PREFIXES", (source_root,))
    monkeypatch.setattr(recovery_engine, "BOOT_CRITICAL_PREFIXES", ())
    snapshot = RecoverySnapshotRepository(tmp_path / "snapshots").capture([source])
    source.write_text("changed=true\n", encoding="utf-8")

    assert main(["--json", "recovery", "plan", str(snapshot)], host=Host(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["verified"] is True
    assert payload["blocked"] is False
    assert payload["current_state"][0]["state"] == "changed-since-snapshot"
    assert payload["current_state"][0]["matches_snapshot"] is False


def test_recovery_export_requires_output_and_writes_only_portable_evidence(
    tmp_path, capsys, monkeypatch
):
    source_root = tmp_path / "etc"
    source_root.mkdir()
    source = source_root / "bc250.conf"
    source.write_text("safe=true\n", encoding="utf-8")
    monkeypatch.setattr(recovery_engine, "ALLOWED_SYSTEM_PREFIXES", (source_root,))
    monkeypatch.setattr(recovery_engine, "BOOT_CRITICAL_PREFIXES", ())
    snapshot = RecoverySnapshotRepository(tmp_path / "snapshots").capture([source])

    with pytest.raises(SystemExit, match="requires --output"):
        main(["recovery", "export", str(snapshot)], host=Host(tmp_path))

    destination = tmp_path / "portable-recovery.zip"
    assert main(
        ["--json", "recovery", "export", str(snapshot), "--output", str(destination)],
        host=Host(tmp_path),
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == str(destination)
    assert payload["automatic_restore_enabled"] is False
    assert destination.is_file()
