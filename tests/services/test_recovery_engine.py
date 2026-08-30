import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import bc250cc.infrastructure.persistence.recovery_engine as recovery
from bc250cc.infrastructure.persistence.recovery_engine import (
    RecoverySnapshotRepository,
    _source_changed_during_copy,
)


@pytest.fixture
def allowed_tmp(monkeypatch, tmp_path):
    system = tmp_path / "etc"
    system.mkdir()
    monkeypatch.setattr(recovery, "ALLOWED_SYSTEM_PREFIXES", (system,))
    monkeypatch.setattr(recovery, "BOOT_CRITICAL_PREFIXES", (system / "boot",))
    return system


def _stable_metadata(**overrides):
    values = {
        "st_dev": 1,
        "st_ino": 2,
        "st_mode": 0o100644,
        "st_uid": 1000,
        "st_gid": 1000,
        "st_size": 16,
        "st_mtime_ns": 100,
        "st_ctime_ns": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_stable_source_metadata_accepts_only_same_identity_and_copy_length():
    before = _stable_metadata()

    assert _source_changed_during_copy(before, _stable_metadata(), 16) is False
    assert _source_changed_during_copy(before, _stable_metadata(st_ctime_ns=101), 16) is True
    assert _source_changed_during_copy(before, _stable_metadata(st_mode=0o100600), 16) is True
    assert _source_changed_during_copy(before, _stable_metadata(st_ino=3), 16) is True
    assert _source_changed_during_copy(before, _stable_metadata(), 15) is True


def test_snapshot_is_private_atomic_and_verifiable(tmp_path, allowed_tmp):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config], label="before-change")
    entries = repository.load(snapshot)
    assert snapshot.stat().st_mode & 0o777 == 0o700
    assert (snapshot / "manifest.json").stat().st_mode & 0o777 == 0o600
    assert entries[0].state == "captured"
    assert repository.verify(snapshot)
    assert not snapshot.name.startswith(".")
    assert not list((tmp_path / "snapshots").glob(".capture-*"))


def test_failed_manifest_publish_removes_private_staging_tree(
    tmp_path, allowed_tmp, monkeypatch
):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    monkeypatch.setattr(
        repository,
        "_write_manifest",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        repository.capture([config])

    assert list((tmp_path / "snapshots").iterdir()) == []


def test_interrupted_atomic_rename_removes_private_staging_tree(
    tmp_path, allowed_tmp, monkeypatch
):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    root = tmp_path / "snapshots"
    repository = RecoverySnapshotRepository(root)
    original_rename = Path.rename

    def interrupted_rename(path, target):
        if path.parent == root and path.name.startswith(".capture-"):
            raise OSError("publication interrupted")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", interrupted_rename)

    with pytest.raises(OSError, match="publication interrupted"):
        repository.capture([config])

    assert list(root.iterdir()) == []


def test_directory_fsync_failure_after_rename_removes_published_snapshot(
    tmp_path, allowed_tmp, monkeypatch
):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    root = tmp_path / "snapshots"
    repository = RecoverySnapshotRepository(root)
    original_fsync = recovery._fsync_directory

    def failing_root_fsync(path):
        if Path(path) == root:
            raise OSError("directory fsync failed")
        return original_fsync(path)

    monkeypatch.setattr(recovery, "_fsync_directory", failing_root_fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        repository.capture([config])

    assert list(root.iterdir()) == []


def test_tampered_backup_blocks_restore_plan(tmp_path, allowed_tmp):
    config = allowed_tmp / "service.conf"
    config.write_text("original\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])
    entry = repository.load(snapshot)[0]
    (snapshot / entry.backup).write_text("tampered\n", encoding="utf-8")
    plan = repository.build_restore_plan(snapshot)
    assert not plan.verified
    assert plan.blocked
    assert not plan.actions[0].automatic_allowed


def test_boot_critical_entry_is_never_automatically_restored(tmp_path, allowed_tmp):
    boot_dir = allowed_tmp / "boot"
    boot_dir.mkdir()
    config = boot_dir / "kernel.conf"
    config.write_text("parameter=old\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    plan = repository.build_restore_plan(repository.capture([config]))
    assert plan.verified
    assert plan.blocked
    assert plan.actions[0].action == "restore-file"
    assert not plan.actions[0].automatic_allowed
    assert "proven recovery path" in plan.actions[0].reason


def test_portable_export_is_private_verified_reproducible_and_non_executable(
    tmp_path, allowed_tmp
):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config], label="before-portable-export")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    report = repository.export_portable_bundle(snapshot, first)
    repository.export_portable_bundle(snapshot, second)

    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_mode & 0o777 == 0o600
    assert report["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert report["automatic_restore_enabled"] is False
    with zipfile.ZipFile(first) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {
            "manifest.json", "RESTORE_PLAN.json", "README.txt",
            "files/0000-service.conf",
        }
        plan = json.loads(archive.read("RESTORE_PLAN.json"))
        assert plan["automatic_restore_enabled"] is False
        assert archive.read("files/0000-service.conf") == b"safe=true\n"
        assert not any(info.external_attr & 0o111 for info in archive.infolist())


def test_portable_export_refuses_tampering_and_never_overwrites_destination(
    tmp_path, allowed_tmp
):
    config = allowed_tmp / "service.conf"
    config.write_text("original\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])
    destination = tmp_path / "recovery.zip"
    destination.write_bytes(b"keep-me")

    with pytest.raises(FileExistsError, match="already exists"):
        repository.export_portable_bundle(snapshot, destination)
    assert destination.read_bytes() == b"keep-me"

    entry = repository.load(snapshot)[0]
    (snapshot / entry.backup).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="verification failed"):
        repository.export_portable_bundle(snapshot, tmp_path / "tampered.zip")
    assert not (tmp_path / "tampered.zip").exists()


def test_missing_path_creates_reversible_remove_plan(tmp_path, allowed_tmp):
    missing = allowed_tmp / "new-service.conf"
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    plan = repository.build_restore_plan(repository.capture([missing]))
    assert plan.actions[0].action == "remove-if-created"
    assert plan.actions[0].automatic_allowed


def test_root_owned_runtime_snapshot_is_evidence_not_an_automatic_restore(
    tmp_path, monkeypatch
):
    runtime = tmp_path / "usr/libexec/bc250-control-center"
    runtime.mkdir(parents=True)
    helper = runtime / "bc250-steamos-amdgpu-overlay"
    helper.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(recovery, "ALLOWED_SYSTEM_PREFIXES", (runtime,))
    monkeypatch.setattr(recovery, "MANUAL_RESTORE_PREFIXES", (runtime,))

    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    plan = repository.build_restore_plan(repository.capture([helper]))

    assert plan.verified
    assert plan.actions[0].action == "restore-file"
    assert not plan.actions[0].automatic_allowed
    assert "reviewed application build" in plan.actions[0].reason


def test_live_comparison_requires_a_verified_snapshot_and_detects_change(tmp_path, allowed_tmp):
    config = allowed_tmp / "service.conf"
    config.write_text("original=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])

    assert repository.inspect_current_state(snapshot)[0].state == "unchanged"
    config.write_text("changed=true\n", encoding="utf-8")
    observed = repository.inspect_current_state(snapshot)[0]
    assert observed.state == "changed-since-snapshot"
    assert observed.matches_snapshot is False
    assert "content" in observed.reason

    entry = repository.load(snapshot)[0]
    (snapshot / entry.backup).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="verification failed"):
        repository.inspect_current_state(snapshot)


def test_live_comparison_catches_later_creation_and_never_follows_links(tmp_path, allowed_tmp):
    missing = allowed_tmp / "absent.conf"
    captured = allowed_tmp / "captured.conf"
    captured.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([missing, captured])

    initial = {item.source: item for item in repository.inspect_current_state(snapshot)}
    assert initial[str(missing)].state == "still-missing"
    assert initial[str(missing)].matches_snapshot is True

    missing.write_text("created=true\n", encoding="utf-8")
    captured.unlink()
    captured.symlink_to(missing)
    current = {item.source: item for item in repository.inspect_current_state(snapshot)}
    assert current[str(missing)].state == "created-since-snapshot"
    assert current[str(captured)].state == "unsafe-symbolic-link"
    assert current[str(captured)].matches_snapshot is False


def test_live_comparison_rejects_regular_file_swap_between_lstat_and_open(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_text("original=true\n", encoding="utf-8")
    replacement = allowed_tmp / "replacement.conf"
    # Keep bytes and mode intentionally identical: content comparison alone
    # must not turn an inspect-time path substitution into "unchanged".
    replacement.write_text("original=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([source])
    original_open = recovery.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == source and not swapped:
            swapped = True
            source.unlink()
            replacement.rename(source)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(recovery.os, "open", racing_open)
    observed = repository.inspect_current_state(snapshot)[0]

    assert observed.state == "changed-during-inspection"
    assert observed.matches_snapshot is False
    assert "changed before" in observed.reason


def test_symlinks_and_paths_outside_allowlist_are_rejected(tmp_path, allowed_tmp):
    target = allowed_tmp / "target"
    target.write_text("data", encoding="utf-8")
    link = allowed_tmp / "link"
    link.symlink_to(target)
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    entry = repository.load(repository.capture([link]))[0]
    assert entry.state == "unsupported"
    with pytest.raises(ValueError, match="outside"):
        repository.capture([tmp_path / "elsewhere"])


def test_malformed_manifest_fails_closed(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(json.dumps({"schema": 999, "entries": []}))
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    assert not repository.verify(snapshot)
    assert repository.build_restore_plan(snapshot).blocked


@pytest.mark.parametrize(
    ("field", "value"),
    (("label", ""), ("label", "x" * 65), ("created_at", True), ("created_at", float("nan"))),
)
def test_malformed_manifest_metadata_fails_closed(tmp_path, allowed_tmp, field, value):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])
    manifest = snapshot / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload[field] = value
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert not repository.verify(snapshot)
    assert repository.build_restore_plan(snapshot).blocked


def test_snapshot_label_cannot_escape_recovery_root(tmp_path, allowed_tmp):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    root = tmp_path / "snapshots"
    snapshot = RecoverySnapshotRepository(root).capture([config], label="../../outside / unsafe")
    assert snapshot.parent == root
    assert ".." not in snapshot.name
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("backup", "../../outside"),
        ("backup", "/etc/passwd"),
        ("source", "/home/user-controlled"),
        ("sha256", "not-a-digest"),
        ("mode", 0o10000),
        ("boot_critical", True),
        ("state", "execute-command"),
    ),
)
def test_tampered_manifest_fields_fail_closed(tmp_path, allowed_tmp, field, value):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])
    manifest = snapshot / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0][field] = value
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert not repository.verify(snapshot)
    assert repository.build_restore_plan(snapshot).blocked
    assert repository.build_restore_plan(snapshot).actions == ()


@pytest.mark.parametrize("duplicate_field", ("source", "backup"))
def test_duplicate_manifest_identity_fails_closed(
    tmp_path, allowed_tmp, duplicate_field
):
    first = allowed_tmp / "first.conf"
    second = allowed_tmp / "second.conf"
    first.write_text("first\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([first, second])
    manifest = snapshot / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][1][duplicate_field] = payload["entries"][0][duplicate_field]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    assert repository.verify(snapshot) is False
    plan = repository.build_restore_plan(snapshot)
    assert plan.blocked is True
    assert plan.actions == ()


def test_symlinked_snapshot_root_and_manifest_are_rejected(tmp_path, allowed_tmp):
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="root must not be"):
        RecoverySnapshotRepository(linked_root).capture([allowed_tmp / "missing"])

    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])
    manifest = snapshot / "manifest.json"
    target = snapshot / "other.json"
    manifest.rename(target)
    manifest.symlink_to(target)
    assert not repository.verify(snapshot)


def test_symlinked_snapshot_files_directory_is_rejected_before_export(tmp_path, allowed_tmp):
    config = allowed_tmp / "service.conf"
    config.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([config])
    files = snapshot / "files"
    actual = snapshot / "files-real"
    files.rename(actual)
    files.symlink_to(actual, target_is_directory=True)

    assert repository.verify(snapshot) is False
    assert repository.build_restore_plan(snapshot).blocked is True
    with pytest.raises(ValueError, match="verification failed"):
        repository.export_portable_bundle(snapshot, tmp_path / "recovery.zip")


def test_source_swapped_to_symlink_before_open_is_not_captured(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_text("original\n", encoding="utf-8")
    outside = tmp_path / "secret"
    outside.write_text("must-not-be-captured\n", encoding="utf-8")
    original_open = recovery.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == source and not swapped:
            swapped = True
            source.unlink()
            source.symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(recovery.os, "open", racing_open)
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([source])
    entry = repository.load(snapshot)[0]
    assert entry.state == "unreadable"
    assert entry.backup == ""
    assert not list((snapshot / "files").iterdir())


def test_source_swapped_to_another_regular_file_before_open_is_not_captured(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_text("original\n", encoding="utf-8")
    replacement = allowed_tmp / "replacement.conf"
    replacement.write_text("replacement\n", encoding="utf-8")
    original_open = recovery.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == source and not swapped:
            swapped = True
            source.unlink()
            replacement.rename(source)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(recovery.os, "open", racing_open)
    snapshot = RecoverySnapshotRepository(tmp_path / "snapshots").capture([source])
    entry = RecoverySnapshotRepository.load(snapshot)[0]

    assert entry.state == "unreadable"
    assert "changed before" in entry.reason
    assert not list((snapshot / "files").iterdir())


def test_source_growth_during_copy_is_bounded_and_partial_backup_is_removed(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_bytes(b"a" * 16)
    original_read = recovery.os.read
    first_read = True

    def growing_read(descriptor, amount):
        nonlocal first_read
        if first_read:
            first_read = False
            with source.open("ab") as handle:
                handle.write(b"b" * 32)
        return original_read(descriptor, amount)

    monkeypatch.setattr(recovery, "MAX_SNAPSHOT_FILE_BYTES", 32)
    monkeypatch.setattr(recovery.os, "read", growing_read)
    snapshot = RecoverySnapshotRepository(tmp_path / "snapshots").capture([source])
    entry = RecoverySnapshotRepository.load(snapshot)[0]

    assert entry.state == "unreadable"
    assert "size limit" in entry.reason
    assert not list((snapshot / "files").iterdir())


def test_snapshot_copy_handles_partial_descriptor_writes(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_bytes(b"complete-payload")
    original_write = recovery.os.write
    monkeypatch.setattr(
        recovery.os,
        "write",
        lambda descriptor, payload: original_write(descriptor, payload[:2]),
    )

    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([source])
    entry = repository.load(snapshot)[0]

    assert entry.state == "captured"
    assert (snapshot / entry.backup).read_bytes() == b"complete-payload"
    assert repository.verify(snapshot)


def test_manifest_size_and_entry_count_are_bounded(tmp_path, allowed_tmp, monkeypatch):
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    with pytest.raises(ValueError, match="too many source"):
        repository.capture(
            [allowed_tmp / f"missing-{index}" for index in range(257)]
        )

    snapshot = tmp_path / "oversized"
    snapshot.mkdir()
    manifest = snapshot / "manifest.json"
    manifest.write_bytes(b" " * 129)
    monkeypatch.setattr(recovery, "MAX_MANIFEST_BYTES", 128)
    assert not repository.verify(snapshot)


def test_manifest_must_be_regular_utf8_file(tmp_path):
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = tmp_path / "invalid-utf8"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_bytes(b"\xff")
    assert not repository.verify(snapshot)

    directory_manifest = tmp_path / "directory-manifest"
    directory_manifest.mkdir()
    (directory_manifest / "manifest.json").mkdir()
    assert not repository.verify(directory_manifest)

    wrong_root = tmp_path / "wrong-root"
    wrong_root.mkdir()
    (wrong_root / "manifest.json").write_text("[]", encoding="utf-8")
    assert not repository.verify(wrong_root)


def test_manifest_entry_count_and_backup_size_fail_closed(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_text("safe=true\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([source])
    manifest = snapshot / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"] = payload["entries"] * 2
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(recovery, "MAX_SNAPSHOT_ENTRIES", 1)
    assert not repository.verify(snapshot)

    snapshot = repository.capture([source])
    entry = repository.load(snapshot)[0]
    (snapshot / entry.backup).write_bytes(b"x" * 33)
    monkeypatch.setattr(recovery, "MAX_SNAPSHOT_FILE_BYTES", 32)
    assert not repository.verify(snapshot)


def test_backup_symlink_swap_during_verify_fails_closed(
    tmp_path, allowed_tmp, monkeypatch
):
    source = allowed_tmp / "service.conf"
    source.write_text("original\n", encoding="utf-8")
    repository = RecoverySnapshotRepository(tmp_path / "snapshots")
    snapshot = repository.capture([source])
    entry = repository.load(snapshot)[0]
    backup = snapshot / entry.backup
    outside = tmp_path / "outside"
    outside.write_text("original\n", encoding="utf-8")
    original_open = recovery.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == backup and not swapped:
            swapped = True
            backup.unlink()
            backup.symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(recovery.os, "open", racing_open)
    assert not repository.verify(snapshot)
