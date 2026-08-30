from __future__ import annotations

__all__ = ["ControlCenterWindow"]


def __getattr__(name: str):
    if name == "ControlCenterWindow":
        from .app import ControlCenterWindow
        return ControlCenterWindow
    raise AttributeError(name)
