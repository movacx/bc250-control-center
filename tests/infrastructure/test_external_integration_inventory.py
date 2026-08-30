from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS


class InventoryRepository(DependenciasRepository):
    def __init__(self, root, responses=None):
        self.root = root
        self.responses = responses or {}

    def _tool_dir(self):
        return self.root

    def _ejecutar(self, command, timeout=2):
        key = (command[2], tuple(command[3:]))
        return self.responses.get(key, (1, "", "unavailable"))


def test_external_inventory_reports_exact_verified_checkout(tmp_path):
    spec = EXTERNAL_TOOLS["cpu_smu_oc"]
    destination = tmp_path / "bc250_smu_oc"
    (destination / ".git").mkdir(parents=True)
    responses = {
        (str(destination), ("remote", "get-url", "origin")): (0, spec.upstream, ""),
        (str(destination), ("rev-parse", "--verify", "HEAD")): (
            0, spec.reviewed_revision, "",
        ),
        (str(destination), ("status", "--porcelain", "--untracked-files=all")): (
            0, "", "",
        ),
    }

    inventory = InventoryRepository(tmp_path, responses)._probe_external_integration_inventory()

    assert set(inventory) == set(EXTERNAL_TOOLS)
    assert inventory["cpu_smu_oc"]["verified"] is True
    assert inventory["cpu_smu_oc"]["source_verified"] is True
    assert inventory["cpu_smu_oc"]["tracked_dirty"] is False
    assert inventory["cpu_smu_oc"]["untracked_count"] == 0
    assert inventory["cpu_smu_oc"]["dirty"] is False
    assert inventory["core_unlock"]["present"] is False
    assert inventory["core_unlock"]["verified"] is False


def test_external_inventory_keeps_failed_git_evidence_local(tmp_path):
    destination = tmp_path / "bc250-core-unlock"
    (destination / ".git").mkdir(parents=True)

    inventory = InventoryRepository(tmp_path)._probe_external_integration_inventory()

    assert inventory["core_unlock"]["present"] is True
    assert inventory["core_unlock"]["git_checkout"] is True
    assert inventory["core_unlock"]["origin_matches"] is False
    assert inventory["core_unlock"]["revision_matches"] is False
    assert inventory["core_unlock"]["dirty"] is None
    assert inventory["core_unlock"]["source_verified"] is False
    assert inventory["core_unlock"]["verified"] is False
    assert inventory["gfx1013_direct"]["actions"] == ["check", "install", "rollback", "uninstall"]
