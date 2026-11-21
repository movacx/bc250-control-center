"""Settings › Appearance › Interface style: the GPU screen in either layout.

Modern is the current screen; Original is the one from before the
2026-11-14 redesign, offered for people who preferred it. Both drive the
same page, so switching never touches the backend.
"""

from __future__ import annotations

import pytest

from frontends.desktop.core.preferences import application_settings
from frontends.desktop.pages import gpu_governor_integration as integration
from frontends.desktop.pages.gpu_governor import GpuGovernorPage
from frontends.desktop.pages.gpu_governor_view import GpuGovernorView, GpuViewState
from frontends.desktop.pages.gpu_governor_view_classic import (
    GpuGovernorView as ClassicGpuGovernorView,
)


@pytest.fixture
def style():
    settings = application_settings()
    yield lambda value: settings.setValue(integration.GPU_INTERFACE_KEY, value)
    settings.remove(integration.GPU_INTERFACE_KEY)


def _page(qtbot) -> GpuGovernorPage:
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    return page


def test_modern_is_the_default(qtbot, style):
    style("")
    assert integration.gpu_interface() == "modern"
    assert type(_page(qtbot)._redesigned_gpu_view) is GpuGovernorView


def test_original_brings_back_the_old_layout(qtbot, style):
    style("original")
    page = _page(qtbot)
    assert type(page._redesigned_gpu_view) is ClassicGpuGovernorView


def test_switching_swaps_the_view_and_keeps_following_the_backend(qtbot, style):
    style("modern")
    page = _page(qtbot)
    old = page._redesigned_gpu_view
    view = integration.switch_gpu_interface(page, "original")
    assert type(view) is ClassicGpuGovernorView and page._redesigned_gpu_view is view
    assert view.parent() is not None and old.parent() is None
    # The refresh wrapper follows the new view, wrapped once only.
    seen = []
    view.apply_state = lambda state: seen.append(state)
    page._apply_state({"governor_backend": "cyan"}, {})
    assert len(seen) == 1 and isinstance(seen[0], GpuViewState)
    assert integration.switch_gpu_interface(page, "original") is view


def test_both_layouts_offer_the_same_controls():
    signals = {name for name in dir(GpuGovernorView) if name.endswith("_requested") or name == "profile_changed"}
    assert signals and signals <= set(dir(ClassicGpuGovernorView))


def test_the_classic_layout_renders_a_state(qtbot):
    view = ClassicGpuGovernorView()
    qtbot.addWidget(view)
    view.resize(1440, 900)
    view.apply_state(GpuViewState())
    view.set_oberon_mode(True)
    view.set_oberon_mode(False)
