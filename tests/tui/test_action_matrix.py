"""Explore action menus across distro families, with all system writes replaced."""
from copy import deepcopy

import pytest

from frontends.tui.i18n import set_language
from frontends.tui.pages import build_pages

from .fakes import CU_STATE, GPU_STATE, make_context
from .test_no_action_leaves_the_console import Console, Watched, nothing_real  # noqa: F401
from .test_pages import render


class MenuExplorer(Console):
    def __init__(self, path=()):
        super().__init__()
        self.path, self.branch, self.alternatives = path, [], []

    def choose(self, title, options):
        if not options:
            return None
        depth = len(self.branch)
        index = self.path[depth] if depth < len(self.path) else 0
        index = min(index, len(options) - 1)
        self.alternatives.extend(tuple([*self.branch, item]) for item in range(len(options)) if item != index)
        self.branch.append(index)
        return options[index][0]


def context(family, extended):
    service = Watched()
    service.estado_bc250 = lambda: dict(deepcopy(GPU_STATE),
        governor_backend='oberon-governor' if extended else GPU_STATE['governor_backend'],
        safe_points=[{'frequency': 500, 'voltage': 700}, {'frequency': 2000, 'voltage': 960},
                     {'frequency': 2400, 'voltage': 1150}],
        safe_points_with_voltage=[{'frequency': 500, 'voltage': 700}, {'frequency': 2000, 'voltage': 960},
                                  {'frequency': 2400, 'voltage': 1150}],
        high_frequency_points={'available': True, 'enabled_frequencies': [2400] if extended else []})
    service.obtener_estado_cu_cache = lambda: dict(deepcopy(CU_STATE), privileged_backend_ready=True, service_installed=extended)
    service.estado_cpu_oc_persistente = lambda: {'enabled': 'enabled' if extended else 'disabled'}
    ctx = make_context(service)
    ctx.state('system')['os'] = family, family
    ctx.state('cpu')['target'] = {'profile': 0, 'manual': extended, 'scale': -34, 'force_mask': extended}
    ctx.state('gpu')['level'] = -1 if extended else 1
    ctx.state('cu')['masks'] = [30, 31, 31, 31]
    ctx.state('remote')['visible_until'] = float('inf')
    return ctx


@pytest.mark.parametrize('family', ['arch', 'cachyos', 'manjaro', 'bazzite', 'steamos', 'ubuntu', 'debian', 'alpine', 'gentoo'])
@pytest.mark.parametrize('extended', [False, True])
def test_every_enabled_action_and_menu_branch_stays_inside_its_terminal_job(family, extended, record_property):
    Watched.outside = []
    pages = build_pages()
    attempted = 0
    for key, page in pages.items():
        ctx = context(family, extended)
        for tab, _title in page.tabs(ctx) or [('', '')]:
            baseline = render(page, ctx, MenuExplorer(), tab)
            for index, action in enumerate(baseline.choices):
                if not action.enabled or action.handler is None or action.pad:
                    continue
                queue, seen = [()], set()
                while queue:
                    path = queue.pop()
                    if path in seen:
                        continue
                    seen.add(path)
                    ui = MenuExplorer(path)
                    fresh = context(family, extended)
                    current = render(page, fresh, ui, tab).choices[index]
                    try:
                        current.handler(ui)
                    finally:
                        set_language('en')
                    queue.extend(p for p in ui.alternatives if p not in seen and len(p) <= 4)
                    attempted += 1
    record_property('executed_action_paths', attempted)
    assert attempted >= 100, (family, extended, attempted)
    assert not Watched.outside, sorted(set(Watched.outside))
