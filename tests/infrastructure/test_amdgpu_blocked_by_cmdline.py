"""A kernel started with nomodeset has no BC-250 GPU to drive.

R-26b082c7 and R-6cecd644 came from one Fedora 45 board booted with
``nomodeset vga=791`` (left by Fedora's basic-graphics install). The hardware
video build failed with "render node was not found" and the Cyan governor
with a bare systemd "Dependency failed"; neither named the kernel option.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import gpu_repository, vaapi_video
from bc250cc.infrastructure.hardware_identity import (
    amdgpu_blocked_by_cmdline,
    amdgpu_blocked_message,
)
from bc250cc.shared.errors import ActionNeeded


@pytest.mark.parametrize(
    ("cmdline", "option"),
    [
        ("ro nomodeset vga=791 rhgb quiet", "nomodeset"),
        ("quiet amdgpu.modeset=0", "amdgpu.modeset=0"),
        ("quiet modprobe.blacklist=nouveau,amdgpu", "modprobe.blacklist=nouveau,amdgpu"),
        ("module_blacklist=amdgpu", "module_blacklist=amdgpu"),
        ("ro quiet splash amdgpu.ppfeaturemask=0xffffffff", ""),
        ("ro quiet amdgpu.modeset=1 modprobe.blacklist=nouveau", ""),
        ("", ""),
    ],
)
def test_only_the_options_that_stop_amdgpu_are_named(cmdline, option):
    assert amdgpu_blocked_by_cmdline(cmdline) == option


def test_the_message_names_the_option_and_how_to_remove_it():
    message = amdgpu_blocked_message("nomodeset")
    assert "nomodeset" in message and "GRUB" in message and "Nothing was changed" in message


def test_the_video_driver_is_not_offered_under_nomodeset():
    ok, reason = vaapi_video.vaapi_supported(
        family="fedora", machine="x86_64", glibc=(2, 42), bc250=True,
        cmdline="ro nomodeset vga=791 rhgb quiet",
    )
    assert not ok and "nomodeset" in reason
    assert vaapi_video.vaapi_supported(
        family="fedora", machine="x86_64", glibc=(2, 42), bc250=True, cmdline="ro rhgb quiet",
    ) == (True, "")


@pytest.mark.parametrize("action", ["activar", "reiniciar"])
def test_starting_the_governor_under_nomodeset_stops_before_any_command(monkeypatch, action):
    repository = object.__new__(gpu_repository.GPURepository)
    monkeypatch.setattr(gpu_repository, "require_bc250_hardware", lambda: None)
    monkeypatch.setattr(
        gpu_repository, "detect_init_manager",
        lambda: SimpleNamespace(persistence_supported=True, kind="systemd", display_name="systemd"),
    )
    monkeypatch.setattr(gpu_repository, "amdgpu_blocked_by_cmdline", lambda: "nomodeset")
    monkeypatch.setattr(repository, "_selected_gpu_governor", lambda: gpu_repository.CYAN_GOVERNOR, raising=False)
    monkeypatch.setattr(repository, "_require_openrc_governor_preflight", lambda _selected: None, raising=False)
    monkeypatch.setattr(
        repository, "_abrir_terminal",
        lambda *_a, **_k: pytest.fail("no terminal may open"), raising=False,
    )
    with pytest.raises(ActionNeeded, match="nomodeset"):
        repository.controlar_governor(action)
