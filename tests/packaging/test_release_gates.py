from argparse import Namespace

from bc250cc.application.headless_dispatch import dispatch_safe
from bc250cc.application.recovery.release_gates import build_release_gate_report
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS


def test_release_report_never_converts_static_tests_into_public_readiness():
    report = build_release_gate_report()
    assert report["schema"] == 2
    assert report["static_contracts_ready"] is True
    assert report["public_release_ready"] is False
    assert report["manifest_issues"] == {}
    assert report["recovery"]["capture_contract_complete"] is True
    assert report["recovery"]["restore_executor_enabled"] is False


def test_release_report_exposes_legal_and_physical_gates_separately():
    report = build_release_gate_report()
    assert report["redistribution_blockers"] == {}
    # fsr4_runtime joins these because upstream publishes no LICENSE file, so
    # it must stay runtime-fetch-only and its payload must never be bundled.
    assert set(report["redistribution_constraints"]) == {
        "cu_manager_standard", "cu_manager_steamos", "fsr4_runtime"
    }
    assert "core_unlock" in report["hardware_validation_blockers"]
    assert "nct6687" in report["hardware_validation_blockers"]
    assert report["internal_hardware_validation_blockers"]["quick_access_decky"]["status"] == (
        "pending-external-evidence"
    )
    assert "steamos_amdgpu" in report["boot_recovery_blockers"]
    assert "core_unlock" in report["boot_recovery_blockers"]
    assert EXTERNAL_TOOLS["gfx1013_direct"].automated is True
    assert "gfx1013_direct" in report["boot_recovery_blockers"]
    assert "stock Fedora boot entry" in (
        report["boot_recovery_blockers"]["gfx1013_direct"]["rollback"]
    )


def test_release_report_covers_every_automated_hardware_writer_without_self_certification():
    report = build_release_gate_report()
    matrix = report["hardware_qualification_matrix"]
    covered = {
        tool
        for section in matrix.values()
        for tool in section["tools"]
    }
    required = {
        key
        for key, spec in EXTERNAL_TOOLS.items()
        if spec.automated and spec.hardware_writes
    }

    assert report["qualification_contract_complete"] is True
    assert required <= covered
    assert set(matrix) == {
        "cpu_smu", "gpu_governors", "compute_units", "fan_pwm",
        "quick_access_decky", "core_unlock_and_boot", "memory_thermal",
    }
    assert "gddr6_memory_temp" in matrix["memory_thermal"]["tools"]
    assert all(
        section["status"] == "pending-external-evidence"
        and section["mock_results_can_qualify"] is False
        and section["independent_reproduction_required"] is True
        for section in matrix.values()
    )


def test_headless_release_gate_handler_is_read_only_and_machine_ready():
    result = dispatch_safe(Namespace(command="release-gates"), object())
    assert result.exit_code == 0
    assert result.payload["public_release_ready"] is False
    assert len(result.payload["required_external_evidence"]) == 4
