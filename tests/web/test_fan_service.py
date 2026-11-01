"""Fan boot service actions reuse the protected application service and saved policy."""
from types import SimpleNamespace

import pytest

from frontends.web.actions import Invalid, fan_curve, fan_service
from frontends.web.data import _fans


class Settings:
    def __init__(self):
        self.config = {}

    def read_local_config(self):
        return self.config.copy()

    def save_local_config(self, payload):
        self.config.update(payload)


def context(**state):
    calls = []
    system = {"available": True, "enabled": False, **state}
    service = SimpleNamespace(
        estado_control_fan_sistema=lambda: system,
        activar_control_fan_sistema=lambda policy: calls.append(("enable", policy)),
        sincronizar_control_fan_sistema=lambda policy: calls.append(("sync", policy)),
        desactivar_control_fan_sistema=lambda: calls.append(("disable", None)),
    )
    return SimpleNamespace(service=service, settings=Settings()), system, calls


CURVE = {"pwm": 2, "enabled": True, "points": [[40, 50], [60, 75], [75, 100]]}


def test_save_and_start_enables_the_service_with_the_edited_curve():
    ctx, _system, calls = context()
    level, work = fan_curve(ctx, {**CURVE, "start_service": True}, None)
    assert level == 1 and not calls
    work()
    assert calls[0][0] == "enable"
    assert calls[0][1]["points"] == CURVE["points"]
    assert calls[0][1]["pwm"] == 2
    assert ctx.settings.config["fan_curve"]["enabled"]


@pytest.mark.parametrize("operation", ["enable", "sync", "disable"])
def test_service_operations_use_current_saved_policy(operation):
    ctx, system, calls = context()
    fan_curve(ctx, CURVE, None)[1]()
    system["enabled"] = True
    level, work = fan_service(ctx, {"operation": operation}, None)
    assert level == 1 and not calls
    work()
    assert calls[0][0] == operation
    if operation != "disable":
        assert calls[0][1]["points"] == CURVE["points"]


@pytest.mark.parametrize("operation", ["enable", "sync", "disable"])
def test_handoff_is_rechecked_when_the_action_executes(operation):
    ctx, system, calls = context()
    fan_curve(ctx, CURVE, None)[1]()
    _, work = fan_service(ctx, {"operation": operation}, None)
    system["external"] = True
    with pytest.raises(Invalid):
        work()
    assert not calls


@pytest.mark.parametrize("state", [{"available": False}, {"external": True}])
def test_blocked_combined_activation_does_not_save_the_curve(state):
    ctx, _system, calls = context(**state)
    _, work = fan_curve(ctx, {**CURVE, "start_service": True}, None)
    with pytest.raises(Invalid):
        work()
    assert not calls and not ctx.settings.config


def test_no_policy_or_invalid_operation_cannot_start_service():
    ctx, _system, calls = context()
    with pytest.raises(Invalid):
        fan_service(ctx, {"operation": "enable"}, None)[1]()
    with pytest.raises(Invalid):
        fan_service(ctx, {"operation": "arbitrary"}, None)
    with pytest.raises(Invalid):
        fan_curve(ctx, {**CURVE, "start_service": "yes"}, None)
    with pytest.raises(Invalid):
        fan_curve(ctx, {**CURVE, "enabled": False, "start_service": True}, None)
    assert not calls


def test_disabling_a_saved_curve_clears_the_services_old_policy():
    ctx, system, calls = context()
    fan_curve(ctx, CURVE, None)[1]()
    system["enabled"] = True
    fan_curve(ctx, {**CURVE, "enabled": False}, None)[1]()
    assert calls == [("sync", None)]


def test_web_state_exposes_persistence_availability_and_policy():
    ctx, _system, _calls = context()
    fan_curve(ctx, CURVE, None)[1]()
    data = _fans({"system": {"enabled": True, "available": True, "state": "active"},
                  "config": ctx.settings.config}, ctx)
    assert data["service"] == {"enabled": True, "available": True, "state": "active", "has_policy": True, "out_of_date": True}
