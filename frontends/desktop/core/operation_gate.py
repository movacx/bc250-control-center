"""Small generation gate for one in-flight UI mutation."""

from __future__ import annotations


class OperationGate:
    def __init__(self) -> None:
        self._generation = 0
        self._active: int | None = None

    @property
    def busy(self) -> bool:
        return self._active is not None

    def begin(self) -> int | None:
        if self._active is not None:
            return None
        self._generation += 1
        self._active = self._generation
        return self._active

    def is_current(self, token: int) -> bool:
        return self._active == token

    def finish(self, token: int) -> bool:
        if self._active != token:
            return False
        self._active = None
        return True
