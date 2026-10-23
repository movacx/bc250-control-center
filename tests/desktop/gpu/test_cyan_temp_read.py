"""Cyan's gpu-usage.temp-read: shown beside the other methods, sent only when read."""

from __future__ import annotations

from bc250cc.infrastructure.cyan_governor_runtime import binary_understands
from frontends.desktop.pages.gpu_governor_view import GpuGovernorView, GpuViewState


def test_the_panel_shows_and_sends_the_temperature_source(qtbot):
    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.apply_state(GpuViewState(temp_read="sysfs", temp_read_supported=True))

    assert view.temp_read_combo.currentData() == "sysfs"
    assert view.temp_read_combo.isEnabled()
    assert view.compatibility_options()["temp_read"] == "sysfs"


def test_an_older_cyan_gets_no_temperature_source(qtbot):
    """It would ignore the key, so the line is left as it is."""
    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.apply_state(GpuViewState(temp_read="drm", temp_read_supported=False))

    assert not view.temp_read_combo.isEnabled()
    assert view.compatibility_options()["temp_read"] is None
    view.temp_read_combo.open_options()  # disabled: no menu, no change
    assert view.temp_read_combo.currentData() == "drm"


def test_an_unknown_binary_leaves_the_choice_usable(qtbot):
    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.apply_state(GpuViewState(temp_read_supported=None))
    assert view.temp_read_combo.isEnabled()
    assert view.compatibility_options()["temp_read"] == "drm"


def test_support_is_read_from_the_binary_itself(tmp_path):
    new = tmp_path / "new"
    # Across a read boundary too: the key must not be missed when split.
    new.write_bytes(b"\0" * (1024 * 1024 - 4) + b"temp-read" + b"\0" * 32)
    old = tmp_path / "old"
    old.write_bytes(b"\0fix-freq\0method\0")

    assert binary_understands(new, "temp-read") is True
    assert binary_understands(old, "temp-read") is False
    assert binary_understands(tmp_path / "missing", "temp-read") is None


def test_the_repository_sends_it_last_and_only_when_chosen(monkeypatch):
    from bc250cc.infrastructure.gpu_repository import GPURepository

    calls = []
    repo = GPURepository.__new__(GPURepository)
    monkeypatch.setattr(repo, "_current_cyan_compatibility", lambda: ("smu", "busy-flag", True, False), raising=False)
    monkeypatch.setattr(repo, "_service_is_active", lambda _service: False, raising=False)
    monkeypatch.setattr(repo, "_editar_governor_toml", lambda *args: calls.append(args) or "ok", raising=False)

    repo.configurar_compatibilidad_gpu_cyan("smu", "busy-flag", True, False, "sysfs")
    repo.configurar_compatibilidad_gpu_cyan("smu", "busy-flag", True, False)

    assert calls[0] == ("set-cyan-compatibility", "smu", "busy-flag", True, False, "sysfs")
    assert calls[1] == ("set-cyan-compatibility", "smu", "busy-flag", True, False)
