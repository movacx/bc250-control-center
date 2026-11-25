"""Dashboard: the desktop's three cards, GDDR6, power rails and system preparation."""

from __future__ import annotations

import math
import time

from bc250cc.application.fan import board_view
from bc250cc.application.preparation.component_engine import component_capabilities
from bc250cc.domain.telemetry import voltage_mv
from bc250cc.shared.version import __version__
from frontends.desktop.core import compatibility_dialogs as dialogs
from frontends.desktop.core.dashboard_presenter import FAN_OWNER_LABELS

from ..content import (
    Buttons,
    Card,
    Chart,
    Choice,
    Field,
    Gap,
    Gauges,
    Grid,
    Heading,
    Meter,
    Note,
    Panel,
    Spans,
    heat_tone,
    load_tone,
    number,
    percent,
)
from ..i18n import tr, tr_format
from ..support import available_version
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
        if hasattr(value, "to_dict"):
            value = value.to_dict()
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


#: Disks without a name of their own; a volume label stays as the user wrote it.
DISK_KIND_LABELS = {"system": "System", "home": "Home"}


def extra_disk_meters(volumes: object) -> list:
    """A "Storage" heading and one meter per disk after the first, external drives included."""
    if not isinstance(volumes, (list, tuple)):
        return []
    rows = []
    for volume in list(volumes)[1:]:
        if not isinstance(volume, dict):
            continue
        name = DISK_KIND_LABELS.get(str(volume.get("kind") or ""))
        label = tr(name) if name else str(volume.get("label") or volume.get("mountpoint") or "--")
        rows.append(memory_meter(label, volume.get("used"), volume.get("total")))
    return [Heading(tr("Storage")), *rows] if rows else []


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
            (("daemon", "cu", "performance", "cpu_persistence", "fan_system"), MEDIUM_SECONDS,
             (service.estado_bc250_daemon, service.obtener_estado_cu_cache, service.rendimiento,
              service.estado_cpu_oc_persistente, service.estado_control_fan_sistema)),
            (("gddr6",), MEDIUM_SECONDS, (service.estado_gddr6_memory_temp,)),
            (("tools",), SLOW_SECONDS, (service.estado_herramientas_bc250,)),
        ):
            if now - state.get(f"{keys[0]}_at", -seconds) >= seconds or ctx.page_data.get(self.key) is None:
                state[f"{keys[0]}_at"] = now
                state.update({key: _safe(read) or {} for key, read in zip(keys, reads)})
        data = {key: state.get(key, {}) for key in ("daemon", "cu", "tools", "gddr6", "performance", "cpu_persistence", "fan_system")}
        data["fans"] = _safe(service.estado_fans_bc250)
        data["sample"] = _safe(service.ultima_temperatura_vram) or {}
        data["config"] = _safe(ctx.settings.read_local_config) if ctx.settings is not None else {}
        # The Cooling card's fan: the one the service follows or that turns (shared with the web).
        data["cooling_fan"] = board_view.dashboard_fan(data["fans"] or {}, data.get("fan_system") or {},
                                                       data["config"] or {})
        return data

    def tabs(self, ctx):
        return [("overview", tr("Dashboard")), ("prepare", tr("Prepare BC250 system"))]

    def build(self, ctx, data, tab, ui):
        if tab == "prepare":
            return self._prepare(ctx, data or {}, ui) + self._telemetry(ctx)
        if not ctx.metrics:
            return [Note(ctx.metrics_error or tr("Waiting for data…"), "bad" if ctx.metrics_error else "dim")]
        data = data or {}
        blocks = metric_blocks(ctx)
        gpu, cpu, memory, sensors, power = (blocks[k] for k in ("gpu", "cpu", "memory", "sensors", "power"))
        daemon = data.get("daemon") or {}
        performance = data.get("performance") or {}
        disk = blocks["disk"]
        cpu_voltage = voltage_mv(cpu.get("voltage_mv", performance.get("cpu_voltage")))
        persistence = data.get("cpu_persistence") or {}
        registered = persistence.get("config") or {}
        oc = tr("Not detected")
        if persistence.get("applied_this_boot") and registered.get("valid"):
            frequency, scale = registered.get("frequency"), registered.get("scale")
            if isinstance(frequency, (int, float)) and frequency > 0 and isinstance(scale, int) and -50 <= scale <= 0:
                oc = f"{frequency} MHz · {tr('Scale')} {scale}"
        pump = data.get("cooling_fan") or {}
        owner = pump.get("owner") or "manual"
        busy = gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")
        cus = ((data.get("cu") or {}).get("rows")) or []
        active_cus = sum(bin(int(row.get("mask", 0))).count("1") * 2 for row in cus) if cus else None

        cores = []
        usage = cpu.get("per_core_percent") or []
        clocks = cpu.get("per_core_frequency_mhz") or []
        for index in range(8):
            if index >= max(len(usage), len(clocks)):
                cores.append(Meter(f"N{index + 1}", None, tr("Hidden")))
                continue
            freq = clocks[index] if index < len(clocks) else None
            value = usage[index] if index < len(usage) else None
            cores.append(Meter(f"N{index + 1}", percent(value), f"{number(freq, 'MHz')} {number(value, '%')}", load_tone(value)))
        # One rule for every card: a bar only for a reading with a known ceiling (a
        # temperature, a percentage, memory used of total); clocks, power,
        # voltages and names are plain values. Missing sensors remain visible,
        # just as on the desktop, so an unavailable rail is not silently lost.
        def heat(label, value):
            return [temperature_meter(label, value)] if value is not None else [Field(label, tr("Not detected"), "dim")]

        cpu_card = Card(tr("Processor"), [
            *heat(tr("Core temperature"), cpu.get("temperature_c")),
            load_meter(tr("CPU usage"), cpu.get("usage_percent")),
            Field(tr("Registered OC"), oc),
            Field(tr("Topology"), tr_format("{cores} cores / {threads} threads", cores=cpu.get("physical_cores", "--"),
                                            threads=cpu.get("logical_cores", "--"))),
            Heading(tr("Live core monitor")), Gauges(cores, minimum=25),
        ], number(cpu.get("frequency_mhz", 0) / 1000 if cpu.get("frequency_mhz") else None, "GHz", 2))
        gpu_card = Card(tr("Graphics"), [
            *heat(tr("Temperature"), gpu.get("temperature_c")),
            load_meter(tr("GPU load"), busy),
            *[Field(" · ".join(name for name, _v in clocks), " · ".join(number(v) for _n, v in clocks) + " MHz")
              for clocks in [[(name, gpu[key]) for name, key in (("MCLK", "memory_frequency_mhz"), ("SOC", "soc_frequency_mhz"),
                                                                 ("FCLK", "fabric_frequency_mhz")) if gpu.get(key)]] if clocks],
            Heading(tr("Memory")),
            memory_meter("VRAM", gpu.get("vram_used"), gpu.get("vram_total")),
            memory_meter("GTT", gpu.get("gtt_used"), gpu.get("gtt_total")),
            memory_meter(tr("System memory"), memory.get("used"), memory.get("total")),
            Heading(tr("Status")),
            Field(tr("Compute units"), f"{active_cus} / 40" if active_cus is not None else "--"),
            Field(tr("Governor"), str(daemon.get("governor_backend") or "--").replace("-skillfish-governor-smu", "")),
            Field(tr("Requested range"), f"{daemon.get('current_min', '--')} – {daemon.get('current_max', '--')} MHz"),
            Field(tr("PCIe link"), str(gpu.get("pcie_link") or "--")),
            Field("VBIOS", str(gpu.get("vbios_version") or "--")),
        ], number(gpu.get("frequency_mhz"), "MHz"))
        fan_cycle = pump.get("pwm")
        duty = round(int(fan_cycle) * 100 / 255) if isinstance(fan_cycle, int) else None
        cool_card = Card(tr("Cooling"), [
            Meter(tr("PWM duty"), percent(duty), number(duty, "%"), "accent"),
            Field(tr("PWM mode"), tr(FAN_OWNER_LABELS.get(owner, "Not detected"))),
            Field(tr("Controller"), str(pump.get("name") or "--")),
            *heat(tr("Board temperature"), sensors.get("board_temperature_c")),
        ], number(pump.get("rpm"), "RPM"))
        disk_card = Card(tr("Storage"), [
            *heat(tr("Temperature"), sensors.get("nvme_temperature_c")),
            *heat(tr("Hotspot"), sensors.get("nvme_hotspot_temperature_c")),
            memory_meter(tr("Used"), disk.get("used", performance.get("disco_usado")),
                         disk.get("total", performance.get("disco_total"))),
            memory_meter("Swap", memory.get("swap_used"), memory.get("swap_total")),
            *extra_disk_meters(disk.get("volumes", performance.get("discos"))),
            Field("BIOS", str(data.get("bios") or ctx.state(self.key).get("bios") or self._bios(ctx))),
        ])

        own = {"cpu_v": cpu_voltage / 1000 if cpu_voltage is not None else None,
               "gpu_v": gpu["voltage_mv"] / 1000 if gpu.get("voltage_mv") else None,
               "gpu_w": power.get("value_w", gpu.get("power_w")) or None}  # 0 W is how a missing sensor reads
        # The memory under the processor, the regulators first in their column: even columns on a wide
        # terminal, and near the top on a narrow one.
        newer = available_version(ctx)
        news = [Panel(tr("Update available"), [Note(f"{__version__} → {newer}. " + tr("Press U to read what is new and install it."))], badge=newer, badge_tone="warn")] if newer else []
        page = [*news, cpu_card, self._gddr6(ctx, data.get("gddr6") or {}, data.get("sample") or {}), gpu_card,
                self._power(sensors, ctx.service, (data.get("tools") or {}).get("accessories") or {}, own), cool_card, disk_card]
        return [*page, *self._temperatures(ctx, ui, page)]

    @staticmethod
    def _temperatures(ctx, ui, page):
        """The last minutes of the temperatures, when the readings above leave room for a plot."""
        from ..layout import Glyphs, build_page
        from .performance import axis_for, window_text

        if not hasattr(ui, "_content_box"):
            return []
        width = ui._content_box()[1]
        room = ui._view() - len(build_page(page, width, Glyphs.for_terminal(unicode_ok=True)).rows)
        traces = [(name, list(ctx.history.get(f"trace:{key}", ())), tone) for name, key, tone in (
            ("GPU", "gpu", "accent"), ("CPU", "cpu", "ok"), ("VRM", "vrm", ""))]
        times = sorted({moment for _name, trace, _tone in traces for moment, _value in trace})
        series = []
        for name, trace, tone in traces:
            values = dict(trace)
            if values:
                series.append((name, [values.get(moment, math.nan) for moment in times], tone))
        if room < 13 or width < 100 or len(times) < 2 or not series:
            return []
        window = next((seconds for seconds in (60, 120, 300, 600) if times[-1] - times[0] <= seconds), 600)

        def show(value):
            return number(value, "°C", 1)

        scale, height = axis_for([v for _n, values, _t in series for v in values if not math.isnan(v)], "°C", min(22, room - 5))
        return [Panel(tr("Temperatures"), [Chart(series, times, scale.minimum, scale.maximum, height, show, window=window,
                                                 ticks=scale.ticks, now=tr("Now"), mark=lambda value: number(value, "°C", 0)
                                                 if float(value).is_integer() else show(value)),
                                           Spans([[part for name, _values, tone in series for part in (
                                               ("● " if getattr(ui, "unicode", True) else "* ", tone), (f"{name}    ", "dim"))]])],
                      badge=window_text(window), wide=True)]

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
        out = []
        if average is not None:
            out += [temperature_meter(tr("Hottest chip"), hotspot), temperature_meter(tr("Average across 8 chips"), average)]
        else:
            out.append(Field(tr("Status"), str(sample.get("error") or status.get("governor_state") or tr("Waiting for data…")), "dim"))
        if chips:
            hottest = max((c.get("temperature_c") or 0 for c in chips[:8]), default=0)
            out += [Gap(), Gauges([Meter(f"Chip {c.get('chip')}", percent((c.get("temperature_c") or 0) / 110 * 100),
                                         number(c.get("temperature_c"), "°C", 0) + (" ▴" if c.get("temperature_c") == hottest else "  "),
                                         heat_tone(c.get("temperature_c"), 85, 95)) for c in chips[:8]], minimum=24), Gap()]

        def read(ui_):
            ok, result = ui_.run(tr("GDDR6 memory temperature"), lambda: service.leer_temperatura_vram(chips=True))
            if ok and isinstance(result, dict):
                state["gddr6_sample"] = result
            ui_.refresh()

        def prepare(ui_):
            if ui_.confirm(tr("Prepare readings")):
                guarded(ui_, tr("GDDR6 memory temperature"), service.comando_preparar_gddr6_memory_temp)

        buttons = [] if status.get("kernel_driver") else [Choice(tr("Refresh"), read, enabled=bool(status.get("reader_ready", True)))]  # the driver already feeds every refresh
        if not status.get("repository_ready"):
            buttons.append(Choice(tr("Prepare readings"), prepare))
        source = tr("Kernel driver") if status.get("kernel_driver") else ""
        if source and chips:
            out.append(Field(tr("Source"), source))
        return Panel(tr("GDDR6 memory temperature"), [*out, *([Buttons(buttons)] if buttons else [])],
                     badge=number(hotspot, "°C", 0) if hotspot is not None else source, badge_tone=heat_tone(hotspot, 85, 95))

    @staticmethod
    def _telemetry(ctx):
        from .extras import INSTALL, run

        return [Heading(tr("BC250-Telemetry service")),
                Choice(tr("BC250-Telemetry service") + " ›", lambda ui_: run(
                    ui_, "BC250-Telemetry service", ctx.service.gestionar_apu_telemetry, INSTALL)), Gap()]

    # -- power rails ------------------------------------------------------------

    @staticmethod
    def _power(sensors, service=None, accessories=None, own=None):
        """Every voltage and power reading in one place: the regulators' rails, then what each chip says of itself."""
        own = own or {}
        rails = [(name, number(sensors.get(f"vrm_{key}_voltage_v"), "", 3), number(sensors.get(f"vrm_{key}_current_a"), "", 1),
                  number(sensors.get(f"vrm_{key}_power_w"), "", 1), number(sensors.get(f"vrm_{key}_temperature_c"), "", 0))
                 for key, name in (("cpu", "VRM CPU"), ("gpu", "VRM GPU"))]
        total, mos, vin = (sensors.get(f"vrm_{key}") for key in ("total_power_w", "mos_temperature_c", "input_voltage_v"))
        missing = total is None and mos is None and vin is None and all(cell == "--" for row in rails for cell in row[1:])
        out: list = []
        if missing:
            out.append(Note(tr("No sensor reads the power rails of this board. Additional settings can add one."), "dim"))
            if (accessories or {}).get("vrm_sensor", {}).get("state") in ("installed", "active"):
                out.append(Choice(tr("Restart driver"), lambda ui_: ui_.confirm(tr("Restart driver"))
                                  and guarded(ui_, tr("Restart driver"), service.reiniciar_sensor_vrm)))
        else:
            out += [Grid(["", "V", "A", "W", "°C"], rails, gap=3), Gap(),
                    Field(tr("Input voltage"), number(vin, "V", 2)), Field(tr("VRM MOS"), number(mos, "°C", 0))]
        # The chips' own sensors; a missing one only matters when no rail reads that chip either.
        for label, value, unit, digits, rail in (
                (tr("Core voltage"), own.get("cpu_v"), "V", 3, "vrm_cpu_voltage_v"),
                (tr("GPU voltage"), own.get("gpu_v"), "V", 3, "vrm_gpu_voltage_v"),
                (tr("GPU power"), own.get("gpu_w"), "W", 0, "vrm_gpu_power_w")):
            if value is not None:
                out.append(Field(label, number(value, unit, digits)))
            elif sensors.get(rail) is None:
                out.append(Field(label, tr("Not detected"), "dim"))
        return Panel(f"{tr('Power')} · {tr('Voltages')}", out, badge=number(total, "W", 1) if total is not None else "", badge_tone="")

    # -- system preparation ------------------------------------------------------

    def _prepare(self, ctx, data, ui):
        service = ctx.service
        state = ctx.state(self.key)
        family, name = os_family(ctx)
        capabilities = component_capabilities(type("Info", (), {"family": family})())
        debian = family in ("debian", "ubuntu")  # there UMR may build LLVM: an explicit choice, as on the desktop
        selected = state.setdefault("selected", {key for key, _label in COMPONENTS if not debian or key in ("runtime", "governor")})
        tools = data.get("tools") or {}
        capabilities = tools.get("prepare_components") or capabilities
        installed = {"governor": tools.get("governor_pkg"), "umr": tools.get("umr"), "cu_manager": tools.get("cu_manager_exists"),
                     **{key: True for key, item in capabilities.items() if item.get("installed")}}
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

        out.append(Choice(f"{tr('Prepare selected')} ({chosen})", prepare, enabled=bool(chosen) and "runtime" in selected, tone="accent"))
        quick = tools.get("quick_access") or {}
        if not quick.get("supported"):
            return out
        plugin_only = bool(quick.get("decky_detected")) and bool(quick.get("decky_frontend_compatible", True))
        label = tr("Install / repair BC250 Quick Access" if plugin_only else "Install Decky + Quick Access (Beta)")
        question = tr("This installs or repairs only the local BC250 Quick Access plugin and its protected helper inside an existing "
                      "Decky installation. It does not reinstall Decky or apply a hardware setting. Continue?") if plugin_only else \
            tr("Bazzite installs Decky through its native ujust setup-decky install workflow. BC250 then installs only its local "
               "Quick Access panel. Continue?") if family == "bazzite" else tr(dialogs.DECKY_BOOTSTRAP)

        def decky(ui_):
            if ui_.confirm(f"{label}\n\n{question}", danger=True):
                guarded(ui_, "Decky", lambda: service.preparar_quick_access_steamos(install_decky=not plugin_only))

        out += [Gap(), Heading("Decky"), Note(tr(
            "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet." if quick.get("ready") else
            "Decky must be updated because this Steam client uses the renamed initialization API."
            if quick.get("decky_detected") and not plugin_only else
            "Decky is detected, but the BC250 Quick Access plugin or its protected helper needs installation or repair."
            if plugin_only else "Decky is optional. It is never installed by generic dependency preparation."), "dim"),
            Choice(label, decky, enabled=bool(quick.get("decky_plugin_root_safe", True)))]
        return out
