"""Configuración: las mismas secciones del escritorio, descritas como bloques que la web dibuja.

Un bloque es un diccionario con ``tipo``. Una fila lleva su título, su explicación y un
``control``; un botón lleva una ``orden`` cerrada (acción, ajuste, sección, enlace o texto).
Aquí no se arma ningún comando: las acciones están en ``ACCIONES`` y validan lo que llega.
"""

from __future__ import annotations

import ast
import os
import shutil
from datetime import datetime
from pathlib import Path

from bc250cc.application.system import quick_auth
from bc250cc.infrastructure import SystemdUserService
from bc250cc.infrastructure.apu_telemetry_service import apu_telemetry_state
from bc250cc.infrastructure.gddr6_memory_temp_repository import (
    board_bios_version,
    gddr6_firmware_supported,
)
from bc250cc.infrastructure.governor_conflicts import normalize_governor_preference
from bc250cc.infrastructure.system_setup import MEMORY_SENSOR_OPTION
from bc250cc.infrastructure.vrm_telemetry_reader import (
    kernel_vrm_driver_present,
    sondear_telemetria_vrm,
)
from bc250cc.platform.init.services import detect_init_manager
from bc250cc.platform.packages.strategies.detector import detect_os_info
from bc250cc.shared.version import __version__
from frontends.desktop.core.temperature_unit import use_unit
from frontends.desktop.i18n import (
    LANGUAGE_OPTIONS,
    SUPPORTED_LANGUAGES,
    daemon_details,
    project_overview,
)
from frontends.desktop.theme import (
    ACCENTS,
    STYLES,
    TERMINAL_THEME_GROUPS,
    TERMINAL_THEMES,
    THEMES,
)
from frontends.tui.i18n import tr, tr_format
from frontends.web.actions import Invalid, choice, flag

SERVICIO_DAEMON = "bc250-control-centerd.service"
GOBERNADORES = ("auto", "cyan-skillfish-governor-smu", "oberon-governor")
PAGINAS = ("dashboard", "cpu", "gpu", "cu", "performance", "fans", "processes", "settings")

#: Preferencias propias de la web: clave -> (valores que admite, valor inicial).
PREFERENCIAS = {
    "language": (("auto", *SUPPORTED_LANGUAGES), "auto"),
    "temperature_unit": (("celsius", "fahrenheit"), "celsius"),
    "start_page": (PAGINAS, "dashboard"),
    "reopen_last": ((True, False), True),
    "sidebar_collapsed": ((True, False), False),
    "report_glow": ((True, False), True),
    "theme": (("system", *THEMES), "dark"),
    "style": (STYLES, "formal"),
    "accent": (tuple(ACCENTS), "green"),
    "density": (("comfortable", "compact"), "comfortable"),
    "scale": (tuple(range(70, 151, 10)), 100),
    "gpu_interface": (("original", "modern"), "modern"),
    "embedded_terminal": ((True, False), True),
    "console_auto_hide": ((True, False), False),
    "console_theme": (("app", *TERMINAL_THEMES), "app"),
    "gamepad_navigation": ((True, False), False),
    "gamepad_keypad": ((True, False), True),
    "gddr6_manual": ((True, False), False),
    "vrm_manual": ((True, False), False),
    "detailed_diagnostics": ((True, False), False),
    "welcome_done": ((True, False), False),
}

VRM_REDUNDANTE = ("This kernel reads the regulator itself (bc250_vrm), so the BC250-Telemetry service "
                  "is not needed and cannot open the bus. Remove it here.")
NOTA_GDDR6 = ("The SMU has one mailbox, shared with Cyan and CPU overclocking. If two programs use it "
              "at once the board can freeze until it is unplugged. Nothing is written to the BIOS.")
AVISO_GDDR6 = ("Memory temperature readings will start even while Cyan may be writing to the same SMU mailbox. "
               "That is exactly how these readings used to freeze boards. Use it only if you understand the risk.")
AVISO_DAEMON = {
    True: ("This runs systemctl --user enable --now bc250-control-centerd.service. The daemon records telemetry and "
           "restores the saved fan mode after login: an enabled automatic curve, a named preset or the last manual "
           "speed. It does not apply overclock automatically."),
    False: ("This stops and disables bc250-control-centerd.service for the current user. Saved configuration and "
            "history files are preserved."),
}


# -- preferencias -------------------------------------------------------------------------------

def preferencias(config: dict) -> dict:
    """Lo guardado, o el valor inicial cuando falta o no es válido."""
    guardadas = config.get("web_prefs") if isinstance(config.get("web_prefs"), dict) else {}
    valores = {}
    for clave, (admitidos, inicial) in PREFERENCIAS.items():
        valor = guardadas.get(clave, inicial)
        valores[clave] = valor if valor in admitidos and isinstance(valor, type(inicial)) else inicial
    return valores


def guardar_preferencia(ctx, p) -> None:
    validar_campos(p, {"key", "value"})
    clave = choice(p, "key", tuple(PREFERENCIAS))
    admitidos, inicial = PREFERENCIAS[clave]
    valor = p.get("value")
    if type(valor) is not type(inicial) or valor not in admitidos:
        raise Invalid("value")
    config = ctx.settings.read_local_config()
    nuevas = {**preferencias(config), clave: valor}
    cambios = {"web_prefs": nuevas}
    if clave in ("theme", "accent", "style"):
        cambios.update(web_theme=nuevas["theme"], web_accent=nuevas["accent"], web_style=nuevas["style"])
    ctx.settings.save_local_config(cambios)
    if clave == "temperature_unit":
        use_unit(valor)


def reiniciar_preferencias(ctx, p) -> None:
    if p:
        raise Invalid("params")
    iniciales = {clave: inicial for clave, (_admitidos, inicial) in PREFERENCIAS.items()}
    ctx.settings.save_local_config({"web_prefs": iniciales, "web_theme": iniciales["theme"],
                                    "web_accent": iniciales["accent"], "web_style": iniciales["style"]})


# -- piezas con las que se describe una sección ---------------------------------------------------

def grupo(titulo: str, *bloques) -> dict:
    return {"tipo": "grupo", "titulo": tr(titulo), "bloques": [bloque for bloque in bloques if bloque]}


def fila(titulo: str, detalle: str, control: dict | None = None, **mas) -> dict:
    return {"tipo": "fila", "titulo": tr(titulo), "detalle": tr(detalle), "control": control or {}, **mas}


def lista(clave: str, opciones, valor) -> dict:
    return {"tipo": "lista", "clave": clave, "valor": str(valor),
            "opciones": [{"valor": str(codigo), "nombre": tr(nombre)} for nombre, codigo in opciones]}


def interruptor(clave: str, valor: bool, aviso: dict | None = None) -> dict:
    return {"tipo": "interruptor", "clave": clave, "activo": bool(valor), "aviso": aviso or {}}


def segmentos(clave: str, opciones, valor) -> dict:
    return {**lista(clave, opciones, valor), "tipo": "segmentos"}


def accion(nombre: str, titulo: str, mensaje: str = "", *, peligro: bool = False, **parametros) -> dict:
    return {"orden": "accion", "nombre": nombre, "titulo": tr(titulo), "mensaje": tr(mensaje) if mensaje else tr(titulo),
            "peligro": peligro, "parametros": parametros}


def ajuste(nombre: str, titulo: str, mensaje: str = "", **parametros) -> dict:
    return {"orden": "ajuste", "nombre": nombre, "titulo": tr(titulo), "mensaje": tr(mensaje), "parametros": parametros}


def seccion(nombre: str) -> dict:
    return {"orden": "seccion", "nombre": nombre}


def enlace(direccion: str) -> dict:
    return {"orden": "enlace", "nombre": direccion}


def texto(titulo: str, contenido: str) -> dict:
    return {"orden": "texto", "titulo": tr(titulo), "mensaje": contenido}


def copiar(contenido: str) -> dict:
    return {"orden": "copiar", "mensaje": contenido}


def boton(nombre: str, orden: dict, *, activo: bool = True, clase: str = "normal", traducir: bool = True) -> dict:
    return {"texto": tr(nombre) if traducir else nombre, "orden": orden, "activo": activo, "clase": clase}


def botones(*varios, estado: str = "") -> dict:
    return {"tipo": "botones", "estado": estado, "botones": [uno for uno in varios if uno]}


def parrafo(contenido: str, clase: str = "cuerpo", traducir: bool = True) -> dict:
    return {"tipo": "parrafo", "texto": tr(contenido) if traducir else contenido, "clase": clase}


def titulo(contenido: str, numero: int = 0) -> dict:
    return {"tipo": "titulo", "texto": tr(contenido), "numero": numero}


def puntos(elementos) -> dict:
    return {"tipo": "puntos", "textos": [tr(elemento) for elemento in elementos]}


def comando(contenido: str) -> dict:
    return {"tipo": "comando", "texto": contenido}


def foto(archivo: str, descripcion: str, ancho: int = 560) -> dict:
    return {"tipo": "foto", "archivo": archivo, "texto": tr(descripcion), "ancho": ancho}


REGLA = {"tipo": "regla"}


# -- secciones ------------------------------------------------------------------------------------

def _fila_sin_clave() -> dict:
    activo = quick_auth.enabled()
    orden = accion("settings.quick_auth", quick_auth.TITLE, "" if activo else quick_auth.WARNING,
                   peligro=not activo, enable=not activo)
    return fila(quick_auth.TITLE, quick_auth.DETAIL, botones(boton("Disable" if activo else "Enable", orden)))


def general(ctx, p) -> list:
    idiomas = [(nombre, codigo) for codigo, nombre in LANGUAGE_OPTIONS]
    paginas = [("Dashboard", "dashboard"), ("CPU / SMU", "cpu"), ("GPU Governor", "gpu"), ("Compute Units", "cu"),
               ("Performance", "performance"), ("Fans", "fans"), ("Processes", "processes"), ("Settings", "settings")]
    return [
        grupo("Language",
              fila("Language", "Set the interface language. The change is applied immediately to the interface and its dialogs.",
                   lista("language", idiomas, p["language"])),
              fila("Temperature unit", "How temperatures are shown everywhere in the app. Limits and fan curves are still kept in Celsius.",
                   lista("temperature_unit", [("Celsius", "celsius"), ("Fahrenheit", "fahrenheit")], p["temperature_unit"]))),
        grupo("Startup",
              fila("Start page", "Choose the module to open by default.", lista("start_page", paginas, p["start_page"])),
              fila("Reopen last module", "Restore the last visited module when the application starts.",
                   interruptor("reopen_last", p["reopen_last"])),
              fila("Collapsed sidebar at launch", "Open the main navigation in compact mode.",
                   interruptor("sidebar_collapsed", p["sidebar_collapsed"]))),
        grupo("Permissions", _fila_sin_clave()),
        grupo("Help",
              fila("Guided tour", "Walk through the modules again, with each stop pointing at the control it describes.",
                   botones(boton("Start the tour", {"orden": "recorrido"}))),
              fila("Alert animations", "On the dashboard, the buttons take turns moving: the support button sends out a ping, "
                   "the developer's megaphone sends out sound waves, Ko-fi beats like a heart, and GitHub, Discord and "
                   "Telegram move too. Turn it off to keep them all still.", interruptor("report_glow", p["report_glow"])),
              fila("Reset interface preferences", "",
                   botones(boton("Reset preferences", ajuste("settings.reset", "Reset interface preferences", "Reset preferences"))))),
    ]


def apariencia(ctx, p) -> list:
    return [
        grupo("Theme and color",
              {"tipo": "temas", "valor": p["theme"], "acento": p["accent"],
               "opciones": [{"valor": codigo, "nombre": tr(nombre)} for nombre, codigo in
                            (("System", "system"), ("Light", "light"), ("Dark", "dark"), ("Night blue", "midnight"))]},
              fila("Style", "The register, in any theme. Standard keeps the rounded, lively look. Formal uses deeper, quieter "
                   "colours, squarer corners and flat cards.",
                   segmentos("style", [("Standard", "standard"), ("Formal", "formal")], p["style"])),
              fila("Accent color", "Select the main interface accent used across modules.",
                   {"tipo": "acentos", "clave": "accent", "valor": p["accent"], "opciones": [{"valor": nombre} for nombre in ACCENTS]})),
        grupo("Layout",
              fila("Density", "Comfortable keeps generous spacing. Compact tightens margins, rows and buttons in every module so "
                   "more fits on screen; text keeps its size.",
                   segmentos("density", [("Comfortable", "comfortable"), ("Compact", "compact")], p["density"])),
              fila("Interface scale", "Scale fonts, controls, spacing, and technical panels from 70% to 150%.",
                   {**lista("scale", [(f"{valor}%", valor) for valor in range(70, 151, 10)], p["scale"]), "ancho": 145})),
        grupo("Interface style",
              fila("GPU screen", "Only applies to the GPU screen. Original brings back the layout it had before the redesign.",
                   segmentos("gpu_interface", [("Original style", "original"), ("Modern", "modern")], p["gpu_interface"]))),
    ]


def terminal(ctx, p) -> list:
    grupos_de_tema = []
    for clase, nombre in TERMINAL_THEME_GROUPS:
        tarjetas = [{"valor": clave, "nombre": tema["name"], "fondo": tema["bg"], "texto": tema["text"], "borde": tema["border"],
                     "apagado": tema["muted"], "acento": tema["accent"], "colores": list(tema["ansi"])}
                    for clave, tema in TERMINAL_THEMES.items() if tema.get("group") == clase]
        if tarjetas:
            grupos_de_tema.append({"nombre": tr(nombre), "tarjetas": tarjetas})
    return [
        grupo("Built-in terminal",
              fila("Terminal inside the window", "Run workflows in a panel at the bottom of the window instead of opening a "
                   "separate terminal window.", interruptor("embedded_terminal", p["embedded_terminal"])),
              fila("Hide the terminal when a workflow finishes without errors", "A workflow that fails keeps the terminal open "
                   "so its output can be read.", interruptor("console_auto_hide", p["console_auto_hide"])),
              fila("Show or hide the terminal", "", {"tipo": "tecla", "texto": "F4"})),
        grupo("Game controller",
              fila("Gamepad navigation", "Detect controllers automatically and show controller hints while active.",
                   interruptor("gamepad_navigation", p["gamepad_navigation"])),
              fila("Automatic gamepad keypad", "Show the on-screen keypad automatically when a gamepad focuses an editable field.",
                   interruptor("gamepad_keypad", p["gamepad_keypad"]))),
        grupo("Terminal theme", {"tipo": "terminales", "clave": "console_theme", "valor": p["console_theme"], "grupos": grupos_de_tema}),
    ]


def gobernador(ctx, p) -> list:
    actual = normalize_governor_preference(ctx.settings.read_local_config().get("gpu_governor", "auto"))
    opciones = [("Automatic detection", "auto"), ("Cyan Skillfish Governor (SMU)", "cyan-skillfish-governor-smu"),
                ("Oberon Governor", "oberon-governor")]
    control = {**lista("gpu_governor", opciones, actual),
               "orden": accion("settings.governor", "Switch GPU governor safely", "Only one GPU governor can be enabled at a time. "
                               "Preparing another governor will ask before stopping the active one.", peligro=True)}
    return [grupo("GPU governor", fila("GPU governor backend", "Only one GPU governor can be enabled at a time. Preparing another "
                                       "governor will ask before stopping the active one.", control))]


def _telemetria_apu() -> dict:
    try:
        info = detect_os_info(has_rpm_ostree=bool(shutil.which("rpm-ostree")))
        return apu_telemetry_state(family=info.family, distro_id=info.distro_id, immutable=info.immutable)
    except (OSError, RuntimeError, ValueError):
        return {"state": "not-installed", "supported": False, "blocked_reason": ""}


def _boton_telemetria(estado: dict) -> tuple[str, dict]:
    """(estado en palabras, botón) del servicio BC250-Telemetry."""
    clase = estado.get("state")
    if clase == "publishing":
        palabra = "Running"
    elif clase == "external" or estado.get("managed"):
        palabra = "Installed"
    elif estado.get("supported"):
        palabra = "Not installed"
    else:
        palabra = "Not available here"
    if clase == "external":
        return palabra, boton("Installed separately", {}, activo=False)
    if estado.get("managed"):
        return palabra, boton("Remove service", accion("settings.telemetry", "Remove service", peligro=True, action="uninstall"))
    return palabra, boton("Install service", accion("settings.telemetry", "Install service", action="install"),
                          activo=bool(estado.get("supported")))


def _controladores() -> dict:
    try:
        from bc250cc.infrastructure.accessories import vram_sensor, vrm_sensor

        familia = detect_os_info().family
        return {"vrm_sensor": vrm_sensor.inventory(familia), "vram_sensor": vram_sensor.inventory(familia)}
    except Exception:  # noqa: BLE001 - la sección se muestra igual
        return {}


def describir_controlador(clave: str, info: dict) -> tuple[str, str]:
    """(estado, operación) de un controlador del kernel, como lo dice el escritorio."""
    estado, lectura = str(info.get("state") or ""), info.get("reading")
    if estado == "active" and isinstance(lectura, (int, float)):
        return tr_format("Reading {value} °C", value=f"{lectura:.0f}"), "remove"
    if estado in {"active", "installed"}:
        return tr("Installed, no reading yet"), "remove"
    if estado == "update-available":
        return tr("Update available"), "update"
    if estado == "not-installed":
        return tr("Not installed"), "install"
    if estado == "managed-elsewhere":
        return tr("Built into this kernel"), ""
    if estado == "unsupported":
        if clave == "vram_sensor" and info.get("device") and not info.get("bios_supported", True):
            return tr("Needs BIOS P3.00"), ""
        return tr("Arch-based systems only" if info.get("device", True) else "Not a BC-250"), ""
    return tr("Unavailable"), ""


def _boton_controlador(clave: str, operacion: str) -> dict | None:
    if not operacion:
        return None
    nombre = {"install": "Install", "update": "Update", "remove": "Remove"}[operacion]
    verbo = "remove" if operacion == "remove" else "install"
    return boton(nombre, accion("settings.driver", nombre, peligro=verbo == "remove", key=clave, action=verbo))


def describir_vrm(sonda: dict) -> str:
    daemon = str(sonda.get("daemon") or "missing")
    rieles = sonda.get("rails") if isinstance(sonda.get("rails"), dict) else {}
    valido = any(isinstance(riel, dict) and riel.get("valid") for riel in rieles.values())
    if daemon == "kernel":
        return tr("Detected: the kernel driver (bc250_vrm) reads the regulator" if valido else
                  "Not detected: the kernel driver (bc250_vrm) gets no answer from the regulator")
    if daemon == "missing":
        return tr("Not detected: the kernel driver (bc250_vrm) gets no answer from the regulator"
                  if kernel_vrm_driver_present() else "Not detected: BC250-Telemetry is not running")
    if daemon == "unreadable":
        return tr("Not detected: its snapshot could not be read")
    if daemon == "stale":
        return tr_format("Not detected: its snapshot is {age} s old", age=f"{float(sonda.get('age_s') or 0):.0f}")
    return tr("Detected: the PMIC answers over I2C" if valido else "Not detected: BC250-Telemetry gets no answer from the PMIC")


def _opcion_memoria(ctx) -> tuple[str, str, bool, bool]:
    """(estado, botón, activo, administrada) de cargar bc250_memory al arrancar."""
    preparacion = dict((ctx.service.estado_herramientas_bc250() or {}).get("system_setup") or {})
    opciones = dict(preparacion.get("kernel_options") or {})
    item = dict(dict(opciones.get("arguments") or {}).get(MEMORY_SENSOR_OPTION) or {})
    soporte = dict(dict(opciones.get("parameters") or {}).get(MEMORY_SENSOR_OPTION) or {})
    administrada = bool(item.get("managed"))
    if not preparacion.get("helper_available") or not opciones.get("available"):
        estado, activo = "Update Control Center's system setup helper first.", False
    elif item.get("external"):
        estado, activo = "Set outside Control Center", False
    elif administrada:
        estado, activo = ("Loads at every boot" if item.get("active") else "Loads at the next boot"), True
    elif not soporte.get("supported"):
        estado, activo = "This kernel has no bc250_memory driver.", False
    else:
        estado, activo = ("Loaded now, not at boot" if soporte.get("loaded") else "Off"), True
    return estado, ("Stop loading at boot" if administrada else "Load at boot"), activo, administrada


def _systemctl(*argumentos: str, espera: int = 5):
    if detect_init_manager().kind != "systemd":
        raise RuntimeError(tr("The optional daemon requires an active systemd user manager; "
                              "live hardware monitoring in the open application remains available."))
    return SystemdUserService().command(*argumentos, timeout=espera)


def _estado_daemon() -> tuple[str, bool]:
    activos = {"active": "Active", "inactive": "Inactive", "failed": "Failed", "activating": "Starting", "deactivating": "Stopping"}
    habilitados = {"enabled": "Enabled", "enabled-runtime": "Enabled for this session", "disabled": "Disabled", "static": "Static",
                   "indirect": "Indirect", "masked": "Masked", "masked-runtime": "Masked for this session",
                   "generated": "Generated", "transient": "Transient", "not-found": "Not installed"}
    try:
        activo = _systemctl("is-active", SERVICIO_DAEMON)
        habilitado = _systemctl("is-enabled", SERVICIO_DAEMON)
    except Exception:  # noqa: BLE001 - sin systemd de usuario no hay servicio que mostrar
        return tr("Unavailable"), detect_init_manager().kind == "systemd"
    palabras = (activos.get(activo.stdout.strip().lower(), "Unknown"), habilitados.get(habilitado.stdout.strip().lower(), "Unknown"))
    return " · ".join(tr(palabra) for palabra in palabras), True


def telemetria(ctx, p) -> list:
    servicio = _telemetria_apu()
    palabra, boton_servicio = _boton_telemetria(servicio)
    controladores = _controladores()
    filas_controlador = []
    for clave, nombre, detalle in (
            ("vrm_sensor", "bc250-vrm", "Regulator temperatures read through the fan chip. No wires needed."),
            ("vram_sensor", "bc250-memory", "GDDR6 temperature read through the SMU. BIOS P3.00 only.")):
        estado, operacion = describir_controlador(clave, dict(controladores.get(clave) or {}))
        filas_controlador.append({**fila("", detalle, botones(_boton_controlador(clave, operacion), estado=estado)),
                                  "titulo": tr_format("{driver} · by Hexxeh", driver=nombre)})
    deteccion = describir_vrm(sondear_telemetria_vrm())
    if kernel_vrm_driver_present() and servicio.get("managed"):
        deteccion += "\n" + tr(VRM_REDUNDANTE)
    estado_memoria, boton_memoria, memoria_activa, administrada = _opcion_memoria(ctx)
    bios = board_bios_version()
    nota_bios = ""
    if bios and not gddr6_firmware_supported(bios):
        nota_bios = tr_format("This board runs BIOS {version}: live readings need P3.00 (stock, Chipset Menu or MeiMeiDXE), "
                              "so the button stays off even in manual mode.", version=bios)
    estado_daemon, hay_systemd = _estado_daemon()
    intervalo = ctx.settings.read_local_config().get("daemon_interval_seconds", 2)
    return [
        grupo("Sensor sources",
              fila("BC250-Telemetry", "Power delivery readings over the I2C modification. Needs the wires on the board.",
                   botones(boton_servicio, estado=tr(palabra))),
              *filas_controlador,
              parrafo("The kernel drivers are built with DKMS on Arch, CachyOS and Manjaro.", "pista"),
              {"tipo": "enlace", "texto": tr("Board sensors guide: I2C wiring, bc250-vrm and bc250-memory"),
               "orden": seccion("telemetry_guide"), "ultimo": True}),
        grupo("Power delivery",
              fila("Show readings by hand", "Show the dashboard band even when no source is detected, invalid readings included. "
                   "Useful while wiring the I2C mod.", interruptor("vrm_manual", p["vrm_manual"])),
              fila("Detection", "What the app finds right now.", {"tipo": "texto", "texto": deteccion})),
        grupo("GDDR6 memory temperature",
              fila("Manual monitoring", "Read the memory temperature even when the SMU check says to wait.",
                   interruptor("gddr6_manual", p["gddr6_manual"], {"titulo": tr("Turn off the SMU channel check?"),
                               "mensaje": tr(AVISO_GDDR6), "aceptar": tr("Enable manual monitoring")})),
              fila("Load bc250_memory at boot", "BC-250 kernels only. Keeps the temperature on screen all the time.",
                   botones(boton(boton_memoria, accion("settings.memory_boot", boton_memoria, enable=not administrada),
                                 activo=memoria_activa), estado=tr(estado_memoria))),
              parrafo(nota_bios, "pista", traducir=False) if nota_bios else None,
              parrafo(NOTA_GDDR6, "pista")),
        grupo("Optional daemon",
              fila("Status", "bc250-control-centerd keeps sampling while the app is closed.", {"tipo": "texto", "texto": estado_daemon}),
              fila("Sampling interval", "How often the daemon reads the sensors.",
                   {**lista("daemon_interval", [("1 second", 1), ("2 seconds", 2), ("5 seconds", 5), ("10 seconds", 10)], intervalo),
                    "ajuste": "settings.daemon_interval"}),
              fila("Service", "Turn the daemon on or off for this user.", botones(
                  boton("Enable", accion("settings.daemon", "Enable optional daemon", AVISO_DAEMON[True], enable=True), activo=hay_systemd),
                  boton("Disable", accion("settings.daemon", "Disable optional daemon", AVISO_DAEMON[False], enable=False),
                        activo=hay_systemd),
                  boton("Details", texto("Optional daemon", daemon_details()))))),
    ]


def _carpetas(ctx) -> list[tuple[str, str, str]]:
    casa = Path.home()
    datos = Path(os.environ.get("XDG_DATA_HOME") or casa / ".local" / "share")
    estado = Path(os.environ.get("XDG_STATE_HOME") or casa / ".local" / "state")
    configuracion = str((ctx.settings.config_paths() or {}).get("config") or "")
    carpeta = str(Path(configuracion).expanduser().resolve().parent) if configuracion else str(
        Path(os.environ.get("XDG_CONFIG_HOME") or casa / ".config") / "bc250-control-center")
    return [
        ("Configuration folder", "Shared application configuration used by the GUI and optional daemon.", carpeta),
        ("Data folder", "Tools, helper scripts and releases the application manages for you.", str(datos / "bc250-control-center")),
        ("State and logs", "Application log, workflow logs, saved reports and the list of sent reports.",
         str(estado / "bc250-control-center")),
        ("System data", "Data the application keeps for the whole system.", "/var/lib/bc250-control-center"),
    ]


def _contenido(carpeta: str) -> str:
    """Los nombres y tamaños de una carpeta de la aplicación: en la web no se abre un explorador."""
    ruta = Path(carpeta)
    if not ruta.is_dir():
        return tr("That folder does not exist yet.")
    try:
        elementos = sorted(ruta.iterdir(), key=lambda elemento: (not elemento.is_dir(), elemento.name))[:200]
        lineas = [f"{elemento.name}/" if elemento.is_dir() else f"{elemento.name}   {elemento.stat().st_size // 1024} KiB"
                  for elemento in elementos]
    except OSError:
        return tr("Unavailable")
    return "\n".join([carpeta, "", *lineas])


def acerca(ctx, p) -> list:
    filas = [fila(nombre, detalle, {"tipo": "ruta", "texto": carpeta, "orden": texto(nombre, _contenido(carpeta)), "boton": tr("Open")})
             for nombre, detalle, carpeta in _carpetas(ctx)]
    ayudas = (("Project overview", "overview"), ("Official repositories", "repositories"), ("Support", "support"))
    return [
        {"tipo": "identidad", "nombre": "BC250 Control Center", "detalle": f"{tr('Version')} {__version__}",
         "boton": boton("Update application", {"orden": "actualizar"}, clase="principal")},
        grupo("Application", *filas),
        grupo("Help", *[{"tipo": "enlace", "texto": tr(nombre), "orden": seccion(destino), "ultimo": destino == "support"}
                        for nombre, destino in ayudas]),
    ]


def presentacion(ctx, p) -> list:
    bloques = [bloque.strip() for bloque in project_overview().split("\n\n") if bloque.strip()]
    salida = [parrafo(bloques[0], "entrada", traducir=False)] if bloques else []
    for bloque in bloques[1:]:
        lineas = [linea.strip() for linea in bloque.splitlines() if linea.strip()]
        encabezado = lineas[0].rstrip(":") if lineas and not lineas[0].startswith("•") else ""
        cuerpo = lineas[1 if encabezado else 0:]
        salida.append({"tipo": "grupo", "titulo": encabezado, "sangria": True,
                       "bloques": [parrafo(linea, "apunte", traducir=False) for linea in cuerpo]})
    return salida


def repositorios(ctx, p) -> list:
    from frontends.desktop.core.official_repositories import OFFICIAL_REPOSITORIES

    archivados = {"duggasco/bc250-40cu-unlock"}
    filas = [{"numero": f"{numero:02d}", "titulo": tr(nombre), "detalle": direccion,
              "marca": tr("Archived") if direccion in archivados else "",
              "boton": boton("Open", enlace(url))} for numero, (nombre, direccion, url) in enumerate(OFFICIAL_REPOSITORIES, 1)]
    return [parrafo("BC250 Control Center does not own these tools. They are installed, cloned, or used as credited reference "
                    "implementations according to each integration.", "descripcion"),
            {"tipo": "fichas", "buscar": tr("Search repositories"), "vacio": tr("No results"), "fichas": filas}]


SECCIONES = {
    "general": ("General", general), "appearance": ("Appearance", apariencia), "console": ("Terminal and controls", terminal),
    "hardware": ("Hardware", gobernador), "telemetry": ("Telemetry", telemetria), "about": ("About", acerca),
    "overview": ("Project overview", presentacion), "repositories": ("Official repositories", repositorios),
}
#: De dónde cuelga una página interior: a dónde vuelve y cómo se llama.
VUELTAS = {"overview": ("about", "About"), "repositories": ("about", "About"), "support": ("about", "About"),
           "support_report": ("support", "Support"), "support_reports": ("support", "Support"),
           "support_detail": ("support", "Support"), "support_errors": ("support", "Support"),
           "support_error_detail": ("support_errors", "Known errors"), "telemetry_guide": ("telemetry", "Telemetry")}


def consultar(web, parametros) -> dict:
    """Una sección de Configuración, lista para dibujar."""
    from frontends.web.modulos import soporte

    nombre = parametros.get("section", "general")
    secciones = {**SECCIONES, **soporte.SECCIONES}
    if nombre not in secciones:
        nombre = "general"
    encabezado, construir = secciones[nombre]
    valores = preferencias(web.ctx.settings.read_local_config())
    if nombre in soporte.SECCIONES:
        bloques = construir(web.ctx, valores, parametros)
    else:
        bloques = construir(web.ctx, valores)
    if isinstance(bloques, tuple):  # la sección le pone su propio título
        encabezado, bloques = bloques
        titulo_final = encabezado
    else:
        titulo_final = tr(encabezado)
    vuelta = VUELTAS.get(nombre)
    return {"seccion": nombre, "titulo": titulo_final, "bloques": bloques,
            "vuelta": {"seccion": vuelta[0], "texto": tr(vuelta[1])} if vuelta else {}}


# -- acciones ---------------------------------------------------------------------------------------

def cambiar_gobernador(ctx, p, shell):
    validar_campos(p, {"value"})
    elegido = choice(p, "value", GOBERNADORES)

    def cambiar():
        if elegido != "auto":
            ctx.service.cambiar_governor(elegido)
        ctx.settings.save_local_config({"gpu_governor": elegido})
        return tr("Saved")
    return (2 if elegido != "auto" else 1), cambiar


def acciones_sin_clave(ctx, p, shell):
    validar_campos(p, {"enable"})
    activar = flag(p, "enable")
    return (2 if activar else 1), lambda: ctx.service.gestionar_acciones_sin_clave(activar)


def validar_campos(parametros, campos):
    if set(parametros) != campos:
        raise Invalid("params")


def servicio_telemetria(ctx, p, shell):
    validar_campos(p, {"action"})
    operacion = choice(p, "action", ("install", "uninstall"))

    def ejecutar():
        estado = _telemetria_apu()
        retirar = estado.get("managed") and estado.get("state") != "external"
        instalar = estado.get("supported") and not estado.get("managed") and estado.get("state") != "external"
        if not (retirar if operacion == "uninstall" else instalar):
            raise Invalid(tr("Not available here"))
        return ctx.service.gestionar_apu_telemetry(operacion)
    return 1, ejecutar


def controlador(ctx, p, shell):
    validar_campos(p, {"key", "action"})
    clave, operacion = choice(p, "key", ("vrm_sensor", "vram_sensor")), choice(p, "action", ("install", "remove"))

    def ejecutar():
        _, disponible = describir_controlador(clave, _controladores().get(clave) or {})
        esperada = "install" if disponible == "update" else disponible
        if operacion != esperada:
            raise Invalid(tr("Not available here"))
        return ctx.service.manage_accessory(clave, operacion)
    return 1, ejecutar


def memoria_al_arrancar(ctx, p, shell):
    validar_campos(p, {"enable"})
    activar = flag(p, "enable")

    def cambiar():
        estado, _, disponible, _ = _opcion_memoria(ctx)
        if not disponible:
            raise Invalid(tr(estado))
        preparacion = (ctx.service.estado_herramientas_bc250() or {}).get("system_setup") or {}
        argumentos = (preparacion.get("kernel_options") or {}).get("arguments") or {}
        administradas = {clave for clave, valor in argumentos.items() if (valor or {}).get("managed")}
        if activar:
            administradas.add(MEMORY_SENSOR_OPTION)
        else:
            administradas.discard(MEMORY_SENSOR_OPTION)
        return ctx.service.gestionar_opciones_kernel(tuple(sorted(administradas)))
    return 1, cambiar


def daemon(ctx, p, shell):
    validar_campos(p, {"enable"})
    activar = flag(p, "enable")

    def cambiar():
        resultado = _systemctl("enable" if activar else "disable", "--now", SERVICIO_DAEMON, espera=25)
        if resultado.returncode != 0:
            raise RuntimeError(tr("Failed"))
        return tr("The optional daemon is enabled." if activar else "The optional daemon is disabled.")
    return 1, cambiar


def intervalo_daemon(ctx, p) -> None:
    validar_campos(p, {"value"})
    valor = p.get("value")
    if valor not in ("1", "2", "5", "10"):
        raise Invalid("value")
    ctx.settings.save_local_config({"daemon_interval_seconds": int(valor)})


def actualizar(ctx, p, shell):
    if p:
        raise Invalid("params")

    def instalar():
        from frontends.tui.pages.base import os_family
        from frontends.tui.support import install_update

        return install_update(ctx, os_family(ctx)[0])
    return 1, instalar


def novedades(web, parametros) -> dict:
    """La versión publicada y sus notas, para la ventana de actualización."""
    from bc250cc.application.system.updates import (
        detect_install_source,
        fetch_latest_release,
        plan_update,
    )
    from frontends.tui.pages.base import os_family

    try:
        publicada = fetch_latest_release()
        plan = plan_update(publicada, detect_install_source(), os_family=os_family(web.ctx)[0])
    except Exception:  # noqa: BLE001 - sin red se dice y ya
        return {"installed": __version__, "error": tr("Unavailable")}
    return {"installed": __version__, "version": str(publicada.version), "notes": str(getattr(publicada, "notes", "") or ""),
            "page": str(publicada.page_url), "kind": str(plan.kind), "reason": tr(str(getattr(plan, "reason", "") or "")),
            "newer": str(publicada.version) != __version__}


def recorrido(web, parametros) -> dict:
    """Las paradas del recorrido, leídas del guion del escritorio sin importarlo (usa Qt)."""
    guion = Path(__file__).resolve().parents[2] / "desktop" / "onboarding" / "script.py"
    paradas = []
    for nodo in ast.walk(ast.parse(guion.read_text(encoding="utf-8"))):
        if not (isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") == "TourStop"):
            continue
        campos = {}
        for argumento in nodo.keywords:
            valor = argumento.value
            if isinstance(valor, ast.Call) and valor.args:  # tr("…")
                valor = valor.args[0]
            if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                campos[argumento.arg] = valor.value
        if {"page", "title", "body"} <= set(campos):
            paradas.append({"orden": nodo.lineno, "page": campos["page"], "titulo": tr(campos["title"]), "cuerpo": tr(campos["body"])})
    return {"stops": sorted(paradas, key=lambda parada: parada["orden"])}


MODULOS_RECORRIDO = (("dashboard", "Dashboard"), ("cpu", "CPU"), ("gpu", "GPU"), ("cu", "Compute units"),
                     ("extras", "Additional settings"), ("performance", "Performance"), ("fans", "Fans"),
                     ("firmware", "Firmware (BIOS)"), ("settings", "Settings"))


def bienvenida(web, parametros) -> dict:
    """Lo que enseña la primera visita: idiomas, aspecto y las paradas del recorrido por módulo."""
    p = preferencias(web.ctx.settings.read_local_config())
    temas, estilo, acento = apariencia(web.ctx, p)[0]["bloques"]
    densidad, escala = apariencia(web.ctx, p)[1]["bloques"]
    paradas = [parada["page"] for parada in recorrido(web, {})["stops"]]
    cuentas = {clave: paradas.count(clave) for clave, _nombre in MODULOS_RECORRIDO}
    if cuentas["dashboard"] > 1 and not cuentas["settings"]:  # la última parada señala Configuración desde el panel
        cuentas["dashboard"] -= 1
        cuentas["settings"] = 1
    fichas = []
    for clave, nombre in MODULOS_RECORRIDO:
        cantidad = cuentas[clave]
        if cantidad:
            frase = "{module} · 1 stop" if cantidad == 1 else "{module} · {count} stops"
            fichas.append(tr_format(frase, module=tr(nombre), count=cantidad))
    return {"idiomas": [{"valor": codigo, "nombre": tr("Automatic") if codigo == "auto" else nombre}
                        for codigo, nombre in LANGUAGE_OPTIONS],
            "idioma": p["language"], "unidad": p["temperature_unit"], "barra": p["sidebar_collapsed"],
            "mando": p["gamepad_navigation"], "temas": temas, "estilo": estilo, "acento": acento,
            "densidad": densidad, "escala": escala, "terminal": terminal(web.ctx, p)[2]["bloques"][0], "paradas": fichas}


def lectura_preferencias(ctx, live) -> dict:
    valores = preferencias(ctx.settings.read_local_config())
    use_unit(valores["temperature_unit"])
    return {"valores": valores, "terminales": {clave: {"fondo": tema["bg"], "texto": tema["text"], "borde": tema["border"]}
                                              for clave, tema in TERMINAL_THEMES.items()},
            "fecha": datetime.now().strftime("%H:%M:%S")}


LECTURAS = {"preferences": (1, lectura_preferencias)}
CONSULTAS = {"settings": consultar, "settings.update": novedades, "settings.tour": recorrido,
             "settings.welcome": bienvenida}
ACCIONES = {"settings.governor": cambiar_gobernador, "settings.telemetry": servicio_telemetria, "settings.driver": controlador,
            "settings.quick_auth": acciones_sin_clave,
            "settings.memory_boot": memoria_al_arrancar, "settings.daemon": daemon, "settings.update": actualizar}
AJUSTES = {"settings.preference": guardar_preferencia, "settings.reset": reiniciar_preferencias,
           "settings.daemon_interval": intervalo_daemon}
