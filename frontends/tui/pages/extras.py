"""Additional settings, laid out as the desktop's: Compatibility, Upscaling, Memory & Swap and Drivers.

Every action calls the same service method as its desktop card, which checks
the distribution itself and refuses what does not apply. The rows only decide
what is worth offering on this system, from the tools snapshot.
"""

from __future__ import annotations

from bc250cc.application.preparation.gpu_dependency_plan import (
    build_gpu_dependency_plan,
)

from ..content import Buttons, Choice, Field, Note, Panel, Split, Tile, Tiles
from ..i18n import tr, tr_format
from .base import Page, guarded, os_family

TAB_TITLES = (("compatibility", "Compatibility"), ("upscaling", "Upscaling"), ("memory", "Memory & Swap"),
              ("drivers", "Drivers"))
MEMORY_POLICIES = (
    ("current", "Keep current configuration"),
    ("zram", "ZRAM (compressed RAM swap)"),
    ("zram-swap-16", "Recommended · ZRAM + 16 GiB emergency swap"),
    ("swap-16", "Disk swap · 16 GiB"),
    ("swap-32", "Disk swap · 32 GiB"),
    ("zswap-16", "ZSWAP + 16 GiB swapfile"),
    ("zswap-32", "Heavy games · ZSWAP + 32 GiB swapfile"),
    ("restore", "Restore BC250 memory changes"),
)
#: The ACPI correction's states, as the desktop's card names them.
ACPI_STATUS = {"active": ("Active", "ok"), "pending-reboot": ("Reboot required", "warn"),
               "not-active": ("Not active", "warn"), "incomplete": ("Incomplete", "warn"),
               "managed-elsewhere": ("Managed externally", "accent"), "needs-check": ("Not verified", "dim"),
               "outdated": ("Update available", "warn"), "needs-repair": ("Repair required", "warn")}
GOVERNORS = (("cyan-skillfish-governor-smu", "Cyan Skillfish Governor", "Arch · Fedora · Debian/Ubuntu · Bazzite",
              "Recommended GPU governor. Supports SMU or patched-kernel controls, selectable load monitoring and "
              "D-Bus ranges."),
             ("oberon-governor", "Oberon Governor", "Alternative backend",
              "Alternative YAML-based backend. GPU telemetry repair remains a separate compatibility step."))
INSTALL = (("status", "Status"), ("install", "Install"), ("uninstall", "Uninstall"))
#: GFX1013 async compute: the reviewed path of each distribution (method, its actions, families).
GFX1013 = (
    ("gestionar_gfx1013_bazzite", INSTALL, ("bazzite",)),
    ("gestionar_gfx1013_fedora", INSTALL + (("boot-patched", "boot-patched"), ("activate", "activate")), ("fedora",)),
    ("gestionar_gfx1013_source", INSTALL + (("rebuild", "Rebuild"), ("enable", "Enable"), ("disable", "Disable")),
     ("arch", "cachyos", "manjaro", "ubuntu", "debian")),
    ("gestionar_radv_async", INSTALL + (("enable", "Enable"), ("disable", "Disable"), ("test", "Test")),
     ("fedora", "arch", "cachyos", "manjaro", "ubuntu", "debian")),
)
#: Kernel options that need a reboot: (tools key, title, description, method, (disable, restore) labels).
REBOOT_CARDS = (
    ("bazzite_mitigations", "CPU security mitigations",
     "Disabling CPU security mitigations can improve some workloads but exposes the system to additional CPU "
     "vulnerabilities.", "gestionar_mitigaciones_bazzite", ("disable", "Disable mitigations"),
     ("restore", "Restore mitigations")),
    ("bazzite_smt", "Simultaneous multithreading (SMT)",
     "The CPU runs one thread per core: 6 or 8 threads instead of 12 or 16. Some games run smoother, others slower; "
     "measure yours. The change applies after reboot and can be restored from Control Center.",
     "gestionar_smt_bazzite", ("disable", "Disable SMT"), ("restore", "Restore SMT")),
    ("bazzite_boot_messages", "Boot messages (hides the RDSEED warning)",
     "The BC-250's CPU makes the kernel print an RDSEED warning at every boot. This hides all kernel messages on "
     "screen while the system starts; they stay in dmesg.", "gestionar_mensajes_arranque_bazzite",
     ("hide", "Hide boot messages"), ("restore", "Show boot messages")),
)
#: The distribution's own BC-250 stacks, offered only where they apply.
DISTRIBUTION = (
    ("SteamOS read-only mode", "gestionar_solo_lectura_steamos", (("status", "Status"), ("disable", "Disable"),
                                                                    ("enable", "Enable")), ("steamos",)),
    ("Graphics", "gestionar_graficos_steamos", INSTALL + (("install-fsr4", "install-fsr4"),
                                                          ("uninstall-fsr4", "uninstall-fsr4")), ("steamos",)),
    ("Check SteamOS compatibility", "preparar_compatibilidad_steamos", (), ("steamos",)),
    ("BC250 SteamOS diagnostics", "diagnostico_steamos", (), ("steamos",)),
    ("Newer kernel and Mesa for the BC-250", "gestionar_kernel_debian", (("install", "Install"),), ("debian",)),
    ("Mesa", "gestionar_mesa_desktop", (("install", "Install"),), ("ubuntu",)),
    ("Install BC-250 kernel and Mesa for Arch/CachyOS", "preparar_cachyos_bc250",
     (("full", "Prepare everything"), ("kernel", "Kernel"), ("mesa", "Mesa")), ("cachyos",)),
)
GUIDE_URL = ("https://github.com/morrownr/USB-WiFi/blob/main/home/"
             "USB_WiFi_Adapters_that_are_supported_with_Linux_in-kernel_drivers.md")


def run(ui, label: str, method, actions=(), danger=False) -> None:
    """Pick one of ``actions`` (when there are several), confirm, then run it in the console."""
    argument = None
    if len(actions) > 1:
        argument = ui.choose(tr(label), [(key, name if name == key else tr(name)) for key, name in actions])
        if argument is None:
            return
    elif actions:
        argument = actions[0][0]
    if ui.confirm(tr(label) + (f": {argument}" if argument else ""), danger=danger and argument != "status"):
        guarded(ui, tr(label), (lambda: method(argument)) if argument else method)


def row(state: dict, key: str, title: str, scope: str, status: str, tone: str, body) -> list:
    """A desktop compatibility row: › title, its scope and a status chip; Enter folds its detail open."""
    opened = key in state.setdefault("open", set())
    return [Choice(f"{'▾' if opened else '›'} {tr(title)}", lambda ui_: state["open"].symmetric_difference_update({key}),
                   scope, badge=tr(status), badge_tone=tone)] + (list(body) if opened else [])


class AdditionalSettingsPage(Page):
    key = "extras"
    title = "Additional settings"
    interval = 6.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TAB_TITLES]

    def load(self, ctx):
        tools = ctx.service.estado_herramientas_bc250()
        try:
            drivers = ctx.service.driver_inventory()
        except Exception:
            drivers = {}
        return {"tools": tools, "drivers": drivers}

    def build(self, ctx, data, tab, ui):
        data = data or {}
        family, name = os_family(ctx)
        build = {"upscaling": self._upscaling, "memory": self._memory, "drivers": self._drivers}.get(
            tab or "compatibility", self._compatibility)
        return [Note(tr_format("Detected system: {distribution}", distribution=name), "dim")] + build(ctx, data, family)

    # -- Compatibility: System, GPU governor, Kernel and graphics, Video, then the reboot options ---------

    def _compatibility(self, ctx, data, family):
        service, state = ctx.service, ctx.state(self.key)
        tools = data.get("tools") or {}
        acpi = ((tools.get("system_setup") or {}).get("acpi") or {})
        status, tone = ACPI_STATUS.get(str(acpi.get("status") or ""), ("Not installed", "dim"))
        acpi_actions = [Choice(tr("Install correction"), lambda ui_: run(ui_, "Install correction", service.gestionar_acpi,
                                                                         (("acpi-install", "Install"),), True))]
        if acpi.get("status") in ("outdated", "needs-repair"):
            acpi_actions.append(Choice(tr("Update correction"), lambda ui_: run(
                ui_, "Update correction", service.gestionar_acpi, (("acpi-update", "Update"),), True)))
        acpi_actions += [Choice(tr("Uninstall"), lambda ui_: run(ui_, "Uninstall", service.gestionar_acpi,
                                                                 (("acpi-uninstall", "Uninstall"),), True), tone="bad"),
                         Choice(tr("Check status"), lambda ui_: guarded(ui_, tr("Check status"),
                                                                        lambda: service.gestionar_acpi("acpi-check")))]
        system = Panel(tr("System"), row(state, "acpi", "CPU power management · ACPI", f"{tr('Beta')} · {family.title()}",
                                         status, tone, [Note(tr("Upstream CPU idle and frequency tables. The original "
                                                                "boot entry remains available for recovery."), "dim"),
                                                        Buttons(acpi_actions)]))

        def governor(ui_, identifier, action):
            plan = build_gpu_dependency_plan(tools, current_governor=tools.get("governor_backend"), action=action,
                                             preference=identifier)
            label = tr("Uninstall") if action == "remove" else tr("Install / update")
            if not ui_.confirm(f"{label}: {identifier}" + (f" ({', '.join(plan.conflicts)})" if plan.conflicts else ""),
                               danger=bool(plan.conflicts) or action == "remove"):
                return
            ctx.settings.save_local_config({"gpu_governor": "auto" if action == "remove" else plan.preference})
            work = (lambda: service.desinstalar_governor(plan.preference)) if action == "remove" else \
                (lambda: service.instalar_governor(plan.has_conflicts, plan.has_conflicts, plan.preference))
            guarded(ui_, label, work)

        governors = []
        for identifier, title, scope, detail in GOVERNORS:
            found = (tools.get("supported_gpu_governors") or {}).get(identifier) or {}
            status, tone = ("Active", "ok") if found.get("active") else ("Installed", "accent") if found.get("detected") \
                else ("Not installed", "dim")
            if identifier.startswith("cyan") and tools.get("cyan_runtime_update_available"):
                status, tone = "Update available", "warn"
            governors += row(state, identifier, title, tr(scope), status, tone, [Note(tr(detail), "dim"), Buttons([
                Choice(tr("Install / update"), lambda ui_, i=identifier: governor(ui_, i, "prepare")),
                Choice(tr("Uninstall"), lambda ui_, i=identifier: governor(ui_, i, "remove"), tone="bad",
                       enabled=bool(found.get("detected")))])])

        gfx = tools.get("gfx1013_compute") or {}
        paths = [(method, actions) for method, actions, families in GFX1013 if family in families]
        gfx_state = str(gfx.get("status") or "")
        kernel = Panel(tr("Kernel and graphics"), row(
            state, "gfx1013", "GFX1013 async compute",
            " · ".join(part for part in (str(gfx.get("version_id") or ""),
                                         f"v{gfx['reviewed_version']}" if gfx.get("reviewed_version") else "") if part),
            "Async compute detected" if gfx_state in ("available", "active") else gfx_state or "Not installed",
            "ok" if gfx_state in ("available", "active") else "dim",
            [Note(tr("Kernel and Mesa must be matched. The interface enables installation only on a reviewed "
                     "distribution path."), "dim")] + [Buttons([
                         Choice(f"{tr('Install / update')} · {method.split('_')[-1]}",
                                lambda ui_, m=method, a=actions: run(ui_, "GFX1013 async compute", getattr(service, m), a))
                         for method, actions in paths])] if paths else []))

        vaapi = tools.get("vaapi_video") or {}
        video = Panel(tr("Video"), row(
            state, "vaapi", "Hardware video · VA-API", tr("Beta"),
            "Active" if vaapi.get("state") == "active" else "Installed" if vaapi.get("installed") else "Not installed",
            "ok" if vaapi.get("state") == "active" else "dim",
            [Buttons([Choice(tr(label), lambda ui_, a=action: run(ui_, "Hardware video · VA-API", service.gestionar_vaapi,
                                                                  ((a, a),), a == "uninstall"),
                             tone="bad" if action == "uninstall" else "")
                      for action, label in (("install", "Install"), ("test", "Test"), ("uninstall", "Uninstall"))])]))

        out = [system, Panel(tr("GPU Governor"), governors), kernel, video]
        for key, title, detail, method, disable, restore in REBOOT_CARDS:
            option = tools.get(key) or {}
            if not option.get("available"):
                continue
            action, label = restore if option.get("configured") else disable
            out.append(Panel(tr(title), [Note(tr(detail), "dim"), Buttons([Choice(
                tr(label), lambda ui_, m=getattr(service, method), a=action, t=label: run(ui_, t, m, ((a, a),), a != "restore"),
                tone="" if action == "restore" else "bad")])],
                badge=tr("Reboot required") if option.get("reboot_required") else tr("Active" if option.get("active") else ""),
                badge_tone="warn"))
        others = [item for item in DISTRIBUTION if family in item[3]]
        if others:
            out.append(Panel(tr("Other distributions"), [Choice(tr(label) + (" ›" if actions else ""),
                                                               lambda ui_, m=method, a=actions, t=label: run(
                                                                   ui_, t, getattr(service, m), a))
                                                        for label, method, actions, _families in others]))
        return out

    # -- Upscaling -----------------------------------------------------------------------------------

    def _upscaling(self, ctx, data, family):
        service, state = ctx.service, ctx.state(self.key)
        tools = data.get("tools") or {}
        out = []
        for key, title, method, actions, detail in (
                ("fsr4", "BC-250 FSR4 V3", service.gestionar_fsr4_bc250,
                 (("install", "Install"), ("uninstall", "Uninstall")),
                 "Installs OptiScaler and the BC250 FSR4 DLL into the games you choose, with a backup of every file it "
                 "replaces. Your driver and Proton stay as they are."),
                ("helixsr", "HelixSR", service.gestionar_helixsr,
                 (("install", "Install"), ("uninstall", "Uninstall"), ("update_all", "update_all")), "")):
            item = tools.get(key) or {}
            installed = bool(item.get("installed"))
            out += row(state, key, title, str(item.get("version") or ""), "Installed" if installed else "Not installed",
                       "ok" if installed else "dim",
                       ([Note(tr(detail), "dim")] if detail else []) + [Buttons([
                           Choice(tr(label) if label != action else label,
                                  lambda ui_, a=action, t=title, m=method: run(ui_, t, m, ((a, a),), a == "uninstall"),
                                  tone="bad" if action == "uninstall" else "") for action, label in actions])])
        return [Panel(tr("Upscaling"), out)]

    # -- Memory & Swap -------------------------------------------------------------------------------

    def _memory(self, ctx, data, family):
        service, state = ctx.service, ctx.state(self.key)
        runtime = (data.get("tools") or {}).get("memory_runtime") or {}
        presets = tuple(runtime.get("supported_ttm_gib_presets") or (8, 10, 12))
        picks = state.setdefault("memory", {"policy": "current", "ttm": 0, "vram": 0})

        def gib(value):
            return f"{value / 2**30:.1f} GiB" if value else "--"

        def pick(key, title, options):
            def handler(ui_):
                chosen = ui_.choose(tr(title), options)
                if chosen is not None:
                    picks[key] = chosen
            return handler

        def apply(ui_, label, work):
            if ui_.confirm(tr(label), danger=True):
                guarded(ui_, tr(label), work)

        policies = [(key, tr(label)) for key, label in MEMORY_POLICIES]
        ttm = [(0, tr("Keep current TTM limit"))] + [(value, f"{value} GiB") for value in presets]
        vram = [(0, tr("Keep current VRAM size"))] + [(size, f"{size} MB") for size in (512, 1024, 2048, 4096, 8192)]
        summary = Tiles([
            Tile(tr("Physical RAM"), gib(runtime.get("physical_ram_bytes")), ""),
            Tile("ZRAM", gib(runtime.get("zram_total_bytes")) if runtime.get("zram_active") else tr("Disabled"), ""),
            Tile(tr("Disk swap"), gib(runtime.get("backing_swap_total_bytes")) if runtime.get("backing_swap_active")
                 else tr("None"), ""),
            Tile("ZSWAP", tr("Active" if runtime.get("zswap_enabled") else "Disabled"), ""),
            Tile(tr("GPU memory limit (TTM)"), gib(runtime.get("ttm_limit_bytes")), "")], minimum=18)
        return [Panel(tr("Memory & Swap"), [summary]),
                Panel(tr("Swap"), [Choice(tr("Swap"), pick("policy", "Swap", policies), dict(policies)[picks["policy"]] + " ›"),
                                   Buttons([Choice(tr("Apply Swap"), lambda ui_: apply(
                                       ui_, "Apply Swap", lambda: service.preparar_memoria(picks["policy"], 0)),
                                       tone="primary")])]),
                Panel(tr("GPU memory limit (TTM)"), [
                    Choice(tr("TTM limit"), pick("ttm", "GPU memory limit (TTM)", ttm), dict(ttm)[picks["ttm"]] + " ›"),
                    Buttons([Choice(tr("Apply TTM"), lambda ui_: apply(
                        ui_, "Apply TTM", lambda: service.preparar_memoria("current", int(picks["ttm"]))),
                        tone="primary", enabled=bool(picks["ttm"]))])]),
                Panel(tr("VRAM size (UMA_SIZE)"), [
                    Choice(tr("VRAM size"), pick("vram", "VRAM size (UMA_SIZE)", vram), dict(vram)[picks["vram"]] + " ›"),
                    Buttons([Choice(tr("Apply VRAM"), lambda ui_: apply(
                        ui_, "Apply VRAM", lambda: service.preparar_vram(int(picks["vram"]))),
                        tone="primary", enabled=bool(picks["vram"]))])])]

    # -- Drivers: network, printing and the external ones -------------------------------------------

    def _drivers(self, ctx, data, family):
        service = ctx.service
        snapshot = data.get("drivers") or {}
        supported = set(snapshot.get("supported_components") or ())

        def install(component, title):
            def handler(ui_):
                if ui_.confirm(tr(title)):
                    guarded(ui_, tr(title), lambda: service.install_driver_support(component))
            return handler

        network = []
        for item in snapshot.get("network") or ():
            up = item.get("state") == "up"
            kind = tr("Wi-Fi") if item.get("kind") == "wifi" else tr("Ethernet")
            network.append(Field(str(item.get("name", "--")), f"{tr_format('{kind} · driver: {driver}', kind=kind, driver=item.get('driver') or tr('No kernel driver'))} · {item.get('state') or '--'}",
                                 "ok" if up else "dim"))
        bluetooth = list(snapshot.get("bluetooth_controllers") or ())
        network.append(Field(tr("Bluetooth"), ", ".join(bluetooth) if bluetooth else tr("No controller detected"),
                             "ok" if bluetooth else "dim"))
        printing = snapshot.get("printing") or {}
        services = [name for key, name in (("cups_tools", "CUPS"), ("ipp_usb", "IPP-over-USB")) if printing.get(key)]
        queues, printers = list(printing.get("queues") or ()), list(snapshot.get("usb_printers") or ())
        aic = snapshot.get("aic8800") or {}
        detected = bool(aic.get("loaded") or aic.get("candidate_detected"))
        return [Split([
            Panel(tr("Network"), network + [Buttons([Choice(tr("Install support"), install("connectivity", "Network support"),
                                                            enabled="connectivity" in supported)])],
                  subtitle=tr("Active kernel drivers and official firmware packages.")),
            Panel(tr("Printing"), [
                Field(tr("Printing stack"), ", ".join(services) or tr("Printing packages not detected"),
                      "ok" if services else "dim"),
                Field(tr("Printer queues"), ", ".join(queues) if queues else tr("No configured queues")),
                Field(tr("USB printers"), ", ".join(str(p.get("name", "USB")) for p in printers) if printers
                      else tr("No USB printer detected"), "ok" if printers else "dim"),
                Buttons([Choice(tr("Install support"), install("printing", "Printing support"),
                                enabled="printing" in supported)])],
                subtitle=tr("Driverless printing with CUPS, IPP and IPP-over-USB. Existing queues are preserved."))],
            [Panel(tr("External drivers"), [
                Field("AIC8800", tr("Detected; automatic installation remains disabled.") if detected
                      else tr("SteamOS-specific; Wi-Fi only. Never installed automatically."), "warn" if detected else "dim"),
                Note(tr("Prefer devices supported by in-kernel Linux drivers."), "dim"),
                Buttons([Choice(tr("View compatibility guide"), lambda ui_: ui_.show_text(
                    tr("View compatibility guide"), f"{tr('Prefer devices supported by in-kernel Linux drivers.')}\n\n{GUIDE_URL}"))])],
                subtitle=tr("Device-specific kernel modules are not generic driver packs."), badge=tr("Reference only"),
                badge_tone="warn")], ratio=0.55)]
