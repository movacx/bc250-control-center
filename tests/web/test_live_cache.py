"""A reading made before an action is never kept as if it had been made after it."""
import threading
from types import SimpleNamespace

from frontends.web.data import STALE_SECONDS, Live


def live():
    return Live(SimpleNamespace(state=lambda _name: {}, lock=threading.Lock(), metrics={}, metrics_error="", history={}))


def test_a_reading_interrupted_by_an_action_is_answered_but_not_kept():
    one = live()

    def read():
        one.forget()
        return "before"

    assert one._kept("cu", 3, read) == "before"
    assert one._kept("cu", 3, lambda: "after") == "after"


def test_a_slightly_old_reading_is_answered_at_once_and_renewed_behind():
    one = live()
    assert one._kept("cu", 3, lambda: 1) == 1
    stamp, value = one._cache["cu"]
    one._cache["cu"] = (stamp - 4, value)
    renewed = threading.Event()

    def read():
        renewed.set()
        return 2

    assert one._kept("cu", 3, read) == 1
    assert renewed.wait(5)
    with one._locks["cu"]:
        assert one._cache["cu"][1] == 2
    one._cache["cu"] = (stamp - 4 - STALE_SECONDS, 2)
    assert one._kept("cu", 3, lambda: 3) == 3


def test_a_failed_renewal_is_read_again_by_the_next_request():
    one = live()
    one._kept("cu", 3, lambda: 1)
    stamp, value = one._cache["cu"]
    one._cache["cu"] = (stamp - 4, value)

    def broken():
        raise RuntimeError

    assert one._kept("cu", 3, broken) == 1
    with one._locks["cu"]:
        pass
    assert one._kept("cu", 3, lambda: 5) == 5
