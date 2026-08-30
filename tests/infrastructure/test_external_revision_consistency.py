from pathlib import Path

from bc250cc.infrastructure.core_unlock_trust import REVIEWED_REVISION
from bc250cc.infrastructure.dependencias_repository import (
    CORE_UNLOCK_REPOSITORY,
    CYAN_GOVERNOR_REPOSITORY,
    STANDARD_CU_REVIEWED_COMMIT,
    STEAMOS_CORE_UNLOCK_REVIEWED_COMMIT,
    STEAMOS_CU_REVIEWED_COMMIT,
    STEAMOS_CYAN_REVIEWED_COMMIT,
    STEAMOS_FIX_REPOSITORY,
    STEAMOS_FIX_REVIEWED_COMMIT,
    STEAMOS_SMU_OC_REVIEWED_COMMIT,
    DependenciasRepository,
)
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS
from bc250cc.infrastructure.gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_UPSTREAM,
    STEAMOS_GFX1013_BACKEND,
)
from bc250cc.infrastructure.health_repository import HealthRepository
from bc250cc.infrastructure.tool_inventory import STANDARD_CU_URL, STEAMOS_CU_URL


def test_dependency_orchestrator_uses_manifest_provenance():
    assert CORE_UNLOCK_REPOSITORY == EXTERNAL_TOOLS["core_unlock"].upstream
    assert CYAN_GOVERNOR_REPOSITORY == EXTERNAL_TOOLS["cyan_smu"].upstream
    assert STEAMOS_FIX_REPOSITORY == EXTERNAL_TOOLS["steamos_amdgpu"].upstream
    assert STEAMOS_FIX_REVIEWED_COMMIT == EXTERNAL_TOOLS["steamos_amdgpu"].reviewed_revision
    assert STEAMOS_CORE_UNLOCK_REVIEWED_COMMIT == EXTERNAL_TOOLS["core_unlock"].reviewed_revision
    assert STEAMOS_CU_REVIEWED_COMMIT == EXTERNAL_TOOLS["cu_manager_steamos"].reviewed_revision
    assert STANDARD_CU_REVIEWED_COMMIT == EXTERNAL_TOOLS["cu_manager_standard"].reviewed_revision
    assert STEAMOS_CYAN_REVIEWED_COMMIT == EXTERNAL_TOOLS["cyan_smu"].reviewed_revision
    assert STEAMOS_SMU_OC_REVIEWED_COMMIT == EXTERNAL_TOOLS["cpu_smu_oc"].reviewed_revision


def test_all_python_integration_inventories_share_manifest_provenance():
    assert STANDARD_CU_URL == EXTERNAL_TOOLS["cu_manager_standard"].upstream
    assert STEAMOS_CU_URL == EXTERNAL_TOOLS["cu_manager_steamos"].upstream
    assert GFX1013_UPSTREAM == EXTERNAL_TOOLS["gfx1013_direct"].upstream
    assert GFX1013_REVIEWED_COMMIT == EXTERNAL_TOOLS["gfx1013_direct"].reviewed_revision
    assert STEAMOS_GFX1013_BACKEND == EXTERNAL_TOOLS["steamos_amdgpu"].upstream
    assert REVIEWED_REVISION == EXTERNAL_TOOLS["core_unlock"].reviewed_revision
    expected = {
        EXTERNAL_TOOLS[key].upstream
        for key in ("cpu_smu_oc", "core_unlock", "cu_manager_standard", "nct6687")
    }
    assert {row[1] for row in HealthRepository._REPOSITORIES} == expected

    repository = DependenciasRepository.__new__(DependenciasRepository)
    repository._tool_dir = lambda: Path("/tmp/bc250-manifest-fixture")
    standard = repository._cu_manager_spec(
        type("OS", (), {"info": type("Info", (), {"family": "arch"})()})()
    )
    steamos = repository._cu_manager_spec(
        type("OS", (), {"info": type("Info", (), {"family": "steamos"})()})()
    )
    assert standard["repository"] == EXTERNAL_TOOLS["cu_manager_standard"].upstream
    assert steamos["repository"] == EXTERNAL_TOOLS["cu_manager_steamos"].upstream


def test_every_fan_script_uses_manifest_reviewed_revision():
    scripts = Path("packaging/common/os-scripts")
    for family in ("arch", "bazzite", "debian", "fedora", "steamos"):
        script = (scripts / family / "prepare-fan-pwm.sh").read_text(encoding="utf-8")
        assert EXTERNAL_TOOLS["nct6687"].reviewed_revision in script, family
        assert "bc250_stage_reviewed_git_tree" in script, family


def test_arch_fan_script_does_not_prefer_mutable_aur_git_package():
    script = Path(
        "packaging/common/os-scripts/arch/prepare-fan-pwm.sh"
    ).read_text(encoding="utf-8")
    assert "nct6687d-dkms-git" not in script
