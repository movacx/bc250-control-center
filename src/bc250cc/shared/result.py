"""Typed success/failure result used by all future frontend adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from .errors import ErrorDetail

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    value: T | None = None
    error: ErrorDetail | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.error is None):
            raise ValueError("Result must contain exactly one of value or error")

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def failure(cls, error: ErrorDetail) -> "Result[T]":
        return cls(error=error)
