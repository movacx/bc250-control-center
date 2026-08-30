from frontends.desktop.core.compute_units_presenter import (
    plan_cu_action_availability,
    present_compute_units_state,
)


def state(**updates):
    value = {
        "available": True,
        "masks": [0x07] * 4,
        "driver_masks": [0x07] * 4,
        "active_cus": 24,
        "routed_wgps": 12,
        "mode": "Factory 24 CUs",
        "service": "Enabled",
        "service_installed": True,
        "service_enabled": True,
        "boot_sync": "Current table saved",
        "boot_sync_key": "saved",
        "privileged_backend_ready": True,
        "driver_topology_available": True,
    }
    value.update(updates)
    return value


def test_presenter_prefers_verified_masks_over_stale_reported_count():
    presentation = present_compute_units_state(
        state(active_cus=40, routed_wgps=20),
        live_masks=[0x07] * 4,
    )

    assert presentation.verified is True
    assert presentation.active_cus == 24
    assert presentation.routed_wgps == 12
    assert presentation.mask_count_mismatch is True


def test_presenter_keeps_a_verified_quick_access_snapshot_on_the_live_spi_path():
    presentation = present_compute_units_state(
        state(source_kind="quick_access", fresh=False), live_masks=[0x0F] * 4
    )

    assert presentation.source_kind == "quick_access"
    assert (presentation.topology_status, presentation.topology_tone) == ("Live verified", "green")


def test_presenter_classifies_saved_pending_and_unverified_persistence():
    saved = present_compute_units_state(state(), live_masks=[0x07] * 4)
    pending = present_compute_units_state(
        state(boot_sync_key="pending"), live_masks=[0x07] * 4
    )
    missing = present_compute_units_state(
        state(boot_sync_key="not_saved"), live_masks=[0x07] * 4
    )

    assert (saved.persistence_status, saved.persistence_tone) == ("Enabled", "green")
    assert (pending.persistence_status, pending.persistence_tone) == ("Enabled", "orange")
    assert (missing.persistence_status, missing.persistence_tone) == ("Enabled", "orange")


def test_installed_service_does_not_disable_live_apply():
    actions = plan_cu_action_availability(state(), pending_wgps=2, busy=False)

    assert actions.apply_live is True
    assert actions.discard is True
    assert actions.remove_service is True


def test_privileged_actions_fail_closed_without_trusted_backend():
    actions = plan_cu_action_availability(
        state(privileged_backend_ready=False), pending_wgps=2, busy=False
    )

    assert actions.install_umr is True
    assert actions.save_boot is False
    assert actions.install_service is False
    assert actions.apply_saved is False
    assert actions.remove_service is False
    assert actions.restore_factory is False
    assert actions.apply_live is False


def test_boot_actions_require_a_verified_saved_table():
    unsaved = plan_cu_action_availability(
        state(boot_sync_key="not_saved"), pending_wgps=0, busy=False
    )
    saved = plan_cu_action_availability(state(), pending_wgps=0, busy=False)

    assert unsaved.save_boot is True
    assert unsaved.install_service is False
    assert unsaved.apply_saved is False
    assert saved.install_service is True
    assert saved.apply_saved is True


def test_invalid_or_out_of_range_masks_fail_closed_instead_of_becoming_40_cus():
    for masks in ([-1] * 4, [0x20] * 4, [True] * 4, [float("inf")] * 4):
        malformed = state(masks=masks)
        actions = plan_cu_action_availability(
            malformed,
            pending_wgps=2,
            busy=False,
        )

        assert actions.save_boot is False
        assert actions.install_service is False
        assert actions.apply_saved is False
        assert actions.apply_live is False


def test_malformed_reported_counts_are_bounded_and_never_crash_presentation():
    presentation = present_compute_units_state(
        state(active_cus="invalid", routed_wgps=float("inf")),
        live_masks=(),
    )

    assert presentation.verified is False
    assert presentation.active_cus == 0
    assert presentation.routed_wgps == 0


def test_malformed_pending_count_cannot_unlock_live_apply():
    actions = plan_cu_action_availability(
        state(),
        pending_wgps="invalid",
        busy=False,
    )

    assert actions.apply_live is False
    assert actions.discard is False
