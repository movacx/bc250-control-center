from bc250cc.domain.gpu.profiles import GpuProfile
from frontends.desktop.features.gpu import gpu_profile_options, profile_label
from frontends.quick_access.backend import map_gpu_status


def test_desktop_and_qam_receive_the_same_gpu_policy_shape():
    desktop = gpu_profile_options({"min": 700, "max": 1800})
    qam = map_gpu_status({"gpu_profiles": desktop})
    assert qam["gpu_profiles"] == desktop
    assert desktop[0]["min"] == 700
    assert desktop[-1]["max"] == 1800


def test_quick_access_does_not_invent_profiles_when_backend_has_none():
    assert map_gpu_status({})["gpu_profiles"] == []


def test_desktop_rejects_malformed_gpu_range_without_throwing():
    assert gpu_profile_options({"min": "not-a-number", "max": 1800}) == []
    assert gpu_profile_options({"min": True, "max": 1800}) == []
    assert gpu_profile_options({"min": 500.9, "max": 1800}) == []
    assert gpu_profile_options({"min": 1900, "max": 1800}) == []


def test_desktop_profile_label_uses_the_domain_model_field():
    assert profile_label(GpuProfile("balanced", "Balanced", 700, 1500)) == "Balanced"


def test_gpu_profile_constructor_cannot_bypass_domain_invariants():
    import pytest

    with pytest.raises(ValueError):
        GpuProfile("", "Balanced", 700, 1500)
    with pytest.raises(ValueError):
        GpuProfile("broken", "Broken", 1500, 700)
    with pytest.raises(ValueError):
        GpuProfile("broken", "Broken", 700.5, 1500)
