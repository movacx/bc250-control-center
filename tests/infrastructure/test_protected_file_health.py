import stat

import pytest

from bc250cc.infrastructure.protected_file_health import (
    ProtectedFileEvidence,
    evaluate_protected_file,
)


def evidence(mode=stat.S_IFREG | 0o755, uid=0, **updates):
    values = {"exists": True, "is_symlink": False, "mode": mode, "uid": uid}
    values.update(updates)
    return ProtectedFileEvidence(**values)


def test_root_owned_nonwritable_executable_helper_is_healthy():
    decision = evaluate_protected_file(evidence(), executable=True)

    assert decision.safe is True
    assert decision.reason == "protected"
    assert decision.mode_text == "0o755"


@pytest.mark.parametrize(
    ("value", "reason"),
    (
        (evidence(exists=False, mode=None), "missing"),
        (evidence(is_symlink=True), "symlink"),
        (evidence(mode=stat.S_IFDIR | 0o755), "not-regular"),
        (evidence(uid=1000), "not-root-owned"),
        (evidence(mode=stat.S_IFREG | 0o775), "group-or-world-writable"),
        (evidence(mode=stat.S_IFREG | 0o644), "not-executable"),
    ),
)
def test_helper_evidence_fails_closed_with_specific_reason(value, reason):
    decision = evaluate_protected_file(value, executable=True)

    assert decision.safe is False
    assert decision.reason == reason


def test_nonexecuting_payload_rejects_accidental_execute_bits():
    assert evaluate_protected_file(
        evidence(mode=stat.S_IFREG | 0o644), executable=False
    ).safe is True
    decision = evaluate_protected_file(
        evidence(mode=stat.S_IFREG | 0o755), executable=False
    )
    assert (decision.safe, decision.reason) == (False, "payload-executable")
