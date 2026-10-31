"""Network switches must not silently kill a working web endpoint."""
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import web_control
from bc250cc.shared.errors import ActionNeeded


def test_missing_runtime_is_detected_before_stopping_or_changing_network(monkeypatch):
    web_control.save_settings(lan=True, tls=True)
    monkeypatch.setattr(web_control, "_listening", lambda _port: True)
    monkeypatch.setattr(web_control, "_command", lambda: (_ for _ in ()).throw(ActionNeeded("missing runtime")))
    monkeypatch.setattr(web_control, "stop", lambda: pytest.fail("Must not stop before preflight"))
    with pytest.raises(ActionNeeded, match="missing runtime"):
        web_control.configure(lan=False)
    assert web_control.options()["lan"] is True


def test_network_switch_restarts_with_loopback_and_preserves_tls(monkeypatch):
    web_control.save_settings(lan=True, tls=True)
    calls = []
    monkeypatch.setattr(web_control, "_listening", lambda _port: True)
    monkeypatch.setattr(web_control, "_command", lambda: ["python", "-m", "frontends.web"])
    monkeypatch.setattr(web_control, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(web_control, "start", lambda: calls.append(web_control.options()["lan"]))
    web_control.configure(lan=False)
    assert calls == ["stop", False]
    assert web_control.options()["tls"] is True


def test_failed_restart_restores_previous_network_and_restarts_it(monkeypatch):
    web_control.save_settings(lan=True, tls=True)
    monkeypatch.setattr(web_control, "_listening", lambda _port: True)
    monkeypatch.setattr(web_control, "_command", lambda: ["python"])
    monkeypatch.setattr(web_control, "stop", lambda: None)
    calls = []

    def start():
        calls.append(web_control.options()["lan"])
        if len(calls) == 1:
            raise ActionNeeded("startup failed")

    monkeypatch.setattr(web_control, "start", start)
    with pytest.raises(ActionNeeded, match="startup failed"):
        web_control.configure(lan=False)
    assert calls == [False, True]
    assert web_control.options()["lan"] is True


def test_start_does_not_report_success_when_child_exits_before_listening(monkeypatch):
    monkeypatch.setattr(web_control, "_listening", lambda _port: False)
    monkeypatch.setattr(web_control, "_command", lambda: ["python"])
    monkeypatch.setattr(web_control, "autostart_state", lambda: {"enabled": False})
    monkeypatch.setattr(web_control.subprocess, "Popen", lambda *a, **k: SimpleNamespace(poll=lambda: 1))
    with pytest.raises(ActionNeeded, match="did not start"):
        web_control.start()


def test_command_uses_the_isolated_runtime_when_system_dependencies_are_missing(tmp_path, monkeypatch):
    runtime = tmp_path / "web-runtime/bin/python"
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    monkeypatch.setattr(web_control, "app_data_dir", lambda: tmp_path)
    calls = []

    def probe(argv, **kwargs):
        calls.append(argv[0])
        return SimpleNamespace(returncode=0 if argv[0] == str(runtime) else 1)

    monkeypatch.setattr(web_control.subprocess, "run", probe)
    assert web_control._command() == [str(runtime), "-m", "frontends.web"]
    assert calls == [web_control.sys.executable, str(runtime)]


@pytest.mark.parametrize("listening", [True, False])
def test_enabling_session_start_does_not_spawn_a_second_running_server(tmp_path, monkeypatch, listening):
    monkeypatch.setattr(web_control, "systemd_available", lambda: True)
    monkeypatch.setattr(web_control, "_unit_path", lambda: tmp_path / "bc250-web.service")
    monkeypatch.setattr(web_control, "_command", lambda: ["python", "-m", "frontends.web"])
    monkeypatch.setattr(web_control, "_listening", lambda _port: listening)
    calls = []
    monkeypatch.setattr(web_control, "_systemctl", lambda *args: calls.append(args) or SimpleNamespace(returncode=0))
    state = web_control.set_autostart(True)
    assert state["enabled"]
    expected = ("enable", web_control.UNIT_FILE_NAME) if listening else ("enable", "--now", web_control.UNIT_FILE_NAME)
    assert expected in calls
    if listening:
        assert not any("--now" in args or "restart" in args or "start" in args for args in calls)


def test_disabling_session_start_keeps_the_current_web_session_running(tmp_path, monkeypatch):
    path = tmp_path / "bc250-web.service"
    path.write_text(web_control.UNIT_MARKER + "\n")
    monkeypatch.setattr(web_control, "systemd_available", lambda: True)
    monkeypatch.setattr(web_control, "_unit_path", lambda: path)
    calls = []
    monkeypatch.setattr(web_control, "_systemctl", lambda *args: calls.append(args) or SimpleNamespace(returncode=0))
    assert not web_control.set_autostart(False)["enabled"]
    assert ("disable", web_control.UNIT_FILE_NAME) in calls
    assert not any("--now" in args or "stop" in args for args in calls)


@pytest.mark.parametrize("resolved", ["bazzite.local", "bc250cc.local", ""])
def test_pairing_offers_only_the_verified_app_alias_and_numeric_fallback(monkeypatch, resolved):
    from bc250cc.infrastructure import web_network

    web_control.save_settings(lan=True)
    monkeypatch.setattr(web_control, "addresses", lambda: ["192.168.0.15"])
    monkeypatch.setattr(web_control, "autostart_state", lambda: {})
    monkeypatch.setattr(web_control, "_listening", lambda _: True)
    monkeypatch.setattr(web_network, "local_hostname", lambda: resolved)
    urls = web_control.status()["urls"]
    assert urls[-1] == "https://192.168.0.15:8250"
    assert all("bazzite" not in url for url in urls)
    assert (urls[0] == "https://bc250cc.local:8250") == (resolved == "bc250cc.local")
