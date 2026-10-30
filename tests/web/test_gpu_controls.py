"""Web GPU controls keep the desktop's voltage rules and file/runtime distinction."""
from types import SimpleNamespace

import pytest

from bc250cc.domain.gpu.voltage_profiles import (
    GOVERNOR_DEFAULT_VOLTAGES,
    voltage_profile,
)
from frontends.web.actions import Invalid, gpu_voltage, gpu_voltage_custom
from frontends.web.data import _gpu


def state(*, enabled=True, loaded=2000, backend="cyan-skillfish-governor-smu"):
    points = [{"frequency": f, "voltage": v} for f, v in GOVERNOR_DEFAULT_VOLTAGES.items() if enabled or f <= 2000]
    return {"governor_backend": backend, "allowed_min": 500, "allowed_max": loaded,
            "safe_points_with_voltage": points,
            "high_frequency_points": {"enabled_frequencies": [p["frequency"] for p in points if p["frequency"] > 2000]}}


def test_file_points_expand_profiles_before_cyan_reloads_and_shrink_after_commenting():
    enabled = _gpu(state(), None)
    assert enabled["allowed_max"] == 2000  # truth about the currently loaded runtime
    assert enabled["profile_max"] == 2400
    assert max(f for f, _ in enabled["voltage_lab"]["points"]) == 2400
    disabled = _gpu(state(enabled=False, loaded=2400), None)
    assert disabled["allowed_max"] == 2400
    assert disabled["profile_max"] == 2000
    assert max(f for f, _ in disabled["voltage_lab"]["points"]) == 2000


def test_voltage_levels_are_the_shared_exact_curves_including_4_5_6():
    lab = _gpu(state(), None)["voltage_lab"]
    assert {p["level"]: p["values"] for p in lab["levels"]} == {level: voltage_profile(level) for level in range(7)}
    called = []
    ctx = SimpleNamespace(service=SimpleNamespace(aplicar_laboratorio_voltaje_gpu=called.append))
    for level in range(7):
        confirmation, work = gpu_voltage(ctx, {"level": level}, None)
        assert confirmation == 2
        work()
    assert called == list(range(7))


@pytest.mark.parametrize("values", [{}, [], {"500": True}, {"500": 599}, {"500": 1211}, {"0500": 700}, {"500;id": 700}])
def test_custom_voltage_rejects_bad_shapes_and_values(values):
    with pytest.raises(Invalid):
        gpu_voltage_custom(None, {"values": values}, None)


@pytest.mark.parametrize("values,backend", [({"777": 800}, "cyan"), ({"500": 900, "1000": 800}, "cyan"), ({"500": 700}, "oberon-governor")])
def test_custom_voltage_rechecks_active_points_monotonicity_and_backend(values, backend):
    calls = []
    service = SimpleNamespace(estado_bc250=lambda: state(backend=backend),
                              aplicar_laboratorio_voltaje_gpu_personalizado=calls.append)
    _, work = gpu_voltage_custom(SimpleNamespace(service=service), {"values": values}, None)
    with pytest.raises(Invalid):
        work()
    assert not calls


def test_valid_custom_curve_reaches_only_the_existing_service():
    calls = []
    service = SimpleNamespace(estado_bc250=state, aplicar_laboratorio_voltaje_gpu_personalizado=calls.append)
    level, work = gpu_voltage_custom(SimpleNamespace(service=service), {"values": {"500": 705}}, None)
    assert level == 2 and not calls
    work()
    assert calls == [{500: 705}]


def test_enabled_but_blocked_points_do_not_raise_the_profile_ceiling():
    raw = state()
    raw["high_frequency_points"]["allowed_frequencies"] = []
    assert _gpu(raw, None)["profile_max"] == 2000
