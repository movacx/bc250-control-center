"""The window hears about the end of a terminal workflow when it happens.

Installers and removals return as soon as their terminal is open. The
Compatibility cards used to learn the result on a later poll through two
caches, so a button could keep offering "Install" well after the installer
had finished.
"""

import threading
from types import SimpleNamespace

from bc250cc.infrastructure import terminal_repository
from bc250cc.infrastructure.terminal_repository import TerminalLaunchResult
from frontends.desktop.app import ControlCenterWindow
from frontends.desktop.core.workflow_watch import (
    EMBEDDED_TERMINAL_NAME,
    WorkflowCompletionWatcher,
    read_exit_status,
)


def _result(tmp_path, name="run", terminal="konsole"):
    return TerminalLaunchResult(
        terminal=terminal,
        title=name,
        pid=None,
        status_file=str(tmp_path / f"status-{name}.txt"),
        log_file=str(tmp_path / f"workflow-{name}.log"),
    )


def test_a_workflow_launched_on_a_worker_thread_is_reported_when_it_ends(qtbot, tmp_path):
    watch = WorkflowCompletionWatcher()
    watch.install()
    try:
        ended = []
        watch.finished.connect(lambda result, code: ended.append((result.title, code)))
        result = _result(tmp_path, "install")
        worker = threading.Thread(target=terminal_repository._announce_workflow, args=(result,))
        worker.start()
        worker.join()
        qtbot.waitUntil(lambda: watch.pending == 1)
        watch.check_now()
        assert ended == []

        (tmp_path / "status-install.txt").write_text("0\n", encoding="utf-8")
        qtbot.waitUntil(lambda: ended == [("install", 0)], timeout=3000)
        assert watch.pending == 0
    finally:
        watch.uninstall()
    assert watch._observe not in terminal_repository._workflow_observers


def test_a_stopped_console_workflow_counts_as_ended_for_its_own_tab_only(qtbot, tmp_path):
    watch = WorkflowCompletionWatcher()
    ended = []
    watch.finished.connect(lambda result, code: ended.append((result.title, code)))
    first = _result(tmp_path, "first", EMBEDDED_TERMINAL_NAME)
    second = _result(tmp_path, "second", EMBEDDED_TERMINAL_NAME)
    watch._track(first)
    watch._track(second)

    # Stopped before it could write its status file.
    watch.embedded_finished(first.log_file, 130)
    assert ended == [("first", 130)]
    assert watch.pending == 1


def test_exit_status_file_reading(tmp_path):
    status = tmp_path / "status.txt"
    assert read_exit_status(str(status)) is None
    status.write_text("", encoding="utf-8")
    assert read_exit_status(str(status)) is None
    status.write_text("3\n", encoding="utf-8")
    assert read_exit_status(str(status)) == 3
    status.write_text("garbage", encoding="utf-8")
    assert read_exit_status(str(status)) == 1


def test_a_failing_observer_never_costs_the_launch(tmp_path):
    def broken(_result):
        raise RuntimeError("observer bug")

    terminal_repository.add_workflow_observer(broken)
    try:
        result = _result(tmp_path)
        assert terminal_repository._announce_workflow(result) is result
    finally:
        terminal_repository.remove_workflow_observer(broken)


def test_the_end_of_a_workflow_drops_every_cache_and_refreshes_at_once():
    calls = []
    dashboard = SimpleNamespace(refresh_now=lambda: calls.append("dashboard"))
    other_page = SimpleNamespace(refresh=lambda: calls.append("page"))
    window = SimpleNamespace(
        controller=SimpleNamespace(invalidar_estado_herramientas=lambda: calls.append("repository")),
        _state_cache=SimpleNamespace(invalidate=lambda *keys: calls.append(("cache", keys))),
        dashboard=dashboard,
        stack=SimpleNamespace(currentWidget=lambda: other_page),
    )
    ControlCenterWindow._workflow_finished(window, None, 0)
    assert calls == ["repository", ("cache", ()), "dashboard", "page"]
