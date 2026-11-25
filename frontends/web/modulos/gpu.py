"""Gobernador y laboratorio: presentación sin Qt y operaciones cerradas."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from bc250cc.application.gpu.diagnostics import present_gpu_diagnostics
from bc250cc.application.gpu.range_policy import RangeEvidence, validate_gpu_range
from bc250cc.application.gpu.service_action import plan_gpu_service_action
from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.application.gpu.voltage_lab_state import build_voltage_lab_state
from bc250cc.application.gpu.voltage_table import build_voltage_table_plan
from bc250cc.domain.gpu.oberon import (
    OBERON_DESKTOP_PROFILES,
)
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    GOVERNOR_DEFAULT_VOLTAGES,
)
from frontends.desktop.core.temperature_unit import format_temperature
from frontends.desktop.i18n import governor_fix_label, shipped_name
from frontends.tui.i18n import tr, tr_format

PREDEFINIDOS = (
    {"key": "balanced", "name": "Balanced", "min": 500, "max": 1500},
    {"key": "gaming", "name": "Gaming", "min": 1000, "max": 1850},
    {"key": "benchmark", "name": "Benchmark", "min": 1000, "max": 2000},
)


def perfiles(ctx, estado=None):
    guardados = ctx.settings.read_local_config().get("tui_gpu_profiles") or []
    por_clave = {p.get("key"): p for p in guardados if isinstance(p, dict)}
    resultado = []
    oberon = (estado or {}).get("governor_backend") == "oberon-governor"
    for indice, original in enumerate(PREDEFINIDOS):
        perfil = dict(original if oberon else por_clave.get(original["key"], original))
        try:
            validar_perfil(perfil)
        except ValueError:
            perfil = dict(original)
        if oberon:
            perfil["min"], perfil["max"] = OBERON_DESKTOP_PROFILES[indice]
        resultado.append(perfil)
    return resultado


def validar_perfil(p):
    from frontends.web.actions import Invalid, _text, choice, number
    clave = choice(p, "key", tuple(v["key"] for v in PREDEFINIDOS))
    nombre = _text(p, "name", 28)
    bajo, alto = number(p, "min", "gpu"), number(p, "max", "gpu")
    if bajo > alto or bajo < 500 or alto > 2400:
        raise Invalid("max")
    return {"key": clave, "name": nombre, "min": bajo, "max": alto}


def guardar_perfil(ctx, p):
    perfil = validar_perfil(p)
    original = next(v for v in PREDEFINIDOS if v["key"] == perfil["key"])
    perfil["name"] = shipped_name(perfil["name"], original["name"])
    valores = [perfil if v["key"] == perfil["key"] else v for v in perfiles(ctx)]
    ctx.settings.save_local_config({"tui_gpu_profiles": valores})


def leer(ctx, live):
    try:
        estado = ctx.service.estado_bc250() or {}
        lab = build_voltage_lab_state(estado)
        curva = dict(GOVERNOR_DEFAULT_VOLTAGES)
        curva.update(dict(lab.current_voltages))
        tarjetas = []
        for perfil in perfiles(ctx, estado):
            def voltaje(f):
                punto = min(curva, key=lambda v: abs(v - f))
                return curva[punto]
            a, b = voltaje(perfil["min"]), voltaje(perfil["max"])
            texto = "1000 mV" if lab.is_oberon else f"{a} – {b} mV" if a != b else f"{a} mV"
            tarjetas.append({**perfil, "voltage": texto})
        high = estado.get("high_frequency_points") or {}
        techo = min(2400 if high.get("enabled") else 2000, high.get("ceiling_mhz") or 2400)
        diagnosticos = present_gpu_diagnostics(estado, detailed=True)
        def dicho(texto):
            return texto.template if texto.literal else tr_format(texto.template, **dict(texto.values))
        filas = [{"label": tr(clave), "value": dicho(linea.value), "detail": dicho(linea.detail)}
                 for clave, linea in (("Device", diagnosticos.device), ("Driver", diagnosticos.driver),
                                      ("Configuration", diagnosticos.config), ("Voltage curve", diagnosticos.curve),
                                      ("Missing voltage", diagnosticos.missing), ("Duplicate frequencies", diagnosticos.duplicates),
                                      ("Power state", diagnosticos.power))]
        apertura = lab.applied_level if lab.applied_level in (1, 2, 3) else 1 if lab.applied_level == 0 else -1
        gpu = (getattr(ctx, "metrics", None) or {}).get("gpu") or {}
        bajo, alto = int(estado.get("current_min") or 0), int(estado.get("current_max") or 0)
        sin_respuesta = estado.get("dbus_responsive") is False
        fichas = [
            ("Core clock", f"{estado.get('sclk_actual') or 0} MHz", "Current SCLK state"),
            ("GPU voltage", f"{estado.get('voltaje_actual') or 0} mV", "OD / SMU telemetry"),
            ("Temperature", format_temperature(float(gpu.get("temperature_c") or 0)), "hwmon"),
            ("GPU load", f"{round(float(gpu.get('usage_percent') or 0))} %", "amdgpu activity"),
            ("Memory clock", f"{estado.get('mclk_actual') or 0} MHz", "Current MCLK state"),
            ("Active range", f"{bajo}–{alto} MHz" if bajo > 0 and alto > 0 else "--",
             "Cyan is not answering" if sin_respuesta else "Persisted on hardware"),
        ]
        lecturas = [{"label": tr(nombre), "value": valor, "detail": tr(nota)} for nombre, valor, nota in fichas]
        return {
            **estado, "tiles": lecturas, "empty": not bool(estado), "opening_level": apertura,
            "profiles": tarjetas, "ceiling": techo, "voltage_lab": asdict(lab),
            "fix_labels": {"metrics": governor_fix_label("metrics"), "frequency": governor_fix_label("frequency")},
            "active_points": tr_format(
                "{active} of {total} in config.toml",
                active=sum(f <= techo for f, _v in lab.points), total=len(lab.points),
            ),
            "availability": disponibilidad(estado), "service_plans": planes_servicio(estado), "diagnostics": filas,
            "rail": [{"frequency": f, "voltage": v} for f, v in GOVERNOR_DEFAULT_VOLTAGES.items()],
            "minimum_mv": CUSTOM_VOLTAGE_MIN_MV, "maximum_mv": CUSTOM_VOLTAGE_MAX_MV,
        }
    except Exception:
        return {"error": tr("Read error")}


def planes_servicio(estado):
    resultado = {}
    for accion in ("activar", "reiniciar", "desactivar"):
        plan = plan_gpu_service_action(accion, backend=estado.get("governor_backend"),
            incompatible_governors=(estado.get("tools") or {}).get("incompatible_gpu_governors") or ())
        resultado[accion] = {"title": plan.label, "message": tr_format(plan.description, **dict(plan.description_values)),
                             "risk": plan.has_conflicts or accion == "desactivar"}
    return resultado


def laboratorio(web, p):
    from frontends.web.actions import Invalid
    try:
        nivel = int(p.get("level", "0"))
    except (ValueError, TypeError):
        raise Invalid("level")
    if nivel not in range(-1, 7):
        raise Invalid("level")
    estado = web.ctx.service.estado_bc250() or {}
    lab = build_voltage_lab_state(estado)
    personalizados = dict(lab.custom_defaults)
    if p.get("values"):
        from frontends.web.actions import gpu_voltage_custom
        if len(p["values"]) > 4096:
            raise Invalid("values")
        try:
            valores = json.loads(p["values"])
        except (ValueError, TypeError):
            raise Invalid("values")
        gpu_voltage_custom(web.ctx, {"values": valores}, None)  # valida la forma; no ejecuta
        if not {int(f) for f in valores}.issubset(lab.editable_frequencies):
            raise Invalid("active voltage points")
        personalizados.update({int(f): v for f, v in valores.items()})
    puntos = dict(lab.points)
    if nivel >= 0:
        for f in lab.profile_frequencies:
            puntos.setdefault(f, 0)
    tabla = build_voltage_table_plan(points=sorted(puntos.items()), selected_level=nivel,
        editable_frequencies=lab.editable_frequencies, profile_frequencies=lab.profile_frequencies,
        custom_values=personalizados, packaged_voltages=GOVERNOR_DEFAULT_VOLTAGES,
        detected_level=lab.detected_level, is_oberon=lab.is_oberon)
    plan = plan_voltage_apply(level=nivel, editable_frequencies=lab.editable_frequencies,
        profile_frequencies=lab.profile_frequencies, current_voltages=dict(lab.current_voltages),
        custom_values=personalizados, is_oberon=lab.is_oberon)
    modificados = sum(v.proposed != v.current for v in tabla.rows)
    error = ""
    if plan.violation:
        error = tr(
            "The voltage curve decreases while frequency rises. No profile will be applied until the TOML "
            "is corrected and the governor is restarted."
        )
    elif not lab.is_oberon and not disponibilidad(estado)["voltage"]:
        error = tr("The Cyan governor must be active before changing its voltage curve.")
    return {
        "rows": [asdict(v) for v in tabla.rows],
        "available": plan.available and disponibilidad(estado)["voltage"] and not plan.violation,
        "changed": modificados, "peak": plan.maximum_voltage, **confirmacion_voltaje(nivel),
        "error": error, "detail": tr_format(tabla.detail_template, **dict(tabla.detail_values)),
    }


def confirmacion_voltaje(nivel):
    if nivel == -1:
        titulo = tr("Custom voltage laboratory")
        mensaje = tr("Only mV voltages in existing TOML safe-points are modified.") + " " + tr(
            "A timestamped backup is created, the governor restarts, and the previous D-Bus range is restored only after confirmation."
        )
    elif nivel == 0:
        titulo = tr_format("Apply GPU voltage Level {level}", level=0)
        mensaje = tr(('This restores every packaged original voltage and disables the +2000 MHz TOML points. If the '
            'current range exceeds 2000 MHz, it is safely limited after the governor restarts. A backup is '
            'created first.'))
    else:
        titulo = tr_format("Apply GPU voltage Level {level}", level=nivel)
        mensaje = tr_format(('This restores the complete packaged governor curve, then adds +{added} mV to every safe-point '
            'from {start} MHz. A backup is created before the governor restarts.'), added=nivel*10, start=2050)
    return {"confirmation": {"title": titulo,
        "message": mensaje + " " + tr("Stop every game, benchmark, and 3D workload before continuing.")}}


def configuracion(web, p):
    # No se acepta una ruta del navegador ni del estado. Solo estos dos archivos de configuración.
    estado = web.ctx.service.estado_bc250() or {}
    ruta = Path("/etc/oberon-config.yaml" if estado.get("governor_backend") == "oberon-governor"
                else "/etc/cyan-skillfish-governor-smu/config.toml")
    try:
        if ruta.is_symlink():
            raise OSError("Governor configuration could not be opened")
        with ruta.open("r", encoding="utf-8") as archivo:
            texto = archivo.read(131073)
        if len(texto) > 131072:
            raise OSError("Governor configuration could not be opened")
        return {"path": str(ruta), "text": texto}
    except OSError:
        return {"path": str(ruta), "error": tr_format(
            "{path} does not exist. Install or repair the selected governor before opening its configuration.", path=str(ruta))}


def disponibilidad(estado):
    conflictos = bool((estado.get("tools") or {}).get("incompatible_gpu_governors"))
    funcionando = estado.get("service_active") == "active"
    arranque = str(estado.get("service_enabled") or "").lower() in ("enabled", "enabled-runtime", "static")
    return {
        "range": bool(estado.get("range_control_ok", estado.get("dbus_ok", estado.get("dbus_connected")))) and not conflictos,
        "high_points": bool((estado.get("high_frequency_points") or {}).get("available")) and not conflictos,
        "voltage": funcionando and estado.get("governor_backend") != "oberon-governor",
        "restart": funcionando,
        "start": not (funcionando and arranque),
        "stop": funcionando or arranque,
        "save_boot": (
            estado.get("governor_backend") != "oberon-governor"
            and 0 < int(estado.get("current_min") or 0) <= int(estado.get("current_max") or 0)
        ),
    }


def evidencia_rango(estado):
    lab = build_voltage_lab_state(estado)
    oberon = lab.is_oberon
    permitido = int(estado.get("allowed_max") or estado.get("config_max_frequency") or estado.get("current_max") or 2000)
    if (estado.get("high_frequency_points") or {}).get("enabled"):
        permitido = max(permitido, max((f for f, _ in lab.points), default=0))
    return RangeEvidence(
        backend=estado.get("governor_backend") or "",
        allowed_min=1000 if oberon else int(estado.get("allowed_min", 300)),
        allowed_max=2000 if oberon else permitido,
        safe_frequencies=tuple(f for f, _ in lab.points),
        safe_voltages=dict(lab.current_voltages),
        packaged_voltages=GOVERNOR_DEFAULT_VOLTAGES,
        lab_frequencies=tuple(GOVERNOR_DEFAULT_VOLTAGES),
        voltage_errors=tuple(estado.get("safe_points_voltage_errors") or ()),
        duplicate_frequencies=tuple(estado.get("safe_points_duplicate_frequencies") or ()),
        missing_voltage=tuple(item["frequency"] for item in estado.get("safe_points_missing_voltage") or ()),
        config_error=str(estado.get("safe_points_error") or ""),
        current_max=int(estado.get("current_max") or 0),
        actual_clock=int(estado.get("sclk_actual") or 0),
        gpu_busy=estado.get("gpu_busy"),
        set_method=(estado.get("cyan_telemetry") or {}).get("set_method") or "smu",
    )


def techo_de(estado):
    altos = estado.get("high_frequency_points") or {}
    return min(2400 if altos.get("enabled") else 2000, altos.get("ceiling_mhz") or 2400)


def validar_rango(estado, bajo, alto):
    from frontends.web.actions import Invalid
    if not disponibilidad(estado)["range"]:
        raise Invalid(tr("Not connected"))
    # El tope de la página: 2000 MHz mientras los puntos altos sigan comentados, y lo que admita el kernel.
    if estado.get("governor_backend") != "oberon-governor" and alto > techo_de(estado):
        raise Invalid(tr_format("Current ceiling {ceiling} MHz per config.toml.", ceiling=techo_de(estado)))
    decision = validate_gpu_range(bajo, alto, evidencia_rango(estado))
    if not decision.valid:
        aviso = decision.notice
        raise Invalid(tr_format(aviso.message, **dict(aviso.values)))
    return decision


def revisar_rango(web, p):
    from frontends.web.actions import Invalid, number
    try:
        parametros = {clave: int(p.get(clave, "")) for clave in ("min", "max")}
    except (ValueError, TypeError):
        raise Invalid("range")
    bajo, alto = number(parametros, "min", "gpu"), number(parametros, "max", "gpu")
    estado = web.ctx.service.estado_bc250() or {}
    decision = validar_rango(estado, bajo, alto)
    oberon = estado.get("governor_backend") == "oberon-governor"
    if oberon:
        mensaje = tr(
            "This updates Oberon's two YAML endpoints to the upstream 1000 mV baseline and restarts the service if it is active."
        )
    else:
        mensaje = ""
    if not oberon and alto > int(estado.get("allowed_max") or 2000):
        mensaje += "\n\n" + tr(
            "Cyan will restart once to load the enabled high safe-points, then the requested D-Bus range will be verified."
        )
    if alto >= 2000:
        mensaje += "\n\n" + tr(
            "High-frequency confirmation: this 2000 MHz range changes live GPU hardware state. "
            "Verify cooling and stability before applying it."
        )
    for aviso in decision.warnings:
        mensaje += "\n\n" + tr_format(aviso.message, **dict(aviso.values))
        if aviso.details:
            mensaje += "\n" + aviso.details
    return {"title": tr_format("Apply {minimum} – {maximum} MHz", minimum=bajo, maximum=alto),
            "message": mensaje.strip(), "risk": alto >= 1850 or bajo >= 2000, "min": bajo, "max": alto}


def aplicar_rango(ctx, p, shell):
    from frontends.web.actions import number
    bajo, alto = number(p, "min", "gpu"), number(p, "max", "gpu")

    def ejecutar():
        validar_rango(ctx.service.estado_bc250() or {}, bajo, alto)
        return ctx.service.aplicar_perfil_gpu(bajo, alto)
    return 2 if alto >= 1850 or bajo >= 2000 else 1, ejecutar


def aplicar_voltaje(ctx, p, shell):
    from frontends.web.actions import Invalid, number
    nivel = number(p, "level")

    def ejecutar():
        estado = ctx.service.estado_bc250() or {}
        validar_voltaje_disponible(estado)
        lab = build_voltage_lab_state(estado)
        plan = plan_voltage_apply(
            level=nivel, editable_frequencies=lab.editable_frequencies, profile_frequencies=lab.profile_frequencies,
            current_voltages=dict(lab.current_voltages), is_oberon=lab.is_oberon,
        )
        if lab.is_oberon or not plan.available or plan.violation:
            raise Invalid(tr("No editable voltage points"))
        return ctx.service.aplicar_laboratorio_voltaje_gpu(nivel)
    return 2, ejecutar


def validar_voltaje_disponible(estado):
    from frontends.web.actions import Invalid
    if not disponibilidad(estado)["voltage"]:
        raise Invalid(tr("The Cyan governor must be active before changing its voltage curve."))


def aplicar_voltaje_personalizado(ctx, p, shell):
    from frontends.web.actions import gpu_voltage_custom
    nivel, trabajo = gpu_voltage_custom(ctx, p, shell)

    def ejecutar():
        validar_voltaje_disponible(ctx.service.estado_bc250() or {})
        return trabajo()
    return nivel, ejecutar


def compatibilidad(ctx, p, shell):
    from frontends.web.actions import Invalid, gpu_compat
    nivel, trabajo = gpu_compat(ctx, p, shell)

    def ejecutar():
        estado = ctx.service.estado_bc250() or {}
        if estado.get("governor_backend") == "oberon-governor":
            raise Invalid(tr("Not available"))
        return trabajo()
    return nivel, ejecutar


def puntos_altos(ctx, p, shell):
    from frontends.web.actions import Invalid, flag
    habilitar = flag(p, "enable")

    def ejecutar():
        estado = ctx.service.estado_bc250() or {}
        if estado.get("governor_backend") == "oberon-governor" or not disponibilidad(estado)["high_points"]:
            raise Invalid(tr("Not available"))
        return ctx.service.alternar_puntos_gpu_altos(habilitar)
    return 2, ejecutar


def guardar_arranque(ctx, p, shell):
    from frontends.web.actions import Invalid
    if p:
        raise Invalid("params")

    def ejecutar():
        if not disponibilidad(ctx.service.estado_bc250() or {})["save_boot"]:
            raise Invalid(tr("Active range unavailable"))
        return ctx.service.guardar_rango_gpu_arranque()
    return 1, ejecutar


def exportar(ctx, p, shell):
    from frontends.desktop.core.decky_export_feedback import (
        export_and_check_plugin,
        export_message,
    )
    def trabajo():
        valores = perfiles(ctx, ctx.service.estado_bc250())

        def exportar_perfiles():
            return ctx.service.exportar_perfiles_gpu_decky(valores)

        presente = export_and_check_plugin(ctx.service, exportar_perfiles)
        return export_message(presente)
    return 1, trabajo


def servicio(ctx, p, shell):
    from frontends.web.actions import GOVERNOR_ACTIONS, choice
    accion = choice(p, "action", GOVERNOR_ACTIONS)
    def trabajo():
        estado = ctx.service.estado_bc250() or {}
        plan = plan_gpu_service_action(accion, backend=estado.get("governor_backend"),
            incompatible_governors=(estado.get("tools") or {}).get("incompatible_gpu_governors") or ())
        permitida = {"reiniciar": "restart", "activar": "start", "desactivar": "stop"}[accion]
        if not disponibilidad(estado)[permitida]:
            from frontends.web.actions import Invalid
            raise Invalid(tr("Not available"))
        return ctx.service.controlar_governor(plan.action, plan.has_conflicts, plan.has_conflicts)
    return 2 if accion == "desactivar" else 1, trabajo


LECTURAS = {"gpu": (3, leer)}
CONSULTAS = {"gpu.laboratorio": laboratorio, "gpu.config": configuracion, "gpu.range": revisar_rango}
AJUSTES = {"gpu.profile": guardar_perfil}
ACCIONES = {
    "gpu.export_decky": exportar, "gpu.service": servicio, "gpu.profile": aplicar_rango,
    "gpu.voltage": aplicar_voltaje, "gpu.voltage_custom": aplicar_voltaje_personalizado,
    "gpu.compat": compatibilidad, "gpu.high_points": puntos_altos, "gpu.save_boot": guardar_arranque,
}
