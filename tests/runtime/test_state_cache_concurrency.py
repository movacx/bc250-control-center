import threading

import pytest

from frontends.desktop.core.state import ControllerStateCache


def test_invalidation_prevents_late_loader_from_repopulating_stale_state():
    cache = ControllerStateCache(object())
    entered = threading.Event()
    release = threading.Event()
    results = []

    def old_loader():
        entered.set()
        assert release.wait(1)
        return {"active_cus": 40}

    worker = threading.Thread(
        target=lambda: results.append(cache.get("cu_cache", old_loader, 10)),
        daemon=True,
    )
    worker.start()
    assert entered.wait(1)
    cache.invalidate("cu_cache")
    fresh = cache.get("cu_cache", lambda: {"active_cus": 36}, 10)
    release.set()
    worker.join(1)

    assert fresh == {"active_cus": 36}
    assert results == [{"active_cus": 40}]
    assert cache.get("cu_cache", lambda: {"active_cus": 24}, 10) == {"active_cus": 36}


def test_concurrent_reader_timeout_is_bounded_when_no_stale_value_exists():
    cache = ControllerStateCache(object())
    entered = threading.Event()
    release = threading.Event()

    def loader():
        entered.set()
        assert release.wait(1)
        return "done"

    worker = threading.Thread(
        target=lambda: cache.get("slow", loader, 10),
        daemon=True,
    )
    worker.start()
    assert entered.wait(1)
    with pytest.raises(TimeoutError, match="still loading"):
        cache.get("slow", lambda: "must not run", 10, coalesce_timeout=0.01)
    release.set()
    worker.join(1)


def test_concurrent_timeout_returns_expired_stale_value_instead_of_blocking():
    cache = ControllerStateCache(object())
    cache.get("metrics", lambda: {"sample": 1}, 0.01)
    cache._entries["metrics"].expires_at = 0
    entered = threading.Event()
    release = threading.Event()

    def refresh():
        entered.set()
        assert release.wait(1)
        return {"sample": 2}

    worker = threading.Thread(
        target=lambda: cache.get("metrics", refresh, 10),
        daemon=True,
    )
    worker.start()
    assert entered.wait(1)

    assert cache.get(
        "metrics", lambda: {"sample": 99}, 10, coalesce_timeout=0.01
    ) == {"sample": 1}
    release.set()
    worker.join(1)
