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
    from PyQt6.QtWidgets import QWidget

    from frontends.desktop.components.async_tools import BackgroundExecutor, _alive

    owner = QWidget()
    qtbot.addWidget(owner)
    executor = BackgroundExecutor(owner)

    captured = {}
    original = executor.start

    def capture(key, operation, on_success=None, on_error=None, on_finished=None):
        started = original(key, operation, on_success, on_error, on_finished)
        captured["signals"] = executor._running[key].signals
        return started

    executor.start = capture
    executor.start("probe", lambda: None)
    signals = captured["signals"]

    owner.deleteLater()
    del owner
    qtbot.waitUntil(lambda: not _alive(executor), timeout=4000)

    # The task finishes late and emits into the deleted executor. Before the
    # guard this raised; now it is simply ignored.
    signals.finished.emit()


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
