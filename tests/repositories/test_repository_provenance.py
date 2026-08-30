import pytest

from bc250cc.infrastructure.repository_provenance import (
    GitProvenanceEvidence,
    ProvenanceState,
    classify_archive_provenance,
    classify_git_provenance,
    read_bounded_text,
)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"origin_ok": False}, ProvenanceState.ORIGIN_INVALID),
        ({"connectivity_ok": False}, ProvenanceState.CONNECTIVITY_INVALID),
        ({"revision_ok": False}, ProvenanceState.REVISION_INVALID),
        ({"status_readable": False}, ProvenanceState.STATUS_UNREADABLE),
        ({"dirty": True}, ProvenanceState.DIRTY),
        ({}, ProvenanceState.VERIFIED),
    ],
)
def test_git_provenance_classifies_each_state(changes, expected):
    values = {
        "origin_ok": True,
        "connectivity_ok": True,
        "revision_required": True,
        "revision_ok": True,
        "status_readable": True,
        "dirty": False,
    }
    values.update(changes)

    assert classify_git_provenance(GitProvenanceEvidence(**values)) is expected


def test_git_provenance_uses_security_evidence_precedence():
    evidence = GitProvenanceEvidence(
        origin_ok=False,
        connectivity_ok=False,
        revision_required=True,
        revision_ok=False,
        status_readable=False,
        dirty=True,
    )

    assert classify_git_provenance(evidence) is ProvenanceState.ORIGIN_INVALID


def test_git_provenance_ignores_revision_when_none_is_required():
    evidence = GitProvenanceEvidence(
        origin_ok=True,
        connectivity_ok=True,
        revision_required=False,
        revision_ok=False,
        status_readable=True,
        dirty=False,
    )

    assert classify_git_provenance(evidence) is ProvenanceState.VERIFIED


@pytest.mark.parametrize(
    ("origin_ok", "revision_required", "revision_ok", "expected"),
    [
        (False, True, False, ProvenanceState.ARCHIVE_ORIGIN_INVALID),
        (True, True, False, ProvenanceState.ARCHIVE_REVISION_INVALID),
        (True, True, True, ProvenanceState.ARCHIVE_VERIFIED),
        (True, False, False, ProvenanceState.ARCHIVE_VERIFIED),
    ],
)
def test_archive_provenance_states(
    origin_ok, revision_required, revision_ok, expected
):
    assert classify_archive_provenance(
        origin_ok=origin_ok,
        revision_required=revision_required,
        revision_ok=revision_ok,
    ) is expected


def test_bounded_text_reader_accepts_a_small_regular_utf8_file(tmp_path):
    marker = tmp_path / "source"
    marker.write_text("official\n", encoding="utf-8")

    assert read_bounded_text(marker) == "official\n"


def test_bounded_text_reader_rejects_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("official", encoding="utf-8")
    marker = tmp_path / "source"
    marker.symlink_to(target)

    with pytest.raises(OSError):
        read_bounded_text(marker)


def test_bounded_text_reader_rejects_oversize_and_invalid_utf8(tmp_path):
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"a" * 5)
    invalid = tmp_path / "invalid"
    invalid.write_bytes(b"\xff")

    with pytest.raises(ValueError, match="size limit"):
        read_bounded_text(oversized, maximum=4)
    with pytest.raises(UnicodeError):
        read_bounded_text(invalid)
