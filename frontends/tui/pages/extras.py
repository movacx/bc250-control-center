"""Additional settings, laid out as the desktop's: Compatibility, Upscaling, Memory & Swap and Drivers.

Every action calls the same service method as its desktop card, which checks
the distribution itself and refuses what does not apply. The rows only decide
what is worth offering on this system, from the tools snapshot.
"""

from __future__ import annotations

import os
from pathlib import Path

from bc250cc.application.preparation.gpu_dependency_plan import (
    build_gpu_dependency_plan,
)
from bc250cc.application.system.cachyos_kernel import DEPENDENCY_NOTE
from bc250cc.shared.contract import vram_size_choices
from frontends.desktop.core.upscaling_rows import game_matrix_rows

from ..content import Buttons, Choice, Field, Info, Note, Panel
from ..i18n import tr, tr_format
from . import compat
from .base import Page, guarded, os_family
from .compat import Action

TAB_TITLES = (("compatibility", "Compatibility"), ("boot", "Kernel boot options"), ("upscaling", "Upscaling"), ("memory", "Memory & Swap"),
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
SWAP_POLICIES = (
    ("preserve", "Keep current configuration"),
    ("swap-16", "Disk swap · 16 GiB"),
    ("swap-32", "Disk swap · 32 GiB"),
    ("zram", "ZRAM · up to 4 GiB"),
    ("zswap-16", "Advanced · ZSWAP + 16 GiB swapfile"),
    ("zswap-32", "Advanced heavy loads · ZSWAP + 32 GiB swapfile"),
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
    ("BC250 SteamOS diagnostics", "diagnostico_steamos", (), ("steamos",)),
    ("Newer kernel and Mesa for the BC-250", "gestionar_kernel_debian", (("install", "Install"),), ("debian",)),
    ("Mesa", "gestionar_mesa_desktop", (("install", "Install"),), ("ubuntu",)),
    ("Install BC-250 kernel and Mesa for Arch/CachyOS", "preparar_cachyos_bc250",
     (("full", "Prepare everything"), ("kernel", "Kernel"), ("mesa", "Mesa"),
      ("pahole", "Prepare dependencies")), ("arch", "cachyos")),
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
    message = tr(label) + (f": {argument}" if argument else "")
    if argument == "pahole":
        from bc250cc.application.system.cachyos_kernel import DEPENDENCY_NOTE

        message += "\n\n" + tr(DEPENDENCY_NOTE)
    if ui.confirm(message, danger=danger and argument != "status"):
        guarded(ui, tr(label), (lambda: method(argument)) if argument else method)


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
        # Both read files only, and change with every package action: read with the page.
        from bc250cc.application.system.package_state import headers_state, lock_state

        state = {}
        for key, read in (("lock", lock_state), ("headers", headers_state)):
            try:
                state[key] = read()
            except Exception:  # a failed read must not blank the page
                state[key] = {}
        return {"tools": tools, "drivers": drivers, **state}

    def build(self, ctx, data, tab, ui):
        data = data or {}
        family, name = os_family(ctx)
        build = {"boot": self._boot_options, "upscaling": self._upscaling, "memory": self._memory, "drivers": self._drivers}.get(
            tab or "compatibility", self._compatibility)
        return [Note(tr_format("Detected system: {distribution}", distribution=name), "dim")] + build(ctx, data, family)

    # -- Compatibility: System, GPU governor, Kernel and graphics, Video, then the reboot options ---------

    def _compatibility(self, ctx, data, family):
        service = ctx.service
        tools = data.get("tools") or {}
        setup = tools.get("system_setup") or {}
        accessories = tools.get("accessories") or {}
        out = [Panel(tr("System"), [choice for choice in (
            self._acpi(service, setup.get("acpi") or {}),
            compat.real_sleep(service, accessories.get("real_sleep") or {}),
            compat.kernel_headers(service, data.get("headers") or {}),
            compat.pacman_lock(service, data.get("lock") or {}),
            compat.read_only_mode(service, tools.get("steamos_readonly") or {}),
        ) if choice is not None])]
        out.append(Panel(tr("GPU Governor"), [self._governor(ctx, tools, *entry) for entry in GOVERNORS]))

        gfx = tools.get("gfx1013_compute") or {}
        gfx_state = str(gfx.get("status") or "")
        detected = gfx_state in ("available", "active")
        actions = [Action(f"{method.removeprefix('gestionar_')} · {name if name == key else tr(name)}",
                          lambda m=method, k=key: getattr(service, m)(k), "", key in ("uninstall", "disable"), confirm=key != "status")
                   for method, entries, families in GFX1013 if family in families for key, name in entries]
        graphics = [compat.component(
            tr("GFX1013 async compute"), tr("Async compute detected" if detected else gfx_state or "Not installed"),
            "ok" if detected else "dim",
            tr("Kernel and Mesa must be matched. The interface enables installation only on a reviewed distribution path."),
            actions)] if family != "steamos" else []
        mesh = compat.directmesh(service, tools.get("directmesh") or {})
        graphics += [mesh] if mesh is not None else []
        others = [item for item in DISTRIBUTION if family in item[3]]
        for label, method, entries, _families in others:
            graphics.append(compat.component(tr(label), "", "dim", "", [
                Action(tr(name) if name != key else name, lambda m=method, k=key: getattr(service, m)(k),
                       tr(DEPENDENCY_NOTE) if key == "pahole" else "", key in ("uninstall", "disable"), confirm=key != "status")
                for key, name in entries] or [Action(tr(label), getattr(service, method))]))
        if graphics:
            out.append(Panel(tr("Kernel and graphics"), graphics))
        out.append(Panel(tr("Video"), [compat.vaapi(service, tools.get("vaapi_video") or {})]))
        sensors = [row for row in (compat.accessory(service, key, title, detail, accessories.get(key) or {})
                                   for key, title, detail in compat.SENSORS) if row is not None]
        if sensors:
            out.append(Panel(tr("Sensors"), sensors))
        if family == "steamos" and tools.get("steamos_real_toolkit"):
            session = (tools.get("steamos_readonly") or {}).get("toolkit_session") or {}
            out += compat.real_toolkit(service, tools, session)
            out.append(compat.alternative(service, tools))
        return out

    # -- Kernel boot options -------------------------------------------------------------------------

    def _boot_options(self, ctx, data, family):
        service, tools = ctx.service, data.get("tools") or {}
        options = compat.kernel_options(service, tools.get("system_setup") or {})
        out = [options] if options else []
        reboot = []
        for key, title, detail, method, disable, restore in REBOOT_CARDS:
            option = tools.get(key) or {}
            if not option.get("available"):
                continue
            action, label = restore if option.get("configured") else disable
            status, tone = ("Reboot required", "warn") if option.get("reboot_required") else \
                ("Active", "ok") if option.get("active") else ("Disabled", "dim")
            reboot.append(compat.component(tr(title), tr(status), tone, tr(detail), [
                Action(tr(label), lambda m=method, a=action: getattr(service, m)(a), "", action != "restore")],
                undo=tr(restore[1])))
        if reboot:
            out.append(Panel(tr("Kernel boot options"), reboot, badge=family))
        if not out:
            out.append(Panel(tr("Kernel boot options"), [Note(tr("Not available here"), "dim")]))
        try:
            arguments = Path("/proc/cmdline").read_text(encoding="utf-8").split()
        except OSError:
            arguments = []
        if arguments:
            out.append(Panel(tr("Kernel"), [Note("  ".join(
                part for part in arguments if not part.startswith(("root=", "rd.luks", "resume=", "cryptdevice="))), "dim")],
                subtitle=os.uname().release))
        return out

    @staticmethod
    def _acpi(service, acpi):
        status, tone = ACPI_STATUS.get(str(acpi.get("status") or ""), ("Not installed", "dim"))
        actions = [Action(tr("Install correction"), lambda: service.gestionar_acpi("acpi-install"), "", True)]
        if acpi.get("status") in ("outdated", "needs-repair"):
            actions.append(Action(tr("Update correction"), lambda: service.gestionar_acpi("acpi-update"), "", True))
        actions += [Action(tr("Check status"), lambda: service.gestionar_acpi("acpi-check"), confirm=False),
                    Action(tr("Uninstall"), lambda: service.gestionar_acpi("acpi-uninstall"), "", True)]
        return compat.component(tr("CPU power management · ACPI"), tr(status), tone, tr(
            "Upstream CPU idle and frequency tables. The original boot entry remains available for recovery."), actions)

    @staticmethod
    def _governor(ctx, tools, identifier, title, scope, detail):
        service = ctx.service
        found = (tools.get("supported_gpu_governors") or {}).get(identifier) or {}
        status, tone = ("Active", "ok") if found.get("active") else ("Installed", "accent") if found.get("detected") \
            else ("Not installed", "dim")
        if identifier.startswith("cyan") and tools.get("cyan_runtime_update_available"):
            status, tone = "Update available", "warn"

        def act(kind):
            plan = build_gpu_dependency_plan(tools, current_governor=tools.get("governor_backend"), action=kind,
                                             preference=identifier)

            def work():
                ctx.settings.save_local_config({"gpu_governor": "auto" if kind == "remove" else plan.preference})
                if kind == "remove":
                    return service.desinstalar_governor(plan.preference)
                return service.instalar_governor(plan.has_conflicts, plan.has_conflicts, plan.preference)

            return Action(tr("Uninstall" if kind == "remove" else "Install / update"), work, ", ".join(plan.conflicts),
                          bool(plan.conflicts) or kind == "remove")

        actions = [act("prepare")] + ([act("remove")] if found.get("detected") else [])
        return compat.component(tr(title), tr(status), tone, f"{tr(detail)} {tr(scope)}", actions)

    # -- Upscaling -----------------------------------------------------------------------------------

    def _upscaling(self, ctx, data, family):
        service = ctx.service
        tools = data.get("tools") or {}
        fsr4, helixsr = tools.get("fsr4") or {}, tools.get("helixsr") or {}
        ready = bool(helixsr.get("network_ready"))
        return [Panel(tr("Upscaling"), [
            self._upscaler(service.gestionar_fsr4_bc250, "BC-250 FSR4 V3", fsr4, tr(
                "Installs OptiScaler and the BC250 FSR4 DLL into the games you choose, with a backup of every file it "
                "replaces. Your driver and Proton stay as they are."), [
                    Action(tr("Open configuration"), lambda: service.gestionar_fsr4_bc250("launch"), confirm=False)]
                if fsr4.get("current") else []),
            self._upscaler(service.gestionar_helixsr, "HelixSR", helixsr, tr(
                "DLSS and FSR 4 networks on this GPU, put into each game by HelixSR's own installer."), [
                    *([] if ready else [Action(tr("Build network files"), lambda: service.gestionar_helixsr("network"))]),
                    Action(tr("Find FSR 3.1 games"), lambda: service.gestionar_helixsr("scan"), confirm=False),
                    Action(tr("Add game"), show=lambda ui: self._add_game(ui, service)),
                    *([Action(tr_format("Update all games ({count})", count=helixsr["outdated_games"]),
                              lambda: service.gestionar_helixsr("update_all"))] if helixsr.get("outdated_games") else [])]
                if helixsr.get("current") else [])]),
            *self._games(service, helixsr, fsr4, ready)]

    @staticmethod
    def _add_game(ui, service):
        folder = ui.ask_text(tr("Choose the game's folder"), "")
        if folder and folder.strip():
            guarded(ui, "HelixSR", lambda: service.gestionar_helixsr("add_folder:" + os.path.expanduser(folder.strip())))

    @staticmethod
    def _upscaler(run, title, state, detail, more):
        installed, newer = bool(state.get("installed")), state.get("newer") or {}
        status, tone = (("Update available", "warn") if newer and installed else ("Installed", "ok") if installed
                        else ("Not installed", "dim") if state.get("supported", True) else ("Unsupported", "dim"))

        def version(ui):
            names = [(r["tag"], r["version"] + ("  " + tr("Recommended") if r.get("default") else "")) for r in state.get("releases") or ()]
            picked = ui.choose(tr("Choose version"), names + [("", tr("Check for new releases"))])
            if picked is not None:
                guarded(ui, title, lambda: run(f"select:{picked}" if picked else "releases"))

        actions = list(more)
        if state.get("installer_available", True) and state.get("supported", True):
            tag = str(newer.get("tag") or "")
            actions.insert(0, Action(tr_format("Update to {version}", version=newer.get("version") or tag) if tag and installed
                                     else tr("Reinstall") if installed else tr("Install"),
                                     lambda: run(f"upgrade:{tag}" if tag and installed else "install")))
            if state.get("releases"):
                actions.append(Action(tr("Choose version"), show=version))
        if state.get("steam_launch_option") or state.get("launch_option"):
            actions.append(Action(tr("Steam launch option"), show=lambda ui: ui.show_text(
                tr("Steam launch option"), str(state.get("steam_launch_option") or state.get("launch_option")))))
        if installed:
            actions.append(Action(tr("Uninstall"), lambda: run("uninstall"), "", True))
        number_ = str(state.get("version") or "")
        return compat.component(title + (f" {number_}" if number_ and installed else ""), tr(status), tone, detail, actions)

    @staticmethod
    def _games(service, helixsr, fsr4, ready):
        """One row per game and tool, from the desktop's own table of what each offers."""
        bridge = helixsr.get("bridge_games") if str(helixsr.get("layout") or "") == "3" and helixsr.get("current") else None
        rows = game_matrix_rows(
            [dict(game) for game in helixsr.get("games") or ()], [dict(game) for game in fsr4.get("games") or ()] if fsr4.get("current") else [],
            helixsr_ready=ready, scaler_games=[dict(game) for game in helixsr.get("scaler_games") or ()],
            scaler_ready=bool(helixsr.get("scaler_supported")), fg_ready=bool(helixsr.get("fg_ready")),
            fsr4_installations=[dict(item) for item in fsr4.get("installations") or ()],
            fsr4_backups=[dict(item) for item in fsr4.get("backups") or ()],
            bridge_games=None if bridge is None else [dict(game) for game in bridge])
        shown = []
        for row in rows:
            for tool, title, run in (("helixsr", "HelixSR", service.gestionar_helixsr), ("fsr4", "FSR4", service.gestionar_fsr4_bc250)):
                cell = row.get(tool)
                if not cell:
                    continue
                text, tone, note, offered = cell
                shown.append(compat.component(
                    f"{row['name']} · {title}", tr(text or "Available"), compat.TONES.get(tone or "", "dim"),
                    "\n\n".join(filter(None, (tr(note) if note else "", str(row.get("folder") or "")))),
                    [Action(tr(label), lambda r=run, a=action.partition("_")[2]: r(a), "", label.startswith(("Remove", "Undo")))
                     for label, action, enabled in offered if enabled]))
        return [Panel(tr("Games"), shown, badge=str(len(shown)))] if shown else []

    # -- Memory & Swap -------------------------------------------------------------------------------

    def _memory(self, ctx, data, family):
        service, state = ctx.service, ctx.state(self.key)
        tools = data.get("tools") or {}
        runtime, setup = tools.get("memory_runtime") or {}, tools.get("system_setup") or {}
        memory, ttm_state = setup.get("memory") or {}, setup.get("ttm") or {}
        bazzite = family == "bazzite"
        presets = tuple(runtime.get("supported_ttm_gib_presets") or (8, 10, 12))
        keep = "current" if bazzite else "preserve"
        picks = state.setdefault("memory", {"policy": keep, "ttm": 0, "vram": 0, "target": ""})

        def gib(value):
            return f"{value / 2**30:.1f} GiB" if value else "--"

        def pick(key, title, options):
            def handler(ui_):
                chosen = ui_.choose(tr(title), options)
                if chosen is not None:
                    picks[key] = chosen
            return handler

        policies = [(key, tr(label)) for key, label in (MEMORY_POLICIES if bazzite else SWAP_POLICIES)]
        policy = picks["policy"] if picks["policy"] in dict(policies) else keep
        takeover = not bazzite and bool(memory.get("zram_takeover_available")) and policy in ("zswap-16", "zswap-32") \
            and policy not in (memory.get("policies") or ())
        reason = str((memory.get("policy_reasons") or {}).get(policy) or "")
        allowed = policy != keep and (bazzite or not memory or takeover or policy == "restore"
                                      or policy in (memory.get("policies") or ()) or policy in (memory.get("direct_switches") or ()))
        note = tr("This disables the ZRAM the distribution set up by default; ZSWAP takes over once you reboot. Nothing else "
                  "about that ZRAM configuration is touched, and it comes back if you restore this setting.") if takeover else \
            tr("A reboot may be required.") if bazzite else \
            tr("Optional system setup. Disk swap uses up to 32 GiB of storage; existing user swap is preserved. TTM is applied "
               "live when supported. ZRAM and deferred restoration require a reboot. Hardware testing is still required.")

        def apply_swap(ui_):
            target = picks["target"] if policy.endswith(("-16", "-32")) and not bazzite else ""
            work = (lambda: service.preparar_memoria_bazzite(policy, 0)) if bazzite else \
                (lambda: service.preparar_memoria(policy, 0, takeover_zram=takeover, target_mount=target))
            if ui_.confirm(f"{tr('Apply Swap')}: {dict(policies)[policy]}" + (f"\n{target}" if target else "") + f"\n\n{note}", danger=True):
                guarded(ui_, tr("Apply Swap"), work)

        def apply_ttm(ui_):
            value = int(picks["ttm"])
            text = tr("The limit is saved as a kernel boot argument, shared with BC250 Quick Access in Game Mode, and takes "
                      "effect at the next reboot.")
            if ui_.confirm(f"{tr('Apply TTM')}: {dict(ttm)[value]}\n\n{text}", danger=True):
                guarded(ui_, tr("Apply TTM"), lambda: service.preparar_memoria(keep, value))

        def apply_vram(ui_):
            if ui_.confirm(f"{tr('Apply VRAM')}: {dict(vram)[int(picks['vram'])]}", danger=True):
                guarded(ui_, tr("Apply VRAM"), lambda: service.preparar_vram(int(picks["vram"])))

        ttm = [(0, tr("Keep current TTM limit"))] + [(value, f"{value} GiB") for value in presets]
        if memory.get("ttm_restore_available") or ttm_state.get("managed") or picks["ttm"] == -1:
            ttm.append((-1, tr("Restore previous TTM limit")))
        vram = [(0, tr("Keep current VRAM size"))] + [(size, f"{size} MB") for size in vram_size_choices()]
        targets = [("", tr("Default (/var/lib)").replace("/var/lib", str(memory.get("default_swap_mount") or "/var/lib")))] + [
            (target, target) for target in sorted(memory.get("swap_targets") or ()) if target]
        location = [Choice(tr("Swapfile location"), pick("target", "Swapfile location", targets), dict(targets).get(picks["target"], picks["target"]) + " ›")] \
            if len(targets) > 1 and policy.endswith(("-16", "-32")) and not bazzite else []
        used, limit = runtime.get("ttm_limit_bytes"), runtime.get("physical_ram_bytes")
        return [Panel(tr("Memory & Swap"), [
                    Field(tr("Physical RAM"), gib(limit)),
                    Field("ZRAM", gib(runtime.get("zram_total_bytes")) if runtime.get("zram_active") else tr("Disabled"),
                          "ok" if runtime.get("zram_active") else "dim"),
                    Field(tr("Disk swap"), gib(runtime.get("backing_swap_total_bytes")) if runtime.get("backing_swap_active")
                          else tr("None"), "ok" if runtime.get("backing_swap_active") else "dim"),
                    Field("ZSWAP", tr("Active" if runtime.get("zswap_enabled") else "Disabled"), "ok" if runtime.get("zswap_enabled") else "dim"),
                    Field(tr("GPU memory limit (TTM)"), gib(used))]),
                Panel(tr("Swap"), [
                    Choice(tr("Swap"), pick("policy", "Swap", policies), dict(policies)[policy] + " ›", info=Info(note, blocked=tr(reason))),
                    *location, *([Note(tr(reason), "warn")] if reason and not allowed else []),
                    Buttons([Choice(tr("Apply Swap"), apply_swap, tone="primary", enabled=allowed)])]),
                Panel(tr("GPU memory limit (TTM)"), [
                    Choice(tr("TTM limit"), pick("ttm", "GPU memory limit (TTM)", ttm), dict(ttm)[picks["ttm"]] + " ›", info=Info(
                        tr("The limit is saved as a kernel boot argument, shared with BC250 Quick Access in Game Mode, and takes "
                           "effect at the next reboot."))),
                    Buttons([Choice(tr("Apply TTM"), apply_ttm, tone="primary", enabled=bool(picks["ttm"]))])]),
                Panel(tr("VRAM size (UMA_SIZE)"), [
                    Choice(tr("VRAM size"), pick("vram", "VRAM size (UMA_SIZE)", vram), dict(vram)[picks["vram"]] + " ›"),
                    Buttons([Choice(tr("Apply VRAM"), apply_vram, tone="primary", enabled=bool(picks["vram"]))])])]

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
        accessories = (data.get("tools") or {}).get("accessories") or {}
        case = [row for row in (compat.accessory(service, key, title, detail, accessories.get(key) or {})
                                for key, title, detail in compat.ACCESSORIES) if row is not None]
        panels = [Panel(tr("Audio and TV"), case[:2])] if case else []
        if case[2:]:
            panels.append(Panel(tr("Case accessories"), case[2:]))
        return [*[
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
            *panels,
            *[Panel(tr("External drivers"), [
                Field("AIC8800", tr("Detected; automatic installation remains disabled.") if detected
                      else tr("SteamOS-specific; Wi-Fi only. Never installed automatically."), "warn" if detected else "dim"),
                Note(tr("Prefer devices supported by in-kernel Linux drivers."), "dim"),
                Buttons([Choice(tr("View compatibility guide"), lambda ui_: ui_.show_text(
                    tr("View compatibility guide"), f"{tr('Prefer devices supported by in-kernel Linux drivers.')}\n\n{GUIDE_URL}"))])],
                subtitle=tr("Device-specific kernel modules are not generic driver packs."), badge=tr("Reference only"),
                badge_tone="warn")]]
