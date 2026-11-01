"""Every resource and staged hardware outcome, without changing real hardware."""
from copy import deepcopy

import pytest

from frontends.tui.content import Chart
from frontends.tui.pages import build_pages
from frontends.tui.pages.performance import PerformancePage
from frontends.tui.runtime import Poller

from .fakes import CU_STATE, METRICS, FakeService, FakeUI, make_context
from .test_pages import choice, render


@pytest.mark.parametrize('resource', ['cpu', 'gpu', 'vram', 'memory', 'disk', 'network'])
def test_each_resource_exposes_real_recorded_series_including_disk_and_network(resource):
    sample = deepcopy(METRICS)
    sample['disk'] = {'usage_percent': 50, 'used': 2**30, 'total': 2**31,
                      'read_bps': 4096, 'write_bps': 2048, 'active_percent': 25}
    sample['network'] = {'download_bps': 8192, 'upload_bps': 1024, 'interface': 'eth0'}
    ctx, ui = make_context(), FakeUI()
    page = PerformancePage()
    recorder = page.recorder(ctx)
    recorder.record(sample, [])
    recorder.record(sample, [])
    blocks = page.build(ctx, None, resource, ui)
    chart = next(block for block in blocks if isinstance(block, Chart))
    assert chart.times and chart.series
    assert all(len(values) == len(chart.times) for _name, values, _tone in chart.series)
    if resource == 'disk':
        assert [values[-1] for _name, values, _tone in chart.series] == [4096, 2048]
    if resource == 'network':
        assert [values[-1] for _name, values, _tone in chart.series] == [8192, 1024]


def test_an_unavailable_gpu_does_not_invent_samples_or_crash_other_resources():
    ctx, ui = make_context(), FakeUI()
    page = PerformancePage()
    page.recorder(ctx).record({'disk': {}, 'network': {}, 'cpu': {}, 'gpu': {}}, [])
    for tab, _ in page.tabs(ctx):
        assert page.build(ctx, None, tab, ui)


def test_a_rejected_cpu_operation_does_not_report_it_as_applied():
    service = FakeService()
    service.ejecutar_cpu_oc_temporal = lambda *args: (_ for _ in ()).throw(RuntimeError('denied'))
    ctx, ui = make_context(service), FakeUI()
    page = build_pages()['cpu']
    choice(render(page, ctx, ui), 'Apply configuration + automatic scale').handler(ui)
    assert 'last' not in ctx.state('cpu')
    assert any('denied' in message for message, _tone in ui.notes)


def test_a_rejected_cu_write_preserves_the_users_staged_selection():
    service = FakeService()
    service.obtener_estado_cu_cache = lambda: dict(deepcopy(CU_STATE), privileged_backend_ready=True)
    service.aplicar_tabla_cu = lambda *args: (_ for _ in ()).throw(RuntimeError('denied'))
    ctx, ui = make_context(service), FakeUI()
    ctx.state('cu')['masks'] = [30, 31, 31, 31]
    page = build_pages()['cu']
    choice(render(page, ctx, ui), 'Apply now').handler(ui)
    assert ctx.state('cu')['masks'] == [30, 31, 31, 31]


def test_a_page_load_error_is_reported_and_a_later_refresh_recovers():
    ctx = make_context()
    page = build_pages()['gpu']
    poller = Poller(ctx, {'gpu': page})
    ctx.service.estado_bc250 = lambda: (_ for _ in ()).throw(RuntimeError('transient'))
    poller._load('gpu', page)
    assert 'transient' in ctx.page_error['gpu']
    ctx.service.estado_bc250 = lambda: {'allowed_min': 500, 'allowed_max': 2000}
    poller._load('gpu', page)
    assert 'gpu' not in ctx.page_error and ctx.page_data['gpu']['allowed_min'] == 500


def test_a_rejected_gpu_range_keeps_the_pending_range_for_retry():
    service = FakeService()
    service.aplicar_rango_bc250 = lambda *args: (_ for _ in ()).throw(RuntimeError('denied'))
    ctx, ui = make_context(service), FakeUI()
    ctx.state('gpu').update(min=1000, max=2000)
    page = build_pages()['gpu']
    choice(render(page, ctx, ui), 'Review and apply range').handler(ui)
    assert ctx.state('gpu')['min'] == 1000 and ctx.state('gpu')['max'] == 2000
