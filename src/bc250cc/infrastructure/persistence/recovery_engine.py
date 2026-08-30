"""Local, verifiable recovery snapshots and non-executing restore plans.

This engine never writes to system paths.  It captures readable allow-listed
files into a private bundle and describes what a future privileged helper would
need to do. Boot-critical entries are always blocked from automatic restore.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_SNAPSHOT_FILE_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SNAPSHOT_ENTRIES = 256
ALLOWED_SYSTEM_PREFIXES = (
    Path("/etc"),
    Path("/usr/local"),
    Path("/var/lib"),
    # BC250's privileged helpers intentionally live outside ``/usr/local``.
    # Do not widen this to all of /usr/libexec: recovery evidence must remain
    # limited to the application's own reviewed runtime.
    Path("/usr/libexec/bc250-control-center"),
)
BOOT_CRITICAL_PREFIXES = (
    Path("/etc/default/grub"),
    Path("/etc/default/grub.d"),
    Path("/etc/kernel/cmdline"),
    Path("/etc/kernel/cmdline.d"),
    Path("/etc/mkinitcpio.conf"),
    Path("/boot"),
    Path("/efi"),
)

# A snapshot of a root-owned executable is useful forensic/recovery evidence,
# but it must never become an automatic way to reintroduce privileged code.
# A supervised operator should instead reinstall the reviewed application build
# and compare the exported snapshot first.  This also covers the historical
# NCT loader installed in /usr/local/sbin.
MANUAL_RESTORE_PREFIXES = (
    Path("/usr/local/sbin"),
    Path("/usr/libexec/bc250-control-center"),
)


def _within(path: Path, prefixes: tuple[Path, ...]) -> bool:
    absolute = Path(os.path.abspath(path))
    return any(absolute == prefix or absolute.is_relative_to(prefix) for prefix in prefixes)


def _digest_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 128 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_bounded_regular_with_metadata(path: Path, maximum: int) -> tuple[bytes, os.stat_result]:
    """Read one stable regular file without following a final symlink.

    The caller may have observed the path with ``lstat`` already.  Returning
    the descriptor metadata lets it prove that the bytes came from that same
    file rather than a replacement that appeared between observation and open.
    A second descriptor stat also rejects a file modified while it is read.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"Recovery file is not regular: {path.name}")
        if metadata.st_size > maximum:
            raise ValueError(f"Recovery file exceeds size limit: {path.name}")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(128 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum:
            raise ValueError(f"Recovery file exceeds size limit: {path.name}")
        after = os.fstat(descriptor)
        if _source_changed_during_copy(metadata, after, len(content)):
            raise ValueError(f"Recovery file changed while being read: {path.name}")
        return content, metadata
    finally:
        os.close(descriptor)


def _read_bounded_regular(path: Path, maximum: int) -> bytes:
    """Read stable bounded bytes when the caller does not need metadata."""
    content, _metadata = _read_bounded_regular_with_metadata(path, maximum)
    return content


def _portable_zip_info(name: str) -> zipfile.ZipInfo:
    """Return stable private-file metadata for a portable recovery archive."""
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _source_changed_during_copy(before: os.stat_result, after: os.stat_result, copied: int) -> bool:
    """Detect content or identity changes made while a snapshot was copied."""
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    return copied != after.st_size or any(
        getattr(before, field) != getattr(after, field) for field in stable_fields
    )


@dataclass(frozen=True)
class SnapshotEntry:
    source: str
    state: str
    backup: str = ""
    sha256: str = ""
    mode: int | None = None
    boot_critical: bool = False
    reason: str = ""


@dataclass(frozen=True)
class RestoreAction:
    source: str
    action: str
    automatic_allowed: bool
    reason: str


@dataclass(frozen=True)
class CurrentState:
    """Read-only comparison of one current path against snapshot evidence.

    This is intentionally observation, not a restore precondition that an
    executor may bypass.  A future privileged restore flow must require an
    explicit operator decision for every state other than the exact expected
    one.
    """

    source: str
    state: str
    matches_snapshot: bool
    reason: str = ""


@dataclass(frozen=True)
class RecoveryPlan:
    snapshot: str
    verified: bool
    actions: tuple[RestoreAction, ...]

    @property
    def blocked(self) -> bool:
        return not self.verified or any(not action.automatic_allowed for action in self.actions)


class RecoverySnapshotRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    @staticmethod
    def _validate_source(source: Path) -> Path:
        absolute = Path(os.path.abspath(source))
        if not _within(absolute, ALLOWED_SYSTEM_PREFIXES):
            raise ValueError(f"Snapshot source is outside the system allow-list: {absolute}")
        return absolute

    def capture(self, sources: list[str | Path], *, label: str = "system") -> Path:
        if len(sources) > MAX_SNAPSHOT_ENTRIES:
            raise ValueError("Recovery snapshot contains too many source paths")
        if self.root.is_symlink():
            raise ValueError("Recovery snapshot root must not be a symbolic link")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(label)).strip(".-")[:64]
        safe_label = safe_label or "system"
        staging = Path(tempfile.mkdtemp(prefix=".capture-", dir=self.root))
        staging.chmod(0o700)
        published: Path | None = None
        try:
            files = staging / "files"
            files.mkdir(mode=0o700)
            entries: list[SnapshotEntry] = []
            seen: set[str] = set()
            for raw_source in sources:
                source = self._validate_source(Path(raw_source))
                if str(source) in seen:
                    continue
                seen.add(str(source))
                boot_critical = _within(source, BOOT_CRITICAL_PREFIXES)
                entries.append(self._capture_entry(
                    source, files, len(entries), boot_critical=boot_critical
                ))
            payload = {
                "schema": 1,
                "created_at": time.time(),
                "label": safe_label,
                "entries": [asdict(entry) for entry in entries],
            }
            self._write_manifest(staging / "manifest.json", payload)
            _fsync_directory(files)
            _fsync_directory(staging)
            stamp = time.time_ns()
            snapshot = self.root / f"{stamp}-{safe_label}"
            collision = 0
            while snapshot.exists():
                collision += 1
                if collision > 100:
                    raise FileExistsError("Could not allocate a unique recovery snapshot identifier")
                snapshot = self.root / f"{stamp + collision}-{safe_label}"
            staging.rename(snapshot)
            published = snapshot
            _fsync_directory(self.root)
            return snapshot
        except Exception:
            shutil.rmtree(published or staging, ignore_errors=True)
            raise

    @staticmethod
    def _capture_entry(
        source: Path, files: Path, index: int, *, boot_critical: bool
    ) -> SnapshotEntry:
        try:
            observed = source.lstat()
        except OSError as error:
            return SnapshotEntry(
                str(source), "missing", boot_critical=boot_critical, reason=str(error)
            )
        if stat.S_ISLNK(observed.st_mode):
            return SnapshotEntry(
                str(source), "unsupported", boot_critical=boot_critical,
                reason="symbolic links are not followed",
            )
        if not stat.S_ISREG(observed.st_mode):
            return SnapshotEntry(
                str(source), "unsupported", boot_critical=boot_critical,
                reason="not a regular file",
            )
        if observed.st_size > MAX_SNAPSHOT_FILE_BYTES:
            return SnapshotEntry(
                str(source), "unsupported", boot_critical=boot_critical,
                reason="file exceeds snapshot size limit",
            )
        relative = Path(f"{index:04d}-{source.name}")
        backup = files / relative
        try:
            digest, mode = RecoverySnapshotRepository._copy_stable_source(
                source, backup, observed
            )
        except (OSError, ValueError) as error:
            backup.unlink(missing_ok=True)
            return SnapshotEntry(
                str(source), "unreadable", boot_critical=boot_critical,
                reason=str(error),
            )
        return SnapshotEntry(
            source=str(source), state="captured",
            backup=str(Path("files") / relative), sha256=digest, mode=mode,
            boot_critical=boot_critical,
        )

    @staticmethod
    def _copy_stable_source(
        source: Path, backup: Path, observed: os.stat_result
    ) -> tuple[str, int]:
        read_flags = (
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        write_flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        source_fd = os.open(source, read_flags)
        backup_fd = -1
        try:
            opened = os.fstat(source_fd)
            if not stat.S_ISREG(opened.st_mode):
                raise OSError("source changed and is no longer a regular file")
            if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
                raise OSError("source changed before snapshot capture")
            if opened.st_size > MAX_SNAPSHOT_FILE_BYTES:
                raise OSError("source exceeds snapshot size limit")
            backup_fd = os.open(backup, write_flags, 0o600)
            if not stat.S_ISREG(os.fstat(backup_fd).st_mode):
                raise OSError("snapshot backup is not a regular file")
            digest = hashlib.sha256()
            copied = 0
            while chunk := os.read(source_fd, 128 * 1024):
                copied += len(chunk)
                if copied > MAX_SNAPSHOT_FILE_BYTES:
                    raise ValueError("source grew beyond snapshot size limit")
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(backup_fd, view)
                    if written <= 0:
                        raise OSError("snapshot backup write made no progress")
                    view = view[written:]
            after = os.fstat(source_fd)
            if _source_changed_during_copy(opened, after, copied):
                raise OSError("source changed during snapshot capture")
            os.fsync(backup_fd)
            return digest.hexdigest(), opened.st_mode & 0o7777
        finally:
            if backup_fd >= 0:
                os.close(backup_fd)
            os.close(source_fd)

    @staticmethod
    def _write_manifest(path: Path, payload: dict) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _manifest_document(snapshot: str | Path) -> tuple[Path, dict]:
        root = Path(snapshot)
        manifest = root / "manifest.json"
        if root.is_symlink() or not root.is_dir() or manifest.is_symlink():
            raise ValueError("Recovery snapshot and manifest must not be symbolic links")
        try:
            payload = json.loads(
                _read_bounded_regular(manifest, MAX_MANIFEST_BYTES).decode("utf-8")
            )
        except UnicodeDecodeError as error:
            raise ValueError("Recovery manifest is not valid UTF-8") from error
        if not isinstance(payload, dict):
            raise ValueError("Recovery manifest root must be an object")
        if payload.get("schema") != 1 or not isinstance(payload.get("entries"), list):
            raise ValueError("Unsupported or malformed recovery snapshot")
        if len(payload["entries"]) > MAX_SNAPSHOT_ENTRIES:
            raise ValueError("Recovery snapshot contains too many entries")
        if any(not isinstance(entry, dict) for entry in payload["entries"]):
            raise ValueError("Recovery snapshot entry is malformed")
        label = payload.get("label")
        created_at = payload.get("created_at")
        if not isinstance(label, str) or not label.strip() or len(label) > 64:
            raise ValueError("Recovery snapshot label is malformed")
        if (
            isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not math.isfinite(float(created_at))
        ):
            raise ValueError("Recovery snapshot timestamp is malformed")
        return root, payload

    @classmethod
    def metadata(cls, snapshot: str | Path) -> dict[str, object]:
        _root, payload = cls._manifest_document(snapshot)
        label = payload["label"]
        created_at = payload["created_at"]
        return {"label": label, "created_at": float(created_at)}

    @classmethod
    def load(cls, snapshot: str | Path) -> tuple[SnapshotEntry, ...]:
        root, payload = cls._manifest_document(snapshot)
        entries = tuple(SnapshotEntry(**entry) for entry in payload["entries"])
        sources: set[str] = set()
        backups: set[str] = set()
        for entry in entries:
            RecoverySnapshotRepository._validate_entry(root, entry)
            if entry.source in sources:
                raise ValueError("Recovery snapshot contains a duplicate source")
            sources.add(entry.source)
            if entry.backup:
                if entry.backup in backups:
                    raise ValueError("Recovery snapshot contains a duplicate backup")
                backups.add(entry.backup)
        return entries

    @staticmethod
    def _validate_entry(root: Path, entry: SnapshotEntry) -> None:
        source = Path(entry.source)
        if not source.is_absolute() or not _within(source, ALLOWED_SYSTEM_PREFIXES):
            raise ValueError("Recovery entry source is outside the system allow-list")
        if entry.state not in {"captured", "missing", "unsupported", "unreadable"}:
            raise ValueError("Recovery entry has an unsupported state")
        expected_boot_critical = _within(source, BOOT_CRITICAL_PREFIXES)
        if bool(entry.boot_critical) != expected_boot_critical:
            raise ValueError("Recovery entry boot-critical classification was modified")
        if entry.state != "captured":
            if entry.backup or entry.sha256 or entry.mode is not None:
                raise ValueError("Non-captured recovery entry contains backup metadata")
            return
        backup = Path(entry.backup)
        if backup.is_absolute() or not entry.backup or ".." in backup.parts:
            raise ValueError("Recovery backup path is unsafe")
        # Capture emits one regular backup directly below ``files/``.  Do not
        # accept a deeper path from a modified manifest: a symlink in an
        # intermediate component could otherwise redirect verification/export
        # outside the snapshot even though the final open uses O_NOFOLLOW.
        if backup.parent != Path("files"):
            raise ValueError("Recovery backup path has an unexpected layout")
        backup_path = Path(os.path.abspath(root / backup))
        files_root = Path(os.path.abspath(root / "files"))
        try:
            files_metadata = (root / "files").lstat()
        except OSError as error:
            raise ValueError("Recovery files directory is unavailable") from error
        if stat.S_ISLNK(files_metadata.st_mode) or not stat.S_ISDIR(files_metadata.st_mode):
            raise ValueError("Recovery files directory must be a real directory")
        if not backup_path.is_relative_to(files_root):
            raise ValueError("Recovery backup escaped the snapshot files directory")
        digest = entry.sha256.lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Recovery backup digest is malformed")
        if isinstance(entry.mode, bool) or not isinstance(entry.mode, int) or not 0 <= entry.mode <= 0o7777:
            raise ValueError("Recovery entry mode is malformed")

    @classmethod
    def verify(cls, snapshot: str | Path) -> bool:
        root = Path(snapshot)
        try:
            entries = cls.load(root)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False
        for entry in entries:
            if entry.state != "captured":
                continue
            backup = root / entry.backup
            descriptor = -1
            try:
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                descriptor = os.open(backup, flags)
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_size > MAX_SNAPSHOT_FILE_BYTES
                    or _digest_descriptor(descriptor) != entry.sha256
                ):
                    return False
            except OSError:
                return False
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        return True

    @classmethod
    def build_restore_plan(cls, snapshot: str | Path) -> RecoveryPlan:
        root = Path(snapshot)
        verified = cls.verify(root)
        try:
            entries = cls.load(root)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            entries = ()
        actions: list[RestoreAction] = []
        for entry in entries:
            if entry.state == "captured":
                action = "restore-file"
                reason = "restore exact verified bytes and recorded mode"
            elif entry.state == "missing":
                action = "remove-if-created"
                reason = "path did not exist when the snapshot was captured"
            else:
                action = "manual-review"
                reason = entry.reason or "entry could not be captured safely"
            privileged_runtime = _within(
                Path(entry.source), MANUAL_RESTORE_PREFIXES
            )
            automatic_allowed = (
                verified
                and entry.state in {"captured", "missing"}
                and not entry.boot_critical
                and not privileged_runtime
            )
            if entry.boot_critical:
                reason = "boot-critical restore requires a separately proven recovery path"
            elif privileged_runtime:
                reason = (
                    "root-owned BC250 runtime restore requires reinstalling the "
                    "reviewed application build and supervised verification"
                )
            actions.append(RestoreAction(entry.source, action, automatic_allowed, reason))
        return RecoveryPlan(str(root), verified, tuple(actions))

    @classmethod
    def inspect_current_state(cls, snapshot: str | Path) -> tuple[CurrentState, ...]:
        """Compare allow-listed live paths with verified snapshot evidence.

        The method has no restore capability and never follows live symlinks.
        It gives a supervised recovery workflow the information needed to stop
        before overwriting a configuration modified after the snapshot.
        """

        root = Path(snapshot)
        if not cls.verify(root):
            raise ValueError("Recovery snapshot verification failed; live comparison refused")
        return tuple(cls._inspect_entry_current_state(entry) for entry in cls.load(root))

    @staticmethod
    def _inspect_entry_current_state(entry: SnapshotEntry) -> CurrentState:
        source = Path(entry.source)
        try:
            observed = source.lstat()
        except FileNotFoundError:
            if entry.state == "missing":
                return CurrentState(entry.source, "still-missing", True)
            return CurrentState(
                entry.source, "missing-since-snapshot", False,
                "the captured source no longer exists",
            )
        except OSError as error:
            return CurrentState(entry.source, "unavailable", False, str(error))

        if entry.state == "missing":
            return CurrentState(
                entry.source, "created-since-snapshot", False,
                "the path did not exist when the snapshot was captured",
            )
        if entry.state != "captured":
            return CurrentState(
                entry.source, "not-comparable", False,
                "the original path was not captured as a regular file",
            )
        if stat.S_ISLNK(observed.st_mode):
            return CurrentState(
                entry.source, "unsafe-symbolic-link", False,
                "live symbolic links are never followed during recovery inspection",
            )
        if not stat.S_ISREG(observed.st_mode):
            return CurrentState(
                entry.source, "not-regular", False,
                "live path is no longer a regular file",
            )
        try:
            content, opened = _read_bounded_regular_with_metadata(
                source, MAX_SNAPSHOT_FILE_BYTES
            )
        except (OSError, ValueError) as error:
            state = (
                "changed-during-inspection"
                if "changed while being read" in str(error)
                else "unavailable"
            )
            return CurrentState(entry.source, state, False, str(error))
        if _source_changed_during_copy(observed, opened, opened.st_size):
            return CurrentState(
                entry.source, "changed-during-inspection", False,
                "live path changed before its contents could be safely inspected",
            )
        content_matches = hashlib.sha256(content).hexdigest() == entry.sha256
        mode_matches = (observed.st_mode & 0o7777) == entry.mode
        if content_matches and mode_matches:
            return CurrentState(entry.source, "unchanged", True)
        changed = []
        if not content_matches:
            changed.append("content")
        if not mode_matches:
            changed.append("mode")
        return CurrentState(
            entry.source, "changed-since-snapshot", False,
            "live " + " and ".join(changed) + " differs from the snapshot",
        )

    @classmethod
    def export_portable_bundle(
        cls, snapshot: str | Path, destination: str | Path
    ) -> dict[str, object]:
        """Export verified evidence without enabling or executing restoration."""
        root = Path(snapshot)
        plan = cls.build_restore_plan(root)
        if not plan.verified:
            raise ValueError("Recovery snapshot verification failed; export refused")
        entries = cls.load(root)
        if tuple(action.source for action in plan.actions) != tuple(
            entry.source for entry in entries
        ):
            raise ValueError("Recovery snapshot changed while preparing export")

        target = Path(destination)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Recovery export destination already exists: {target}")
        parent = target.parent
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError("Recovery export parent must be an existing real directory")

        metadata = cls.metadata(root)
        manifest = {
            "schema": 1,
            "snapshot_id": root.name,
            "label": metadata["label"],
            "created_at": metadata["created_at"],
            "entries": [asdict(entry) for entry in entries],
        }
        restore_plan = {
            "schema": 1,
            "verified_at_export": True,
            "automatic_restore_enabled": False,
            "blocked": plan.blocked,
            "actions": [asdict(action) for action in plan.actions],
        }
        readme = (
            "BC250 Control Center portable recovery evidence\n\n"
            "This archive does not contain an automatic restore executable.\n"
            "Verify manifest.json and RESTORE_PLAN.json before supervised recovery.\n"
            "Boot-critical entries require proven offline recovery and must not be\n"
            "restored automatically. Captured files retain their original source,\n"
            "mode and SHA-256 in manifest.json.\n"
        ).encode("utf-8")

        descriptor, temporary_name = tempfile.mkstemp(prefix=".bc250-recovery-", dir=parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        temporary.chmod(0o600)
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                archive.writestr(
                    _portable_zip_info("manifest.json"),
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
                )
                archive.writestr(
                    _portable_zip_info("RESTORE_PLAN.json"),
                    json.dumps(restore_plan, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
                )
                archive.writestr(_portable_zip_info("README.txt"), readme)
                for entry in entries:
                    if entry.state != "captured":
                        continue
                    content = _read_bounded_regular(root / entry.backup, MAX_SNAPSHOT_FILE_BYTES)
                    if hashlib.sha256(content).hexdigest() != entry.sha256:
                        raise ValueError("Recovery backup changed while preparing export")
                    archive.writestr(_portable_zip_info(entry.backup), content)
            with zipfile.ZipFile(temporary, "r") as archive:
                if archive.testzip() is not None:
                    raise ValueError("Portable recovery archive verification failed")
            archive_fd = os.open(
                temporary,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(archive_fd)
                digest = _digest_descriptor(archive_fd)
            finally:
                os.close(archive_fd)
            os.link(temporary, target, follow_symlinks=False)
            _fsync_directory(parent)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "path": str(target),
            "sha256": digest,
            "entries": len(entries),
            "captured_files": sum(entry.state == "captured" for entry in entries),
            "automatic_restore_enabled": False,
            "boot_critical": sum(entry.boot_critical for entry in entries),
        }
