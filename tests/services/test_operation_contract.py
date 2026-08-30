from bc250cc.shared.operation_contract import (
    OperationExit,
    parse_operation_log,
    parse_result_line,
)


def test_structured_shell_result_round_trips_escaped_message():
    event = parse_result_line(
        r"BC250_RESULT status=ok component=runtime code=0 message=plan\ completed"
    )
    assert event is not None
    assert event.successful
    assert event.message == "plan completed"


def test_malformed_or_unrelated_lines_are_ignored():
    assert parse_result_line("pacman output") is None
    assert parse_result_line("BC250_RESULT status=ok") is None
    assert parse_result_line("BC250_RESULT status=error component=umr code=nope") is None
    assert parse_result_line("BC250_RESULT 'unterminated") is None


def test_log_report_preserves_multiple_component_results(tmp_path):
    log = tmp_path / "workflow.log"
    log.write_text(
        "noise\n"
        "BC250_RESULT status=ok component=runtime code=0 message=check\\ completed\n"
        "BC250_RESULT status=ok component=umr code=0 message=check\\ completed\n",
        encoding="utf-8",
    )
    report = parse_operation_log(log, exit_code=0)
    assert report.successful
    assert report.verified_success
    assert report.has_structured_evidence
    assert [event.component for event in report.events] == ["runtime", "umr"]


def test_failure_report_provides_conservative_next_action(tmp_path):
    report = parse_operation_log(tmp_path / "missing.log", exit_code=OperationExit.KERNEL_HEADERS)
    assert not report.successful
    assert "matching the running kernel" in report.safe_next_action


def test_unknown_failure_never_recommends_blind_retry(tmp_path):
    report = parse_operation_log(tmp_path / "missing.log", exit_code=199)
    assert "Inspect" in report.safe_next_action


def test_zero_exit_without_events_is_not_a_verified_system_operation(tmp_path):
    report = parse_operation_log(tmp_path / "legacy.log", exit_code=0)

    assert report.successful
    assert not report.verified_success
    assert not report.has_structured_evidence
    assert "without structured" in report.safe_next_action


def test_structured_component_failure_overrides_a_misleading_zero_exit(tmp_path):
    log = tmp_path / "workflow.log"
    log.write_text(
        "BC250_RESULT status=error component=umr code=32 message=missing\\ database\n",
        encoding="utf-8",
    )
    report = parse_operation_log(log, exit_code=0)

    assert not report.successful
    assert not report.verified_success
    assert [event.component for event in report.component_failures] == ["umr"]
    assert "component reported failure" in report.safe_next_action
