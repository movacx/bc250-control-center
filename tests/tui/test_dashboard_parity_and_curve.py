"""Dashboard readings match the desktop sources; curve persistence is available inline."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from frontends.tui.pages import build_pages

from .fakes import FakeService, FakeUI, make_context
from .test_pages import choice, render, text_of


@pytest.mark.parametrize('present', [True, False])
def test_dashboard_shows_voltage_registered_oc_vrm_and_storage_without_hiding_missing_sensors(present):
    service = FakeService()
    service.rendimiento = lambda: SimpleNamespace(to_dict=lambda: {'cpu_voltage': 1199} if present else {})
    service.estado_cpu_oc_persistente = lambda: {'applied_this_boot': present, 'config':
                                               {'valid': True, 'frequency': 3850, 'scale': -34}}
    service.estado_control_fan_sistema = lambda: {'enabled': True, 'policy': {'mode': 'curve'}}
    ctx, ui = make_context(service), FakeUI()
    ctx.metrics = deepcopy(ctx.metrics)
    ctx.metrics['disk'] = {'used': 10 * 2**30, 'total': 100 * 2**30}
    ctx.metrics['sensors'].update(vrm_cpu_temperature_c=58 if present else None,
                                  vrm_gpu_temperature_c=61 if present else None)
    shown = text_of(render(build_pages()['dashboard'], ctx, ui))
    assert 'Core voltage' in shown and 'Registered OC' in shown
    assert 'VRM CPU' in shown and 'VRM GPU' in shown
    assert '10.0/100.0 GiB' in shown and 'System service' in shown
    assert 'N8' in shown and 'Hidden' in shown
    if present:
        assert '1.199 V' in shown and '3850 MHz' in shown and '-34' in shown
    else:
        assert '3850 MHz' not in shown and 'Not detected' in shown


def test_dashboard_installs_telemetry_only_after_confirmation_and_in_the_console():
    service, ui = FakeService(), FakeUI()
    ctx = make_context(service)
    choice(render(build_pages()['dashboard'], ctx, ui), 'Install BC250-Telemetry').handler(ui)
    assert ('gestionar_apu_telemetry', ('install',), {}) in service.calls
    assert ui.confirmations and ui.ran
    service.calls.clear()
    ui.confirm_answer = False
    choice(render(build_pages()['dashboard'], ctx, ui), 'Install BC250-Telemetry').handler(ui)
    assert not service.calls


