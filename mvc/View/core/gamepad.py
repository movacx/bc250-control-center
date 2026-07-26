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

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTextEdit,
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
ACTION_CONTEXT_X = "context_x"
ACTION_CONTEXT_Y = "context_y"

_REPEATABLE_ACTIONS = {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}
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
        if value <= -0.55:
            current: str | None = negative
        elif value >= 0.55:
            current = positive
        else:
            current = None
        previous = self._axis_actions.get(axis)
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
                ecodes.BTN_WEST: ACTION_CONTEXT_X,
                ecodes.BTN_NORTH: ACTION_CONTEXT_Y,
                ecodes.BTN_TL: ACTION_PREVIOUS_SECTION,
                ecodes.BTN_TR: ACTION_NEXT_SECTION,
                getattr(ecodes, "BTN_DPAD_UP", -1): ACTION_UP,
                getattr(ecodes, "BTN_DPAD_DOWN", -1): ACTION_DOWN,
                getattr(ecodes, "BTN_DPAD_LEFT", -1): ACTION_LEFT,
                getattr(ecodes, "BTN_DPAD_RIGHT", -1): ACTION_RIGHT,
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
            }.get(number)
            return [GamepadInput(action, bool(value), f"js_button:{number}")] if action else []
        if event_type != self._AXIS:
            return []
        normalized = max(-1.0, min(1.0, float(value) / 32767.0))
        if number == 0:
            return self._axis_transition("left_x", normalized, ACTION_LEFT, ACTION_RIGHT)
        if number == 1:
            return self._axis_transition("left_y", normalized, ACTION_UP, ACTION_DOWN)
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
        self._held: dict[str, float] = {}

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
                    for input_event in backend.poll(0.05):
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
                    self._held[action] = time.monotonic() + 0.38
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
        for action, due in tuple(self._held.items()):
            if now < due:
                continue
            self.action_triggered.emit(action)
            self._held[action] = now + 0.095


class GamepadHintBar(QFrame):
    """Floating Steam-style controller legend that never affects layouts."""

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
        self._accept_text = self._add_hint(layout, "gamepad_a", "Confirm")
        self._cancel_text = self._add_hint(layout, "gamepad_b", "Back")
        sections = QLabel()
        sections.setProperty("gamepadHintText", True)
        layout.addWidget(sections)
        self._sections_label = sections
        self._sections_available = True
        self._available_width = 0
        self.retranslate()
        self.refresh_appearance()

    def _add_hint(self, layout: QHBoxLayout, icon_name: str, text: str) -> QLabel:
        icon_label = QLabel()
        icon_label.setProperty("gamepadHintIcon", True)
        icon_label.setPixmap(QIcon(str(_ICON_DIR / f"{icon_name}.svg")).pixmap(18, 18))
        layout.addWidget(icon_label)
        label = QLabel()
        label.setProperty("gamepadHintText", True)
        label.setProperty("gamepadSourceText", text)
        self._source_labels.append(label)
        layout.addWidget(label)
        return label

    def set_available_width(self, width: int) -> None:
        """Collapse optional text before the overlay can overflow a small window."""

        width = max(0, int(width))
        self._available_width = width
        self._sections_label.setVisible(self._sections_available and width >= 560)
        show_words = width >= 340
        self._accept_text.setVisible(show_words)
        self._cancel_text.setVisible(show_words)
        self.adjustSize()


    def set_sections_available(self, available: bool) -> None:
        """Show LB/RB only where the active window actually handles it."""

        self._sections_available = bool(available)
        self._sections_label.setVisible(self._sections_available and self._available_width >= 560)
        self.adjustSize()

    def retranslate(self) -> None:
        for label in self._source_labels:
            source = label.property("gamepadSourceText")
            if source:
                label.setText(tr(str(source)))
        self._sections_label.setText(f"LB/RB  {tr('Sections')}")
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
        self._focus_rings: dict[int, QFrame] = {}
        self._focus_badges: dict[int, QLabel] = {}
        self._focus_policy_records: dict[
            int, tuple[weakref.ReferenceType[QWidget], Qt.FocusPolicy, Qt.FocusPolicy]
        ] = {}
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
            self._style_focus_ring(ring)
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
            self._queue_maintenance(visuals=True)
        return False

    def _queue_maintenance(self, *, normalize: bool = False, visuals: bool = False, focus: bool = False) -> None:
        if not self.connected:
            return
        self._pending_normalize = self._pending_normalize or normalize
        self._pending_visuals = self._pending_visuals or visuals
        self._pending_focus = self._pending_focus or focus
        if not self._maintenance_timer.isActive():
            self._maintenance_timer.start()

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
        if action in _DIRECTION_KEYS:
            self._move_focus(action)
        elif action == ACTION_ACCEPT:
            self._activate_focused()
        elif action == ACTION_CANCEL:
            self._cancel_or_back()
        elif action == ACTION_PREVIOUS_SECTION:
            self._cycle_section(-1)
        elif action == ACTION_NEXT_SECTION:
            self._cycle_section(1)
        # X/Y are deliberately unbound. No arbitrary hardware action is added.

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

    def _active_popup(self) -> QWidget | None:
        app = QApplication.instance()
        if app is None:
            return None
        try:
            popup = app.activePopupWidget()
        except RuntimeError:
            return None
        return popup if isinstance(popup, QWidget) and _qobject_alive(popup) and popup.isVisible() else None

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
                if bool(widget.property("gamepadSkip")) or self._is_internal_editor(widget):
                    continue
                policy = widget.focusPolicy()
                controller_only = id(widget) in self._focus_policy_records
                if not (policy & Qt.FocusPolicy.TabFocus) and not controller_only:
                    continue
                if widget.width() < 2 or widget.height() < 2:
                    continue
                rect = self._global_rect(widget)
                if rect is None:
                    continue
                positioned.append((rect.top(), rect.left(), widget))
            except (RuntimeError, TypeError):
                continue
        positioned.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in positioned]

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
        if scope is not top:
            # Initial focus prefers the page, while movement can reach dialog
            # chrome and the main sidebar using the same spatial rules.
            candidates = self._focusable_widgets(top, top)
        if not candidates:
            return
        current = QApplication.focusWidget()
        if current is None or current not in candidates:
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

    def _handle_widget_direction(self, widget: QWidget, direction: str) -> bool:
        if isinstance(widget, QAbstractItemView):
            try:
                model = widget.model()
                current = widget.currentIndex()
                parent_index = current.parent() if current.isValid() else current
                row_count = model.rowCount(parent_index)
                column_count = model.columnCount(parent_index)
                if row_count <= 0 or column_count <= 0 or not current.isValid():
                    return False
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
        if isinstance(widget, (QSlider, QAbstractSpinBox, QComboBox)) and direction in {ACTION_LEFT, ACTION_RIGHT}:
            self._send_key(widget, _DIRECTION_KEYS[direction])
            return True
        if isinstance(widget, (QPlainTextEdit, QTextEdit)) and direction in {ACTION_UP, ACTION_DOWN}:
            return self._scroll_nearest(widget, direction)
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
    def _scroll_nearest(widget: QWidget, direction: str) -> bool:
        if not _qobject_alive(widget):
            return False
        try:
            parent: QWidget | None = widget
            while parent is not None:
                if isinstance(parent, QAbstractScrollArea):
                    bar = parent.verticalScrollBar()
                    old = bar.value()
                    amount = max(bar.singleStep() * 4, max(24, bar.pageStep() // 5))
                    bar.setValue(old - amount if direction == ACTION_UP else old + amount)
                    return bar.value() != old
                parent = parent.parentWidget()
        except RuntimeError:
            return False
        return False

    def _focus_changed(self, _old: QWidget | None, _new: QWidget | None) -> None:
        self._queue_maintenance(visuals=True)

    def _refresh_visuals(self) -> None:
        self._prune_visuals()
        if not self.connected or self.profile != "abxy":
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
            bar.set_sections_available(callable(getattr(top, "gamepad_cycle_section", None)))
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
            icon_name = "gamepad_b" if cancel_like else "gamepad_a"
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

    def _position_focus_ring(self, top: QWidget, focused: QWidget) -> None:
        key = id(top)
        ring = self._focus_rings.get(key)
        if not _qobject_alive(ring):
            ring = QFrame(top)
            ring.setObjectName("GamepadFocusRing")
            ring.setProperty("gamepadOverlay", True)
            ring.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._style_focus_ring(ring)
            self._focus_rings[key] = ring
            top.destroyed.connect(lambda _obj=None, item=key: self._focus_rings.pop(item, None))
        try:
            local = focused.mapTo(top, QPoint(0, 0))
            desired = QRect(local.x() - 2, local.y() - 2, focused.width() + 4, focused.height() + 4)
            visible = desired.intersected(top.rect())
            if visible.width() < 4 or visible.height() < 4:
                ring.hide()
                return
            ring.setGeometry(visible)
            ring.show()
            ring.raise_()
        except (RuntimeError, TypeError):
            ring.hide()

    @staticmethod
    def _style_focus_ring(ring: QFrame) -> None:
        ring.setStyleSheet(
            "QFrame#GamepadFocusRing {"
            f"background:transparent; border:2px solid {COLORS['focus']}; border-radius:7px;"
            "}"
        )

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
