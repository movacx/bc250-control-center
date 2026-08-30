"""Portable, checksummed export/import bundles for user configuration."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import stat
import tempfile
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

BUNDLE_SCHEMA = 1
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_STRUCTURE_DEPTH = 12


class ProfileBundleError(ValueError):
    pass


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _checksum(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _validate_structure(value, *, depth=0) -> None:
    if depth > MAX_STRUCTURE_DEPTH:
        raise ProfileBundleError("Bundle structure is too deeply nested")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or key.startswith("__"):
                raise ProfileBundleError("Bundle contains an invalid key")
            _validate_structure(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_structure(item, depth=depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ProfileBundleError("Bundle contains a non-finite number")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ProfileBundleError("Bundle contains an unsupported value")


def _reject_json_constant(value: str):
    raise ProfileBundleError(f"Bundle contains unsupported JSON constant: {value}")


def _read_bounded_regular_file(source: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as error:
        raise ProfileBundleError(f"Profile bundle could not be opened safely: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProfileBundleError("Profile bundle must be a regular file")
        if metadata.st_size > MAX_BUNDLE_BYTES:
            raise ProfileBundleError("Profile bundle exceeds the size limit")
        chunks: list[bytes] = []
        remaining = MAX_BUNDLE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        encoded = b"".join(chunks)
        if len(encoded) > MAX_BUNDLE_BYTES:
            raise ProfileBundleError("Profile bundle exceeds the size limit")
        return encoded
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class BundlePreview:
    source: str
    schema: int
    config_keys: tuple[str, ...]
    profile_sections: tuple[str, ...]
    checksum: str


class ProfileBundleRepository:
    def __init__(self, configuration):
        self.configuration = configuration

    def export(self, destination: str | Path) -> Path:
        destination = Path(destination)
        payload = {
            "schema": BUNDLE_SCHEMA,
            "application": "bc250-control-center",
            "exported_at": time.time(),
            "config": self.configuration.leer_config(),
            "profiles": self.configuration.leer_perfiles(),
        }
        _validate_structure(payload)
        document = dict(payload)
        document["sha256"] = _checksum(payload)
        encoded = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
        if len(encoded) > MAX_BUNDLE_BYTES:
            raise ProfileBundleError("Export exceeds the profile bundle size limit")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @staticmethod
    def _load(source: str | Path) -> tuple[Path, dict]:
        source = Path(source)
        try:
            encoded = _read_bounded_regular_file(source)
            document = json.loads(
                encoded.decode("utf-8"), parse_constant=_reject_json_constant
            )
        except ProfileBundleError:
            raise
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ProfileBundleError(f"Profile bundle could not be read: {error}") from error
        if not isinstance(document, dict):
            raise ProfileBundleError("Profile bundle root must be an object")
        supplied = document.pop("sha256", "")
        if document.get("schema") != BUNDLE_SCHEMA or document.get("application") != "bc250-control-center":
            raise ProfileBundleError("Unsupported profile bundle schema or application")
        if not isinstance(document.get("config"), dict) or not isinstance(document.get("profiles"), dict):
            raise ProfileBundleError("Profile bundle is missing configuration sections")
        _validate_structure(document)
        expected = _checksum(document)
        if not supplied or not hmac.compare_digest(str(supplied), expected):
            raise ProfileBundleError("Profile bundle checksum does not match")
        return source, document

    def preview(self, source: str | Path) -> BundlePreview:
        source, payload = self._load(source)
        return BundlePreview(
            source=str(source),
            schema=payload["schema"],
            config_keys=tuple(sorted(payload["config"])),
            profile_sections=tuple(sorted(payload["profiles"])),
            checksum=_checksum(payload),
        )

    def import_bundle(self, source: str | Path) -> Path:
        """Import both files transactionally and return the pre-import backup."""
        _source, payload = self._load(source)
        old_config = deepcopy(self.configuration.leer_config())
        old_profiles = deepcopy(self.configuration.leer_perfiles())
        backup_dir = Path(self.configuration.config_path()).parent / "backups"
        if backup_dir.is_symlink():
            raise ProfileBundleError("Profile backup directory cannot be a symbolic link")
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if backup_dir.is_symlink() or not backup_dir.is_dir():
            raise ProfileBundleError("Profile backup directory must be a real directory")
        backup_dir.chmod(0o700)
        backup = backup_dir / f"profile-before-import-{time.time_ns()}.json"
        self.export(backup)
        try:
            self.configuration.guardar_config_completa(payload["config"])
            self.configuration.guardar_perfiles(payload["profiles"])
        except Exception as import_error:
            rollback_errors = []
            try:
                self.configuration.guardar_config_completa(old_config)
            except Exception as error:
                rollback_errors.append(f"config: {error}")
            try:
                self.configuration.guardar_perfiles(old_profiles)
            except Exception as error:
                rollback_errors.append(f"profiles: {error}")
            if rollback_errors:
                raise ProfileBundleError(
                    "Profile import failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from import_error
            raise
        return backup
