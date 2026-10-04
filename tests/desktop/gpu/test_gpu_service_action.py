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
            "controlar_governor": lambda self, *args, **_options: calls.append(
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
            "_run_service_plan": GpuGovernorPage._run_service_plan,
        },
    )()

    GpuGovernorPage._service_action(page, "activar")

    dialog = calls[0]
    assert dialog[3]["tone"] == "red"
    assert ("Conflict", "cyan.service") in dialog[3]["summary"]
    assert ("controller", ("activar", True, True)) in calls


def _page_without_conflicts(calls, action_backend="cyan-skillfish-governor-smu"):
    controller = type("Controller", (), {
        "controlar_governor": lambda self, *args, **_options: calls.append(("controller", args)) or "terminal",
    })()
    last_operation = type("Status", (), {"set_values": lambda self, *args: None})()

    def run_action(_self, operation, success, *args, **kwargs):
        success(operation())

    return type("Page", (), {
        "controller": controller,
        "current_state": {"governor_backend": action_backend, "tools": {"incompatible_gpu_governors": []}},
        "last_operation_line": last_operation,
        "_append_console": lambda self, message: None,
        "_run_backend_action": run_action,
        "_run_service_plan": GpuGovernorPage._run_service_plan,
    })()


@pytest.mark.parametrize("action", ["activar", "desactivar", "reiniciar"])
def test_service_actions_go_straight_to_the_password(monkeypatch, action):
    """No window before the terminal's own password prompt: one decision, one step."""
    calls = []
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.ConfirmDialog",
        lambda *args, **kwargs: calls.append("dialog"),
    )
    GpuGovernorPage._service_action(_page_without_conflicts(calls), action)
    assert "dialog" not in calls
    assert ("controller", (action, False, False)) in calls


def test_the_status_opens_in_the_terminal_and_a_stopped_service_is_not_a_failure(monkeypatch):
    from bc250cc.infrastructure import gpu_repository
    from bc250cc.infrastructure.gpu_repository import GPURepository

    opened = []
    monkeypatch.setattr(gpu_repository, "detect_init_manager", lambda: type(
        "Init", (), {"kind": "systemd", "persistence_supported": True, "persistence_detail": ""})())

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _command_path(self, _name):
            return "/usr/bin/cyan"

        def _abrir_terminal(self, command, title):
            opened.append((command, title))
            return "launched"

    assert Repository().status_governor() == "launched"
    command, title = opened[0]
    assert "systemctl status cyan-skillfish-governor-smu.service --no-pager --full -n 0" in command
    # Only the current (or last) run, never the whole boot's history again.
    assert "_SYSTEMD_INVOCATION_ID=" in command and "-n 20" in command
    assert command.rstrip().endswith("true") and title == "GPU governor status"


def test_the_advanced_console_stays_but_has_no_actions(qtbot):
    from PyQt6.QtWidgets import QPushButton

    from frontends.desktop.pages.gpu_governor_view import OperationsConsole

    console = OperationsConsole()
    qtbot.addWidget(console)
    assert console.findChildren(QPushButton) == [] and console.text() == ""
