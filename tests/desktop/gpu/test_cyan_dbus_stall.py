"""A Cyan that runs but does not answer on D-Bus must not stall every refresh.

With gpu-usage.method = "process" and a Proton game open, Cyan's main loop
holds its governor lock almost all the time and the D-Bus thread never gets
it. Each property read then waited the full 2 s; five per refresh left the
dashboard showing "Not detected" and the GPU page "0–0 MHz", and every
action failed with a bare "D-Bus unavailable".
"""

from __future__ import annotations

import pytest

from bc250cc.infrastructure.governor_conflicts import CYAN_GOVERNOR
from bc250cc.infrastructure.sistema_repository import SistemaRepository

SPEC = {"binary": "cyan-skillfish-governor-smu", "service": "cyan-skillfish-governor-smu.service"}


@pytest.fixture
def repository(monkeypatch):
    repository = SistemaRepository.__new__(SistemaRepository)
    repository.calls = []
    repository.main_pid = "29122"
    repository.answers = "timeout"

    def run(command, timeout=2):
        repository.calls.append(command)
        if repository.answers == "timeout":
            return 1, "", f"Command {command!r} timed out after {timeout} seconds"
        return 0, "b true" if command[-1] == "Enabled" else "u 1500", ""

    monkeypatch.setattr(repository, "_ejecutar", run, raising=False)
    monkeypatch.setattr(repository, "_command_path", lambda binary: "/usr/local/bin/" + binary, raising=False)
    monkeypatch.setattr(
        repository,
        "_service_prop",
        lambda service, prop: repository.main_pid if prop == "MainPID" else "active",
        raising=False,
    )
    return repository


def _state(repository):
    return repository._governor_runtime_state(CYAN_GOVERNOR, SPEC, None)


def test_the_first_timeout_ends_the_reads_and_later_refreshes_wait(repository):
    state = _state(repository)
    assert len(repository.calls) == 1
    assert state["dbus_responsive"] is False
    assert state["current_min"] is None and state["allowed_max"] is None

    repository.calls.clear()
    assert _state(repository)["dbus_responsive"] is False
    assert repository.calls == []


def test_a_restarted_cyan_is_asked_again(repository):
    _state(repository)
    repository.calls.clear()
    repository.main_pid = "30001"
    repository.answers = "ok"
    state = _state(repository)
    assert state["dbus_responsive"] is True
    assert (state["current_min"], state["allowed_max"], state["dbus_performance"]) == (1500, 1500, True)
    assert len(repository.calls) == 5


def test_the_backoff_ends(repository, monkeypatch):
    _state(repository)
    stalled_pid, since = repository._cyan_dbus_stall
    repository._cyan_dbus_stall = (stalled_pid, since - repository._CYAN_DBUS_BACKOFF_SECONDS - 1)
    repository.calls.clear()
    repository.answers = "ok"
    assert _state(repository)["dbus_responsive"] is True


def test_a_failure_that_is_not_a_timeout_is_not_a_stall(repository, monkeypatch):
    monkeypatch.setattr(
        repository, "_ejecutar", lambda command, timeout=2: (1, "", "Unit not found."), raising=False
    )
    state = _state(repository)
    assert state["dbus_responsive"] is True
    assert state["current_min"] is None


def test_the_error_names_the_process_method_when_it_is_the_cause(repository, monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[gpu-usage]\nmethod = "process"\n[gpu]\nset-method = "smu"\n', encoding="utf-8")
    monkeypatch.setattr(repository, "_cyan_runtime_config_path", lambda *a, **k: config, raising=False)
    assert "busy-flag" in repository._cyan_dbus_unavailable_detail()
    config.write_text('[gpu-usage]\nmethod = "busy-flag"\n[gpu]\nset-method = "smu"\n', encoding="utf-8")
    assert repository._cyan_dbus_unavailable_detail() == ""


def test_the_gpu_screen_says_why_instead_of_zero_to_zero(qtbot):
    from frontends.desktop.pages.gpu_governor_view import GpuGovernorView, GpuViewState

    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.show()
    state = GpuViewState.from_backend(
        {"service_active": "active", "current_min": None, "current_max": None,
         "dbus_responsive": False, "cyan_telemetry": {"method": "process"}}
    )
    view.apply_state(state)

    tile = view._tiles["range"]
    assert tile.value.text() == "--"
    assert view._bus_notice.isVisible() and "busy-flag" in view._bus_notice.text()
    view._sync_compatibility(state)
    assert view._process_method_warning.isVisible()

    healthy = GpuViewState.from_backend(
        {"service_active": "active", "current_min": 1000, "current_max": 1850,
         "dbus_responsive": True, "cyan_telemetry": {"method": "busy-flag"}}
    )
    view.apply_state(healthy)
    view._sync_compatibility(healthy)
    assert tile.value.text() == "1000–1850 MHz"
    assert not view._bus_notice.isVisible()
    assert not view._process_method_warning.isVisible()
