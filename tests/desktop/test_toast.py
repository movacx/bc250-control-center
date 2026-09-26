"""The outcome of a click is a toast in the window's corner, not a window."""

from __future__ import annotations

from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from frontends.desktop.components import toast as toast_module
from frontends.desktop.components.toast import (
    MAX_DURATION_MS,
    MAX_TOASTS,
    MIN_DURATION_MS,
    ToastHost,
    show_toast,
    toast_duration,
)


def _window(qtbot):
    window = QWidget()
    layout = QVBoxLayout(window)
    button = QPushButton("Apply", window)
    layout.addWidget(button)
    window.resize(900, 600)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window, button


def test_a_toast_sits_in_the_corner_of_the_anchor_window(qtbot):
    window, button = _window(qtbot)

    toast = show_toast(button, "Fan speed applied", "PWM 2 · 60%", tone="blue")

    host = window.findChild(ToastHost)
    assert toast is not None and host is not None and host.isVisible()
    assert toast.title.text() == "Fan speed applied"
    assert toast.message.text() == "PWM 2 · 60%"
    # Bottom-right corner, inside the window, and never the focus owner.
    assert host.geometry().right() <= window.width() and host.geometry().bottom() <= window.height()
    assert host.geometry().left() > window.width() // 2
    assert not toast.hasFocus() and button.window().focusWidget() is not toast


def test_the_same_outcome_twice_keeps_one_toast_and_the_stack_is_bounded(qtbot):
    window, button = _window(qtbot)
    first = show_toast(button, "Profiles exported", tone="green")
    again = show_toast(button, "Profiles exported", tone="green")
    assert again is first

    for index in range(MAX_TOASTS + 2):
        show_toast(button, f"Outcome {index}")
    host = window.findChild(ToastHost)
    assert len(host.toasts()) == MAX_TOASTS


def test_dismissing_the_last_toast_hides_the_stack(qtbot):
    window, button = _window(qtbot)
    toast = show_toast(button, "Page cache released", tone="green")
    host = window.findChild(ToastHost)

    toast.close_button.click()
    qtbot.waitUntil(lambda: not host.toasts(), timeout=2000)
    assert not host.isVisible()


def test_reading_time_grows_with_the_text_within_bounds():
    assert toast_duration("Saved", "") == MIN_DURATION_MS
    assert toast_duration("x" * 50, "y" * 60) > MIN_DURATION_MS
    assert toast_duration("x" * 400, "y" * 400) == MAX_DURATION_MS


def test_no_window_means_no_toast(monkeypatch):
    monkeypatch.setattr(toast_module.QApplication, "activeWindow", staticmethod(lambda: None))
    assert show_toast(None, "Nothing to anchor") is None
