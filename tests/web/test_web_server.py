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
    httpd = server.Server(("127.0.0.1", 0), server.Web(container))
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

    def login(self, key=KEY):
        response, data = self.call("POST", "/api/login", {"key": key})
        if response.status == 200:
            self.cookie = response.getheader("Set-Cookie").split(";")[0]
            self.csrf = data["csrf"]
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
    assert client.action("gpu.range", {"min": "500; reboot", "max": 1000}, confirm=True) == 400
    assert client.action("gpu.range", {"min": 500, "max": 99999}, confirm=True) == 400
    assert client.action("cu.apply", {"masks": [31, 31, 31, 99]}, confirm=True) == 400
    assert client.httpd.service.calls == []


def test_a_changing_action_needs_confirmation_and_a_risk_zone_needs_the_key_again(client):
    client.login()
    assert client.action("gpu.range", {"min": 500, "max": 1800}) == 403
    assert client.action("gpu.range", {"min": 500, "max": 1800}, confirm=True) == 200
    client.wait_idle()
    assert client.action("gpu.range", {"min": 500, "max": 2400}, confirm=True) == 403
    assert client.action("gpu.range", {"min": 500, "max": 2400}, confirm=True, key="NOPE-NOPE") == 403
    assert client.action("gpu.range", {"min": 500, "max": 2400}, confirm=True, key=KEY) == 200
    client.wait_idle()
    assert [call for call in client.httpd.service.calls if call[0] == "aplicar_rango_bc250"] == [
        ("aplicar_rango_bc250", (500, 1800)), ("aplicar_rango_bc250", (500, 2400))]


def test_the_password_is_only_typed_on_this_computer_unless_the_owner_allowed_it(client, monkeypatch):
    client.login()
    assert client.post("/api/job/input", {"text": "x"})[0].status == 200  # loopback
    monkeypatch.setattr(server, "is_loopback", lambda _address: False)
    assert client.post("/api/job/input", {"text": "x"})[0].status == 403
    web_access.save_settings(lan_password=True)
    assert client.post("/api/job/input", {"text": "x"})[0].status == 403


def test_the_action_list_is_closed_and_runs_nothing_outside_the_service_layer():
    assert set(actions.ACTIONS) == {
        "gpu.profile", "gpu.range", "gpu.compat", "gpu.service", "gpu.high_points", "gpu.voltage", "gpu.save_boot",
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


def test_a_type_error_in_work_is_never_retried():
    from frontends.web.jobs import Jobs
    calls = []

    def work():
        calls.append("started")
        raise TypeError("a real error inside the action")

    jobs = Jobs()
    jobs.start("test", work)
    assert jobs.console.done.wait(3)
    assert calls == ["started"]
    assert jobs.view()["ok"] is False


def test_http_errors_do_not_log_the_client_address(client, caplog):
    import logging
    with caplog.at_level(logging.DEBUG):
        client.httpd.handle_error(None, ("192.0.2.123", 1234))
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
    assert client.post("/api/action", {"action": "gpu.range", "params": params, "confirm": True})[0].status == 400
    assert client.httpd.service.calls == []


def test_cpu_manual_mode_must_be_a_boolean(client):
    client.login()
    assert client.action("cpu.apply", {"frequency": 3550, "temperature": 90, "vid": 1050, "manual": "yes", "scale": -34}, confirm=True) == 400
    assert client.httpd.service.calls == []


def test_plaintext_network_cannot_log_in_or_reuse_a_session_to_control_hardware(client, monkeypatch):
    client.login()
    monkeypatch.setattr(server, "is_loopback", lambda _address: False)
    assert client.action("gpu.range", {"min": 500, "max": 1800}, confirm=True) == 403
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


def test_the_job_panel_supports_identity_selection_and_masked_passwords():
    import os
    import termios

    from frontends.tui.console import Console
    from frontends.web.jobs import Jobs
    master, slave = os.openpty()
    jobs = Jobs()
    jobs.console = console = Console("authorization")
    console.master = master
    try:
        console.write("Choose an identity (1-2): ")
        assert jobs.view()["interactive"] is True
        assert jobs.view()["waiting"] is False
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        assert jobs.view()["waiting"] is True
    finally:
        console.master = None
        os.close(master)
        os.close(slave)
