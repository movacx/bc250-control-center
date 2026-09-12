import pytest

from frontends.desktop.core.gfx1013_presenter import present_gfx1013


@pytest.mark.parametrize(
    ("state", "status", "tone", "detail_fragment"),
    [
        (
            {"reason_key": "steamos-dedicated-backend"},
            "SteamOS backend", "blue", "matching AMDGPU first",
        ),
        (
            {"reason_key": "steamos-dedicated-backend", "steamos_kernel_ready": True},
            "Kernel half ready", "blue", "Install the matched Mesa/RADV stage",
        ),
        (
            {
                "reason_key": "steamos-dedicated-backend",
                "steamos_kernel_ready": True,
                "steamos_safe_radv_detected": True,
            },
            "Async compute detected", "green", "both detected",
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
    assert "incomplete or has changed" in presentation.detail[0]


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
    assert inactive.status == "External install"


def test_steamos_actions_follow_kernel_readiness_only():
    missing = present_gfx1013({"reason_key": "steamos-dedicated-backend"})
    ready = present_gfx1013({
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
    })
    fedora = present_gfx1013({"reason_key": "fedora-upstream-managed"})

    assert missing.steamos_actions is True
    assert missing.compatibility_action == "1 · Install SteamOS kernel"
    assert ready.compatibility_action == "Update / repair SteamOS kernel"
    assert fedora.steamos_actions is False
    assert fedora.fedora_actions is True
