"""Channel board changes for the front ends that run them in one call.

The web interface and the terminal interface edit the same per-channel
settings the desktop Fans page edits, with the same rules
(``FansPage._apply_channel`` / ``_apply_profile`` on the desktop):

* the setting is saved through :class:`FanChannelsService` first;
* with control from boot on, the whole policy goes to the root service, after
  checking that the installed helper can follow it;
* with it off, a fixed duty or a hand-back to the firmware is written right
  away through the helper and verified from hwmon; a curve or a mix is only
  saved, and the caller is told what follows it.

Messages are English source strings; each front end translates them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bc250cc.application.fan import board_view as view
from bc250cc.application.fan.channels import ChannelBoard, FanChannelsService
from bc250cc.domain.fan.channels import BUILTIN_MODE_NAMES
from bc250cc.infrastructure.system_fan_control import build_system_fan_policy


@dataclass(frozen=True)
class Outcome:
    title: str
    message: str
    values: dict = field(default_factory=dict)
    tone: str = "blue"


class FanBoardError(ValueError):
    """A change that did not happen. ``notice`` marks a choice still to make
    (a plain notice), not a hardware failure."""

    def __init__(self, title: str, message: str, values: dict | None = None, *, notice: bool = False):
        super().__init__(message)
        self.title, self.message, self.values, self.notice = title, message, dict(values or {}), notice


def needs_low_duty_confirmation(entry: dict | None, service_enabled: bool) -> bool:
    """A fixed duty under 30 % written right now asks first, as on the desktop."""
    entry = entry or {}
    return (not service_enabled and entry.get("mode") == "fixed"
            and view.integer(entry.get("percent"), 100) < view.LOW_DUTY_CONFIRM_PERCENT)


class FanBoardActions:
    def __init__(self, service, settings):
        self.service = service
        self.settings = settings
        self.channels = FanChannelsService(settings)

    # ------------------------------------------------------------ reading

    def snapshot(self) -> dict:
        state = self.service.estado_control_fan_sistema()
        return state if isinstance(state, dict) else {}

    def fans(self) -> dict:
        state = self.service.estado_fans_bc250()
        return state if isinstance(state, dict) else {}

    def board(self) -> ChannelBoard:
        return self.channels.board()

    def _not_external(self, snapshot: dict) -> None:
        if snapshot.get("external"):
            raise FanBoardError("Fan control", view.EXTERNAL_NOTE, notice=True)

    def _sync(self) -> None:
        """The saved channels to the root service; ``None`` clears it."""
        self.service.sincronizar_control_fan_sistema(build_system_fan_policy(self.settings.read_local_config()))

    def _unsupported(self) -> FanBoardError:
        return FanBoardError(view.NOT_READY_TITLE, "Update fan helper", notice=True)

    # ------------------------------------------------------------ changes

    def apply_channel(self, pwm: int, entry: dict | None) -> Outcome:
        snapshot = self.snapshot()
        self._not_external(snapshot)
        service_on = bool(snapshot.get("enabled"))
        mode = (entry or {}).get("mode", "firmware")
        if mode == "firmware":
            entry = None
        if not service_on and mode in {"fixed", "firmware"}:
            # Written right now, through the helper: only on a header that is
            # there and writable.
            fans = self.fans()
            fan = view.fan_rows(fans).get(pwm, {})
            if not fans.get("driver_control") or not fan.get("pwm_path") or not view.is_writable(fan):
                raise FanBoardError(view.NOT_READY_TITLE, view.READ_ONLY_NOTE, notice=True)
        try:
            if service_on and not view.policy_supported(snapshot, self.channels.preview_channel(pwm, entry)):
                raise self._unsupported()
            board = self.channels.set_channel(pwm, entry)
        except FanBoardError:
            raise
        except ValueError as error:
            raise FanBoardError("Could not save fan curve", str(error)) from error
        if service_on:
            self._sync()
            return Outcome("Saved", "PWM {pwm}", {"pwm": pwm})
        if mode == "fixed":
            raw = view.percent_to_pwm(entry["percent"])
            error, values = view.verify_pwm_result(self.service.aplicar_pwm_fan(pwm, raw), pwm=pwm, raw=raw)
            if error:
                raise FanBoardError("Fan PWM operation failed", error, values)
            return Outcome("Fan speed applied", "PWM {pwm} · {percent}%", {"pwm": pwm, "percent": entry["percent"]})
        if mode == "firmware":
            error, values = view.verify_pwm_result(
                self.service.restaurar_pwm_automatico(pwm), pwm=pwm, automatic=True)
            if error:
                raise FanBoardError("Fan PWM operation failed", error, values)
            return Outcome("Automatic fan control restored", "PWM {pwm}", {"pwm": pwm})
        return Outcome("Saved", view.needs_service_notice(board.needs_root_service), tone="orange")

    def rename(self, pwm: int, label: str) -> ChannelBoard:
        return self.channels.set_label(pwm, label)

    def apply_profile(self, name: str, selected: int | None = None) -> Outcome:
        snapshot = self.snapshot()
        self._not_external(snapshot)
        rows = view.fan_rows(self.fans())
        board = self.channels.board()
        targets = view.profile_targets(rows, view.channel_numbers(rows, board.channels), selected)
        service_on = bool(snapshot.get("enabled"))
        try:
            if service_on and not view.policy_supported(snapshot, self.channels.preview_mode(name, targets)):
                raise self._unsupported()
            board = self.channels.apply_mode(name, targets)
        except FanBoardError:
            raise
        except ValueError as error:
            # A profile with nothing to drive is a choice still to make, not a
            # hardware failure: a plain notice, never the BC250-FAN-001 path.
            if not targets and not board.channels:
                raise FanBoardError("No PWM channel", "Select a detected PWM channel first.", notice=True) from error
            raise FanBoardError("Could not save fan curve", str(error), notice=True) from error
        if service_on:
            self._sync()
            return Outcome("Saved", name)
        return Outcome("Saved", view.needs_service_notice(board.needs_root_service), tone="orange")

    def profile_exists(self, name: str) -> bool:
        key = " ".join(str(name).split()).casefold()
        return any(mode["name"].casefold() == key for mode in self.channels.board().modes)

    def save_profile(self, name: str, *, channels: dict | None = None, reserved=()) -> ChannelBoard:
        """``reserved``: the built-in names as the caller shows them (their
        translations), refused like the English ones."""
        text = " ".join(str(name).split())
        if not text:
            raise FanBoardError("Could not save fan curve", "A fan mode needs a name.", notice=True)
        names = {label.casefold() for label in (*BUILTIN_MODE_NAMES.values(), *reserved)}
        if text.casefold() in names:
            raise FanBoardError("Could not save fan curve", "Reserved profile name", notice=True)
        try:
            return self.channels.save_mode(text, channels=channels)
        except ValueError as error:
            raise FanBoardError("Could not save fan curve", str(error), notice=True) from error

    def delete_profile(self, name: str) -> ChannelBoard:
        if name in BUILTIN_MODE_NAMES.values():
            raise FanBoardError("Could not save fan curve", "Reserved profile name", notice=True)
        return self.channels.delete_mode(name)
