"""Memory monitoring uses the reviewed helper and preserves its readiness gates."""
import json
import os
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest

from frontends.web.actions import Invalid, gddr6_monitor
from frontends.web.gddr6 import readiness
from frontends.web.ssh import SSHSession


def status(**changes):
    return dict(hardware_detected=True, helper_ready=True, reader_ready=True,
                repository_ready=True, payload_present=True, firmware_supported=True,
                bios_version="P3.00", external={"state": ""}, **changes)


def test_monitor_calls_only_the_existing_helper_command_with_a_bounded_session():
    calls = []
    service = SimpleNamespace(estado_gddr6_memory_temp=status,
                              comando_monitorizar_vram=lambda seconds: ["protected-helper", "--seconds", str(seconds)])
    level, work = gddr6_monitor(SimpleNamespace(service=service), {}, calls.append)
    assert level == 2 and not calls
    work()
    assert calls == [["protected-helper", "--seconds", "600"]]


@pytest.mark.parametrize("changes", [{"firmware_supported": False}, {"governor_state": "starting"},
                                     {"external": {"state": "active"}}, {"external": {"state": "interrupted"}},
                                     {"repository_ready": False}, {"helper_ready": False}])
def test_blocked_monitor_never_builds_or_executes_a_hardware_command(changes):
    raw = status()
    raw.update(changes)
    calls = []
    service = SimpleNamespace(estado_gddr6_memory_temp=lambda: raw, comando_monitorizar_vram=calls.append)
    assert not readiness(service)["can_monitor"]
    _, work = gddr6_monitor(SimpleNamespace(service=service), {}, calls.append)
    with pytest.raises(Invalid):
        work()
    assert not calls


def test_kernel_sensor_path_keeps_the_existing_firmware_exception():
    raw = status()
    raw.update(kernel_driver=True, firmware_supported=False, repository_ready=False)
    assert readiness(SimpleNamespace(estado_gddr6_memory_temp=lambda: raw))["can_monitor"]


def test_browser_cannot_supply_a_manual_override_or_extend_the_session():
    for params in ({"ignore_governor": True}, {"seconds": 9999}):
        with pytest.raises(Invalid):
            gddr6_monitor(None, params, None)


def test_streaming_parser_keeps_partial_samples_and_never_parses_other_actions():
    received = []
    session = SSHSession.__new__(SSHSession)
    session._active, session._kind = True, "gddr6.monitor"
    session.job_console = SimpleNamespace(_feed=received.append)
    session._sample_buffer, session._sample, session._sample_at = b"", {}, 0
    sample = {"chips": [{"chip": 0, "temperature_c": 52.5}], "average_c": 52.5}
    data = json.dumps(sample).encode() + b"\r\n"
    session._feed(b"BC250 Linux password: " + data[:12])
    assert not session._sample
    session._feed(data[12:])
    assert session._sample == sample and time.monotonic() - session._sample_at < 1
    session._kind = "gpu.status"
    session._feed(b'{"chips":[]}\n')
    assert session._sample == sample


def test_sudo_passes_the_current_user_identity_to_legacy_memory_helpers(monkeypatch):
    from bc250cc.infrastructure import polkit_session as auth
    monkeypatch.setenv(auth.WEB_SUDO_AUTH_ENV, "1")
    monkeypatch.setattr(auth.os, "getuid", lambda: 1234)
    monkeypatch.setattr(auth.shutil, "which", lambda _: "/usr/bin/sudo")
    command = auth.pkexec_argv("pkexec", "/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper", "--action", "monitor")
    assert command == ["/usr/bin/sudo", "-p", "BC250 Linux password: ", "PKEXEC_UID=1234", "--",
                       "/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper", "--action", "monitor"]


@pytest.mark.parametrize("helper", ["bc250-gddr6-temp-helper", "bc250-gddr6-temp-reader"])
def test_native_sudo_parses_memory_identity_before_command_separator(monkeypatch, helper):
    """Exercise real sudo parsing as ourselves; never launch a hardware helper."""
    from bc250cc.infrastructure import polkit_session as auth

    printenv = shutil.which("printenv")
    if os.getuid() == 0 or not shutil.which("sudo") or not printenv:
        pytest.skip("Needs sudo and an ordinary user for a non-privileged parsing probe")
    monkeypatch.setenv(auth.WEB_SUDO_AUTH_ENV, "1")
    command = auth.pkexec_argv("pkexec", f"/usr/libexec/bc250-control-center/{helper}", "--help")
    helper_index = command.index(f"/usr/libexec/bc250-control-center/{helper}")
    # Retain the production auth prefix and assignment ordering, but explicitly
    # select our own UID and replace all helper arguments with a harmless read.
    probe = [command[0], "-n", "-u", f"#{os.getuid()}", *command[1:helper_index], printenv, "PKEXEC_UID"]
    result = subprocess.run(probe, capture_output=True, text=True, timeout=5, check=False)
    if result.returncode and any(reason in result.stderr.lower() for reason in (
        "password is required", "not allowed", "not permitted", "no new privileges",
    )):
        pytest.skip("Host sudo policy does not allow a non-interactive self-user probe")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(os.getuid())


def test_memory_identity_is_web_only_and_does_not_leak_to_other_helpers(monkeypatch):
    from bc250cc.infrastructure import polkit_session as auth

    monkeypatch.setenv(auth.WEB_SUDO_AUTH_ENV, "1")
    monkeypatch.setattr(auth.shutil, "which", lambda _: "/usr/bin/sudo")
    command = auth.pkexec_argv("pkexec", "/usr/libexec/protected-helper", "status", prepare_agent=False)
    assert not any(arg.startswith("PKEXEC_UID=") for arg in command)
    monkeypatch.delenv(auth.WEB_SUDO_AUTH_ENV)
    command = auth.pkexec_argv("pkexec", "/usr/libexec/bc250-gddr6-temp-helper", "--help", prepare_agent=False)
    assert command == ["pkexec", "--disable-internal-agent", "/usr/libexec/bc250-gddr6-temp-helper", "--help"]
