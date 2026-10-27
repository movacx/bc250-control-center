"""The dashboard says what the installed tools need, once, and only when true.

Every notice comes from a state the inventory is certain of. A missing answer
(no inventory yet, no helpers installed at all, a workflow halfway through)
is never turned into a notice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bc250cc.infrastructure import privileged_install_state as helpers_module
from bc250cc.infrastructure.privileged_install_state import privileged_install_state
from frontends.desktop.core import attention
from frontends.desktop.core.attention import attention_items
from frontends.desktop.core.state import DashboardState
from frontends.desktop.pages import dashboard as dashboard_module
from frontends.desktop.pages.dashboard import DashboardPage

HEALTHY = {
    "privileged_install": {"state": "current", "outdated": [], "checkout": False},
    "prepare_components": {
        "runtime": {"available": True, "installed": True},
        "umr": {"available": True, "installed": True},
        "cu_manager": {"available": True, "installed": True},
    },
    "is_steamos": False,
    "cu_privileged_backend_ready": True,
    "cu_steamos_umr_database_ready": False,
    "gfx1013_compute": {
        "reason_key": "bazzite-release-managed", "bazzite_async_state": "ready", "direct_installer_allowed": True,
    },
    "fsr4": {"installer_available": True, "state": "current"},
}


def _with(**changes) -> dict:
    tools = {key: dict(value) if isinstance(value, dict) else value for key, value in HEALTHY.items()}
    for key, value in changes.items():
        tools[key] = {**tools.get(key, {}), **value} if isinstance(value, dict) else value
    return tools


def _components(**installed) -> dict:
    base = {key: dict(value) for key, value in HEALTHY["prepare_components"].items()}
    for key, value in installed.items():
        base[key]["installed"] = value
    return {"prepare_components": base}


def _keys(tools) -> list[str]:
    return [item.key for item in attention_items(tools)]


# ------------------------------------------------------------------ the rules


def test_a_healthy_system_and_an_unread_inventory_say_nothing():
    assert _keys(HEALTHY) == []
    assert _keys({}) == []


def test_outdated_helpers_point_at_the_updater_or_the_installer():
    items = attention_items(_with(privileged_install={"state": "outdated", "outdated": ["x"]}))
    assert [item.key for item in items] == ["helpers-outdated"]
    assert "Settings › About › Update application" in items[0].message
    checkout = attention_items(
        _with(privileged_install={"state": "outdated", "outdated": ["x"], "checkout": True})
    )
    assert "scripts/install-local.sh" in checkout[0].message


def test_helpers_owned_by_a_package_point_at_the_package_manager():
    for checkout in (False, True):
        items = attention_items(_with(privileged_install={
            "state": "outdated", "outdated": ["x"], "checkout": checkout, "package": "bc250-control-center",
        }))
        assert [item.key for item in items] == ["helpers-outdated"]
        assert "bc250-control-center" in items[0].message
        assert "package manager" in items[0].message
        assert "install-local.sh" not in items[0].message


def test_unknown_helpers_are_not_outdated():
    assert _keys(_with(privileged_install={"state": "unknown"})) == []


def test_missing_base_dependencies_are_named():
    assert _keys(_with(prepare_components={"runtime": {"available": True, "installed": False}})) == [
        "runtime-missing"
    ]
    # Unavailable here, or not reported: nothing to ask for.
    assert _keys(_with(prepare_components={"runtime": {"available": False, "installed": False}})) == []
    assert _keys(_with(prepare_components={"runtime": {}})) == []


def test_missing_umr_or_manager_asks_for_the_preparation_card():
    both = attention_items(_with(**_components(umr=False, cu_manager=False)))
    assert [item.key for item in both] == ["cu-tools-missing"]
    assert "UMR database, 40CU manager" in both[0].message
    assert "Prepare selected" in both[0].message and "SteamOS" not in both[0].message
    only_manager = attention_items(_with(**_components(cu_manager=False)))
    assert [item.key for item in only_manager] == ["cu-tools-missing"]
    assert "UMR database" not in only_manager[0].message


def test_steamos_says_it_needs_its_own_backend():
    items = attention_items(_with(is_steamos=True, **_components(umr=False, cu_manager=False)))
    assert [item.key for item in items] == ["cu-tools-missing"]
    assert "SteamOS needs its own 40CU manager" in items[0].message


def test_an_unavailable_component_is_never_reported_missing():
    tools = _with(**_components(umr=False))
    tools["prepare_components"]["umr"]["available"] = False
    assert _keys(tools) == []


def test_base_dependencies_come_first():
    tools = _with(**_components(runtime=False, umr=False, cu_manager=False))
    assert _keys(tools) == ["runtime-missing"]


def test_installed_tools_with_a_broken_backend_ask_for_a_repair():
    items = attention_items(_with(cu_privileged_backend_ready=False))
    assert [item.key for item in items] == ["cu-tools-repair"]
    assert "40CU manager" in items[0].message
    steamos = attention_items(_with(is_steamos=True, cu_steamos_umr_database_ready=False))
    assert [item.key for item in steamos] == ["cu-tools-repair"]
    assert "UMR database" in steamos[0].message
    # The database check is SteamOS only: elsewhere it is always False.
    assert _keys(_with()) == []


def test_a_damaged_bazzite_driver_asks_for_a_repair_and_nothing_else_does():
    assert _keys(_with(gfx1013_compute={"bazzite_async_state": "invalid"})) == ["bazzite-async-invalid"]
    for fine in ("not-installed", "ready", "relogin-required", "active"):
        assert _keys(_with(gfx1013_compute={"bazzite_async_state": fine})) == []
    # Not on a kernel the release refuses: the button is disabled there.
    assert _keys(_with(gfx1013_compute={"bazzite_async_state": "invalid", "direct_installer_allowed": False})) == []
    # The same field outside Bazzite's route means nothing.
    other = _with(gfx1013_compute={"reason_key": "fedora-upstream-managed", "bazzite_async_state": "invalid"})
    assert _keys(other) == []


def test_a_damaged_steamos_radv_asks_for_a_repair():
    tools = _with(gfx1013_compute={
        "reason_key": "steamos-dedicated-backend",
        "steamos_external_radv_state": "invalid",
    })
    assert _keys(tools) == ["steamos-radv-invalid"]


def test_the_fsr4_client_repair_and_update():
    assert _keys(_with(fsr4={"state": "invalid"})) == ["fsr4-invalid"]
    update = attention_items(_with(fsr4={"state": "update-available"}))
    assert [item.key for item in update] == ["fsr4-update"] and update[0].tone == "blue"
    assert _keys(_with(fsr4={"state": "invalid", "installer_available": False})) == []


def test_an_older_cyan_of_control_centers_own_recommends_the_update():
    cyan = {"supported_gpu_governors": {"cyan-skillfish-governor-smu": {"detected": True, "active": True}}}
    notices = attention_items(_with(**cyan, cyan_runtime_update_available=True))
    assert [item.key for item in notices] == ["cyan-update"] and notices[0].tone == "blue"
    assert "Update / repair" in notices[0].message
    # Compatibility is a tab of Additional settings, not of the Dashboard.
    assert "Additional settings › Compatibility" in notices[0].message
    # Current, or not installed at all: nothing to say.
    assert _keys(_with(**cyan, cyan_runtime_update_available=False)) == []
    assert _keys(_with(cyan_runtime_update_available=True)) == []


# ------------------------------------------------------------- helper probe


def _tree(root: Path, files: dict[str, bytes]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


@pytest.fixture
def two_helpers(monkeypatch):
    monkeypatch.setattr(helpers_module, "HELPERS", ("bc250-a-helper", "bc250-b-helper"))
    monkeypatch.setattr(helpers_module, "LIBRARIES", ("common.py",))


def test_identical_helpers_are_current(tmp_path, two_helpers):
    files = {"a": b"one", "b": b"two", "lib": b"three"}
    _tree(tmp_path / "app/privileged", {
        "helpers/bc250-a-helper": files["a"], "helpers/bc250-b-helper": files["b"], "lib/common.py": files["lib"],
    })
    _tree(tmp_path / "libexec", {"bc250-a-helper": files["a"], "bc250-b-helper": files["b"], "lib/common.py": files["lib"]})
    state = privileged_install_state(tmp_path / "app", tmp_path / "libexec")
    assert state == {"state": "current", "outdated": [], "checkout": False, "package": ""}


def test_a_changed_or_missing_helper_is_outdated(tmp_path, two_helpers):
    _tree(tmp_path / "app/privileged", {
        "helpers/bc250-a-helper": b"new", "helpers/bc250-b-helper": b"two", "lib/common.py": b"lib",
    })
    (tmp_path / "app/.git").mkdir()
    _tree(tmp_path / "libexec", {"bc250-a-helper": b"old", "lib/common.py": b"lib"})
    state = privileged_install_state(tmp_path / "app", tmp_path / "libexec")
    assert state["state"] == "outdated" and state["checkout"] is True
    assert state["outdated"] == ["bc250-a-helper", "bc250-b-helper"]


def test_outdated_helpers_name_the_package_that_owns_them(tmp_path, two_helpers, monkeypatch):
    _tree(tmp_path / "app/privileged", {"helpers/bc250-a-helper": b"new", "lib/common.py": b"lib"})
    _tree(tmp_path / "libexec", {"bc250-a-helper": b"old", "lib/common.py": b"lib"})
    asked = []
    monkeypatch.setattr(helpers_module, "owning_package", lambda path: asked.append(path) or "bc250-control-center")
    state = privileged_install_state(tmp_path / "app", tmp_path / "libexec")
    assert state["package"] == "bc250-control-center"
    assert asked == [tmp_path / "libexec/bc250-a-helper"]
    # Current helpers never ask a package manager anything.
    asked.clear()
    _tree(tmp_path / "libexec", {"bc250-a-helper": b"new"})
    assert privileged_install_state(tmp_path / "app", tmp_path / "libexec")["package"] == "" and not asked


def test_no_package_manager_means_no_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers_module.shutil, "which", lambda name: None)
    assert helpers_module.owning_package(tmp_path / "x") == ""


def test_no_installed_helpers_is_unknown_not_outdated(tmp_path, two_helpers):
    _tree(tmp_path / "app/privileged", {"helpers/bc250-a-helper": b"x", "lib/common.py": b"y"})
    state = privileged_install_state(tmp_path / "app", tmp_path / "libexec")
    assert state["state"] == "unknown" and state["outdated"] == []


# ------------------------------------------------------------------ dashboard


class _Controller:
    pass


@pytest.fixture
def page(qtbot, monkeypatch):
    shown = []
    monkeypatch.setattr(
        dashboard_module, "show_toast", lambda anchor, title, message, tone: shown.append((title, message, tone))
    )
    page = DashboardPage(_Controller())
    qtbot.addWidget(page)
    page.show()
    page.shown = shown
    return page


def _outdated_state() -> DashboardState:
    return DashboardState(preparation_tools=_with(privileged_install={"state": "outdated", "outdated": ["x"]}))


def test_the_dashboard_shows_a_notice_once_per_session(page):
    page.apply_state(_outdated_state())
    page.apply_state(_outdated_state())
    title, message, tone = page.shown[0]
    assert len(page.shown) == 1 and title == attention.HELPERS_TITLE and tone == "orange"
    assert message.startswith("They belong to another version")


def test_a_hidden_dashboard_keeps_the_notice_for_later(page):
    page.hide()
    page.apply_state(_outdated_state())
    assert page.shown == []
    page.show()
    page.apply_state(_outdated_state())
    assert len(page.shown) == 1


def test_nothing_is_announced_while_a_workflow_runs(page, monkeypatch):
    class Watch:
        pending = 1

    monkeypatch.setattr(page.window(), "workflow_watch", Watch(), raising=False)
    page.apply_state(_outdated_state())
    assert page.shown == []
    Watch.pending = 0
    page.apply_state(_outdated_state())
    assert len(page.shown) == 1


# ------------------------------------------------------ Bazzite reboot pending


def test_bazzite_packages_waiting_for_a_reboot_ask_for_a_restart_and_a_second_preparation():
    items = attention_items(_with(bazzite_reboot_pending={"pending": True, "packages": ["dkms"]}))
    assert [item.key for item in items] == ["bazzite-reboot-pending"]
    assert items[0].title == attention.REBOOT_TITLE
    assert "Prepare BC250 system" in items[0].message and "Prepare selected" in items[0].message
    assert _keys(_with(bazzite_reboot_pending={"pending": False, "packages": []})) == []


def test_parts_that_arrive_with_the_reboot_are_not_asked_for_before_it():
    tools = _with(
        bazzite_reboot_pending={"pending": True, "packages": ["umr"]},
        **_components(runtime=False, umr=False, cu_manager=False),
    )
    assert _keys(tools) == ["bazzite-reboot-pending"]


def test_nothing_is_announced_over_the_welcome_screen_or_the_tour(page, monkeypatch):
    window = page.window()
    monkeypatch.setattr(window, "_first_run_pending", True, raising=False)
    page.apply_state(_outdated_state())
    assert page.shown == []
    monkeypatch.setattr(window, "_first_run_pending", False, raising=False)
    presenting = [True]
    monkeypatch.setattr(window, "is_presenting_overlay", lambda: presenting[0], raising=False)
    page.apply_state(_outdated_state())
    assert page.shown == []
    # The window asks again once the first steps end.
    presenting[0] = False
    page.announce_pending_attention()
    assert len(page.shown) == 1


def test_a_gpu_without_its_driver_is_said_first():
    # Two reports: amdgpu failed at boot and every GPU page showed errors
    # that hid it.
    items = attention_items(_with(gpu_driver={"present": True, "bound": False, "driver": ""}))
    assert items[0].key == "gpu-driver-missing" and items[0].tone == "red"
    assert not any(item.key == "gpu-driver-missing" for item in attention_items(
        _with(gpu_driver={"present": True, "bound": True, "driver": "amdgpu"})
    ))
