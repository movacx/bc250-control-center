"""The tool inventory as the CPU, GPU and compute unit operations need it."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

#: While set, the inventory leaves out what only Additional settings shows: the
#: HelixSR bridge alone takes about a second, and no hardware operation reads it.
HARDWARE_ONLY: ContextVar[bool] = ContextVar("bc250_hardware_only", default=False)


@contextmanager
def hardware_only():
    token = HARDWARE_ONLY.set(True)
    try:
        yield
    finally:
        HARDWARE_ONLY.reset(token)


def hardware_tools(repository) -> dict:
    with hardware_only():
        return repository.estado_herramientas_bc250()
