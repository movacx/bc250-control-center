"""What a problem report carries: the cause of a long log, nothing twice, nothing empty."""

from __future__ import annotations

from bc250cc.infrastructure import problem_report as reports


def test_a_long_log_keeps_its_start_its_errors_and_its_end():
    lines = ["== DirectMesh directmesh-v1.4 =="] + [f"[{n}/9000] Compiling C object src/file{n}.c.o" for n in range(9000)]
    lines[3000] = "FAILED: src/compiler/nir/x.c.o"
    lines[3001] = "../src/x.c:12:3: error: unknown type name 'foo'"
    lines.append("ninja: build stopped: subcommand failed.")
    log = reports.condense_log("\n".join(lines))
    assert len(log) < reports.LOG_LIMIT
    assert "directmesh-v1.4" in log and "unknown type name" in log and log.endswith("subcommand failed.")
    assert "lines cut" in log


def test_a_short_log_is_sent_as_it_is():
    assert reports.condense_log("one\ntwo") == "one\ntwo"


def test_the_reports_own_log_is_not_sent_twice_and_empty_sections_are_left_out():
    own = "\n".join(f"step number {n} of this workflow did run" for n in range(40))
    other = "\n".join(f"another workflow altogether, line {n}" for n in range(40))
    kept = dict(reports.without_repeats([
        ("Last workflow logs", f"[workflow-2.log]\n{own}\nBC250_CONTEXT {{}}\n\n[workflow-1.log]\n{other}"),
        ("Helper logs", "(no helper log)"),
        ("Black box", "—"),
        ("GPU", "card0: vendor 0x1002"),
    ], own))
    assert set(kept) == {"Last workflow logs", "GPU"}
    assert "another workflow" in kept["Last workflow logs"] and "step number" not in kept["Last workflow logs"]


def test_the_same_failure_on_the_same_version_is_recognised():
    sent = [{"id": "R-1", "kind": "problem", "summary": "HelixSR ·  install failed", "code": "X-1", "version": "1.2"}]
    assert reports.earlier_report("X-1", "HelixSR · install failed", "1.2", sent)["id"] == "R-1"
    assert reports.earlier_report("X-1", "HelixSR · install failed", "1.3", sent) is None
    assert reports.earlier_report("X-2", "HelixSR · install failed", "1.2", sent) is None


def test_recent_actions_list_successes_too(monkeypatch, tmp_path):
    from bc250cc.infrastructure import report_attachments as parts

    (tmp_path / "workflow-1.log").write_text(
        'x\nBC250_WORKFLOW exit_status=0 duration_seconds=4\nBC250_CONTEXT {"action": "Free /var space", "outcome": "completed"}\n')
    (tmp_path / "workflow-2.log").write_text("building\n")
    monkeypatch.setattr(parts.diag, "workflow_log_directory", lambda: tmp_path)
    text = parts._recent_actions()
    assert "Free /var space · completed · exit 0 after 4 s" in text and "interrupted" in text
