import pytest

from bc250cc.application.compute_units import plan_cu_mask_operations, validate_cu_masks
from bc250cc.application.cpu import validate_tuning_target
from bc250cc.domain.compute_units import WgpMaskTable
from bc250cc.domain.cpu import CpuBinding, CpuTuningProfile, estimated_vid


def test_cpu_validation_preserves_reviewed_limits():
    assert validate_tuning_target(3500, -50, 70).ok
    assert not validate_tuning_target(4201, -30, 80).ok
    assert not validate_tuning_target(4000, 1, 80).ok


def test_cpu_validation_returns_typed_failure_for_invalid_input():
    result = validate_tuning_target("not-a-frequency", -30, 80)
    assert result.ok is False
    assert result.error.code == "CPU_INPUT_INVALID"


def test_cpu_validation_rejects_boolean_input():
    result = validate_tuning_target(True, -30, 80)
    assert result.ok is False
    assert result.error.code == "CPU_INPUT_INVALID"


def test_cpu_validation_rejects_values_that_would_be_truncated():
    result = validate_tuning_target(3500.9, -30, 80)
    assert result.ok is False
    assert result.error.code == "CPU_INPUT_INVALID"
    with pytest.raises(TypeError):
        estimated_vid(3850.5, -30)


def test_cpu_domain_models_reject_invalid_reconstructed_state():
    with pytest.raises(ValueError):
        CpuTuningProfile(4201, -30, 80)
    with pytest.raises(ValueError):
        CpuBinding("", "hash", 3850, 80, -30)
    assert CpuTuningProfile(3850, -30, 80).frequency_mhz == 3850


def test_cu_masks_are_four_rows_and_count_wgps_as_two_cus():
    table = WgpMaskTable.from_values([0x1F, 0x1F, 0x1F, 0x1F])

    assert table.active_cus == 40
    assert validate_cu_masks([0x0F, 0x07, 0x07, 0x07]) == (15, 7, 7, 7)
    assert plan_cu_mask_operations([0x0F, 0x07, 0x07, 0x07])[-1][1] == "enable-wgp"


def test_cu_mask_validation_rejects_out_of_range_rows():
    with pytest.raises(ValueError):
        WgpMaskTable.from_values([0, 0, 0, 0x20])


def test_cu_mask_validation_rejects_boolean_rows():
    with pytest.raises(ValueError):
        WgpMaskTable.from_values([True, 0, 0, 0])


def test_cu_mask_validation_rejects_values_that_would_be_truncated():
    with pytest.raises(ValueError):
        WgpMaskTable.from_values([15.9, 0, 0, 0])


def test_cu_domain_state_cannot_bypass_table_invariants():
    with pytest.raises(ValueError):
        WgpMaskTable((0, 0, 0, 32))
    table = WgpMaskTable.from_values([0x0F, 0x07, 0x07, 0x07])
    with pytest.raises(ValueError):
        from bc250cc.domain.compute_units import ComputeUnitState
        ComputeUnitState(24, 40, table)
