"""Dashboard: the desktop's three cards, GDDR6, power rails and system preparation."""

from __future__ import annotations

import time

from bc250cc.application.preparation.component_engine import component_capabilities

from ..content import (
    Card,
    Choice,
    Columns,
    Field,
    Gap,
    Grid,
    Heading,
    Meter,
    Note,
    heat_tone,
    load_tone,
    number,
    percent,
)
from ..i18n import tr
from .base import (
    Page,
    guarded,
    load_meter,
    metric_blocks,
    os_family,
    temperature_meter,
)

COMPONENTS = (
    ("runtime", "Base dependencies"),
    ("governor", "Selected GPU governor"),
    ("cpu_oc", "CPU OC tools"),
    ("core_unlock", "CPU Core Unlock source"),
    ("umr", "UMR database"),
    ("cu_manager", "40CU manager"),
    ("fan_pwm", "NCT sensors and PWM"),
)
MEDIUM_SECONDS = 15.0
SLOW_SECONDS = 60.0


def _safe(call):
    """A service reading, or None when it fails or is not a mapping."""
    try:
        value = call()
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def memory_meter(label: str, used: object, total: object) -> Meter:
    """``used/total`` in the total's unit (MiB below 1 GiB, else GiB): "0.98/7.4 GiB", short enough for a card."""
    try:
        used_b, total_b = float(used), float(total)
        fraction = used_b / total_b
    except (TypeError, ValueError, ZeroDivisionError):
        return Meter(label, None, "--")
    tone = "bad" if fraction >= 0.95 else "warn" if fraction >= 0.85 else "ok"
    scale, unit, digits = (2**30, "GiB", 1) if total_b >= 2**30 else (2**20, "MiB", 0)
    shown = f"{used_b / scale:.{2 if used_b < scale else digits}f}/{total_b / scale:.{digits}f} {unit}"
    return Meter(label, fraction, shown, tone)


def pump_row(fans) -> dict:
    rows = ((fans or {}).get("sensores") or {}).get("fans") or []
    for row in rows:
        label = str(row.get("label") or "").lower() if isinstance(row, dict) else ""
        if any(token in label for token in ("pump", "j4003", "fan2")):
            return row
    return next((row for row in rows if isinstance(row, dict) and row.get("rpm")), {})


class DashboardPage(Page):
    key = "dashboard"
    title = "Dashboard"
    interval = 3.0

    def load(self, ctx):
        service = ctx.service
        state = ctx.state(self.key)
        now = time.monotonic()
        # Each reading at the pace it changes: the fans are sysfs reads; the
        # daemon and CU state ask systemd and D-Bus; the tool inventory runs
        # package managers and git. Polling those every few seconds was most of
        # the interface's idle CPU.
        for keys, seconds, reads in (
            (("daemon", "cu"), MEDIUM_SECONDS, (service.estado_bc250_daemon, service.obtener_estado_cu_cache)),
            (("tools", "gddr6"), SLOW_SECONDS, (service.estado_herramientas_bc250, service.estado_gddr6_memory_temp)),
        ):
            if now - state.get(f"{keys[0]}_at", -seconds) >= seconds or ctx.page_data.get(self.key) is None:
                state[f"{keys[0]}_at"] = now
                state.update({key: _safe(read) or {} for key, read in zip(keys, reads)})
        data = {key: state.get(key, {}) for key in ("daemon", "cu", "tools", "gddr6")}
        data["fans"] = _safe(service.estado_fans_bc250)
        data["sample"] = _safe(service.ultima_temperatura_vram) or {}
        return data

    def build(self, ctx, data, tab, ui):
        if not ctx.metrics:
            return [Note(ctx.metrics_error or tr("Waiting for data…"), "bad" if ctx.metrics_error else "dim")]
        data = data or {}
        blocks = metric_blocks(ctx)
        gpu, cpu, memory, sensors, power = (blocks[k] for k in ("gpu", "cpu", "memory", "sensors", "power"))
        daemon = data.get("daemon") or {}
        pump = pump_row(data.get("fans"))
        busy = gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")
        cus = ((data.get("cu") or {}).get("rows")) or []
        active_cus = sum(bin(int(row.get("mask", 0))).count("1") * 2 for row in cus) if cus else None

        cores = []
        usage = cpu.get("per_core_percent") or []
        clocks = cpu.get("per_core_frequency_mhz") or []
        for index, value in enumerate(usage[:8]):
            freq = clocks[index] if index < len(clocks) else None
            cores.append(Meter(f"N{index + 1}", percent(value), f"{number(freq, 'MHz')} {number(value, '%')}", load_tone(value)))
        # One rule for every card: a bar only for a reading with a known ceiling (a
        # temperature, a percentage, memory used of total); clocks, power,
        # voltages and names are plain values. Absent sensors are left out.
        def heat(label, value):
            return [temperature_meter(label, value)] if value is not None else []

        cpu_card = Card(tr("Processor"), [
            Heading(tr("Thermal")),
            *heat(tr("Core temperature"), cpu.get("temperature_c")), *heat("VRM CPU", sensors.get("vrm_cpu_temperature_c")),
            Heading(tr("Activity")),
            load_meter(tr("CPU usage"), cpu.get("usage_percent")),
            Field(tr("Topology"), f"{cpu.get('physical_cores', '--')} / {cpu.get('logical_cores', '--')}"),
            Heading(tr("Live core monitor")), *cores,
        ], number(cpu.get("frequency_mhz", 0) / 1000 if cpu.get("frequency_mhz") else None, "GHz", 2))
        gpu_card = Card(tr("Graphics"), [
            Heading(tr("Thermal")),
            *heat(tr("Temperature"), gpu.get("temperature_c")), *heat("VRM MOS", sensors.get("vrm_mos_temperature_c")),
            *heat("VRM GPU", sensors.get("vrm_gpu_temperature_c")),
            Heading(tr("Power")),
            Field(tr("GPU power"), number(power.get("value_w", gpu.get("power_w")), "W", 0)),
            Field(tr("GPU voltage"), number((gpu.get("voltage_mv") or 0) / 1000 if gpu.get("voltage_mv") else None, "V", 3)),
            Heading(tr("Clocks")),
            Field("MCLK", number(gpu.get("memory_frequency_mhz"), "MHz")),
            Field("SOCCLK", number(gpu.get("soc_frequency_mhz"), "MHz")),
            Field("FCLK", number(gpu.get("fabric_frequency_mhz"), "MHz")),
            Heading(tr("Memory")),
            memory_meter("VRAM", gpu.get("vram_used"), gpu.get("vram_total")),
            memory_meter("GTT", gpu.get("gtt_used"), gpu.get("gtt_total")),
            memory_meter(tr("System memory"), memory.get("used"), memory.get("total")),
            Heading(tr("Status")),
            load_meter(tr("GPU load"), busy),
            Field(tr("Compute units"), f"{active_cus} / 40" if active_cus is not None else "--"),
            Field(tr("Governor"), str(daemon.get("governor_backend") or "--").replace("-skillfish-governor-smu", "")),
            Field(tr("Requested range"), f"{daemon.get('current_min', '--')} – {daemon.get('current_max', '--')} MHz"),
            Field(tr("PCIe link"), str(gpu.get("pcie_link") or "--")),
            Field("VBIOS", str(gpu.get("vbios_version") or "--")),
        ], number(gpu.get("frequency_mhz"), "MHz"))
        fan_cycle = pump.get("pwm")
        duty = round(int(fan_cycle) * 100 / 255) if isinstance(fan_cycle, int) else None
        cool_card = Card(tr("Cooling"), [
            Heading(tr("Fan")),
            Meter(tr("PWM duty"), percent(duty), number(duty, "%"), "accent"),
            Field(tr("PWM mode"), {2: "Firmware (BIOS)", 1: tr("Manual")}.get(pump.get("pwm_enable"), "--")),
            Field(tr("Controller"), str(pump.get("label") or "--")),
            *heat(tr("Board temperature"), sensors.get("board_temperature_c")),
            Heading(tr("M.2 drive")),
            *heat(tr("Temperature"), sensors.get("nvme_temperature_c")),
            *heat(tr("Hotspot"), sensors.get("nvme_hotspot_temperature_c")),
            memory_meter("Swap", memory.get("swap_used"), memory.get("swap_total")),
            Heading("BIOS"),
            Field(tr("Release"), str(data.get("bios") or ctx.state(self.key).get("bios") or self._bios(ctx))),
        ], number(pump.get("rpm"), "RPM"))

        out = [Columns([cpu_card, gpu_card, cool_card], minimum=40), Gap()]
        out += self._gddr6(ctx, data.get("gddr6") or {}, data.get("sample") or {})
        out += self._power(sensors)
        out += self._prepare(ctx, data, ui)
        return out

    @staticmethod
    def _bios(ctx):
        state = ctx.state("dashboard")
        if "bios" not in state:
            try:
                from bc250cc.application.firmware import firmware_snapshot

                snapshot = firmware_snapshot()
                state["bios"] = f"{snapshot.board.version} {snapshot.installed.variant}".strip()
            except Exception:
                state["bios"] = "--"
        return state["bios"]

    # -- GDDR6 ---------------------------------------------------------------

    def _gddr6(self, ctx, status, last):
        service = ctx.service
        state = ctx.state(self.key)
        sample = state.get("gddr6_sample") or last
        external = status.get("external") or {}
        chips = sample.get("chips") or external.get("chips") or []
        average = sample.get("average_c", external.get("average_c"))
        hotspot = sample.get("hotspot_c", external.get("hotspot_c"))
        out = [Heading(tr("GDDR6 memory temperature"))]
        if average is not None:
            reading, tone = f"{number(average, '°C', 1)}   {tr('Hotspot')} {number(hotspot, '°C', 1)}", heat_tone(hotspot)
        else:
            reading, tone = sample.get("error") or status.get("governor_state") or tr("Waiting for data…"), "dim"
        out.append(Field(tr("Status"), str(reading), tone))
        for first in range(0, len(chips[:8]), 4):
            group = chips[first:first + 4]
            out.append(Grid([f"Chip {c.get('chip')}" for c in group],
                            [[f"{number(c.get('temperature_c'), '°C', 1)}  MR3 0x{int(c.get('code', 0)):02X}" for c in group]],
                            gap=6))

        def read(ui_):
            ok, result = ui_.run(tr("GDDR6 memory temperature"), lambda: service.leer_temperatura_vram(chips=True))
            if ok and isinstance(result, dict):
                state["gddr6_sample"] = result
            ui_.refresh()

        def prepare(ui_):
            if ui_.confirm(tr("Prepare readings")):
                guarded(ui_, tr("GDDR6 memory temperature"), service.comando_preparar_gddr6_memory_temp)

        out.append(Choice(tr("Refresh"), read, enabled=bool(status.get("reader_ready", True))))
        if not status.get("repository_ready"):
            out.append(Choice(tr("Prepare readings"), prepare))
        return out + [Gap()]

    # -- power rails ------------------------------------------------------------

    @staticmethod
    def _power(sensors):
        rails = [
            ("Vin", number(sensors.get("vrm_input_voltage_v"), "V", 2)),
            (tr("CPU voltage"), number(sensors.get("vrm_cpu_voltage_v"), "V", 3)),
            (tr("GPU voltage"), number(sensors.get("vrm_gpu_voltage_v"), "V", 3)),
            (tr("CPU current"), number(sensors.get("vrm_cpu_current_a"), "A", 1)),
            (tr("GPU current"), number(sensors.get("vrm_gpu_current_a"), "A", 1)),
            (tr("Total board power"), number(sensors.get("vrm_total_power_w"), "W", 1)),
        ]
        if all(value == "--" for _label, value in rails):
            return [Heading(tr("Power")), Field(tr("Status"), tr("Not detected"), "dim"), Gap()]
        return [Heading(tr("Power")), *[Field(label, value) for label, value in rails], Gap()]

    # -- system preparation ------------------------------------------------------

    def _prepare(self, ctx, data, ui):
        service = ctx.service
        state = ctx.state(self.key)
        family, name = os_family(ctx)
        capabilities = component_capabilities(type("Info", (), {"family": family})())
        selected = state.setdefault("selected", {key for key, _label in COMPONENTS})
        tools = data.get("tools") or {}
        installed = {"governor": tools.get("governor_pkg"), "umr": tools.get("umr"),
                     "cu_manager": tools.get("cu_manager_exists")}
        out = [Heading(tr("Prepare BC250 system")), Field(tr("Detected system"), name)]
        chosen = 0
        for key, label in COMPONENTS:
            available = bool(capabilities.get(key, {}).get("available", True))
            on = key in selected and available
            chosen += on

            def toggle(ui_, key=key):
                selected.symmetric_difference_update({key})

            mark = "[x]" if on else "[ ]"
            note = tr("Installed") if installed.get(key) else (capabilities.get(key, {}).get("detail") if not available else "")
            out.append(Choice(f"{mark} {tr(label)}", toggle, str(note or ""), enabled=available,
                              tone="ok" if on else ""))

        def prepare(ui_):
            components = [key for key, _label in COMPONENTS if key in selected
                          and capabilities.get(key, {}).get("available", True)]
            if not components:
                return
            preference = str((ctx.config or {}).get("gpu_governor", "auto"))
            if ui_.confirm(f"{tr('Prepare selected')} ({len(components)}): " + ", ".join(components)):
                guarded(ui_, tr("Prepare BC250 system"), lambda: service.instalar_dependencias_bc250(
                    governor_preference=preference, include_pwm="fan_pwm" in components, components=components))

        out.append(Choice(f"{tr('Prepare selected')} ({chosen})", prepare, enabled=bool(chosen), tone="accent"))
        out += [Gap(), Heading("Decky")]

        def decky(ui_):
            if ui_.confirm(tr("Install Decky + Quick Access (Beta)")):
                guarded(ui_, "Decky", lambda: service.preparar_quick_access_steamos(install_decky=True))

        out.append(Note(tr("Decky is optional. It is never installed by generic dependency preparation."), "dim"))
        out.append(Choice(tr("Install Decky + Quick Access (Beta)"), decky))
        return out
