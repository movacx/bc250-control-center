"""Pure presentation policy for the GFX1013 compatibility card."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# Upstream boots the patched entry once after installing and keeps stock
# Fedora as the default, so an installed fix looked missing after the next
# restart. These say so and name the buttons that switch it on.
FEDORA_FIX_STOCK_BOOT_DETAIL = (
    "The fix is installed, but this boot used the stock entry: after installing, "
    "upstream starts the patched entry only once and keeps stock Fedora as the default. "
    "Press Boot with the fix and restart; once it works, press Make the fix the default."
)
FEDORA_FIX_ACTIVE_DETAIL = (
    "The fix is active on this boot. If games and the desktop work well, press Make the "
    "fix the default so later boots use it too. The stock entry stays in the boot menu "
    "for recovery."
)

# The patched RADV alone (radv_async_compute), as both GFX1013 cards show it:
# status, tone and a tr_format template for each radv_async_state() state.
RADV_ROUTE_COPY: dict[str, tuple[str, str, str]] = {
    "not-installed": (
        "Available", "blue",
        "Builds RADV {version} with the GFX1013 compute-queue patch and installs it beside "
        "the system Mesa. Kernel {kernel} needs no patched amdgpu: its amdgpu is the same "
        "one Bazzite's async-compute release runs on. Building takes 10-20 minutes.",
    ),
    "active": (
        "Active", "green",
        "This session uses the patched RADV: games get the compute (ACE) queue with no launch options. Performance › GPU › Async compute shows when a game really uses it.",
    ),
    "relogin-required": (
        "Log out to apply", "blue",
        "Installed and switched on. Log out and back in; sessions started after that use the patched RADV.",
    ),
    "switched-off": (
        "Switched off", "gray",
        "Installed but switched off: sessions use the system driver. One game can still use it with the launch option bc250cc-async-compute run %command%.",
    ),
    "deferred": (
        "Kernel-side fix in use", "orange",
        "The GFX1013 kernel-side fix is loaded on this boot and brings its own RADV. On this kernel it is not needed: remove it to use this one.",
    ),
    "invalid": (
        "Repair needed", "orange",
        "Some files of the patched RADV are missing. Build and install it again.",
    ),
}
RADV_ROUTE_OUTDATED = "A newer build (RADV {version}) is available: build and install again to update."
RADV_ROUTE_SECOND_FIX = (
    "The GFX1013 kernel-side fix is installed too; on kernel 7.2 or newer it is not needed, "
    "and one route is enough."
)


@dataclass(frozen=True)
class RadvRoutePresentation:
    status: str
    tone: str
    #: tr_format templates, filled from ``values``.
    detail: tuple[str, ...]
    values: Mapping[str, str]
    scope: str
    installed: bool
    enabled: bool
    #: Build and install instead of the on/off switch: nothing installed, a
    #: damaged install or an older build.
    build: bool
    #: Only a complete install can run the verification test.
    testable: bool
    #: Removes a kernel-side fix installed beside this route, or "" for none.
    remove_fix_action: str


def present_radv_route(
    radv: Mapping[str, object],
    *,
    source_installed: bool = False,
    dryhopped_installed: bool = False,
    fedora: bool = False,
) -> RadvRoutePresentation:
    """The patched-RADV route on a kernel 7.2+, for Arch-family systems and Fedora."""
    state = str(radv.get("state") or "not-installed")
    installed = bool(radv.get("installed"))
    outdated = bool(radv.get("outdated"))
    status, tone, text = RADV_ROUTE_COPY.get(state, ("Checking", "gray", ""))
    detail = [text] if text else []
    if outdated:
        detail.append(RADV_ROUTE_OUTDATED)
    if source_installed or dryhopped_installed:
        detail.append(RADV_ROUTE_SECOND_FIX)
    return RadvRoutePresentation(
        status=status,
        tone=tone,
        detail=tuple(detail),
        values={
            "version": str(radv.get("expected_version") or radv.get("version") or ""),
            "kernel": str(radv.get("kernel") or ""),
        },
        scope=(
            "Fedora · linux 7.2+ · no kernel module"
            if fedora
            else "Arch family · linux 7.2+ · no kernel module"
        ),
        installed=installed,
        enabled=bool(radv.get("enabled")),
        build=not installed or state == "invalid" or outdated,
        testable=installed and state != "invalid",
        remove_fix_action=(
            "gfx1013_source_uninstall"
            if source_installed
            else "gfx1013_fedora_uninstall"
            if dryhopped_installed
            else ""
        ),
    )


@dataclass(frozen=True)
class Gfx1013Presentation:
    status: str
    tone: str
    detail: tuple[str, ...]
    steamos_actions: bool
    fedora_actions: bool
    bazzite_actions: bool
    compatibility_action: str
    #: Fedora on kernel 7.2+: the patched RADV alone instead of DryhoppedIPA's
    #: installer, whose kernel half Fedora 44 never loads.
    radv_route: RadvRoutePresentation | None = None
    #: Fills the ``detail`` templates through tr_format.
    detail_values: Mapping[str, str] = field(default_factory=dict)


def _status(reason: str, **state: bool) -> tuple[str, str]:
    kernel = state["kernel_ready"]
    safe_radv = state["safe_radv"]
    if (
        state["legacy_radv"]
        or state["external_runtime_invalid"]
        or (reason == "steamos-dedicated-backend" and safe_radv and not kernel)
        or (reason == "steamos-dedicated-backend" and state["external_runtime_current"] and not kernel)
    ):
        return "Review required", "orange"
    if state["bazzite_invalid"]:
        return "Repair required", "orange"
    if state["bazzite_session_active"]:
        return "Async compute detected", "green"
    if state["bazzite_current"] and state["bazzite_enabled"]:
        return "Log out required", "blue"
    if state["bazzite_current"]:
        return "Installed", "green"
    if state["external_boot_active"]:
        return "Patched boot active", "green"
    if state["external_installed"]:
        return "Installed", "blue"
    if state["masta_async_compute_ready"]:
        return "Installed via MastaG", "green"
    if reason == "steamos-dedicated-backend":
        if kernel and state["external_fsr4_current"]:
            return "Async compute detected", "green"
        if kernel and state["external_runtime_current"]:
            return "Async compute detected", "green"
        if kernel and safe_radv:
            return "Async compute detected", "green"
        if kernel:
            return "Kernel half ready", "blue"
        return "SteamOS backend", "blue"
    if reason == "fedora-upstream-managed":
        return "Official upstream workflow", "blue"
    if reason == "bazzite-release-managed":
        return "Bazzite release available", "blue"
    if reason.startswith("bazzite-release-"):
        return "Blocked", "orange"
    return "Manual only", "gray"


def _detail(reason: str, **state: bool) -> tuple[str, ...]:
    kernel = state["kernel_ready"]
    safe_radv = state["safe_radv"]
    if state["legacy_radv"]:
        return ("A legacy SteamOS alternate RADV installation was detected. That older path can include mesh/task patches that current upstream disabled after unrecoverable GPU hangs. Control Center will not run or update it.",)
    if state["bazzite_invalid"]:
        return ("The Bazzite async-compute installation is incomplete or is not the reviewed version. Repair it before enabling the patched RADV driver.",)
    if state["bazzite_session_active"]:
        return ("The reviewed Bazzite 44 async-compute RADV driver is installed and active in this session. System Mesa remains unchanged.",)
    if state["bazzite_current"] and state["bazzite_enabled"]:
        return ("The reviewed Bazzite async-compute driver is installed and enabled. Log out and back in before games and the desktop use it.",)
    if state["bazzite_current"]:
        return ("The reviewed Bazzite async-compute driver is installed. If you notice no difference in a game, the global variable may not be active. Copy the launch option below for each game individually, or copy the always-on enable command and paste it into a terminal. You can use the built-in terminal by pressing F4.",)
    if reason == "steamos-dedicated-backend" and state["external_runtime_invalid"]:
        return ("Mesa/RADV is incomplete or changed. Repair or remove it before playing.",)
    if reason == "steamos-dedicated-backend" and state["external_runtime_current"] and not kernel:
        return ("An external SteamOS RADV runtime is present but the matching kernel repair is not active. Do not use it until the kernel half is active; an unmatched Mesa/RADV runtime can hang the GPU.",)
    if reason == "steamos-dedicated-backend" and safe_radv and not kernel:
        return ("A GFX1013 RADV path was detected, but the verified SteamOS kernel compute repair is not active. Do not use the patched RADV driver until the kernel half is active; upstream warns that Mesa without the kernel repair can hang the GPU.",)
    if state["external_boot_active"]:
        return (FEDORA_FIX_ACTIVE_DETAIL,)
    if state["external_installed"]:
        return (FEDORA_FIX_STOCK_BOOT_DETAIL,)
    if state["masta_async_compute_ready"]:
        return ("The GFX1013 async-compute fix is already installed and active through MastaG's matched BC-250 kernel and Mesa/RADV packages. No separate DryhoppedIPA installation is required. Continue to test stability per game; async compute can increase GPU load and voltage requirements.",)
    if reason == "steamos-dedicated-backend":
        # One short line per state: the two status chips below already name
        # each stage, and the buttons carry the order (1 · kernel, 2 · Mesa).
        detail = []
        if kernel and safe_radv:
            detail.append("Another GFX1013 RADV is installed. Review it before using this one.")
        elif kernel and state["external_runtime_current"]:
            detail.append("Kernel and Mesa/RADV verified. Async compute is ready.")
            if state["external_fsr4_current"]:
                detail.append("The optional per-game FSR4 profile is also intact. Keep its launch option scoped to the games you are testing.")
        elif kernel:
            detail.append("The kernel is ready. Install Mesa/RADV to enable async compute.")
        else:
            detail.append("Two steps: install the kernel and reboot, then install Mesa/RADV.")
        return tuple(detail)
    details = {
        "fedora-upstream-managed": "Control Center updates DryhoppedIPA's official main branch and invokes its combined kernel + Mesa/RADV workflow unchanged. Upstream performs the Fedora/kernel compatibility checks and keeps the stock boot entry as the recovery path.",
        "arch-family-manual-untested": "Upstream documents this Arch-family path as manual and untested. Control Center does not automate kernel/Mesa changes here.",
        "bazzite-release-managed": "The reviewed v0.2.4 release installs a separate RADV driver under /usr/local for Bazzite 44. It does not replace system Mesa or patch the kernel; activation takes effect after logging out and back in.",
        "bazzite-release-kernel-unsupported": "This Bazzite 44 system is detected, but the reviewed release requires kernel 7.2.0-ogc4.1 or newer. Installation stays blocked until a compatible OGC kernel is running.",
        "bazzite-release-version-unsupported": "The reviewed async-compute release supports Bazzite 44 only. Installation stays blocked on this Bazzite version.",
    }
    if reason == "bazzite-release-managed":
        return (
            details[reason],
            "Upstream enables this driver system-wide by default, including the desktop compositor. If the desktop does not return, use Ctrl+Alt+F3 to remove /etc/environment.d/95-bc250-async-compute.conf and reboot.",
        )
    return (details.get(reason, "Upstream provides manual patch guidance only for this distribution. Control Center does not automate the kernel/Mesa stack."),)


def present_gfx1013(
    state: Mapping[str, object], *, include_fsr4: bool = True
) -> Gfx1013Presentation:
    reason = str(state.get("reason_key") or "manual-patches-only")
    values = {
        "kernel_ready": bool(state.get("steamos_kernel_ready")),
        "safe_radv": bool(state.get("steamos_safe_radv_detected")),
        "legacy_radv": bool(state.get("legacy_steamos_radv_detected")),
        "external_runtime_invalid": (
            str(state.get("steamos_external_radv_state") or "") == "invalid"
            or (
                include_fsr4
                and str(state.get("steamos_external_fsr4_state") or "") == "invalid"
            )
        ),
        "external_runtime_current": bool(state.get("steamos_external_radv_current")),
        "external_fsr4_current": include_fsr4
        and bool(state.get("steamos_external_fsr4_current")),
        "external_installed": bool(state.get("dryhopped_installed")),
        "external_boot_active": bool(state.get("dryhopped_boot_active")),
        "masta_async_compute_ready": bool(state.get("masta_async_compute_ready")),
        "bazzite_current": bool(state.get("bazzite_async_current")),
        "bazzite_enabled": bool(state.get("bazzite_async_enabled")),
        "bazzite_session_active": bool(state.get("bazzite_async_session_active")),
        "bazzite_invalid": bool(state.get("bazzite_async_installed"))
        and not bool(state.get("bazzite_async_current")),
    }
    radv = state.get("radv_async")
    radv_route = None
    if reason == "fedora-upstream-managed" and isinstance(radv, Mapping) and radv.get("supported"):
        radv_route = present_radv_route(
            radv,
            dryhopped_installed=values["external_installed"],
            fedora=True,
        )
    if radv_route is not None:
        status, tone, detail = radv_route.status, radv_route.tone, radv_route.detail
    else:
        status, tone = _status(reason, **values)
        detail = _detail(reason, **values)
    return Gfx1013Presentation(
        status=status,
        tone=tone,
        detail=detail,
        steamos_actions=reason == "steamos-dedicated-backend",
        fedora_actions=reason == "fedora-upstream-managed" and radv_route is None,
        bazzite_actions=reason.startswith("bazzite-release-"),
        compatibility_action=("1 · Repair kernel" if values["kernel_ready"] else "1 · Install kernel"),
        radv_route=radv_route,
        detail_values=dict(radv_route.values) if radv_route is not None else {},
    )
