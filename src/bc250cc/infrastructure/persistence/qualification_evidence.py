"""Strict, read-only validation for supervised hardware qualification evidence.

Evidence can prove that the release checklist is complete and internally
consistent.  It cannot prove that the physical observations are truthful, so
this module never grants a hardware-qualified or public-release state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from bc250cc.shared.version import __version__

SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1 << 20
MAX_ARTIFACT_BYTES = 64 << 20
MAX_BUNDLE_BYTES = 128 << 20
MAX_BUNDLE_UNCOMPRESSED_BYTES = 192 << 20
MAX_BUNDLE_MEMBERS = 256
BUNDLE_MANIFEST = "qualification.json"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROOT_KEYS = frozenset({
    "schema", "section", "source_version", "board_id", "installation_id",
    "operator", "started_at", "finished_at", "independent_reproduction",
    "checks",
})
_CHECK_KEYS = frozenset({"requirement", "status", "artifacts", "notes"})
_ARTIFACT_KEYS = frozenset({"path", "sha256"})
_STATUSES = frozenset({"passed", "failed", "skipped"})


class QualificationEvidenceError(ValueError):
    """Raised when an evidence manifest is unsafe, malformed or incomplete."""


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QualificationEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise QualificationEvidenceError("evidence manifest must be a regular non-symlink file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_MANIFEST_BYTES:
        raise QualificationEvidenceError("evidence manifest size is invalid")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QualificationEvidenceError("evidence manifest is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise QualificationEvidenceError("evidence manifest root must be an object")
    return payload


def _exact_keys(value: Mapping[str, object], expected: frozenset[str], context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise QualificationEvidenceError(
            f"{context} keys mismatch; missing={missing}, unknown={unknown}"
        )


def _identifier(value: object, name: str) -> str:
    text = value if isinstance(value, str) else ""
    if not _IDENTIFIER.fullmatch(text):
        raise QualificationEvidenceError(f"{name} is invalid")
    return text


def _timestamp(value: object, name: str) -> datetime:
    text = value if isinstance(value, str) else ""
    if not text.endswith("Z"):
        raise QualificationEvidenceError(f"{name} must be an RFC3339 UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise QualificationEvidenceError(f"{name} is invalid") from error


def _artifact(path: Path, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QualificationEvidenceError("artifact must be an object")
    _exact_keys(value, _ARTIFACT_KEYS, "artifact")
    relative = value["path"] if isinstance(value["path"], str) else ""
    requested_hash = value["sha256"] if isinstance(value["sha256"], str) else ""
    candidate = Path(relative)
    if (
        not relative or relative == BUNDLE_MANIFEST or "\\" in relative
        or candidate.is_absolute() or ".." in candidate.parts
    ):
        raise QualificationEvidenceError("artifact path must be relative and contained")
    if not _SHA256.fullmatch(requested_hash):
        raise QualificationEvidenceError("artifact sha256 is invalid")
    root = path.parent.resolve()
    joined = root / candidate
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise QualificationEvidenceError(
                f"artifact path contains a symbolic link: {relative}"
            )
    artifact = joined.resolve()
    try:
        artifact.relative_to(root)
    except ValueError as error:
        raise QualificationEvidenceError("artifact path escapes the evidence directory") from error
    if not artifact.is_file():
        raise QualificationEvidenceError(f"artifact is missing or not a regular file: {relative}")
    size = artifact.stat().st_size
    if size <= 0 or size > MAX_ARTIFACT_BYTES:
        raise QualificationEvidenceError(f"artifact exceeds the validation size limit: {relative}")
    digest = hashlib.sha256()
    with artifact.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != requested_hash:
        raise QualificationEvidenceError(f"artifact hash mismatch: {relative}")
    return {"path": relative, "sha256": requested_hash, "bytes": size}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _bounded_bundle_members(bundle: Path) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]]:
    if bundle.is_symlink() or not bundle.is_file():
        raise QualificationEvidenceError("qualification bundle must be a regular non-symlink file")
    size = bundle.stat().st_size
    if size <= 0 or size > MAX_BUNDLE_BYTES:
        raise QualificationEvidenceError("qualification bundle size is invalid")
    try:
        archive = zipfile.ZipFile(bundle, "r")
        infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise QualificationEvidenceError("qualification bundle is not a valid ZIP") from error
    try:
        if not infos or len(infos) > MAX_BUNDLE_MEMBERS:
            raise QualificationEvidenceError("qualification bundle member count is invalid")
        members: dict[str, zipfile.ZipInfo] = {}
        total = 0
        for info in infos:
            name = info.filename
            candidate = PurePosixPath(name)
            mode = info.external_attr >> 16
            if (
                not name or "\\" in name or info.is_dir() or candidate.is_absolute()
                or ".." in candidate.parts or stat.S_ISLNK(mode)
                or bool(mode & 0o111) or bool(info.flag_bits & 0x1)
                or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise QualificationEvidenceError(f"unsafe qualification bundle member: {name}")
            if name in members:
                raise QualificationEvidenceError(f"duplicate qualification bundle member: {name}")
            limit = MAX_MANIFEST_BYTES if name == BUNDLE_MANIFEST else MAX_ARTIFACT_BYTES
            if info.file_size <= 0 or info.file_size > limit:
                raise QualificationEvidenceError(f"qualification bundle member size is invalid: {name}")
            total += info.file_size
            if total > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                raise QualificationEvidenceError("qualification bundle expands beyond the size limit")
            members[name] = info
        if BUNDLE_MANIFEST not in members:
            raise QualificationEvidenceError("qualification bundle manifest is missing")
        return archive, members
    except Exception:
        archive.close()
        raise


def qualification_template(
    section: str,
    requirements: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    """Return a non-writing template for one supervised qualification section."""
    if section not in requirements:
        raise QualificationEvidenceError(f"unknown qualification section: {section}")
    return {
        "schema": SCHEMA_VERSION,
        "section": section,
        "source_version": __version__,
        "board_id": "replace-with-pseudonymous-board-id",
        "installation_id": "replace-with-installation-id",
        "operator": "replace-with-operator-id",
        "started_at": "YYYY-MM-DDTHH:MM:SSZ",
        "finished_at": "YYYY-MM-DDTHH:MM:SSZ",
        "independent_reproduction": False,
        "checks": [
            {
                "requirement": requirement,
                "status": "skipped",
                "artifacts": [],
                "notes": "",
            }
            for requirement in requirements[section]
        ],
    }


def validate_qualification_evidence(
    manifest: str | Path,
    requirements: Mapping[str, Sequence[str]],
    *,
    expected_version: str = __version__,
) -> dict[str, object]:
    """Validate one portable evidence manifest and every referenced artifact."""
    path = Path(manifest)
    payload = _read_json(path)
    _exact_keys(payload, _ROOT_KEYS, "manifest")
    if payload["schema"] != SCHEMA_VERSION:
        raise QualificationEvidenceError("unsupported qualification evidence schema")
    section = payload["section"] if isinstance(payload["section"], str) else ""
    if section not in requirements:
        raise QualificationEvidenceError("unknown qualification section")
    if payload["source_version"] != expected_version:
        raise QualificationEvidenceError(
            f"source version mismatch; expected {expected_version}"
        )
    board_id = _identifier(payload["board_id"], "board_id")
    installation_id = _identifier(payload["installation_id"], "installation_id")
    operator = _identifier(payload["operator"], "operator")
    if not isinstance(payload["independent_reproduction"], bool):
        raise QualificationEvidenceError("independent_reproduction must be boolean")
    started = _timestamp(payload["started_at"], "started_at")
    finished = _timestamp(payload["finished_at"], "finished_at")
    if finished < started:
        raise QualificationEvidenceError("finished_at precedes started_at")
    checks = payload["checks"]
    if not isinstance(checks, list):
        raise QualificationEvidenceError("checks must be an array")
    expected = tuple(requirements[section])
    observed: dict[str, dict[str, object]] = {}
    for raw_check in checks:
        if not isinstance(raw_check, dict):
            raise QualificationEvidenceError("check must be an object")
        _exact_keys(raw_check, _CHECK_KEYS, "check")
        requirement = raw_check["requirement"] if isinstance(raw_check["requirement"], str) else ""
        if requirement not in expected:
            raise QualificationEvidenceError(f"unknown requirement: {requirement}")
        if requirement in observed:
            raise QualificationEvidenceError(f"duplicate requirement: {requirement}")
        status = raw_check["status"] if isinstance(raw_check["status"], str) else ""
        if status not in _STATUSES:
            raise QualificationEvidenceError(f"invalid check status: {status}")
        notes = raw_check["notes"] if isinstance(raw_check["notes"], str) else None
        if notes is None or len(notes) > 4096:
            raise QualificationEvidenceError("check notes must be a bounded string")
        raw_artifacts = raw_check["artifacts"]
        if not isinstance(raw_artifacts, list):
            raise QualificationEvidenceError("check artifacts must be an array")
        artifacts = [_artifact(path, item) for item in raw_artifacts]
        if status == "passed" and not artifacts:
            raise QualificationEvidenceError(
                f"passed requirement has no hashed artifact: {requirement}"
            )
        observed[requirement] = {
            "requirement": requirement,
            "status": status,
            "artifacts": artifacts,
            "notes": notes,
        }
    missing = [item for item in expected if item not in observed]
    if missing:
        raise QualificationEvidenceError(f"missing requirements: {missing}")
    ordered = [observed[item] for item in expected]
    complete = all(item["status"] == "passed" for item in ordered)
    return {
        "path": str(path),
        "valid": True,
        "complete": complete,
        "section": section,
        "source_version": expected_version,
        "board_id": board_id,
        "installation_id": installation_id,
        "operator": operator,
        "started_at": payload["started_at"],
        "finished_at": payload["finished_at"],
        "independent_reproduction": payload["independent_reproduction"],
        "checks": ordered,
        "review_required": True,
        "grants_hardware_qualification": False,
    }


def validate_qualification_bundle(
    bundle: str | Path,
    requirements: Mapping[str, Sequence[str]],
    *,
    expected_version: str = __version__,
) -> dict[str, object]:
    """Validate a portable bundle without trusting archive paths or metadata."""
    bundle_path = Path(bundle)
    archive, members = _bounded_bundle_members(bundle_path)
    try:
        with tempfile.TemporaryDirectory(prefix="bc250-qualification-") as directory:
            root = Path(directory)
            for name, info in members.items():
                target = root.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                target.chmod(0o600)
            result = validate_qualification_evidence(
                root / BUNDLE_MANIFEST,
                requirements,
                expected_version=expected_version,
            )
            expected_members = {BUNDLE_MANIFEST}
            for check in result["checks"]:
                expected_members.update(
                    artifact["path"] for artifact in check["artifacts"]
                )
            extras = sorted(set(members) - expected_members)
            missing = sorted(expected_members - set(members))
            if extras or missing:
                raise QualificationEvidenceError(
                    f"qualification bundle contents mismatch; missing={missing}, unknown={extras}"
                )
    finally:
        archive.close()
    return {
        **result,
        "path": str(bundle_path),
        "format": "bc250-qualification-bundle-v1",
        "bundle_sha256": _file_sha256(bundle_path),
        "bundle_bytes": bundle_path.stat().st_size,
    }


def export_qualification_bundle(
    manifest: str | Path,
    destination: str | Path,
    requirements: Mapping[str, Sequence[str]],
    *,
    expected_version: str = __version__,
) -> dict[str, object]:
    """Atomically publish deterministic, non-executing qualification evidence."""
    manifest_path = Path(manifest)
    validated = validate_qualification_evidence(
        manifest_path, requirements, expected_version=expected_version
    )
    payload = _read_json(manifest_path)
    canonical_manifest = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    artifact_paths = sorted({
        str(artifact["path"])
        for check in validated["checks"]
        for artifact in check["artifacts"]
    })
    output = Path(destination)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"qualification bundle destination already exists: {output}")
    parent = output.parent
    if not parent.is_dir():
        raise QualificationEvidenceError("qualification bundle destination directory is missing")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".bc250-qualification-", suffix=".zip", dir=parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.chmod(0o600)
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            archive.writestr(_zip_info(BUNDLE_MANIFEST), canonical_manifest)
            for relative in artifact_paths:
                source = manifest_path.parent / relative
                with source.open("rb") as input_file, archive.open(
                    _zip_info(relative), "w"
                ) as output_file:
                    shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        with temporary.open("rb") as completed:
            os.fsync(completed.fileno())
        result = validate_qualification_bundle(
            temporary, requirements, expected_version=expected_version
        )
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise FileExistsError(
                f"qualification bundle destination already exists: {output}"
            ) from None
        temporary.unlink()
        try:
            directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        return {
            **result,
            "path": str(output),
            "bundle_sha256": _file_sha256(output),
            "bundle_bytes": output.stat().st_size,
            "private_mode": oct(stat.S_IMODE(output.stat().st_mode)),
            "automatic_actions": False,
        }
    finally:
        temporary.unlink(missing_ok=True)
