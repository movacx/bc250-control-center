from bc250cc.infrastructure.cpu_live_test_policy import classify_cpu_live_test


def _detection(**overrides):
    value = {
        "matches_current_config": True,
        "detector_evidence_pristine": True,
        "snapshot": {
            "run_id": "run-a",
            "frequency": 3850,
            "scale": -36,
            "temperature": 90,
            "detected_config_sha256": "sha-a",
        },
    }
    value.update(overrides)
    return value


def _live_test(**overrides):
    value = {
        "result": "applied-live",
        "boot_id": "boot-a",
        "detection_run_id": "run-a",
        "detected_config_sha256": "sha-a",
        "detected_frequency": 3850,
        "detected_scale": -36,
        "detected_temperature": 90,
        "frequency": 3700,
        "scale": -30,
        "temperature": 85,
    }
    value.update(overrides)
    return value


def test_exact_live_test_is_active_and_valid_for_persistence():
    state = classify_cpu_live_test(
        _live_test(), _detection(), "boot-a",
        requested_scale=-30, requested_frequency=3700, requested_temperature=85,
    )

    assert state["matches_detection"] is True
    assert state["active_in_current_session"] is True
    assert state["valid_for_persistence"] is True


def test_previous_boot_test_remains_persistence_evidence_but_is_not_active():
    state = classify_cpu_live_test(_live_test(), _detection(), "boot-b")

    assert state["matches_detection"] is True
    assert state["same_boot"] is False
    assert state["active_in_current_session"] is False
    assert state["valid_for_persistence"] is True


def test_malformed_or_ambiguous_identity_fails_closed():
    cases = (
        ({}, _detection()),
        (_live_test(detection_run_id=""), _detection()),
        (_live_test(detected_config_sha256=""), _detection()),
        (_live_test(detected_scale="bad"), _detection()),
        (_live_test(), _detection(matches_current_config=False)),
        (_live_test(), _detection(detector_evidence_pristine=False)),
        (_live_test(), _detection(snapshot={})),
    )
    for saved_test, detection in cases:
        state = classify_cpu_live_test(saved_test, detection, "boot-a")
        assert state["matches_detection"] is False
        assert state["valid_for_persistence"] is False


def test_requested_candidate_must_match_all_three_values():
    for requested in (
        {"requested_scale": -29},
        {"requested_frequency": 3850},
        {"requested_temperature": 90},
    ):
        state = classify_cpu_live_test(_live_test(), _detection(), "boot-a", **requested)
        assert state["matches_detection"] is True
        assert state["valid_for_persistence"] is False


def test_success_marker_is_required_even_when_identity_matches():
    state = classify_cpu_live_test(_live_test(result="failed"), _detection(), "boot-a")

    assert state["matches_detection"] is True
    assert state["valid_for_persistence"] is False
