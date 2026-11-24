"""Kernel and graphics: the one route each distribution, kernel and install state has, as the desktop offers it."""

from __future__ import annotations

from typing import Any

from bc250cc.application.preparation.distribution_rows import distribution_group
from bc250cc.application.system.cachyos_kernel import DEPENDENCY_NOTE
from frontends.desktop.core import compatibility_dialogs as dialogs
from frontends.desktop.core.feature_visibility import GFX1013_FSR4_UI_ENABLED
from frontends.desktop.core.gfx1013_presenter import (
    RADV_ROUTE_SECOND_FIX,
    present_gfx1013,
    present_radv_route,
)

from ..content import Choice
from ..i18n import tr, tr_format
from .compat import TONES, Action, component

SOURCE_STATUS = {
    "not-installed": ("Source build available", "dim"), "active": ("Active", "ok"), "reboot-required": ("Restart required", "warn"),
    "rebuild-needed": ("Rebuild needed", "warn"), "switched-off": ("Switched off", "dim"),
    "fell-back": ("Switched off after a failed boot", "warn"), "blocked-early-load": ("Loaded too early", "warn"),
}


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _asked(label: str, work, dialog: tuple) -> Action:
    """An action whose question is the desktop dialog's own text."""
    return Action(tr(label), work, tr(dialog[1]), dialog[3] != "blue")


def gfx1013(service, tools: dict, family: str) -> Choice | None:
    """The GFX1013 row, or None where nothing is on offer."""
    state = _mapping(tools.get("gfx1013_compute"))
    group = distribution_group(family)
    radv, source, upgrade = (_mapping(state.get(key)) for key in ("radv_async", "source", "kernel_upgrade"))
    reason, masta_ready = str(state.get("reason_key") or ""), bool(state.get("masta_async_compute_ready"))
    if group == "steamos":
        return None  # the toolkit's own rows
    shown = present_gfx1013(state, include_fsr4=GFX1013_FSR4_UI_ENABLED)
    status, tone = shown.status, shown.tone
    detail = " ".join(tr_format(part, **shown.detail_values) for part in shown.detail)
    actions: list[Action] = []
    if reason == "fedora-upstream-managed" and shown.radv_route is None:
        installed, active = bool(state.get("dryhopped_installed")), bool(state.get("dryhopped_boot_active"))

        def fedora(key):
            return lambda: service.gestionar_gfx1013_fedora(key)

        if installed:
            actions.append(Action(tr("Make the fix the default" if active else "Boot with the fix"),
                                  fedora("activate" if active else "boot-patched"), detail, True))
        actions.append(Action(tr("Install / update"), fedora("install"), detail, True))
        if installed:
            actions.append(Action(tr("Uninstall"), fedora("uninstall"), detail, True))
    elif reason.startswith("bazzite-release-"):
        installed = bool(state.get("bazzite_async_installed"))

        def bazzite(key):
            return lambda: service.gestionar_gfx1013_bazzite(key)

        if state.get("direct_installer_allowed"):
            actions.append(Action(tr("Repair / update" if installed else "Install / update"), bazzite("install"), detail, True))
        if installed:
            actions += [Action(tr("Uninstall"), bazzite("uninstall"), detail, True),
                        Action(tr("Check status"), bazzite("status"), confirm=False)]
    elif radv.get("supported") and not masta_ready:
        fedora_route = reason == "fedora-upstream-managed"
        route = present_radv_route(radv, source_installed=bool(source.get("installed")),
                                   dryhopped_installed=fedora_route and bool(state.get("dryhopped_installed")), fedora=fedora_route)
        status, tone = route.status, route.tone
        detail = " ".join(tr_format(part, **route.values) for part in route.detail)

        def radv_action(key):
            return lambda: service.gestionar_radv_async(key)

        if route.build:
            actions.append(_asked("Build and install", radv_action("install"), dialogs.RADV_ASYNC["install"]))
        else:
            key = "disable" if route.enabled else "enable"
            actions.append(_asked("Switch off" if route.enabled else "Switch on", radv_action(key), dialogs.RADV_ASYNC[key]))
        if route.testable:
            actions.append(Action(tr("Test async compute"), radv_action("test"), confirm=False))
        if route.installed:
            actions.append(_asked("Remove", radv_action("uninstall"), dialogs.RADV_ASYNC["uninstall"]))
        if route.remove_fix_action:
            remove = service.gestionar_gfx1013_source if "source" in route.remove_fix_action else service.gestionar_gfx1013_fedora
            actions.append(Action(tr("Remove the kernel-side fix"), lambda: remove("uninstall"), tr(RADV_ROUTE_SECOND_FIX), True))
    elif source.get("supported") and not masta_ready:
        kind, installed = str(source.get("state") or "not-installed"), bool(source.get("installed"))
        status, tone = SOURCE_STATUS.get(kind, ("Checking", "dim"))
        detail = tr(dialogs.GFX1013_SOURCE["install"][1])

        def build(key):
            return lambda: service.gestionar_gfx1013_source(key)

        key, label = (("install", "Build and install the fix") if not installed else ("rebuild", "Rebuild for this kernel")
                      if kind == "rebuild-needed" else ("disable", "Switch off") if source.get("enabled") else ("enable", "Switch on"))
        actions.append(_asked(label, build(key), dialogs.GFX1013_SOURCE[key]))
        if installed:
            actions.append(_asked("Remove the fix", build("uninstall"), dialogs.GFX1013_SOURCE["uninstall"]))
    elif upgrade.get("offered") and source.get("hide_offer"):
        restart = str(upgrade.get("state") or "") == "reboot-required"
        status, tone = ("Restart required", "warn") if restart else ("Newer kernel and Mesa needed", "warn")
        detail = tr(dialogs.DEBIAN_KERNEL if upgrade.get("install_kernel", True) else dialogs.DEBIAN_MESA)
        if not restart:
            actions.append(Action(tr("Install from backports"), lambda: service.gestionar_kernel_debian("install"), detail, True))
    elif group == "arch" or source.get("hide_offer"):
        return None  # the matched stack's own row, or a kernel too old for any route
    return component(tr("GFX1013 async compute"), tr(status), TONES.get(tone, tone if tone in ("ok", "warn", "bad") else "dim"), detail, actions)


def mesa(service, tools: dict) -> Choice | None:
    state = _mapping(tools.get("mesa_desktop"))
    if not state.get("offered"):
        return None
    route, actions = str(state.get("route") or ""), []
    if route in ("ppa", "backports"):
        text = dialogs.MESA_PPA if route == "ppa" else dialogs.DEBIAN_MESA
        work = (lambda: service.gestionar_kernel_debian("install")) if str(state.get("action")) == "debian_kernel_install" else \
            (lambda: service.gestionar_mesa_desktop("install"))
        actions.append(Action(tr("Update Mesa" if route == "ppa" else "Install from backports"), work, tr(text), True))
    detail = ("The Mesa of this system does not draw the desktop on the BC-250 GPU, so windows are drawn by the CPU and feel slow, "
              "although games using Vulkan already run on the GPU. Fedora 44 ships Mesa 26.1 or newer: upgrade to it with GNOME "
              "Software, KDE Discover or dnf system-upgrade.") if route == "release" else \
        dialogs.DEBIAN_MESA if route == "backports" else dialogs.MESA_PPA
    return component("Mesa", tr("Mesa too old for the desktop"), "warn", tr(detail), actions)


#: MastaG's packages: (key, title, [(action, label, label once installed)], removal action).
def mastag(service, tools: dict, family: str) -> list[Choice]:
    """MastaG's matched BC-250 kernel, Mesa, Proton and extras (Arch Linux and CachyOS)."""
    stack = _mapping(tools.get("masta_bc250_stack"))
    if distribution_group(family) != "arch":
        return []
    if not stack.get("supported", tools.get("masta_bc250_stack_supported")):
        return [component(tr("Install BC-250 kernel and Mesa for Arch/CachyOS"), tr("Not compatible"), "dim",
                          tr("Available only on plain Arch Linux or CachyOS"), [])]
    proton, extras, variants = (_mapping(stack.get(key)) for key in ("proton_installed", "extras_installed", "variants_installed"))

    def add(label: str, key: str, text: str = "") -> Action:
        return Action(tr(label), lambda: service.preparar_cachyos_bc250(key), tr(dialogs.MASTAG_TRUST) + (" " + tr(text) if text else ""), True)

    def drop(label: str, key: str, text: str) -> Action:
        return Action(tr(label), lambda: service.preparar_cachyos_bc250(key), tr(text), True)

    kernel, mesa_, active = bool(stack.get("kernel_installed")), bool(stack.get("mesa_installed")), bool(stack.get("kernel_active"))
    pahole = _mapping(stack.get("pahole_dependency"))
    status, tone = (("Full stack installed", "ok") if kernel and mesa_ and active else ("Installed · reboot required", "warn")
                    if kernel and mesa_ else ("Partially installed", "warn") if kernel or mesa_ else ("Available", "dim"))
    main = [*([Action(tr("Prepare dependencies"), lambda: service.preparar_cachyos_bc250("pahole"), tr(DEPENDENCY_NOTE), True)]
              if pahole.get("requirement") and not pahole.get("ready") else []),
            add("Update / repair full stack" if kernel and mesa_ else "Install kernel + Mesa", "full"),
            add("Update / repair kernel" if kernel else "Install kernel", "kernel"),
            add("Update / repair Mesa" if mesa_ else "Install Mesa", "mesa"),
            add("Update / repair RC kernel" if variants.get("rc") else "Install RC kernel", "kernel-rc"),
            add("Update / repair BORE kernel" if variants.get("bore") else "Install BORE kernel", "kernel-bore"),
            add("Update / repair the BC-250 bundle" if stack.get("meta_installed") else "Install the full BC-250 bundle", "meta",
                dialogs.MASTAG_BUNDLE)]
    names = {"native": "Proton BC-250", "ge": "Proton-GE BC-250", "slr": "Proton SLR BC-250"}
    have = [key for key in names if proton.get(key)]
    protons = [add("Update / repair Proton BC-250" if proton.get("native") else "Install Proton BC-250 (recommended)", "proton-native"),
               add("Update / repair Proton-GE BC-250" if proton.get("ge") else "Install Proton-GE BC-250", "proton-ge"),
               *[Action(f"{tr('Remove')} {names[key]}", lambda k=key: service.preparar_cachyos_bc250(f"remove-proton-{k}"),
                        tr("This removes the Proton package from your system. Games that used it will ask for another Proton."), True)
                 for key in have]]
    own_ac3 = str(_mapping(_mapping(tools.get("accessories")).get("hdmi_ac3")).get("state") or "") in {"installed", "active", "reboot-required"}
    more = []
    for key, install, remove in (("fixes", "Install BC-250 fixes", "Remove BC-250 fixes"),
                                 ("paccache", "Install pacman cache cleanup", "Remove pacman cache cleanup"),
                                 ("ch7218", "Install UGREEN adapter firmware files", "Remove UGREEN adapter firmware files"),
                                 ("dual-audio", "Install dual audio output (Dolby 5.1)", "Remove dual audio output")):
        if extras.get(key):
            more.append(drop(remove, f"remove-extra-{key}", "This removes the package from your system."))
        elif not (key == "dual-audio" and own_ac3):  # two 5.1 outputs get in each other's way
            more.append(add(install, f"extra-{key}"))
    return [component(tr("Install BC-250 kernel and Mesa for Arch/CachyOS"), tr(status), tone, tr(dialogs.MASTAG_TRUST), main),
            component("Proton BC-250", ", ".join(names[key] for key in have) or tr("Not installed"), "ok" if have else "dim",
                      tr("Kernel and Mesa are not changed"), protons),
            component("BC-250 · MastaG", "", "dim", tr("Kernel and Mesa are not changed"), more)]
