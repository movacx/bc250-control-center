"""The redesigned GPU view and the backend planner must agree on action names.

The view emits English ("restart"); ``plan_gpu_service_action`` only accepts
Spanish ("reiniciar") and raises ValueError otherwise.  Raising inside a Qt
slot aborts the process, so a mismatch here is a hard crash, not a no-op.
"""
import pytest

from bc250cc.application.gpu.service_action import plan_gpu_service_action
from frontends.desktop.pages.gpu_governor_integration import _SERVICE_ACTIONS
from frontends.desktop.pages.gpu_governor_view import GpuGovernorView

BACKEND = "cyan-skillfish-governor-smu"


def _service_actions(qtbot) -> tuple[str, ...]:
    view = GpuGovernorView()
    qtbot.addWidget(view)
    return tuple(view.service_buttons)


def test_every_service_button_reaches_a_supported_backend_action(qtbot):
    for action in _service_actions(qtbot):
        if action == "status":
            continue  # a pure read; it never reaches the planner
        assert action in _SERVICE_ACTIONS, action
        plan = plan_gpu_service_action(_SERVICE_ACTIONS[action], backend=BACKEND)
        assert plan.action == _SERVICE_ACTIONS[action]


def test_the_view_still_offers_a_status_read(qtbot):
    assert "status" in _service_actions(qtbot)


@pytest.mark.parametrize("action", sorted(_SERVICE_ACTIONS.values()))
def test_every_mapped_name_is_accepted_by_the_planner(action):
    assert plan_gpu_service_action(action, backend=BACKEND).action == action


def test_an_unmapped_name_would_have_raised():
    """Guards the assumption the mapping exists to satisfy."""
    with pytest.raises(ValueError):
        plan_gpu_service_action("restart", backend=BACKEND)
