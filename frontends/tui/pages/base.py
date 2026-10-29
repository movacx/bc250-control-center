"""The contract between a page and the screen that draws it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from ..content import (
    Block,
    Field,
    Meter,
    Note,
    Trend,
    heat_tone,
    load_tone,
    number,
    percent,
)
from ..i18n import tr
from ..runtime import Context, describe_error, describe_result


class UI(Protocol):
    """What an action may ask of the screen. The screen implements it."""

    unicode: bool

    def confirm(self, message: str, *, danger: bool = False) -> bool: ...
    def ask_int(self, label: str, minimum: int, maximum: int, default: int) -> int | None: ...
    def ask_text(self, label: str, default: str = "") -> str | None: ...
    def choose(self, title: str, options: list[tuple[Any, str]]) -> Any: ...
    def notify(self, message: str, tone: str = "") -> None: ...
    def run(self, label: str, work: Callable[[], Any]) -> tuple[bool, Any]: ...
    def show_text(self, title: str, text: str) -> None: ...
    def refresh(self) -> None: ...
    def apply_theme(self, theme: str) -> None: ...
    def goto(self, page_key: str) -> None: ...


class Page:
    """One sidebar entry.

    ``load`` runs on a worker thread and may block on hardware; ``build`` runs
    on the drawing thread and must only format what ``load`` returned.
    """

    key = ""
    title = ""  # English source text; shown through tr()
    loads = True
    interval = 3.0

    def tabs(self, ctx: Context) -> list[tuple[str, str]]:
        return []

    def load(self, ctx: Context) -> Any:
        return None

    def build(self, ctx: Context, data: Any, tab: str, ui: UI) -> list[Block]:
        raise NotImplementedError


def guarded(ui: UI, label: str, work: Callable[[], Any], *, success: str = "") -> None:
    """Run a mutating service call in the foreground and report its outcome.

    The screen is handed back to the terminal for the call, so a privilege
    prompt (pkexec/sudo) can ask on the tty, and the person sees the output.
    """
    ok, result = ui.run(label, work)
    if isinstance(result, BaseException):
        ui.notify(describe_error(result), "bad")
    elif ok:
        ui.notify(describe_result(result) or success or tr("Done"), "ok")
    ui.refresh()


def metric_blocks(ctx: Context) -> dict[str, dict]:
    metrics = ctx.metrics or {}
    return {name: metrics.get(name) if isinstance(metrics.get(name), dict) else {} for name in
            ("gpu", "cpu", "power", "sensors", "memory", "disk", "network")}


def waiting(ctx: Context, key: str) -> list[Block] | None:
    """The placeholder while a page has neither data nor an error yet."""
    if key in ctx.page_data:
        return None
    if ctx.page_error.get(key):
        return [Note(ctx.page_error[key], "bad")]
    return [Note(tr("Waiting for data…"), "dim")]


def trend(ctx: Context, label: str, name: str, unit: str, tone: str = "accent") -> Trend:
    values = list(ctx.history.get(name, ()))
    return Trend(label, values, number(values[-1], unit) if values else "--", tone)


def temperature_meter(label: str, celsius: object, ceiling: float = 110.0) -> Meter:
    try:
        fraction = max(0.0, min(1.0, float(celsius) / ceiling))
    except (TypeError, ValueError):
        fraction = None
    return Meter(label, fraction, number(celsius, "°C", 1), heat_tone(celsius))


def load_meter(label: str, value: object) -> Meter:
    return Meter(label, percent(value), number(value, "%", 0), load_tone(value))


def field_or_dash(label: str, value: object, unit: str = "", digits: int = 0) -> Field:
    return Field(label, number(value, unit, digits))
