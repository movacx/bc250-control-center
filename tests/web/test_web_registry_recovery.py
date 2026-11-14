"""Remote access must come back after a power cut.

Seen on the maintainer's board (2026-11-13): after forced restarts the
browser-session registry was a 0-byte file, and every press of "Start web
access" died in the server's first lines on ``json.loads("")``. The desktop
only said "did not start", because the server's output went to /dev/null.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import web_control, web_devices, web_pairing
from bc250cc.shared.errors import ActionNeeded


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    monkeypatch.setattr(web_pairing, "app_config_dir", lambda: tmp_path)
    return tmp_path


def test_an_empty_registry_left_by_a_power_cut_reads_as_no_sessions(config):
    (config / "web-devices.json").write_text("")
    assert web_devices.devices() == []


def test_a_corrupt_registry_is_set_aside_and_nobody_stays_signed_in(config):
    (config / "web-devices.json").write_text('{"half-written": {"id": ')
    assert web_devices.devices() == []
    kept = list(config.glob("web-devices.json.corrupt-*"))
    assert len(kept) == 1 and kept[0].read_text().startswith('{"half-written"')


def test_a_registry_that_is_not_a_mapping_fails_closed(config):
    (config / "web-devices.json").write_text("[1, 2, 3]")
    assert web_devices.devices() == []


def test_registry_writes_are_synced_before_and_after_the_rename(config, monkeypatch):
    synced: list = []
    real_fsync = web_devices.os.fsync
    monkeypatch.setattr(web_devices.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))
    web_devices.register("token", "192.0.2.1", "browser", 600)
    assert len(synced) >= 2  # the new file, then its directory
    data = json.loads((config / "web-devices.json").read_text())
    assert len(data) == 1


def test_the_pairing_store_writes_durably_too(config, monkeypatch):
    calls: list = []
    monkeypatch.setattr(web_pairing, "write_durably", lambda *args: calls.append(args))
    web_pairing.issue()
    assert calls and calls[0][1] == config / "web-pairing.json"


def test_a_server_that_dies_on_start_says_why(tmp_path, monkeypatch):
    log = tmp_path / "web-server.log"
    monkeypatch.setattr(web_control, "server_log_path", lambda: log)
    monkeypatch.setattr(web_control, "_listening", lambda _port: False)
    monkeypatch.setattr(web_control, "_command", lambda: ["python"])
    monkeypatch.setattr(web_control, "access_key", lambda: "ABCD-EFGH")
    monkeypatch.setattr(web_control, "autostart_state", lambda: {"enabled": False})

    def died(*_args, stdout=None, **_kwargs):
        stdout.write("Traceback (most recent call last):\n  ...\n"
                     "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)\n")
        stdout.flush()
        return SimpleNamespace(poll=lambda: 1)

    monkeypatch.setattr(web_control.subprocess, "Popen", died)
    with pytest.raises(ActionNeeded) as raised:
        web_control.start()
    # Plain words for the owner; the technical cause stays in the log.
    assert str(raised.value) == web_control.START_FAILED
    assert "JSONDecodeError: Expecting value" in log.read_text()
    assert "[Control Center]" in log.read_text()


def test_a_server_that_binds_then_dies_is_not_reported_as_started(tmp_path, monkeypatch):
    monkeypatch.setattr(web_control, "server_log_path", lambda: tmp_path / "web-server.log")
    monkeypatch.setattr(web_control, "_listening", lambda _port: True)
    monkeypatch.setattr(web_control, "_command", lambda: ["python"])
    monkeypatch.setattr(web_control, "access_key", lambda: "ABCD-EFGH")
    monkeypatch.setattr(web_control, "autostart_state", lambda: {"enabled": False})
    states = iter([None, 1, 1, 1])
    # First check: the port is already open, but start() checked _listening
    # once before launching, so make that first call say "not yet".
    listening = iter([False, True, True, True])
    monkeypatch.setattr(web_control, "_listening", lambda _port: next(listening, True))
    monkeypatch.setattr(
        web_control.subprocess, "Popen",
        lambda *a, **k: SimpleNamespace(poll=lambda: next(states, 1), terminate=lambda: None),
    )
    with pytest.raises(ActionNeeded, match="could not start"):
        web_control.start()
