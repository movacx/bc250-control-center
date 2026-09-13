from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOL_DIRECTORIES,
    EXTERNAL_TOOL_LIFECYCLES,
    EXTERNAL_TOOLS,
    LifecycleAction,
)

KEY = "gddr6_memory_temp"


def test_manifest_declares_the_reverse_engineered_smu_tool_as_high_risk():
    spec = EXTERNAL_TOOLS[KEY]

    assert spec.upstream == "https://github.com/pan-Rijovich/bc250-memory-temperature"
    assert spec.license == "MIT"
    assert len(spec.reviewed_revision) == 40
    assert spec.hardware_writes is True
    assert spec.privilege_class != "userspace"
    assert spec.adoption_ready is True
    assert spec.redistribution_ready is True


def test_lifecycle_never_exposes_rollback_since_only_a_power_cycle_reverts_it():
    lifecycle = EXTERNAL_TOOL_LIFECYCLES[KEY]

    assert LifecycleAction.CHECK in lifecycle.actions
    assert LifecycleAction.APPLY in lifecycle.actions
    assert LifecycleAction.ROLLBACK not in lifecycle.actions
    assert lifecycle.validation_issues() == ()


def test_apply_requires_confirmation_and_is_flagged_as_writing_hardware(tmp_path):
    from bc250cc.infrastructure.external_tools.catalog import ExternalToolAdapter

    class VerifiedGitReader:
        def origin(self, _path):
            return EXTERNAL_TOOLS[KEY].upstream

        def revision(self, _path):
            return EXTERNAL_TOOLS[KEY].reviewed_revision

        def dirty(self, _path):
            return False

    destination = tmp_path / "tool"
    (destination / ".git").mkdir(parents=True)
    adapter = ExternalToolAdapter(EXTERNAL_TOOLS[KEY], destination, VerifiedGitReader())

    plan = adapter.plan(LifecycleAction.APPLY)

    assert plan.available
    assert plan.hardware_writes
    assert plan.requires_confirmation


def test_directory_mapping_exists_for_checkout_inventory():
    assert KEY in EXTERNAL_TOOL_DIRECTORIES
