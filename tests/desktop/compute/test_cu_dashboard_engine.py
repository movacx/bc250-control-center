import inspect

from bc250cc.infrastructure.cu_dashboard import clean_dashboard, parse_dashboard
from bc250cc.infrastructure.cu_repository import CURepository

ROWS = ("SE0.SH0", "SE0.SH1", "SE1.SH0", "SE1.SH1")


def base_state():
    return {
        "available": False,
        "rows": [],
        "masks": [0x07] * 4,
        "driver_masks": [0x07] * 4,
        "active_cus": 24,
        "routed_wgps": 12,
        "service": "Not installed",
        "service_installed": False,
        "service_enabled": False,
        "boot_sync": "Not saved",
        "boot_sync_key": "not_saved",
        "driver_topology_available": False,
        "parse_error": "",
    }


def dashboard(row: str = "| SE0.SH0 | D+ | D+ | D+ | -- | -- | 0x07 | 0xfff80000 | 6/10 |"):
    rendered = []
    for name in ROWS:
        rendered.append(row.replace("SE0.SH0", name))
    return "\n".join(("Service: enabled", *rendered, "CUs active & routed: 24/40"))


def parse(text):
    return parse_dashboard(
        text, base_state=base_state(), row_names=ROWS,
        source="fixture", updated_at="12:00:00",
    )


def test_pure_parser_accepts_complete_consistent_topology():
    state = parse(dashboard())
    assert state["available"] is True
    assert state["active_cus"] == 24
    assert state["mode_key"] == "factory"
    assert state["service_enabled"] is True
    assert state["source"] == "fixture"
    assert state["fresh"] is False


def test_token_count_mismatch_fails_closed():
    state = parse(dashboard().replace("6/10", "10/10", 1))
    assert state["available"] is False
    assert "inconsistent tokens" in state["parse_error"]


def test_odd_total_and_incomplete_table_are_never_available():
    state = parse("CUs active & routed: 39/40")
    assert state["available"] is False
    assert "invalid active-CU total" in state["parse_error"]


def test_cleaner_removes_ansi_footer_and_blank_lines():
    assert clean_dashboard(
        "\x1b[31mService: enabled\x1b[0m\n\n== Process finished with exit code 0 ==\n"
    ) == "Service: enabled"


def test_parser_does_not_mutate_caller_fallback():
    fallback = base_state()
    result = parse_dashboard(
        dashboard(), base_state=fallback, row_names=ROWS,
        source="live", updated_at="12:00:00",
    )
    assert result is not fallback
    assert fallback["available"] is False
    assert fallback["rows"] == []


def test_repository_method_is_a_narrow_parser_delegate():
    source = inspect.getsource(CURepository.parsear_dashboard_cu)
    assert "parse_dashboard(" in source
    assert "re.search" not in source
    assert len(source.splitlines()) <= 9
