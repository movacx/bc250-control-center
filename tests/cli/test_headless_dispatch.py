from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.application.headless_dispatch import (
    SAFE_HANDLERS,
    DispatchResult,
    dispatch_safe,
    log_result,
)
from bc250cc.platform.packages.strategies.detector import detect_os_info
from frontends.cli import main


class Host:
    def _os_release(self):
        return {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Fixture"}

    def _command_path(self, _name):
        return ""

    def _tool_dir(self):
        return Path("/tmp/bc250-headless-fixture/tools")


def test_safe_dispatch_registry_is_complete_and_immutable():
    assert set(SAFE_HANDLERS) == {
        "system", "components", "integrations", "quick-access", "parse-log",
        "recovery", "profiles", "metrics", "release-gates", "qualification", "telemetry",
    }
    with pytest.raises(TypeError):
        SAFE_HANDLERS["hardware-write"] = lambda *_args: None


def test_unknown_command_is_left_for_the_dependency_boundary():
    result = dispatch_safe(Namespace(command="dependencies"), object())
    assert result is None


def test_telemetry_command_emits_passive_diagnostics(monkeypatch, capsys):
    import json

    from bc250cc.infrastructure import apu_telemetry

    report = {"schema_version": 1, "metrics": {}, "status": "unavailable"}
    monkeypatch.setattr(apu_telemetry, "collect_apu_telemetry", lambda: report)
    assert main(["--json", "telemetry"], host=Host()) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_system_handler_returns_typed_result_without_side_effects():
    info = detect_os_info(
        {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Fixture"},
        has_rpm_ostree=False,
    )
    result = dispatch_safe(Namespace(command="system"), info)
    assert isinstance(result, DispatchResult)
    assert result.exit_code == 0
    assert result.payload["family"] == "ubuntu"


def test_parse_log_exposes_verified_evidence_not_just_the_shell_exit_code(tmp_path):
    legacy = tmp_path / "legacy.log"
    legacy.write_text("completed without a structured marker\n", encoding="utf-8")

    result = log_result(Namespace(path=legacy, exit_code=0), object())

    assert result.exit_code == 0
    assert result.payload["successful"] is True
    assert result.payload["has_structured_evidence"] is False
    assert result.payload["verified_success"] is False
    assert "without structured" in result.payload["safe_next_action"]


def test_dependency_runner_receives_only_fixed_bash_argv(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=23)

    exit_code = main(
        ["dependencies", "--component", "runtime", "--mode", "check"],
        host=Host(), runner=runner,
    )
    assert exit_code == 23
    assert calls[0][0][:2] == ["bash", "-lc"]
    assert len(calls[0][0]) == 3
    assert calls[0][1] == {"check": False}


def test_apply_needs_both_independent_confirmation_flags():
    def forbidden(*_args, **_kwargs):
        pytest.fail("runner must stay closed")

    for flags in ([], ["--yes"], ["--allow-system-changes"]):
        with pytest.raises(SystemExit, match="pass both"):
            main(
                ["dependencies", "--mode", "apply", *flags],
                host=Host(), runner=forbidden,
            )


def test_rejected_apply_does_not_even_construct_a_distribution_command():
    class GuardedHost(Host):
        def _tool_dir(self):
            pytest.fail("rejected apply must stop before command construction")

    with pytest.raises(SystemExit, match="pass both"):
        main(["dependencies", "--mode", "apply"], host=GuardedHost())
