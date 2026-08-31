"""Pure presentation policy for the GFX1013 compatibility card."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Gfx1013Presentation:
    status: str
    tone: str
    detail: tuple[str, ...]
    steamos_actions: bool
    fedora_actions: bool
    bazzite_actions: bool
    compatibility_action: str


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
        return "External install", "blue"
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
        return ("The reviewed Bazzite async-compute driver is installed but not enabled system-wide. System Mesa remains unchanged.",)
    if reason == "steamos-dedicated-backend" and state["external_runtime_invalid"]:
        return ("The SteamOS RADV/FSR4 runtime is incomplete or has changed. Use the reviewed repair or remove action before enabling it for games.",)
    if reason == "steamos-dedicated-backend" and state["external_runtime_current"] and not kernel:
        return ("An external SteamOS RADV runtime is present but the matching kernel repair is not active. Do not use it until the kernel half is active; an unmatched Mesa/RADV runtime can hang the GPU.",)
    if reason == "steamos-dedicated-backend" and safe_radv and not kernel:
        return ("A GFX1013 RADV path was detected, but the verified SteamOS kernel compute repair is not active. Do not use the patched RADV driver until the kernel half is active; upstream warns that Mesa without the kernel repair can hang the GPU.",)
    if state["external_boot_active"]:
        return ("An external DryhoppedIPA installation is active on this boot. Control Center will not modify its boot entry, initramfs, amdgpu module or Mesa files.",)
    if state["external_installed"]:
        return ("An external DryhoppedIPA installation was detected, but this boot is not using its patched entry. Boot selection and rollback remain managed by the upstream installer.",)
    if state["masta_async_compute_ready"]:
        return ("The GFX1013 async-compute fix is already installed and active through MastaG's matched BC-250 kernel and Mesa/RADV packages. No separate DryhoppedIPA installation is required. Continue to test stability per game; async compute can increase GPU load and voltage requirements.",)
    if reason == "steamos-dedicated-backend":
        detail = ["SteamOS uses the reviewed BC-250 toolkit in two ordered stages: matching AMDGPU first, then the matching async-compute Mesa/RADV runtime. The unsafe legacy mesh/task series is never installed."]
        if kernel and safe_radv:
            detail.append("The verified SteamOS kernel repair and another GFX1013 RADV path were both detected. Review that external path before using Control Center's managed runtime.")
        elif kernel and state["external_runtime_current"]:
            detail.append("The verified SteamOS AMDGPU and Mesa/RADV stages are ready.")
            if state["external_fsr4_current"]:
                detail.append("The optional per-game FSR4 profile is also intact. Keep its launch option scoped to the games you are testing.")
        elif kernel:
            detail.append("The SteamOS kernel stage is active. Install the matched Mesa/RADV stage to complete GFX1013 async compute.")
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


def present_gfx1013(state: Mapping[str, object]) -> Gfx1013Presentation:
    reason = str(state.get("reason_key") or "manual-patches-only")
    values = {
        "kernel_ready": bool(state.get("steamos_kernel_ready")),
        "safe_radv": bool(state.get("steamos_safe_radv_detected")),
        "legacy_radv": bool(state.get("legacy_steamos_radv_detected")),
        "external_runtime_invalid": str(state.get("steamos_external_radv_state") or "") == "invalid"
        or str(state.get("steamos_external_fsr4_state") or "") == "invalid",
        "external_runtime_current": bool(state.get("steamos_external_radv_current")),
        "external_fsr4_current": bool(state.get("steamos_external_fsr4_current")),
        "external_installed": bool(state.get("dryhopped_installed")),
        "external_boot_active": bool(state.get("dryhopped_boot_active")),
        "masta_async_compute_ready": bool(state.get("masta_async_compute_ready")),
        "bazzite_current": bool(state.get("bazzite_async_current")),
        "bazzite_enabled": bool(state.get("bazzite_async_enabled")),
        "bazzite_session_active": bool(state.get("bazzite_async_session_active")),
        "bazzite_invalid": bool(state.get("bazzite_async_installed"))
        and not bool(state.get("bazzite_async_current")),
    }
    status, tone = _status(reason, **values)
    return Gfx1013Presentation(
        status=status,
        tone=tone,
        detail=_detail(reason, **values),
        steamos_actions=reason == "steamos-dedicated-backend",
        fedora_actions=reason == "fedora-upstream-managed",
        bazzite_actions=reason.startswith("bazzite-release-"),
        compatibility_action=("Update / repair SteamOS kernel" if values["kernel_ready"] else "1 · Install SteamOS kernel"),
    )
