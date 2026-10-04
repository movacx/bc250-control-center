import pytest

from frontends.desktop.core.gfx1013_presenter import (
    RADV_ROUTE_SECOND_FIX,
    present_gfx1013,
    present_radv_route,
)


@pytest.mark.parametrize(
    ("state", "status", "tone", "detail_fragment"),
    [
        (
            {"reason_key": "steamos-dedicated-backend"},
            "SteamOS backend", "blue", "Two steps: install the kernel",
        ),
        (
            {"reason_key": "steamos-dedicated-backend", "steamos_kernel_ready": True},
            "Kernel half ready", "blue", "Install Mesa/RADV to enable async compute",
        ),
        (
            {
                "reason_key": "steamos-dedicated-backend",
                "steamos_kernel_ready": True,
                "steamos_safe_radv_detected": True,
            },
            "Async compute detected", "green", "Another GFX1013 RADV is installed",
        ),
        (
            {
                "reason_key": "steamos-dedicated-backend",
                "steamos_safe_radv_detected": True,
            },
            "Review required", "orange", "Do not use",
        ),
        (
            {"reason_key": "fedora-upstream-managed"},
            "Official upstream workflow", "blue", "official main branch",
        ),
        (
            {"reason_key": "arch-family-manual-untested"},
            "Manual only", "gray", "manual and untested",
        ),
        (
            {
                "reason_key": "arch-family-manual-untested",
                "masta_async_compute_ready": True,
            },
            "Installed via MastaG", "green", "No separate DryhoppedIPA installation",
        ),
        (
            {"reason_key": "bazzite-release-kernel-unsupported"},
            "Blocked", "orange", "7.2.0-ogc4.1",
        ),
        (
            {"reason_key": "bazzite-release-managed"},
            "Bazzite release available", "blue", "separate RADV driver",
        ),
        (
            {"reason_key": "manual-patches-only"},
            "Manual only", "gray", "manual patch guidance",
        ),
    ],
)
def test_presenter_maps_supported_host_states(state, status, tone, detail_fragment):
    presentation = present_gfx1013(state)

    assert presentation.status == status
    assert presentation.tone == tone
    assert detail_fragment in " ".join(presentation.detail)


def test_legacy_radv_has_highest_warning_precedence():
    presentation = present_gfx1013({
        "reason_key": "steamos-dedicated-backend",
        "legacy_steamos_radv_detected": True,
        "steamos_kernel_ready": True,
        "steamos_safe_radv_detected": True,
        "dryhopped_boot_active": True,
    })

    assert presentation.status == "Review required"
    assert "legacy SteamOS alternate RADV" in presentation.detail[0]


def test_current_external_steamos_radv_is_not_labelled_as_legacy():
    presentation = present_gfx1013({
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
        "steamos_external_radv_state": "ready",
        "steamos_external_radv_current": True,
        "steamos_external_fsr4_state": "ready",
        "steamos_external_fsr4_current": True,
    })

    assert presentation.status == "Async compute detected"
    assert presentation.tone == "green"
    assert "optional per-game FSR4 profile is also intact" in " ".join(presentation.detail)


def test_incomplete_external_steamos_runtime_requires_review():
    presentation = present_gfx1013({
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
        "steamos_external_fsr4_state": "invalid",
    })

    assert presentation.status == "Review required"
    assert "incomplete or changed" in presentation.detail[0]


def test_hidden_fsr4_state_does_not_change_visible_gfx1013_presentation():
    presentation = present_gfx1013(
        {
            "reason_key": "steamos-dedicated-backend",
            "steamos_kernel_ready": True,
            "steamos_external_fsr4_state": "invalid",
            "steamos_external_fsr4_current": True,
        },
        include_fsr4=False,
    )

    assert presentation.status == "Kernel half ready"
    assert "FSR4" not in " ".join(presentation.detail)


def test_external_boot_state_precedes_an_inactive_external_install():
    active = present_gfx1013({
        "dryhopped_installed": True,
        "dryhopped_boot_active": True,
    })
    inactive = present_gfx1013({"dryhopped_installed": True})

    assert active.status == "Patched boot active"
    assert inactive.status == "Installed"


def test_steamos_actions_follow_kernel_readiness_only():
    missing = present_gfx1013({"reason_key": "steamos-dedicated-backend"})
    ready = present_gfx1013({
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
    })
    fedora = present_gfx1013({"reason_key": "fedora-upstream-managed"})

    assert missing.steamos_actions is True
    assert missing.compatibility_action == "1 · Install kernel"
    assert ready.compatibility_action == "1 · Repair kernel"
    assert fedora.steamos_actions is False
    assert fedora.fedora_actions is True


def test_an_installed_fix_on_a_stock_boot_names_the_buttons_that_switch_it_on():
    """Upstream boots the patched entry once: the next restart looked uninstalled."""
    inactive = present_gfx1013({
        "reason_key": "fedora-upstream-managed",
        "dryhopped_installed": True,
    })
    active = present_gfx1013({
        "reason_key": "fedora-upstream-managed",
        "dryhopped_installed": True,
        "dryhopped_boot_active": True,
    })

    assert "Boot with the fix" in " ".join(inactive.detail)
    assert "Make the fix the default" in " ".join(active.detail)


def test_fedora_on_7_2_presents_the_patched_radv_instead_of_dryhoppeds_installer():
    """DryhoppedIPA's kernel half never loads on Fedora 44: its amdgpu waits for root."""
    radv = {"supported": True, "state": "not-installed", "installed": False,
            "kernel": "7.2.8-200.fc44.x86_64", "expected_version": "26.2.3"}
    presentation = present_gfx1013({
        "reason_key": "fedora-upstream-managed",
        "dryhopped_installed": True,
        "radv_async": radv,
    })

    assert presentation.fedora_actions is False
    route = presentation.radv_route
    assert route is not None and route.build and not route.installed
    assert route.remove_fix_action == "gfx1013_fedora_uninstall"
    assert route.scope == "Fedora · linux 7.2+ · no kernel module"
    assert presentation.status == "Available"
    assert presentation.detail_values == {"version": "26.2.3", "kernel": "7.2.8-200.fc44.x86_64"}
    assert presentation.detail[-1] == RADV_ROUTE_SECOND_FIX


def test_fedora_without_the_route_keeps_dryhoppeds_installer():
    for radv in ({"supported": False}, None):
        state = {"reason_key": "fedora-upstream-managed"}
        if radv is not None:
            state["radv_async"] = radv
        presentation = present_gfx1013(state)
        assert presentation.fedora_actions is True and presentation.radv_route is None


def test_the_patched_radv_route_reads_the_same_on_arch():
    route = present_radv_route(
        {"state": "switched-off", "installed": True, "enabled": False, "version": "26.2.3"},
        source_installed=True,
    )
    assert (route.status, route.tone) == ("Switched off", "gray")
    assert not route.build and route.testable and route.installed
    assert route.remove_fix_action == "gfx1013_source_uninstall"
    assert route.scope == "Arch family · linux 7.2+ · no kernel module"
