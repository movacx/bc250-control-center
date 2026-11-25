"""Funciones del escritorio que la TUI no muestra: menús, Decky y editores."""
from __future__ import annotations

import math

from frontends.tui.content import Buttons, Field, Note, Panel
from frontends.tui.i18n import tr
from frontends.web.actions import Invalid

from .ajustes_adicionales_compat import Action, Fila, component

PROYECTOS = {
    "CPU power management · ACPI": "https://github.com/e-tho/bc250-acpi-fix",
    "Cyan Skillfish Governor": "https://github.com/filippor/cyan-skillfish-governor/tree/smu",
    "Oberon Governor": "https://gitlab.com/mothenjoyer69/oberon-governor",
    "GFX1013 async compute": "https://github.com/DryhoppedIPA/bc250-gfx1013-fix",
    "Install BC-250 kernel and Mesa for Arch/CachyOS": "https://github.com/MastaG/linux-cachyos-bc250",
    "BC-250 · MastaG": "https://github.com/MastaG/linux-cachyos-bc250",
    "Proton BC-250": "https://github.com/MastaG/linux-cachyos-bc250",
    "Hardware video · VA-API": "https://github.com/simpmix/bc250-encoding-decoding-fix",
    "Thermalright cooler display": "https://github.com/Lexonight1/thermalright-trcc-linux",
    "Corsair fans and RGB": "https://github.com/jurkovic-nikola/OpenLinkHub",
    "HDMI audio · Dolby Digital 5.1": "https://github.com/keyboardspecialist/bc250-steamos/tree/main/hdmi-ac3",
    "TV control · HDMI-CEC": "https://gitlab.steamos.cloud/holo/linux-cec",
    "Power delivery readings (I2C mod)": "https://github.com/onlinermm/BC250-Telemetry",
    "Power delivery readings (kernel driver)": "https://github.com/Hexxeh/bc250-vrm-dkms",
    "VRAM temperature (kernel driver)": "https://github.com/Hexxeh/bc250-memory-dkms",
    "Sleep · bc250-sleep": "https://github.com/superkeka/bc250-sleep",
    "DirectMesh": "https://github.com/DryhoppedIPA/DirectMesh",
    "BC-250 FSR4 V3": "https://github.com/daniel-h-0/bc250-fsr4-fork/blob/v4/docs/optiscaler-client.md",
    "FSR4 INT8": "https://github.com/daniel-h-0/bc250-fsr4-fork/blob/v4/docs/optiscaler-client.md",
    "HelixSR": "https://github.com/lonewolf0622/HelixSR",
}


def enlaces(titulo):
    for clave, url in PROYECTOS.items():
        if titulo == tr(clave) or titulo.startswith(tr(clave) + " "):
            return [{"label": "Open upstream project", "url": url}]
    return []


def texto(ui, titulo, detalle):
    ui.show_text(tr(titulo), detalle)


def agregar_decky(ctx, tools):
    from frontends.desktop.core.compatibility_dialogs import DECKY_BOOTSTRAP
    estado = tools.get("quick_access") or {}
    plugin = bool(estado.get("decky_detected") and estado.get("decky_frontend_compatible", True))
    etiqueta = "Install / repair BC250 Quick Access" if plugin else "Install Decky + Quick Access (Beta)"
    detalle = "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet." if estado.get("ready") else (
        "Decky must be updated because this Steam client uses the renamed initialization API." if estado.get("decky_detected") and not plugin else
        "Decky is detected, but the BC250 Quick Access plugin or its protected helper needs installation or repair." if plugin else
        "Decky is optional. It is never installed by generic dependency preparation.")
    pregunta = ("This installs or repairs only the local BC250 Quick Access plugin and its protected helper inside an existing "
                "Decky installation. It does not reinstall Decky or apply a hardware setting. Continue?") if plugin else DECKY_BOOTSTRAP
    acciones = []
    if estado.get("supported") and estado.get("decky_plugin_root_safe", True):
        acciones.append(Action(tr(etiqueta), lambda: ctx.service.preparar_quick_access_steamos(install_decky=not plugin), tr(pregunta), True))
    return Panel("Decky", [component(tr("Game Mode Quick Access (Beta)"), tr("Ready" if estado.get("ready") else "Not installed"),
                                      "ok" if estado.get("ready") else "dim", tr(detalle), acciones)])


def completar(ctx, datos, pestaña, paneles):
    tools = datos.get("tools") or {}
    if pestaña == "decky":
        return [agregar_decky(ctx, tools)]
    if pestaña == "compatibility":
        # El escritorio ofrece volver a comprobar también en los estados listos.
        for panel in paneles:
            for fila in panel.blocks:
                if isinstance(fila, Fila) and fila.label in (tr("Package manager lock · pacman"), tr("Kernel headers · DKMS")):
                    fila.acciones.append(Action(tr("Check again"), show=lambda ui, f=fila: ui.show_text(f.label, f.badge + "\n\n" + f.info.summary)))
                    fila.enabled = True
        _accesorios(ctx, tools, paneles)
    if pestaña == "drivers":
        _organizar_controladores(paneles)
        _accesorios(ctx, tools, paneles)
        # Los inventarios completos permanecen accesibles en Detalles.
        for panel in paneles:
            if panel.title == tr("External drivers"):
                panel.blocks = list(panel.blocks) + [component(tr("View compatibility guide"), "", "dim", "", [], blocked="")]
    if pestaña == "upscaling":
        _escalado(ctx, tools, paneles)
    return paneles


def _accesorios(ctx, tools, paneles):
    from .ajustes_adicionales_compat import ACCESSORIES, SENSORS
    accesorios = tools.get("accessories") or {}
    titulos = {key: title for key, title, _ in (*SENSORS, *ACCESSORIES)}
    # Mientras llega una sonda, cada fila sigue existiendo como «Comprobando».
    for key, title, detail in (*SENSORS, *ACCESSORIES):
        destino = "Sensors" if key in {s[0] for s in SENSORS} else "Audio and TV" if key.startswith("hdmi_") else "Case accessories"
        if (destino == "Sensors") != any(p.title == tr("GPU Governor") for p in paneles):
            continue
        panel = next((p for p in paneles if p.title == tr(destino)), None)
        if panel is None:
            panel = Panel(tr(destino), [])
            paneles.append(panel)
        if not any(isinstance(f, Fila) and f.label == tr(title) for f in panel.blocks):
            if key not in accesorios:
                panel.blocks = list(panel.blocks) + [component(tr(title), tr("Checking"), "dim", tr(detail), [])]
    for panel in paneles:
        for fila in panel.blocks:
            if not isinstance(fila, Fila):
                continue
            key = next((k for k, title in titulos.items() if fila.label == tr(title)), None)
            if key is None:
                continue
            estado = accesorios.get(key) or {}
            if key == "hdmi_ac3" and estado.get("state") == "installed":
                fila.acciones.insert(0, Action(tr("Use 5.1 output"), lambda: ctx.service.manage_accessory("hdmi_ac3", "install")))
            if estado.get("state") in ("installed", "active", "update-available", "relogin-required", "managed-elsewhere"):
                if key == "thermalright":
                    def configurar(ui):
                        ui.run(tr("Open configuration"), lambda: ui.shell(ctx.service.accessory_configure_argv("thermalright")))
                    fila.acciones.insert(0, Action(tr("Open configuration"), show=configurar))
                # El panel de Corsair usa un enlace validado y cerrado; se abre
                # en el navegador del equipo que controla la sesión.
                if key == "corsair":
                    fila.acciones.insert(0, Action(tr("Open control panel"), show=lambda ui: ui.show_text(tr("Open control panel"), "http://127.0.0.1:27003")))
            if key == "apu_telemetry":
                for accion in fila.acciones:
                    if accion.label == tr("Install"):
                        accion.label = tr("Install service")
                    elif accion.label == tr("Remove"):
                        accion.label = tr("Remove service")
            fila.enabled = bool(fila.acciones)


def _escalado(ctx, tools, paneles):
    fsr4, helixsr = tools.get("fsr4") or {}, tools.get("helixsr") or {}
    if not paneles:
        return
    for fila in paneles[0].blocks:
        if not isinstance(fila, Fila):
            continue
        if fila.label.startswith("BC-250 FSR4 V3"):
            fila.label = tr("FSR4 INT8")
            fila.info = type(fila.info)(tr("AMD's FSR 4 in INT8, installed per game by OptiScaler Client."))
            fila.acciones.append(Action(tr("Check for new releases"), lambda: ctx.service.gestionar_fsr4_bc250("releases")))
            if fsr4.get("current"):
                if not any(a.label == tr("Open configuration") for a in fila.acciones):
                    fila.acciones.append(Action(tr("Open configuration"), lambda: ctx.service.gestionar_fsr4_bc250("launch")))
                fila.acciones.append(Action(tr("Add to every Steam game"), lambda: ctx.service.gestionar_fsr4_bc250("steam_option_all"), tr(
                    "Every installed Steam game gets the option OptiScaler needs. What each game already had stays, "
                    "and games without OptiScaler run as before. Close Steam first.")))
            if fsr4.get("legacy_installed") or fsr4.get("legacy"):
                fila.acciones.append(Action(tr("Remove old FSR4 V3 runtime"), lambda: ctx.service.gestionar_fsr4_bc250("legacy_uninstall"), danger=True))
        if fila.label.startswith("HelixSR"):
            fila.acciones.append(Action(tr("Check for new releases"), lambda: ctx.service.gestionar_helixsr("releases")))
            if helixsr.get("current"):
                capacidades = helixsr.get("capabilities") or {}
                if str(helixsr.get("layout")) == "3":
                    for key, label, action in (("preset_k", "Build Preset K", "network:preset_k"),
                                                ("vulkan", "Build Vulkan kernels", "network:vulkan,rebuild")):
                        if capacidades.get(key):
                            fila.acciones.append(Action(tr(label), lambda a=action: ctx.service.gestionar_helixsr(a)))
                elif helixsr.get("scaler_supported"):
                    fila.acciones.append(Action(tr("Build frame generation"), lambda: ctx.service.gestionar_helixsr("fg")))
                def añadir(ui):
                    ruta = ui.ask_text(tr("Choose the game's folder"))
                    ui.run(tr("Add OptiScaler game"), lambda: ctx.service.gestionar_helixsr("add_opti_folder:" + ruta))
                fila.acciones.append(Action(tr("Add OptiScaler game"), show=añadir))
        fila.enabled = bool(fila.acciones)


def opciones_helixsr(datos):
    from bc250cc.infrastructure.helixsr import HELIXSR_SETTINGS
    estado = (datos.get("tools") or {}).get("helixsr") or {}
    if not estado.get("current"):
        return []
    valores = estado.get("settings") or {}
    opciones = []
    if str(estado.get("layout")) != "3":
        for seccion, clave, tipo, defecto, elecciones in HELIXSR_SETTINGS:
            identificador = f"{seccion}.{clave}"
            opciones.append({"id": identificador, "label": f"{seccion} · {clave}", "kind": tipo,
                             "value": valores.get(identificador, defecto),
                             "choices": list(elecciones) if tipo == "choice" else [],
                             "min": elecciones[0] if tipo == "float" else 0,
                             "max": elecciones[-1] if tipo == "float" else 1})
    for grupo in ("extra_settings", "scaler_settings", "bridge_settings"):
        for fila in estado.get(grupo) or ():
            elecciones = list(fila.get("choices") or ())
            tipo = fila.get("kind") or fila.get("type") or "choice"
            opciones.append({"id": fila["id"], "label": f"{fila.get('section', '')} · {fila.get('key', fila['id'])}",
                             "kind": tipo, "value": valores.get(fila["id"], fila.get("value", fila.get("default", ""))),
                             "choices": elecciones, "min": fila.get("min", 0), "max": fila.get("max", 64)})
    return opciones


def validar_helixsr(datos, valores):
    if not isinstance(valores, dict) or not 1 <= len(valores) <= 128:
        raise Invalid("values")
    opciones = {fila["id"]: fila for fila in opciones_helixsr(datos)}
    for clave, valor in valores.items():
        fila = opciones.get(clave)
        if not fila:
            raise Invalid("setting")
        if fila["kind"] == "bool":
            valido = isinstance(valor, bool)
        elif fila["choices"]:
            valido = any(type(valor) is type(v) and valor == v for v in fila["choices"])
        else:
            valido = type(valor) in (int, float) and math.isfinite(valor) and fila["min"] <= valor <= fila["max"]
        if not valido:
            raise Invalid(clave)
    return dict(valores)


ALCANCES = {
    "Package manager lock · pacman": "Systems with pacman: Arch, CachyOS, Manjaro, SteamOS",
    "Kernel headers · DKMS": "Systems with pacman, dnf or apt: Arch, CachyOS, Manjaro, Fedora, Ubuntu, Linux Mint, Debian",
    "Cyan Skillfish Governor": "Arch · Fedora · Debian/Ubuntu · Bazzite",
    "Oberon Governor": "Alternative backend",
    "CPU power management · ACPI": "Validated · Arch / CachyOS / Manjaro",
    "Thermalright cooler display": "Case accessory", "Corsair fans and RGB": "Case accessory",
    "Power delivery readings (I2C mod)": "Board sensor",
    "Power delivery readings (kernel driver)": "Board sensor", "VRAM temperature (kernel driver)": "Board sensor",
    "HDMI audio · Dolby Digital 5.1": "Audio and TV", "TV control · HDMI-CEC": "Audio and TV",
    "DirectMesh": "Experimental", "Hardware video · VA-API": "Beta",
}


def alcance(titulo):
    for clave, valor in ALCANCES.items():
        if titulo == tr(clave) or titulo.startswith(tr(clave) + " "):
            return f"{tr('Compatibility')}: {tr(valor)}"
    return ""


def _organizar_controladores(paneles):
    conectividad = []
    otros = []
    for panel in paneles:
        if panel.title not in (tr("Network"), tr("Printing"), tr("External drivers")):
            otros.append(panel)
            continue
        titulo = {tr("Network"): "Wi-Fi and Bluetooth support", tr("Printing"): "Printing support",
                  tr("External drivers"): "External drivers"}[panel.title]
        detalle = []
        acciones = []
        for elemento in panel.blocks:
            if isinstance(elemento, Field):
                detalle.append(f"{elemento.label}: {elemento.value}")
            elif isinstance(elemento, Note):
                detalle.append(elemento.text)
            elif isinstance(elemento, Buttons):
                for boton in elemento.choices:
                    acciones.append(Action(boton.label, show=boton.handler, enabled=boton.enabled))
        fila = component(tr(titulo), "", "dim", panel.subtitle, acciones)
        # El inventario y la guía completos aparecen en el diálogo Detalles.
        fila.info = type(fila.info)(panel.subtitle, "\n".join(detalle))
        conectividad.append(fila)
    if conectividad:
        otros.insert(0, Panel(tr("Connectivity"), conectividad))
    paneles[:] = otros
