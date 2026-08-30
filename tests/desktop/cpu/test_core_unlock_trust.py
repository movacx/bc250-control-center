import runpy
from pathlib import Path

from bc250cc.infrastructure.core_unlock_trust import (
    REVIEWED_REVISION,
    REVIEWED_SCRIPT_SHA256,
    payload_matches_review,
)
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged" / "helpers" / "bc250-core-unlock-helper"


def test_packaged_helper_and_unprivileged_ui_share_exact_trust_anchors():
    namespace = runpy.run_path(str(HELPER))
    assert namespace["REVIEWED_REVISION"] == REVIEWED_REVISION
    assert namespace["REVIEWED_SCRIPT_SHA256"] == REVIEWED_SCRIPT_SHA256
    assert EXTERNAL_TOOLS["core_unlock"].reviewed_revision == REVIEWED_REVISION


def test_local_remote_ref_cannot_authorize_a_different_commit():
    reviewed_payload = b"reviewed payload"
    assert not payload_matches_review("f" * 40, reviewed_payload, reviewed_payload)


def test_pinned_commit_still_requires_the_independent_payload_digest():
    forged_payload = b"different payload"
    assert not payload_matches_review(REVIEWED_REVISION, forged_payload, forged_payload)


def test_worktree_and_git_object_must_be_byte_identical():
    assert not payload_matches_review(REVIEWED_REVISION, b"working", b"committed")
