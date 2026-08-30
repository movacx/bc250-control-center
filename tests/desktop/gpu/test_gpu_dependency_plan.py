import pytest

from bc250cc.application.preparation.gpu_dependency_plan import (
    DEFAULT_PREPARATION_COMPONENTS,
    build_gpu_dependency_plan,
)


def _tools(**updates):
    tools = {
        "governor_backend": "cyan-skillfish-governor-smu",
        "os_label": "SteamOS 3",
        "supported_gpu_governors": {
            "cyan-skillfish-governor-smu": {"active": True, "enabled": True},
            "oberon-governor": {"active": False, "enabled": False},
        },
        "gfx1013_compute": {"steamos_kernel_ready": False, "kernel": "6.16-test"},
    }
    tools.update(updates)
    return tools


def test_automatic_plan_uses_shared_route_and_preserves_component_contract():
    plan = build_gpu_dependency_plan(
        _tools(),
        current_governor="oberon-governor",
        action="prepare",
        preference="auto",
        selected_components=DEFAULT_PREPARATION_COMPONENTS,
    )
    assert plan.route == "shared"
    assert plan.resolved_governor == "cyan-skillfish-governor-smu"
    assert plan.components == DEFAULT_PREPARATION_COMPONENTS
    assert plan.include_pwm is True
    assert plan.conflicts == ()


def test_component_plan_enforces_runtime_and_umr_for_cu_manager():
    plan = build_gpu_dependency_plan(
        _tools(),
        current_governor="cyan-skillfish-governor-smu",
        action="prepare",
        preference="auto",
        selected_components={"cu_manager"},
    )
    assert plan.components == frozenset({"runtime", "umr", "cu_manager"})
    assert plan.include_pwm is False
    assert plan.conflicts == ()


def test_explicit_governor_plan_normalizes_and_deduplicates_conflicts():
    tools = _tools(
        supported_gpu_governors={
            "cyan-skillfish-governor-smu": {"active": True, "enabled": True},
            "oberon-governor": {"active": False, "enabled": False},
            "legacy": {"active": True, "identifier": "cyan-skillfish-governor-smu"},
        }
    )
    plan = build_gpu_dependency_plan(
        tools,
        current_governor="cyan-skillfish-governor-smu",
        action="prepare",
        preference="oberon-governor",
        selected_components={"runtime", "governor"},
    )
    assert plan.route == "governor"
    assert plan.conflicts == ("cyan-skillfish-governor-smu",)


def test_automatic_plan_accepts_mixed_backend_conflict_evidence():
    plan = build_gpu_dependency_plan(
        _tools(incompatible_gpu_governors=[{"service": "old.service"}, "legacy"]),
        current_governor="cyan-skillfish-governor-smu",
        action="prepare",
        preference="auto",
        selected_components={"runtime", "governor"},
    )
    assert plan.conflicts == ("old.service", "legacy")


def test_compatibility_plan_exposes_confirmation_evidence_without_execution():
    plan = build_gpu_dependency_plan(
        _tools(),
        current_governor="cyan-skillfish-governor-smu",
        action="steamos_compat",
        preference="",
    )
    assert plan.route == "compatibility"
    assert plan.requires_kernel_confirmation is True
    assert (plan.os_label, plan.kernel) == ("SteamOS 3", "6.16-test")


def test_unknown_dependency_action_is_rejected_before_controller_dispatch():
    with pytest.raises(ValueError, match="Unsupported dependency action"):
        build_gpu_dependency_plan(
            _tools(),
            current_governor="cyan-skillfish-governor-smu",
            action="format-disk",
            preference="auto",
        )
