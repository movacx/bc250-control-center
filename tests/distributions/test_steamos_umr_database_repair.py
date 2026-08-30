import errno
import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "system" / "repair-steamos-umr-database.py"
)
SPEC = importlib.util.spec_from_file_location("bc250_umr_database_repair", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _database(root: Path, *, valid=True, mapped=False) -> Path:
    root.mkdir(parents=True)
    (root / "ip").mkdir()
    (root / "cyan_skillfish.asic").write_text(
        "cyan_skillfish cyan_skillfish.soc15 4 13 2 1\n"
        "gfx1010 GC 0 ip/gc_10_1_0.reg\n",
        encoding="utf-8",
    )
    (root / "cyan_skillfish.soc15").write_text("soc data\n", encoding="utf-8")
    registers = "\n".join(MODULE.EXPECTED_REGISTERS) if valid else "missing registers"
    (root / "ip" / "gc_10_1_0.reg").write_text(registers + "\n", encoding="utf-8")
    (root / "pci.did").write_text(
        "0x13FE cyan_skillfish.asic\n" if mapped else "0x9999 other.asic\n",
        encoding="utf-8",
    )
    return root


def test_atomic_umr_install_replaces_only_after_validation_and_adds_mapping(tmp_path):
    source = _database(tmp_path / "source")
    target = tmp_path / "database"
    target.mkdir()
    (target / "old.txt").write_text("known-good\n", encoding="utf-8")

    details, mapping_added = MODULE._install_tree_atomic(
        source, target, move_source=False
    )

    assert mapping_added is True
    assert details["selector"] == "cyan_skillfish.gfx1010"
    assert not (target / "old.txt").exists()
    assert "0x13FE cyan_skillfish.asic" in (target / "pci.did").read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".database.new-*"))
    assert not list(tmp_path.glob(".database.old-*"))


def test_invalid_umr_staging_preserves_target_and_removes_residue(tmp_path):
    source = _database(tmp_path / "source", valid=False)
    target = tmp_path / "database"
    target.mkdir()
    (target / "old.txt").write_text("known-good\n", encoding="utf-8")

    with pytest.raises(MODULE.DatabaseError, match="no GC register file"):
        MODULE._install_tree_atomic(source, target, move_source=False)

    assert (target / "old.txt").read_text(encoding="utf-8") == "known-good\n"
    assert not list(tmp_path.glob(".database.new-*"))
    assert not list(tmp_path.glob(".database.old-*"))


def test_umr_payload_symlink_is_rejected_without_touching_external_file(tmp_path):
    source = _database(tmp_path / "source")
    outside = tmp_path / "outside"
    outside.write_text("external\n", encoding="utf-8")
    (source / "unrelated-link").symlink_to(outside)
    target = tmp_path / "database"
    target.mkdir()
    (target / "old.txt").write_text("known-good\n", encoding="utf-8")

    with pytest.raises(MODULE.DatabaseError, match="refusing symlink"):
        MODULE._install_tree_atomic(source, target, move_source=False, owner_uid=None)

    assert outside.read_text(encoding="utf-8") == "external\n"
    assert (target / "old.txt").read_text(encoding="utf-8") == "known-good\n"
    assert not list(tmp_path.glob(".database.new-*"))


def test_valid_database_fixture_reports_exact_bc250_selector(tmp_path):
    database = _database(tmp_path / "database", mapped=True)

    details = MODULE.validate_database(database)

    assert details["header"] == "cyan_skillfish cyan_skillfish.soc15 4 13 2 1"
    assert details["gc_register_file"] == "ip/gc_10_1_0.reg"
    assert details["selector"] == "cyan_skillfish.gfx1010"


def test_umr_install_rejects_symlink_target_without_changing_external_tree(tmp_path):
    source = _database(tmp_path / "source")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("external\n", encoding="utf-8")
    target = tmp_path / "database"
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(MODULE.DatabaseError, match="database target"):
        MODULE._install_tree_atomic(source, target, move_source=False)

    assert target.is_symlink()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "external\n"


def test_main_print_selector_and_invalid_check_only_are_read_only(
    tmp_path, capsys
):
    valid = _database(tmp_path / "valid", mapped=True)
    assert MODULE.main(["--target", str(valid), "--print-selector"]) == 0
    assert capsys.readouterr().out.strip() == "cyan_skillfish.gfx1010"

    invalid = _database(tmp_path / "invalid", valid=False, mapped=True)
    assert MODULE.main(["--target", str(invalid), "--check-only"]) == 42
    assert "database is invalid" in capsys.readouterr().err


def test_main_migrates_valid_legacy_database_transactionally(
    tmp_path, monkeypatch, capsys
):
    target = tmp_path / "target" / "database"
    legacy_root = tmp_path / "legacy"
    legacy = _database(legacy_root / "database", mapped=False)
    original = (legacy / "cyan_skillfish.asic").read_bytes()
    monkeypatch.setattr(MODULE.shutil, "which", lambda _name: "/usr/bin/git")

    result = MODULE.main([
        "--target", str(target),
        "--legacy-root", str(legacy_root),
    ])

    assert result == 0
    assert MODULE.validate_database(target)["selector"] == "cyan_skillfish.gfx1010"
    assert (legacy / "cyan_skillfish.asic").read_bytes() == original
    assert "Migrating the valid legacy database" in capsys.readouterr().out


def test_main_clone_path_uses_temporary_target_filesystem_staging(
    tmp_path, monkeypatch
):
    target = tmp_path / "target" / "database"
    source = _database(tmp_path / "downloaded", mapped=False)
    monkeypatch.setattr(MODULE.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(MODULE, "_clone_database", lambda _repository, _tmp: source)

    assert MODULE.main([
        "--target", str(target),
        "--legacy-root", str(tmp_path / "missing-legacy"),
    ]) == 0
    assert MODULE.validate_database(target)["selector"] == "cyan_skillfish.gfx1010"
    assert not list(target.parent.glob(".bc250-umr-download-*"))


def test_main_reports_storage_full_without_publishing_partial_target(
    tmp_path, monkeypatch, capsys
):
    target = tmp_path / "target" / "database"
    monkeypatch.setattr(MODULE.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        MODULE,
        "_install_repaired_database",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.ENOSPC, "full")),
    )

    assert MODULE.main([
        "--target", str(target),
        "--legacy-root", str(tmp_path / "missing-legacy"),
    ]) == 47
    assert not target.exists()
    assert "CU_UMR_STORAGE_FULL" in capsys.readouterr().err
