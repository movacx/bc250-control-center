"""The local web interface: a stdlib HTTP server in front of the services the other frontends use.

Authentication is not optional: every route except the page itself, its
assets, the login, build version and the language catalogue needs a session opened with the
access key the desktop application shows. Mutating requests carry the
session's CSRF token, and only names from ``actions.ACTIONS`` ever run.
"""

from __future__ import annotations

import hmac
import http.cookies
import io
import ipaddress
import json
import logging
import mimetypes
import os
import secrets
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from email.message import Message
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path

from cheroot.ssl.builtin import BuiltinSSLAdapter
from cheroot.wsgi import Server as WsgiServer

from bc250cc.application import ApplicationContainer
from bc250cc.application.system import web_access, web_network
from bc250cc.application.system import web_announcement as web_mdns
from bc250cc.application.system import web_sessions as web_devices
from bc250cc.application.system.privacy import redact_machine
from bc250cc.application.system.workflow_console import (
    TERMINAL_AUTH_ENV,
    set_translator,
)
from bc250cc.shared.errors import BoundaryError
from frontends.desktop.i18n import (
    LANGUAGE_OPTIONS,
    SUPPORTED_LANGUAGES,
    normalize_language,
    set_language,
    tr,
)
from frontends.desktop.theme import ACCENTS, THEMES, theme_palette
from frontends.tui.runtime import Context, describe_error
from frontends.web.actions import ACTIONS, Invalid
from frontends.web.arguments import argument_parser
from frontends.web.data import PAGES, Live, performance
from frontends.web.ssh import SSHSession

web_access.require_supported_version()

logger = logging.getLogger(__name__)
DIST = Path(__file__).resolve().parent / "dist"
COOKIE = "bc250_session"
SESSION_SECONDS = 8 * 3600
SESSION_COOKIE_SECONDS = web_devices.MAX_SESSION_SECONDS
MAX_FAILS, LOCK_SECONDS = 5, 300
MAX_BODY = 64 * 1024
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def clean_key(value: object) -> str:
    return str(value or "").replace("-", "").replace(" ", "").upper()


def same_key(given: object, expected: str) -> bool:
    return bool(clean_key(given)) and hmac.compare_digest(clean_key(given).encode(), clean_key(expected).encode())


def is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%")[0]).is_loopback
    except ValueError:
        return False


def host_allowed(header: str) -> bool:
    """Only an address, localhost or this machine's own name: a rebinding page names neither."""
    name = urllib.parse.urlsplit(f"//{header}").hostname or ""
    if name in ("localhost", web_network.LOCAL_ALIAS, socket.gethostname().lower(), f"{socket.gethostname().lower()}.local"):
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


class Web:
    """Server state: the services, sessions and the failed-login ledger."""

    def __init__(self, container=None, *, terminal_factory=SSHSession) -> None:
        container = container or ApplicationContainer.production()
        self.ctx = Context(service=container.system_service, settings=container.settings_service,
                           activity=container.activity_service, platform=container.platform,
                           config=container.settings_service.read_local_config())
        self.live = Live(self.ctx)
        self.terminal_factory = terminal_factory
        self.local_sessions: dict[str, SSHSession] = {}
        self.language = normalize_language(self.ctx.config.get("idioma", "auto"))
        self.sessions: dict[str, tuple[str, float]] = {}
        self.ssh_sessions: dict[str, SSHSession] = {}
        self.job_owner = ""
        self.job_backend = None
        self.live.monitor_job = lambda: self.job_backend.view() if self.job_backend is not None and hasattr(self.job_backend, "view") else {}
        self.completed_job = None
        self.job_lock = threading.Lock()
        self.key = web_access.access_key()
        self.fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _strings() -> list[str]:
        try:
            return json.loads((DIST / "strings.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def locked(self, who: str) -> bool:
        now = time.monotonic()
        self.fails = {key: [t for t in times if now - t < LOCK_SECONDS]
                      for key, times in self.fails.items() if times and now - times[-1] < LOCK_SECONDS}
        if len(self.fails) >= 256 and who not in self.fails:
            return True
        recent = [t for t in self.fails.get(who, []) if now - t < LOCK_SECONDS]
        self.fails[who] = recent
        return len(recent) >= MAX_FAILS

    def login(self, who: str, key: object, agent: str = "") -> tuple[str, str] | None:
        with self.lock:
            if self.locked(who):
                raise PermissionError
            self._sync_key()
            if not same_key(key, self.key):
                self.fails[who].append(time.monotonic())
                return None
            self.fails.pop(who, None)
            now = time.monotonic()
            valid_ids = {device["id"] for device in web_devices.devices()}
            for token in tuple(self.sessions):
                if web_devices.identity(token) not in valid_ids:
                    self._drop_session(token)
            session = secrets.token_urlsafe(32)
            csrf = self._csrf(session)
            web_devices.register(session, who, agent, SESSION_SECONDS, key_id=self._key_id())
            self.sessions[session] = (csrf, now + SESSION_SECONDS)
            return session, csrf

    def _key_id(self) -> str:
        return hmac.new(self.key.encode(), b"bc250-session-key", "sha256").hexdigest()

    def _csrf(self, token: str) -> str:
        # Stable across restarts without persisting a cookie or CSRF secret.
        return hmac.new(self.key.encode(), b"bc250-csrf\0" + token.encode(), "sha256").hexdigest()

    def _sync_key(self):
        current = web_access.access_key()
        if not same_key(self.key, current):
            self.sessions.clear()
            web_devices.revoke_all()
            for collection in (self.ssh_sessions, self.local_sessions):
                for terminal in collection.values():
                    terminal.close()
                collection.clear()
            self.key = current

    def session(self, token: str) -> str | None:
        with self.lock:
            self._sync_key()
            csrf, expires = self.sessions.get(token, ("", 0))
            device = web_devices.session(token) if token else {}
            if device.get("key_id") != self._key_id():
                device = {}
            if not csrf and device:
                csrf = self._csrf(token)
                expires = time.monotonic() + max(0, float(device["expires"]) - time.time())
                self.sessions[token] = (csrf, expires)
            # A desktop-selected duration is authoritative; do not silently
            # reapply the original eight-hour cap held in this process.
            legacy_expired = expires <= time.monotonic() and device.get("duration_seconds") is None
            if not csrf or not device or legacy_expired:
                self._drop_session(token)
                return None
            return csrf

    def _drop_session(self, token):
        self.sessions.pop(token, None)
        for collection in (self.ssh_sessions, self.local_sessions):
            terminal = collection.pop(token, None)
            if terminal:
                terminal.close()

    def job(self) -> dict:
        result = self.job_backend.request("job") if self.job_backend is not None else {"id": 0}
        identity = (self.job_backend, result.get("id"))
        if result.get("done") and identity != self.completed_job:
            self.completed_job = identity
            # Actions run in another process. Invalidate this reader's caches
            # after completion, including failed or partially applied actions.
            self.ctx.service.invalidar_estado_herramientas()
            self.live.forget()
        return result


class Handler:
    """Request/controller adapter; Cheroot owns HTTP parsing, TLS and workers."""

    def __init__(self, server, environ):
        self.server = server
        self.client_address = (environ.get("REMOTE_ADDR", ""), 0)
        self.path = environ.get("PATH_INFO", "/") + ("?" + environ["QUERY_STRING"] if environ.get("QUERY_STRING") else "")
        self.headers = Message()
        for name, value in environ.items():
            if name.startswith("HTTP_"):
                self.headers[name[5:].replace("_", "-")] = str(value)
        for key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            if environ.get(key):
                self.headers[key.replace("_", "-")] = str(environ[key])
        self.rfile = environ["wsgi.input"]
        self.wfile = io.BytesIO()
        self.response_status = 200
        self.response_headers = []

    def send_response(self, status):
        self.response_status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        pass

    @property
    def web(self) -> Web:
        return self.server.web

    # -- replies --------------------------------------------------------------------------------

    def reply(self, body: bytes, kind: str, status: int = 200, extra: dict | None = None) -> None:
        self.send_response(status)
        for name, value in {"Content-Type": kind, "Content-Length": str(len(body)),
                            "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
                            "Referrer-Policy": "no-referrer", "Cross-Origin-Opener-Policy": "same-origin",
                            "Cross-Origin-Resource-Policy": "same-origin", "X-Frame-Options": "DENY",
                            "Cache-Control": "no-store", **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def json(self, payload, status: int = 200, extra: dict | None = None) -> None:
        language = normalize_language(self.headers.get("X-BC250-Language") or self.web.language)
        display_fields = {"title", "hint", "label", "name", "detail", "message", "error", "context", "primary", "value",
                          "applied_value", "applied_detail", "live_value", "live_detail", "detection_value", "detection_detail"}

        def localize(value, key=""):
            if isinstance(value, dict):
                return {k: localize(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [localize(v, key) for v in value]
            return tr(value, language) if isinstance(value, str) and key in display_fields else value

        payload = localize(payload)
        self.reply(json.dumps(payload, ensure_ascii=False, default=str).encode(), "application/json", status, extra)

    def fail(self, message: str, status: int = 400, **more) -> None:
        self.json({"ok": False, "error": redact_machine(message), **more}, status)

    def body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length)) if 0 < length <= MAX_BODY else {}
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # -- guards ---------------------------------------------------------------------------------

    def token(self) -> str:
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return ""
        return jar[COOKIE].value if COOKIE in jar else ""

    def origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or (urllib.parse.urlsplit(origin).netloc == self.headers.get("Host")
                                  and urllib.parse.urlsplit(origin).scheme == ("https" if self.server.secure else "http"))

    def can_type_password(self) -> bool:
        return bool(getattr(self.server, "secure", False)) or is_loopback(self.client_address[0])

    # -- routing --------------------------------------------------------------------------------

    def route(self, method: str) -> None:
        if method not in {"GET", "POST"}:
            return self.fail("Method not allowed", 405)
        if not web_network.allows(self.client_address[0], self.server.allowed_networks):
            return self.fail("Access is limited to this computer and its home network.", 403)
        if int(self.headers.get("Content-Length", "0") or 0) > MAX_BODY:
            return self.fail("Request body too large", 413)
        if not host_allowed(self.headers.get("Host", "")):
            return self.fail("Bad host", 400)
        url = urllib.parse.urlsplit(self.path)
        path, query = url.path, {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        if not path.startswith("/api/") and path != "/theme.css":
            return self.static(path) if method == "GET" else self.fail("Method not allowed", 405)
        if path == "/theme.css":
            return self.reply(theme_css().encode(), "text/css; charset=utf-8", extra={"Cache-Control": "no-cache"})
        if method == "POST" and not self.origin_ok():
            return self.fail("Origin not allowed", 403)
        if (method, path) == ("POST", "/api/login"):
            return self.login()
        if path == "/api/i18n":
            lang = normalize_language(query.get("lang") or self.web.language)
            lang = lang if lang in SUPPORTED_LANGUAGES else "en"
            return self.json({"language": lang, "languages": [{"key": key, "title": title} for key, title in LANGUAGE_OPTIONS if key != "auto"],
                              "strings": {s: tr(s, lang) for s in self.web._strings()}})
        if method == "GET" and path == "/api/version":
            try:
                version = json.loads((DIST / "version.json").read_text(encoding="utf-8")).get("version", "")
            except (OSError, ValueError):
                version = ""
            return self.json({"version": version})
        csrf = self.web.session(self.token())
        if path == "/api/session":
            local_name = web_network.local_hostname() if csrf and web_access.options()["lan"] else ""
            scheme = "https" if getattr(self.server, "secure", False) else "http"
            return self.json({"authenticated": csrf is not None, "csrf": csrf,
                              "password": self.can_type_password(), "encrypted": bool(getattr(self.server, "secure", False)),
                              "control": bool(csrf and web_devices.session(self.token()).get("control")),
                              "device_code": web_devices.identity(self.token())[:8] if csrf else None,
                              "named_url": f"{scheme}://{local_name}:{self.server.server_address[1]}" if local_name else None})
        if csrf is None:
            return self.fail("Authentication required", 401, authenticated=False)
        if method == "POST" and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf):
            return self.fail("Invalid CSRF token", 403)
        if method == "POST" and path not in {"/api/logout", "/api/performance/reset", "/api/job/interrupt", "/api/ssh/close"}:
            if not web_devices.session(self.token()).get("control"):
                return self.fail("This device has monitoring access. Enable hardware control in Remote access on the desktop.", 403)
        handler = {"GET": self.GET, "POST": self.POST}[method].get(path)
        if handler is None:
            return self.fail("Not found", 404)
        try:
            handler(query if method == "GET" else self.body())
        except BoundaryError as error:
            self.fail(error.detail.message, 409, code=error.detail.code)
        except Exception as error:  # the page shows the sentence; the log keeps no personal data
            logger.debug("request failed", exc_info=True)
            self.fail(describe_error(error), 500)

    @property
    def GET(self) -> dict:
        return {"/api/live": self.live, "/api/page": self.page, "/api/performance": self.performance,
                "/api/job": self.job, "/api/ssh": self.ssh_status}

    @property
    def POST(self) -> dict:
        return {"/api/logout": self.logout, "/api/performance/reset": self.reset_statistics, "/api/action": self.action, "/api/job/input": self.job_input,
                "/api/job/interrupt": self.job_interrupt, "/api/ssh/start": self.ssh_start,
                "/api/ssh/input": self.ssh_input, "/api/ssh/close": self.ssh_close}

    # -- endpoints ------------------------------------------------------------------------------

    def login(self) -> None:
        if not self.can_type_password():
            return self.fail("HTTPS required", 403)
        try:
            result = self.web.login(self.client_address[0], self.body().get("key"), self.headers.get("User-Agent", ""))
        except PermissionError:
            return self.fail("Too many attempts. Try again in a few minutes.", 429)
        if result is None:
            return self.fail("That key is not right.", 401)
        session, csrf = result
        cookie = f"{COOKIE}={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_COOKIE_SECONDS}"
        if getattr(self.server, "secure", False):
            cookie += "; Secure"
        self.json({"ok": True, "csrf": csrf}, extra={"Set-Cookie": cookie})

    def logout(self, _body: dict) -> None:
        with self.web.lock:
            self.web.sessions.pop(self.token(), None)
            web_devices.revoke(web_devices.identity(self.token()))
            for collection in (self.web.ssh_sessions, self.web.local_sessions):
                terminal = collection.pop(self.token(), None)
                if terminal:
                    terminal.close()
        self.json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

    def live(self, _query: dict) -> None:
        self.web.live.touch()
        job = self.web.job() if self.web.job_owner == self.token() else None
        self.json({**self.web.live.live(), "job": {"id": job["id"], "done": job.get("done", True)} if job else None})

    def page(self, query: dict) -> None:
        name = query.get("name", "")
        if name not in PAGES:
            return self.fail("Not found", 404)
        self.web.live.touch()
        self.json({"ok": True, "data": self.web.live.page(name)})

    def performance(self, query: dict) -> None:
        self.web.live.touch()
        self.json(performance(self.web.live, query))

    def reset_statistics(self, _body: dict) -> None:
        self.web.live.recorder.log.reset_statistics()
        self.json({"ok": True})

    def action(self, body: dict) -> None:
        if not self.can_type_password():
            return self.fail("HTTPS required", 403)
        build = ACTIONS.get(str(body.get("action")))
        if build is None:
            return self.fail("Unknown action", 400)
        if not isinstance(body.get("params", {}), dict):
            return self.fail("Invalid parameter: params", 400)

        def shell(_command):
            return None  # Validation only; the tty worker executes it.

        try:
            level, _work = build(self.web.ctx, body.get("params") or {}, shell)
        except Invalid as error:
            return self.fail(f"Invalid parameter: {error}", 400)
        if level and body.get("confirm") is not True:
            return self.fail("This action needs confirmation.", 403, confirm=True)
        with self.web.job_lock:
            current = self.web.job()
            if (current.get("kind") == "gddr6.monitor" and not current.get("done", True)
                    and self.web.job_owner == self.token() and body["action"] != "gddr6.monitor"):
                self.web.job_backend.request("interrupt")
                deadline = time.monotonic() + 5
                while not current.get("done", True) and time.monotonic() < deadline:
                    time.sleep(.05)
                    current = self.web.job()
            if current.get("id") and not current.get("done", True):
                return self.fail("Another hardware action is still running.", 409)
            terminal = self.web.ssh_sessions.get(self.token())
            if terminal is None:
                terminal = self.web.local_sessions.get(self.token())
                if terminal is None or terminal.closed:
                    terminal = self.web.terminal_factory(local=True)
                    self.web.local_sessions[self.token()] = terminal
                    deadline = time.monotonic() + 5
                    while not terminal.ready and not terminal.closed and time.monotonic() < deadline:
                        time.sleep(.02)
            if not terminal.ready:
                return self.fail("The control terminal is unavailable. Reconnect SSH or retry the action.", 409)
            result = terminal.request("action", action=body["action"], params=body.get("params") or {},
                                      title=str(body.get("title") or body["action"])[:80], confirmed=bool(body.get("confirm")),
                                      language=normalize_language(self.headers.get("X-BC250-Language") or self.web.language))
            if not result.get("ok"):
                return self.fail(result.get("error", "Terminal disconnected"), 409)
            self.web.job_owner, self.web.job_backend = self.token(), terminal
            job = result["job"]
        self.web.live.forget()
        self.json({"ok": True, "job": job})

    def job_input(self, body: dict) -> None:
        if not self.can_type_password():
            return self.fail("The password is only accepted on this computer, or after turning that option on.", 403)
        if self.web.job_owner and self.web.job_owner != self.token():
            return self.fail("This operation belongs to another session.", 403)
        text = str(body.get("text", ""))
        if len(text) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in text):
            return self.fail("Invalid parameter: terminal input", 400)
        if self.web.job_backend is not None:
            return self.json(self.web.job_backend.request("input", text=text))
        self.json({"ok": False})

    def job(self, _query: dict) -> None:
        self.json(self.web.job() if self.web.job_owner == self.token() else {"id": 0})

    def job_interrupt(self, _body: dict) -> None:
        if self.web.job_owner != self.token():
            return self.fail("This operation belongs to another session.", 403)
        if self.web.job_backend is not None:
            return self.json(self.web.job_backend.request("interrupt"))
        self.json({"ok": False})

    def ssh_status(self, _query: dict) -> None:
        ssh = self.web.ssh_sessions.get(self.token())
        self.json(ssh.status() if ssh else {"ready": False, "closed": True, "text": ""})

    def ssh_start(self, _body: dict) -> None:
        if not self.can_type_password():
            return self.fail("Use HTTPS before entering your Linux password.", 403)
        with self.web.lock:
            ssh = self.web.ssh_sessions.get(self.token())
            if ssh is not None and not ssh.closed:
                return self.json(ssh.status())
            ledger = "ssh:" + self.token()
            if self.web.locked(ledger):
                return self.fail("Too many attempts. Try again in a few minutes.", 429)
            self.web.fails[ledger].append(time.monotonic())
            self.web.ssh_sessions[self.token()] = ssh = self.web.terminal_factory()
        self.json(ssh.status())

    def ssh_input(self, body: dict) -> None:
        if not self.can_type_password():
            return self.fail("Use HTTPS before entering your Linux password.", 403)
        ssh = self.web.ssh_sessions.get(self.token())
        text = str(body.get("text", ""))
        if len(text) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in text):
            return self.fail("Invalid parameter: password", 400)
        self.json({"ok": bool(ssh and ssh.login_input(text))})

    def ssh_close(self, _body: dict) -> None:
        ssh = self.web.ssh_sessions.pop(self.token(), None)
        if ssh:
            ssh.close()
        self.json({"ok": True})

    def static(self, path: str) -> None:
        target = (DIST / path.lstrip("/")).resolve()
        if path in ("", "/") or not target.is_file() or DIST.resolve() not in target.parents:
            if "." in path.rsplit("/", 1)[-1]:
                return self.fail("Not found", 404)
            target = DIST / "index.html"
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.reply(target.read_bytes(), kind + ("; charset=utf-8" if kind.startswith("text") or "javascript" in kind
                                                else ""), extra={"Cache-Control": "no-cache"})


@lru_cache(maxsize=1)
def theme_css() -> str:
    """All desktop Formal palettes, chosen locally by theme and accent."""
    palettes = {(theme, accent): theme_palette(theme, accent, "formal")
                for theme in THEMES for accent in ACCENTS}

    def block(theme: str, accent: str) -> str:
        palette = palettes[theme, accent]
        ink = "#FFFFFF" if theme == "light" else palette["window"]
        variables = {f"--c-{name.replace('_', '-')}": value for name, value in palette.items()
                     if isinstance(value, str)}
        variables["--c-on-accent"] = ink
        variables.update({f"--c-accent-{key}": palettes[theme, key]["blue"] for key in ACCENTS})
        variables.update({f"--c-preview-{key}-{surface}": palettes[key, accent][surface]
                          for key in THEMES for surface in ("window", "panel")})
        return "".join(f"{key}:{value};" for key, value in variables.items())

    rules = []
    # Keep violet for browsers without a saved choice, preserving their look.
    for accent in ("violet", *(key for key in ACCENTS if key != "violet")):
        selector = ":root" if accent == "violet" else f":root[data-accent={accent}]"
        rules.append(f"{selector}{{color-scheme:light;{block('light', accent)}}}")
        rules.append(f"@media (prefers-color-scheme:dark){{{selector}:not([data-theme])"
                     f"{{color-scheme:dark;{block('dark', accent)}}}}}")
        for theme in THEMES:
            scheme = "light" if theme == "light" else "dark"
            rules.append(f"{selector}[data-theme={theme}]{{color-scheme:{scheme};{block(theme, accent)}}}")
    return "".join(rules)


class Server(WsgiServer):
    """Bounded WSGI server with native TLS; no development HTTP server."""

    def __init__(self, address: tuple[str, int], web: Web, *, certificate=None, networks=None):
        self.web = web
        self.secure = certificate is not None
        self.allowed_networks = list(networks or [])
        super().__init__(address, self.application, numthreads=4, max=12, request_queue_size=16,
                         accepted_queue_size=16, accepted_queue_timeout=1, timeout=10, shutdown_timeout=2)
        self.keep_alive_conn_limit = 12
        self.max_request_header_size = 16 * 1024
        self.max_request_body_size = MAX_BODY
        self.software = "bc250-web"
        if certificate:
            cert, key = certificate
            adapter = BuiltinSSLAdapter(str(cert), str(key))
            adapter.context.minimum_version = ssl.TLSVersion.TLSv1_2
            self.ssl_adapter = adapter
        self.prepare()
        self.server_address = self.bind_addr
        # Browser permissions and expiry remain in the private registry. A
        # restart never clears them; Web.session binds them to the current key.
        for device in web_devices.devices():
            if device.get("key_id") != web._key_id():
                web_devices.revoke(device["id"])

    def error_log(self, msg="", level=logging.INFO, traceback=False):
        # Cheroot messages may contain request bytes or addresses. Keep the
        # event only; never log credentials, URLs or terminal input.
        logger.log(level, "HTTPS connection failed")

    def application(self, environ, start_response):
        handler = Handler(self, environ)
        try:
            handler.route(environ["REQUEST_METHOD"])
        except Exception:
            handler.response_headers.clear()
            handler.wfile = io.BytesIO()
            handler.fail("Request could not be processed", 400)
        start_response(f"{handler.response_status} {HTTPStatus(handler.response_status).phrase}", handler.response_headers)
        return [handler.wfile.getvalue()]

    def serve_forever(self):
        self.serve()

    def shutdown(self):
        self.stop()

    def server_close(self):
        for collection in (self.web.ssh_sessions, self.web.local_sessions):
            for terminal in collection.values():
                terminal.close()
        self.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argument_parser()
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("Run the web interface as your ordinary Linux user, never as root.")
    options = web_access.options()
    host = args.host or ("0.0.0.0" if options["lan"] else "127.0.0.1")  # nosec B104 - only when the owner turned it on
    port = args.port or options["port"]
    os.environ[TERMINAL_AUTH_ENV] = "1"  # passwords are asked on the job's console, never in a window
    os.environ["SSH_ASKPASS_REQUIRE"] = "never"
    logging.basicConfig(level=logging.WARNING)
    key = web_access.access_key()
    web = Web()
    set_language(web.language)
    set_translator(tr)
    encrypted = options["tls"] and not args.http
    if not encrypted and not is_loopback(host):
        parser.error("Home-network access requires HTTPS. HTTP is available only on loopback.")
    networks = web_network.home_networks() if not is_loopback(host) else []
    server = Server((host, port), web, certificate=web_access.tls_certificate() if encrypted else None, networks=networks)
    try:
        # Advertise the alias only after acquiring the port. Failed duplicate
        # startups must neither publish a competing alias nor clear sessions.
        with web_mdns.LanAlias(enabled=bool(networks)):
            web_access.write_pid(port)
            print(f"BC250 Control Center web: {'https' if server.secure else 'http'}://{host}:{port}", flush=True)
            if sys.stdout.isatty():  # never into a journal: the key opens hardware controls
                print(f"Access key: {key}", flush=True)
            for name in (signal.SIGINT, signal.SIGTERM):
                signal.signal(name, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
            server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
