"""Read-only release-gate report; never infers physical validation from tests."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOLS,
    validate_external_tool_manifest,
)
from bc250cc.infrastructure.persistence.qualification_evidence import (
    QualificationEvidenceError,
    qualification_template,
    validate_qualification_bundle,
    validate_qualification_evidence,
)

from .service import recovery_capture_readiness

_QUALIFIED_HARDWARE_LEVELS = frozenset({
    "hardware-qualified-two-hosts",
    "hardware-qualified-independent-reproduction",
})

_HARDWARE_QUALIFICATION_MATRIX = {
    "cpu_smu": {
        "tools": ("cpu_smu_oc",),
        "requirements": (
            "temporary detection and exact evidence binding",
            "manual scale live validation before persistence",
            "warm reboot, cold boot and disable-to-stock verification",
        ),
    },
    "gpu_governors": {
        "tools": ("cyan_smu", "oberon_governor"),
        "requirements": (
            "single-governor and conflict-path validation",
            "frequency and voltage behavior under a real 3D workload",
            "failed configuration/service restart rollback evidence",
        ),
    },
    "compute_units": {
        "tools": ("cu_manager_standard", "cu_manager_steamos"),
        "requirements": (
            "factory topology capture and temporary topology validation",
            "saved topology warm-reboot verification",
            "factory restore of live routing and persistence state",
        ),
    },
    "fan_pwm": {
        "tools": ("nct6687",),
        "requirements": (
            "physical PWM channel identification",
            "RPM response at two nonzero duties",
            "automatic/manual transition and daemon failsafe verification",
        ),
    },
    "quick_access_decky": {
        "tools": (),
        "requirements": (
            "Decky deployment state and protected helper inventory",
            "named live GPU/CU actions with real readback and no repeated Polkit prompts",
            "identified system-fan automatic restore and bounded CPU live/service confirmation",
        ),
    },
    "core_unlock_and_boot": {
        "tools": ("core_unlock", "steamos_amdgpu"),
        "requirements": (
            "recoverable-board preflight and offline recovery media",
            "warm/cold boot and video-output verification",
            "rollback rehearsal before success classification",
        ),
    },
}


def qualification_requirements() -> dict[str, tuple[str, ...]]:
    """Return a detached copy of the supervised qualification contract."""
    return {
        key: tuple(item["requirements"])
        for key, item in _HARDWARE_QUALIFICATION_MATRIX.items()
    }


def build_qualification_template(section: str) -> dict[str, object]:
    return qualification_template(section, qualification_requirements())


def _qualification_matrix(
    evidence: Sequence[str | Path] = (),
) -> tuple[dict[str, object], bool, list[dict[str, object]]]:
    matrix = {
        key: {
            "status": "pending-external-evidence",
            "tools": list(item["tools"]),
            "requirements": list(item["requirements"]),
            "mock_results_can_qualify": False,
            "independent_reproduction_required": True,
            "evidence_records": 0,
            "complete_records": 0,
            "distinct_boards": 0,
            "distinct_installations": 0,
            "independent_records": 0,
            "independent_reproduction_pair_present": False,
        }
        for key, item in _HARDWARE_QUALIFICATION_MATRIX.items()
    }
    evidence_results: list[dict[str, object]] = []
    identities: set[tuple[str, str, str, str]] = set()
    aggregate = {
        key: {"boards": set(), "installations": set(), "independent": 0}
        for key in matrix
    }
    for manifest in evidence:
        try:
            path = Path(manifest)
            validator = (
                validate_qualification_bundle
                if path.suffix.lower() == ".zip"
                else validate_qualification_evidence
            )
            result = validator(path, qualification_requirements())
        except (OSError, QualificationEvidenceError) as error:
            evidence_results.append({
                "path": str(manifest),
                "valid": False,
                "complete": False,
                "error": str(error),
                "review_required": True,
                "grants_hardware_qualification": False,
            })
            continue
        identity = (
            str(result["section"]), str(result["board_id"]),
            str(result["installation_id"]), str(result["started_at"]),
        )
        if identity in identities:
            evidence_results.append({
                "path": str(manifest),
                "valid": False,
                "complete": False,
                "error": "duplicate qualification evidence identity",
                "review_required": True,
                "grants_hardware_qualification": False,
            })
            continue
        identities.add(identity)
        evidence_results.append(result)
        section = str(result["section"])
        current = matrix[section]
        current["evidence_records"] += 1
        if result["complete"]:
            current["complete_records"] += 1
            aggregate[section]["boards"].add(str(result["board_id"]))
            aggregate[section]["installations"].add(str(result["installation_id"]))
            aggregate[section]["independent"] += int(
                bool(result["independent_reproduction"])
            )
        current["status"] = (
            "evidence-complete-awaiting-maintainer-approval"
            if current["complete_records"]
            else "evidence-recorded-incomplete"
        )
    for section, counts in aggregate.items():
        current = matrix[section]
        current["distinct_boards"] = len(counts["boards"])
        current["distinct_installations"] = len(counts["installations"])
        current["independent_records"] = counts["independent"]
        current["independent_reproduction_pair_present"] = bool(
            current["complete_records"] >= 2
            and current["distinct_boards"] >= 2
            and current["distinct_installations"] >= 2
            and current["independent_records"] >= 1
        )
    covered = {
        tool
        for item in _HARDWARE_QUALIFICATION_MATRIX.values()
        for tool in item["tools"]
    }
    required = {
        key
        for key, spec in EXTERNAL_TOOLS.items()
        if spec.automated and spec.hardware_writes
    }
    return matrix, required.issubset(covered), evidence_results


def build_release_gate_report(
    evidence: Sequence[str | Path] = (),
) -> dict[str, object]:
    manifest_issues = validate_external_tool_manifest()
    recovery = recovery_capture_readiness()
    redistribution_constraints = {
        key: list(spec.release_gates)
        for key, spec in EXTERNAL_TOOLS.items()
        if spec.release_gates
    }
    redistribution_blockers = {
        key: reasons
        for key, reasons in redistribution_constraints.items()
        if EXTERNAL_TOOLS[key].bundled_payload
    }
    hardware = {
        key: {
            "validation_level": spec.validation_level,
            "privilege_class": spec.privilege_class,
            "required": "supervised physical validation and independent reproduction",
        }
        for key, spec in EXTERNAL_TOOLS.items()
        if spec.automated
        and spec.hardware_writes
        and spec.validation_level not in _QUALIFIED_HARDWARE_LEVELS
    }
    boot = {
        key: {
            "validation_level": spec.validation_level,
            "rollback": spec.rollback,
            "required": "proven offline/physical recovery plus warm and cold reboot validation",
        }
        for key, spec in EXTERNAL_TOOLS.items()
        if spec.automated
        and any(
            token in spec.privilege_class
            for token in ("boot", "kernel", "initramfs", "reboot")
        )
    }
    (
        qualification_matrix,
        qualification_contract_complete,
        qualification_evidence,
    ) = _qualification_matrix(evidence)
    static_ready = not manifest_issues and bool(
        recovery["capture_contract_complete"]
    ) and qualification_contract_complete
    return {
        "schema": 2,
        "static_contracts_ready": static_ready,
        "public_release_ready": False,
        "manifest_issues": manifest_issues,
        "recovery": recovery,
        "redistribution_blockers": redistribution_blockers,
        "redistribution_constraints": redistribution_constraints,
        "hardware_validation_blockers": hardware,
        "internal_hardware_validation_blockers": {
            "quick_access_decky": {
                "required": (
                    "optional Decky feature requires supervised physical validation "
                    "before it can be claimed as hardware-tested"
                ),
                "status": qualification_matrix["quick_access_decky"]["status"],
            },
        },
        "boot_recovery_blockers": boot,
        "qualification_contract_complete": qualification_contract_complete,
        "hardware_qualification_matrix": qualification_matrix,
        "qualification_evidence": qualification_evidence,
        "qualification_evidence_can_self_certify": False,
        "required_external_evidence": [
            "Record the final full test, translation, packaging and clean-install results for the exact release commit.",
            "Complete supervised physical hardware qualification for every hardware-writing integration, including optional Quick Access when shipped.",
            "Prove boot-critical rollback from an offline recovery path before applying the hardware-tested label.",
            "Do not bundle payloads whose upstream license is not declared.",
        ],
    }
