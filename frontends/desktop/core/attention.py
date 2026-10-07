"""What the tools Control Center installed need from the owner right now.

Read from the same inventory the Prepare card shows, and only from states
that are certain: a helper whose bytes differ from this version, a base
component the inventory reports missing, a driver its own probe calls
damaged, Bazzite packages layered by Prepare dependencies that wait for the
next boot. Anything that depends on how the owner chose to boot or log in
(a kernel installed but not running, a session not yet reloaded) is left
to the cards, because it can be a deliberate choice.

The dashboard shows each notice once per session, as a toast.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..i18n import tr, tr_format

HELPERS_TITLE = "Control Center's system helpers are out of date"
HELPERS_MESSAGE = (
    "They belong to another version, so some actions can fail. Reinstall this "
    "version from {path}."
)
HELPERS_MESSAGE_CHECKOUT = (
    "They belong to another version, so some actions can fail. Run "
    "scripts/install-local.sh from this checkout."
)
HELPERS_MESSAGE_PACKAGE = (
    "They belong to the installed package {package}, so some actions can "
    "fail. Update or reinstall that package with your package manager."
)
REBOOT_TITLE = "Restart the computer to apply the changes"
REBOOT_MESSAGE = (
    "Some setup is still pending. After restarting, prepare the dependencies "
    "again: open {section} at the bottom of the Dashboard and press {button}."
)
RUNTIME_TITLE = "Base dependencies are missing"
RUNTIME_MESSAGE = "Open {section} at the bottom of the Dashboard and press {button}."
CU_MISSING_TITLE = "The 40CU tools are missing"
CU_MISSING_MESSAGE = (
    "Not prepared: {items}. The Compute Units page cannot work without them. "
    "Open {section} at the bottom of the Dashboard, tick them and press {button}."
)
CU_MISSING_MESSAGE_STEAMOS = (
    "Not prepared: {items}. SteamOS needs its own 40CU manager and UMR "
    "database; a standard one is ignored. Open {section} at the bottom of the "
    "Dashboard, tick them and press {button}."
)
CU_REPAIR_TITLE = "The 40CU tools need a repair"
CU_REPAIR_MESSAGE = (
    "They are installed, but part of them ({items}) is missing or was "
    "changed, often by another kit. Open {section} at the bottom of the "
    "Dashboard, tick it and press {button} to repair it."
)
BAZZITE_TITLE = "Async compute needs a repair"
BAZZITE_MESSAGE = (
    "The async compute driver is damaged or from another version. Press "
    "{button} in {section}."
)
STEAMOS_RADV_TITLE = "Mesa RADV needs a repair"
STEAMOS_RADV_MESSAGE = (
    "The BC250 Mesa RADV driver is damaged or from another version. Repair it "
    "in {section}."
)
FSR4_REPAIR_TITLE = "The FSR4 client needs a repair"
FSR4_REPAIR_MESSAGE = (
    "Its folder is incomplete or was changed. Press {button} in {section}; "
    "your game backups are kept."
)
FSR4_UPDATE_TITLE = "An FSR4 client update is ready"
FSR4_UPDATE_MESSAGE = "Press {button} in {section}. Your games and backups are kept."


def _where(*labels: str) -> str:
    """A path through the interface, in the words the interface uses."""
    return " › ".join(tr(label) for label in labels)


def _say(template: str, **labels: str) -> str:
    return tr_format(template, **labels)


@dataclass(frozen=True)
class Attention:
    key: str
    #: A catalogue key; the toast translates it.
    title: str
    #: Already translated, with the interface's own labels filled in.
    message: str
    tone: str = "orange"


def _mapping(value: object) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _compute_unit_tools(tools: Mapping, *, base_ready: bool) -> list[Attention]:
    """UMR and the 40CU manager: the Compute Units page cannot work without them.

    Ordinary distributions and SteamOS use different backends, so the two
    are told apart only in the wording; the fix is the same card. Nothing is
    said while the base dependencies are missing, because preparing those
    comes first and the runtime notice already asks for it.
    """
    components = _mapping(tools.get("prepare_components"))
    umr = _mapping(components.get("umr"))
    manager = _mapping(components.get("cu_manager"))
    if not base_ready or not umr or not manager:
        return []
    steamos = bool(tools.get("is_steamos"))
    section = tr("Prepare BC250 system")
    button = tr("Prepare selected")
    umr_label, manager_label = tr("UMR database"), tr("40CU manager")

    missing = []
    if umr.get("available", True) and umr.get("installed") is False:
        missing.append(umr_label)
    if manager.get("available", True) and manager.get("installed") is False:
        missing.append(manager_label)
    if missing:
        template = CU_MISSING_MESSAGE_STEAMOS if steamos else CU_MISSING_MESSAGE
        return [Attention("cu-tools-missing", CU_MISSING_TITLE, _say(
            template, items=", ".join(missing), section=section, button=button,
        ))]

    damaged = []
    if steamos and tools.get("cu_steamos_umr_database_ready") is False:
        damaged.append(umr_label)
    if manager.get("installed") is True and tools.get("cu_privileged_backend_ready") is False:
        damaged.append(manager_label)
    if damaged:
        return [Attention("cu-tools-repair", CU_REPAIR_TITLE, _say(
            CU_REPAIR_MESSAGE, items=", ".join(damaged), section=section, button=button,
        ))]
    return []


def attention_items(tools: Mapping) -> tuple[Attention, ...]:
    """The notices that apply to ``tools`` (the preparation inventory)."""
    tools = _mapping(tools)
    if not tools:
        # The inventory has not been read yet: no answer is not a problem.
        return ()
    items: list[Attention] = []

    compatibility = _where("Prepare BC250 system", "Compatibility")
    upscaling = _where("Additional settings", "Upscaling")
    helpers = _mapping(tools.get("privileged_install"))
    if helpers.get("state") == "outdated":
        # A package still owns these files: a local install would overwrite
        # what the package manager tracks, so its fix comes first.
        package = str(helpers.get("package") or "")
        if package:
            message = _say(HELPERS_MESSAGE_PACKAGE, package=package)
        elif helpers.get("checkout"):
            message = tr(HELPERS_MESSAGE_CHECKOUT)
        else:
            message = _say(HELPERS_MESSAGE, path=_where("Settings", "About", "Update application"))
        items.append(Attention("helpers-outdated", HELPERS_TITLE, message))

    if _mapping(tools.get("bazzite_reboot_pending")).get("pending"):
        # Bazzite layered the packages into the next deployment. Whatever
        # reads as missing now arrives with the reboot, and the second
        # preparation after it finishes the rest; asking to prepare the
        # missing parts before that reboot would only repeat the first run.
        items.append(Attention("bazzite-reboot-pending", REBOOT_TITLE, _say(
            REBOOT_MESSAGE, section=tr("Prepare BC250 system"), button=tr("Prepare selected"),
        )))
    else:
        runtime = _mapping(_mapping(tools.get("prepare_components")).get("runtime"))
        if runtime and runtime.get("available", True) and runtime.get("installed") is False:
            items.append(Attention("runtime-missing", RUNTIME_TITLE, _say(
                RUNTIME_MESSAGE, section=tr("Prepare BC250 system"), button=tr("Prepare selected"),
            )))

        items.extend(_compute_unit_tools(tools, base_ready=not (
            runtime and runtime.get("available", True) and runtime.get("installed") is False
        )))

    gfx = _mapping(tools.get("gfx1013_compute"))
    reason = str(gfx.get("reason_key") or "")
    if (
        reason.startswith("bazzite-release-")
        and gfx.get("bazzite_async_state") == "invalid"
        # The repair button is disabled on a kernel the release does not
        # support; the card itself explains that case.
        and gfx.get("direct_installer_allowed")
    ):
        items.append(Attention("bazzite-async-invalid", BAZZITE_TITLE, _say(
            BAZZITE_MESSAGE, button=tr("Repair / update"), section=compatibility,
        )))
    if reason == "steamos-dedicated-backend" and gfx.get("steamos_external_radv_state") == "invalid":
        items.append(Attention("steamos-radv-invalid", STEAMOS_RADV_TITLE, _say(
            STEAMOS_RADV_MESSAGE, section=compatibility,
        )))

    fsr4 = _mapping(tools.get("fsr4"))
    if fsr4.get("installer_available"):
        if fsr4.get("state") == "invalid":
            items.append(Attention("fsr4-invalid", FSR4_REPAIR_TITLE, _say(
                FSR4_REPAIR_MESSAGE, button=tr("Repair FSR4 client"), section=upscaling,
            )))
        elif fsr4.get("state") == "update-available":
            items.append(Attention("fsr4-update", FSR4_UPDATE_TITLE, _say(
                FSR4_UPDATE_MESSAGE, button=tr("Update FSR4 client"), section=upscaling,
            ), "blue"))
    return tuple(items)
