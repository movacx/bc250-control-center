"""Keep the real exception behind an error window.

Background work reports a failure to the interface as text (``str(error)``),
so by the time a red window opens the exception, its type and the line that
raised it are gone. Every worker hands the exception here first; the window
then finds it again by its message and shows it raw, with the function that
raised it (``error_origins``).
"""

from __future__ import annotations

import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

from bc250cc.shared.error_origins import Origin, format_raw, raise_site

#: Enough for the failures of one burst of work; older ones are not asked for.
KEEP = 32
#: A message this short matches too much to be told apart.
MIN_MATCH = 6


@dataclass(frozen=True)
class RawError:
    kind: str
    message: str
    text: str
    site: Origin | None
    at: float


_lock = threading.Lock()
_recent: deque[RawError] = deque(maxlen=KEEP)


def capture(error: BaseException) -> RawError:
    return RawError(
        kind=type(error).__name__,
        message=str(error).strip(),
        text=format_raw(error),
        site=raise_site(error),
        at=time.time(),
    )


def remember(error: BaseException) -> None:
    """Called by a worker in its ``except`` block. Never raises."""
    try:
        raw = capture(error)
    except Exception:  # noqa: BLE001 - keeping evidence must not break the failure path
        return
    with _lock:
        _recent.append(raw)


def find(message: object) -> RawError | None:
    """The exception a window is about: the one being handled right now, or
    the newest remembered one whose message the window's text contains."""
    text = str(message or "")
    active = sys.exc_info()[1]
    # The exception being handled only when the window is about it: a window
    # opened inside an unrelated ``except`` must not borrow its traceback.
    if active is not None and len(str(active).strip()) >= MIN_MATCH and str(active).strip() in text:
        return capture(active)
    with _lock:
        recent = list(_recent)
    for raw in reversed(recent):
        if len(raw.message) >= MIN_MATCH and raw.message in text:
            return raw
    return None


def clear() -> None:
    with _lock:
        _recent.clear()
