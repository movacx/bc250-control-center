from bc250cc.infrastructure.cpu_detection_policy import classify_cpu_detection


def _snapshot(**overrides):
    value = {
        "boot_id": "boot-a",
        "frequency": 3850,
        "scale": -35,
        "temperature": 90,
        "config_sha256": "digest-a",
        "detected_config_sha256": "digest-a",
    }
    value.update(overrides)
    return value


def _config(**overrides):
    value = {"valid": True, "frequency": 3850, "scale": -35, "max_temperature": 90}
    value.update(overrides)
    return value


def test_pristine_detection_requires_file_values_digest_and_boot_identity():
    state = classify_cpu_detection(_snapshot(), _config(), "digest-a", "boot-a")

    assert state["recorded"] is True
    assert state["matches_current_config"] is True
    assert state["same_boot"] is True
    assert state["detector_evidence_pristine"] is True
    assert state["legacy_override_in_detector_config"] is False


def test_matching_detection_from_previous_boot_remains_safe_reference_not_active_state():
    state = classify_cpu_detection(_snapshot(), _config(), "digest-a", "boot-b")

    assert state["matches_current_config"] is True
    assert state["same_boot"] is False
    assert state["detector_evidence_pristine"] is True


def test_legacy_in_place_override_is_recognized_but_never_pristine():
    snapshot = _snapshot(current_scale=-30, config_sha256="digest-b")
    state = classify_cpu_detection(snapshot, _config(scale=-30), "digest-b", "boot-a")

    assert state["matches_current_config"] is True
    assert state["detector_evidence_pristine"] is False
    assert state["legacy_override_in_detector_config"] is True


def test_malformed_or_incomplete_evidence_fails_closed():
    for snapshot in (
        None,
        [],
        _snapshot(frequency="invalid"),
        _snapshot(current_scale=None),
        _snapshot(config_sha256="wrong"),
        _snapshot(detected_config_sha256=""),
    ):
        state = classify_cpu_detection(snapshot, _config(), "digest-a", "boot-a")
        if snapshot and snapshot.get("detected_config_sha256") == "":
            assert state["matches_current_config"] is True
        else:
            assert state["matches_current_config"] is False
        assert state["detector_evidence_pristine"] is False


def test_invalid_current_config_cannot_match_even_with_equal_values():
    state = classify_cpu_detection(_snapshot(), _config(valid=False), "digest-a", "boot-a")

    assert state["matches_current_config"] is False
    assert state["detector_evidence_pristine"] is False
