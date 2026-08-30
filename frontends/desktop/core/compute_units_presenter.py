"""Pure presentation and action-readiness policy for Compute Units."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def _masks(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return ()
    try:
        masks = tuple(int(mask) for mask in value)
    except (TypeError, ValueError, OverflowError):
        return ()
    if any(isinstance(mask, bool) for mask in value) or any(mask < 0 or mask > 0x1F for mask in masks):
        return ()
    return masks


def _bounded_integer(value: object, *, minimum: int, maximum: int, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _cus(masks: Sequence[int]) -> int:
    return sum(int(mask).bit_count() * 2 for mask in masks)


@dataclass(frozen=True)
class CuStatePresentation:
    verified: bool
    active_cus: int
    routed_wgps: int
    mode: str
    mode_short: str
    service: str
    init_manager: str
    boot_sync: str
    boot_sync_key: str
    persistence_detail: str
    topology_status: str
    topology_tone: str
    persistence_status: str
    persistence_tone: str
    source: str
    source_kind: str
    fresh: bool
    umr: str
    driver_ready: bool
    driver_cus: int
    asic: str
    updated_at: str
    mask_count_mismatch: bool


@dataclass(frozen=True)
class CuActionAvailability:
    install_umr: bool
    save_boot: bool
    install_service: bool
    apply_saved: bool
    remove_service: bool
    restore_factory: bool
    discard: bool
    apply_live: bool


def _topology_values(
    state: Mapping[str, object],
    masks: Sequence[int],
) -> tuple[bool, int, int, bool]:
    verified = bool(state.get("available")) and bool(masks)
    reported = _bounded_integer(state.get("active_cus"), minimum=0, maximum=40)
    active = _cus(masks) if verified else reported
    mismatch = verified and active != reported
    routed = (
        active // 2
        if mismatch
        else _bounded_integer(
            state.get("routed_wgps"),
            minimum=0,
            maximum=20,
            default=active // 2,
        )
    )
    return verified, active, routed, mismatch


def _persistence_values(
    boot_key: str, persistence_detail: str = "", *, service_enabled: bool = False,
    service_known: bool = False,
) -> tuple[str, str, str]:
    if boot_key == "unsupported":
        return (
            "Unsupported", "gray",
            persistence_detail
            or "boot persistence is unsupported; live topology remains available",
        )
    if service_known:
        if not service_enabled:
            return "Disabled", "gray", "live changes may reset at boot"
        if boot_key == "saved":
            return "Enabled", "green", "boot table matches live state"
        return "Enabled", "orange", "live changes may reset at boot"
    if boot_key == "saved":
        return "Not verified", "gray", "live changes may reset at boot"
    if boot_key == "pending":
        return "Pending", "orange", "live changes may reset at boot"
    return "Not saved", "gray", "live changes may reset at boot"


def _topology_freshness(verified: bool, fresh: bool, source_kind: str) -> tuple[str, str]:
    if source_kind == "quick_access" and verified:
        return "Live verified", "green"
    if fresh:
        return "Live verified", "green"
    if verified:
        return "Authorized cache", "gray"
    return "Not verified", "gray"


def present_compute_units_state(
    state: Mapping[str, object],
    *,
    live_masks: Sequence[int],
) -> CuStatePresentation:
    masks = _masks(live_masks)
    verified, active, routed, mismatch = _topology_values(state, masks)
    mode = str(state.get("mode") or "Not verified")
    fresh = bool(state.get("fresh"))
    source_kind = str(state.get("source_kind") or "")
    boot_key = str(state.get("boot_sync_key") or "")
    persistence_status, persistence_tone, persistence_detail = _persistence_values(
        boot_key, str(state.get("persistence_detail") or ""),
        service_enabled=state.get("service_enabled") is True,
        service_known="service_enabled" in state,
    )
    topology_status, topology_tone = _topology_freshness(verified, fresh, source_kind)
    driver_masks = _masks(state.get("driver_masks"))
    return CuStatePresentation(
        verified=verified,
        active_cus=active,
        routed_wgps=routed,
        mode=mode,
        mode_short=mode.replace(" CUs", ""),
        service=str(state.get("service") or "Not verified"),
        init_manager=str(state.get("init_manager") or "unknown"),
        boot_sync=str(state.get("boot_sync") or "Not verified"),
        boot_sync_key=boot_key,
        persistence_detail=persistence_detail,
        topology_status=topology_status,
        topology_tone=topology_tone,
        persistence_status=persistence_status,
        persistence_tone=persistence_tone,
        source=str(state.get("source") or "Not verified"),
        source_kind=source_kind,
        fresh=fresh,
        umr=str(state.get("umr") or ""),
        driver_ready=bool(state.get("driver_topology_available")),
        driver_cus=_cus(driver_masks),
        asic=str(state.get("asic") or "Not verified"),
        updated_at=str(state.get("updated_at") or "--:--:--"),
        mask_count_mismatch=mismatch,
    )


def plan_cu_action_availability(
    state: Mapping[str, object],
    *,
    pending_wgps: int,
    busy: bool,
) -> CuActionAvailability:
    idle = not busy
    write_ready = bool(state.get("privileged_backend_ready"))
    verified = bool(state.get("available")) and bool(_masks(state.get("masks")))
    saved = str(state.get("boot_sync_key") or "") == "saved"
    persistence_supported = state.get("persistence_supported") is not False
    writable_verified = idle and write_ready and verified
    pending = _bounded_integer(pending_wgps, minimum=0, maximum=20)
    return CuActionAvailability(
        install_umr=idle,
        save_boot=writable_verified and persistence_supported,
        install_service=writable_verified and saved and persistence_supported,
        apply_saved=writable_verified and saved and pending == 0 and persistence_supported,
        remove_service=(
            idle and write_ready and persistence_supported
            and bool(state.get("service_installed"))
        ),
        restore_factory=idle and write_ready,
        discard=idle and pending > 0,
        apply_live=writable_verified and pending > 0,
    )
