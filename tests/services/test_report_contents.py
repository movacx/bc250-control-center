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


def test_a_report_drops_only_what_its_area_never_needs():
    from bc250cc.infrastructure import report_attachments as parts

    every = [(title, "x") for title, _read in (*parts.diag.SECTIONS, *parts.STATE_SECTIONS)]
    for code in ("BC250-GENERAL-001", "BC250-WORKFLOW-001", "BC250-GPU-001", "", "free text - with dashes - here"):
        assert parts.for_area(every, parts.report_area(code)) == every
    short = dict(parts.for_area(every, parts.report_area("BC250-UPSCALE-001")))
    assert "Kernel log (unfiltered)" not in short
    assert {"Last workflow logs", "Boot and deployments", "Application log", "GPU device", "Storage"} <= set(short)
    assert parts.report_area("BC250-UPSCALE-001", "also my fans stopped") == ""
    names = {title for title, _text in every}
    for area, dropped in parts.AREA_WITHOUT.items():
        assert dropped <= names, area


def test_unlock_attempts_keep_the_mask_chosen_and_the_mask_read(monkeypatch, tmp_path):
    from bc250cc.infrastructure import core_unlock_attempts as unlock

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    helper = ["pkexec", "helper", "--repo", "/x", "--reboot"]
    assert unlock.chosen_mask(helper) == "standard 0x77"
    assert unlock.chosen_mask([*helper, "--accept-mask", "0xb7"]) == "only 0xB7"
    assert unlock.chosen_mask(["bash", "-c", "rm -f x; exec helper --reboot --ignore-core-mask"]) == "any (check skipped)"
    assert unlock.chosen_mask(["bash", "-c", "rm -f x; exec helper --reboot"]) == "standard 0x77"
    for number in range(20):
        unlock.record_attempt("Unlock", chosen="standard 0x77", reported=0xB7, result=f"stopped (exit {number})")
    rows = unlock.recent_attempts()
    assert len(rows) == unlock.KEPT and "mask read: 0xB7" in rows[-1] and "exit 19" in rows[-1]
