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


def test_automatic_curve_can_save_and_enable_its_service_without_switching_tabs():
    service, ui = FakeService(), FakeUI()
    service.estado_control_fan_sistema = lambda: {'enabled': False, 'available': True, 'state': 'off'}
    ctx = make_context(service)
    page = build_pages()['fans']
    ctx.settings.read_local_config = lambda: {}
    saved = []
    ctx.settings.save_local_config = saved.append
    choice(render(page, ctx, ui, 'curve'), 'Balanced').handler(ui)
    control = choice(render(page, ctx, ui, 'curve'), 'Save curve + Turn on control from boot')
    assert control.enabled
    control.handler(ui)
    assert saved[-1]['fan_curve']['enabled']
    call = next(item for item in service.calls if item[0] == 'activar_control_fan_sistema')
    assert call[1][0]['mode'] == 'curve' and len(call[1][0]['points']) == 5
    assert 'points' not in ctx.state('fans')


def test_rejected_curve_service_keeps_staged_curve_for_retry():
    service, ui = FakeService(), FakeUI()
    service.estado_control_fan_sistema = lambda: {'enabled': False, 'available': True, 'state': 'off'}
    service.activar_control_fan_sistema = lambda *_: (_ for _ in ()).throw(RuntimeError('denied'))
    ctx = make_context(service)
    page = build_pages()['fans']
    choice(render(page, ctx, ui, 'curve'), 'Balanced').handler(ui)
    choice(render(page, ctx, ui, 'curve'), 'Save curve + Turn on control from boot').handler(ui)
    assert ctx.state('fans')['points'] and any('denied' in note for note, _tone in ui.notes)


def test_disabling_the_curve_clears_the_services_old_policy():
    service, ui = FakeService(), FakeUI()
    service.estado_control_fan_sistema = lambda: {'enabled': True, 'available': True,
                                                'state': 'active', 'policy': {'mode': 'curve'}}
    ctx = make_context(service)
    ctx.settings.read_local_config = lambda: {'fan_curve': {'enabled': True, 'pwm': 2, 'points': [
        {'temperature': 40, 'speed': 50}, {'temperature': 60, 'speed': 75}, {'temperature': 74, 'speed': 100}]}}
    page = build_pages()['fans']
    choice(render(page, ctx, ui, 'curve'), '[x] Automatic curve').handler(ui)
    choice(render(page, ctx, ui, 'curve'), 'Save curve').handler(ui)
    assert ('sincronizar_control_fan_sistema', (None,), {}) in service.calls
