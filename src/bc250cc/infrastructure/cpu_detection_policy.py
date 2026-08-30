"""Pure classification of persisted CPU detection evidence."""


def _same_integer(left, right):
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def classify_cpu_detection(snapshot, current_config, current_digest, current_boot_id):
    """Bind a saved detector run to the current file and boot identity.

    The returned flags are deliberately conservative: incomplete or malformed
    evidence never authorizes a live-test or persistence workflow.
    """
    snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
    current_config = dict(current_config) if isinstance(current_config, dict) else {}
    digest = str(current_digest or "")
    boot_id = str(current_boot_id or "")

    saved_boot_id = str(snapshot.get("boot_id") or "")
    same_boot = bool(snapshot and saved_boot_id and boot_id and saved_boot_id == boot_id)

    expected_scale = snapshot.get("current_scale", snapshot.get("scale"))
    matches = bool(
        snapshot
        and current_config.get("valid")
        and digest
        and snapshot.get("config_sha256") == digest
        and _same_integer(snapshot.get("frequency"), current_config.get("frequency"))
        and _same_integer(expected_scale, current_config.get("scale"))
        and _same_integer(snapshot.get("temperature"), current_config.get("max_temperature"))
    )

    detector_evidence_pristine = False
    legacy_override_in_detector_config = False
    if matches:
        try:
            detected_scale = int(snapshot.get("scale"))
            current_scale = int(snapshot.get("current_scale", detected_scale))
        except (TypeError, ValueError):
            pass
        else:
            detected_digest = str(snapshot.get("detected_config_sha256") or "")
            detector_evidence_pristine = bool(
                current_scale == detected_scale
                and detected_digest
                and digest == detected_digest
            )
            legacy_override_in_detector_config = current_scale != detected_scale

    return {
        "recorded": bool(snapshot),
        "matches_current_config": matches,
        "same_boot": same_boot,
        "detector_evidence_pristine": detector_evidence_pristine,
        "legacy_override_in_detector_config": legacy_override_in_detector_config,
        "snapshot": snapshot,
        "current_config": current_config,
        "current_sha256": digest,
    }
