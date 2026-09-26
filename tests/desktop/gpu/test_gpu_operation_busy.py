"""A GPU operation in flight shows a small progress ring, and only then.

Adjusting a second setting while the first was still being applied opened a
dialog asking to wait, with nothing on screen saying that anything was
running or when it would be done. The configuration card now carries a ring
in its status pill's place while an operation is pending, and the "wait"
dialog spins and closes by itself the moment that operation ends.
"""

from __future__ import annotations

import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from frontends.desktop.components.busy_spinner import BusyBadge, BusySpinner
from frontends.desktop.components.page_widgets import SectionCard
from frontends.desktop.components.widgets import InfoDialog
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def test_the_ring_only_turns_while_it_is_running_and_on_screen(qtbot):
    spinner = BusySpinner(16)
    qtbot.addWidget(spinner)
    assert spinner.isHidden() and not spinner._timer.isActive()

    spinner.start()
    assert not spinner.isHidden() and spinner._timer.isActive()
    angle = spinner._angle
    qtbot.waitUntil(lambda: spinner._angle != angle, timeout=1000)

    spinner.stop()
    assert spinner.isHidden() and not spinner._timer.isActive()


def test_a_card_swaps_its_status_pill_for_the_ring_while_work_runs(qtbot):
    card = SectionCard("GPU configuration", status=("Safe mode", "green"))
    qtbot.addWidget(card)
    card.resize(900, 200)
    card.show()

    card.set_busy(True, "GPU operation in progress")
    badge = card.findChild(BusyBadge)
    assert badge is not None and badge.isVisible()
    assert badge.spinner.running
    assert not card.status.isVisible()
    assert badge.label.text() == "GPU operation in progress"

    card.set_busy(False)
    assert badge.isHidden()
    assert not badge.spinner.running
    assert card.status.isVisible()


def test_a_card_that_was_never_busy_builds_no_ring(qtbot):
    card = SectionCard("Plain", status=("Ready", "green"))
    qtbot.addWidget(card)
    card.set_busy(False)
    assert card.findChild(BusyBadge) is None


def _page(qtbot) -> GpuGovernorPage:
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.timer.stop()
    return page


def test_the_gpu_page_shows_the_ring_for_exactly_as_long_as_the_operation(qtbot):
    page = _page(qtbot)
    view = page._redesigned_gpu_view
    release = threading.Event()
    states = []
    page.operation_busy_changed.connect(states.append)

    def operation():
        release.wait(5)
        return {}

    started = page._run_backend_action(operation, lambda _result: None, "Title", refresh=False)
    assert started
    badge = view._configuration.findChild(BusyBadge)
    assert badge is not None and not badge.isHidden()
    assert states == [True]

    release.set()
    qtbot.waitUntil(lambda: not page._action_gate.busy, timeout=5000)
    assert badge.isHidden()
    assert states == [True, False]


def test_the_wait_dialog_spins_and_closes_itself_when_the_operation_ends(qtbot, monkeypatch):
    page = _page(qtbot)
    release = threading.Event()
    page._run_backend_action(lambda: release.wait(5) or {}, lambda _r: None, "Title", refresh=False)
    assert page._action_gate.busy

    shown = []
    original_exec = InfoDialog.exec

    def exec_and_watch(dialog):
        shown.append(dialog)
        assert dialog.spinner is not None and dialog.spinner.running
        # The running operation finishes while the dialog is up.
        QTimer.singleShot(50, release.set)
        return original_exec(dialog)

    monkeypatch.setattr(InfoDialog, "exec", exec_and_watch)
    # A second request while the first is still running.
    refused = page._run_backend_action(lambda: {}, lambda _r: None, "Title", refresh=False)

    assert refused is False
    assert len(shown) == 1
    # exec() returned by itself: the dialog closed when the gate freed.
    assert not page._action_gate.busy
    QApplication.processEvents()
