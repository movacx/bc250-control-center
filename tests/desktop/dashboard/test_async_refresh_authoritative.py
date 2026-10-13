from PyQt6.QtCore import QObject

from frontends.desktop.components.async_tools import AsyncRefresh


def test_authoritative_result_replaces_replay_cache_without_rerender(qtbot):
    owner = QObject()
    rendered = []
    refresh = AsyncRefresh(owner, "test", lambda: {"cus": 40}, rendered.append)
    refresh.set_active(True)
    refresh._result_ready({"cus": 40}, 0)
    assert rendered == [{"cus": 40}]

    rendered.append({"cus": 36})
    refresh.adopt_authoritative({"cus": 36}, already_rendered=True)
    refresh.set_active(False)
    refresh.set_active(True)

    assert refresh.replay_latest() is False
    assert rendered == [{"cus": 40}, {"cus": 36}]


def test_inflight_result_before_authoritative_write_is_ignored(qtbot):
    owner = QObject()
    rendered = []
    refresh = AsyncRefresh(owner, "test", lambda: {}, rendered.append)
    refresh.set_active(True)
    old_generation = refresh._source_generation

    refresh.adopt_authoritative({"cus": 36})
    refresh._result_ready({"cus": 40}, old_generation)

    assert rendered == [{"cus": 36}]
    assert refresh._latest == {"cus": 36}


# ------------------------------------- a task that outlives what started it


def test_a_finished_task_does_not_touch_a_destroyed_executor(qtbot):
    """A background task keeps running after its page is gone.

    ``BackgroundExecutor`` is a QObject parented to a widget, and its
    ``finished`` handler is a plain closure — not a bound method Qt can
    auto-disconnect when the receiver dies. So a read still in flight when the
    page closes reached an executor Qt had already deleted, and the
    ``RuntimeError`` surfaced from inside the event loop, reported against
    whichever unrelated test happened to be running.
    """
    import threading

    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.components.async_tools import BackgroundExecutor, _alive

    owner = QWidget()
    qtbot.addWidget(owner)
    executor = BackgroundExecutor(owner)
    gate = threading.Event()
    executor.start("probe", lambda: gate.wait(5))
    signals = executor._running["probe"].signals

    owner.deleteLater()
    del owner
    qtbot.waitUntil(lambda: not _alive(executor), timeout=4000)

    # The task finishes late, into the deleted executor. Before the guard this
    # raised; now it is ignored, and its signals are released afterwards.
    gate.set()
    qtbot.waitUntil(lambda: not _alive(signals), timeout=4000)


def test_a_finished_task_releases_its_signals_only_after_delivering_them(qtbot):
    """The slot of ``finished`` drops the last reference to its task.

    Python then destroyed the task's signals object while Qt was still
    delivering that very signal from it, and the test run crashed now and then
    on CI (Python 3.11). The object is handed to Qt and deleted later instead.
    """
    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.components.async_tools import (
        AsyncRefresh,
        BackgroundExecutor,
        _alive,
    )

    owner = QWidget()
    qtbot.addWidget(owner)
    executor = BackgroundExecutor(owner)
    done = []
    executor.start("probe", lambda: 1, on_success=done.append, on_finished=lambda: done.append("finished"))
    signals = executor._running["probe"].signals
    qtbot.waitUntil(lambda: done == [1, "finished"], timeout=4000)
    assert not executor.is_running()
    qtbot.waitUntil(lambda: not _alive(signals), timeout=4000)

    results = []
    refresh = AsyncRefresh(owner, "probe", lambda: 2, results.append)
    refresh.set_active(True)
    refresh.request()
    refresh_signals = refresh._task.signals
    qtbot.waitUntil(lambda: results == [2] and not refresh.running, timeout=4000)
    assert refresh._task is None
    qtbot.waitUntil(lambda: not _alive(refresh_signals), timeout=4000)


def test_liveness_is_answered_for_the_awkward_inputs(qtbot):
    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.components.async_tools import _alive

    assert _alive(None) is False
    widget = QWidget()
    qtbot.addWidget(widget)
    assert _alive(widget) is True


def test_the_refresher_ignores_a_result_that_arrives_too_late(qtbot):
    """Its success handler is a lambda, so Qt cannot disconnect it either."""
    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.components.async_tools import AsyncRefresh, _alive

    owner = QWidget()
    qtbot.addWidget(owner)
    applied: list[object] = []
    refresher = AsyncRefresh(owner, "probe", lambda: "value", applied.append)

    owner.deleteLater()
    del owner
    qtbot.waitUntil(lambda: not _alive(refresher), timeout=4000)

    refresher._result_ready("late", None)
    assert applied == [], "a result was rendered into a destroyed page"
