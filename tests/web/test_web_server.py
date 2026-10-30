"""The local web interface: who gets in, what a request may do, and that nothing outside the list runs."""

from __future__ import annotations

import http.client
import json
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.application.system import web_access
from bc250cc.infrastructure import web_devices
from frontends.web import actions, server

KEY = "ABCD-EFGH"


class Service:
    """Records what the web asked of the service layer; reads return small, valid shapes."""

    def __init__(self):
        self.calls = []

    def metricas_tiempo_real(self):
        return {"cpu": {"usage_percent": 1.0}}

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args))
            return {"message": "ok"}
        return call


class Settings:
    def read_local_config(self):
        return {}

    def save_local_config(self, values):
        return values


@pytest.fixture
def web(monkeypatch, tmp_path):
    monkeypatch.setattr("frontends.tui.console.shutil.which", lambda _name: None)  # no pkttyagent in tests
    web_access.save_settings(pin=KEY, lan_password=False)
    service = Service()
    container = SimpleNamespace(system_service=service, settings_service=Settings(), activity_service=None, platform=None)
    class Terminal:
        ready, closed = True, False

        def __init__(self, **_kwargs):
            self.job = {"id": 0}

        def request(self, op, **values):
            if op == "job":
                return self.job
            if op == "action":
                _, work = actions.ACTIONS[values["action"]](httpd.web.ctx, values["params"], lambda _: "")
                work()
                self.job = {"id": self.job["id"] + 1, "done": True, "ok": True}
                return {"ok": True, "job": self.job["id"]}
            return {"ok": False}

        def close(self):
            self.closed = True

    httpd = server.Server(("127.0.0.1", 0), server.Web(container, terminal_factory=Terminal))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    httpd.service = service
    yield httpd
    httpd.shutdown()
    httpd.server_close()


class Client:
    def __init__(self, httpd):
        self.port, self.cookie, self.csrf, self.httpd = httpd.server_address[1], "", "", httpd

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        sent = {"Host": f"127.0.0.1:{self.port}", **(headers or {})}
        if self.cookie:
            sent["Cookie"] = self.cookie
        if body is not None:
            sent["Content-Type"] = "application/json"
        connection.request(method, path, json.dumps(body) if body is not None else None, sent)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        try:
            return response, json.loads(raw)
        except ValueError:
            return response, raw

    def login(self, key=KEY, *, control=True):
        response, data = self.call("POST", "/api/login", {"key": key})
        if response.status == 200:
            self.cookie = response.getheader("Set-Cookie").split(";")[0]
            self.csrf = data["csrf"]
            if control:
                web_devices.set_control(web_devices.identity(self.cookie.split("=", 1)[1]), True)
        return response, data

    def post(self, path, body, **headers):
        return self.call("POST", path, body, {"X-CSRF-Token": self.csrf, **headers})

    def action(self, name, params=None, **extra):
        return self.post("/api/action", {"action": name, "params": params or {}, **extra})[0].status

    def wait_idle(self):
        for _ in range(100):
            if self.call("GET", "/api/job")[1].get("done", True):
                return
            time.sleep(0.05)


@pytest.fixture
def client(web):
    return Client(web)


def test_the_page_is_public_but_every_api_route_needs_a_session(client):
    assert client.call("GET", "/")[0].status == 200
    assert client.call("GET", "/api/session")[1]["authenticated"] is False
    for route in ("/api/live", "/api/page?name=cpu", "/api/performance", "/api/job"):
        assert client.call("GET", route)[0].status == 401
    assert client.call("POST", "/api/action", {"action": "gpu.status"})[0].status == 401


def test_a_wrong_key_is_refused_and_five_wrong_keys_lock_even_the_right_one(client):
    for _ in range(5):
        assert client.login("WRONG-KEYS")[0].status == 401
    assert client.login()[0].status == 429


def test_login_sets_a_strict_http_only_cookie(client):
    response, data = client.login(KEY.lower().replace("-", " "))
    cookie = response.getheader("Set-Cookie")
    assert response.status == 200 and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert data["csrf"] and client.call("GET", "/api/session")[1]["authenticated"] is True


def test_posts_need_the_csrf_token_and_the_same_origin(client):
    client.login()
    assert client.call("POST", "/api/logout", {})[0].status == 403
    assert client.post("/api/logout", {}, Origin="http://evil.example")[0].status == 403
    assert client.post("/api/logout", {}, **{"X-CSRF-Token": "x" * 43})[0].status == 403


def test_a_foreign_host_name_is_refused_against_dns_rebinding(client):
    client.login()
    assert client.call("GET", "/api/live", headers={"Host": "attacker.example"})[0].status == 400


def test_responses_carry_a_strict_policy_and_no_cors(client):
    response, _ = client.call("GET", "/")
    policy = response.getheader("Content-Security-Policy")
    assert "unsafe-inline" not in policy and "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert response.getheader("Access-Control-Allow-Origin") is None
    assert client.call("PUT", "/api/action", {})[0].status in (405, 501)
    assert client.call("DELETE", "/api/session")[0].status in (405, 501)


def test_only_listed_actions_run_and_their_parameters_are_checked(client):
    client.login()
    assert client.action("os.system", {"command": "id"}) == 400
    assert client.action("gpu.profile", {"min": "500; reboot", "max": 1000}, confirm=True) == 400
    assert client.action("gpu.profile", {"min": 500, "max": 99999}, confirm=True) == 400
    assert client.action("cu.apply", {"masks": [31, 31, 31, 99]}, confirm=True) == 400
    assert client.httpd.service.calls == []


def test_changes_need_confirmation_but_never_repeat_the_web_login_key(client):
    client.login()
    assert client.action("gpu.profile", {"min": 500, "max": 1800}) == 403
    assert client.action("gpu.profile", {"min": 500, "max": 1800}, confirm=True) == 200
    client.wait_idle()
    assert client.action("gpu.profile", {"min": 500, "max": 2400}, confirm=True) == 200
    client.wait_idle()
    assert client.action("cu.apply", {"masks": [7, 7, 7, 7]}) == 403
    assert client.action("cu.apply", {"masks": [7, 7, 7, 7]}, confirm=True) == 200
    client.wait_idle()
    assert [call for call in client.httpd.service.calls if call[0] == "aplicar_perfil_gpu"] == [
        ("aplicar_perfil_gpu", (500, 1800)), ("aplicar_perfil_gpu", (500, 2400))]


def test_the_password_is_only_typed_on_this_computer_unless_the_owner_allowed_it(client, monkeypatch):
    client.login()
    assert client.post("/api/job/input", {"text": "x"})[0].status == 200  # loopback
    monkeypatch.setattr(server, "is_loopback", lambda _address: False)
    assert client.post("/api/job/input", {"text": "x"})[0].status == 403
    web_access.save_settings(lan_password=True)
    assert client.post("/api/job/input", {"text": "x"})[0].status == 403


def test_the_action_list_is_closed_and_runs_nothing_outside_the_service_layer():
    assert set(actions.ACTIONS) == {
        "gddr6.monitor", "gddr6.prepare", "gpu.profile", "gpu.compat", "gpu.service", "gpu.high_points", "gpu.voltage", "gpu.voltage_custom", "gpu.save_boot",
        "gpu.status", "cpu.apply", "cpu.unlock", "cpu.persist", "cpu.persist_off", "cu.sync", "cu.apply", "cu.save",
        "cu.action", "fan.pwm", "fan.auto", "fan.curve"}
    source = Path(actions.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b(subprocess|os\.system|eval|exec|open)\(|import (subprocess|os)\b", source)


def test_every_string_the_page_asks_for_is_in_the_catalogue():
    from frontends.desktop.i18n.locale_catalog import LOCALE_DIRECTORY
    catalogue = json.loads((LOCALE_DIRECTORY / "en.json").read_text(encoding="utf-8"))
    strings = json.loads((server.DIST / "strings.json").read_text(encoding="utf-8"))
    assert strings and not [text for text in strings if text not in catalogue]


def test_the_theme_is_the_desktops_palette(client):
    css = client.call("GET", "/theme.css")[1].decode()
    assert "--c-panel:#FFFFFF" in css and "--c-blue-soft:" in css and "prefers-color-scheme:dark" in css


def test_host_and_address_helpers():
    assert server.is_loopback("127.0.0.1") and server.is_loopback("::1") and not server.is_loopback("192.168.1.20")
    assert server.host_allowed("192.168.1.20:8250") and server.host_allowed("localhost:8250")
    assert not server.host_allowed("evil.example")
    assert server.same_key("abcd efgh", KEY) and not server.same_key("", KEY)


def test_the_access_key_is_private_and_the_service_unit_needs_systemd(monkeypatch):
    from bc250cc.infrastructure import web_control
    from bc250cc.shared.errors import ActionNeeded
    key = web_control.access_key(renew=True)
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", key) and web_control.settings_path().stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(web_control, "systemd_available", lambda: False)
    with pytest.raises(ActionNeeded):
        web_control.set_autostart(True)


def test_plain_http_lan_never_accepts_passwords_even_with_the_old_option(client, monkeypatch):
    client.login()
    monkeypatch.setattr(server, "is_loopback", lambda _address: False)
    web_access.save_settings(lan_password=True)
    assert client.post("/api/ssh/start", {})[0].status == 403
    assert client.post("/api/ssh/input", {"text": "secret"})[0].status == 403
    assert client.post("/api/job/input", {"text": "secret"})[0].status == 403
    client.httpd.secure = True
    assert client.call("GET", "/api/session")[1]["password"] is True


def test_key_rotation_revokes_existing_browser_sessions(client):
    client.login()
    web_access.access_key(renew=True)
    assert client.call("GET", "/api/live")[0].status == 401


def test_another_browser_cannot_read_or_interrupt_a_job(client):
    client.login()
    other = Client(client.httpd)
    other.login()
    client.httpd.web.job_owner = client.cookie.split("=", 1)[1]
    assert other.call("GET", "/api/job")[1] == {"id": 0}
    assert other.post("/api/job/input", {"text": "secret"})[0].status == 403
    assert other.post("/api/job/interrupt", {})[0].status == 403


def test_ssh_endpoints_require_login_and_csrf(client):
    for path in ("ssh/start", "ssh/input", "ssh/close"):
        assert client.call("POST", "/api/" + path, {})[0].status == 401
    client.login()
    assert client.call("POST", "/api/ssh/start", {})[0].status == 403


def test_failed_inherited_workflow_never_falls_back_to_another_terminal(monkeypatch):
    from frontends.web.action_worker import InheritedTerminal
    calls = []
    monkeypatch.setattr("frontends.web.action_worker.subprocess.call", lambda argv: calls.append(argv) or 1)
    terminal = InheritedTerminal()
    request = SimpleNamespace(argv=("bash", "workflow.sh"), title="test", status_file="status", log_file="log")
    assert terminal(request).terminal == "bc250-web"
    assert calls == [["bash", "workflow.sh"]]
    assert terminal.failed


def test_http_errors_do_not_log_the_client_address(client, caplog):
    import logging
    with caplog.at_level(logging.DEBUG):
        client.httpd.error_log("Connection from 192.0.2.123", logging.DEBUG)
    assert "192.0.2.123" not in caplog.text


def test_display_translation_never_changes_protocol_values(client):
    client.login()
    _, data = client.call("GET", "/api/i18n?lang=es", headers={"X-BC250-Language": "es"})
    assert data["language"] == "es"
    assert data["strings"]["Connect SSH"] == "Conectar SSH"
    _, session = client.call("GET", "/api/session", headers={"X-BC250-Language": "es"})
    assert session["authenticated"] is True
    assert session["csrf"] == client.csrf


@pytest.mark.parametrize("params", [[], "command", 1, True])
def test_actions_reject_non_object_parameters(client, params):
    client.login()
    assert client.post("/api/action", {"action": "gpu.profile", "params": params, "confirm": True})[0].status == 400
    assert client.httpd.service.calls == []


def test_cpu_manual_mode_must_be_a_boolean(client):
    client.login()
    assert client.action("cpu.apply", {"frequency": 3550, "temperature": 90, "vid": 1050, "manual": "yes", "scale": -34}, confirm=True) == 400
    assert client.httpd.service.calls == []


def test_plaintext_network_cannot_log_in_or_reuse_a_session_to_control_hardware(client, monkeypatch):
    client.login()
    monkeypatch.setattr(server, "is_loopback", lambda _address: False)
    assert client.action("gpu.profile", {"min": 500, "max": 1800}, confirm=True) == 403
    other = Client(client.httpd)
    assert other.login()[0].status == 403
    assert client.httpd.service.calls == []


def test_a_custom_port_does_not_overwrite_the_installed_server_pid(tmp_path, monkeypatch):
    from bc250cc.infrastructure import web_control
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(web_control, "options", lambda: {"port": 8250})
    original = tmp_path / "bc250-web.pid"
    original.write_text("12345")
    web_control.write_pid(18250)
    assert original.read_text() == "12345"
    assert (tmp_path / "bc250-web-18250.pid").is_file()


def test_job_panel_masks_native_sudo_password_and_rejects_control_input():
    from frontends.tui.console import Console
    from frontends.web.ssh import SSHSession
    session = SSHSession.__new__(SSHSession)
    session.job_console = Console("authorization")
    session._job_id, session._active = 1, True
    session._state_lock = threading.Lock()
    session.console = SimpleNamespace(send=lambda _: True)
    session.job_console.write("Continue? ")
    assert session.view()["interactive"] is True
    assert session.view()["waiting"] is False
    session.job_console.write("\nBC250 Linux password: ")
    assert session.view()["waiting"] is True
    assert session.request("input", text="dummy-password")["ok"] is True
    assert session.request("input", text="bad\ninput")["ok"] is False
    session._active = False
    assert session.request("input", text="dummy-password")["ok"] is False


@pytest.mark.parametrize("end", ["logout", "rotate", "expire"])
def test_local_terminal_is_revoked_with_the_browser_session(client, end):
    client.login()
    assert client.action("gpu.status") == 200
    token = client.cookie.split("=", 1)[1]
    terminal = client.httpd.web.local_sessions[token]
    if end == "logout":
        assert client.post("/api/logout", {})[0].status == 200
    elif end == "rotate":
        web_access.access_key(renew=True)
        assert client.call("GET", "/api/live")[0].status == 401
    else:
        client.httpd.web.sessions[token] = (client.csrf, time.monotonic() - 1)
        assert client.call("GET", "/api/live")[0].status == 401
    assert terminal.closed
    assert token not in client.httpd.web.local_sessions


@pytest.mark.parametrize("text", ["bad\ninput", "\x03", "\x7f", "x" * 257])
def test_terminal_input_cannot_inject_controls_or_be_silently_truncated(client, text):
    client.login()
    assert client.post("/api/job/input", {"text": text})[0].status == 400


def test_worker_completion_invalidates_the_reader_cache_once_per_job(client):
    client.login()
    assert client.action("gpu.status") == 200
    client.wait_idle()
    for _ in range(3):
        client.call("GET", "/api/job")
    calls = client.httpd.service.calls
    assert [name for name, _ in calls].count("invalidar_estado_herramientas") == 1
    assert client.action("gpu.status") == 200
    client.wait_idle()
    assert [name for name, _ in calls].count("invalidar_estado_herramientas") == 2


def test_build_identity_is_public_and_asset_urls_change_with_it(client):
    response, metadata = client.call("GET", "/api/version")
    assert response.status == 200
    assert set(metadata) == {"version"}
    version = metadata["version"]
    assert re.fullmatch(r"[a-f0-9]{16}", version)
    html = client.call("GET", "/")[1].decode()
    assert f'name="bc250-build" content="{version}"' in html
    assert f'app.js?v={version}' in html and f'app.css?v={version}' in html
    assert client.call("GET", f"/app.js?v={version}")[0].status == 200


def test_build_updates_are_detected_without_restarting_the_server(client, tmp_path, monkeypatch):
    old_version = client.call("GET", "/api/version")[1]["version"]
    monkeypatch.setattr(server, "DIST", tmp_path)
    (tmp_path / "version.json").write_text(json.dumps({"version": "e" * 16}))
    assert old_version != client.call("GET", "/api/version")[1]["version"] == "e" * 16
    (tmp_path / "strings.json").write_text(json.dumps(["Custom"]))
    assert client.call("GET", "/api/i18n?lang=es")[1]["strings"] == {"Custom": "Personalizado"}


def test_own_memory_monitor_is_stopped_before_another_hardware_action(client):
    client.login()
    class Monitor:
        stopped = False
        interrupts = 0
        def request(self, op):
            if op == "interrupt":
                self.stopped = True
                self.interrupts += 1
                return {"ok": True}
            return {"id": 7, "kind": "gddr6.monitor", "done": self.stopped, "ok": True}
    monitor = Monitor()
    client.httpd.web.job_backend = monitor
    client.httpd.web.job_owner = client.cookie.split("=", 1)[1]
    assert client.action("gpu.status") == 200
    assert monitor.interrupts == 1


def test_another_browser_cannot_automatically_stop_the_memory_monitor(client):
    client.login()
    other = Client(client.httpd)
    other.login()
    operations = []
    monitor = SimpleNamespace(request=lambda op: operations.append(op) or {"id": 7, "kind": "gddr6.monitor", "done": False})
    client.httpd.web.job_backend = monitor
    client.httpd.web.job_owner = client.cookie.split("=", 1)[1]
    assert other.action("gpu.status") == 409
    assert "interrupt" not in operations


def test_new_device_can_monitor_but_cannot_self_grant_hardware_control(client):
    assert client.login(control=False)[0].status == 200
    assert client.call("GET", "/api/live")[0].status == 200
    assert client.call("GET", "/api/session")[1]["control"] is False
    for route, body in (("/api/action", {"action": "gpu.status"}), ("/api/ssh/start", {}),
                        ("/api/job/input", {"text": "password"}), ("/api/ssh/input", {"text": "password"})):
        assert client.post(route, {**body, "control": True, "confirm": True})[0].status == 403
    assert not client.httpd.web.local_sessions
    device = web_devices.devices()[0]
    assert client.call("GET", "/api/session")[1]["device_code"] == device["id"][:8]
    web_devices.set_control(device["id"], True)
    assert client.call("GET", "/api/session")[1]["control"] is True
    assert client.action("gpu.status") == 200
    web_devices.set_control(device["id"], False)
    assert client.action("gpu.status") == 403


def test_desktop_revocation_invalidates_only_the_selected_browser(client):
    client.login()
    other = Client(client.httpd)
    other.login()
    web_devices.revoke(web_devices.identity(client.cookie.split("=", 1)[1]))
    assert client.call("GET", "/api/live")[0].status == 401
    assert other.call("GET", "/api/live")[0].status == 200
    web_devices.revoke_all()
    assert other.call("GET", "/api/live")[0].status == 401


def test_revoked_device_cannot_reuse_permission_on_a_new_login(client):
    client.login()
    web_devices.revoke_all()
    client.login(control=False)
    assert client.action("gpu.status") == 403


def test_wrong_origin_scheme_is_rejected_even_on_same_host(client):
    client.login()
    assert client.post("/api/logout", {}, Origin=f"https://127.0.0.1:{client.port}")[0].status == 403


def test_network_policy_ignores_proxy_headers(client, monkeypatch):
    client.login()
    monkeypatch.setattr(server.web_network, "allows", lambda _peer, _networks: False)
    assert client.call("GET", "/api/live", headers={"X-Forwarded-For": "192.168.0.25"})[0].status == 403


def test_rotated_key_allows_a_fresh_monitoring_login_without_old_permissions(client):
    client.login()
    key = web_access.access_key(renew=True)
    assert client.login(key, control=False)[0].status == 200
    assert client.call("GET", "/api/session")[1]["authenticated"] is True
    assert client.action("gpu.status") == 403
