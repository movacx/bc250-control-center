"""Guards that keep failure reporting diagnosable.

These tests exist because the interface used to print bare numbers such as
"code 43": the privileged helpers exited with statuses 20-57 while the terminal
explained only 13 unrelated ones. Nothing failed when the two drifted apart, so
the drift stayed invisible until a user hit it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.shared import error_catalog

HELPERS = Path("privileged/helpers")
QUICK_ACCESS_HELPER = HELPERS / "bc250-quick-access-helper"

# Every fail(..., <status>) call, whatever shape its message takes. Matching
# only the literal "PREFIX: ..." form missed status 10, whose message arrives
# through a variable — exactly the kind of gap this test exists to catch.
_FAIL_WITH_STATUS = re.compile(r"fail\(.*?,\s*(\d+)\s*\)", re.S)
# `int(value, 10)` and friends also end in ", 10)"; only count real fail calls.
_FAIL_CALL = re.compile(r"\bfail\(")


def _statuses_in(source: str) -> set[int]:
    statuses: set[int] = set()
    lines = source.splitlines()
    for line_number, line in enumerate(lines):
        if not _FAIL_CALL.search(line):
            continue
        # A fail() call may span lines; join the next few to find its status.
        window = "\n".join(lines[line_number:line_number + 8])
        match = _FAIL_WITH_STATUS.search(window)
        if match:
            statuses.add(int(match.group(1)))
    return statuses


def _helper_files() -> list[Path]:
    return sorted(path for path in HELPERS.glob("bc250-*") if path.is_file())


def test_every_status_a_helper_emits_is_explained() -> None:
    """No helper may exit with a status the catalog cannot explain.

    Checking only the Quick Access helper once hid 27 unmapped statuses in the
    SteamOS game helper — including 43, the number that started this work.
    """
    known = error_catalog.known_exit_statuses()
    unexplained = {
        path.name: sorted(_statuses_in(path.read_text(encoding="utf-8", errors="replace")) - known)
        for path in _helper_files()
    }
    offenders = {name: codes for name, codes in unexplained.items() if codes}
    assert not offenders, (
        "these helper exit statuses have no catalog entry, so the interface "
        f"would print the bare number: {offenders}"
    )


def test_success_never_reports_an_exit_code(tmp_path: Path) -> None:
    """A successful run is not a diagnosis; it must not print a status."""
    wrapped = workflow_wrapper("true", tmp_path / "status", tmp_path / "log")
    result = subprocess.run(
        ["/usr/bin/bash", "-c", wrapped],
        input="\n", capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "Completed" in result.stdout
    assert "exit code" not in result.stdout.lower()
    assert "Diagnostic code" not in result.stdout


@pytest.mark.parametrize(
    ("status", "code"),
    (
        (22, "BC250-DBUS-001"),
        (51, "BC250-CPU-001"),
        (124, "BC250-TIMEOUT-001"),
        # The status that prompted this whole refactor: it means "CPU
        # frequency must be between 3500 and 4200 MHz", and used to reach the
        # user as the bare number 43.
        (43, "BC250-RANGE-001"),
    ),
)
def test_helper_statuses_resolve_to_their_diagnostic(
    tmp_path: Path, status: int, code: str
) -> None:
    """Statuses the helpers really emit explain themselves in the terminal."""
    wrapped = workflow_wrapper(f"exit {status}", tmp_path / "s", tmp_path / "l")
    result = subprocess.run(
        ["/usr/bin/bash", "-c", wrapped],
        input="\n", capture_output=True, text=True, check=False,
    )
    assert result.returncode == status
    assert f"Diagnostic code: {code}" in result.stdout
    assert "What happened:" in result.stdout
    assert "How to fix it:" in result.stdout


def test_catalog_identifiers_are_unique_and_well_formed() -> None:
    codes = [entry.code for entry in error_catalog.all_codes()]
    assert len(codes) == len(set(codes)), "duplicate diagnostic identifier"
    pattern = re.compile(r"^BC250-[A-Z]+-\d{3}$")
    assert [code for code in codes if not pattern.match(code)] == []


def test_no_two_entries_claim_the_same_exit_status() -> None:
    """One status must map to one diagnosis, or the mapping is ambiguous."""
    seen: dict[int, str] = {}
    for entry in error_catalog.all_codes():
        for status in entry.exit_statuses:
            assert status not in seen, (
                f"status {status} claimed by both {seen[status]} and {entry.code}"
            )
            seen[status] = entry.code


def test_every_entry_offers_a_next_step() -> None:
    """A diagnosis without an action leaves the user stuck."""
    for entry in error_catalog.all_codes():
        assert entry.summary.strip(), f"{entry.code} has no summary"
        assert entry.cause.strip(), f"{entry.code} has no cause"
        assert entry.action.strip(), f"{entry.code} has no action"


DECKY_PLUGIN = Path("integrations/decky/bc250-quick-access/src/index.tsx")


def test_quick_access_panel_uses_the_same_identifiers() -> None:
    """Game Mode and the Desktop must not invent separate ids.

    The panel used its own BC250-QAM-* scheme, so one fault was reported under
    two different codes depending on where the user hit it.
    """
    source = DECKY_PLUGIN.read_text(encoding="utf-8")
    assert "BC250-QAM-" not in source, "the panel reintroduced a private id scheme"
    used = set(re.findall(r'"(BC250-[A-Z]+-\d{3})"', source))
    unknown = sorted(used - set(error_catalog.BY_CODE))
    assert not unknown, f"panel reports ids the catalog does not define: {unknown}"


def _run_workflow(tmp_path: Path, script: str) -> str:
    wrapped = workflow_wrapper(script, tmp_path / "s", tmp_path / "l")
    return subprocess.run(
        ["/usr/bin/bash", "-c", wrapped],
        input="\n", capture_output=True, text=True, check=False,
    ).stdout


def test_a_workflows_own_error_wins_over_a_status_guess(tmp_path: Path) -> None:
    """Our scripts name the exact kernel or package; a rule cannot.

    Status 43 maps to BC250-RANGE-001, which once answered a "kernel headers
    do not match" failure with "the requested value is outside the supported
    range" — contradicting the script the user had just read.
    """
    output = _run_workflow(tmp_path, (
        "echo '[ERROR] PWM installation stopped because kernel and headers do not match.'; "
        "echo '[ERROR] Install headers for exactly: 7.2.3-1.87-cachyos-bc250'; "
        "exit 43"
    ))
    assert "kernel and headers do not match" in output
    assert "Install headers for exactly: 7.2.3-1.87-cachyos-bc250" in output
    assert "BC250-WORKFLOW-001" in output
    # The misleading rule must not appear at all.
    assert "BC250-RANGE-001" not in output
    assert "outside the supported range" not in output


def test_third_party_output_still_uses_the_catalog(tmp_path: Path) -> None:
    """Only our own bracketed [ERROR] lines count as a self-explanation.

    pacman writes lowercase "error:"; treating that as an explanation would
    throw away a rule that says something more useful than the raw line.
    """
    output = _run_workflow(tmp_path, (
        "echo \"error: failed retrieving file 'x.db' from github.com : "
        "The requested URL returned error: 404\"; exit 1"
    ))
    assert "BC250-UPSTREAM-404" in output
    assert "BC250-WORKFLOW-001" not in output
