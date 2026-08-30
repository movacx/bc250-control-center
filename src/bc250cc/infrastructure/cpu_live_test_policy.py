"""Pure identity checks for CPU manual-scale live-test evidence."""


def _same_integer(left, right):
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def _optional_integer_matches(actual, requested):
    return requested is None or _same_integer(actual, requested)


def classify_cpu_live_test(
    saved_test,
    detection,
    current_boot_id,
    *,
    requested_scale=None,
    requested_frequency=None,
    requested_temperature=None,
):
    """Return whether a saved live apply belongs to exact detector evidence."""
    saved_test = dict(saved_test) if isinstance(saved_test, dict) else {}
    detection = dict(detection) if isinstance(detection, dict) else {}
    snapshot_value = detection.get("snapshot")
    snapshot = dict(snapshot_value) if isinstance(snapshot_value, dict) else {}

    exact_scale = _optional_integer_matches(saved_test.get("scale"), requested_scale)
    exact_frequency = _optional_integer_matches(
        saved_test.get("frequency"), requested_frequency
    )
    exact_temperature = _optional_integer_matches(
        saved_test.get("temperature"), requested_temperature
    )

    boot_id = str(current_boot_id or "")
    saved_boot_id = str(saved_test.get("boot_id") or "")
    same_boot = bool(saved_test and saved_boot_id and boot_id and saved_boot_id == boot_id)
    direct_manual = bool(saved_test.get("reference_source") == "manual-direct")

    identity_matches = bool(
        saved_test
        and snapshot
        and detection.get("matches_current_config")
        and detection.get("detector_evidence_pristine")
        and _same_integer(
            saved_test.get("detected_frequency", saved_test.get("frequency")),
            snapshot.get("frequency"),
        )
        and _same_integer(
            saved_test.get("detected_temperature", saved_test.get("temperature")),
            snapshot.get("temperature"),
        )
        and _same_integer(saved_test.get("detected_scale"), snapshot.get("scale"))
        and str(saved_test.get("detection_run_id") or "")
        == str(snapshot.get("run_id") or "")
        and str(saved_test.get("detected_config_sha256") or "")
        == str(snapshot.get("detected_config_sha256") or "")
        and bool(str(snapshot.get("run_id") or ""))
        and bool(str(snapshot.get("detected_config_sha256") or ""))
    )
    valid_for_persistence = bool(
        saved_test
        and saved_test.get("result") == "applied-live"
        and identity_matches
        and exact_scale
        and exact_frequency
        and exact_temperature
    )
    return {
        "recorded": bool(saved_test),
        "matches_detection": identity_matches,
        "same_boot": same_boot,
        # A direct manual apply is valid live evidence for this boot, but it is
        # deliberately never detector evidence and cannot authorize boot
        # persistence.
        "active_in_current_session": bool(same_boot and (identity_matches or direct_manual)),
        "direct_manual": direct_manual,
        "exact_scale": exact_scale,
        "exact_frequency": exact_frequency,
        "exact_temperature": exact_temperature,
        "valid_for_persistence": valid_for_persistence,
        "test": saved_test,
        "detection": detection,
    }
