import pytest

from bc250cc.infrastructure.tool_inventory import (
    mark_component_installation,
    select_cu_backend,
)


def selection(**overrides):
    values = {
        "is_steamos": False,
        "standard_path": "/tools/standard/manager.sh",
        "standard_path_exists": True,
        "standard_backend": "standard",
        "standard_repository": "/tools/standard",
        "steamos_path": "/tools/steamos/manager.sh",
        "steamos_exists": False,
        "steamos_repository": "/tools/steamos",
        "expected_steamos_repository": "/expected/steamos",
    }
    values.update(overrides)
    return select_cu_backend(**values)


def test_standard_linux_selects_only_discovered_standard_manager():
    selected = selection()
    assert selected.backend == "standard"
    assert selected.manager == "/tools/standard/manager.sh"
    assert selected.exists is True
    assert selected.blocked is False
    assert selected.wrong_backend_present is False


def test_standard_linux_missing_manager_never_advertises_stale_path():
    selected = selection(standard_path_exists=False)
    assert selected.manager == ""
    assert selected.kind == ""
    assert selected.repository_path == ""
    assert selected.exists is False


def test_steamos_never_selects_winnielv_even_when_present():
    selected = selection(is_steamos=True)
    assert selected.backend == "steamos"
    assert selected.manager == ""
    assert selected.exists is False
    assert selected.blocked is True
    assert selected.wrong_backend_present is True
    assert "ignored" in selected.warning
    assert selected.repository_path == "/expected/steamos"


def test_steamos_selects_f5go_and_clears_warning():
    selected = selection(is_steamos=True, steamos_exists=True)
    assert selected.manager == "/tools/steamos/manager.sh"
    assert selected.kind == "F5GO/bc250-cu-live-manager-SteamOS"
    assert selected.repository_path == "/tools/steamos"
    assert selected.warning == ""
    assert selected.blocked is False


def test_steamos_compatible_global_backend_is_not_mislabeled_as_wrong():
    selected = selection(
        is_steamos=True, standard_backend="steamos", steamos_exists=False
    )
    assert selected.wrong_backend_present is False
    assert "ignored" not in selected.warning
    assert selected.manager == ""


@pytest.mark.parametrize("is_steamos", (False, True))
def test_no_discovery_evidence_never_produces_a_manager(is_steamos):
    selected = selection(
        is_steamos=is_steamos,
        standard_path="",
        standard_path_exists=False,
        standard_backend="unknown",
        steamos_path="",
        steamos_exists=False,
        steamos_repository="",
    )
    assert selected.manager == ""
    assert selected.exists is False


def test_component_overlay_copies_input_and_ignores_unknown_keys():
    original = {
        "runtime": {"supported": True},
        "umr": {"supported": False, "installed": False},
    }
    result = mark_component_installation(
        original, {"runtime": True, "umr": True, "invented": True}
    )
    assert result["runtime"]["installed"] is True
    assert result["umr"]["installed"] is True
    assert "invented" not in result
    assert "installed" not in original["runtime"]
    assert original["umr"]["installed"] is False
