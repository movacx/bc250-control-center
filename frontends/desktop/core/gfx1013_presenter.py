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
    if state["external_boot_active"]:
        return "Patched boot active", "green"
    if state["external_installed"]:
        return "External install", "blue"
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
    if reason == "fedora-exact-upstream-host":
        return "Upstream-validated host", "blue"
    if reason == "bazzite-not-supported-upstream":
        return "Blocked", "orange"
    return "Manual only", "gray"


def _detail(reason: str, **state: bool) -> tuple[str, ...]:
    kernel = state["kernel_ready"]
    safe_radv = state["safe_radv"]
    if state["legacy_radv"]:
        return ("A legacy SteamOS alternate RADV installation was detected. That older path can include mesh/task patches that current upstream disabled after unrecoverable GPU hangs. Control Center will not run or update it.",)
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
        "fedora-exact-upstream-host": "This exact Fedora 43/kernel combination matches upstream validation. Control Center offers the reviewed combined kernel + Mesa/RADV workflow; it keeps the stock boot entry as default and selects the patched entry for one boot first.",
        "fedora-outside-upstream-validation": "This Fedora host is outside the exact Fedora 43/kernel combination validated upstream. Control Center will not automate the patch.",
        "arch-family-manual-untested": "Upstream documents this Arch-family path as manual and untested. Control Center does not automate kernel/Mesa changes here.",
        "bazzite-not-supported-upstream": "Upstream currently says Bazzite is not supported. Control Center blocks the direct installer on immutable systems.",
    }
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
    }
    status, tone = _status(reason, **values)
    return Gfx1013Presentation(
        status=status,
        tone=tone,
        detail=_detail(reason, **values),
        steamos_actions=reason == "steamos-dedicated-backend",
        fedora_actions=reason == "fedora-exact-upstream-host",
        compatibility_action=("Update / repair SteamOS kernel" if values["kernel_ready"] else "1 · Install SteamOS kernel"),
    )
