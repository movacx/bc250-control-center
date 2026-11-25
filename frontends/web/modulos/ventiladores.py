"""Tablero de canales y herramientas de ventilación, sin dependencias de Qt."""
import json
import time
from dataclasses import asdict

from bc250cc.application.fan import board_view as vista
from bc250cc.application.fan.board_actions import FanBoardActions
from bc250cc.application.fan.calibration import calibrate
from bc250cc.domain.fan.profile_exchange import (
    MAX_DOCUMENT_BYTES, channel_profiles_document, decky_fan_profiles, decky_fan_raised,
    imported_profile_updates, parse_channel_profiles_document,
)
from frontends.tui.i18n import tr
from frontends.tui.pages.fans import live_temperatures
from frontends.web.actions import Invalid, choice, flag, number

PREDETERMINADOS = ({"key": "quiet", "name": "Quiet", "percent": 45},
                  {"key": "balanced", "name": "Balanced", "percent": 60},
                  {"key": "maximum", "name": "Maximum", "percent": 100})


def perfiles(config):
    guardados = config.get("web_fan_profiles") or []
    por_clave = {fila.get("key"): fila for fila in guardados if isinstance(fila, dict)}
    return [por_clave.get(fila["key"], fila) for fila in PREDETERMINADOS]


def leer(ctx, live):
    # Importación local: data importa el registro de módulos al arrancar.
    from frontends.web.data import _fans
    fans = ctx.service.estado_fans_bc250() or {}
    sistema = ctx.service.estado_control_fan_sistema() or {}
    config = ctx.settings.read_local_config()
    resultado = _fans({"fans": fans, "system": sistema, "config": config}, ctx)
    resultado["temperatures"] = live_temperatures(ctx)
    for canal in resultado["channels"]:
        canal["resume"] = vista.channel_status(sistema, canal["pwm"]).get("state") == "override"
    resultado["speed_profiles"] = perfiles(config)
    resultado["calibration"] = config.get("web_fan_calibration") or {}
    return resultado


def diagnostico(web, p):
    tipo = choice(p, "view", ("paths", "status", "export"))
    config = web.ctx.settings.read_local_config()
    if tipo == "export":
        documento = channel_profiles_document(perfiles(config), config)
        return {"text": json.dumps(documento, ensure_ascii=False, indent=2)}
    estado = web.ctx.service.estado_fans_bc250() or {}
    # Rutas descubiertas por el servicio, nunca recibidas del navegador.
    if tipo == "paths":
        return {"tabs": rutas_pwm(estado)}
    return {"text": json.dumps(estado, ensure_ascii=False, indent=2, default=str)}


def herramientas(ctx, p, shell):
    operacion = choice(p, "operation", ("prepare", "readonly", "disable", "handoff", "decky"))
    if set(p) != ({"operation", "enabled"} if operacion == "handoff" else {"operation"}):
        raise Invalid("params")
    if operacion == "handoff":
        ceder = flag(p, "enabled")
        return 2, lambda: ctx.service.ceder_fan_a_otro_programa(ceder)
    if operacion == "decky":
        return 1, lambda: exportar_decky(ctx)
    metodos = {"prepare": "preparar_nct6687_control_pwm", "readonly": "cargar_nct6683_solo_lectura",
               "disable": "desactivar_nct6687_control_pwm"}
    # Estos servicios abren el flujo de trabajo en la consola embebida del trabajador.
    return 2, getattr(ctx.service, metodos[operacion])


def exportar_decky(ctx):
    from frontends.desktop.core.decky_export_feedback import export_and_check_plugin, export_message, fan_export_notes
    guardados = perfiles(ctx.settings.read_local_config())
    publicados = decky_fan_profiles(guardados)
    instalado = export_and_check_plugin(ctx.service, lambda: ctx.service.exportar_perfiles_fan_decky(publicados))
    elevados = [(tr(nombre), pedido, publicado) for nombre, pedido, publicado in decky_fan_raised(guardados)]
    return export_message(instalado, fan_export_notes(elevados))


def importar(ctx, p):
    texto = p.get("text")
    reemplazar = flag(p, "replace")
    if not isinstance(texto, str) or len(texto.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise Invalid("text")
    try:
        paquete = parse_channel_profiles_document(json.loads(texto))
        config = ctx.settings.read_local_config()
        cambios = imported_profile_updates(config, paquete, snapshot_name=tr("Imported configuration"))
        reservados = {tr(nombre).casefold() for nombre in ("Quiet", "Balanced", "Performance")}
        if any(fila["name"].casefold() in reservados for fila in cambios["fan_modes"]):
            raise Invalid("Reserved profile name")
        existentes = {fila["name"].casefold(): fila for fila in config.get("fan_modes", [])}
        if not reemplazar and any(fila["name"].casefold() in existentes and fila != existentes[fila["name"].casefold()]
                                  for fila in cambios["fan_modes"]):
            raise Invalid("Replace fan profile?")
        cambios["web_fan_profiles"] = paquete["profiles"]
        ctx.settings.save_local_config(cambios)
    except (ValueError, TypeError, KeyError) as error:
        raise Invalid(str(error)) from error


def calibrar(ctx, p, shell):
    pwm = number(p, "pwm")
    if set(p) != {"pwm"}:
        raise Invalid("params")

    def ejecutar():
        tablero = FanBoardActions(ctx.service, ctx.settings)
        estado = tablero.snapshot()
        canal = tablero.board().channels.get(str(pwm), {})
        fan = vista.fan_rows(tablero.fans()).get(pwm, {})
        if estado.get("external") or canal.get("role") == "pump" or not vista.is_writable(fan):
            raise Invalid("PWM control is not ready")
        ctx.settings.save_local_config({"web_fan_calibration": {}})

        def escribir(porcentaje):
            valor = vista.percent_to_pwm(porcentaje)
            respuesta = ctx.service.aplicar_pwm_fan(pwm, valor)
            error, valores = vista.verify_pwm_result(respuesta, pwm=pwm, raw=valor)
            if error:
                raise Invalid(error)

        def rpm():
            fila = vista.fan_rows(ctx.service.estado_fans_bc250()).get(pwm, {})
            valor = fila.get("rpm")
            return int(valor) if valor is not None else None

        def temperatura():
            # Muestra fresca: exige al menos un sensor APU como el calibrador del escritorio.
            metricas = ctx.service.metricas_tiempo_real() or {}
            valores = [vista.finite_number((metricas.get(nombre) or {}).get("temperature_c")) for nombre in ("gpu", "cpu")]
            apu = [valor for valor in valores if valor is not None and valor > 0]
            if not apu:
                return None
            sensores = metricas.get("sensors") or {}
            otras = [vista.finite_number(sensores.get(clave)) for clave in ("vrm_temperature_c", "board_temperature_c")]
            return max(apu + [valor for valor in otras if valor is not None])

        resultado = calibrate(write=escribir, read_rpm=rpm, hottest_c=temperatura, sleep=time.sleep)
        datos = {"pwm": pwm, **asdict(resultado)}
        ctx.settings.save_local_config({"web_fan_calibration": datos})
        if resultado.aborted:
            raise Invalid(resultado.aborted)
        return tr("Calibration finished")
    return 2, ejecutar


LECTURAS = {"fans": (2, leer)}
CONSULTAS = {"fans.diagnostics": diagnostico}
ACCIONES = {"fans.tools": herramientas, "fans.calibrate": calibrar}
AJUSTES = {"fans.import": importar}


def aplicar(ctx, p, shell):
    from frontends.web.actions import _entry, _text, _said
    from bc250cc.domain.fan.channels import LABEL_MAX_LENGTH
    pwm = number(p, "pwm")
    entrada = _entry(p)
    nombre = _text(p, "label", LABEL_MAX_LENGTH, empty=True)

    def ejecutar():
        tablero = FanBoardActions(ctx.service, ctx.settings)
        resultado = tablero.apply_channel(pwm, entrada)
        tablero.rename(pwm, nombre)
        return _said(resultado)
    nivel = 2 if entrada and entrada.get("mode") == "fixed" and entrada.get("percent", 100) < vista.LOW_DUTY_CONFIRM_PERCENT else 1
    return nivel, ejecutar


ACCIONES["fans.apply"] = aplicar


def validar(web, p):
    from frontends.web.actions import _entry
    texto = p.get("entry", "")
    if not isinstance(texto, str) or len(texto) > 4096:
        raise Invalid("entry")
    try:
        entrada = _entry({"entry": json.loads(texto)})
        from bc250cc.domain.fan import engine
        normalizada = engine.validate_policy({"schema": 2, "channels": {"1": entrada}})["channels"]["1"] if entrada else {"mode": "firmware"}
        return {"valid": True, "error": "", "entry": normalizada}
    except (ValueError, TypeError) as error:
        return {"valid": False, "error": str(error)}


CONSULTAS["fans.validate"] = validar


def rutas_pwm(estado):
    """El mismo informe de detección, persistencia y verificación, sin widgets."""
    from pathlib import Path
    from bc250cc.platform.init.services import detect_init_manager

    sensores = estado.get("sensores") or {}
    modulos = estado.get("modulos") or {}
    rutas = []
    for campo in ("pwms", "fans"):
        for fila in sensores.get(campo) or []:
            ruta = fila.get("path", fila.get("pwm_path")) if isinstance(fila, dict) else None
            if ruta and ruta not in rutas:
                rutas.append(ruta)

    def existentes(candidatos):
        encontrados = [ruta for ruta in candidatos if Path(ruta).is_file()]
        return "\n".join(encontrados)

    def informe(campos):
        return "\n\n".join(f"{tr(titulo)}\n{valor}" for titulo, valor in campos)

    ayudantes = existentes(("/usr/libexec/bc250-control-center/bc250-fan-pwm-helper",
                            "/usr/local/libexec/bc250-control-center/bc250-fan-pwm-helper"))
    configuraciones = existentes(tuple(f"/etc/{carpeta}/{nombre}.conf" for carpeta, nombre in (
        ("modprobe.d", "nct6683"), ("modprobe.d", "nct6687"), ("modprobe.d", "sensors"),
        ("modules-load.d", "nct6683"), ("modules-load.d", "nct6687"), ("modules-load.d", "99-sensors"))))
    detectado = informe((
        ("Live Linux detection", tr("Values below are evidence from the latest NCT scan. Missing data is shown as missing; no path is guessed.")),
        ("Chip", sensores.get("chip") or tr("Not detected")),
        ("Hwmon route", sensores.get("path") or tr("No NCT hwmon route was reported by the latest scan.")),
        ("Loaded modules", f"nct6683={bool(modulos.get('nct6683'))} · nct6687={bool(modulos.get('nct6687'))}"),
        ("Reported PWM files", "\n".join(rutas) or tr("No PWM file was reported by the latest scan.")),
        ("Installed PWM helpers", ayudantes or tr("No installed root PWM helper was detected.")),
        ("Detected fan configuration", configuraciones or tr("No BC250 fan configuration file is currently detected.")),
    ))
    inicio = detect_init_manager()
    if inicio.available and inicio.kind in ("systemd", "openrc"):
        openrc = inicio.kind == "openrc"
        candidatos = (("/etc/init.d/nct6687-load", "/etc/conf.d/nct6687-load", "/usr/local/sbin/bc250-load-nct6687") if openrc
                      else ("/etc/systemd/system/nct6687-load.service", "/usr/local/sbin/bc250-load-nct6687"))
        persistencia = informe((
            ("Active manager", inicio.display_name),
            ("Detected service files" if openrc else "Detected unit files", existentes(candidatos) or tr(
                "No BC250 NCT6687 OpenRC service file is currently detected." if openrc else "No BC250 NCT6687 systemd unit file is currently detected.")),
            ("Status command", "rc-service nct6687-load status" if openrc else "systemctl status nct6687-load.service --no-pager"),
            ("Runlevel command" if openrc else "Journal command", "rc-update show default" if openrc else "journalctl -b -u nct6687-load.service --no-pager"),
        ))
    else:
        persistencia = informe((("Persistence unavailable", tr("No supported active init manager was detected. This window will not suggest a service command.")),
                               ("Detection", inicio.detail), ("Current capability", tr("Live sensor inspection remains read-only."))))
    verificacion = informe((
        ("Read-only verification", tr("Copy a command only when you need more diagnostics. None of these commands changes fan mode, duty, modules, or services.")),
        ("Modules", 'lsmod | grep -E "nct6683|nct6687"'), ("Driver metadata", "modinfo nct6687"),
        ("Sensors", 'sensors | sed -n "/nct668/,+45p"'),
        ("Hwmon files", "find /sys/class/hwmon -maxdepth 2 -name 'pwm*_enable' -o -name 'fan*_input'"),
    ))
    return [{"key": clave, "label": etiqueta, "text": texto} for clave, etiqueta, texto in (
        ("detected", "Detected", detectado), ("persistence", "Persistence", persistencia), ("verification", "Verification", verificacion))]
