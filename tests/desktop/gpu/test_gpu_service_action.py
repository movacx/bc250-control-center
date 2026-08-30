import pytest
from PyQt6.QtWidgets import QDialog

from bc250cc.application.gpu.service_action import plan_gpu_service_action
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


@pytest.mark.parametrize(
    ("action", "label", "persistence", "tone"),
    (
        ("activar", "Enable and start", "Enabled", "blue"),
        ("reiniciar", "Restart", "Unchanged", "blue"),
        ("desactivar", "Stop and disable", "Disabled", "orange"),
    ),
)
def test_service_action_plan_has_deterministic_lifecycle_copy(
    action, label, persistence, tone,
):
    plan = plan_gpu_service_action(
        action,
        backend="cyan-skillfish-governor-smu",
    )
    assert (plan.label, plan.boot_persistence, plan.tone) == (
        label, persistence, tone,
    )
    assert plan.service == "cyan-skillfish-governor-smu.service"
    assert plan.has_conflicts is False


def test_oberon_conflicts_accept_mixed_evidence_and_force_red_confirmation():
    plan = plan_gpu_service_action(
        "activar",
        backend="oberon-governor",
        incompatible_governors=[
            {"identifier": "cyan-skillfish-governor-smu"},
            "legacy.service",
            {"service": "legacy.service"},
        ],
    )
    assert plan.service == "oberon-governor.service"
    assert plan.conflicts == (
        "cyan-skillfish-governor-smu", "legacy.service",
    )
    assert plan.has_conflicts is True
    assert plan.tone == "red"
    assert plan.confirm_text == "Disable conflict and enable service"
    assert dict(plan.description_values) == {
        "governors": "cyan-skillfish-governor-smu, legacy.service",
        "selected_governor": "oberon-governor",
    }


def test_stop_action_never_treats_other_governors_as_a_start_conflict():
    plan = plan_gpu_service_action(
        "desactivar",
        backend="oberon-governor",
        incompatible_governors=[{"identifier": "cyan-skillfish-governor-smu"}],
    )
    assert plan.conflicts == ()
    assert plan.tone == "orange"


def test_unknown_service_action_is_rejected_before_controller_dispatch():
    with pytest.raises(ValueError, match="Unsupported governor service action"):
        plan_gpu_service_action("erase", backend="oberon-governor")


def test_real_page_adapter_dispatches_the_exact_confirmed_plan(monkeypatch):
    calls = []

    class AcceptedDialog:
        def __init__(self, title, description, **options):
            calls.append(("dialog", title, description, options))

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.ConfirmDialog", AcceptedDialog
    )
    controller = type(
        "Controller",
        (),
        {
            "controlar_governor": lambda self, *args: calls.append(
                ("controller", args)
            ) or "terminal"
        },
    )()
    last_operation = type(
        "Status", (), {"set_values": lambda self, *args: calls.append(("status", args))}
    )()

    def run_action(_self, operation, success, *args, **kwargs):
        success(operation())

    page = type(
        "Page",
        (),
        {
            "controller": controller,
            "current_state": {
                "governor_backend": "oberon-governor",
                "tools": {"incompatible_gpu_governors": ["cyan.service"]},
            },
            "last_operation_line": last_operation,
            "_append_console": lambda self, message: calls.append(("console", message)),
            "_run_backend_action": run_action,
        },
    )()

    GpuGovernorPage._service_action(page, "activar")

    dialog = calls[0]
    assert dialog[3]["tone"] == "red"
    assert ("Conflict", "cyan.service") in dialog[3]["summary"]
    assert ("controller", ("activar", True, True)) in calls
