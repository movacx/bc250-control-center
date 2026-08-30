from pathlib import Path

import pytest

from bc250cc.application.recovery import service as recovery_facade
from bc250cc.application.recovery.service import (
    DEFAULT_RECOVERY_SOURCES,
    RECOVERY_SOURCE_GROUPS,
    RecoveryRepository,
    recovery_capture_readiness,
)
from bc250cc.infrastructure.persistence import recovery_engine
from bc250cc.infrastructure.persistence.recovery_engine import (
    RecoverySnapshotRepository,
)
from bc250cc.infrastructure.system_service import SistemaService


class Repository(RecoveryRepository):
    def __init__(self, root: Path):
        self.root = root

    def _recovery_snapshot_root(self) -> Path:
        return self.root


@pytest.fixture
def recovery_source(monkeypatch, tmp_path):
    source_root = tmp_path / "etc"
    source_root.mkdir()
    monkeypatch.setattr(recovery_engine, "ALLOWED_SYSTEM_PREFIXES", (source_root,))
    monkeypatch.setattr(recovery_engine, "BOOT_CRITICAL_PREFIXES", (source_root / "boot",))
    source = source_root / "service.conf"
    source.write_text("enabled=true\n", encoding="utf-8")
    return source


def test_inventory_reports_verified_snapshot_without_restore_capability(
    tmp_path, recovery_source
):
    root = tmp_path / "recovery"
    snapshot = RecoverySnapshotRepository(root).capture([recovery_source], label="before-test")
    payload = Repository(root).recovery_inventory()
    assert payload["restore_available"] is False
    assert payload["snapshots"] == [
        {
            "id": snapshot.name,
            "label": "before-test",
            "created_at": payload["snapshots"][0]["created_at"],
            "verified": True,
            "blocked": False,
            "actions": 1,
            "automatic_actions": 1,
        }
    ]
    assert payload["readiness"]["restore_executor_enabled"] is False


def test_plan_is_read_only_and_never_advertises_restore(tmp_path, recovery_source):
    root = tmp_path / "recovery"
    snapshot = RecoverySnapshotRepository(root).capture([recovery_source])
    original = recovery_source.read_bytes()
    plan = Repository(root).recovery_plan(snapshot.name)
    assert plan["verified"]
    assert plan["restore_available"] is False
    assert plan["actions"][0]["action"] == "restore-file"
    assert plan["current_state"] == [{
        "source": str(recovery_source),
        "state": "unchanged",
        "matches_snapshot": True,
        "reason": "",
    }]
    assert recovery_source.read_bytes() == original


@pytest.mark.parametrize("identifier", ("../outside", "/absolute", "", "a/b"))
def test_plan_rejects_identifier_escape(tmp_path, identifier):
    with pytest.raises(ValueError, match="identifier"):
        Repository(tmp_path / "recovery").recovery_plan(identifier)


def test_inventory_skips_symlinked_and_unexpected_entries(tmp_path):
    root = tmp_path / "recovery"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "not a snapshot").mkdir()
    (root / ".capture-interrupted").mkdir()
    assert Repository(root).recovery_inventory()["snapshots"] == []


def test_inventory_marks_tampered_snapshot_invalid(tmp_path, recovery_source):
    root = tmp_path / "recovery"
    snapshot = RecoverySnapshotRepository(root).capture([recovery_source])
    (snapshot / "manifest.json").write_text("{}", encoding="utf-8")
    item = Repository(root).recovery_inventory()["snapshots"][0]
    assert item["verified"] is False
    assert item["blocked"] is True
    assert item["label"] == "Invalid snapshot"


def test_recovery_contract_delegates_through_desktop_application_api():
    class Backend:
        def recovery_inventory(self, limit):
            return {"limit": limit}

        def create_recovery_snapshot(self, label):
            return {"label": label}

        def recovery_plan(self, snapshot_id):
            return {"id": snapshot_id}

        def export_recovery_snapshot(self, snapshot_id, destination):
            return {"id": snapshot_id, "path": destination}

    service = SistemaService(Backend())
    assert service.recovery_inventory(7) == {"limit": 7}
    assert service.create_recovery_snapshot("before-test") == {
        "label": "before-test"
    }
    assert service.recovery_plan("snapshot-1") == {"id": "snapshot-1"}
    assert service.export_recovery_snapshot("snapshot-1", "/tmp/evidence.zip") == {
        "id": "snapshot-1", "path": "/tmp/evidence.zip"
    }


def test_facade_exports_only_a_verified_snapshot_inside_its_private_root(
    tmp_path, recovery_source
):
    root = tmp_path / "recovery"
    snapshot = RecoverySnapshotRepository(root).capture([recovery_source])
    destination = tmp_path / "portable.zip"

    payload = Repository(root).export_recovery_snapshot(snapshot.name, destination)

    assert payload["path"] == str(destination)
    assert payload["automatic_restore_enabled"] is False
    assert destination.is_file()
    with pytest.raises(ValueError, match="identifier"):
        Repository(root).export_recovery_snapshot("../outside", tmp_path / "bad.zip")


def test_create_snapshot_uses_curated_sources_and_reports_states(
    tmp_path, recovery_source, monkeypatch
):
    boot = recovery_source.parent / "boot"
    boot.mkdir()
    boot_config = boot / "kernel.conf"
    boot_config.write_text("safe-option\n", encoding="utf-8")
    missing = recovery_source.parent / "missing.conf"
    monkeypatch.setattr(
        recovery_facade,
        "DEFAULT_RECOVERY_SOURCES",
        (str(recovery_source), str(boot_config), str(missing)),
    )
    payload = Repository(tmp_path / "recovery").create_recovery_snapshot(
        "before-ui-test"
    )
    assert payload["verified"] is True
    assert payload["blocked"] is True
    assert payload["restore_available"] is False
    assert payload["entries"] == 3
    assert payload["states"] == {"captured": 2, "missing": 1}
    assert payload["boot_critical"] == 1


def test_inventory_metadata_uses_bounded_manifest_reader(
    tmp_path, recovery_source, monkeypatch
):
    root = tmp_path / "recovery"
    snapshot = RecoverySnapshotRepository(root).capture([recovery_source])
    (snapshot / "manifest.json").write_bytes(b" " * 129)
    monkeypatch.setattr(recovery_engine, "MAX_MANIFEST_BYTES", 128)
    item = Repository(root).recovery_inventory()["snapshots"][0]
    assert item["verified"] is False
    assert item["label"] == "Invalid snapshot"


def test_default_recovery_capture_contract_covers_every_managed_subsystem():
    readiness = recovery_capture_readiness()
    assert readiness["capture_contract_complete"] is True
    assert set(readiness["source_groups"]) == set(RECOVERY_SOURCE_GROUPS)
    assert all(
        item["complete"] and item["missing_sources"] == []
        for item in readiness["source_groups"].values()
    )
    assert readiness["restore_executor_enabled"] is False
    assert readiness["physical_boot_recovery_proven"] is False
    assert len(DEFAULT_RECOVERY_SOURCES) == len(set(DEFAULT_RECOVERY_SOURCES))
    assert RECOVERY_SOURCE_GROUPS["steamos_amdgpu_runtime"] == {
        "/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/patch-driver.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/boot-config.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-update-persistence.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-storage.sh",
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/.bc250-control-center-reviewed-revision",
    }


def test_recovery_readiness_reports_exact_missing_coverage_without_writing():
    readiness = recovery_capture_readiness(["/etc/bc250-smu-oc.conf"])
    assert readiness["capture_contract_complete"] is False
    assert readiness["source_groups"]["cpu_tuning"]["missing_sources"] == [
        "/etc/systemd/system/bc250-smu-oc.service"
    ]
    assert readiness["source_groups"]["steamos_boot"]["complete"] is False
