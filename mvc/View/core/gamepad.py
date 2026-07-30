from __future__ import annotations

"""Optional Linux gamepad input and Qt focus navigation.

The input monitor lives in a ``QThread`` and never grabs the device, so Steam
Input plus the existing mouse/keyboard paths continue to work. ``python-evdev``
is preferred for semantic Linux input codes; a dependency-free ``/dev/input/js*``
reader is used when evdev is unavailable or cannot open a suitable device.

The Qt integration is deliberately dormant while no controller is connected.
It installs its event filter only for an active controller, coalesces all deferred
UI work through one owned ``QTimer``, and restores every focus policy it changes
when the controller disconnects. This prevents stale single-shot callbacks from
outliving short-lived Qt widgets such as spin-box editors and dialog children.
"""

from dataclasses import dataclass
from pathlib import Path
import glob
import logging
import os
import select
import struct
import threading
import time
from typing import Callable, Iterable, Protocol
import weakref

from PyQt6.QtCore import QEvent, QEasingCurve, QObject, QPoint, QRect, Qt, QThread, QTimer, pyqtSignal, QPropertyAnimation
from PyQt6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:  # ``sip.isdeleted`` is the authoritative PyQt wrapper-lifetime check.
    from PyQt6 import sip
except ImportError:  # pragma: no cover - PyQt6 always ships sip at runtime.
    sip = None

from ..i18n import tr
from ..theme import COLORS


logger = logging.getLogger(__name__)

ACTION_UP = "up"
ACTION_DOWN = "down"
ACTION_LEFT = "left"
ACTION_RIGHT = "right"
ACTION_ACCEPT = "accept"
ACTION_CANCEL = "cancel"
ACTION_PREVIOUS_SECTION = "previous_section"
ACTION_NEXT_SECTION = "next_section"
ACTION_TOGGLE_SIDEBAR = "toggle_sidebar"
ACTION_OPEN_SETTINGS = "open_settings"
ACTION_GO_DASHBOARD = "go_dashboard"
ACTION_CONTEXT_X = "context_x"
ACTION_CONTEXT_Y = "context_y"
ACTION_SCROLL_UP = "scroll_up"
ACTION_SCROLL_DOWN = "scroll_down"

_REPEATABLE_ACTIONS = {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT, ACTION_SCROLL_UP, ACTION_SCROLL_DOWN}
_AXIS_PRESS_THRESHOLD = 0.56
_AXIS_RELEASE_THRESHOLD = 0.34
_NAVIGATION_POLL_INTERVAL = 0.012
_NAVIGATION_REPEAT_INITIAL_DELAY = 0.36
_NAVIGATION_REPEAT_INTERVAL_START = 0.118
_NAVIGATION_REPEAT_INTERVAL_MIN = 0.088
_NAVIGATION_REPEAT_RAMP = 0.010
_FOCUS_ANIMATION_MS = 82
_DIRECTION_KEYS = {
    ACTION_UP: Qt.Key.Key_Up,
    ACTION_DOWN: Qt.Key.Key_Down,
    ACTION_LEFT: Qt.Key.Key_Left,
    ACTION_RIGHT: Qt.Key.Key_Right,
}
_ICON_DIR = Path(__file__).resolve().parents[1] / "theme" / "icons"


def _qobject_alive(obj: QObject | None) -> bool:
    """Return ``False`` for wrappers whose underlying C++ object is gone."""

    if obj is None:
        return False
    try:
        if sip is not None and sip.isdeleted(obj):
            return False
        # A harmless Qt call also protects installations where sip is hidden.
        obj.objectName()
        return True
    except (RuntimeError, TypeError, AttributeError):
        return False


@dataclass(frozen=True)
class GamepadDevice:
    identifier: str
    name: str
    profile: str = "abxy"


@dataclass(frozen=True)
class GamepadInput:
    action: str
    pressed: bool
    source: str = ""


@dataclass(frozen=True)
class _HeldNavigation:
    next_due: float
    repeat_count: int = 0


def infer_gamepad_profile(name: str) -> str:
    """Return the visual button family without changing semantic controls."""

    lowered = str(name or "").casefold()
    if any(token in lowered for token in ("playstation", "dualsense", "dualshock", "sony interactive")):
        return "playstation"
    return "abxy"


class GamepadBackend(Protocol):
    def refresh(self) -> GamepadDevice | None: ...

    def poll(self, timeout: float) -> list[GamepadInput]: ...

    def close(self) -> None: ...


class _AxisStateMixin:
    def __init__(self) -> None:
        self._axis_actions: dict[str, str | None] = {}

    def _axis_transition(self, axis: str, value: float, negative: str, positive: str) -> list[GamepadInput]:
        previous = self._axis_actions.get(axis)
        if value <= -_AXIS_PRESS_THRESHOLD:
            current: str | None = negative
        elif value >= _AXIS_PRESS_THRESHOLD:
            current = positive
        elif previous == negative and value <= -_AXIS_RELEASE_THRESHOLD:
            current = negative
        elif previous == positive and value >= _AXIS_RELEASE_THRESHOLD:
            current = positive
        else:
            current = None
        if previous == current:
            return []
        result: list[GamepadInput] = []
        if previous is not None:
            result.append(GamepadInput(previous, False, axis))
        if current is not None:
            result.append(GamepadInput(current, True, axis))
        self._axis_actions[axis] = current
        return result

    def _release_axes(self) -> list[GamepadInput]:
        result = [GamepadInput(action, False, axis) for axis, action in self._axis_actions.items() if action]
        self._axis_actions.clear()
        return result


class EvdevGamepadBackend(_AxisStateMixin):
    """Semantic Linux input backend used when python-evdev is available.

    Exactly one deterministic primary controller is opened. Additional devices
    remain untouched, preventing duplicate actions when the same physical pad is
    exposed through multiple Linux input nodes. If the primary disappears, the
    next suitable device is selected on the following scan.
    """

    def __init__(self, evdev_module=None) -> None:
        super().__init__()
        if evdev_module is None:
            try:
                import evdev as evdev_module  # type: ignore
            except ImportError:
                evdev_module = None
        self._evdev = evdev_module
        self._device = None
        self._device_info: GamepadDevice | None = None
        self._last_scan = 0.0

    @property
    def available(self) -> bool:
        return self._evdev is not None

    @staticmethod
    def _looks_like_gamepad(keys: set[int], axes: set[int], ecodes) -> bool:
        """Reject keyboards/mice and ambiguous HIDs with conservative checks."""

        face_buttons = {
            ecodes.BTN_SOUTH,
            ecodes.BTN_EAST,
            ecodes.BTN_NORTH,
            ecodes.BTN_WEST,
        }
        has_face_pair = len(keys & face_buttons) >= 2
        has_left_stick = {ecodes.ABS_X, ecodes.ABS_Y}.issubset(axes)
        has_dpad = {ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y}.issubset(axes)
        dpad_key_codes = {
            getattr(ecodes, "BTN_DPAD_UP", -10),
            getattr(ecodes, "BTN_DPAD_DOWN", -11),
            getattr(ecodes, "BTN_DPAD_LEFT", -12),
            getattr(ecodes, "BTN_DPAD_RIGHT", -13),
        }
        has_dpad_keys = len(keys & dpad_key_codes) >= 2
        return has_face_pair and (has_left_stick or has_dpad or has_dpad_keys)

    def refresh(self) -> GamepadDevice | None:
        if self._evdev is None:
            return None
        if self._device is not None:
            try:
                os.fstat(self._device.fd)
                return self._device_info
            except (OSError, AttributeError):
                self.close()
        now = time.monotonic()
        if now - self._last_scan < 0.8:
            return None
        self._last_scan = now
        ecodes = self._evdev.ecodes
        try:
            paths = sorted(self._evdev.list_devices())
        except Exception:
            logger.debug("Unable to enumerate Linux input devices", exc_info=True)
            return None
        for path in paths:
            device = None
            try:
                device = self._evdev.InputDevice(path)
                capabilities = device.capabilities(absinfo=False)
                keys = set(capabilities.get(ecodes.EV_KEY, ()))
                axes = set(capabilities.get(ecodes.EV_ABS, ()))
                if not self._looks_like_gamepad(keys, axes, ecodes):
                    device.close()
                    continue
                self._device = device
                name = device.name or "Linux gamepad"
                self._device_info = GamepadDevice(path, name, infer_gamepad_profile(name))
                return self._device_info
            except (OSError, PermissionError):
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        logger.debug("Unable to close rejected evdev device %s", path, exc_info=True)
                continue
            except Exception:
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        logger.debug("Unable to close invalid evdev device %s", path, exc_info=True)
                logger.debug("Unable to inspect Linux input device %s", path, exc_info=True)
        return None

    def poll(self, timeout: float) -> list[GamepadInput]:
        if self._device is None or self._evdev is None:
            time.sleep(max(0.0, timeout))
            return []
        try:
            ready, _write, _error = select.select([self._device.fd], [], [], max(0.0, timeout))
            if not ready:
                return []
            result: list[GamepadInput] = []
            for event in self._device.read():
                result.extend(self._map_event(event))
            return result
        except (OSError, BlockingIOError):
            released = self._release_axes()
            self.close()
            return released
        except Exception:
            logger.debug("Gamepad event polling failed", exc_info=True)
            return []

    def _map_event(self, event) -> list[GamepadInput]:
        ecodes = self._evdev.ecodes
        if event.type == ecodes.EV_KEY:
            action = {
                ecodes.BTN_SOUTH: ACTION_ACCEPT,
                ecodes.BTN_EAST: ACTION_CANCEL,
                # Linux keeps the historical BTN_X/BTN_Y aliases: Xbox X is
                # BTN_NORTH (307) and Xbox Y is BTN_WEST (308). Mapping the
                # geometric names literally swaps the two physical buttons.
                ecodes.BTN_NORTH: ACTION_CONTEXT_X,
                ecodes.BTN_WEST: ACTION_CONTEXT_Y,
                getattr(ecodes, "BTN_THUMBR", -18): ACTION_CONTEXT_X,
                ecodes.BTN_TL: ACTION_PREVIOUS_SECTION,
                ecodes.BTN_TR: ACTION_NEXT_SECTION,
                getattr(ecodes, "BTN_SELECT", -19): ACTION_OPEN_SETTINGS,
                getattr(ecodes, "BTN_START", -20): ACTION_TOGGLE_SIDEBAR,
                getattr(ecodes, "BTN_MODE", -25): ACTION_GO_DASHBOARD,
                getattr(ecodes, "BTN_DPAD_UP", -21): ACTION_UP,
                getattr(ecodes, "BTN_DPAD_DOWN", -22): ACTION_DOWN,
                getattr(ecodes, "BTN_DPAD_LEFT", -23): ACTION_LEFT,
                getattr(ecodes, "BTN_DPAD_RIGHT", -24): ACTION_RIGHT,
            }.get(event.code)
            if action is None or event.value == 2:
                return []
            return [GamepadInput(action, bool(event.value), f"ev_key:{event.code}")]
        if event.type != ecodes.EV_ABS:
            return []
        if event.code in (ecodes.ABS_X, ecodes.ABS_Y):
            try:
                info = self._device.absinfo(event.code)
                center = (info.minimum + info.maximum) / 2.0
                half_range = max(1.0, (info.maximum - info.minimum) / 2.0)
                normalized = (event.value - center) / half_range
            except Exception:
                normalized = float(event.value) / 32767.0
            if event.code == ecodes.ABS_X:
                return self._axis_transition("left_x", normalized, ACTION_LEFT, ACTION_RIGHT)
            return self._axis_transition("left_y", normalized, ACTION_UP, ACTION_DOWN)
        if event.code == getattr(ecodes, "ABS_RY", -200):
            try:
                info = self._device.absinfo(event.code)
                center = (info.minimum + info.maximum) / 2.0
                half_range = max(1.0, (info.maximum - info.minimum) / 2.0)
                normalized = (event.value - center) / half_range
            except Exception:
                normalized = float(event.value) / 32767.0
            return self._axis_transition("right_y", normalized, ACTION_SCROLL_UP, ACTION_SCROLL_DOWN)
        if event.code == ecodes.ABS_HAT0X:
            return self._axis_transition("hat_x", float(event.value), ACTION_LEFT, ACTION_RIGHT)
        if event.code == ecodes.ABS_HAT0Y:
            return self._axis_transition("hat_y", float(event.value), ACTION_UP, ACTION_DOWN)
        return []

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                logger.debug("Unable to close evdev gamepad cleanly", exc_info=True)
        self._device = None
        self._device_info = None
        self._axis_actions.clear()


class LinuxJoystickBackend(_AxisStateMixin):
    """Dependency-free fallback for kernel ``/dev/input/js*`` devices."""

    _EVENT = struct.Struct("<IhBB")
    _BUTTON = 0x01
    _AXIS = 0x02
    _INIT = 0x80

    def __init__(self) -> None:
        super().__init__()
        self._fd: int | None = None
        self._path = ""
        self._device_info: GamepadDevice | None = None
        self._last_scan = 0.0

    def refresh(self) -> GamepadDevice | None:
        if self._fd is not None:
            try:
                os.fstat(self._fd)
                return self._device_info
            except OSError:
                logger.debug("Linux joystick descriptor is no longer valid", exc_info=True)
            self.close()
        now = time.monotonic()
        if now - self._last_scan < 0.8:
            return None
        self._last_scan = now
        for path in sorted(glob.glob("/dev/input/js*")):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except (OSError, PermissionError):
                continue
            self._fd = fd
            self._path = path
            name = self._read_name(fd) or Path(path).name
            self._device_info = GamepadDevice(path, name, infer_gamepad_profile(name))
            return self._device_info
        return None

    @staticmethod
    def _read_name(fd: int) -> str:
        try:
            import fcntl

            length = 128
            # JSIOCGNAME(length): _IOR('j', 0x13, char[length])
            request = 0x80006A13 + (length << 16)
            buffer = bytearray(length)
            fcntl.ioctl(fd, request, buffer)
            return bytes(buffer).split(b"\0", 1)[0].decode("utf-8", "replace")
        except Exception:
            return ""

    def poll(self, timeout: float) -> list[GamepadInput]:
        if self._fd is None:
            time.sleep(max(0.0, timeout))
            return []
        try:
            ready, _write, _error = select.select([self._fd], [], [], max(0.0, timeout))
            if not ready:
                return []
            result: list[GamepadInput] = []
            while True:
                try:
                    payload = os.read(self._fd, self._EVENT.size)
                except BlockingIOError:
                    break
                if len(payload) != self._EVENT.size:
                    break
                _timestamp, value, event_type, number = self._EVENT.unpack(payload)
                initialized = bool(event_type & self._INIT)
                event_type &= ~self._INIT
                mapped = self._map_event(event_type, number, value)
                if not initialized:
                    result.extend(mapped)
            return result
        except (OSError, ValueError):
            released = self._release_axes()
            self.close()
            return released

    def _map_event(self, event_type: int, number: int, value: int) -> list[GamepadInput]:
        if event_type == self._BUTTON:
            action = {
                0: ACTION_ACCEPT,
                1: ACTION_CANCEL,
                2: ACTION_CONTEXT_X,
                3: ACTION_CONTEXT_Y,
                4: ACTION_PREVIOUS_SECTION,
                5: ACTION_NEXT_SECTION,
                6: ACTION_OPEN_SETTINGS,
                7: ACTION_TOGGLE_SIDEBAR,
                8: ACTION_GO_DASHBOARD,
                10: ACTION_CONTEXT_X,
                16: ACTION_GO_DASHBOARD,
            }.get(number)
            return [GamepadInput(action, bool(value), f"js_button:{number}")] if action else []
        if event_type != self._AXIS:
            return []
        normalized = max(-1.0, min(1.0, float(value) / 32767.0))
        if number == 0:
            return self._axis_transition("left_x", normalized, ACTION_LEFT, ACTION_RIGHT)
        if number == 1:
            return self._axis_transition("left_y", normalized, ACTION_UP, ACTION_DOWN)
        if number == 4:
            return self._axis_transition("right_y", normalized, ACTION_SCROLL_UP, ACTION_SCROLL_DOWN)
        if number == 6:
            return self._axis_transition("hat_x", normalized, ACTION_LEFT, ACTION_RIGHT)
        if number == 7:
            return self._axis_transition("hat_y", normalized, ACTION_UP, ACTION_DOWN)
        return []

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                logger.debug("Unable to close Linux joystick descriptor cleanly", exc_info=True)
        self._fd = None
        self._path = ""
        self._device_info = None
        self._axis_actions.clear()


class AutoGamepadBackend:
    """Prefer evdev and transparently fall back to the joystick API."""

    def __init__(self) -> None:
        evdev_backend = EvdevGamepadBackend()
        self._backends: list[GamepadBackend] = []
        if evdev_backend.available:
            self._backends.append(evdev_backend)
        self._backends.append(LinuxJoystickBackend())
        self._active: GamepadBackend | None = None

    def refresh(self) -> GamepadDevice | None:
        if self._active is not None:
            device = self._active.refresh()
            if device is not None:
                return device
            # Publish one clean disconnected scan before selecting another
            # backend. This avoids a stale js node immediately replacing the
            # same evdev device during rapid unplug/replug cycles.
            self._active.close()
            self._active = None
            return None
        for backend in self._backends:
            device = backend.refresh()
            if device is not None:
                self._active = backend
                return device
        return None

    def poll(self, timeout: float) -> list[GamepadInput]:
        if self._active is None:
            time.sleep(max(0.0, timeout))
            return []
        return self._active.poll(timeout)

    def close(self) -> None:
        for backend in self._backends:
            backend.close()
        self._active = None


class GamepadMonitorThread(QThread):
    connection_changed = pyqtSignal(bool, str, str)
    action_triggered = pyqtSignal(str)

    def __init__(
        self,
        backend_factory: Callable[[], GamepadBackend] = AutoGamepadBackend,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend_factory = backend_factory
        self._stop_event = threading.Event()
        self._pressed_sources: set[tuple[str, str]] = set()
        self._action_sources: dict[str, set[str]] = {}
        self._held: dict[str, _HeldNavigation] = {}

    def prepare_start(self) -> None:
        self._stop_event.clear()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        backend: GamepadBackend | None = None
        connected: GamepadDevice | None = None
        try:
            while not self._stop_event.is_set():
                try:
                    if backend is None:
                        backend = self._backend_factory()
                    device = backend.refresh()
                    connected = self._publish_device_change(device, connected)
                    if device is None:
                        self._stop_event.wait(0.35)
                        continue
                    for input_event in backend.poll(_NAVIGATION_POLL_INTERVAL):
                        self._handle_input(input_event)
                    # A pad can disappear inside poll(). Re-check before held
                    # repeats so an unplugged D-pad cannot cause one final move.
                    device = backend.refresh()
                    connected = self._publish_device_change(device, connected)
                    if device is not None:
                        self._emit_repeats()
                except Exception:
                    # A malformed/disappearing HID must not permanently kill
                    # hot-plug support. Drop the backend and retry cleanly.
                    logger.debug("Recovering gamepad monitor after backend failure", exc_info=True)
                    if backend is not None:
                        try:
                            backend.close()
                        except Exception:
                            logger.debug("Unable to close failed gamepad backend", exc_info=True)
                    backend = None
                    self._pressed_sources.clear()
                    self._action_sources.clear()
                    self._held.clear()
                    if connected is not None:
                        connected = None
                        self.connection_changed.emit(False, "", "abxy")
                    self._stop_event.wait(0.5)
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    logger.debug("Unable to close gamepad backend during shutdown", exc_info=True)
            self._pressed_sources.clear()
            self._action_sources.clear()
            self._held.clear()
            if connected is not None:
                self.connection_changed.emit(False, "", "abxy")

    def _publish_device_change(
        self, device: GamepadDevice | None, connected: GamepadDevice | None
    ) -> GamepadDevice | None:
        if device == connected:
            return connected
        self._pressed_sources.clear()
        self._action_sources.clear()
        self._held.clear()
        self.connection_changed.emit(
            device is not None,
            device.name if device else "",
            device.profile if device else "abxy",
        )
        return device

    def _handle_input(self, input_event: GamepadInput) -> None:
        action = input_event.action
        source = input_event.source or action
        key = (action, source)
        if input_event.pressed:
            if key in self._pressed_sources:
                return
            self._pressed_sources.add(key)
            sources = self._action_sources.setdefault(action, set())
            first_source = not sources
            sources.add(source)
            if first_source:
                self.action_triggered.emit(action)
                if action in _REPEATABLE_ACTIONS:
                    self._held[action] = _HeldNavigation(
                        time.monotonic() + _NAVIGATION_REPEAT_INITIAL_DELAY
                    )
        else:
            self._pressed_sources.discard(key)
            sources = self._action_sources.get(action)
            if sources is not None:
                sources.discard(source)
                if not sources:
                    self._action_sources.pop(action, None)
                    self._held.pop(action, None)

    def _emit_repeats(self) -> None:
        now = time.monotonic()
        for action, held in tuple(self._held.items()):
            if now < held.next_due:
                continue
            self.action_triggered.emit(action)
            repeat_count = held.repeat_count + 1
            interval = max(
                _NAVIGATION_REPEAT_INTERVAL_MIN,
                _NAVIGATION_REPEAT_INTERVAL_START - min(repeat_count, 4) * _NAVIGATION_REPEAT_RAMP,
            )
            self._held[action] = _HeldNavigation(now + interval, repeat_count)


class GamepadFocusRing(QWidget):
    """Small painted overlay for the focused widget.

    The focus highlight must not animate QSS or QGraphicsDropShadowEffect.
    Geometry changes repaint only this tiny transparent child widget instead of
    invalidating the page stylesheet or a large parent subtree.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("GamepadFocusRing")
        self.setProperty("gamepadOverlay", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._focus_color = QColor(COLORS["focus"])
        self._fill_color = QColor(110, 159, 255, 18)

    def refresh_appearance(self) -> None:
        self._focus_color = QColor(COLORS["focus"])
        self._fill_color = QColor(110, 159, 255, 18)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(5, 5, -5, -5)
        if rect.width() <= 2 or rect.height() <= 2:
            return
        for inset, alpha, width in ((1, 38, 2), (3, 24, 2), (5, 15, 1)):
            glow = QColor(self._focus_color)
            glow.setAlpha(alpha)
            painter.setPen(QPen(glow, width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-inset, -inset, inset, inset), 11 + inset, 11 + inset)
        painter.setPen(QPen(self._focus_color, 2))
        painter.setBrush(self._fill_color)
        painter.drawRoundedRect(rect, 9, 9)


class GamepadKeypadOverlay(QFrame):
    """Gamepad-operated numeric pad for in-app Qt text/numeric controls.

    It deliberately targets only widgets owned by this application. External
    Polkit/password dialogs run in another process and are not safe to capture
    or drive from here.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("GamepadKeypadOverlay")
        self.setProperty("gamepadKeypad", True)
        self.setWindowFlag(Qt.WindowType.SubWindow, True)
        self._target: QWidget | None = None
        self._buffer = ""
        self._replace_on_next_digit = False
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(7)
        title = QLabel(tr("Numeric pad"))
        title.setProperty("gamepadKeypadTitle", True)
        layout.addWidget(title)
        self._title = title

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        layout.addLayout(grid)
        self._buttons: list[QPushButton] = []
        entries = [
            ("1", "1"), ("2", "2"), ("3", "3"),
            ("4", "4"), ("5", "5"), ("6", "6"),
            ("7", "7"), ("8", "8"), ("9", "9"),
            ("⌫", "backspace"), ("0", "0"), ("✓", "accept"),
        ]
        for index, (label, action) in enumerate(entries):
            button = QPushButton(label)
            button.setProperty("gamepadKeypadButton", True)
            button.setMinimumSize(44, 36)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(lambda checked=False, item=action: self._activate(item))
            grid.addWidget(button, index // 3, index % 3)
            self._buttons.append(button)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        clear = QPushButton(tr("Clear"))
        clear.setProperty("gamepadKeypadSecondary", True)
        clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        clear.clicked.connect(lambda: self._activate("clear"))
        hide = QPushButton(tr("Hide"))
        hide.setProperty("gamepadKeypadSecondary", True)
        hide.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        hide.clicked.connect(self._hide_and_restore)
        controls.addWidget(clear)
        controls.addWidget(hide)
        layout.addLayout(controls)
        self._buttons.extend((clear, hide))
        self._clear_button = clear
        self._hide_button = hide
        self.setStyleSheet(
            "QFrame#GamepadKeypadOverlay {"
            f"background:{COLORS['panel_raised']}; border:1px solid {COLORS['border_strong']};"
            "border-radius:13px;}"
            f"QLabel[gamepadKeypadTitle='true'] {{color:{COLORS['muted']}; font-size:10px; font-weight:820;}}"
            "QPushButton[gamepadKeypadButton='true'], QPushButton[gamepadKeypadSecondary='true'] {"
            f"background:{COLORS['control']}; color:{COLORS['text']}; border:1px solid {COLORS['border']};"
            "border-radius:9px; font-size:13px; font-weight:820; padding:5px 8px;}"
            "QPushButton[gamepadKeypadButton='true']:focus, QPushButton[gamepadKeypadSecondary='true']:focus {"
            f"border:2px solid {COLORS['focus']}; background:{COLORS['control_hover']};}}"
        )

    def set_target(self, target: QWidget) -> bool:
        if not self._editable_target(target):
            return False
        if target is self._target and self.isVisible():
            return True
        self._target = target
        try:
            if isinstance(target, QAbstractSpinBox):
                editor = target.lineEdit()
                self._buffer = self._spinbox_plain_text(target)
                target.setProperty("gamepadKeypadKeyboardTracking", bool(target.keyboardTracking()))
                target.setKeyboardTracking(False)
                editor.setFocus(Qt.FocusReason.OtherFocusReason)
                editor.selectAll()
                self._replace_on_next_digit = True
            elif isinstance(target, QLineEdit):
                self._buffer = target.selectedText() if target.hasSelectedText() else target.text()
                target.setFocus(Qt.FocusReason.OtherFocusReason)
                self._replace_on_next_digit = target.hasSelectedText()
        except (RuntimeError, TypeError, AttributeError):
            return False
        return True

    def show_for(self, target: QWidget, top: QWidget, *, focus_keypad: bool = True) -> bool:
        if not self.set_target(target):
            return False
        self.adjustSize()
        try:
            local = target.mapTo(top, QPoint(0, 0))
            x = min(max(8, local.x() + target.width() - self.width()), max(8, top.width() - self.width() - 8))
            below = local.y() + target.height() + 8
            above = local.y() - self.height() - 8
            y = below if below + self.height() <= top.height() - 8 else max(8, above)
            self.move(x, y)
            self.show()
            self.raise_()
            if focus_keypad and self._buttons:
                self._buttons[0].setFocus(Qt.FocusReason.TabFocusReason)
            return True
        except (RuntimeError, TypeError):
            self._restore_spinbox_tracking()
            self.hide()
            return False

    def retranslate(self) -> None:
        self._title.setText(tr("Numeric pad"))
        self._clear_button.setText(tr("Clear"))
        self._hide_button.setText(tr("Hide"))

    def focusable_buttons(self) -> list[QPushButton]:
        buttons: list[QPushButton] = []
        for button in self._buttons:
            if not _qobject_alive(button):
                continue
            try:
                if button.isEnabled() and button.isVisibleTo(self):
                    buttons.append(button)
            except RuntimeError:
                continue
        return buttons

    @staticmethod
    def _editable_target(widget: QWidget | None) -> bool:
        if not isinstance(widget, (QLineEdit, QAbstractSpinBox)):
            return False
        try:
            return widget.isEnabled() and widget.isVisible()
        except RuntimeError:
            return False

    def owns_focus(self) -> bool:
        focused = QApplication.focusWidget()
        return isinstance(focused, QWidget) and (focused is self or self.isAncestorOf(focused))

    def _hide_and_restore(self) -> None:
        target = self._target
        self._restore_spinbox_tracking()
        self.hide()
        if isinstance(target, QWidget) and _qobject_alive(target):
            try:
                target.setProperty("gamepadKeypadDismissed", True)
                target.setFocus(Qt.FocusReason.OtherFocusReason)
            except (RuntimeError, TypeError):
                pass

    def _restore_spinbox_tracking(self) -> None:
        target = self._target
        if isinstance(target, QAbstractSpinBox) and _qobject_alive(target):
            try:
                stored = target.property("gamepadKeypadKeyboardTracking")
                if stored is not None:
                    target.setKeyboardTracking(bool(stored))
                    target.setProperty("gamepadKeypadKeyboardTracking", None)
            except (RuntimeError, TypeError):
                pass

    @staticmethod
    def _spinbox_plain_text(target: QAbstractSpinBox) -> str:
        if isinstance(target, QSpinBox):
            return str(target.value())
        if isinstance(target, QDoubleSpinBox):
            text = str(target.value())
            return text.rstrip("0").rstrip(".") if "." in text else text
        try:
            return target.lineEdit().text().strip()
        except (RuntimeError, AttributeError):
            return ""

    @staticmethod
    def _clamp_spinbox_text(target: QAbstractSpinBox, text: str) -> str:
        if text == "":
            return ""
        try:
            if isinstance(target, QSpinBox):
                value = int(text)
                value = max(target.minimum(), min(target.maximum(), value))
                target.setValue(value)
                return str(value)
            if isinstance(target, QDoubleSpinBox):
                value = float(text)
                value = max(target.minimum(), min(target.maximum(), value))
                target.setValue(value)
                return str(value).rstrip("0").rstrip(".") if "." in str(value) else str(value)
            editor = target.lineEdit()
            editor.setText(text)
            target.interpretText()
            return text
        except (RuntimeError, TypeError, ValueError, AttributeError):
            return text

    def _apply_buffer(self) -> None:
        target = self._target
        if isinstance(target, QAbstractSpinBox) and _qobject_alive(target):
            try:
                tracking = bool(target.keyboardTracking())
                target.setKeyboardTracking(False)
                target.lineEdit().setText(self._buffer)
                target.setKeyboardTracking(tracking)
            except (RuntimeError, AttributeError):
                pass
            return
        editor = self._target_editor()
        if editor is None:
            return
        if isinstance(target, QLineEdit):
            editor.setText(self._buffer)
        else:
            editor.setText(self._buffer)

    def _target_editor(self) -> QLineEdit | None:
        target = self._target
        if isinstance(target, QLineEdit) and _qobject_alive(target):
            return target
        if isinstance(target, QAbstractSpinBox) and _qobject_alive(target):
            try:
                return target.lineEdit()
            except (RuntimeError, AttributeError):
                return None
        return None

    def _activate(self, action: str) -> None:
        editor = self._target_editor()
        if editor is None:
            self._restore_spinbox_tracking()
            self.hide()
            return
        try:
            if action.isdigit():
                if self._replace_on_next_digit:
                    self._buffer = ""
                    self._replace_on_next_digit = False
                self._buffer = f"{self._buffer}{action}"
                self._apply_buffer()
            elif action == "backspace":
                self._replace_on_next_digit = False
                self._buffer = self._buffer[:-1]
                self._apply_buffer()
            elif action == "clear":
                self._replace_on_next_digit = False
                self._buffer = ""
                self._apply_buffer()
            elif action == "accept":
                target = self._target
                if isinstance(target, QAbstractSpinBox):
                    self._buffer = self._clamp_spinbox_text(target, self._buffer)
                    self._restore_spinbox_tracking()
                    target.interpretText()
                self.hide()
                target = self._target
                if isinstance(target, QWidget) and _qobject_alive(target):
                    target.setProperty("gamepadKeypadDismissed", True)
                    target.setFocus(Qt.FocusReason.OtherFocusReason)
        except (RuntimeError, TypeError):
            self._restore_spinbox_tracking()
            self.hide()


class GamepadHintBar(QFrame):
    """Floating Steam-style controller legend that never affects layouts."""

    ICONS = {
        "abxy": {
            "move": "gamepad_dpad",
            "accept": "gamepad_a",
            "cancel": "gamepad_b",
            "keypad": "gamepad_x",
            "refresh": "gamepad_y",
            "view": "gamepad_view",
            "menu": "gamepad_menu",
            "previous_section": "gamepad_lb",
            "next_section": "gamepad_rb",
        },
        "playstation": {
            "move": "gamepad_ps_dpad",
            "accept": "gamepad_ps_cross",
            "cancel": "gamepad_ps_circle",
            "keypad": "gamepad_ps_square",
            "refresh": "gamepad_ps_triangle",
            "view": "gamepad_ps_share",
            "menu": "gamepad_ps_options",
            "previous_section": "gamepad_ps_l1",
            "next_section": "gamepad_ps_r1",
        },
    }

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("GamepadHintBar")
        self.setProperty("gamepadOverlay", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(8)
        self._source_labels: list[QLabel] = []
        self._section_widgets: list[QWidget] = []
        self._menu_widgets: list[QWidget] = []
        self._settings_widgets: list[QWidget] = []
        self._icon_labels: dict[str, QLabel] = {}
        self._profile = "abxy"
        self._move_text = self._add_hint(layout, "move", "Move")
        self._accept_text = self._add_hint(layout, "accept", "Confirm")
        self._cancel_text = self._add_hint(layout, "cancel", "Back")
        self._keypad_widgets: list[QWidget] = []
        self._keypad_widgets.append(self._add_icon(layout, "keypad"))
        self._keypad_text = QLabel()
        self._keypad_text.setProperty("gamepadHintText", True)
        layout.addWidget(self._keypad_text)
        self._keypad_widgets.append(self._keypad_text)
        self._refresh_text = self._add_hint(layout, "refresh", "Refresh")
        self._settings_widgets.append(self._add_icon(layout, "view"))
        self._settings_text = QLabel()
        self._settings_text.setProperty("gamepadHintText", True)
        layout.addWidget(self._settings_text)
        self._settings_widgets.append(self._settings_text)
        self._menu_widgets.append(self._add_icon(layout, "menu"))
        self._menu_text = QLabel()
        self._menu_text.setProperty("gamepadHintText", True)
        layout.addWidget(self._menu_text)
        self._menu_widgets.append(self._menu_text)
        self._section_widgets.append(self._add_icon(layout, "previous_section"))
        self._section_widgets.append(self._add_icon(layout, "next_section"))
        sections = QLabel()
        sections.setProperty("gamepadHintText", True)
        layout.addWidget(sections)
        self._sections_label = sections
        self._section_widgets.append(sections)
        self._sections_available = True
        self._menu_available = True
        self._settings_available = True
        self._keypad_available = False
        self._available_width = 0
        self.retranslate()
        self.set_profile("abxy")
        self.refresh_appearance()

    def _icon_name(self, semantic: str) -> str:
        family = self.ICONS.get(self._profile, self.ICONS["abxy"])
        return family.get(semantic, self.ICONS["abxy"].get(semantic, "gamepad_a"))

    def _add_icon(self, layout: QHBoxLayout, semantic: str, size: int = 18) -> QLabel:
        icon_label = QLabel()
        icon_label.setProperty("gamepadHintIcon", True)
        icon_label.setProperty("gamepadSemanticIcon", semantic)
        icon_label.setPixmap(QIcon(str(_ICON_DIR / f"{self._icon_name(semantic)}.svg")).pixmap(size, size))
        layout.addWidget(icon_label)
        self._icon_labels[semantic] = icon_label
        return icon_label

    def _add_hint(self, layout: QHBoxLayout, semantic: str, text: str) -> QLabel:
        self._add_icon(layout, semantic)
        label = QLabel()
        label.setProperty("gamepadHintText", True)
        label.setProperty("gamepadSourceText", text)
        self._source_labels.append(label)
        layout.addWidget(label)
        return label

    def set_profile(self, profile: str) -> None:
        normalized = "playstation" if profile == "playstation" else "abxy"
        if normalized == self._profile:
            return
        self._profile = normalized
        for semantic, label in self._icon_labels.items():
            label.setPixmap(QIcon(str(_ICON_DIR / f"{self._icon_name(semantic)}.svg")).pixmap(18, 18))
        self.adjustSize()

    def set_available_width(self, width: int) -> None:
        """Collapse optional text before the overlay can overflow a small window."""

        width = max(0, int(width))
        if width == self._available_width:
            return
        self._available_width = width
        self._set_sections_visible(self._sections_available and width >= 620)
        show_words = width >= 430
        self._move_text.setVisible(width >= 520)
        self._accept_text.setVisible(show_words)
        self._cancel_text.setVisible(show_words)
        self._set_keypad_visible(self._keypad_available and width >= 620)
        self._refresh_text.setVisible(width >= 520)
        self._set_settings_visible(self._settings_available and width >= 760)
        self._set_menu_visible(self._menu_available and width >= 700)
        self.adjustSize()

    def set_sections_available(self, available: bool) -> None:
        """Show LB/RB only where the active window actually handles it."""

        available = bool(available)
        if available == self._sections_available:
            return
        self._sections_available = available
        self._set_sections_visible(self._sections_available and self._available_width >= 620)
        self.adjustSize()

    def set_menu_available(self, available: bool) -> None:
        available = bool(available)
        if available == self._menu_available:
            return
        self._menu_available = available
        self._set_menu_visible(self._menu_available and self._available_width >= 700)
        self.adjustSize()

    def set_settings_available(self, available: bool) -> None:
        available = bool(available)
        if available == self._settings_available:
            return
        self._settings_available = available
        self._set_settings_visible(self._settings_available and self._available_width >= 760)
        self.adjustSize()

    def set_keypad_available(self, available: bool) -> None:
        available = bool(available)
        if available == self._keypad_available:
            return
        self._keypad_available = available
        self._set_keypad_visible(self._keypad_available and self._available_width >= 620)
        self.adjustSize()

    def _set_sections_visible(self, visible: bool) -> None:
        for widget in self._section_widgets:
            widget.setVisible(visible)

    def _set_menu_visible(self, visible: bool) -> None:
        for widget in self._menu_widgets:
            widget.setVisible(visible)

    def _set_settings_visible(self, visible: bool) -> None:
        for widget in self._settings_widgets:
            widget.setVisible(visible)

    def _set_keypad_visible(self, visible: bool) -> None:
        for widget in self._keypad_widgets:
            widget.setVisible(visible)

    def retranslate(self) -> None:
        for label in self._source_labels:
            source = label.property("gamepadSourceText")
            if source:
                label.setText(tr(str(source)))
        self._settings_text.setText(tr("Settings"))
        self._keypad_text.setText(tr("Keypad"))
        self._menu_text.setText(tr("Sidebar"))
        self._sections_label.setText(tr("Sections"))
        self.adjustSize()

    def refresh_appearance(self) -> None:
        self.setStyleSheet(
            "QFrame#GamepadHintBar {"
            f"background:{COLORS['panel_raised']}; border:1px solid {COLORS['border_strong']};"
            "border-radius:11px;}"
            f"QLabel[gamepadHintText='true'] {{color:{COLORS['muted']}; font-size:10px; font-weight:720;}}"
        )
        self.adjustSize()


class GamepadNavigationController(QObject):
    """Translate semantic gamepad actions into normal Qt widget behavior."""

    connection_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        host: QMainWindow,
        *,
        backend_factory: Callable[[], GamepadBackend] = AutoGamepadBackend,
        start_worker: bool = True,
    ) -> None:
        super().__init__(host)
        self.host = host
        self.connected = False
        self.device_name = ""
        self.profile = "abxy"
        self._ui_hooks_installed = False
        self._bars: dict[int, GamepadHintBar] = {}
        self._keypads: dict[int, GamepadKeypadOverlay] = {}
        self._focus_rings: dict[int, GamepadFocusRing] = {}
        self._focus_ring_animations: dict[int, QPropertyAnimation] = {}
        self._focus_badges: dict[int, QLabel] = {}
        self._focus_policy_records: dict[
            int, tuple[weakref.ReferenceType[QWidget], Qt.FocusPolicy, Qt.FocusPolicy]
        ] = {}
        self._focus_candidates_cache: dict[tuple[int, int], tuple[int, list[weakref.ReferenceType[QWidget]]]] = {}
        self._focus_cache_revision = 0
        self._onscreen_keypad_enabled = True
        self._onscreen_keypad_auto_show = False
        self._shutdown = False
        self._pending_normalize = False
        self._pending_visuals = False
        self._pending_focus = False
        self._maintenance_timer = QTimer(self)
        self._maintenance_timer.setSingleShot(True)
        self._maintenance_timer.setInterval(0)
        self._maintenance_timer.timeout.connect(self._run_deferred_maintenance)
        self._worker: GamepadMonitorThread | None = None
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop)
        if start_worker:
            self._worker = GamepadMonitorThread(backend_factory, self)
            self._worker.connection_changed.connect(self._set_connection)
            self._worker.action_triggered.connect(self.dispatch_action)

    def start(self) -> None:
        self._shutdown = False
        if self._worker is not None and not self._worker.isRunning():
            self._worker.prepare_start()
            self._worker.start()

    def stop(self) -> None:
        self._shutdown = True
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.stop()
            worker.wait(1_500)
        self.connected = False
        self.device_name = ""
        self._maintenance_timer.stop()
        self._pending_normalize = False
        self._pending_visuals = False
        self._pending_focus = False
        self._disable_ui_hooks()
        self._restore_focus_policies()
        self._hide_visuals()
        self._hide_keypads()

    def set_onscreen_keypad_enabled(self, enabled: bool) -> None:
        self._onscreen_keypad_enabled = bool(enabled)
        if not self._onscreen_keypad_enabled:
            self._hide_keypads()
        self._queue_maintenance(visuals=True)

    def set_onscreen_keypad_auto_show(self, enabled: bool) -> None:
        self._onscreen_keypad_auto_show = bool(enabled)
        if not self._onscreen_keypad_auto_show:
            self._hide_keypads()
        self._queue_maintenance(visuals=True)

    def set_connected_for_testing(self, connected: bool, name: str = "Test ABXY gamepad", profile: str = "abxy") -> None:
        if connected:
            self._shutdown = False
        self._set_connection(connected, name if connected else "", profile)

    def _set_connection(self, connected: bool, name: str, profile: str) -> None:
        connected = bool(connected)
        if connected and self._shutdown:
            # Ignore a queued worker signal delivered after closeEvent()/stop().
            return
        name = str(name or "")
        profile = str(profile or "abxy")
        changed = self.connected != connected or self.profile != profile or self.device_name != name
        was_connected = self.connected
        self.connected = connected
        self.device_name = name
        self.profile = profile
        if connected:
            self._install_ui_hooks()
            self._queue_maintenance(normalize=True, visuals=True, focus=not was_connected)
        else:
            self._maintenance_timer.stop()
            self._pending_normalize = False
            self._pending_visuals = False
            self._pending_focus = False
            self._disable_ui_hooks()
            self._restore_focus_policies()
            self._hide_visuals()
            self._hide_keypads()
        if changed:
            self.connection_changed.emit(self.connected, self.device_name)

    def _install_ui_hooks(self) -> None:
        if self._ui_hooks_installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        app.focusChanged.connect(self._focus_changed)
        self._ui_hooks_installed = True

    def _disable_ui_hooks(self) -> None:
        if not self._ui_hooks_installed:
            return
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except (TypeError, RuntimeError):
                logger.debug("Gamepad event filter was already removed", exc_info=True)
            try:
                app.focusChanged.disconnect(self._focus_changed)
            except (TypeError, RuntimeError):
                logger.debug("Gamepad focus hook was already disconnected", exc_info=True)
        self._ui_hooks_installed = False

    def retranslate(self) -> None:
        for key, bar in tuple(self._bars.items()):
            if not _qobject_alive(bar):
                self._bars.pop(key, None)
                continue
            bar.retranslate()
        for key, keypad in tuple(self._keypads.items()):
            if not _qobject_alive(keypad):
                self._keypads.pop(key, None)
                continue
            keypad.retranslate()
        self._queue_maintenance(visuals=True)

    def refresh_appearance(self) -> None:
        for key, bar in tuple(self._bars.items()):
            if not _qobject_alive(bar):
                self._bars.pop(key, None)
                continue
            bar.refresh_appearance()
        for key, ring in tuple(self._focus_rings.items()):
            if not _qobject_alive(ring):
                self._focus_rings.pop(key, None)
                continue
            ring.refresh_appearance()
        self._queue_maintenance(visuals=True)

    def defer_focus_current_scope(self) -> None:
        self._queue_maintenance(normalize=True, visuals=True, focus=True)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if not self.connected or not isinstance(watched, QWidget):
            return False
        if self._is_overlay_widget(watched):
            return False
        event_type = event.type()
        if event_type == QEvent.Type.ChildAdded:
            child_getter = getattr(event, "child", None)
            child = child_getter() if callable(child_getter) else None
            if isinstance(child, QWidget) and self._is_overlay_widget(child):
                return False
        if event_type in {QEvent.Type.Show, QEvent.Type.ChildAdded}:
            self._queue_maintenance(
                normalize=True,
                visuals=True,
                focus=event_type == QEvent.Type.Show and self._safe_is_window(watched),
            )
        elif event_type in {
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Hide,
        }:
            # Candidate membership does not change when live labels resize or
            # layouts move. Geometry is read fresh for every navigation action,
            # and cached candidates are revalidated before use. Avoiding a full
            # cache rebuild here keeps telemetry-heavy pages responsive.
            self._queue_maintenance(visuals=True)
        elif event_type in {QEvent.Type.EnabledChange, QEvent.Type.ParentChange}:
            self._invalidate_focus_cache()
        return False

    def _queue_maintenance(self, *, normalize: bool = False, visuals: bool = False, focus: bool = False) -> None:
        if not self.connected:
            return
        if normalize or focus:
            self._invalidate_focus_cache()
        self._pending_normalize = self._pending_normalize or normalize
        self._pending_visuals = self._pending_visuals or visuals
        self._pending_focus = self._pending_focus or focus
        if not self._maintenance_timer.isActive():
            self._maintenance_timer.start()

    def _invalidate_focus_cache(self) -> None:
        self._focus_cache_revision += 1
        self._focus_candidates_cache.clear()

    def _run_deferred_maintenance(self) -> None:
        normalize = self._pending_normalize
        visuals = self._pending_visuals
        focus = self._pending_focus
        self._pending_normalize = False
        self._pending_visuals = False
        self._pending_focus = False
        if not self.connected or not _qobject_alive(self.host):
            return
        if normalize:
            self._normalize_all_top_levels()
        if focus:
            self.focus_current_scope()
        if visuals:
            self._refresh_visuals()

    def dispatch_action(self, action: str) -> None:
        if not self.connected:
            return
        if action in {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}:
            keypad = self._active_keypad()
            if keypad is not None:
                self._move_keypad_focus(keypad, action)
            else:
                self._move_focus(action)
        elif action in {ACTION_SCROLL_UP, ACTION_SCROLL_DOWN}:
            self._scroll_active_scope(ACTION_UP if action == ACTION_SCROLL_UP else ACTION_DOWN)
        elif action == ACTION_ACCEPT:
            keypad = self._active_keypad()
            focused = QApplication.focusWidget()
            if keypad is not None and not keypad.owns_focus():
                buttons = keypad.focusable_buttons()
                if buttons:
                    self._safe_set_focus(buttons[0])
                    self._queue_maintenance(visuals=True)
            else:
                self._activate_focused()
        elif action == ACTION_CANCEL:
            self._cancel_or_back()
        elif action == ACTION_PREVIOUS_SECTION:
            self._cycle_section(-1)
        elif action == ACTION_NEXT_SECTION:
            self._cycle_section(1)
        elif action == ACTION_TOGGLE_SIDEBAR:
            self._toggle_sidebar()
        elif action == ACTION_OPEN_SETTINGS:
            self._open_settings()
        elif action == ACTION_GO_DASHBOARD:
            self._go_dashboard()
        elif action == ACTION_CONTEXT_X:
            self._toggle_keypad()
        elif action == ACTION_CONTEXT_Y:
            self._refresh_current_page()

    def focus_current_scope(self) -> None:
        if not self.connected or not _qobject_alive(self.host):
            return
        if self._active_popup() is not None:
            return
        top = self._active_top_level()
        if top is None:
            return
        scope = self._focus_scope(top)
        candidates = self._focusable_widgets(scope, top)
        if not candidates:
            return
        current = QApplication.focusWidget()
        if current not in candidates:
            target = self._preferred_entry(candidates)
            self._safe_set_focus(target)
            self._ensure_visible(target)


    def _scroll_active_scope(self, direction: str) -> None:
        if self._active_popup() is not None:
            target = QApplication.focusWidget()
            if isinstance(target, QWidget) and _qobject_alive(target):
                self._send_key(target, _DIRECTION_KEYS[direction])
            return
        top = self._active_top_level()
        if top is None:
            return
        focused = QApplication.focusWidget()
        for widget in (focused, self._focus_scope(top), top):
            if isinstance(widget, QWidget) and _qobject_alive(widget):
                if self._scroll_nearest(widget, direction, multiplier=2.4):
                    self._queue_maintenance(visuals=True)
                    return

    def _active_popup(self) -> QWidget | None:
        app = QApplication.instance()
        if app is None:
            return None
        try:
            popup = app.activePopupWidget()
        except RuntimeError:
            return None
        return popup if isinstance(popup, QWidget) and _qobject_alive(popup) and popup.isVisible() else None

    @staticmethod
    def _combo_popup_visible(combo: QComboBox) -> bool:
        try:
            view = combo.view()
            return isinstance(view, QWidget) and _qobject_alive(view) and view.isVisible()
        except (RuntimeError, TypeError):
            return False

    def _active_top_level(self) -> QWidget | None:
        app = QApplication.instance()
        if app is not None:
            try:
                modal = app.activeModalWidget()
                if isinstance(modal, QWidget) and _qobject_alive(modal) and modal.isVisible():
                    return modal
                active = app.activeWindow()
                if isinstance(active, QDialog) and _qobject_alive(active) and active.isVisible():
                    return active
            except RuntimeError:
                return self.host if _qobject_alive(self.host) else None
        return self.host if _qobject_alive(self.host) else None

    @staticmethod
    def _focus_scope(top: QWidget) -> QWidget:
        provider = getattr(top, "gamepad_focus_scope", None)
        if callable(provider):
            try:
                scope = provider()
                if isinstance(scope, QWidget) and _qobject_alive(scope):
                    return scope
            except Exception:
                logger.debug("Unable to resolve gamepad focus scope", exc_info=True)
        return top

    def _normalize_all_top_levels(self) -> None:
        if not self.connected:
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            tops = tuple(app.topLevelWidgets())
        except RuntimeError:
            return
        for top in tops:
            if _qobject_alive(top) and not self._is_overlay_widget(top):
                self._normalize_focusables(top)

    def _normalize_focusables(self, root: QWidget) -> None:
        if not self.connected or not _qobject_alive(root):
            return
        try:
            widgets: Iterable[QWidget] = (root, *root.findChildren(QWidget))
        except (RuntimeError, TypeError):
            return
        for widget in widgets:
            if not self._normalizable_widget(widget):
                continue
            try:
                policy = widget.focusPolicy()
                if policy == Qt.FocusPolicy.NoFocus and self._record_focus_policy(
                    widget, policy, Qt.FocusPolicy.ClickFocus
                ):
                    # ClickFocus accepts programmatic controller focus without
                    # adding the widget to the keyboard Tab chain.
                    widget.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            except (RuntimeError, TypeError):
                continue

    def _normalizable_widget(self, widget: QWidget) -> bool:
        if not _qobject_alive(widget) or self._is_overlay_widget(widget):
            return False
        try:
            if isinstance(widget, QHeaderView):
                return False
            if bool(widget.property("gamepadSkip")) or self._is_internal_editor(widget):
                return False
            activator = getattr(widget, "gamepad_activate", None)
            return isinstance(
                widget,
                (
                    QAbstractButton,
                    QComboBox,
                    QLineEdit,
                    QAbstractSpinBox,
                    QSlider,
                    QAbstractItemView,
                    QPlainTextEdit,
                    QTextEdit,
                ),
            ) or callable(activator)
        except (RuntimeError, TypeError):
            return False

    @staticmethod
    def _is_internal_editor(widget: QWidget) -> bool:
        if not isinstance(widget, QLineEdit):
            return False
        try:
            parent = widget.parentWidget()
            while parent is not None and not parent.isWindow():
                if isinstance(parent, (QAbstractSpinBox, QComboBox)):
                    return True
                parent = parent.parentWidget()
        except RuntimeError:
            return True
        return False

    def _record_focus_policy(
        self, widget: QWidget, policy: Qt.FocusPolicy, applied: Qt.FocusPolicy
    ) -> bool:
        key = id(widget)
        existing = self._focus_policy_records.get(key)
        if existing is not None and existing[0]() is widget:
            return True
        try:
            reference = weakref.ref(widget)
        except TypeError:
            return False
        self._focus_policy_records[key] = (reference, policy, applied)
        try:
            widget.destroyed.connect(lambda _obj=None, item=key: self._focus_policy_records.pop(item, None))
        except (RuntimeError, TypeError):
            self._focus_policy_records.pop(key, None)
            return False
        return True

    def _restore_focus_policies(self) -> None:
        records = tuple(self._focus_policy_records.items())
        self._focus_policy_records.clear()
        for _key, (reference, original, applied) in records:
            widget = reference()
            if not _qobject_alive(widget):
                continue
            try:
                # Do not overwrite an unrelated policy change made by the page.
                if widget.focusPolicy() == applied:
                    widget.setFocusPolicy(original)
            except (RuntimeError, TypeError):
                continue

    def _focusable_widgets(self, root: QWidget, top: QWidget) -> list[QWidget]:
        if not _qobject_alive(root) or not _qobject_alive(top):
            return []
        cache_key = (id(root), id(top))
        cached = self._focus_candidates_cache.get(cache_key)
        if cached is not None and cached[0] == self._focus_cache_revision:
            widgets: list[QWidget] = []
            for reference in cached[1]:
                widget = reference()
                if isinstance(widget, QWidget) and self._cached_focus_candidate_valid(widget, top):
                    widgets.append(widget)
            if widgets:
                return widgets
        self._normalize_focusables(root)
        try:
            widgets = [root, *root.findChildren(QWidget)]
        except (RuntimeError, TypeError):
            return []
        positioned: list[tuple[int, int, QWidget]] = []
        for widget in widgets:
            try:
                if not _qobject_alive(widget) or self._is_overlay_widget(widget):
                    continue
                if not self._normalizable_widget(widget):
                    continue
                if widget is top and not isinstance(widget, (QAbstractButton, QAbstractItemView)):
                    continue
                if not self._widget_belongs_to_top(widget, top):
                    continue
                if not widget.isEnabled() or not widget.isVisibleTo(top):
                    continue
                if isinstance(widget, QHeaderView):
                    continue
                if bool(widget.property("gamepadSkip")) or self._is_internal_editor(widget):
                    continue
                policy = widget.focusPolicy()
                controller_only = id(widget) in self._focus_policy_records
                mouse_focus = bool(policy & Qt.FocusPolicy.ClickFocus)
                if not (policy & Qt.FocusPolicy.TabFocus) and not controller_only and not mouse_focus:
                    continue
                if widget.width() < 2 or widget.height() < 2:
                    continue
                rect = self._global_rect(widget)
                if rect is None:
                    continue
                if rect.width() < 2 or rect.height() < 2:
                    continue
                positioned.append((rect.top(), rect.left(), widget))
            except (RuntimeError, TypeError):
                continue
        positioned.sort(key=lambda item: (item[0], item[1]))
        result = [item[2] for item in positioned]
        self._focus_candidates_cache[cache_key] = (
            self._focus_cache_revision,
            [weakref.ref(widget) for widget in result],
        )
        return result

    def _cached_focus_candidate_valid(self, widget: QWidget, top: QWidget) -> bool:
        if not _qobject_alive(widget) or not _qobject_alive(top) or self._is_overlay_widget(widget):
            return False
        try:
            if isinstance(widget, QHeaderView):
                return False
            if not self._normalizable_widget(widget):
                return False
            if not self._widget_belongs_to_top(widget, top):
                return False
            if not widget.isEnabled() or not widget.isVisibleTo(top):
                return False
            if bool(widget.property("gamepadSkip")) or self._is_internal_editor(widget):
                return False
            policy = widget.focusPolicy()
            controller_only = id(widget) in self._focus_policy_records
            mouse_focus = bool(policy & Qt.FocusPolicy.ClickFocus)
            if not (policy & Qt.FocusPolicy.TabFocus) and not controller_only and not mouse_focus:
                return False
            return widget.width() >= 2 and widget.height() >= 2
        except (RuntimeError, TypeError):
            return False

    @staticmethod
    def _preferred_entry(candidates: list[QWidget]) -> QWidget:
        for widget in candidates:
            try:
                is_default = getattr(widget, "isDefault", None)
                if callable(is_default) and bool(is_default()):
                    return widget
                if bool(widget.property("gamepadEntry")):
                    return widget
            except (RuntimeError, TypeError, AttributeError):
                continue
        return candidates[0]

    @staticmethod
    def _global_rect(widget: QWidget) -> QRect | None:
        if not _qobject_alive(widget):
            return None
        try:
            origin = widget.mapToGlobal(QPoint(0, 0))
            return QRect(origin, widget.size())
        except (RuntimeError, TypeError):
            return None

    @staticmethod
    def _widget_belongs_to_top(widget: QWidget, top: QWidget) -> bool:
        try:
            return widget is top or widget.window() is top or top.isAncestorOf(widget)
        except RuntimeError:
            return False

    def _move_focus(self, direction: str) -> None:
        popup = self._active_popup()
        if popup is not None:
            target = QApplication.focusWidget()
            if target is None or not _qobject_alive(target):
                target = popup.findChild(QAbstractItemView)
            if isinstance(target, QWidget) and _qobject_alive(target):
                self._send_key(target, _DIRECTION_KEYS[direction])
            return

        top = self._active_top_level()
        if top is None:
            return
        scope = self._focus_scope(top)
        candidates = self._focusable_widgets(scope if scope is not top else top, top)
        if not candidates:
            return
        current = QApplication.focusWidget()
        if current is None or current not in candidates:
            if scope is not top:
                # Do not scan the whole main window on every normal page move:
                # that includes hidden/large page trees and makes the highlight
                # feel delayed. Only fall back to the full top-level graph when
                # focus already lives outside the active page, such as sidebar
                # chrome or a dialog header button.
                top_candidates = self._focusable_widgets(top, top)
                if current in top_candidates:
                    candidates = top_candidates
                else:
                    self.focus_current_scope()
                    return
            else:
                self.focus_current_scope()
                return
        if self._handle_widget_direction(current, direction):
            self._queue_maintenance(visuals=True)
            return
        current_rect = self._global_rect(current)
        if current_rect is None:
            self.focus_current_scope()
            return
        current_center = current_rect.center()
        scored: list[tuple[float, QWidget]] = []
        for candidate in candidates:
            if candidate is current:
                continue
            rect = self._global_rect(candidate)
            if rect is None:
                continue
            center = rect.center()
            dx = center.x() - current_center.x()
            dy = center.y() - current_center.y()
            if direction == ACTION_UP and dy >= -2:
                continue
            if direction == ACTION_DOWN and dy <= 2:
                continue
            if direction == ACTION_LEFT and dx >= -2:
                continue
            if direction == ACTION_RIGHT and dx <= 2:
                continue
            if direction in {ACTION_UP, ACTION_DOWN}:
                primary = abs(dy)
                orthogonal = abs(dx)
                overlaps = rect.right() >= current_rect.left() and rect.left() <= current_rect.right()
            else:
                primary = abs(dx)
                orthogonal = abs(dy)
                overlaps = rect.bottom() >= current_rect.top() and rect.top() <= current_rect.bottom()
            score = primary + orthogonal * 1.7 + (0.0 if overlaps else 95.0)
            scored.append((score, candidate))
        if scored:
            target = min(scored, key=lambda item: item[0])[1]
            self._safe_set_focus(target)
            self._ensure_visible(target)
            return
        if self._scroll_nearest(current, direction):
            return
        index = candidates.index(current)
        step = -1 if direction in {ACTION_UP, ACTION_LEFT} else 1
        target = candidates[(index + step) % len(candidates)]
        self._safe_set_focus(target)
        self._ensure_visible(target)

    def _move_keypad_focus(self, keypad: GamepadKeypadOverlay, direction: str) -> None:
        candidates = keypad.focusable_buttons()
        if not candidates:
            return
        current = QApplication.focusWidget()
        if current not in candidates:
            self._safe_set_focus(candidates[0])
            self._queue_maintenance(visuals=True)
            return
        current_rect = self._global_rect(current)
        if current_rect is None:
            self._safe_set_focus(candidates[0])
            return
        current_center = current_rect.center()
        scored: list[tuple[float, QWidget]] = []
        for candidate in candidates:
            if candidate is current:
                continue
            rect = self._global_rect(candidate)
            if rect is None:
                continue
            center = rect.center()
            dx = center.x() - current_center.x()
            dy = center.y() - current_center.y()
            if direction == ACTION_UP and dy >= -2:
                continue
            if direction == ACTION_DOWN and dy <= 2:
                continue
            if direction == ACTION_LEFT and dx >= -2:
                continue
            if direction == ACTION_RIGHT and dx <= 2:
                continue
            if direction in {ACTION_UP, ACTION_DOWN}:
                primary = abs(dy)
                orthogonal = abs(dx)
                overlaps = rect.right() >= current_rect.left() and rect.left() <= current_rect.right()
            else:
                primary = abs(dx)
                orthogonal = abs(dy)
                overlaps = rect.bottom() >= current_rect.top() and rect.top() <= current_rect.bottom()
            scored.append((primary + orthogonal * 1.4 + (0.0 if overlaps else 80.0), candidate))
        if scored:
            target = min(scored, key=lambda item: item[0])[1]
        else:
            index = candidates.index(current)
            step = -1 if direction in {ACTION_UP, ACTION_LEFT} else 1
            target = candidates[(index + step) % len(candidates)]
        self._safe_set_focus(target)
        self._queue_maintenance(visuals=True)

    def _handle_widget_direction(self, widget: QWidget, direction: str) -> bool:
        if isinstance(widget, QAbstractItemView):
            try:
                model = widget.model()
                current = widget.currentIndex()
                parent_index = current.parent() if current.isValid() else current
                row_count = model.rowCount(parent_index)
                column_count = model.columnCount(parent_index)
                if row_count <= 0 or column_count <= 0:
                    return False
                if not current.isValid():
                    widget.setCurrentIndex(model.index(0, 0))
                    current = widget.currentIndex()
                    if not current.isValid():
                        return False
                    try:
                        widget.scrollTo(current, QAbstractItemView.ScrollHint.EnsureVisible)
                    except (RuntimeError, AttributeError, TypeError):
                        pass
                    return True
                at_boundary = (
                    (direction == ACTION_UP and current.row() <= 0)
                    or (direction == ACTION_DOWN and current.row() >= row_count - 1)
                    or (direction == ACTION_LEFT and current.column() <= 0)
                    or (direction == ACTION_RIGHT and current.column() >= column_count - 1)
                )
                if at_boundary:
                    return False
            except (RuntimeError, AttributeError, TypeError):
                return False
            self._send_key(widget, _DIRECTION_KEYS[direction])
            return True
        if isinstance(widget, QComboBox):
            return self._handle_combo_direction(widget, direction)
        if isinstance(widget, (QSlider, QAbstractSpinBox)) and direction in {ACTION_LEFT, ACTION_RIGHT}:
            self._send_key(widget, _DIRECTION_KEYS[direction])
            return True
        if isinstance(widget, (QPlainTextEdit, QTextEdit)) and direction in {ACTION_UP, ACTION_DOWN}:
            return self._scroll_nearest(widget, direction)
        return False

    def _handle_combo_direction(self, combo: QComboBox, direction: str) -> bool:
        if direction not in _DIRECTION_KEYS:
            return False
        if self._combo_popup_visible(combo):
            self._send_key(combo.view(), _DIRECTION_KEYS[direction])
            return True
        if direction in {ACTION_UP, ACTION_DOWN}:
            return False
        try:
            count = combo.count()
            current = combo.currentIndex()
            if count <= 0 or current < 0:
                return True
            delta = -1 if direction in {ACTION_UP, ACTION_LEFT} else 1
            target = max(0, min(count - 1, current + delta))
            if target != current:
                combo.setCurrentIndex(target)
            return True
        except (RuntimeError, TypeError):
            return False

    def _activate_focused(self) -> None:
        popup = self._active_popup()
        if popup is not None:
            target = QApplication.focusWidget()
            if target is None or not _qobject_alive(target):
                target = popup
            self._send_key(target, Qt.Key.Key_Return)
            return

        top = self._active_top_level()
        widget = QApplication.focusWidget()
        if top is None or widget is None or not self._valid_action_target(widget, top):
            self.focus_current_scope()
            return
        try:
            activator = getattr(widget, "gamepad_activate", None)
            if callable(activator):
                activator()
                return
            if isinstance(widget, QAbstractButton):
                widget.click()
                return
            if isinstance(widget, QComboBox):
                widget.showPopup()
                return
            self._send_key(widget, Qt.Key.Key_Return)
        except (RuntimeError, TypeError):
            self.focus_current_scope()

    def _valid_action_target(self, widget: QWidget, top: QWidget) -> bool:
        if not _qobject_alive(widget) or not self._widget_belongs_to_top(widget, top):
            return False
        try:
            return widget.isEnabled() and widget.isVisibleTo(top) and not bool(widget.property("gamepadSkip"))
        except (RuntimeError, TypeError):
            return False

    def _cancel_or_back(self) -> None:
        keypad = self._active_keypad()
        if keypad is not None:
            target = keypad._target
            keypad.hide()
            self._invalidate_focus_cache()
            if isinstance(target, QWidget) and _qobject_alive(target):
                target.setProperty("gamepadKeypadDismissed", True)
                target.setFocus(Qt.FocusReason.OtherFocusReason)
            self._queue_maintenance(visuals=True)
            return
        popup = self._active_popup()
        if popup is not None:
            target = QApplication.focusWidget()
            self._send_key(target if isinstance(target, QWidget) and _qobject_alive(target) else popup, Qt.Key.Key_Escape)
            self._queue_maintenance(visuals=True)
            return
        top = self._active_top_level()
        if isinstance(top, QDialog) and top is not self.host:
            try:
                top.reject()
            except RuntimeError:
                return
            return
        callback = getattr(self.host, "gamepad_back", None)
        if callable(callback):
            callback()

    def _cycle_section(self, delta: int) -> None:
        if self._active_popup() is not None:
            return
        top = self._active_top_level()
        if top is None:
            return
        callback = getattr(top, "gamepad_cycle_section", None)
        if callable(callback):
            callback(delta)
        elif top is self.host:
            callback = getattr(self.host, "gamepad_cycle_section", None)
            if callable(callback):
                callback(delta)
        # Never switch the page behind an unrelated modal dialog.
        self.defer_focus_current_scope()

    def _go_dashboard(self) -> None:
        if self._active_popup() is not None:
            return
        top = self._active_top_level()
        if top is None or top is not self.host:
            return
        callback = getattr(self.host, "gamepad_go_dashboard", None)
        if callable(callback):
            callback()
            self.defer_focus_current_scope()

    def _open_settings(self) -> None:
        if self._active_popup() is not None:
            return
        top = self._active_top_level()
        if top is None or top is not self.host:
            return
        callback = getattr(self.host, "gamepad_open_settings", None)
        if callable(callback):
            callback()

    def _current_keypad_target(self) -> QWidget | None:
        if not self._onscreen_keypad_enabled:
            return None
        focused = QApplication.focusWidget()
        if not isinstance(focused, QWidget) or not _qobject_alive(focused):
            return None
        keypad = self._focused_keypad()
        if keypad is not None:
            target = keypad._target
            return target if isinstance(target, QWidget) and _qobject_alive(target) else None
        parent = focused.parentWidget()
        if isinstance(parent, QAbstractSpinBox) and GamepadKeypadOverlay._editable_target(parent):
            return parent
        if GamepadKeypadOverlay._editable_target(focused):
            return focused
        return None

    def _keypad_for(self, top: QWidget) -> GamepadKeypadOverlay:
        key = id(top)
        keypad = self._keypads.get(key)
        if not _qobject_alive(keypad):
            keypad = GamepadKeypadOverlay(top)
            self._keypads[key] = keypad
            top.destroyed.connect(lambda _obj=None, item=key: self._keypads.pop(item, None))
        return keypad

    def _show_keypad_for(self, target: QWidget, top: QWidget, *, focus_keypad: bool) -> bool:
        keypad = self._keypad_for(top)
        shown = keypad.show_for(target, top, focus_keypad=focus_keypad)
        if shown:
            self._invalidate_focus_cache()
            self._queue_maintenance(visuals=True)
        return shown

    def _toggle_keypad(self) -> None:
        if self._active_popup() is not None or not self._onscreen_keypad_enabled:
            return
        top = self._active_top_level()
        target = self._current_keypad_target()
        if top is None or target is None:
            return
        keypad = self._keypad_for(top)
        if keypad.isVisible() and keypad._target is target:
            keypad.hide()
            self._invalidate_focus_cache()
            try:
                target.setProperty("gamepadKeypadDismissed", True)
                target.setFocus(Qt.FocusReason.OtherFocusReason)
            except (RuntimeError, TypeError):
                pass
            return
        try:
            target.setProperty("gamepadKeypadDismissed", False)
        except (RuntimeError, TypeError):
            pass
        self._show_keypad_for(target, top, focus_keypad=True)

    def _focused_keypad(self) -> GamepadKeypadOverlay | None:
        for keypad in self._keypads.values():
            if _qobject_alive(keypad) and keypad.isVisible() and keypad.owns_focus():
                return keypad
        return None

    def _active_keypad(self) -> GamepadKeypadOverlay | None:
        focused_keypad = self._focused_keypad()
        if focused_keypad is not None:
            return focused_keypad
        focused = QApplication.focusWidget()
        for keypad in self._keypads.values():
            if not (_qobject_alive(keypad) and keypad.isVisible()):
                continue
            target = keypad._target
            if not isinstance(target, QWidget) or not _qobject_alive(target):
                continue
            if focused is target:
                return keypad
            try:
                if isinstance(target, QAbstractSpinBox) and focused is target.lineEdit():
                    return keypad
            except (RuntimeError, AttributeError):
                continue
        return None

    def _focus_inside_keypad(self) -> bool:
        return self._focused_keypad() is not None

    def _hide_keypads(self) -> None:
        self._invalidate_focus_cache()
        for key, keypad in tuple(self._keypads.items()):
            if not _qobject_alive(keypad):
                self._keypads.pop(key, None)
                continue
            try:
                keypad.hide()
            except RuntimeError:
                self._keypads.pop(key, None)

    def _toggle_sidebar(self) -> None:
        if self._active_popup() is not None:
            return
        top = self._active_top_level()
        if top is None or top is not self.host:
            return
        callback = getattr(self.host, "gamepad_toggle_sidebar", None)
        if callable(callback):
            callback()
            self._queue_maintenance(normalize=True, visuals=True, focus=False)

    def _refresh_current_page(self) -> None:
        if self._active_popup() is not None:
            return
        top = self._active_top_level()
        if top is None:
            return
        scope = self._focus_scope(top)
        refresh_targets: list[QWidget] = []
        if isinstance(scope, QWidget):
            refresh_targets.append(scope)
        if isinstance(top, QWidget) and top not in refresh_targets:
            refresh_targets.append(top)
        host_page = None
        try:
            stack = getattr(self.host, "stack", None)
            current_widget = getattr(stack, "currentWidget", None)
            if callable(current_widget):
                host_page = current_widget()
        except RuntimeError:
            host_page = None
        if isinstance(host_page, QWidget) and host_page not in refresh_targets:
            refresh_targets.append(host_page)
        for target in refresh_targets:
            for method_name in ("refresh", "refresh_authorized"):
                method = getattr(target, method_name, None)
                if callable(method):
                    try:
                        method()
                    except TypeError:
                        continue
                    except RuntimeError:
                        return
                    self._queue_maintenance(visuals=True)
                    return

    @staticmethod
    def _send_key(widget: QWidget, key: Qt.Key) -> None:
        if not _qobject_alive(widget):
            return
        try:
            press = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            release = QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(widget, press)
            if _qobject_alive(widget):
                QApplication.sendEvent(widget, release)
        except (RuntimeError, TypeError):
            return

    @staticmethod
    def _safe_set_focus(widget: QWidget) -> None:
        if not _qobject_alive(widget):
            return
        try:
            widget.setFocus(Qt.FocusReason.TabFocusReason)
        except (RuntimeError, TypeError):
            return

    @staticmethod
    def _ensure_visible(widget: QWidget) -> None:
        if not _qobject_alive(widget):
            return
        try:
            parent = widget.parentWidget()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    parent.ensureWidgetVisible(widget, 24, 24)
                parent = parent.parentWidget()
        except RuntimeError:
            return

    @staticmethod
    def _scroll_nearest(widget: QWidget, direction: str, *, multiplier: float = 1.0) -> bool:
        if not _qobject_alive(widget):
            return False
        try:
            parent: QWidget | None = widget
            while parent is not None:
                if isinstance(parent, QAbstractScrollArea):
                    bar = parent.verticalScrollBar()
                    old = bar.value()
                    amount = max(bar.singleStep() * 4, max(24, bar.pageStep() // 5))
                    amount = max(1, int(amount * max(0.25, multiplier)))
                    bar.setValue(old - amount if direction == ACTION_UP else old + amount)
                    return bar.value() != old
                parent = parent.parentWidget()
        except RuntimeError:
            return False
        return False

    def _focus_changed(self, _old: QWidget | None, _new: QWidget | None) -> None:
        if self._onscreen_keypad_enabled and self._onscreen_keypad_auto_show:
            if self._focus_inside_keypad():
                self._queue_maintenance(visuals=True)
                return
            target = self._current_keypad_target()
            if target is not None:
                try:
                    if bool(target.property("gamepadKeypadDismissed")):
                        self._queue_maintenance(visuals=True)
                        return
                except (RuntimeError, TypeError):
                    return
                top = self._active_top_level()
                if top is not None:
                    self._show_keypad_for(target, top, focus_keypad=False)
            else:
                self._hide_keypads()
        self._queue_maintenance(visuals=True)

    def _refresh_visuals(self) -> None:
        self._prune_visuals()
        if not self.connected or self.profile not in {"abxy", "playstation"}:
            self._hide_visuals()
            return
        top = self._active_top_level()
        if top is None or not _qobject_alive(top) or not top.isVisible():
            self._hide_visuals()
            return
        key = id(top)
        bar = self._bars.get(key)
        if not _qobject_alive(bar):
            bar = GamepadHintBar(top)
            self._bars[key] = bar
            top.destroyed.connect(lambda _obj=None, item=key: self._bars.pop(item, None))
        try:
            bar.setToolTip(f"{tr('Controller connected')}: {self.device_name}\n{tr('Gamepad navigation active')}")
            bar.set_profile(self.profile)
            bar.set_sections_available(callable(getattr(top, "gamepad_cycle_section", None)))
            bar.set_menu_available(top is self.host and callable(getattr(self.host, "gamepad_toggle_sidebar", None)))
            bar.set_settings_available(top is self.host and callable(getattr(self.host, "gamepad_open_settings", None)))
            bar.set_keypad_available(self._onscreen_keypad_enabled and self._current_keypad_target() is not None)
            bar.set_available_width(top.width())
            bar.adjustSize()
            x = max(8, top.width() - bar.width() - 18)
            y = max(8, top.height() - bar.height() - 18)
            if bar.pos() != QPoint(x, y):
                bar.move(x, y)
            bar.show()
            bar.raise_()
        except (RuntimeError, TypeError):
            self._bars.pop(key, None)
            return
        for other_key, other_bar in tuple(self._bars.items()):
            if other_key != key and _qobject_alive(other_bar):
                try:
                    other_bar.hide()
                except RuntimeError:
                    self._bars.pop(other_key, None)
        self._position_focus_badge(top)
        # The persistent legend is informational and must remain above the
        # transient focus ring/badge if a compact layout places them nearby.
        if _qobject_alive(bar):
            try:
                bar.raise_()
            except RuntimeError:
                self._bars.pop(key, None)

    def _position_focus_badge(self, top: QWidget) -> None:
        key = id(top)
        badge = self._focus_badges.get(key)
        if not _qobject_alive(badge):
            badge = QLabel(top)
            badge.setObjectName("GamepadFocusBadge")
            badge.setProperty("gamepadOverlay", True)
            badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            badge.setFixedSize(20, 20)
            self._focus_badges[key] = badge
            top.destroyed.connect(lambda _obj=None, item=key: self._focus_badges.pop(item, None))
        focused = QApplication.focusWidget()
        if focused is None or not self._valid_action_target(focused, top):
            self._hide_focus_ring(key)
            badge.hide()
            return
        self._position_focus_ring(top, focused)
        cancel_like = self._is_cancel_widget(focused)
        if not cancel_like and not self._has_accept_action(focused):
            badge.hide()
            return
        try:
            icon_name = self._button_icon("cancel" if cancel_like else "accept")
            badge.setPixmap(QIcon(str(_ICON_DIR / f"{icon_name}.svg")).pixmap(20, 20))
            local = focused.mapTo(top, QPoint(0, 0))
            if cancel_like and local.x() >= 26:
                desired_x = local.x() - 22
            else:
                desired_x = local.x() + focused.width() - 23
            x = min(max(4, desired_x), max(4, top.width() - 24))
            y = min(max(4, local.y() + 3), max(4, top.height() - 24))
            if badge.pos() != QPoint(x, y):
                badge.move(x, y)
            badge.show()
            badge.raise_()
        except (RuntimeError, TypeError):
            badge.hide()

    def _button_icon(self, semantic: str) -> str:
        if self.profile == "playstation":
            return {
                "accept": "gamepad_ps_cross",
                "cancel": "gamepad_ps_circle",
            }.get(semantic, "gamepad_ps_cross")
        return {
            "accept": "gamepad_a",
            "cancel": "gamepad_b",
        }.get(semantic, "gamepad_a")

    def _position_focus_ring(self, top: QWidget, focused: QWidget) -> None:
        key = id(top)
        ring = self._focus_rings.get(key)
        if not _qobject_alive(ring):
            ring = GamepadFocusRing(top)
            self._focus_rings[key] = ring
            top.destroyed.connect(
                lambda _obj=None, item=key: (
                    self._focus_rings.pop(item, None),
                    self._focus_ring_animations.pop(item, None),
                )
            )
        try:
            local = focused.mapTo(top, QPoint(0, 0))
            desired = QRect(local.x() - 4, local.y() - 4, focused.width() + 8, focused.height() + 8)
            visible = desired.intersected(top.rect())
            if visible.width() < 4 or visible.height() < 4:
                ring.hide()
                return
            if not ring.isVisible():
                ring.setGeometry(visible)
            elif ring.geometry() != visible:
                animation = self._focus_ring_animations.get(key)
                if animation is None or not _qobject_alive(animation):
                    animation = QPropertyAnimation(ring, b"geometry", ring)
                    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
                    self._focus_ring_animations[key] = animation
                elif animation.state() != QPropertyAnimation.State.Stopped:
                    animation.stop()
                animation.setDuration(_FOCUS_ANIMATION_MS)
                animation.setStartValue(ring.geometry())
                animation.setEndValue(visible)
                animation.start()
            ring.show()
            ring.raise_()
        except (RuntimeError, TypeError):
            ring.hide()

    def _hide_focus_ring(self, key: int) -> None:
        ring = self._focus_rings.get(key)
        if _qobject_alive(ring):
            try:
                ring.hide()
            except RuntimeError:
                self._focus_rings.pop(key, None)

    @staticmethod
    def _has_accept_action(widget: QWidget) -> bool:
        try:
            if isinstance(widget, QAbstractItemView):
                return widget.currentIndex().isValid()
            return callable(getattr(widget, "gamepad_activate", None)) or isinstance(
                widget, (QAbstractButton, QComboBox)
            )
        except RuntimeError:
            return False

    @staticmethod
    def _is_cancel_widget(widget: QWidget) -> bool:
        try:
            if bool(widget.property("gamepadCancel")):
                return True
            object_name = widget.objectName().casefold()
            text = widget.text().casefold() if isinstance(widget, QAbstractButton) else ""
            tooltip = widget.toolTip().casefold()
        except (RuntimeError, TypeError):
            return False
        translated = tuple(tr(source).casefold() for source in ("Cancel", "Close", "Back"))
        tokens = ("cancel", "close", "back", "cerrar", "cancelar", "volver", *translated)
        return any(token and (token in object_name or token in text or token in tooltip) for token in tokens)

    def _hide_visuals(self) -> None:
        for key, bar in tuple(self._bars.items()):
            if not _qobject_alive(bar):
                self._bars.pop(key, None)
                continue
            try:
                bar.hide()
            except RuntimeError:
                self._bars.pop(key, None)
        for key, ring in tuple(self._focus_rings.items()):
            if not _qobject_alive(ring):
                self._focus_rings.pop(key, None)
                continue
            try:
                ring.hide()
            except RuntimeError:
                self._focus_rings.pop(key, None)
        for key, badge in tuple(self._focus_badges.items()):
            if not _qobject_alive(badge):
                self._focus_badges.pop(key, None)
                continue
            try:
                badge.hide()
            except RuntimeError:
                self._focus_badges.pop(key, None)

    def _prune_visuals(self) -> None:
        for key, bar in tuple(self._bars.items()):
            if not _qobject_alive(bar):
                self._bars.pop(key, None)
        for key, ring in tuple(self._focus_rings.items()):
            if not _qobject_alive(ring):
                self._focus_rings.pop(key, None)
        for key, badge in tuple(self._focus_badges.items()):
            if not _qobject_alive(badge):
                self._focus_badges.pop(key, None)

    @staticmethod
    def _safe_is_window(widget: QWidget) -> bool:
        try:
            return widget.isWindow()
        except RuntimeError:
            return False

    @staticmethod
    def _is_overlay_widget(widget: QWidget) -> bool:
        try:
            current: QWidget | None = widget
            while current is not None:
                if bool(current.property("gamepadOverlay")):
                    return True
                current = current.parentWidget()
        except RuntimeError:
            return True
        return False
