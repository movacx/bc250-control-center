"""Panel pasivo y preparación: solo servicios existentes y parámetros cerrados."""
from __future__ import annotations

import time

from frontends.web.actions import Invalid, choice, flag
from bc250cc.application.preparation.gpu_dependency_plan import build_gpu_dependency_plan
from frontends.tui.pages.dashboard import COMPONENTS, DashboardPage, _safe
from frontends.desktop.core.dashboard_presenter import FAN_OWNER_LABELS
from frontends.desktop.core.developer_note_text import PARAGRAPHS, TITLE, WHEN, THANKS, SIGNATURE
from frontends.desktop.core.compatibility_dialogs import DECKY_BOOTSTRAP
from frontends.tui.i18n import tr, tr_format

CLAVES = tuple(key for key, _ in COMPONENTS)
DETALLES = ("Runtime files and packages.", "Cyan or Oberon setup.", "bc250_smu_oc support.",
            "Experimental source.", "Required for 40CU.", "CU routing and restore.", "Fan control route.")
ENLACES = (
    ("Official repositories", "https://github.com/movacx/BC250-Control-Center"),
    ("Discord", "https://discord.com/invite/8eZfFWhczz"),
    ("Telegram", "https://t.me/+LJAp9e4cpPs3Mzky"),
    ("Ko-fi", "https://ko-fi.com/movacx"),
)


def mostrar(valor, unidad="", decimales=0, cero=False):
    if not isinstance(valor, (int, float)) or (valor == 0 and not cero):
        return tr("Not detected")
    return f"{valor:.{decimales}f}" + (f" {unidad}" if unidad else "")


def memoria(usado, total):
    if not isinstance(total, (int, float)) or total <= 0:
        return tr("Not detected")
    escala, unidad = (2**30, "GB") if total >= 2**30 else (2**20, "MB")
    return f"{(usado or 0) / escala:.1f} / {total / escala:.1f} {unidad}"


def fila(nombre, valor, detalle=""):
    unidad = ""
    tono = ""
    for sufijo in ("°C", "°F", "MHz", "GHz", "RPM", "mV", "W", "V", "A", "%", "GB", "MB"):
        if str(valor).endswith(" " + sufijo):
            valor, unidad = valor[:-len(sufijo)].strip(), sufijo
            break
    if unidad == "°C":
        try:
            temperatura = float(valor)
            tono = "danger" if temperatura >= 90 else "warning" if temperatura >= 80 else ""
        except ValueError:
            pass
    return {"label": nombre, "value": valor, "unit": unidad, "detail": detalle, "tone": tono}


def grupo(nombre, filas, columna=0):
    return {"title": nombre, "rows": filas, "column": columna}


def leer(ctx, live):
    datos = DashboardPage().load(ctx)
    ctx.page_data["dashboard"] = datos
    metricas = ctx.metrics or {}
    almacen = ctx.state("web.panel")
    if time.monotonic() - almacen.get("gpu_at", -15) >= 15:
        almacen["gpu"] = _safe(ctx.service.estado_bc250) or {}
        almacen["gpu_at"] = time.monotonic()
    diagnostico = almacen.get("gpu") or {}
    cpu, gpu, sensores, ram, disco = [metricas.get(key) or {} for key in ("cpu", "gpu", "sensors", "memory", "disk")]
    tools, cu, daemon = [datos.get(key) or {} for key in ("tools", "cu", "daemon")]
    ventilador = datos.get("cooling_fan") or {}
    persistencia = datos.get("cpu_persistence") or {}
    registrado = persistencia.get("config") or {}
    oc = bool(persistencia.get("applied_this_boot") and registrado.get("valid"))
    activos = cu.get("active_cus")
    if activos is None and cu.get("rows"):
        activos = sum(int(row.get("mask", 0)).bit_count() * 2 for row in cu["rows"])
    topologia = tr_format("{cores} cores / {threads} threads", cores=cpu.get("physical_cores", "--"), threads=cpu.get("logical_cores", "--"))
    cpu_grupos = [grupo("Thermal", [fila("Core temperature", mostrar(cpu.get("temperature_c"), "°C", 1)),
                                  fila("VRM CPU", mostrar(sensores.get("vrm_cpu_temperature_c"), "°C"))]),
                  grupo("Activity", [fila("CPU usage", mostrar(cpu.get("usage_percent"), "%", cero=True)),
                                     fila("Core voltage", mostrar(cpu.get("voltage_mv"), "mV")),
                                     fila("Registered OC", mostrar(registrado.get("frequency"), "MHz") if oc else "None",
                                          tr_format("Scale {scale}", scale=registrado.get("scale")) if oc else "")])]
    gpu_grupos = [
        grupo("Thermal", [fila("Temperature", mostrar(gpu.get("temperature_c"), "°C")),
                          fila("VRM MOS", mostrar(sensores.get("vrm_mos_temperature_c"), "°C")),
                          fila("VRM GPU", mostrar(sensores.get("vrm_gpu_temperature_c"), "°C"))]),
        grupo("Power", [fila("GPU power", mostrar((metricas.get("power") or {}).get("gpu_w", gpu.get("power_w")), "W")),
                        fila("GPU voltage", mostrar(gpu.get("voltage_mv"), "mV"))]),
        grupo("Clocks", [fila(label, mostrar(gpu.get(key), "MHz")) for label, key in
                         (("MCLK", "memory_frequency_mhz"), ("SOCCLK", "soc_frequency_mhz"), ("FCLK", "fabric_frequency_mhz"))]),
        grupo("Memory", [fila(label, memoria(obj.get(used), obj.get(total))) for label, obj, used, total in
                         (("VRAM", gpu, "vram_used", "vram_total"), ("GTT", gpu, "gtt_used", "gtt_total"),
                          ("System memory", ram, "used", "total"))], 1),
        grupo("Status", [fila("GPU load", mostrar(gpu.get("usage_percent"), "%", cero=True)),
                         fila("Compute Units", f"{activos} / 40" if activos is not None else "Not detected"),
                         fila("Governor", daemon.get("governor_backend") or "Not detected"),
                         fila("Requested range", f"{daemon.get('current_min', '--')} – {daemon.get('current_max', '--')} MHz"),
                         fila("PCIe link", gpu.get("pcie_link") or "Not detected"),
                         fila("VBIOS", gpu.get("vbios_version") or "Not detected")], 1),
    ]
    pwm = ventilador.get("pwm")
    refrigeracion = [grupo("Fan", [fila("PWM duty", mostrar(pwm * 100 / 255 if isinstance(pwm, (int, float)) else None, "%", cero=True)),
                                    fila("PWM mode", FAN_OWNER_LABELS.get(ventilador.get("owner"), "Not detected")),
                                    fila("Board temperature", mostrar(sensores.get("board_temperature_c"), "°C"))]),
                     grupo("M.2 drive", [fila("Temperature", mostrar(sensores.get("nvme_temperature_c"), "°C")),
                                          fila("Hotspot", mostrar(sensores.get("nvme_hotspot_temperature_c"), "°C")),
                                          fila("Used", memoria(disco.get("used"), disco.get("total"))),
                                          fila("Swap", memoria(ram.get("swap_used"), ram.get("swap_total")))])]
    extras = [fila({"system": "System", "home": "Home"}.get(item.get("kind"), item.get("label") or item.get("mountpoint", "")),
                   memoria(item.get("used"), item.get("total"))) for item in (disco.get("volumes") or [])[1:]]
    if extras:
        refrigeracion.append(dict(grupo("Storage", extras), collapsed=True))
    refrigeracion.append(grupo("BIOS", [fila("Version", tools.get("bios_version") or DashboardPage._bios(ctx))]))
    nucleos = []
    cargas, frecuencias = cpu.get("per_core_percent") or [], cpu.get("per_core_frequency_mhz") or []
    for indice in range(8):
        online = indice < max(len(cargas), len(frecuencias))
        frecuencia = frecuencias[indice] if indice < len(frecuencias) else None
        carga = cargas[indice] if indice < len(cargas) else None
        nucleos.append({"label": f"N{indice + 1}", "value": mostrar(frecuencia / 1000 if frecuencia else None, "GHz", 2) if online else tr("Hidden"),
                        "usage": carga, "detail": mostrar(carga, "%", cero=True) if online else ""})
    capacidades = tools.get("prepare_components") or {}
    componentes = []
    for (key, title), detail in zip(COMPONENTS, DETALLES):
        estado = capacidades.get(key) or {}
        componentes.append({"key": key, "title": title, "detail": estado.get("detail") or detail,
                            "available": bool(estado.get("available", True)), "installed": bool(estado.get("installed")),
                            "selected": bool(estado.get("selected", tools.get("os_family") not in ("debian", "ubuntu") or key in ("runtime", "governor")))})
    quick = tools.get("quick_access") or {}
    plugin = bool(quick.get("decky_detected") and quick.get("decky_frontend_compatible", True))
    quick = {**quick, "title": "Game Mode Quick Access (Beta)",
             "label": "Install / repair BC250 Quick Access" if plugin else "Install Decky + Quick Access (Beta)",
             "detail": "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet." if quick.get("ready") else
             "Decky must be updated because this Steam client uses the renamed initialization API." if quick.get("decky_detected") and not plugin else
             "Decky is detected, but the BC250 Quick Access plugin or its protected helper needs installation or repair." if plugin else
             "Decky is optional. It is never installed by generic dependency preparation.",
             "message": "This installs or repairs only the local BC250 Quick Access plugin and its protected helper inside an existing Decky installation. It does not reinstall Decky or apply a hardware setting. Continue?" if plugin else
             "Bazzite installs Decky through its native ujust setup-decky install workflow. BC250 then installs only its local Quick Access panel. Continue?" if tools.get("os_family") == "bazzite" else DECKY_BOOTSTRAP, "install_decky": not plugin}
    rails = [fila(label, mostrar(sensores.get(key), unit, decimals)) for label, key, unit, decimals in (
        ("12V in", "vrm_input_voltage_v", "V", 2), ("VRM power", "vrm_total_power_w", "W", 1),
        ("CPU rail voltage", "vrm_cpu_voltage_v", "V", 3), ("GPU rail voltage", "vrm_gpu_voltage_v", "V", 3),
        ("CPU current", "vrm_cpu_current_a", "A", 1), ("GPU current", "vrm_gpu_current_a", "A", 1),
        ("CPU rail temperature", "vrm_cpu_temperature_c", "°C", 0), ("GPU rail temperature", "vrm_gpu_temperature_c", "°C", 0))]
    telemetria = presentar_telemetria(diagnostico, tools)
    if (diagnostico.get("apu_telemetry") or {}).get("status") == "invalid":
        for agrupacion in gpu_grupos:
            for lectura in agrupacion["rows"]:
                if lectura["label"] in ("Temperature", "GPU voltage", "MCLK") and lectura["value"] == tr("Not detected"):
                    lectura["value"] = "Invalid"
    from frontends.web.gddr6 import readiness
    gddr = readiness(ctx.service)
    muestra = live.gddr6.get("sample") or datos.get("sample") or gddr.get("external") or (gddr if gddr.get("kernel_driver") else {})
    return {"title": "AMD BC-250", "specification": f"BC250 · {topologia} · {activos or '--'} / 40 {tr('Compute Units')} · {mostrar((gpu.get('vram_total') or 0) / 2**30, 'GB', 1)} VRAM",
            "cards": [{"key": "cpu", "title": "Processor", "primary": mostrar((cpu.get("frequency_mhz") or 0) / 1000, "GHz", 2), "value": mostrar((cpu.get("frequency_mhz") or 0) / 1000, decimales=2), "unit": "GHz", "groups": cpu_grupos},
                      {"key": "gpu", "title": "Graphics", "primary": mostrar(gpu.get("frequency_mhz"), "MHz"), "value": mostrar(gpu.get("frequency_mhz")), "unit": "MHz", "groups": gpu_grupos},
                      {"key": "fans", "title": "Cooling", "primary": mostrar(ventilador.get("rpm"), "RPM", cero=True), "value": mostrar(ventilador.get("rpm"), cero=True), "unit": "RPM", "groups": refrigeracion}],
            "cores": nucleos, "topology": topologia, "telemetry": telemetria, "preparation": conflictos_preparacion(tools), "components": componentes, "quick_access": quick,
            "system": tools.get("os_label") or tools.get("os_name") or tools.get("os_family") or "Not detected",
            "gddr6": {**gddr, "sample": muestra, "active": live.gddr6.get("active", False)},
            "rails": rails, "vrm_present": sensores.get("vrm_source") == "pmbus",
            "vrm_repair": regulador_atascado(metricas),
            "links": [{"key": title, "title": title, "url": url} for title, url in ENLACES],
            "repositories": repositorios(),
            "note": {"title": TITLE, "paragraphs": list(PARAGRAPHS), "when": WHEN, "thanks": THANKS, "signature": SIGNATURE},
            "error": ctx.metrics_error, "waiting": not bool(metricas)}


def preparar(ctx, p, shell):
    if not {"components", "governor"}.issubset(p) or set(p) - {"components", "governor", "disable_conflicts"}:
        raise Invalid("params")
    seleccion = p.get("components")
    if not isinstance(seleccion, list) or not seleccion or len(seleccion) > len(CLAVES):
        raise Invalid("components")
    if any(not isinstance(key, str) or key not in CLAVES for key in seleccion) or len(set(seleccion)) != len(seleccion):
        raise Invalid("components")
    if "runtime" not in seleccion or ("cu_manager" in seleccion and "umr" not in seleccion):
        raise Invalid("components")
    governor = choice(p, "governor", ("auto", "cyan", "oberon"))
    desactivar = flag(p, "disable_conflicts") if "disable_conflicts" in p else False

    def ejecutar():
        tools = ctx.service.estado_herramientas_bc250() or {}
        capacidades = tools.get("prepare_components") or {}
        if any(not capacidades.get(key, {}).get("available", True) for key in seleccion):
            raise Invalid("components unavailable")
        plan = build_gpu_dependency_plan(tools, current_governor=None, action="prepare", preference=governor, selected_components=seleccion)
        opciones = {}
        if plan.has_conflicts:
            if not desactivar:
                raise Invalid("GPU governor conflict requires confirmation")
            opciones = {"confirmar_conflictos": True, "desactivar_conflictos": True}
        resultado = ctx.service.instalar_dependencias_bc250(governor_preference=governor, include_pwm="fan_pwm" in seleccion, components=seleccion, **opciones)
        ctx.settings.save_local_config({"gpu_governor": governor})
        return resultado
    return (2 if desactivar else 1), ejecutar


def decky(ctx, p, shell):
    if p:
        raise Invalid("params")

    def ejecutar():
        quick = (ctx.service.estado_herramientas_bc250() or {}).get("quick_access") or {}
        if not quick.get("supported") or not quick.get("decky_plugin_root_safe", True):
            raise Invalid("Decky unavailable")
        plugin = quick.get("decky_detected") and quick.get("decky_frontend_compatible", True)
        return ctx.service.preparar_quick_access_steamos(install_decky=not plugin)
    return 2, ejecutar


def reparar_vrm(ctx, p, shell):
    if p:
        raise Invalid("params")
    return 1, ctx.service.reiniciar_sensor_vrm


LECTURAS = {"dashboard": (3, leer)}
ACCIONES = {"panel.prepare": preparar, "panel.decky": decky, "panel.repair_vrm": reparar_vrm}


def repositorios():
    from frontends.desktop.core.official_repositories import OFFICIAL_REPOSITORIES
    return [{"title": title, "detail": repo, "url": url} for title, repo, url in OFFICIAL_REPOSITORIES]


def preparar_memoria(ctx, p, shell):
    if p:
        raise Invalid("params")
    return 1, lambda: shell(ctx.service.comando_preparar_gddr6_memory_temp())


def reparar_telemetria(ctx, p, shell):
    if p:
        raise Invalid("params")
    return 1, ctx.service.reparar_telemetria_8core


def actualizacion(web, parametros):
    from bc250cc.infrastructure.release_check import check_for_update, RELEASES_PAGE_URL
    status = check_for_update()
    return {"available": status.update_available, "version": status.published,
            "url": RELEASES_PAGE_URL, "detail": "See what's new"}


CONSULTAS = {"panel.update": actualizacion}
ACCIONES.update({"gddr6.prepare": preparar_memoria, "panel.repair_telemetry": reparar_telemetria})


def regulador_atascado(metricas):
    sonda = (metricas.get("sensors") or {}).get("vrm_probe") or metricas.get("vrm_probe") or {}
    return any(isinstance(rail, dict) and (rail.get("implausible") or rail.get("unresponsive"))
               for rail in (sonda.get("rails") or {}).values())


def presentar_telemetria(gpu, tools):
    from frontends.desktop.core.error_diagnostics import (TELEMETRY_GUIDE_TITLE, TELEMETRY_GUIDE_BODY,
        TELEMETRY_GUIDE_PATCH_OFF, TELEMETRY_GUIDE_PATCH_ON, TELEMETRY_GUIDE_BAZZITE_NOTE)
    apu = gpu.get("apu_telemetry") or {}
    reparacion = (tools.get("system_setup") or {}).get("telemetry") or {}
    compatible = not apu or (apu.get("parameters") or {}).get("cs_legacy_8core_metrics") is not None
    pendiente = bool(reparacion.get("reboot_required") and not reparacion.get("active") and compatible)
    disponible = bool(reparacion.get("available", True) and compatible)
    desajuste = bool(apu.get("layout_mismatch_suspected"))
    recomendacion = apu.get("recommendation")
    pasos = tr(TELEMETRY_GUIDE_PATCH_OFF) if recomendacion == "disable_smu_reporting_patch" else tr_format(TELEMETRY_GUIDE_PATCH_ON, page=tr("Firmware (BIOS)"))
    if recomendacion not in ("disable_smu_reporting_patch", "enable_smu_reporting_patch"):
        pasos += "\n\n" + tr(TELEMETRY_GUIDE_BAZZITE_NOTE)
    return {"visible": desajuste or pendiente, "pending": pendiente, "available": disponible,
            "label": "Restart to finish telemetry repair" if pendiente else "Repair BC250 telemetry" if disponible else "How to fix BC250 telemetry",
            "title": TELEMETRY_GUIDE_TITLE, "detail": tr(TELEMETRY_GUIDE_BODY) + "\n\n" + pasos}


def conflictos_preparacion(tools):
    plan = build_gpu_dependency_plan(tools, current_governor=None, action="prepare", preference="auto")
    mensaje = tr_format("{governors} is active or enabled. Running two GPU frequency governors can crash the GPU or cause a green screen at boot. Stop and disable it before preparing {selected_governor}?",
                        governors=", ".join(plan.conflicts), selected_governor=plan.resolved_governor) if plan.has_conflicts else ""
    return {"conflicts": list(plan.conflicts), "message": mensaje}
