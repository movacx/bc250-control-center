"""Fans: the desktop's channel board — every header with its own setting,
named profiles, control from boot and the PWM driver.

The rows, states, notices and rules come from the shared fan board
(``bc250cc.application.fan.board_view`` / ``board_actions``), the same ones
the desktop Fans page and the web interface use.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bc250cc.application.fan import board_view as view
from bc250cc.application.fan.board_actions import (
    FanBoardActions,
    FanBoardError,
    needs_low_duty_confirmation,
)
from bc250cc.application.fan.calibration import CalibrationResult, calibrate
from bc250cc.application.fan.calibration_io import hottest_temperature, read_int
from bc250cc.application.fan.system_control import (
    build_system_fan_policy,
    policy_overview,
)
from bc250cc.domain.fan import engine
from bc250cc.domain.fan.channels import BUILTIN_MODE_NAMES
from bc250cc.domain.fan.profile_exchange import (
    MAX_DOCUMENT_BYTES,
    channel_profiles_document,
    imported_profile_updates,
    parse_channel_profiles_document,
)

from ..content import (
    Buttons,
    Choice,
    Field,
    Heading,
    Note,
    Pad,
    PadCell,
    PadRow,
    Panel,
    Spans,
    Split,
    number,
)
from ..i18n import tr, tr_format
from ..runtime import describe_error
from .base import Page, guarded

TABS = (("channels", "Channels"), ("boot", "Control from boot"), ("driver", "Driver"))
MODES = tuple(key for key, _label in view.MODE_LABELS)
SOURCES = tuple(key for key, _label in view.SOURCE_LABELS)
TONES = {"green": "ok", "orange": "warn", "red": "bad", "blue": "accent", "": "dim"}
ADVANCED = (("min_percent", "Minimum PWM", 0, 100), ("max_percent", "Maximum PWM", 0, 100),
            ("start_percent", "Spin-up kick", 0, 100))
MAX_POINTS = engine.CURVE_MAX_POINTS
PLOT_ROWS = 9
BRAILLE = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
PLOT_COLS = 38  # with the axis labels, 50 columns: an 80x24 terminal's content


def say(template: str, values: dict | None = None) -> str:
    return tr_format(template, **values) if values else tr(template)


def plot(points, current_temp, *, unicode: bool = True, chosen: int = -1) -> list[list[tuple[str, str]]]:
    """The curve over a faint grid: duty up, temperature across, its points marked and the reading now."""
    if not points:
        return []
    points = sorted([int(t), int(s)] for t, s in points)
    low, high = min(20, points[0][0] - 5) // 10 * 10, -(-max(90, points[-1][0] + 5) // 10) * 10
    dots_x, dots_y = (2, 4) if unicode else (1, 1)
    width, height = PLOT_COLS, PLOT_ROWS
    masks = [[0] * width for _ in range(height)]

    def column(temp: float, scale: int = 1) -> int:
        return round((temp - low) / (high - low) * (width * scale - 1))

    def line(duty: float, scale: int = 1) -> int:
        return height * scale - 1 - round(duty / 100 * (height * scale - 1))

    previous = None
    for x in range(width * dots_x):
        y = line(engine.interpolate(points, low + (high - low) * x / (width * dots_x - 1)), dots_y)
        for step in range(min(y, previous if previous is not None else y), max(y, previous if previous is not None else y) + 1):
            masks[step // dots_y][x // dots_x] |= BRAILLE[step % 4][x % 2] if unicode else 1
        previous = y
    now = column(current_temp) if current_temp is not None and low <= current_temp <= high else None
    marks = {(line(s), column(t)): index for index, (t, s) in enumerate(points)}
    every = {column(temp): temp for temp in range(low, high + 1, 10)}
    rows = []
    for y in range(height):
        duty = round(100 * (height - 1 - y) / (height - 1))
        spans = [(f"{duty:>3} % " if y % 2 == 0 else "      ", "dim"), ("│" if unicode else "|", "edge")]
        for x in range(width):
            if (y, x) in marks:
                picked = marks[y, x] == chosen
                cell = ("●" if unicode else "o", "warn!" if picked else "accent!")
            elif masks[y][x]:
                cell = (chr(0x2800 + masks[y][x]) if unicode else ".", "accent")
            elif x == now:
                cell = ("┊" if unicode else "|", "ok")
            elif y % 2 == 0 and x % 2 == 0:
                cell = ("·" if unicode else " ", "edge")
            else:
                cell = (" ", "")
            if spans[-1][1] == cell[1] and len(spans) > 2:
                spans[-1] = (spans[-1][0] + cell[0], cell[1])
            else:
                spans.append(cell)
        rows.append(spans)
    rows.append([("      ", ""), (("└" if unicode else "+") + ("─" if unicode else "-") * width, "edge")])
    axis = [" "] * (width + 4)
    for x, temp in every.items():
        text = str(temp)
        start = max(0, min(width - len(text) + 2, x - len(text) // 2 + 1))
        axis[start:start + len(text)] = text
    rows.append([("      ", ""), ("".join(axis).rstrip() + " °C", "dim")])
    if now is not None:
        rows.append([("       ", ""), (tr("Now") + " ", "dim"), (number(current_temp, "°C", 1), "ok"),
                     (" → " if unicode else " > ", "dim"), (f"{round(engine.interpolate(points, current_temp))} %", "accent!")])
    return rows


def with_mode(entry: dict, mode: str) -> dict:
    """A setting turned into another mode, keeping what it can (the desktop editor's entry())."""
    if mode == "firmware":
        return {"mode": "firmware"}
    role = entry.get("role", "fan")
    pump = role == "pump"
    curve = entry.get("points") or ((entry.get("mix") or [{}])[0].get("points")) or view.DEFAULT_CURVE
    if mode == "fixed":
        return {"mode": "fixed", "role": role, "percent": int(entry.get("percent", 90 if pump else 60)),
                "preset": "", "stall_detect": entry.get("stall_detect", True)}
    base = {"mode": mode, "role": role, "stall_detect": entry.get("stall_detect", True)}
    for key, *_rest in ADVANCED:
        if key in entry:
            base[key] = entry[key]
    if pump and int(base.get("min_percent", 0)) < engine.PUMP_FLOOR_PERCENT:
        base["min_percent"] = engine.PUMP_DEFAULT_MIN_PERCENT
    if mode == "curve":
        return {**base, "source": entry.get("source", "hottest"), "points": [list(p) for p in curve]}
    return {**base, "mix": entry.get("mix") or [{"source": "gpu", "points": curve}, {"source": "vrm", "points": curve}]}


def validation_error(pwm: int, entry: dict) -> str:
    if entry.get("mode") == "firmware":
        return ""
    try:
        engine.validate_policy({"schema": 2, "channels": {str(pwm): entry}})
    except ValueError as error:
        return tr(str(error))
    return ""


def normalized(pwm: int, entry: dict) -> dict:
    if entry.get("mode", "firmware") == "firmware":
        return {"mode": "firmware"}
    try:
        return engine.validate_policy({"schema": 2, "channels": {str(pwm): entry}})["channels"][str(pwm)]
    except ValueError:
        return dict(entry)


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

    # ------------------------------------------------------------- changes

    def _run(self, ctx, ui, label: str, work) -> bool:
        """Run one board change; afterwards the page shows the saved config at once."""
        def done():
            result = work()
            try:
                config = ctx.settings.read_local_config()
                ctx.page_data.get(self.key, {}).update(config=config)
            except Exception:
                pass
            return result

        ok, result = ui.run(label, done)
        if isinstance(result, FanBoardError):
            ui.notify(describe_error(result), "warn" if result.notice else "bad")
        elif isinstance(result, BaseException):
            ui.notify(describe_error(result), "bad")
        elif ok:
            ui.notify(result or tr("Done"), "ok")
        ui.refresh()
        return bool(ok)

    @staticmethod
    def _outcome(outcome) -> str:
        return f"{tr(outcome.title)} · {say(outcome.message, outcome.values)}"

    # ---------------------------------------------------------------- build

    def build(self, ctx, data, tab, ui):
        data = data or {}
        fans_state = data.get("fans") or {}
        system = data.get("system") or {}
        config = data.get("config") or {}
        board = view.board_from_config(config)
        rows = view.board_rows(board, fans_state, system)
        mine = ctx.state(self.key)
        tab = tab or "channels"
        if tab == "channels":
            return self._channels(ctx, ui, mine, board, rows, fans_state, system, config)
        if tab == "boot":
            return self._boot(ctx, ui, system, config, rows)
        return self._driver(ctx, ui, fans_state, (fans_state.get("sensores") or {}))

    # ------------------------------------------------------------ channels

    def _channels(self, ctx, ui, mine, board, rows, fans_state, system, config):
        """The desktop's Fans page for a terminal: the channel table with the
        editor beside it (below it on a narrow terminal), keyboard first.

        Arrows move through the table, Enter opens a channel; Mode, Function
        and Follows change with left/right; the curve's points are a grid
        (arrows to move, Enter to type a value); Apply sends the draft.
        """
        actions = FanBoardActions(ctx.service, ctx.settings)
        external = bool(system.get("external"))
        sensors = fans_state.get("sensores") or {}
        if not rows:
            return [Note(tr("Waiting for data…"), "dim")]
        by_pwm = {row["pwm"]: row for row in rows}
        if mine.get("pwm") not in by_pwm:
            mine["pwm"] = next((row["pwm"] for row in rows if row["detected"]), rows[0]["pwm"])
            mine.pop("draft", None)
        row = by_pwm[mine["pwm"]]
        saved = row["entry"]
        draft = mine.get("draft") or dict(saved)
        dirty = normalized(row["pwm"], draft) != normalized(row["pwm"], saved)

        def apply(ui_) -> bool:
            entry = draft if draft.get("mode") != "firmware" else None
            low = needs_low_duty_confirmation(entry, bool(system.get("enabled")))
            title = tr("Apply a low fan speed") if low else tr("Apply")
            detail = f"PWM {row['pwm']} · {tr(dict(view.MODE_LABELS)[draft.get('mode', 'firmware')])}"
            if draft.get("mode") == "fixed":
                detail += f" · {draft['percent']} %"
            if low:
                detail += f"\n{tr('A fan this slow can let the board overheat under load.')}"
            if not ui_.confirm(f"{title}: {detail}", danger=low):
                return False
            if self._run(ctx, ui_, title, lambda: self._outcome(actions.apply_channel(row["pwm"], entry))):
                mine.pop("draft", None)
                return True
            return False

        def open_channel(ui_, pwm: int) -> None:
            if pwm == mine["pwm"]:
                return
            if dirty:
                answer = ui_.choose(f"{tr('Unapplied changes')}: {tr('The changes to this fan were not applied.')}",
                                    [("apply", tr("Apply")), ("discard", tr("Discard")), ("cancel", tr("Cancel"))])
                if answer in (None, "cancel"):
                    mine["cursor"] = (rows.index(row), 0)
                    return
                if answer == "apply" and not apply(ui_):
                    return
            mine["pwm"] = pwm
            mine.pop("draft", None)

        out = [self._header(ctx, ui, mine, board, row, draft, dirty, actions, system, config)]
        driver = ""
        if fans_state and not sensors.get("chip"):
            driver = "No NCT fan controller was found. Prepare the PWM driver to read and control the fans."
        elif fans_state and not view.control_available(fans_state):
            driver = "The fans are shown read-only. Prepare the nct6687 PWM driver to control them."
        narrow = hasattr(ui, "size") and ui.size()[1] < 110
        table = self._table(ctx, mine, rows, row, dirty, open_channel, sensors, driver, narrow)
        editor = self._editor(ctx, ui, mine, row, draft, dirty, apply, actions, external, system)
        return out + table + editor

    def _header(self, ctx, ui, mine, board, row, draft, dirty, actions, system, config):
        """Profile, control from boot and the service line: the desktop's top bar."""
        external = bool(system.get("external"))
        builtin = list(BUILTIN_MODE_NAMES.values())
        saved = [mode["name"] for mode in board.modes]
        current = board.active_mode or ("Custom" if board.channels else "Balanced")
        policy = build_system_fan_policy(config)
        template, values, tone = view.service_summary(system, policy)
        enabled = bool(system.get("enabled"))

        def apply_profile(ui_):
            options = [(name, tr(name)) for name in builtin] + [(name, name) for name in saved]
            name = ui_.choose(tr("Apply profile"), options)
            if not name:
                return
            question = f"{tr('Apply profile')}: {tr(name)}"
            if dirty:
                question += f"\n{tr('The changes to this fan were not applied.')}"
            if not ui_.confirm(question):
                return
            if self._run(ctx, ui_, tr("Apply profile"), lambda: self._outcome(actions.apply_profile(name, row["pwm"]))):
                mine.pop("draft", None)

        def save_profile(ui_):
            name = " ".join((ui_.ask_text(tr("Profile"), "") or "").split())
            if not name:
                return
            if name.casefold() in {item.casefold() for item in saved} and not ui_.confirm(tr("Replace fan profile?")):
                return
            channels = None
            if dirty:
                error = validation_error(row["pwm"], draft)
                if error:
                    ui_.notify(error, "bad")
                    return
                channels = dict(board.channels)
                if draft.get("mode") == "firmware":
                    channels.pop(str(row["pwm"]), None)
                else:
                    channels[str(row["pwm"])] = draft
            reserved = [tr(label) for label in builtin]
            self._run(ctx, ui_, tr("Save as…"), lambda: (
                actions.save_profile(name, channels=channels, reserved=reserved), f"{tr('Saved')} · {name}")[1])

        def delete_profile(ui_):
            name = ui_.choose(tr("Delete"), [(item, item) for item in saved])
            if name and ui_.confirm(f"{tr('Delete')}: {name}"):
                self._run(ctx, ui_, tr("Delete"), lambda: (actions.delete_profile(name), tr("Saved"))[1])

        def boot(ui_):
            service = ctx.service
            if enabled:
                if ui_.confirm(tr("Turn off control from boot")):
                    guarded(ui_, tr("Turn off"), service.desactivar_control_fan_sistema)
                return
            if policy is None:
                ui_.notify(tr("Choose a curve or a preset first"), "warn")
                return
            if not view.policy_supported(system, policy):
                ui_.notify(f"{tr(view.NOT_READY_TITLE)}: {tr('Update fan helper')}", "warn")
                return
            overview = policy_overview(policy)
            if ui_.confirm(f"{tr('Turn on control from boot')}\n{tr('Channel')}: {overview['channels_text']}"):
                guarded(ui_, tr("Turn on"), lambda: service.activar_control_fan_sistema(policy))

        rows = [Choice(tr("Profile"), apply_profile, f"{tr(current)} ›", enabled=not external),
                Choice(tr("Control from boot"), boot, tr("Enabled") if enabled else tr("Disabled"),
                       enabled=(enabled or bool(system.get("available"))) and not external, tone="ok" if enabled else "")]
        def export(ui_):
            path = ui_.ask_text(tr("Export fan profiles"), str(Path.home() / "bc250-fan-profiles.json"))
            if path:
                document = channel_profiles_document(list(config.get("fan_profiles") or []), config)
                ok, _result = ui_.run(tr("Export fan profiles"), lambda: Path(path).expanduser().write_text(
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"))
                ui_.notify(tr("Saved") if ok else tr("Could not export fan profiles"), "ok" if ok else "bad")

        def bring_in(ui_):
            path = ui_.ask_text(tr("Import fan profiles"), str(Path.home() / "bc250-fan-profiles.json"))
            if not path:
                return

            def work():
                source = Path(path).expanduser()
                if source.stat().st_size > MAX_DOCUMENT_BYTES:
                    raise ValueError("This file is not a BC250 fan profile export.")
                bundle = parse_channel_profiles_document(json.loads(source.read_text(encoding="utf-8")))
                ctx.settings.save_local_config(imported_profile_updates(
                    ctx.settings.read_local_config(), bundle, snapshot_name=source.stem[:24]))
                return tr("Fan profiles imported")

            self._run(ctx, ui_, tr("Import fan profiles"), work)

        buttons = [Choice(tr("Save as…"), save_profile, enabled=not external),
                   Choice(tr("Export to a file…"), export), Choice(tr("Import from a file…"), bring_in, enabled=not external)]
        if saved:
            buttons.append(Choice(tr("Delete"), delete_profile, enabled=not external))
        return Panel(tr("Fans"), [*rows, Buttons(buttons), Note(say(template, values), TONES.get(tone, "dim"))], wide=True)

    def _table(self, ctx, mine, rows, row, dirty, open_channel, sensors, driver, narrow=False):
        """Every header as one row of a grid: arrows move, Enter opens it."""
        count = len(rows)
        cursor = tuple(mine.get("cursor") or (rows.index(row), 0))
        if cursor[0] >= count:
            cursor = (rows.index(row), 0)

        def move(dr, dc):
            r = cursor[0] + dr
            if dc or not 0 <= r < count:
                return False  # sideways or past the ends: leave the table
            mine["cursor"] = (r, 0)
            if not dirty:  # nothing to lose: the editor follows the cursor
                mine["pwm"] = rows[r]["pwm"]
                mine.pop("draft", None)
            return True

        def toggle(ui_):
            r = (mine.get("cursor") or cursor)[0]
            open_channel(ui_, rows[r]["pwm"])

        # A narrow terminal keeps what changes: the mode, the output and the speed.
        shown = (1, 4, 5) if narrow else (0, 1, 2, 3, 4, 5)
        heads = ["BIOS", tr("Mode"), tr("Follows"), "°C", tr("PWM %"), "RPM"]
        pad_rows = []
        for item in rows:
            mode = tr(item["mode_label"]) + (f" · {tr('Pump')}" if item["role"] == "pump" and item["mode"] != "firmware" else "")
            temperature = f"{item['temperature']:.1f}" if item["temperature"] is not None else "—"
            mark = ">" if item["pwm"] == row["pwm"] else " "
            cells = [
                PadCell(str(item["bios"] or "—")),
                PadCell(mode, "accent" if item["mode"] != "firmware" else ""),
                PadCell(say(item["follows"], item["follows_values"]) if item["mode"] != "firmware" else "—"),
                PadCell(temperature),
                PadCell(str(item["duty"]) if item["duty"] is not None else "—"),
                PadCell(str(item["rpm"]) if item["rpm"] is not None else "—", "ok" if (item["rpm"] or 0) > 0 else "dim"),
            ]
            pad_rows.append(PadRow(f"{mark} {item['label'] or item['short_header']}", [cells[i] for i in shown],
                                   say(item["state"]), TONES.get(item["tone"], "dim")))
        counts = [tr_format("{count} channels", count=count),
                  tr_format("{count} turning", count=sum(1 for r in rows if (r["rpm"] or 0) > 0)),
                  tr_format("{count} controlled", count=sum(1 for r in rows if r["mode"] != "firmware"))]
        if sensors.get("chip"):
            counts.append(str(sensors["chip"]))
        metrics = ctx.metrics or {}
        gpu, cpu, now = metrics.get("gpu") or {}, metrics.get("cpu") or {}, metrics.get("sensors") or {}
        readings = " · ".join(f"{name} {number(value, '°C', 1)}" for name, value in (
            ("GPU", gpu.get("temperature_c")), ("CPU", cpu.get("temperature_c")),
            ("VRM", now.get("vrm_temperature_c")), (tr("Board"), now.get("board_temperature_c"))))
        blocks = [Pad([heads[i] for i in shown], pad_rows, cursor, move, toggle,
                      tr("State"), place=lambda r, c: mine.update(cursor=(r, 0)), corner=tr("Fan"))]
        if driver:
            blocks.append(Note(tr(driver), "warn"))
        blocks += [Note(" · ".join(counts), "dim"), Note(readings, "dim")]
        return [Panel(tr("Channels"), blocks)]

    def _editor(self, ctx, ui, mine, row, draft, dirty, apply, actions, external, system):
        pwm = row["pwm"]
        mode = draft.get("mode", "firmware")
        curve: list = []
        bios = view.bios_number(pwm)
        identity = f"PWM {pwm} · {row['header']}" + (f" · {tr_format('BIOS Fan {number}', number=bios)}" if bios else "")
        live = f"{number(row['rpm'], 'RPM')} · {row['duty'] if row['duty'] is not None else '--'} %"
        title = row["label"] or row["header"]
        if external:
            return [Panel(title, [Note(tr(view.EXTERNAL_NOTE), "warn")], subtitle=identity)]

        def set_draft(**changes):
            mine["draft"] = {**draft, **changes}

        def rename(ui_):
            text = ui_.ask_text(tr("Name this fan"), row["label"])
            if text is None:
                return
            label = " ".join(text.split())
            if label != row["label"]:
                self._run(ctx, ui_, tr("Name"), lambda: (actions.rename(pwm, label), tr("Saved"))[1])

        def cycle(options, current, key):
            def adjust(ui_, direction=1):
                index = options.index(current) if current in options else 0
                set_draft(**{key: options[(index + direction) % len(options)]})
            return adjust

        def cycle_mode(ui_, direction=1):
            mine["draft"] = with_mode(draft, MODES[(MODES.index(mode) + direction) % len(MODES)])

        def pick_mode(ui_):
            chosen = ui_.choose(tr("Mode"), [(key, tr(label)) for key, label in view.MODE_LABELS])
            if chosen:
                mine["draft"] = with_mode(draft, chosen)

        blocks = [Choice(tr("Name"), rename, row["label"] or "—"),
                  Choice(tr("Mode"), pick_mode, f"< {tr(dict(view.MODE_LABELS)[mode])} >", adjust=cycle_mode, tone="accent")]
        if mode == "firmware":
            blocks.append(Note(tr("The BIOS fan curve drives this header. BC250 Control Center does not write to it."), "dim"))
        else:
            def toggle_role(ui_, _direction=1):
                role = "fan" if draft.get("role", "fan") == "pump" else "pump"
                changes = {"role": role}
                if role == "pump" and mode == "fixed" and int(draft.get("percent", 0)) < engine.PUMP_FLOOR_PERCENT:
                    changes["percent"] = engine.PUMP_FLOOR_PERCENT
                if role == "pump" and mode != "fixed" and int(draft.get("min_percent", 0)) < engine.PUMP_FLOOR_PERCENT:
                    changes["min_percent"] = engine.PUMP_DEFAULT_MIN_PERCENT
                set_draft(**changes)

            blocks.append(Choice(tr("Function"), toggle_role,
                                 f"< {tr(dict(view.ROLE_LABELS)[draft.get('role', 'fan')])} >", adjust=toggle_role))
        floor = engine.PUMP_FLOOR_PERCENT if draft.get("role") == "pump" else 0
        if mode == "fixed":
            percent = int(draft.get("percent", 60))

            def edit_speed(ui_):
                value = ui_.ask_int(tr("Speed") + " (%)", floor, 100, percent)
                if value is not None:
                    set_draft(percent=value)

            blocks.append(Choice(tr("Speed"), edit_speed,
                                 f"< {percent} % >  " + tr_format("Raw PWM {raw} / 255", raw=view.percent_to_pwm(percent)),
                                 adjust=lambda ui_, d: set_draft(percent=max(floor, min(100, percent + 5 * d))),
                                 tone="warn" if percent < view.LOW_DUTY_CONFIRM_PERCENT else ""))
        elif mode == "curve":
            source = draft.get("source", "hottest")
            blocks.append(Choice(tr("Follows"), cycle(SOURCES, source, "source"),
                                 f"< {tr(dict(view.SOURCE_LABELS)[source])} >", adjust=cycle(SOURCES, source, "source")))
            temperature = row["temperature"]
            if temperature is None:
                temperature = view.finite_number(((ctx.metrics or {}).get("gpu") or {}).get("temperature_c"))
            curve = [Spans(plot(draft.get("points") or [], temperature, unicode=getattr(ui, "unicode", True),
                                chosen=(mine.get("point_cursor") or (0, 0))[0])), *self._points(mine, draft, set_draft)]
        elif mode == "mix":
            blocks.append(Note(tr("The fan takes the highest PWM of these curves, each on its own sensor."), "dim"))
            for index, member in enumerate(draft.get("mix") or []):
                def cycle_source(ui_, d=1, index=index):
                    members = [dict(item) for item in draft.get("mix") or []]
                    current = members[index]["source"]
                    members[index]["source"] = SOURCES[(SOURCES.index(current) + d) % len(SOURCES)]
                    set_draft(mix=members)

                blocks.append(Choice(f"#{index + 1} {tr('Follows')}", cycle_source,
                                     f"< {tr(dict(view.SOURCE_LABELS)[member['source']])} >  "
                                     + " ".join(f"{t}/{s}" for t, s in member["points"]), adjust=cycle_source))
        if mode != "firmware":
            shown = bool(mine.get("advanced"))
            blocks.append(Choice(f"{'-' if shown else '+'} {tr('Advanced')}",
                                 lambda ui_: mine.update(advanced=not shown)))
            if shown:
                if mode in ("curve", "mix"):
                    for key, label, low, high in ADVANCED:
                        value = int(draft.get(key, engine.PUMP_DEFAULT_MIN_PERCENT if key == "min_percent" and floor else
                                              100 if key == "max_percent" else 0))
                        low = max(low, floor) if key == "min_percent" else low

                        def edit(ui_, key=key, label=label, low=low, high=high, value=value):
                            number_ = ui_.ask_int(tr(label) + " (%)", low, high, value)
                            if number_ is not None:
                                set_draft(**{key: number_})

                        blocks.append(Choice(f"  {tr(label)}", edit, f"< {value} % >",
                                             adjust=lambda ui_, d, key=key, low=low, high=high, value=value:
                                             set_draft(**{key: max(low, min(high, value + 5 * d))})))
                stall = bool(draft.get("stall_detect", True))
                blocks.append(Choice(f"  [{'x' if stall else ' '}] {tr('Warn when the fan stops while it should turn')}",
                                     lambda ui_: set_draft(stall_detect=not stall)))
        def calibrate_fan(ui_):
            question = tr("The fan goes to full speed, then down step by step until it stops, then up until it starts "
                          "again. It takes one to two minutes and stops at once if the board reaches 80 °C. "
                          "It ends at full speed; nothing is saved until you press Apply.")
            if not ui_.confirm(f"{tr('Calibrate this fan')}: {question}", danger=True):
                return
            ok, result = ui_.run(tr("Calibrate this fan"), lambda: self._calibrate(ctx, ui_, pwm))
            if not ok or not isinstance(result, CalibrationResult):
                return
            if result.aborted:
                ui_.notify(tr(result.aborted), "warn")
                return
            mine["draft"] = {**draft, "min_percent": result.proposed_min, "start_percent": result.proposed_start}
            mine["advanced"] = True
            ui_.notify(tr_format("Keeps turning down to {stop}, starts at {start}. Review the proposal and press Apply.",
                                 stop="--" if result.stop_percent is None else f"{result.stop_percent} %",
                                 start="--" if result.start_percent is None else f"{result.start_percent} %"), "ok")

        if mode in ("curve", "mix"):
            blocks.append(Choice(tr("Calibrate") + " ›", calibrate_fan, enabled=bool(row["writable"]) and not floor))
        error = validation_error(pwm, draft)
        if error:
            blocks.append(Note(error, "bad"))
        if not row["writable"] and not system.get("enabled") and mode in ("fixed", "firmware"):
            blocks.append(Note(tr(view.READ_ONLY_NOTE), "warn"))
        elif not system.get("enabled") and mode in ("curve", "mix"):
            blocks.append(Note(tr("Curves are followed by control from boot. Without it, only the desktop follows one curve, after you log in."), "dim"))
        actions_row = Buttons([Choice(tr("Revert"), lambda ui_: mine.pop("draft", None), enabled=dirty),
                               Choice(tr("Apply"), apply, enabled=dirty and not error, tone="primary")])
        badge = tr("Unapplied changes") if dirty else live
        # The form beside its curve (as the desktop's editor), stacked on a narrow terminal.
        body = [Split(blocks, curve, ratio=0.44, minimum=96)] if curve else blocks
        return [Panel(title, [*body, actions_row], subtitle=identity, badge=badge,
                      badge_tone="warn" if dirty else "dim")]

    @staticmethod
    def _calibrate(ctx, ui, pwm: int):
        """Measure where the fan stops and starts; runs in the console, Ctrl+C ends it at full speed."""
        service, console = ctx.service, getattr(ui, "job", None)
        hwmon = str((service.estado_fans_bc250().get("sensores") or {}).get("path") or "")
        if not hwmon:
            raise RuntimeError(tr("This channel is read-only until the PWM driver is prepared."))

        def cancelled() -> bool:
            return bool(console is not None and console.interrupted)

        def write(percent: int) -> None:
            raw = view.percent_to_pwm(percent)
            template, values = view.verify_pwm_result(service.aplicar_pwm_fan(pwm, raw), pwm=pwm, raw=raw)
            if template:
                raise RuntimeError(say(template, values))
            print(f"PWM {percent:>3} %", flush=True)

        def sleep(seconds: float) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end and not cancelled():
                time.sleep(0.1)

        return calibrate(write=write, read_rpm=lambda: read_int(Path(hwmon) / f"fan{pwm}_input"),
                         hottest_c=hottest_temperature, sleep=sleep, cancelled=cancelled)

    @staticmethod
    def _points(mine, draft, set_draft):
        """The curve's points as a grid: arrows move, Enter types the value."""
        points = sorted([int(t), int(s)] for t, s in draft.get("points") or [])
        if not points:
            return []
        r, c = mine.get("point_cursor") or (0, 0)
        r, c = min(r, len(points) - 1), min(c, 1)

        def move(dr, dc):
            nr, nc = r + dr, c + dc
            if 0 <= nr < len(points) and 0 <= nc <= 1:
                mine["point_cursor"] = (nr, nc)
                return True
            return False

        def edit(ui_):
            low, high = (20, 110) if c == 0 else (0, 100)
            label = tr("Temperature") + " (°C)" if c == 0 else tr("PWM duty") + " (%)"
            value = ui_.ask_int(f"#{r + 1} {label}", low, high, points[r][c])
            if value is not None:
                changed = [list(p) for p in points]
                changed[r][c] = value
                set_draft(points=sorted(changed))

        def add(ui_):
            # After the chosen point: halfway to the next one, or a little past the last.
            here = points[r]
            after = points[r + 1] if r + 1 < len(points) else [min(110, here[0] + 10), min(100, here[1] + 10)]
            new = [(here[0] + after[0]) // 2, (here[1] + after[1]) // 2]
            if new[0] not in [t for t, _s in points]:
                set_draft(points=sorted(points + [new]))

        rows = [PadRow(f"#{index + 1}", [PadCell(f"{t} °C"), PadCell(f"{s} %")]) for index, (t, s) in enumerate(points)]
        return [Pad([tr("Temperature"), tr("PWM %")], rows, (r, c), move, edit,
                    place=lambda rr, cc: mine.update(point_cursor=(rr, cc))),
                Buttons([Choice(tr("Add point"), add, enabled=len(points) < MAX_POINTS),
                         Choice(tr("Remove point"), lambda ui_: set_draft(points=points[:r] + points[r + 1:]),
                                enabled=len(points) > engine.CURVE_MIN_POINTS)])]

    # ----------------------------------------------------------------- boot

    def _boot(self, ctx, ui, system, config, rows):
        service = ctx.service
        enabled = bool(system.get("enabled"))
        available = bool(system.get("available"))
        state = str(system.get("state") or "")
        policy = build_system_fan_policy(config)
        out_of_date = view.service_out_of_date(system, policy)
        template, values, tone = view.service_summary(system, policy)
        out = [Heading(tr("Control from boot")),
               Field(tr("State"), tr("Enabled") if enabled else tr("Disabled"), "ok" if enabled else "dim"),
               Note(say(template, values), TONES.get(tone, "dim"))]
        for row in rows:
            if row["mode"] == "firmware" and not row["fault"]:
                continue
            reading = f"{row['temperature']:.1f} °C → " if row["temperature"] is not None else ""
            target = f"{row['target']} %" if row["target"] is not None else "--"
            value = f"{reading}{target} · {say(row['state'])}"
            out.append(Field(f"PWM {row['pwm']} {row['label']}".strip(), value, TONES.get(row["tone"], "dim")))

        def toggle(ui_):
            if enabled:
                if ui_.confirm(tr("Turn off control from boot")):
                    guarded(ui_, tr("Turn off"), service.desactivar_control_fan_sistema)
                return
            if policy is None:
                ui_.notify(tr("Choose a curve or a preset first"), "warn")
                return
            if not view.policy_supported(system, policy):
                ui_.notify(f"{tr(view.NOT_READY_TITLE)}: {tr('Update fan helper')}", "warn")
                return
            overview = policy_overview(policy)
            follows = (tr_format("Curve with {count} points", count=overview["points"]) if overview["mode"] in ("curve", "mix")
                       else tr_format("Preset · {percent}%", percent=overview["percent"]))
            if ui_.confirm(f"{tr('Turn on control from boot')}\n{tr('Channel')}: {overview['channels_text']}\n{tr('Follows')}: {follows}"):
                guarded(ui_, tr("Turn on"), lambda: service.activar_control_fan_sistema(policy))

        def sync(ui_):
            if not view.policy_supported(system, policy):
                ui_.notify(f"{tr(view.NOT_READY_TITLE)}: {tr('Update fan helper')}", "warn")
                return
            guarded(ui_, tr("Sync now"), lambda: service.sincronizar_control_fan_sistema(policy))

        def external(ui_):
            handing = not system.get("external")
            if ui_.confirm(tr("Hand off to another program") if handing else tr("Take control back")):
                guarded(ui_, tr("Fan control"), lambda: service.ceder_fan_a_otro_programa(handing))

        out += [Choice(tr("Turn off") if enabled else tr("Turn on"), toggle, tone="warn" if enabled else "ok",
                       enabled=(enabled or available) and not system.get("external")),
                Choice(tr("Sync now"), sync, enabled=enabled and (out_of_date or state == "override")),
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
