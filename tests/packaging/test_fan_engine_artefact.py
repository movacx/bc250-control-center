"""The root fan service runs a generated copy of the engine; keep it exact."""

from __future__ import annotations

import importlib.util
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "development" / "generate_fan_engine.py"
ARTEFACT = ROOT / "privileged" / "lib" / "bc250_fan_engine.py"
HELPER = ROOT / "privileged" / "helpers" / "bc250-fan-pwm-helper"


def test_the_committed_engine_is_what_the_generator_writes():
    generator = runpy.run_path(str(GENERATOR))
    assert ARTEFACT.read_text(encoding="utf-8") == generator["artefact"](), (
        "run scripts/development/generate_fan_engine.py"
    )
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_the_artefact_runs_isolated_and_agrees_with_canon():
    spec = importlib.util.spec_from_file_location("bc250_fan_engine_artefact", ARTEFACT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    from bc250cc.domain.fan import engine

    assert module.ENGINE_REVISION == engine.ENGINE_REVISION
    policy = {"schema": 2, "channels": {"2": {"mode": "curve", "points": [[40, 30], [80, 100]]}}}
    assert module.validate_policy(policy) == engine.validate_policy(policy)


def test_the_helper_requires_the_revision_it_was_built_for():
    from bc250cc.domain.fan import engine

    text = HELPER.read_text(encoding="utf-8")
    assert f"REQUIRED_ENGINE_REVISION = {engine.ENGINE_REVISION}\n" in text
    assert "/usr/libexec/bc250-control-center/lib" in text


def test_every_installer_ships_the_engine():
    for relative in (
        "packaging/scripts/stage-package-root.sh",
        "scripts/install-local.sh",
        "scripts/uninstall-local.sh",
        "scripts/qa/validate-install-source.sh",
        "src/bc250cc/infrastructure/privileged_install_state.py",
    ):
        assert "bc250_fan_engine.py" in (ROOT / relative).read_text(encoding="utf-8"), relative
