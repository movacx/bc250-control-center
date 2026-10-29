"""Additional settings: the preparation tabs of the desktop's Dashboard.

Every entry calls the same service method as its desktop card, which checks
the distribution itself and raises when the action does not apply. The list
here only decides what is worth offering on this system.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..content import Choice, Field, Gap, Heading, Note
from ..i18n import tr
from .base import Page, guarded, os_family

ALL = None
IMMUTABLE_RPM = ("bazzite",)

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
STATUS_INSTALL = (("status", "Status"), ("install", "Install"), ("uninstall", "Uninstall"))


@dataclass(frozen=True)
class Entry:
    label: str
    method: str
    actions: tuple[tuple[str, str], ...] = ()
    families: tuple[str, ...] | None = ALL
    danger: bool = False
    note: str = ""


def entry(label, method, actions=(), families=ALL, danger=False, note=""):
    return Entry(label, method, tuple(actions), families, danger, note)


TABS = {
    "compatibility": (
        entry("Simultaneous multithreading (SMT)", "gestionar_smt_bazzite",
              (("status", "Status"), ("disable", "Disable"), ("restore", "Restore")), ("bazzite",), True),
        entry("CPU security mitigations", "gestionar_mitigaciones_bazzite",
              (("status", "Status"), ("disable", "Disable"), ("restore", "Restore")), ("bazzite",), True),
        entry("Kernel boot messages", "gestionar_mensajes_arranque_bazzite",
              (("status", "Status"), ("hide", "Hide"), ("restore", "Restore")), ("bazzite",)),
        entry("GFX1013 fix", "gestionar_gfx1013_bazzite", STATUS_INSTALL, ("bazzite",)),
        entry("GFX1013 fix", "gestionar_gfx1013_fedora",
              STATUS_INSTALL + (("boot-patched", "boot-patched"), ("activate", "activate")), ("fedora",)),
        entry("Build and install the GFX1013 fix", "gestionar_gfx1013_source",
              STATUS_INSTALL + (("rebuild", "Rebuild"), ("enable", "Enable"), ("disable", "Disable")),
              ("arch", "cachyos", "manjaro", "ubuntu", "debian")),
        entry("Build and install async compute", "gestionar_radv_async",
              STATUS_INSTALL + (("enable", "Enable"), ("disable", "Disable"), ("test", "Test")),
              ("bazzite", "fedora", "arch", "cachyos", "manjaro", "ubuntu", "debian")),
        entry("Eight-core GPU telemetry", "gestionar_acpi",
              (("telemetry-fix", "Install"), ("telemetry-restore", "Restore"))),
        entry("BC250-Telemetry service", "gestionar_apu_telemetry", STATUS_INSTALL),
        entry("SteamOS read-only mode", "gestionar_solo_lectura_steamos",
              (("status", "Status"), ("disable", "Disable"), ("enable", "Enable")), ("steamos",), True),
        entry("Graphics", "gestionar_graficos_steamos",
              STATUS_INSTALL + (("install-fsr4", "install-fsr4"), ("uninstall-fsr4", "uninstall-fsr4")), ("steamos",)),
        entry("Check SteamOS compatibility", "preparar_compatibilidad_steamos", (), ("steamos",)),
        entry("BC250 SteamOS diagnostics", "diagnostico_steamos", (), ("steamos",)),
        entry("Newer kernel and Mesa for the BC-250", "gestionar_kernel_debian", (("install", "Install"),), ("debian",)),
        entry("Mesa", "gestionar_mesa_desktop", (("install", "Install"),), ("ubuntu",)),
        entry("CachyOS BC-250 kernel", "preparar_kernel_cachyos_bc250", (), ("cachyos",)),
        entry("Install BC-250 kernel and Mesa for Arch/CachyOS", "preparar_cachyos_bc250",
              (("full", "Prepare everything"), ("kernel", "Kernel"), ("mesa", "Mesa")), ("cachyos",)),
    ),
    "memory": (),  # built by hand: it needs the live memory snapshot
    "decky": (
        entry("Install Decky + Quick Access (Beta)", "preparar_quick_access_steamos", (), ("steamos", "bazzite", "cachyos")),
        entry("Prepare the VRAM reader", "comando_preparar_gddr6_memory_temp", (), ALL),
    ),
    "drivers": (
        entry("Connectivity support", "install_driver_support", (), ALL),
    ),
    "upscaling": (
        entry("BC-250 FSR4 V3", "gestionar_fsr4_bc250", (("install", "Install"), ("uninstall", "Uninstall")), ALL),
        entry("HelixSR", "gestionar_helixsr", (("install", "Install"), ("uninstall", "Uninstall"), ("update_all", "update_all")), ALL),
        entry("Hardware video · VA-API", "gestionar_vaapi",
              (("install", "Install"), ("install32", "install32"), ("test", "Test"), ("uninstall", "Uninstall")), ALL),
    ),
}

TAB_TITLES = (
    ("compatibility", "Compatibility"),
    ("memory", "Memory & Swap"),
    ("decky", "Decky"),
    ("drivers", "Drivers"),
    ("upscaling", "Upscaling"),
)

# install_driver_support takes a component, not an action.
DRIVER_COMPONENTS = (("connectivity", "Connectivity support"), ("printing", "Printing"))


def run_entry(ctx, ui, item: Entry) -> None:
    service = ctx.service
    method: Callable = getattr(service, item.method)
    argument = None
    if item.actions:
        argument = ui.choose(tr(item.label), [(key, label if label == key else tr(label)) for key, label in item.actions])
        if argument is None:
            return
    elif item.method == "preparar_quick_access_steamos":
        method = lambda: service.preparar_quick_access_steamos(install_decky=True)  # noqa: E731
    elif item.method == "install_driver_support":
        argument = ui.choose(tr(item.label), [(key, tr(label)) for key, label in DRIVER_COMPONENTS])
        if argument is None:
            return
    if not ui.confirm(f"{tr(item.label)}" + (f": {argument}" if argument else ""),
                      danger=item.danger and argument not in ("status",)):
        return
    guarded(ui, tr(item.label), (lambda: method(argument)) if argument else method)


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
        tab = tab or "compatibility"
        family, name = os_family(ctx)
        out = [Heading(tr(dict(TAB_TITLES).get(tab, tab))), Field(tr("System"), name)]
        if tab == "memory":
            out += self._memory(ctx)
        else:
            shown = [item for item in TABS.get(tab, ()) if item.families is None or family in item.families]
            if not shown:
                out.append(Note(tr("Not available"), "dim"))
            for item in shown:  # "›": Enter opens the entry's actions
                out.append(Choice(tr(item.label) + (" ›" if item.actions else ""),
                                  lambda ui_, item=item: run_entry(ctx, ui_, item), tone="warn" if item.danger else ""))
        return out

    def _memory(self, ctx):
        service = ctx.service
        memory = (ctx.metrics or {}).get("memory") or {}
        presets = tuple(memory.get("supported_ttm_gib_presets") or (8, 10, 12))
        out = [Field("RAM", f"{memory.get('usage_percent', '--')} %"),
               Field("Swap", f"{memory.get('swap_percent', '--')} %"),
               Field("ZRAM", tr("Yes") if memory.get("zram_active") else tr("No")),
               Field(tr("GPU memory limit (TTM)"), f"{(memory.get('ttm_limit_bytes') or 0) / 2**30:.1f} GiB"),
               Gap(), Heading(tr("Actions"))]

        def policy(ui_):
            chosen = ui_.choose(tr("Memory & Swap"), [(key, tr(label)) for key, label in MEMORY_POLICIES])
            if chosen is None:
                return
            ttm = ui_.choose(tr("GPU memory limit (TTM)"),
                             [(0, tr("Unchanged"))] + [(value, f"{value} GiB") for value in presets])
            if ttm is None or not ui_.confirm(tr("Memory & Swap"), danger=True):
                return
            guarded(ui_, tr("Memory & Swap"), lambda: service.preparar_memoria(chosen, int(ttm)))

        def vram(ui_):
            size = ui_.ask_int(tr("VRAM size (UMA_SIZE)") + " (MB)", 256, 12288, 512)
            if size is not None and ui_.confirm(tr("VRAM size (UMA_SIZE)"), danger=True):
                guarded(ui_, tr("VRAM size (UMA_SIZE)"), lambda: service.preparar_vram(size))

        out += [Choice(tr("Memory & Swap"), policy, tone="warn"), Choice(tr("VRAM size (UMA_SIZE)"), vram, tone="warn")]
        return out
