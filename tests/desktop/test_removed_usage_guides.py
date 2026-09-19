"""The usage guides are gone; the actions they carried are not.

Each hardware page had a collapsible "Usage guide" card. On two of the three
pages its only toggle was hidden at construction, with a comment saying the
card was kept "in case this guide is reintroduced later" — so the card was
dead weight. Worse, it was not empty: the Compute Units guide held the only
"Install UMR" button on the page, which made a real action unreachable behind
a hidden toggle, and the CPU guide held "Prepare CPU tools".

Removing a container is only safe if what it contained found a home. That is
what this file checks, because a button that exists but is in no layout looks
exactly like a button that works.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QWidget

from frontends.desktop.pages.compute_units import ComputeUnitsPage
from frontends.desktop.pages.cpu_smu import CpuSmuPage
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _in_a_layout(widget: QWidget) -> bool:
    """True when some layout in the window actually places this widget."""
    parent = widget.parentWidget()
    while parent is not None:
        layout = parent.layout()
        if layout is not None and layout.indexOf(widget) >= 0:
            return True
        parent = parent.parentWidget()
    return widget.parentWidget() is not None and widget.isVisibleTo(widget.window())


def test_no_page_still_builds_a_usage_guide(qtbot):
    for factory in (CpuSmuPage, GpuGovernorPage, ComputeUnitsPage):
        page = factory(object())
        qtbot.addWidget(page)
        assert not hasattr(page, "workflow_guide"), factory.__name__
        assert not hasattr(page, "workflow_guide_button"), factory.__name__


def test_the_guide_card_type_is_gone_from_the_component_library():
    from frontends.desktop.components import page_widgets

    assert not hasattr(page_widgets, "WorkflowGuideCard")


def test_compute_units_no_longer_offers_to_install_umr(qtbot):
    """The action moved out of the page rather than to another corner of it.

    It had been unreachable for some time, hidden inside the usage guide, and
    the dependency-preparation workflow on the Dashboard installs ``umr`` as
    one of its components — so the page does not need a second door to it.
    """
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    assert not hasattr(page, "install_umr_button")
    assert not hasattr(page, "install_umr")


def test_umr_is_still_installable_from_the_dependency_workflow():
    """Removing a button must not remove the capability behind it."""
    from pathlib import Path

    script = Path("packaging/common/os-scripts/arch/prepare-dependencies.sh")
    assert "install_umr()" in script.read_text(encoding="utf-8")


def test_the_cpu_page_no_longer_offers_to_prepare_its_tools(qtbot):
    """The action left the page the same way "Install UMR" left its own.

    ``bc250_smu_oc`` is vendored into the package and installed alongside the
    privileged helpers, and the Dashboard's dependency workflow installs the
    one external thing the CPU path needs. The button was a repair door for a
    case the normal install already covers.
    """
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    view = page._unified_cpu_control
    assert not hasattr(view, "prepare_tools_button")


def test_the_vendored_cpu_tool_still_ships_with_the_package():
    """Removing a button must not remove the capability behind it."""
    from pathlib import Path

    assert Path("privileged/lib/bc250_smu_oc_vendor.zip").is_file()
    script = Path("packaging/common/os-scripts/arch/prepare-dependencies.sh")
    assert "install_stress()" in script.read_text(encoding="utf-8")


@pytest.mark.parametrize("factory", (CpuSmuPage, GpuGovernorPage, ComputeUnitsPage))
def test_every_page_still_builds_without_its_guide(qtbot, factory):
    page = factory(object())
    qtbot.addWidget(page)
    page.resize(1280, 800)
    page.show()
    assert page.isVisible()
