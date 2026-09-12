"""A failure has to be diagnosed as what it is, not as what its number says.

Twelve helpers were written over time and each picked its own exit numbers, so
the same number came to mean different things in different helpers. That would
be harmless if nothing read the number — but ``error_catalog`` translates it
into the sentence the user is shown, and ``terminal_plan`` only falls back to
the number when the message carries no registered marker.

The result was a set of confident, wrong answers. ``CPU_BACKEND_UNTRUSTED``
("the installed BC250 CPU helper is unsafe") rendered as "a required program is
missing", which sends the user to prepare dependencies instead of repairing the
install. Four Compute Units verification failures rendered as "the interface and
protected helper are different versions", which tells the user to reinstall.
"Invalid gpu-voltage action" rendered as "the fan control path is unavailable".

The existing contract test checks that every status has *an* entry. It never
checked that the entry means the same thing as the message, which is why none
of this failed.

The fix is not renumbering: markers already take precedence over numbers, and
every one of those messages already carried a marker the catalog simply did not
know. So what is pinned here is that a helper's own words decide.
"""

from __future__ import annotations

import ast
import collections
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged" / "helpers"

sys.path.insert(0, str(ROOT / "src"))
from bc250cc.shared.error_catalog import (  # noqa: E402
    _CODES,
    for_exit_status,
    for_marker,
)

MARKER_RE = re.compile(r"^([A-Z][A-Z0-9_]{3,}):")

# Numbers whose meaning is genuinely shared and correct across helpers: a usage
# error is a usage error wherever it happens.
SHARED_BY_DESIGN = frozenset({2, 3, 10, 11, 124, 125})


def _failures() -> list[tuple[str, int, str]]:
    """Every ``fail(<literal>, <literal>)`` in every helper."""
    found: list[tuple[str, int, str]] = []
    if not HELPERS.is_dir():  # pragma: no cover - packaging layouts
        pytest.skip("privileged/helpers is not present in this checkout")
    for helper in sorted(HELPERS.iterdir()):
        if not helper.is_file() or helper.is_symlink() or helper.name == "README.md":
            continue
        try:
            tree = ast.parse(helper.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - not a Python helper
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "fail" or len(node.args) < 2:
                continue
            message, status = node.args[0], node.args[1]
            if not isinstance(status, ast.Constant) or not isinstance(status.value, int):
                continue
            if not isinstance(message, ast.Constant):
                continue
            found.append((helper.name, status.value, str(message.value)))
    return found


def _entry_for(message: str, status: int):
    """What the user will actually be shown.

    Resolved through the catalog's own functions rather than a reimplementation
    of them — the tie-break between overlapping markers (``QUICK_ACCESS_CU_SERVICE``
    is a prefix of ``QUICK_ACCESS_CU_SERVICE_VERIFY``) is longest-first, and a
    test that got that wrong would be testing itself.
    """
    return for_marker(message) or for_exit_status(status)


# ------------------------------------------------------------ the guard rails


def test_there_are_failures_to_check():
    """A guard that silently covers nothing is worse than none."""
    assert len(_failures()) >= 100


def test_every_failure_resolves_to_a_diagnosis():
    orphans = [
        f"{helper}: exit {status} — {message[:60]}"
        for helper, status, message in _failures()
        if _entry_for(message, status) is None
    ]
    assert orphans == [], "\n  ".join(orphans)


def test_an_ambiguous_number_never_decides_anything():
    """One number may cover several failures — if each names its own.

    Thirty-one statuses are shared between helpers and several are reused
    inside one helper. That is workable, because a marker outranks a number.
    What is not workable is a message with no marker sharing a number with a
    message that has one: the unmarked message then inherits whatever the
    number happens to mean, which is how "Invalid gpu-voltage action" came to
    be reported as an unavailable fan control path.
    """
    meanings: dict[tuple[str, int], set[str]] = collections.defaultdict(set)
    for helper, status, message in _failures():
        entry = _entry_for(message, status)
        if entry is not None:
            meanings[(helper, status)].add(entry.code)
    undecided = [
        f"{helper}: exit {status} means {sorted(meanings[(helper, status)])} "
        f"but this message names none of them — {message[:52]}"
        for helper, status, message in _failures()
        if status not in SHARED_BY_DESIGN
        and len(meanings[(helper, status)]) > 1
        and for_marker(message) is None
    ]
    assert undecided == [], "\n  ".join(undecided)


def test_every_marker_a_helper_prints_is_one_the_catalog_knows():
    """An unregistered marker is a message whose number silently wins.

    That is exactly how ``CPU_BACKEND_UNTRUSTED`` came to be reported as a
    missing program: the marker was printed, nothing recognised it, and exit 48
    resolved to a different failure entirely.
    """
    # A marker may be registered with its colon, to stop a short name matching
    # a longer sibling: ``QUICK_ACCESS_CU_SERVICE`` is a prefix of
    # ``QUICK_ACCESS_CU_SERVICE_VERIFY``.
    known = {marker.rstrip(":") for entry in _CODES for marker in entry.markers}
    unregistered: set[str] = set()
    for _helper, _status, message in _failures():
        match = MARKER_RE.match(message)
        if match and match.group(1) not in known:
            unregistered.add(match.group(1))
    # These three name *where* a request came from rather than what went wrong,
    # and each is used for both a platform mismatch and an authorization
    # refusal. Splitting them needs a catalog entry with new wording, which
    # costs thirty translations; their exit statuses resolve correctly today.
    allowed = {"GAME_MODE_CONTEXT", "CU_CONTEXT", "DAEMON_CONTEXT"}
    assert unregistered <= allowed, sorted(unregistered - allowed)


def test_the_allowlist_has_not_gone_stale():
    """When those three are registered, this test says so instead of rotting."""
    known = {marker.rstrip(":") for entry in _CODES for marker in entry.markers}
    printed: set[str] = set()
    for _helper, _status, message in _failures():
        match = MARKER_RE.match(message)
        if match:
            printed.add(match.group(1))
    for name in ("GAME_MODE_CONTEXT", "CU_CONTEXT", "DAEMON_CONTEXT"):
        assert name in printed or name in known, f"{name} is no longer used anywhere"


# ------------------------------------------- the specific faults that shipped


def test_an_untrusted_cpu_helper_is_reported_as_a_helper_problem():
    entry = _entry_for("CPU_BACKEND_UNTRUSTED: the installed BC250 CPU helper is unsafe.", 48)
    assert entry is not None and entry.code == "BC250-HELPER-001"


def test_a_compute_units_verification_failure_is_reported_as_one():
    for marker in (
        "QUICK_ACCESS_CU_STATE",
        "QUICK_ACCESS_CU_VERIFY",
        "QUICK_ACCESS_CU_SERVICE_PROFILE",
        "QUICK_ACCESS_CU_SERVICE_VERIFY",
    ):
        entry = _entry_for(f"{marker}: something", 33)
        assert entry is not None and entry.code == "BC250-CU-001", marker


def test_a_governor_conflict_is_not_reported_as_a_range_error():
    entry = _entry_for("QUICK_ACCESS_GPU_CONFLICT: Cyan and Oberon are both active.", 21)
    assert entry is not None and entry.code == "BC250-SERVICE-003"


def test_a_missing_governor_helper_is_not_reported_as_a_range_error():
    entry = _entry_for("QUICK_ACCESS_GPU_HELPER: the helper is missing.", 21)
    assert entry is not None and entry.code == "BC250-HELPER-001"


def test_an_invalid_oberon_yaml_is_reported_as_a_configuration_problem():
    entry = _entry_for("QUICK_ACCESS_GPU_CONFIG: the root-owned Oberon YAML is invalid.", 22)
    assert entry is not None and entry.code == "BC250-CONFIG-001"


def test_a_gpu_voltage_usage_error_is_not_reported_as_a_fan_fault():
    entry = _entry_for("HELPER_USAGE: Invalid gpu-voltage action.", 40)
    assert entry is not None and entry.code == "BC250-PROTOCOL-001"


def test_a_governor_request_error_is_not_reported_as_a_cpu_tuning_failure():
    for message, status in (
        ("HELPER_USAGE: governor-config expects an action.", 91),
        ("HELPER_USAGE: Invalid governor-config request.", 92),
        ("HELPER_USAGE: Invalid governor service restart request.", 94),
    ):
        entry = _entry_for(message, status)
        assert entry is not None and entry.code == "BC250-PROTOCOL-001", message


def test_an_untrusted_payload_is_not_reported_as_a_missing_program():
    entry = _entry_for(
        "HELPER_UNTRUSTED: Governor TOML editor is not a root-owned, non-writable installed payload.",
        31,
    )
    assert entry is not None and entry.code == "BC250-HELPER-001"
