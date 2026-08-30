"""Pure resolution of the CPU tuning active in the current session."""

from __future__ import annotations


def resolve_active_cpu_tuning(persistent, detection, scale_live, quick_access=None):
    """Resolve current CPU state without reading persistence or hardware.

    Desktop and Quick Access evidence are compared by action timestamp so a
    polling refresh cannot make an older setting appear active.
    """
    persistent = dict(persistent or {})
    detection = dict(detection or {})
    scale_live = dict(scale_live or {})
    boot_config = dict(persistent.get("config") or {})
    snapshot = dict(detection.get("snapshot") or {})
    live_test = dict(scale_live.get("test") or {})
    quick_access = dict(quick_access or {})
    quick_profile = dict(quick_access.get("active_profile") or {})

    desktop_live_ns = int(live_test.get("applied_at_epoch_ns") or 0)
    desktop_detection_ns = int(snapshot.get("recorded_at_epoch_ns") or 0)
    quick_ns = int(
        quick_access.get("action_observed_at_unix_ns")
        or int(quick_profile.get("observed_at") or 0) * 1_000_000_000
    )
    if quick_access.get("available") and quick_profile and quick_ns >= max(
        desktop_live_ns, desktop_detection_ns
    ):
        return {
            "source": "live" if quick_profile.get("mode") == "manual" else "detection",
            "source_kind": "quick_access",
            "frequency": quick_profile.get("frequency"),
            "scale": quick_profile.get("scale"),
            "temperature": quick_profile.get("temperature"),
            "estimated_vid": quick_profile.get("estimated_vid"),
        }
    if scale_live.get("active_in_current_session") and live_test:
        return {
            "source": "live", "source_kind": "desktop",
            "frequency": live_test.get("frequency"), "scale": live_test.get("scale"),
            "temperature": live_test.get("temperature"),
            "estimated_vid": live_test.get("estimated_vid"),
        }
    if persistent.get("applied_this_boot") and boot_config.get("valid"):
        return {
            "source": "boot", "source_kind": "boot",
            "frequency": boot_config.get("frequency"), "scale": boot_config.get("scale"),
            "temperature": boot_config.get("max_temperature"),
            "estimated_vid": boot_config.get("estimated_vid"),
        }
    if detection.get("same_boot") and detection.get("matches_current_config") and snapshot:
        return {
            "source": "detection", "source_kind": "desktop",
            "frequency": snapshot.get("frequency"), "scale": snapshot.get("scale"),
            "temperature": snapshot.get("temperature"),
            "estimated_vid": snapshot.get("estimated_vid"),
        }
    return {
        "source": "", "source_kind": "", "frequency": None, "scale": None,
        "temperature": None, "estimated_vid": None,
    }
