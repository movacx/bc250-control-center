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
