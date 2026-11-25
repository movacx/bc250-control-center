"""Topología WGP, disponibilidad y balance: mismas reglas que el escritorio, sin Qt."""
from dataclasses import asdict
import json

from frontends.desktop.core.compute_units_presenter import present_compute_units_state, plan_cu_action_availability, cus_found_at_driver_start
from frontends.desktop.core.cu_balance import balanced_masks, engine_balance
from bc250cc.application.gpu.telemetry import present_gpu_telemetry
from bc250cc.application.system.temperature_unit import localize_temperature_text
from frontends.tui.i18n import tr, tr_format

AVISO_KERNEL = (
    "The BC-250 kernel manages the compute units (amdgpu.bc250_cc_write_mode=3): "
    "it unlocked all of them at boot. This page is read-only while that boot option "
    "is set; umr and the live manager are not needed. To change the routing, turn "
    "the kernel CU unlock off in Additional settings and reboot."
)


GUIA_VALIDACION = '1. Save open work, then press Unlock / Sync to read the live WGP table.\n\n2. Start from the factory layout and enable only one additional WGP pair (2 CUs) at a time. Apply it live; do not save it for boot yet.\n\n3. Run FurMark or another heavy 3D workload for an initial 15-minute pass. Watch for artifacts, freezes, black screens, application crashes, or an amdgpu reset.\n\n4. If the test fails, disable the most recently added WGP pair and repeat. The faulty pair can differ from one BC-250 to another.\n\n5. FurMark FPS does not prove that GFX1013 async compute works. FurMark is useful here to expose unstable CUs; async compute must be checked with a game or workload that actually uses graphics and compute queues concurrently.\n\n6. After the initial pass, test real games and workloads for longer. Only then use Save selection and Install service.'


def confirmaciones():
    fuentes = {
        "apply": ("Apply WGP routing table", "The selected WGP pairs will be written through the official live manager. The application will verify the resulting SPI table before reporting success."),
        "save": ("Save selected boot table", "The selected WGP table will be applied now, verified, and saved to /etc/bc250-cu-live-manager.conf. The boot service is installed separately."),
        "install_service": ("Install boot restore service", "The official systemd service will be installed and enabled. Save the intended live table first so the correct layout is restored after reboot."),
        "remove_service": ("Remove boot restore service", "The service and its saved configuration will be removed. The current live WGP routing remains active until reboot or another live action changes it."),
        "factory_repair": ("Restore factory 24 CU routing", "The live SPI table will be rebuilt from the amdgpu boot CU topology. Any saved Compute Units boot service and its configuration will be removed first, so an obsolete /usr/local/bin service cannot restore a broken layout after reboot."),
        "apply_saved": ("Apply saved boot layout now", "The WGP masks stored in /etc/bc250-cu-live-manager.conf will replace the current live routing table."),
    }
    return {clave: {"title": titulo, "message": mensaje} for clave, (titulo, mensaje) in fuentes.items()}


def seleccion(estado, valores):
    vivos = estado.get("masks") or [0] * 4
    pendientes = sum((a ^ b).bit_count() for a, b in zip(valores, vivos))
    balance = engine_balance(valores)
    plantilla = ("SE0 {se0} · SE1 {se1} CUs — balanced: every active CU adds performance." if balance.balanced else
        "SE0 {se0} · SE1 {se1} CUs — unbalanced: performs like {effective} CUs; {idle} CUs on the stronger engine only add heat.")
    detalle = tr_format(plantilla, se0=balance.se0, se1=balance.se1, effective=balance.effective, idle=balance.idle)
    filas = []
    drivers = estado.get("driver_masks") or [0]*4
    originales = estado.get("rows") or []
    for i, mascara in enumerate(valores):
        celdas = []
        for wgp in range(5):
            activo, driver = bool(mascara & (1 << wgp)), bool(drivers[i] & (1 << wgp))
            token = "D+" if activo and driver else "S+" if activo else "D!" if driver else "--"
            celdas.append({"token": token, "label": "ROUTED" if activo else "BLOCKED" if driver else "OFF"})
        origen = originales[i] if i < len(originales) else {}
        filas.append({"name": f"SE{i // 2}.SH{i % 2}", "cells": celdas, "count": f"{mascara.bit_count() * 2} / 10",
                      "live": f"0x{vivos[i]:02x}", "target": f"0x{mascara:02x}", "driver": f"0x{drivers[i]:02x}",
                      "cc": str(origen.get("cc") or "--")})
    return {"rows": filas, "target": balance.total, "pending": pendientes, "balance_detail": detalle,
            "summary": tr_format("Target: {count} / 40 CUs", count=balance.total) + "\n" + detalle + "\n" + tr("Masks") + ": " + ", ".join(f"0x{v:02x}" for v in valores),
            "balanced": balance.balanced, "balanced_masks": balanced_masks(valores, estado.get("driver_masks") or [0]*4),
            "availability": asdict(plan_cu_action_availability(estado, pending_wgps=pendientes, busy=False))}


def telemetria(ctx, presentacion):
    gpu = ctx.service.estado_bc250() or {}
    perf = ctx.service.rendimiento() or {}
    vista = present_gpu_telemetry(gpu, perf)
    def dicho(texto):
        return texto.template if texto.literal else tr_format(texto.template, **dict(texto.values))
    def lectura(clave, unidad, decimales=0):
        valor = perf.get(clave)
        return f"{float(valor):.{decimales}f} {unidad}" if isinstance(valor, (int, float)) and valor > 0 else tr("Not detected")
    pmbus = perf.get("vrm_source") == "pmbus"
    potencia = lectura("vrm_gpu_power_w", "W", 1) if pmbus and perf.get("vrm_gpu_power_w") else lectura("gpu_power" if perf.get("gpu_power") else "power_w", "W", 1)
    vrm = lectura("vrm_temp_gpu", "°C") if pmbus and perf.get("vrm_temp_gpu") else lectura("vrm_mos_temp", "°C")
    sclk = gpu.get("sclk_actual")
    config = ctx.settings.read_local_config()
    unidad = config.get("temperature_unit") or config.get("settings/temperature_unit")
    return [{"label": nombre, "value": localize_temperature_text(valor, unidad), "detail": detalle} for nombre, valor, detalle in (
        ("Service", presentacion.service, "optional boot restore"),
        ("Persistence", presentacion.persistence_status, presentacion.persistence_detail),
        ("GPU frequency", f"{int(sclk)} MHz" if sclk else tr("Not detected"), "Current SCLK state"),
        ("GPU load", dicho(vista.utilization_text), "amdgpu busy percentage"),
        ("GPU power", potencia, "VRM GPU · PMBus" if pmbus else str(perf.get("power_label") or "SoC package power")),
        ("GPU temperature", dicho(vista.temperature_text), "GPU edge sensor"),
        ("VRM temperature", vrm, "VRM GPU · PMBus" if pmbus else "VRM MOS"),
        ("Fan speed", lectura("fan_rpm", "RPM"), "RPM observed"))]


def leer(ctx, live):
    try:
        estado = ctx.service.obtener_estado_cu_cache() or {}
        valores = estado.get("masks") or [0]*4
        presentacion = present_compute_units_state(estado, live_masks=valores)
        temprano = cus_found_at_driver_start(estado)
        aviso = tr(AVISO_KERNEL) if estado.get("kernel_managed") else tr_format(
            "The driver already found {count} compute units when it started, more than the usual 24. "
            "The BIOS or another boot program may have turned them on: change them there, or both will keep setting them.", count=temprano) if temprano else ""
        return {"guide": {"title": "CU stability validation", "message": GUIA_VALIDACION, "detail": "Opening this guide does not change the live WGP table."}, "confirmations": confirmaciones(), "cu": estado, "presentation": asdict(presentacion), "selection": seleccion(estado, valores), "notice": aviso, "telemetry": telemetria(ctx, presentacion)}
    except Exception as error:
        return {"error": str(error)}


def consultar(web, p):
    from frontends.web.actions import masks, Invalid
    try:
        valores = masks({"masks": json.loads(p.get("masks", "[]"))})
    except (ValueError, TypeError):
        raise Invalid("masks")
    return seleccion(web.ctx.service.obtener_estado_cu_cache() or {}, valores)


def _permitir(ctx, nombre, valores=None):
    from frontends.web.actions import Invalid
    estado = ctx.service.obtener_estado_cu_cache() or {}
    valores = valores if valores is not None else estado.get("masks") or [0]*4
    plan = seleccion(estado, valores)["availability"]
    if not plan.get(nombre):
        raise Invalid(estado.get("privileged_backend_reason") or "CU write actions are locked until a verified root-owned backend is installed.")


def aplicar(ctx, p, shell):
    from frontends.web.actions import masks
    valores = masks(p)
    def trabajo():
        _permitir(ctx, "apply_live", valores)
        return ctx.service.aplicar_tabla_cu(valores)
    return 2, trabajo


def guardar(ctx, p, shell):
    from frontends.web.actions import masks
    valores = masks(p)
    def trabajo():
        _permitir(ctx, "save_boot", valores)
        return ctx.service.guardar_tabla_cu(valores)
    return 2, trabajo


def accion(ctx, p, shell):
    from frontends.web.actions import choice
    nombre = choice(p, "name", ("install_service", "remove_service", "factory", "factory_repair", "apply_saved"))
    def trabajo():
        _permitir(ctx, "restore_factory" if nombre in ("factory", "factory_repair") else nombre)
        return ctx.service.ejecutar_accion_cu_grafica(nombre)
    return 2 if nombre in ("factory", "factory_repair") else 1, trabajo


def preparar(ctx, p, shell):
    return 1, lambda: ctx.service.instalar_dependencias_bc250(components={"cu_manager"})


def estado_crudo(ctx, p, shell):
    return 0, lambda: str((ctx.service.obtener_estado_cu_cache() or {}).get("raw") or tr("No authorized raw CU status is available yet."))


LECTURAS = {"cu": (3, leer)}
CONSULTAS = {"cu.selection": consultar}
ACCIONES = {"cu.apply": aplicar, "cu.save": guardar, "cu.action": accion,
            "cu.prepare": preparar, "cu.raw": estado_crudo,
            "cu.sync": lambda ctx, p, shell: (1, ctx.service.obtener_estado_cu)}
