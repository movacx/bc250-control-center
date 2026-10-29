"""The local web interface: a stdlib HTTP server in front of the services the other frontends use.

Authentication is not optional: every route except the page itself, its
assets, the login and the language catalogue needs a session opened with the
access key the desktop application shows. Mutating requests carry the
session's CSRF token, and only names from ``actions.ACTIONS`` ever run.
"""

from __future__ import annotations

import argparse
import hmac
import http.cookies
import http.server
import ipaddress
import json
import logging
import mimetypes
import os
import secrets
import signal
import sys
import socket
import threading
import time
import urllib.parse
from pathlib import Path

from bc250cc.application import ApplicationContainer
from bc250cc.application.system import web_access
from bc250cc.application.system.privacy import redact_machine
from bc250cc.application.system.workflow_console import TERMINAL_AUTH_ENV, set_translator
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, normalize_language, set_language, tr
from frontends.desktop.theme import theme_palette
from frontends.tui.runtime import Context, describe_error
from frontends.web.actions import ACTIONS, Invalid
from frontends.web.data import PAGES, Live, performance
from frontends.web.jobs import Busy, Jobs

logger = logging.getLogger(__name__)
DIST = Path(__file__).resolve().parent / "dist"
COOKIE = "bc250_session"
SESSION_SECONDS = 12 * 3600
MAX_FAILS, LOCK_SECONDS = 5, 300
MAX_BODY = 64 * 1024
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


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
    if name in ("localhost", socket.gethostname().lower(), f"{socket.gethostname().lower()}.local"):
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


class Web:
    """Server state: the services, sessions and the failed-login ledger."""

    def __init__(self, container=None) -> None:
        container = container or ApplicationContainer.production()
        self.ctx = Context(service=container.system_service, settings=container.settings_service,
                           activity=container.activity_service, platform=container.platform,
                           config=container.settings_service.read_local_config())
        self.live, self.jobs = Live(self.ctx), Jobs()
        self.language = normalize_language(self.ctx.config.get("idioma", "auto"))
        self.sessions: dict[str, tuple[str, float]] = {}
        self.fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()
        self.strings = self._strings()

    @staticmethod
    def _strings() -> list[str]:
        try:
            return json.loads((DIST / "strings.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def locked(self, who: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self.fails.get(who, []) if now - t < LOCK_SECONDS]
        self.fails[who] = recent
        return len(recent) >= MAX_FAILS

    def login(self, who: str, key: object) -> tuple[str, str] | None:
        with self.lock:
            if self.locked(who):
                raise PermissionError
            if not same_key(key, web_access.access_key()):
                self.fails[who].append(time.monotonic())
                return None
            self.fails.pop(who, None)
            now = time.monotonic()
            self.sessions = {s: v for s, v in self.sessions.items() if v[1] > now}
            session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[session] = (csrf, now + SESSION_SECONDS)
            return session, csrf

    def session(self, token: str) -> str | None:
        with self.lock:
            csrf, expires = self.sessions.get(token, ("", 0))
            return csrf if expires > time.monotonic() else None


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "bc250-web"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # addresses and paths are personal data: nothing is logged
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
        return origin is None or urllib.parse.urlsplit(origin).netloc == self.headers.get("Host")

    def can_type_password(self) -> bool:
        return is_loopback(self.client_address[0]) or web_access.options()["lan_password"]

    # -- routing --------------------------------------------------------------------------------

    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def route(self, method: str) -> None:
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
            return self.json({"language": lang, "strings": {s: tr(s, lang) for s in self.web.strings}})
        csrf = self.web.session(self.token())
        if path == "/api/session":
            return self.json({"authenticated": csrf is not None, "csrf": csrf,
                              "password": self.can_type_password()})
        if csrf is None:
            return self.fail("Authentication required", 401, authenticated=False)
        if method == "POST" and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf):
            return self.fail("Invalid CSRF token", 403)
        handler = {"GET": self.GET, "POST": self.POST}[method].get(path)
        if handler is None:
            return self.fail("Not found", 404)
        try:
            handler(query if method == "GET" else self.body())
        except Exception as error:  # the page shows the sentence; the log keeps no personal data
            logger.debug("request failed", exc_info=True)
            self.fail(describe_error(error), 500)

    @property
    def GET(self) -> dict:
        return {"/api/live": self.live, "/api/page": self.page, "/api/performance": self.performance,
                "/api/job": lambda q: self.json(self.web.jobs.view() or {"id": 0})}

    @property
    def POST(self) -> dict:
        return {"/api/logout": self.logout, "/api/performance/reset": self.reset_statistics, "/api/action": self.action, "/api/job/input": self.job_input,
                "/api/job/interrupt": lambda b: (self.web.jobs.interrupt(), self.json({"ok": True}))}

    # -- endpoints ------------------------------------------------------------------------------

    def login(self) -> None:
        try:
            result = self.web.login(self.client_address[0], self.body().get("key"))
        except PermissionError:
            return self.fail("Too many attempts. Try again in a few minutes.", 429)
        if result is None:
            return self.fail("That key is not right.", 401)
        session, csrf = result
        cookie = f"{COOKIE}={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}"
        self.json({"ok": True, "csrf": csrf}, extra={"Set-Cookie": cookie})

    def logout(self, _body: dict) -> None:
        with self.web.lock:
            self.web.sessions.pop(self.token(), None)
        self.json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

    def live(self, _query: dict) -> None:
        self.web.live.touch()
        job = self.web.jobs.view()
        self.json({**self.web.live.live(), "job": {"id": job["id"], "done": job["done"]} if job else None})

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
        build = ACTIONS.get(str(body.get("action")))
        if build is None:
            return self.fail("Unknown action", 400)
        jobs = self.web.jobs
        try:
            level, work = build(self.web.ctx, body.get("params") or {}, jobs.shell)
        except Invalid as error:
            return self.fail(f"Invalid parameter: {error}", 400)
        if level and body.get("confirm") is not True:
            return self.fail("This action needs confirmation.", 403, confirm=True)
        if level == 2 and not same_key(body.get("key"), web_access.access_key()):
            return self.fail("This action needs the access key again.", 403, key=True)
        try:
            job = jobs.start(str(body.get("title") or body["action"])[:80], work)
        except Busy:
            return self.fail("Another hardware action is still running.", 409)
        self.web.live.forget()
        self.json({"ok": True, "job": job})

    def job_input(self, body: dict) -> None:
        if not self.can_type_password():
            return self.fail("The password is only accepted on this computer, or after turning that option on.", 403)
        self.json({"ok": self.web.jobs.send(str(body.get("text", ""))[:256])})

    def static(self, path: str) -> None:
        target = (DIST / path.lstrip("/")).resolve()
        if path in ("", "/") or not target.is_file() or DIST.resolve() not in target.parents:
            if "." in path.rsplit("/", 1)[-1]:
                return self.fail("Not found", 404)
            target = DIST / "index.html"
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.reply(target.read_bytes(), kind + ("; charset=utf-8" if kind.startswith("text") or "javascript" in kind
                                                else ""), extra={"Cache-Control": "no-cache"})


def theme_css() -> str:
    """The desktop's own palette (formal style, violet accent) as CSS variables, light and dark."""
    def block(mode: str) -> str:
        palette = theme_palette(mode, "violet", "formal")
        # Text on the accent: white on the light theme's deep violet, the window's own ink on the dark one's pale one.
        ink = "#FFFFFF" if mode == "light" else palette["window"]
        return "".join(f"--c-{name.replace('_', '-')}:{value};" for name, value in palette.items()
                       if isinstance(value, str)) + f"--c-on-accent:{ink};"
    return (f":root{{color-scheme:light dark;{block('light')}}}"
            f"@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{{block('dark')}}}}}"
            f":root[data-theme=dark]{{color-scheme:dark;{block('dark')}}}"
            f":root[data-theme=light]{{color-scheme:light;{block('light')}}}")


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], web: Web):
        self.web = web
        super().__init__(address, Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bc250-control-center web",
                                     description="BC250 Control Center local web interface")
    parser.add_argument("--host", default="", help="address to listen on (default: this computer only, or the "
                                                   "local network when it was turned on in Remote access)")
    parser.add_argument("--port", type=int, default=0, help=f"port (default {web_access.DEFAULT_PORT})")
    args = parser.parse_args(argv)
    options = web_access.options()
    host = args.host or ("0.0.0.0" if options["lan"] else "127.0.0.1")  # nosec B104 - only when the owner turned it on
    port = args.port or options["port"]
    os.environ[TERMINAL_AUTH_ENV] = "1"  # passwords are asked on the job's console, never in a window
    logging.basicConfig(level=logging.WARNING)
    key = web_access.access_key()
    web = Web()
    set_language(web.language)
    set_translator(tr)
    server = Server((host, port), web)
    web_access.write_pid()
    print(f"BC250 Control Center web: http://{host}:{port}", flush=True)
    if sys.stdout.isatty():  # never into a journal: the key opens hardware controls
        print(f"Access key: {key}", flush=True)
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
