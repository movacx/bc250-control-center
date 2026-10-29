"""Fans: the desktop's four areas — by hand, automatic curve, control from boot, driver."""

from __future__ import annotations

from bc250cc.application.fan.system_control import (
    build_system_fan_policy,
    policy_digest,
    system_fan_control_owns_fan,
)
from bc250cc.domain.fan.persistence import (
    CUSTOM_FAN_PRESET,
    interpolate_fan_curve,
    normalize_fan_curve,
    normalize_fan_preset,
    validate_fan_curve_points,
)
from bc250cc.shared.contract import DESKTOP_FAN_PRESET_PERCENT
from frontends.desktop.core.dashboard_presenter import FAN_OWNER_LABELS, fan_owner

from ..content import Choice, Field, Gap, Heading, Meter, Note, Raw, Track, number
from ..i18n import tr, tr_format
from .base import Page, guarded, temperature_meter, trend

TABS = (("manual", "Manual"), ("curve", "Automatic curve"), ("boot", "Fans from the moment it boots"),
        ("driver", "PWM driver preparation"))
#: Same values as the desktop's curve presets.
CURVE_PRESETS = {
    "silent": ((45, 40), (55, 50), (65, 65), (72, 85), (78, 100)),
    "balanced": ((40, 50), (50, 60), (60, 75), (67, 90), (74, 100)),
    "aggressive": ((40, 60), (48, 70), (56, 82), (63, 92), (70, 100)),
}
MAX_POINTS = 8
LOW_DUTY_CONFIRM_PERCENT = 30
PLOT_ROWS = 9
PLOT_COLS = 48


def to_pwm(percent: int) -> int:
    return round(max(0, min(100, percent)) * 255 / 100)


def plot(points, current_temp, glyphs_ok: bool) -> list[str]:
    """The curve as a small chart: duty on the vertical axis, temperature across."""
    if not points:
        return []
    low, high = min(t for t, _s in points) - 5, max(t for t, _s in points) + 5
    dot, mark = "o", "|"
    grid = [[" "] * PLOT_COLS for _ in range(PLOT_ROWS)]
    for col in range(PLOT_COLS):
        temp = low + (high - low) * col / (PLOT_COLS - 1)
        row = PLOT_ROWS - 1 - round(interpolate_fan_curve(points, temp) / 100 * (PLOT_ROWS - 1))
        grid[row][col] = "."
    for temp, speed in points:
        col = round((temp - low) / (high - low) * (PLOT_COLS - 1))
        grid[PLOT_ROWS - 1 - round(speed / 100 * (PLOT_ROWS - 1))][col] = dot
    if current_temp is not None and low <= current_temp <= high:
        col = round((current_temp - low) / (high - low) * (PLOT_COLS - 1))
        for row in range(PLOT_ROWS):
            if grid[row][col] == " ":
                grid[row][col] = mark
    lines = []
    for index, row in enumerate(grid):
        percent = round(100 * (PLOT_ROWS - 1 - index) / (PLOT_ROWS - 1))
        lines.append(f"{percent:>3} % " + "".join(row))
    lines.append("      " + f"{low:.0f} °C".ljust(PLOT_COLS - 8) + f"{high:.0f} °C")
    return lines


class FansPage(Page):
    key = "fans"
    title = "Fans"
    interval = 2.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        service = ctx.service
        try:
            system = service.estado_control_fan_sistema()
        except Exception:
            system = {}
        config = {}
        try:
            config = ctx.settings.read_local_config()
        except Exception:
            pass
        return {"fans": service.estado_fans_bc250(), "system": system if isinstance(system, dict) else {},
                "config": config}

    # -------------------------------------------------------------- config

    @staticmethod
    def _curve(config):
        return normalize_fan_curve((config or {}).get("fan_curve"))

    def _policy(self, config, mine):
        merged = dict(config)
        if "curve" in mine:
            merged["fan_curve"] = mine["curve"]
        return build_system_fan_policy(merged)

    def _save(self, ctx, ui, payload: dict, system: dict, label: str) -> None:
        """Save fan settings, then hand the new policy to the root service when it is on."""
        def work():
            ctx.settings.save_local_config(payload)
            config = dict(ctx.page_data.get(self.key, {}).get("config") or {})
            config.update(payload)
            ctx.page_data.get(self.key, {}).update(config=config)
            if system.get("enabled"):
                policy = build_system_fan_policy(config)
                if policy is not None:
                    ctx.service.sincronizar_control_fan_sistema(policy)
            return tr("Fan curve saved") if "fan_curve" in payload and "fan_preset" not in payload else tr("Saved")

        guarded(ui, label, work)

    # ---------------------------------------------------------------- build

    def build(self, ctx, data, tab, ui):
        data = data or {}
        fans_state = data.get("fans") or {}
        sensors = fans_state.get("sensores") or {}
        rows = [row for row in sensors.get("fans") or [] if isinstance(row, dict)]
        system = data.get("system") or {}
        config = data.get("config") or {}
        mine = ctx.state(self.key)
        curve = self._curve(config)
        preset = normalize_fan_preset(config.get("fan_preset"))
        writable = [row for row in rows if row.get("pwm_root_writable") or row.get("pwm_writable")]
        if "pwm" not in mine:
            mine["pwm"] = int(curve.get("pwm") or (writable[0].get("index") if writable else 2) or 2)
        selected = next((row for row in rows if row.get("index") == mine["pwm"]), rows[0] if rows else {})

        out = self._overview(ctx, rows, selected, system, curve, preset, ui)
        tab = tab or "manual"
        if tab == "manual":
            out += self._manual(ctx, ui, mine, rows, writable, selected, system, config, curve, preset)
        elif tab == "curve":
            out += self._curve_tab(ctx, ui, mine, selected, system, config, curve)
        elif tab == "boot":
            out += self._boot(ctx, ui, mine, system, config)
        else:
            out += self._driver(ctx, ui, fans_state, sensors)
        return out

    # ------------------------------------------------------------- overview

    def _overview(self, ctx, rows, selected, system, curve, preset, ui):
        metrics = ctx.metrics or {}
        gpu, cpu = metrics.get("gpu") or {}, metrics.get("cpu") or {}
        sensors = metrics.get("sensors") or {}
        owner = fan_owner(system_owned=system_fan_control_owns_fan(system), pwm_enable=selected.get("pwm_enable"),
                          curve_enabled=bool(curve.get("enabled")), preset_enabled=bool(preset.get("enabled")),
                          external=bool(system.get("external")))
        out = [Heading(tr("Fans")),
               Field(tr("Fan controlled by"), tr(FAN_OWNER_LABELS.get(owner, owner)), "ok" if owner != "manual" else "warn")]
        if not rows:
            out.append(Note(tr("Not detected"), "warn"))
        # Unused headers (no tachometer, not the selected channel) would push the controls off screen.
        for row in (r for r in rows if r.get("rpm") or r.get("index") == selected.get("index")):
            pwm = row.get("pwm")
            try:
                duty = max(0, min(100, round(int(pwm) * 100 / 255)))
            except (TypeError, ValueError):
                duty = None
            mark = ">" if row.get("index") == selected.get("index") else " "
            out.append(Meter(f"{mark}PWM{row.get('index')} {row.get('label') or ''}".strip(),
                             None if duty is None else duty / 100.0,
                             f"{number(row.get('rpm'), 'RPM')}  {duty if duty is not None else '--'} %"))
        out += [temperature_meter("GPU", gpu.get("temperature_c")), temperature_meter("CPU", cpu.get("temperature_c")),
                temperature_meter("VRM", sensors.get("vrm_temperature_c")),
                temperature_meter(tr("Board"), sensors.get("board_temperature_c")),
                trend(ctx, tr("Temperature"), "gpu_temp", "°C", "warn"), Gap()]
        return out

    # --------------------------------------------------------------- manual

    def _manual(self, ctx, ui, mine, rows, writable, selected, system, config, curve, preset):
        service = ctx.service
        percent = mine.setdefault("percent", int(preset.get("percent") or 60) if preset.get("enabled") else 60)
        chosen_preset = mine.get("preset", preset.get("preset") if preset.get("enabled") else "")
        external = bool(system.get("external"))
        ready = bool(selected.get("pwm_root_writable") or selected.get("pwm_writable"))

        def channel(ui_, direction=1):
            options = [row.get("index") for row in (writable or rows)]
            if options:
                current = options.index(mine["pwm"]) if mine["pwm"] in options else 0
                mine["pwm"] = options[(current + direction) % len(options)]

        out = [Heading(tr("Fan speed control")),
               Choice(tr("PWM channel"), channel, f"PWM {mine['pwm']} · {selected.get('label') or ''}",
                      adjust=lambda ui_, d: channel(ui_, d))]
        for key, value in DESKTOP_FAN_PRESET_PERCENT.items():
            def pick(ui_, key=key, value=value):
                mine["preset"], mine["percent"] = key, value

            on = chosen_preset == key
            out.append(Choice(f"({'x' if on else ' '}) {tr(key.capitalize())}", pick, f"{value} %", tone="ok" if on else ""))

        def adjust(ui_, direction):
            mine["percent"] = max(0, min(100, percent + 5 * direction))
            mine["preset"] = ""

        def edit(ui_):
            value = ui_.ask_int(tr("Fan speed") + " (%)", 0, 100, percent)
            if value is not None:
                mine["percent"], mine["preset"] = value, ""

        out += [Track(tr("Fan speed"), 0, 100, 0, percent, f"{percent} %  ({tr_format('Raw PWM {raw} / 255', raw=to_pwm(percent))})",
                      "warn" if percent < LOW_DUTY_CONFIRM_PERCENT else "accent"),
                Choice(tr("Fan speed"), edit, f"< {percent} % >", adjust=adjust)]

        def apply(ui_):
            pwm, value = mine["pwm"], mine["percent"]
            if percent < LOW_DUTY_CONFIRM_PERCENT and not ui_.confirm(
                    f"{tr('Apply a low fan speed')}: PWM {pwm} · {percent} %", danger=True):
                return
            if percent >= LOW_DUTY_CONFIRM_PERCENT and not ui_.confirm(f"{tr('Apply PWM')}: PWM {pwm} · {value} %"):
                return

            def write():
                service.aplicar_pwm_fan(pwm, to_pwm(value))
                # Manual mode is what the fan does now: the curve steps aside and the speed is saved.
                curve_config = dict(curve, enabled=False)
                preset_config = {"enabled": True, "preset": mine.get("preset") or CUSTOM_FAN_PRESET,
                                 "percent": value, "pwm": pwm}
                payload = {"fan_curve": curve_config, "fan_preset": preset_config}
                ctx.settings.save_local_config(payload)
                if system.get("enabled"):
                    merged = dict(config, **payload)
                    policy = build_system_fan_policy(merged)
                    if policy is not None:
                        service.sincronizar_control_fan_sistema(policy)
                return tr_format("PWM {pwm} · {percent}%", pwm=pwm, percent=value)

            guarded(ui_, tr("Apply PWM"), write)

        def automatic(ui_):
            if ui_.confirm(f"{tr('Restore automatic mode')}: PWM {mine['pwm']}"):
                guarded(ui_, tr("Restore automatic mode"), lambda: service.restaurar_pwm_automatico(mine["pwm"]))

        out += [Choice(tr("Apply PWM"), apply, enabled=ready and not external, tone="accent"),
                Choice(tr("Restore automatic mode"), automatic, enabled=ready and not external)]
        if not ready:
            out.append(Note(tr("PWM control is not ready"), "warn"))
        if external:
            out.append(Note(tr("The fan is handed to another program. Nothing here writes to it."), "warn"))
        return out

    # ---------------------------------------------------------------- curve

    def _curve_tab(self, ctx, ui, mine, selected, system, config, saved):
        service = ctx.service
        points = mine.setdefault("points", [(int(p["temperature"]), int(p["speed"])) for p in saved.get("points") or []])
        enabled = mine.setdefault("enabled", bool(saved.get("enabled")))
        metrics = ctx.metrics or {}
        temp = (metrics.get("gpu") or {}).get("temperature_c")
        try:
            temp = float(temp)
        except (TypeError, ValueError):
            temp = None
        valid, message = validate_fan_curve_points(sorted(points))
        target = interpolate_fan_curve(sorted(points), temp) if temp is not None and points else None
        dirty = (sorted(points), enabled) != ([(int(p["temperature"]), int(p["speed"])) for p in saved.get("points") or []],
                                              bool(saved.get("enabled")))

        out = [Heading(tr("Automatic curve")),
               Field(tr("Fan curve"), tr_format("Curve with {count} points", count=len(points)), "warn" if dirty else ""),
               Field(tr("Temperature"), f"{number(temp, '°C', 1)}  →  {target} %" if target is not None else "--")]
        if not valid:
            out.append(Note(tr(message), "bad"))
        out.append(Raw(plot(sorted(points), temp, ui.unicode), "accent"))

        def toggle(ui_):
            mine["enabled"] = not enabled

        out.append(Choice(f"[{'x' if enabled else ' '}] {tr('Automatic curve')}", toggle, tone="ok" if enabled else ""))
        for name, values in CURVE_PRESETS.items():
            def preset(ui_, values=values):
                mine["points"] = list(values)
                mine["enabled"] = True

            out.append(Choice(f"{tr(name.capitalize())}", preset, " ".join(f"{t}/{s}" for t, s in values)))

        for index, (t, s) in enumerate(sorted(points)):
            def edit(ui_, index=index):
                ordered = sorted(mine["points"])
                new_t = ui_.ask_int(f"{tr('Temperature')} #{index + 1} (°C)", 20, 110, ordered[index][0])
                if new_t is None:
                    return
                new_s = ui_.ask_int(f"{tr('Fan speed')} #{index + 1} (%)", 0, 100, ordered[index][1])
                if new_s is not None:
                    ordered[index] = (new_t, new_s)
                    mine["points"] = ordered

            def nudge(ui_, direction, index=index):
                ordered = sorted(mine["points"])
                ordered[index] = (ordered[index][0], max(0, min(100, ordered[index][1] + 5 * direction)))
                mine["points"] = ordered

            out.append(Choice(f"#{index + 1}", edit, f"{t} °C → {s} %", adjust=nudge))

        def add(ui_):
            ordered = sorted(mine["points"])
            if len(ordered) < MAX_POINTS:
                last = ordered[-1] if ordered else (50, 50)
                mine["points"] = ordered + [(min(110, last[0] + 5), min(100, last[1] + 5))]

        def remove(ui_):
            ordered = sorted(mine["points"])
            if len(ordered) > 2:
                mine["points"] = ordered[:-1]

        def save(ui_):
            ordered = sorted(mine["points"])
            ok, text = validate_fan_curve_points(ordered)
            if not ok:
                ui_.notify(tr(text), "bad")
                return
            pwm = int(mine["pwm"])
            body = {"enabled": bool(mine["enabled"]), "edit_enabled": bool(mine["enabled"]), "pwm": pwm,
                    "point_count": len(ordered), "points": [{"temperature": t, "speed": s} for t, s in ordered],
                    "preset": saved.get("preset", "custom"), "last_pwm_text": saved.get("last_pwm_text", "--")}
            for number_, (t, s) in enumerate(ordered[:3], start=1):  # legacy daemon keys
                body[f"t{number_}"], body[f"s{number_}"] = t, s
            payload = {"fan_curve": body}
            if body["enabled"]:
                payload["fan_preset"] = {"enabled": False, "preset": "", "percent": 0, "pwm": pwm}
            self._save(ctx, ui_, payload, system, tr("Fan curve saved"))
            for key in ("points", "enabled"):
                mine.pop(key, None)

        def apply_now(ui_):
            if target is None:
                return
            pwm = int(mine["pwm"])
            if ui_.confirm(f"{tr('Apply curve now')}: PWM {pwm} · {target} %", danger=target < LOW_DUTY_CONFIRM_PERCENT):
                guarded(ui_, tr("Apply curve now"), lambda: service.aplicar_pwm_fan(pwm, to_pwm(target)))

        out += [Choice(tr("Add point"), add, enabled=len(points) < MAX_POINTS),
                Choice(tr("Remove point"), remove, enabled=len(points) > 2),
                Choice(tr("Save curve"), save, enabled=valid, tone="accent"),
                Choice(tr("Apply curve now"), apply_now, enabled=target is not None and not system.get("external"))]
        return out

    # ----------------------------------------------------------------- boot

    def _boot(self, ctx, ui, mine, system, config):
        service = ctx.service
        enabled = bool(system.get("enabled"))
        available = bool(system.get("available"))
        state = str(system.get("state") or "")
        status = system.get("status") if isinstance(system.get("status"), dict) else {}
        policy = build_system_fan_policy(config)
        out_of_date = bool(enabled and policy is not None and system.get("policy_digest") != policy_digest(policy))
        channel = status.get("pwm") or (system.get("policy") or {}).get("pwm")
        if system.get("external"):
            chip, tone = "Another program", "accent"
            managers = ", ".join(system.get("managers") or [])
            detail = (tr_format("{program} controls the fan. Nothing here writes to it.", program=managers) if managers
                      else tr("The fan is handed to another program. Nothing here writes to it."))
        elif not system:
            chip, tone, detail = "Checking", "dim", tr("Checking the system fan service…")
        elif not enabled and not available:
            chip, tone, detail = "Unavailable", "dim", tr("Needs the installed BC250 Control Center package and systemd or OpenRC.")
        elif not enabled:
            chip, tone, detail = "Off", "dim", tr("Only the desktop follows the curve, and only after you log in.")
        elif state == "active":
            sensor = str(status.get("sensor") or "").upper()
            temperature = status.get("temperature")
            reading = f"{sensor} {float(temperature):.1f} °C → " if temperature is not None else ""
            chip, tone, detail = "Active", "ok", f"PWM {channel} · {reading}{status.get('percent', '--')} %"
        elif state == "override":
            chip, tone = "Paused", "warn"
            detail = tr_format("PWM {channel} was changed by hand or from Quick Access. Apply the curve or a preset to resume; it resumes on its own after a reboot.", channel=channel or "--")
        elif state in ("waiting-driver", "waiting-sensor"):
            chip, tone = "Waiting", "accent"
            detail = tr("Waiting for the NCT fan driver." if state == "waiting-driver" else "Waiting for temperature sensors.")
        elif state == "error":
            chip, tone, detail = "Error", "bad", str(status.get("error") or tr("The service reported an error."))
        elif state == "idle":
            chip, tone, detail = "Idle", "dim", tr("No curve or preset to follow; the firmware drives the fan.")
        else:
            chip, tone, detail = "Stopped", "warn", tr("The service is enabled but not running. The firmware drives the fan.")
        if out_of_date and chip in ("Active", "Paused", "Waiting"):
            chip, tone = "Out of date", "warn"
            detail = tr("The service still follows an older curve or preset. Sync it to use the one on screen.")
        out = [Heading(tr("Fans from the moment it boots")), Field(tr("State"), tr(chip), tone), Note(detail, "dim")]

        def toggle(ui_):
            if enabled:
                if ui_.confirm(tr("Turn off control from boot")):
                    guarded(ui_, tr("Turn off"), service.desactivar_control_fan_sistema)
                return
            if policy is None:
                ui_.notify(tr("Choose a curve or a preset first"), "warn")
                return
            follows = (tr_format("Curve with {count} points", count=len(policy["points"])) if policy["mode"] == "curve"
                       else tr_format("Preset · {percent}%", percent=policy["percent"]))
            if ui_.confirm(f"{tr('Turn on control from boot')}\n{tr('Channel')}: PWM {policy['pwm']}\n{tr('Follows')}: {follows}"):
                guarded(ui_, tr("Turn on"), lambda: service.activar_control_fan_sistema(policy))

        def sync(ui_):
            if policy is not None:
                guarded(ui_, tr("Sync now"), lambda: service.sincronizar_control_fan_sistema(policy))

        def external(ui_):
            handing = not system.get("external")
            if ui_.confirm(tr("Hand off to another program") if handing else tr("Take control back")):
                guarded(ui_, tr("Fan control"), lambda: service.ceder_fan_a_otro_programa(handing))

        out += [Choice(tr("Turn off") if enabled else tr("Turn on"), toggle, tone="warn" if enabled else "ok",
                       enabled=(enabled or available) and not system.get("external")),
                Choice(tr("Sync now"), sync, enabled=out_of_date),
                Choice(tr("Take control back") if system.get("external") else tr("Hand off to another program"),
                       external)]
        return out

    # --------------------------------------------------------------- driver

    def _driver(self, ctx, ui, fans_state, sensors):
        service = ctx.service
        out = [Heading(tr("PWM driver preparation")),
               Field(tr("NCT chip"), str(sensors.get("chip") or tr("NCT not detected"))),
               Field("hwmon", str(sensors.get("path") or "--"))]

        def action(label, call, danger=False):
            def handler(ui_):
                if ui_.confirm(label, danger=danger):
                    guarded(ui_, label, call)
            return handler

        def raw(ui_):
            lines = [f"{k}: {v}" for k, v in fans_state.items() if k != "sensores"]
            lines += [f"{k}: {v}" for k, v in sensors.items() if k != "fans"]
            for row in sensors.get("fans") or []:
                lines.append(str(row))
            ui_.show_text(tr("Raw chip status"), "\n".join(lines))

        out += [Choice(tr("Prepare nct6687 PWM"), action(tr("Prepare nct6687 PWM"), service.preparar_nct6687_control_pwm)),
                Choice(tr("Load read-only nct6683"), action(tr("Load read-only nct6683"), service.cargar_nct6683_solo_lectura)),
                Choice(tr("Disable nct6687 PWM setup"), action(tr("Disable nct6687 PWM setup"), service.desactivar_nct6687_control_pwm, True), tone="warn"),
                Choice(tr("Raw chip status"), raw)]
        return out
