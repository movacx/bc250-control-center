"""Preparing dependencies stages the GDDR6 source like every other tool."""

from dataclasses import replace
from pathlib import Path

from bc250cc.application.preparation.component_engine import (
    COMPONENT_SPECS,
    normalize_components,
)
from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOL_DIRECTORIES,
    EXTERNAL_TOOLS,
)
from bc250cc.infrastructure.preparation_workflow import (
    PreparationContext,
    _mutable_source_commands,
)

UPSTREAM = EXTERNAL_TOOLS["gddr6_memory_temp"].upstream
DESTINATION = Path("/home/tester/.local/share/tools") / EXTERNAL_TOOL_DIRECTORIES[
    "gddr6_memory_temp"
]


class FakeRepository:
    def _hardware_source_checkout_command(self, url, destination, os_repository=None):
        return f"clone {url} -> {destination}"

    def _generic_cu_privileged_backend_stage_command(self, script):
        return f"stage {script}"


def _context(components):
    return PreparationContext(
        repository=FakeRepository(),
        os_repository=None,
        selected_components=frozenset(components),
        selected_governor="cyan",
        conflicts=(),
        disable_conflicts=False,
        include_pwm=False,
        paths={},
        tool_dir=Path("/home/tester/.local/share/tools"),
        cpu_destination=Path("/tmp/cpu"),
        core_repository="https://example.invalid/core",
        core_destination=Path("/tmp/core"),
        core_script=Path("/tmp/core/bc250-unlock-cores.py"),
        cu_spec={
            "destination": Path("/tmp/cu"),
            "upstream_script": Path("/tmp/cu/up.sh"),
            "script": Path("/tmp/cu/run.sh"),
            "repository": "https://example.invalid/cu",
        },
        prepare_cu_backend="",
        cpu_repository="https://example.invalid/cpu",
        cpu_reviewed_revision="0" * 40,
        cyan_directory="cyan",
        steamos_fix_directory="steamos",
        gddr6_repository=UPSTREAM,
        gddr6_destination=DESTINATION,
    )


def test_the_component_exists_and_is_declared_high_risk():
    spec = COMPONENT_SPECS["gddr6_temp"]

    assert spec.risk == "high"
    assert not spec.required
    assert "gddr6_temp" in normalize_components(["gddr6_temp"])


def test_selecting_it_clones_the_reviewed_upstream_source():
    commands = "\n".join(_mutable_source_commands(_context(["gddr6_temp"])))

    assert f"clone {UPSTREAM} -> {DESTINATION}" in commands
    # The privileged reader imports this package and refuses it otherwise.
    assert "bc250_smu" in commands
    assert "SMUPayload.bin" in commands


def test_not_selecting_it_stages_nothing():
    commands = "\n".join(_mutable_source_commands(_context(["cpu_oc"])))

    assert UPSTREAM not in commands


def test_preparing_everything_else_still_works_without_a_destination():
    """An older caller that does not fill the new context fields must not break."""
    context = replace(_context(["gddr6_temp"]), gddr6_destination=None)

    commands = "\n".join(_mutable_source_commands(context))

    assert UPSTREAM not in commands
