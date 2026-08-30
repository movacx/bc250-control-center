import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

from bc250cc.application.recovery.release_gates import (
    build_qualification_template,
    build_release_gate_report,
    qualification_requirements,
)
from bc250cc.infrastructure.persistence.qualification_evidence import (
    QualificationEvidenceError,
    export_qualification_bundle,
    validate_qualification_bundle,
    validate_qualification_evidence,
)
from bc250cc.shared.version import __version__
from frontends.cli import main


class Host:
    def __init__(self, root: Path):
        self.root = root

    def _os_release(self):
        return {"ID": "arch", "PRETTY_NAME": "Fixture"}

    def _command_path(self, _name):
        return ""

    def _tool_dir(self):
        return self.root / "tools"


def _write_evidence(
    tmp_path: Path, *, section="compute_units", statuses=None,
    board_id="board-fixture-01", installation_id="install-fixture-01",
    independent=False,
):
    artifact = tmp_path / "session.log"
    artifact.write_text("supervised fixture evidence\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    requirements = qualification_requirements()[section]
    statuses = statuses or ["passed"] * len(requirements)
    payload = {
        "schema": 1,
        "section": section,
        "source_version": __version__,
        "board_id": board_id,
        "installation_id": installation_id,
        "operator": "operator-fixture",
        "started_at": "2026-08-13T12:00:00Z",
        "finished_at": "2026-08-13T12:30:00Z",
        "independent_reproduction": independent,
        "checks": [
            {
                "requirement": requirement,
                "status": status,
                "artifacts": (
                    [{"path": artifact.name, "sha256": digest}]
                    if status == "passed" else []
                ),
                "notes": "synthetic fixture only",
            }
            for requirement, status in zip(requirements, statuses, strict=True)
        ],
    }
    manifest = tmp_path / "qualification.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest, payload, artifact


def test_template_covers_exact_section_contract_without_writing():
    payload = build_qualification_template("compute_units")
    assert payload["source_version"] == __version__
    assert [item["requirement"] for item in payload["checks"]] == list(
        qualification_requirements()["compute_units"]
    )
    assert all(item["status"] == "skipped" for item in payload["checks"])


def test_complete_hashed_evidence_is_recorded_but_never_self_certifies(tmp_path):
    manifest, _, _ = _write_evidence(tmp_path)
    result = validate_qualification_evidence(
        manifest, qualification_requirements()
    )
    assert result["valid"] is True
    assert result["complete"] is True
    assert result["review_required"] is True
    assert result["grants_hardware_qualification"] is False

    report = build_release_gate_report([manifest])
    section = report["hardware_qualification_matrix"]["compute_units"]
    assert section["status"] == "evidence-complete-awaiting-maintainer-approval"
    assert section["complete_records"] == 1
    assert report["public_release_ready"] is False
    assert report["qualification_evidence_can_self_certify"] is False


def test_failed_check_is_valid_incomplete_evidence(tmp_path):
    manifest, _, _ = _write_evidence(
        tmp_path, statuses=["passed", "failed", "skipped"]
    )
    report = build_release_gate_report([manifest])
    evidence = report["qualification_evidence"][0]
    assert evidence["valid"] is True
    assert evidence["complete"] is False
    assert report["hardware_qualification_matrix"]["compute_units"]["status"] == (
        "evidence-recorded-incomplete"
    )


def test_artifact_tampering_fails_closed_in_report(tmp_path):
    manifest, _, artifact = _write_evidence(tmp_path)
    artifact.write_text("changed after capture\n", encoding="utf-8")
    with pytest.raises(QualificationEvidenceError, match="hash mismatch"):
        validate_qualification_evidence(manifest, qualification_requirements())
    result = build_release_gate_report([manifest])["qualification_evidence"][0]
    assert result["valid"] is False
    assert result["grants_hardware_qualification"] is False


def test_artifact_symlink_is_rejected_even_when_target_stays_contained(tmp_path):
    manifest, payload, artifact = _write_evidence(tmp_path)
    linked = tmp_path / "linked.log"
    linked.symlink_to(artifact)
    payload["checks"][0]["artifacts"][0]["path"] = linked.name
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QualificationEvidenceError, match="symbolic link"):
        validate_qualification_evidence(manifest, qualification_requirements())


def test_multiple_records_are_aggregated_independently_of_input_order(tmp_path):
    complete_root = tmp_path / "complete"
    incomplete_root = tmp_path / "incomplete"
    complete_root.mkdir()
    incomplete_root.mkdir()
    complete, _, _ = _write_evidence(complete_root)
    incomplete, _, _ = _write_evidence(
        incomplete_root, statuses=["passed", "failed", "skipped"],
        board_id="board-fixture-02", installation_id="install-fixture-02",
    )
    for paths in ([complete, incomplete], [incomplete, complete]):
        section = build_release_gate_report(paths)["hardware_qualification_matrix"][
            "compute_units"
        ]
        assert section["status"] == (
            "evidence-complete-awaiting-maintainer-approval"
        )
        assert section["evidence_records"] == 2
        assert section["complete_records"] == 1


def test_duplicate_record_cannot_inflate_evidence_counts(tmp_path):
    manifest, _, _ = _write_evidence(tmp_path)
    report = build_release_gate_report([manifest, manifest])
    section = report["hardware_qualification_matrix"]["compute_units"]
    assert section["evidence_records"] == 1
    assert section["complete_records"] == 1
    assert report["qualification_evidence"][1]["valid"] is False
    assert "duplicate" in report["qualification_evidence"][1]["error"]


def test_independent_pair_requires_distinct_complete_board_and_installation(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first, _, _ = _write_evidence(first_root)
    second, _, _ = _write_evidence(
        second_root,
        board_id="board-fixture-02",
        installation_id="install-fixture-02",
        independent=True,
    )
    section = build_release_gate_report([first, second])[
        "hardware_qualification_matrix"
    ]["compute_units"]
    assert section["distinct_boards"] == 2
    assert section["distinct_installations"] == 2
    assert section["independent_records"] == 1
    assert section["independent_reproduction_pair_present"] is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda payload: payload.update(source_version="0.0.0"), "version mismatch"),
        (lambda payload: payload["checks"].pop(), "missing requirements"),
        (lambda payload: payload["checks"].append(dict(payload["checks"][0])), "duplicate requirement"),
        (lambda payload: payload.update(finished_at="2026-08-13T11:59:59Z"), "precedes"),
    ),
)
def test_manifest_identity_and_coverage_fail_closed(tmp_path, mutation, message):
    manifest, payload, _ = _write_evidence(tmp_path)
    mutation(payload)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QualificationEvidenceError, match=message):
        validate_qualification_evidence(manifest, qualification_requirements())


def test_passed_requirement_requires_at_least_one_hashed_artifact(tmp_path):
    manifest, payload, _ = _write_evidence(tmp_path)
    payload["checks"][0]["artifacts"] = []
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QualificationEvidenceError, match="no hashed artifact"):
        validate_qualification_evidence(manifest, qualification_requirements())


def test_headless_template_validate_and_release_gate_are_read_only(
    tmp_path, capsys
):
    assert main(
        ["--json", "qualification", "template", "--section", "fan_pwm"],
        host=Host(tmp_path),
    ) == 0
    template = json.loads(capsys.readouterr().out)
    assert template["section"] == "fan_pwm"

    manifest, _, _ = _write_evidence(tmp_path, section="fan_pwm")
    assert main(
        ["--json", "qualification", "validate", str(manifest)],
        host=Host(tmp_path),
    ) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True

    assert main(
        ["--json", "release-gates", "--evidence", str(manifest)],
        host=Host(tmp_path),
    ) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["hardware_qualification_matrix"]["fan_pwm"]["status"] == (
        "evidence-complete-awaiting-maintainer-approval"
    )
    assert report["public_release_ready"] is False


def test_portable_bundle_is_deterministic_private_and_release_gate_ready(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest, _, _ = _write_evidence(source)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    result = export_qualification_bundle(
        manifest, first, qualification_requirements()
    )
    export_qualification_bundle(manifest, second, qualification_requirements())

    assert first.read_bytes() == second.read_bytes()
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert result["automatic_actions"] is False
    assert result["grants_hardware_qualification"] is False
    verified = validate_qualification_bundle(first, qualification_requirements())
    assert verified["complete"] is True
    gate = build_release_gate_report([first])
    assert gate["qualification_evidence"][0]["valid"] is True
    assert gate["public_release_ready"] is False


def test_portable_bundle_refuses_existing_destination(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest, _, _ = _write_evidence(source)
    destination = tmp_path / "existing.zip"
    destination.write_bytes(b"keep")
    with pytest.raises(FileExistsError, match="already exists"):
        export_qualification_bundle(
            manifest, destination, qualification_requirements()
        )
    assert destination.read_bytes() == b"keep"


def test_portable_bundle_rejects_tampered_artifact_and_unknown_member(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest, _, _ = _write_evidence(source)
    original = tmp_path / "original.zip"
    export_qualification_bundle(manifest, original, qualification_requirements())

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(original) as source_zip, zipfile.ZipFile(tampered, "w") as output:
        for info in source_zip.infolist():
            data = source_zip.read(info)
            if info.filename == "session.log":
                data = b"tampered\n"
            output.writestr(info, data)
    with pytest.raises(QualificationEvidenceError, match="hash mismatch"):
        validate_qualification_bundle(tampered, qualification_requirements())

    extra = tmp_path / "extra.zip"
    with zipfile.ZipFile(original) as source_zip, zipfile.ZipFile(extra, "w") as output:
        for info in source_zip.infolist():
            output.writestr(info, source_zip.read(info))
        output.writestr("undeclared.txt", b"unexpected")
    with pytest.raises(QualificationEvidenceError, match="contents mismatch"):
        validate_qualification_bundle(extra, qualification_requirements())


def test_portable_bundle_rejects_archive_traversal(tmp_path):
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("qualification.json", b"{}")
        archive.writestr("../escape", b"unsafe")
    with pytest.raises(QualificationEvidenceError, match="unsafe.*member"):
        validate_qualification_bundle(bundle, qualification_requirements())


@pytest.mark.parametrize("mode", (stat.S_IFLNK | 0o777, stat.S_IFREG | 0o700))
def test_portable_bundle_rejects_link_or_executable_metadata(tmp_path, mode):
    bundle = tmp_path / f"unsafe-{mode}.zip"
    unsafe = zipfile.ZipInfo("qualification.json")
    unsafe.create_system = 3
    unsafe.external_attr = mode << 16
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(unsafe, b"{}")
    with pytest.raises(QualificationEvidenceError, match="unsafe.*member"):
        validate_qualification_bundle(bundle, qualification_requirements())


def test_headless_exports_and_validates_portable_qualification_bundle(
    tmp_path, capsys
):
    source = tmp_path / "source"
    source.mkdir()
    manifest, _, _ = _write_evidence(source)
    bundle = tmp_path / "qualification.zip"
    assert main(
        ["--json", "qualification", "export", str(manifest), "--output", str(bundle)],
        host=Host(tmp_path),
    ) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["path"] == str(bundle)
    assert exported["automatic_actions"] is False
    assert main(
        ["--json", "qualification", "validate-bundle", str(bundle)],
        host=Host(tmp_path),
    ) == 0
    assert json.loads(capsys.readouterr().out)["bundle_sha256"] == exported[
        "bundle_sha256"
    ]
