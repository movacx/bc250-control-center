#!/usr/bin/env python3
"""Validate, migrate and repair the SteamOS-private UMR database.

The SteamOS CU backend needs UMR's cyan_skillfish static model.  SteamOS ships a
very small /var partition, so keeping the full UMR database under /var/lib can
fill the filesystem and leave zero-byte or partial model files.  This tool keeps
the private database in the invoking user's BC250 data directory, validates the
exact model/register chain used by the BC-250, and installs it atomically.

Only the SteamOS dependency workflow calls this tool.  Other distributions and
their UMR/database layouts are not changed.
"""
from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import re
import pwd
import shutil
import subprocess
import sys
import tempfile

DEFAULT_TARGET = Path("~/.local/share/bc250-control-center/ResourceTools/umr-steamos/database")
DEFAULT_REPOSITORY = "https://gitlab.freedesktop.org/tomstdenis/umr.git"
DEFAULT_LEGACY_ROOT = Path("/var/lib/bc250-cu-live-manager/umr")
MODEL_FILE = "cyan_skillfish.asic"
EXPECTED_REGISTERS = (
    "mmCC_GC_SHADER_ARRAY_CONFIG",
    "mmSPI_PG_ENABLE_STATIC_WGP_MASK",
    "mmRLC_PG_ALWAYS_ON_WGP_MASK",
)
PCI_MAPPING_RE = re.compile(r"^\s*0x0*13fe\s+cyan_skillfish(?:\.asic)?\s*$", re.IGNORECASE)


class DatabaseError(RuntimeError):
    pass


def _reject_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise DatabaseError(f"refusing symlink for {label}: {path}")


def _validate_target_scope(target: Path, owner_uid: int | None) -> None:
    """Keep the sudo repair write confined to the invoking user's app data."""
    if owner_uid is None:
        return
    try:
        home = Path(pwd.getpwuid(owner_uid).pw_dir).resolve()
    except KeyError as exc:
        raise DatabaseError(f"unknown owner uid {owner_uid}") from exc
    expected = (
        home
        / ".local"
        / "share"
        / "bc250-control-center"
        / "ResourceTools"
        / "umr-steamos"
        / "database"
    )
    if target != expected:
        raise DatabaseError(f"refusing out-of-scope SteamOS UMR target: {target}; expected {expected}")
    current = home
    _reject_symlink(current, "home")
    for component in expected.relative_to(home).parts[:-1]:
        current = current / component
        if current.exists():
            _reject_symlink(current, "target component")


def _safe_database_file(database: Path, relative: str) -> Path:
    _reject_symlink(database, "database directory")
    candidate = database / relative
    _reject_symlink(candidate, "database file")
    try:
        root = database.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DatabaseError(f"cannot resolve database file {candidate}: {exc}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DatabaseError(f"database file escapes the database root: {candidate}") from exc
    return candidate


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise DatabaseError(f"cannot read {path}: {exc}") from exc


def _first_nonempty_line(path: Path) -> str:
    for line in _read_text(path).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _validate_asic_header(database: Path) -> tuple[str, str, list[str]]:
    model = _safe_database_file(database, MODEL_FILE)
    if not model.is_file():
        raise DatabaseError(f"missing {model}")
    if model.stat().st_size <= 0:
        raise DatabaseError(f"{model} is empty")

    lines = _read_text(model).splitlines()
    header = next((line.strip() for line in lines if line.strip()), "")
    fields = header.split()
    if len(fields) != 6:
        raise DatabaseError(
            f"invalid {MODEL_FILE} header: expected 6 fields, got {len(fields)}: {header!r}"
        )
    common_name, soc15_name, family, block_count, vgpr_granularity, is_apu = fields
    if common_name != "cyan_skillfish":
        raise DatabaseError(f"unexpected ASIC common name in {MODEL_FILE}: {common_name!r}")
    try:
        family_i = int(family, 0)
        blocks_i = int(block_count, 0)
        vgpr_i = int(vgpr_granularity, 0)
        apu_i = int(is_apu, 0)
    except ValueError as exc:
        raise DatabaseError(f"non-numeric ASIC header field in {MODEL_FILE}: {header!r}") from exc
    if family_i < 0 or blocks_i <= 0 or vgpr_i < 0 or apu_i not in (0, 1):
        raise DatabaseError(f"out-of-range ASIC header field in {MODEL_FILE}: {header!r}")

    soc15 = _safe_database_file(database, soc15_name)
    if not soc15.is_file() or soc15.stat().st_size <= 0:
        raise DatabaseError(f"missing or empty SOC15 database file: {soc15}")
    return header, soc15_name, lines


def _referenced_gc_register(database: Path, model_lines: list[str]) -> tuple[str, Path]:
    candidates: list[tuple[str, Path]] = []
    for line in model_lines[1:]:
        fields = line.split()
        if len(fields) != 4:
            continue
        ip_common, ip_soc, _instance, regfile = fields
        if ip_common.startswith("gfx") or ip_soc == "GC":
            candidates.append((ip_common, _safe_database_file(database, regfile)))
    for ip_common, candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            text = _read_text(candidate)
            if all(register in text for register in EXPECTED_REGISTERS):
                return ip_common, candidate
    names = ", ".join(str(item) for _ip, item in candidates) or "none"
    raise DatabaseError(
        "no GC register file referenced by cyan_skillfish.asic contains all BC-250 CU registers; "
        f"candidates: {names}"
    )


def _ensure_pci_mapping(database: Path) -> bool:
    pci = _safe_database_file(database, "pci.did")
    if not pci.is_file():
        raise DatabaseError(f"missing {pci}")
    text = _read_text(pci)
    if any(PCI_MAPPING_RE.match(line) for line in text.splitlines()):
        return False
    with pci.open("a", encoding="utf-8") as handle:
        if text and not text.endswith("\n"):
            handle.write("\n")
        handle.write("0x13FE cyan_skillfish.asic\n")
    return True


def validate_database(database: Path, *, require_pci_mapping: bool = True) -> dict[str, str]:
    if not database.is_dir():
        raise DatabaseError(f"database directory does not exist: {database}")
    header, soc15_name, model_lines = _validate_asic_header(database)
    gc_ip, gc_file = _referenced_gc_register(database, model_lines)
    if require_pci_mapping:
        pci = _safe_database_file(database, "pci.did")
        if not pci.is_file():
            raise DatabaseError(f"missing {pci}")
        if not any(PCI_MAPPING_RE.match(line) for line in _read_text(pci).splitlines()):
            raise DatabaseError("pci.did does not map PCI ID 0x13FE to cyan_skillfish.asic")
    return {
        "header": header,
        "soc15": soc15_name,
        "gc_register_file": str(gc_file.relative_to(database)),
        # The actual UMR register namespace comes from the GC block name in the
        # .asic file. On current databases this is gfx1010, not gfx1013.
        "selector": f"cyan_skillfish.{gc_ip}",
    }


def _clone_database(repository: str, destination: Path) -> Path:
    repo = destination / "umr-source"
    command = ["git", "clone", "--depth", "1", repository, str(repo)]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise DatabaseError(
            "failed to clone the UMR source database:\n" + (result.stdout or "(no output)").strip()
        )
    database = repo / "database"
    if not database.is_dir():
        raise DatabaseError(f"UMR repository did not contain {database}")
    return database


def _chmod_tree(target: Path, owner_uid: int | None = None) -> None:
    for root, dirs, files in os.walk(target):
        try:
            os.chmod(root, 0o755)
            if owner_uid is not None:
                os.chown(root, owner_uid, -1)
        except OSError:
            pass
        for name in dirs:
            try:
                path = Path(root) / name
                os.chmod(path, 0o755)
                if owner_uid is not None:
                    os.chown(path, owner_uid, -1)
            except OSError:
                pass
        for name in files:
            try:
                path = Path(root) / name
                os.chmod(path, 0o644)
                if owner_uid is not None:
                    os.chown(path, owner_uid, -1)
            except OSError:
                pass


def _install_tree_atomic(source: Path, target: Path, *, move_source: bool, owner_uid: int | None = None) -> tuple[dict[str, str], bool]:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{target.name}.new-{os.getpid()}"
    old = parent / f".{target.name}.old-{os.getpid()}"
    for stale in (staging, old):
        if stale.exists():
            shutil.rmtree(stale)

    if move_source:
        source.rename(staging)
    else:
        shutil.copytree(source, staging, symlinks=True)
    mapping_added = _ensure_pci_mapping(staging)
    details = validate_database(staging, require_pci_mapping=True)

    if target.exists():
        target.rename(old)
    try:
        staging.rename(target)
    except Exception:
        if old.exists() and not target.exists():
            old.rename(target)
        raise
    if old.exists():
        shutil.rmtree(old)
    _chmod_tree(target, owner_uid)
    return details, mapping_added


def _safe_remove(path: Path) -> int:
    """Remove one known legacy tree and return its approximate byte count."""
    if not path.exists() or path.is_symlink():
        return 0
    size = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    size += item.stat().st_size
            except OSError:
                pass
        shutil.rmtree(path)
    except OSError as exc:
        raise DatabaseError(f"could not remove legacy UMR tree {path}: {exc}") from exc
    return size


def cleanup_legacy_root(legacy_root: Path, *, remove_database: bool) -> int:
    """Delete only stale paths created by older BC250 Control Center builds."""
    if not legacy_root.is_dir():
        return 0
    candidates: list[Path] = []
    for item in legacy_root.iterdir():
        name = item.name
        if (
            name.startswith("database.new.")
            or name.startswith(".database.new-")
            or name.startswith("database.broken-")
            or name == "database.manual-backup"
            or (remove_database and name == "database")
        ):
            candidates.append(item)
    return sum(_safe_remove(item) for item in candidates)




def update_service_config(config: Path, database: Path, selector: str) -> bool:
    """Update only the two UMR environment keys in the known service config."""
    if not config.exists():
        return False
    if config.is_symlink():
        raise DatabaseError(f"refusing symlinked service config: {config}")
    text = _read_text(config)
    lines = text.splitlines()
    replacements = {
        "UMR_DATABASE_PATH": str(database),
        "UMR_ASIC": selector,
    }
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")
    temporary = config.with_name(config.name + f".tmp-{os.getpid()}")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o644)
    temporary.replace(config)
    return True

def _print_valid(target: Path, details: dict[str, str]) -> None:
    print(f"[OK] SteamOS UMR database is valid: {target}")
    print(f"[OK] ASIC header: {details['header']}")
    print(f"[OK] GC registers: {details['gc_register_file']}")
    print(f"[OK] UMR selector: {details['selector']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--legacy-root", type=Path, default=DEFAULT_LEGACY_ROOT)
    parser.add_argument("--force", action="store_true", help="refresh even when the current database validates")
    parser.add_argument("--check-only", action="store_true", help="validate without changing files")
    parser.add_argument("--owner-uid", type=int, default=None, help="chown the installed database to this uid")
    parser.add_argument("--service-config", type=Path, default=Path("/etc/bc250-cu-live-manager.conf"))
    parser.add_argument("--update-service-config", action="store_true")
    parser.add_argument(
        "--cleanup-legacy",
        action="store_true",
        help="after a valid user database exists, remove stale/full databases from the old /var location",
    )
    args = parser.parse_args()

    target = args.target.expanduser().resolve()
    legacy_root = args.legacy_root.expanduser().resolve()
    _validate_target_scope(target, args.owner_uid)
    try:
        current = validate_database(target, require_pci_mapping=True)
    except DatabaseError as exc:
        current = None
        current_error = str(exc)
    else:
        current_error = ""

    if current is not None and not args.force:
        if not args.check_only:
            _chmod_tree(target, args.owner_uid)
        _print_valid(target, current)
        if args.update_service_config and update_service_config(args.service_config, target, current["selector"]):
            print(f"[OK] Updated service UMR path: {args.service_config}")
        if args.cleanup_legacy:
            freed = cleanup_legacy_root(legacy_root, remove_database=True)
            if freed:
                print(f"[OK] Freed {freed / (1024 * 1024):.1f} MiB from the obsolete /var UMR trees")
        return 0

    if args.check_only:
        print(f"[ERR] SteamOS UMR database is invalid: {current_error}", file=sys.stderr)
        return 42

    target.parent.mkdir(parents=True, exist_ok=True)
    if args.owner_uid is not None:
        try:
            os.chown(target.parent, args.owner_uid, -1)
            os.chmod(target.parent, 0o755)
        except OSError:
            pass
    if shutil.which("git") is None:
        print("[ERR] git is required to refresh the UMR database", file=sys.stderr)
        return 44

    print(f"[WARN] SteamOS UMR database needs repair: {current_error or 'forced refresh'}")

    legacy_database = legacy_root / "database"
    legacy_details: dict[str, str] | None = None
    if legacy_database.resolve() != target:
        try:
            legacy_details = validate_database(legacy_database, require_pci_mapping=False)
        except DatabaseError:
            legacy_details = None

    try:
        if legacy_details is not None:
            print(f"[INFO] Migrating the valid legacy database out of the small /var partition: {legacy_database}")
            installed, mapping_added = _install_tree_atomic(legacy_database, target, move_source=False, owner_uid=args.owner_uid)
            source_details = legacy_details
        else:
            # Put the download and staging area on the target filesystem. This
            # avoids filling SteamOS /var and makes the final rename atomic.
            with tempfile.TemporaryDirectory(prefix=".bc250-umr-download-", dir=target.parent) as tmp:
                source = _clone_database(args.repository, Path(tmp))
                source_details = validate_database(source, require_pci_mapping=False)
                installed, mapping_added = _install_tree_atomic(source, target, move_source=True, owner_uid=args.owner_uid)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            print(
                f"[ERR] CU_UMR_STORAGE_FULL: no space left while creating {target}. "
                "The SteamOS CU database is now stored under /home; free space there and retry.",
                file=sys.stderr,
            )
            return 47
        raise

    print(f"[OK] Refreshed SteamOS UMR database atomically: {target}")
    if mapping_added:
        print("[OK] Added PCI mapping: 0x13FE -> cyan_skillfish.asic")
    print(f"[OK] Source ASIC header: {source_details['header']}")
    print(f"[OK] Installed GC registers: {installed['gc_register_file']}")
    print(f"[OK] Selected register namespace: {installed['selector']}")
    if args.update_service_config and update_service_config(args.service_config, target, installed["selector"]):
        print(f"[OK] Updated service UMR path: {args.service_config}")

    if args.cleanup_legacy:
        freed = cleanup_legacy_root(legacy_root, remove_database=True)
        if freed:
            print(f"[OK] Freed {freed / (1024 * 1024):.1f} MiB from the obsolete /var UMR trees")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatabaseError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        raise SystemExit(45)
    except Exception as exc:
        print(f"[ERR] unexpected SteamOS UMR database repair failure: {exc}", file=sys.stderr)
        raise SystemExit(46)
