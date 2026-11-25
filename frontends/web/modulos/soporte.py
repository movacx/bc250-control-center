"""Soporte: reportes, diagnóstico, errores frecuentes y la guía de sensores.

Los textos y el orden son los del escritorio; cada sección devuelve bloques (ver ``configuracion``).
Un reporte solo sale del equipo cuando la persona lo confirma, y se arma en la consola de la web.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from bc250cc.application.system.feedback import reports as formulario
from bc250cc.application.system.feedback import system_snapshot
from bc250cc.platform.packages.strategies.detector import detect_os_info
from bc250cc.shared import known_errors
from bc250cc.shared.version import __version__
from frontends.desktop.core.diagnostic_history import (
    clear_history,
    current_wording,
    diagnostic_report,
    history_entries,
)
from frontends.desktop.i18n import (
    count_label,
    current_language,
    tr,
    tr_format,
    translate_history_event,
)
from frontends.tui import report_form
from frontends.web.actions import Invalid, choice, flag
from frontends.web.modulos import temporales
from frontends.web.modulos.configuracion import (
    REGLA,
    _boton_controlador,
    _boton_telemetria,
    _controladores,
    _telemetria_apu,
    accion,
    ajuste,
    boton,
    botones,
    comando,
    copiar,
    enlace,
    foto,
    parrafo,
    puntos,
    seccion,
    titulo,
)

DISTRIBUCIONES = {
    "arch": "Arch / CachyOS / Manjaro", "steamos": "SteamOS", "bazzite": "Bazzite / Fedora Atomic", "fedora": "Fedora / Nobara",
    "ubuntu": "Ubuntu / Mint", "debian": "Debian", "other": "Other distributions",
}
ESTADOS = {
    "fixed": "Resolved", "fixed-dev": "Fixed in development", "user": "User steps", "pending": "Pending",
    "expected": "Expected behavior", "analysis": "Under investigation",
}
#: Lo más largo que se acepta de cada texto del formulario.
LARGOS = {"summary": 300, "code": 60, "steps": 4000, "expected": 2000, "media": 500, "contact": 120, "notes": 4000,
          "terminal": 60000, "version": 40, "area": 120, "frequency": 80, "worked_before": 80, "distribution": 80,
          "install": 120, "bios": 120, "cores": 80, "cus": 80}


def _cuando(sello: str) -> str:
    """El momento como lo diría una persona: hoy, ayer o la fecha."""
    try:
        momento = datetime.fromisoformat(sello).astimezone()
    except ValueError:
        return ""
    dias = (datetime.now().astimezone().date() - momento.date()).days
    if dias == 0:
        return tr_format("Today {time}", time=momento.strftime("%H:%M"))
    if dias == 1:
        return tr_format("Yesterday {time}", time=momento.strftime("%H:%M"))
    return momento.strftime("%Y-%m-%d %H:%M")


def _de_esta_semana(sello: str) -> bool:
    try:
        momento = datetime.fromisoformat(sello.replace("Z", "+00:00"))
    except ValueError:
        return False
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento >= datetime.now(timezone.utc) - timedelta(days=7)


# -- soporte y reportes enviados ----------------------------------------------------------------------

def portada(ctx, p, parametros) -> list:
    tarjetas = [
        {"titulo": tr(nombre), "detalle": tr(detalle), "ir": tr(ir), "orden": seccion(destino), "principal": principal}
        for nombre, detalle, ir, destino, principal in (
            ("Report a problem", "Tell us what failed. We attach the diagnostics for you.", "Begin", "support_report", True),
            ("View reports", "System diagnostics and the movement history.", "Open", "support_reports", False),
            ("Known errors", "Find an error and how to fix it.", "Open", "support_errors", False))]
    enviados = formulario.sent_reports()
    filas = [{
        "id": str(item.get("id") or ""), "titulo": str(item.get("summary") or tr("Suggestion")),
        "detalle": tr("Suggestion") if str(item.get("kind") or "") == "idea" else tr(str(item.get("area") or "")),
        "version": str(item.get("version") or ""), "cuando": _cuando(str(item.get("sent_at") or "")),
        "semana": _de_esta_semana(str(item.get("sent_at") or "")),
    } for item in enviados]
    return [
        {"tipo": "tarjetas", "tarjetas": tarjetas},
        {"tipo": "enviados", "titulo": tr("Sent reports"), "todos": tr("All reports"), "semana": tr("This week"),
         "columnas": [tr("ID"), tr("Problem"), tr("Version"), tr("When")], "ver": tr("View"), "copiar": tr("Copy"),
         "vacio": tr("No reports sent yet. Each report you send shows here with its ID."), "filas": filas},
        parrafo("Keep the ID to ask about a report on GitHub or Discord. The list only exists on this computer.", "descripcion"),
    ]


def detalle(ctx, p, parametros):
    pedido = parametros.get("id", "")
    item = next((uno for uno in formulario.sent_reports() if str(uno.get("id") or "") == pedido), None)
    if item is None:
        return tr("Report"), [parrafo("No results", "descripcion")]
    idea = str(item.get("kind") or "") == "idea"
    datos = (("Problem", str(item.get("summary") or tr("Suggestion"))),
             ("Area", tr("Suggestion") if idea else (tr(str(item.get("area") or "")) or "—")),
             ("Code", str(item.get("code") or "—")), ("Version", str(item.get("version") or "—")),
             ("Sent", _cuando(str(item.get("sent_at") or "")) or "—"))
    adjuntos = [tr(nombre) for nombre in ("Version and system", "Recent logs", "System diagnostics")] if item.get("attached") else []
    return pedido, [{"tipo": "ficha_reporte", "datos": [{"nombre": tr(nombre), "valor": valor} for nombre, valor in datos],
                     "encabezado": tr("What was attached").upper(), "adjuntos": adjuntos,
                     "vacio": tr("Nothing was attached."), "boton": boton("Copy ID", copiar(pedido))}]


# -- diagnóstico e historial ---------------------------------------------------------------------------

def informes(ctx, p, parametros) -> list:
    sistema = [(str(nombre), str(valor)) for nombre, valor in system_snapshot()]
    entradas = history_entries()
    errores = []
    for entrada in entradas:
        explicacion = current_wording(entrada)
        origen = {"terminal": tr("Terminal"), "decky": tr("Decky Quick Access")}.get(entrada.source, tr("Window"))
        partes = [f"{entrada.code} · {tr(entrada.title)}", f"{tr('How to fix it')}\n{tr(explicacion.action)}"]
        if entrada.detail:
            partes.append(f"{tr('Technical detail')}\n{entrada.detail}")
        errores.append({"celdas": [datetime.fromtimestamp(entrada.at).strftime("%Y-%m-%d %H:%M:%S"), entrada.code, origen,
                                   tr(explicacion.summary), tr(explicacion.cause)], "detalle": "\n\n".join(partes)})
    movimientos = []
    for evento in (ctx.activity.list(100) if ctx.activity is not None else []):
        datos = evento if isinstance(evento, dict) else {"detalle": str(evento)}
        nombre, explicacion = translate_history_event(datos)
        movimientos.append({"celdas": [str(datos.get("fecha") or "--"), tr(str(datos.get("nivel") or "info").capitalize()),
                                       nombre, explicacion], "nivel": str(datos.get("nivel") or "info").lower()})
    diagnostico = [
        {"tipo": "cabecera", "texto": tr("System"), "interruptor": {"clave": "detailed_diagnostics", "activo": p["detailed_diagnostics"],
                                                                     "texto": tr("Detailed diagnostics")},
         "botones": [boton("Copy diagnostics", copiar(diagnostic_report(sistema, entradas))), boton("Refresh", {"orden": "recargar"})]},
        {"tipo": "tabla", "columnas": [tr("Item"), tr("Value")], "pesos": [0, 1],
         "filas": [{"celdas": [tr(nombre), tr(valor)]} for nombre, valor in sistema]},
        {"tipo": "cabecera", "texto": tr("Diagnostic history"), "cuenta": tr_format("{count} entries", count=len(entradas)),
         "botones": [boton("Clear history", ajuste("support.clear_diagnostics", "Clear history", "Clear history"), activo=bool(entradas))]},
    ]
    if errores:
        diagnostico.append({"tipo": "tabla", "columnas": [tr(nombre) for nombre in ("Date and time", "Code", "Where", "What happened", "Likely cause")],
                            "pesos": [0, 0, 0, 1, 1], "filas": errores, "con_detalle": True,
                            "pista": tr("Select a row to see how to fix it and the technical detail.")})
    else:
        diagnostico.append(parrafo("No errors recorded. Every error Control Center explains, in a window or in the terminal, "
                                   "appears here.", "vacio"))
    historial = [
        {"tipo": "cabecera", "texto": tr("Recent activity"), "cuenta": count_label(len(movimientos), "event"), "botones": [
            boton("Refresh", {"orden": "recargar"}),
            boton("Clear history", ajuste("support.clear_history", "Clear local history",
                                          "The JSONL history file will be emptied. This cannot be undone."))]},
        {"tipo": "tabla", "columnas": [tr(nombre) for nombre in ("Date", "Level", "Event", "Details")], "pesos": [0, 0, 1, 1],
         "filas": movimientos, "alto": 330},
    ]
    return [{"tipo": "pestanas", "pestanas": [{"clave": "diagnostics", "nombre": tr("Diagnostics"), "bloques": diagnostico},
                                              {"clave": "history", "nombre": tr("Movement history"), "bloques": historial}]}]


# -- errores frecuentes -------------------------------------------------------------------------------

def errores_frecuentes(ctx, p, parametros) -> list:
    idioma = current_language()
    busqueda, modulo = parametros.get("query", "")[:200], parametros.get("module", "")
    nombres = {item["id"]: tr(item["label"]) for item in known_errors.modules()}
    if modulo not in nombres:
        modulo = ""
    fichas = []
    for numero, hallado in enumerate(known_errors.search_matches(busqueda, module=modulo), 1):
        entrada = hallado.entry
        datos = f"{nombres[entrada['module']]}  ·  {entrada['id']}"
        if hallado.kind:
            termino = nombres.get(hallado.term, hallado.term) if hallado.kind == "module" else hallado.term
            datos += "  ·  " + (f"{tr('Error code')}: {termino}" if hallado.kind == "code" else tr_format("Matches: {term}", term=termino))
        fichas.append({"numero": f"{numero:02d}", "titulo": known_errors.localized(entrada["guide"]["title"], idioma), "detalle": datos,
                       "boton": boton("Open guide", {"orden": "seccion", "nombre": "support_error_detail", "id": entrada["id"]})})
    sugerencias = []
    if not fichas:
        from bc250cc.shared.known_errors_search import suggested_modules

        sugerencias = [{"texto": tr_format("Did you mean: {term}?", term=termino), "buscar": termino}
                       for termino in known_errors.search_suggestions(busqueda, module=modulo)[:3]]
        sugerencias += [{"texto": nombres[clave], "modulo": clave} for clave in suggested_modules(busqueda)[:3] if clave in nombres]
    return [{"tipo": "errores", "buscar": tr("Search by code, message or keyword"), "consulta": busqueda, "modulo": modulo,
             "modulos": [{"valor": "", "nombre": tr("All modules")}, *[{"valor": c, "nombre": n} for c, n in nombres.items()]],
             "fichas": fichas, "vacio": tr("No results"), "ayuda": tr("Try another search or select a module."),
             "sugerencias": sugerencias, "reportar": tr("Report a problem")}]


def error_detalle(ctx, p, parametros):
    entrada = known_errors.for_id(parametros.get("id", ""))
    if entrada is None:
        return tr("Known errors"), [parrafo("No results", "descripcion")]
    idioma = current_language()
    try:
        detectada = known_errors.family_for(detect_os_info().family)
    except OSError:
        detectada = "other"
    elegida = parametros.get("distro", "auto")
    familia = elegida if elegida in known_errors.FAMILIES else detectada
    resumen = known_errors.localized(entrada["guide"]["summary"], idioma)
    vistos = {known_errors.localized(entrada["title"], idioma).strip(), resumen.strip()}
    cabecera = [
        {"tipo": "titulo_guia", "texto": known_errors.localized(entrada["guide"]["title"], idioma), "marca": entrada["id"]},
        parrafo(resumen, "guia_entrada", traducir=False),
        {"tipo": "hechos", "hechos": [
            {"nombre": tr("Code").upper(), "valor": ", ".join(entrada["codes"]) or "—"},
            {"nombre": tr("Status").upper(), "valor": " · ".join(tr(ESTADOS[marca]) for marca in entrada["status_flags"])},
            {"nombre": tr("Seen on").upper(), "valor": ", ".join((entrada.get("distros") or {}).get("reported") or ()) or "—"}]},
    ]
    if entrada["owner"] == "expected":
        cabecera.append(parrafo("A protection, not an error", "aviso"))
    if known_errors.needs_update(entrada, __version__):
        cabecera.append(botones(boton(tr_format("Update to {version}", version=entrada["fixed_in"]), {"orden": "actualizar"},
                                      clase="principal", traducir=False)))
    solucion = []
    for encabezado, campo in (("What you see", "symptom"), ("Why it happens", "cause")):
        contenido = known_errors.localized(entrada.get(campo) or {}, idioma).strip()
        if contenido and contenido not in vistos:
            solucion += [titulo(encabezado), parrafo(contenido, "guia", traducir=False)]
    solucion.append(titulo("How to fix it"))
    solucion.append({"tipo": "distribucion", "valor": elegida if elegida in known_errors.FAMILIES else "auto", "nombre": tr("Distribution"),
                     "opciones": [{"valor": "auto", "nombre": f"{tr('Automatic')} · {tr(DISTRIBUCIONES[detectada])}"},
                                  *[{"valor": clave, "nombre": tr(DISTRIBUCIONES[clave])} for clave in known_errors.FAMILIES]]})
    arreglo = known_errors.fix_for(entrada, familia)
    if arreglo is None:
        solucion.append(parrafo("Not applicable", "aviso"))
    else:
        solucion.append(parrafo(tr_format("Steps for {distribution}", distribution=tr(DISTRIBUCIONES[familia])), "guia_dato", traducir=False))
        if arreglo["scope"] == "equivalent":
            solucion.append(parrafo("Equivalent issue", "aviso"))
        for paso in arreglo["article"]:
            solucion.append(parrafo(known_errors.localized(paso["text"], idioma), "guia", traducir=False))
            solucion += [comando(orden) for orden in paso["commands"]]
    notas = [titulo("Status"), parrafo(" · ".join(tr(ESTADOS[marca]) for marca in entrada["status_flags"]), "guia", traducir=False),
             titulo("Developer notes"), parrafo(known_errors.localized(entrada["developer"], idioma), "guia", traducir=False)]
    return "", [*cabecera, {"tipo": "pestanas", "pestanas": [
        {"clave": "solution", "nombre": tr("Solution"), "bloques": solucion},
        {"clave": "developer", "nombre": tr("Developer notes"), "bloques": notas}]}]


# -- guía de sensores ----------------------------------------------------------------------------------

#: Los textos de la guía del escritorio (``components/sensor_guide_page.py`` e ``i2c_guide.py``), sin Qt.
NECESITAS = (
    "Two wires with a 2-pin connector. The cable of an old PC case's power or reset button works well.",
    "A 2.0 mm connector for the TPMS1 end: standard 2.54 mm Dupont plugs sit loose on it.",
    "Nothing to solder and no ground wire: both headers already share the board's ground.",
    "The board switched off, with the power supply unplugged.")
SI_NO_FUNCIONA = (
    "SCL and SDA swapped. It damages nothing, but the bus stays silent: swap them and try again.",
    "A loose connector on TPMS1. A 2.54 mm plug moves on 2.0 mm pins.",
    "The wrong pins on TPMS1. Count from the triangle: pin 1 is bottom left, pins 4 and 6 are the second and third of the top row.",
    "A kernel that reads the regulator itself (bc250_vrm). It keeps the bus to itself; use the bc250-vrm tab instead.")
CABLES = (("SCL (red)", "Pin 4", "SMB_CLK_MAIN"), ("SDA (blue)", "Pin 6", "SMB_DATA_MAIN"))
CREDITO = ("Photos, wiring and research: BC250-Telemetry by onlinermm and fansteori (MIT license). "
           "Pinout: AMD BC-250 Documentation (elektricM), from mothenjoyer69's reverse engineering.")
DIRECCIONES = {"i2c": "https://github.com/onlinermm/BC250-Telemetry/blob/main/hardware.md",
               "vrm": "https://github.com/Hexxeh/bc250-vrm-dkms", "vram": "https://github.com/Hexxeh/bc250-memory-dkms"}
ESTADOS_CONTROLADOR = {
    "vrm": {
        "unsupported": "Builds on Arch-based systems (Arch, CachyOS, Manjaro) on a BC-250.",
        "managed-elsewhere": "Your kernel already includes this driver (MastaG's BC-250 kernels do), so there is nothing to build.",
        "installed": "Installed, but the regulator does not answer through the fan chip. Run sudo dmesg | grep bc250_vrm to see why.",
        "update-available": "This copy was built by an earlier version of Control Center. Press Update to build it again with the current fixes.",
    },
    "vram": {
        "unsupported": "Needs an Arch-based system (Arch, CachyOS, Manjaro) on a BC-250 with BIOS P3.00: the driver patches the SMU at addresses reviewed for that BIOS only.",
        "managed-elsewhere": "Your kernel already includes this driver (MastaG's BC-250 kernels do), so there is nothing to build.",
        "installed": "Installed, but this BIOS keeps the SMU locked, so the driver waits. Press Monitor live on the dashboard once after each power-on: Control Center patches the SMU and the driver reads from then on.",
        "update-available": "This copy was built by an earlier version of Control Center. Press Update to build it again with the current fixes.",
    },
}


def _aviso(contenido: str) -> dict:
    return {"tipo": "advertencia", "texto": tr(contenido)}


def _guia_i2c() -> list:
    from bc250cc.infrastructure.vrm_telemetry_reader import (
        kernel_vrm_driver_present,
        sondear_telemetria_vrm,
    )

    if kernel_vrm_driver_present():
        estado = ("Your kernel has its own driver for the voltage regulator (bc250_vrm), but the regulator does not answer it. Version "
                  "1.1.0 and later read it through the fan chip without wires; older versions need the I2C modification. Update the "
                  "kernel, or see the bc250-vrm tab. The BC250-Telemetry service cannot open the bus on this kernel.")
    elif str(sondear_telemetria_vrm().get("daemon") or "missing") in {"running", "stale"}:
        estado = ("The BC250-Telemetry service is running, but the voltage regulator does not answer over I2C. Check the two wires of "
                  "the I2C modification between I2C_HEADER1 and TPMS1, then look at Settings › Telemetry › Automatic detection.")
    else:
        estado = ("These readings come from the board's voltage regulator (PMIC) over I2C, which needs the physical I2C modification: "
                  "two wires between I2C_HEADER1 and TPMS1. With the modification in place, open Settings › Telemetry and install the "
                  "BC250-Telemetry service under Power delivery (I2C mod). The readings appear here a few seconds after it starts.")
    servicio = _telemetria_apu()
    palabra, boton_servicio = _boton_telemetria(servicio)
    if servicio.get("state") == "external":
        palabra = "Installed with BC250-Telemetry's own installer, so Control Center leaves it alone."
    elif not servicio.get("managed") and not servicio.get("supported") and servicio.get("blocked_reason"):
        palabra = str(servicio["blocked_reason"])
    return [
        parrafo("Two wires between I2C_HEADER1 and TPMS1 let Linux read the board's voltage regulator: the 12 V input, the CPU and GPU "
                "rails, their current and power, and the VRM temperatures. The BC250-Telemetry service then publishes them for the "
                "dashboard.", "guia"),
        {"tipo": "recuadro", "texto": tr(estado)},
        titulo("What you need"), puntos(NECESITAS),
        _aviso("Work with the board switched off and the power supply unplugged. This is a community modification with no warranty: "
               "check every pin before powering on."), REGLA,
        titulo("Find I2C_HEADER1", 1),
        parrafo("I2C_HEADER1, beside the heatsink. Red is SCL (middle pin), blue is SDA (the pin closer to the power connectors).", "guia"),
        foto("i2c-header1-pins.jpg", "Find I2C_HEADER1"), REGLA,
        titulo("Find TPMS1", 2),
        parrafo("TPMS1: 18 pins, 2.0 mm apart. The triangle marks pin 1 (bottom row, left). Pin 4 (red, to SCL) and pin 6 (blue, to SDA) "
                "are the second and third pins of the top row.", "guia"),
        foto("tpms1-pins.jpg", "Find TPMS1"), REGLA,
        titulo("Connect the two wires", 3),
        parrafo("SCL to pin 4 and SDA to pin 6. Swapping them damages nothing, but the bus stays silent. The 2-pin cable of an old PC "
                "case's power or reset button fits well. Standard Dupont connectors are 2.54 mm and sit loose on TPMS1, so give that end "
                "a 2.0 mm connector.", "guia"),
        {"tipo": "tabla", "columnas": ["I2C_HEADER1", "TPMS1", tr("Signal")], "pesos": [0, 0, 1],
         "filas": [{"celdas": [tr(origen), tr(pin), senal]} for origen, pin, senal in CABLES]},
        {"tipo": "fotos", "fotos": [foto("tpms1-connected.jpg", "TPMS1 with the connector on pins 4 and 6.", 275),
                                    foto("i2c-header1-connected.jpg", "I2C_HEADER1 with the wires routed through the heatsink.", 275)]}, REGLA,
        titulo("Install the service", 4),
        parrafo("Power the board on. Control Center builds BC250-Telemetry from its reviewed source and installs only the service that "
                "reads the regulator; it asks for your password once.", "guia"),
        botones(boton_servicio, estado=tr(palabra)), REGLA,
        titulo("Check it", 5),
        parrafo("The readings appear on the dashboard within a few seconds, and Telemetry › Detection says the regulator answers. To check "
                "the bus by hand, this should show a device at 0x60:", "guia"),
        comando("sudo i2cdetect -y 4"), titulo("If nothing shows up"), puntos(SI_NO_FUNCIONA), REGLA,
        parrafo(CREDITO, "pista"), botones(boton("BC250-Telemetry", enlace(DIRECCIONES["i2c"]), clase="enlace", traducir=False)),
    ]


def _guia_controlador(clave: str) -> list:
    vrm = clave == "vrm"
    nombre = "vrm_sensor" if vrm else "vram_sensor"
    info = dict(_controladores().get(nombre) or {})
    estado, lectura = str(info.get("state") or ""), info.get("reading")
    valor = f"{lectura:.0f} °C" if isinstance(lectura, (int, float)) else ""
    if estado == "active":
        palabra = tr_format("Installed and reading: {value}.", value=valor)
    elif estado == "not-installed":
        palabra = tr("Not installed yet. Compile and install builds it in a terminal; it asks for your password.")
    elif estado in ESTADOS_CONTROLADOR[clave]:
        palabra = tr(ESTADOS_CONTROLADOR[clave][estado])
        if estado == "managed-elsewhere" and valor:
            palabra += " " + tr_format("Reading now: {value}.", value=valor)
    else:
        palabra = tr("Could not check this board yet.")
    operacion = "remove" if estado in {"active", "installed"} else "install" if estado in {"not-installed", "update-available"} else ""
    hacer = _boton_controlador(nombre, operacion)
    if hacer and operacion == "install":
        hacer["texto"] = tr("Update" if estado == "update-available" else "Compile and install")
    return [
        parrafo("bc250-vrm is a kernel driver by Liam McLoughlin (Hexxeh). It reads the board's voltage regulator through the fan chip, so "
                "it needs none of the I2C wiring: the 12 V input, the CPU and GPU rails and the VRM temperatures show up on the Dashboard "
                "and in sensors." if vrm else
                "bc250-memory is the same author's driver for the video memory. It reads the temperature of the eight GDDR6 chips through "
                "the SMU and shows it as a normal sensor: the hottest chip, the average and each chip.", "guia"),
        titulo("This board"), botones(hacer, estado=palabra), REGLA,
        titulo("How it is installed"),
        parrafo("Control Center downloads the reviewed source, builds it with DKMS for your kernel and loads it. When the kernel updates, "
                "DKMS builds it again by itself. It needs Arch, CachyOS, Manjaro or another Arch-based system; MastaG's BC-250 kernels "
                "already include it.", "guia"),
        _aviso("Use one way, not both: if you already have the I2C wires with the BC250-Telemetry service, remove the service first. Two "
               "readers on the same regulator mix up each other's readings." if vrm else
               "On a BIOS that keeps the SMU locked (stock P3.00), the driver waits until the SMU is patched. Press Monitor live on the "
               "dashboard once after each power-on: Control Center patches the SMU and the driver reads from then on."), REGLA,
        titulo("Check it"), parrafo("Once it is installed, this lists the driver's readings:", "guia"),
        comando("sensors 'bc250_vrm-*'" if vrm else "sensors 'bc250_memory-*'"), REGLA,
        parrafo("bc250-vrm-dkms · Liam McLoughlin (Hexxeh) · GPL-2.0" if vrm else
                "bc250-memory-dkms · Liam McLoughlin (Hexxeh) · GPL-2.0 · SMU payload: pan-Rijovich (MIT)", "pista", traducir=False),
        botones(boton("bc250-vrm" if vrm else "bc250-memory", enlace(DIRECCIONES[clave]), clase="enlace", traducir=False)),
    ]


def guia_sensores(ctx, p, parametros) -> list:
    return [{"tipo": "pestanas", "pestanas": [
        {"clave": "i2c", "nombre": tr("I2C modification"), "bloques": _guia_i2c()},
        {"clave": "vrm", "nombre": "bc250-vrm", "bloques": _guia_controlador("vrm")},
        {"clave": "vram", "nombre": "bc250-memory", "bloques": _guia_controlador("vram")}]}]


# -- formulario de reporte ------------------------------------------------------------------------------

def _opciones(valores) -> list:
    return [{"valor": "", "nombre": tr("Choose…")}, *[{"valor": valor, "nombre": tr(valor)} for valor in valores]]


def formulario_reporte(ctx, p, parametros) -> list:
    from frontends.desktop.core.report_facts import read_report_facts

    borrador = report_form.new_draft()
    try:
        borrador.facts = read_report_facts(attachments=False)
        report_form.prefill(borrador, borrador.facts)
    except Exception:  # noqa: BLE001 - el formulario se abre igual, sin esos datos
        borrador.facts = {}
    hechos = borrador.facts
    anteriores = formulario.history_items(hechos.get("history") or (), exclude_raw="", exclude_title="")
    automatico = [
        (tr("System specifications"), tr("Included") if hechos.get("system") else "…"),
        (tr("Hardware diagnostics"), tr("Included")),
        (tr("Recent errors"), str(len(anteriores)) if anteriores else tr("None recorded"))]
    return [{
        "tipo": "reporte", "valores": {**borrador.values, "summary": parametros.get("query", "")[:200]}, "otro": formulario.OTHER,
        "areas": _opciones(formulario.AREAS), "frecuencias": _opciones(formulario.FREQUENCIES),
        "antes": _opciones(formulario.WORKED_BEFORE), "distribuciones": _opciones(formulario.DISTRIBUTIONS),
        "instalaciones": _opciones(formulario.INSTALLS), "bios": _opciones(formulario.BIOSES),
        "nucleos": _opciones(formulario.CORES), "unidades": _opciones(formulario.CUS),
        "vistos": [{"valor": valor, "nombre": tr(valor)} for valor in formulario.SEEN],
        "herramientas": [{"valor": valor, "nombre": tr(valor)} for valor in formulario.OTHER_TOOLS],
        "automatico": [{"nombre": nombre, "valor": valor} for nombre, valor in automatico],
        "pista": tr(formulario.SUMMARY_HINT),
    }]


def _borrador(p: dict) -> report_form.Draft:
    """El reporte que llega del navegador, con cada campo acotado."""
    permitidos = {"kind", "values", "seen", "other_tools", "attach"}
    if set(p) - permitidos or not isinstance(p.get("values"), dict):
        raise Invalid("params")
    borrador = report_form.new_draft()
    borrador.kind = choice(p, "kind", (formulario.KIND_PROBLEM, formulario.KIND_IDEA))
    borrador.attach = flag(p, "attach")
    for clave, valor in p["values"].items():
        if clave not in LARGOS or not isinstance(valor, str) or len(valor) > LARGOS[clave]:
            raise Invalid(str(clave))
        borrador.values[clave] = valor.strip()
    for nombre, admitidos, destino in (("seen", formulario.SEEN, borrador.seen), ("other_tools", formulario.OTHER_TOOLS, borrador.other_tools)):
        marcados = p.get(nombre, [])
        if not isinstance(marcados, list) or any(uno not in admitidos for uno in marcados):
            raise Invalid(nombre)
        destino.update(marcados)
    falta = report_form.report_of(borrador).missing()
    if falta:
        raise Invalid(tr(falta))
    return borrador


def _documento(borrador):
    report_form.read_all_facts(borrador)
    return report_form.report_of(borrador)


def guardar_borrador(ctx, p) -> None:
    """El reporte se guarda aquí y la acción lo lee: no cabe en una línea de la consola."""
    _borrador(p)
    temporales.guardar_json("report", p)


def _guardado(p) -> report_form.Draft:
    if p:
        raise Invalid("params")
    try:
        return _borrador(temporales.leer_json("report"))
    except (OSError, ValueError) as error:
        raise Invalid("report") from error


def ver_reporte(ctx, p, shell):
    borrador = _guardado(p)
    return 0, lambda: json.dumps(formulario.payload(_documento(borrador)), indent=2, ensure_ascii=False)


def enviar_reporte(ctx, p, shell):
    borrador = _guardado(p)

    def enviar():
        try:
            identificador = formulario.submit(_documento(borrador))
        except formulario.ReportError as error:
            mensaje = tr_format("It was not sent: {reason}. What you wrote is still here.", reason=tr(str(error)).rstrip("."))
            if error.saved is not None:
                mensaje += " " + tr_format("A copy was saved to {path}.", path=formulario.redact_machine(str(error.saved)))
            raise RuntimeError(mensaje) from error
        temporales.borrar("report")
        return f"{tr('Thanks, it was sent')} ({identificador})"
    return 1, enviar


def vaciar_diagnostico(ctx, p) -> None:
    if p:
        raise Invalid("params")
    clear_history()


def vaciar_historial(ctx, p) -> None:
    if p:
        raise Invalid("params")
    if ctx.activity is not None:
        ctx.activity.clear()


SECCIONES = {
    "support": ("Support", portada), "support_detail": ("Report", detalle), "support_reports": ("View reports", informes),
    "support_errors": ("Known errors", errores_frecuentes), "support_error_detail": ("Known errors", error_detalle),
    "support_report": ("Report a problem", formulario_reporte), "telemetry_guide": ("Board sensors guide", guia_sensores),
}
ACCIONES = {"support.preview": ver_reporte, "support.send": enviar_reporte}
AJUSTES = {"support.draft": guardar_borrador, "support.clear_diagnostics": vaciar_diagnostico, "support.clear_history": vaciar_historial}

__all__ = ["ACCIONES", "AJUSTES", "SECCIONES", "accion"]
