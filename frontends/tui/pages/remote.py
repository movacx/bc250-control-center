"""Local web ownership and SSH controls for a keyboard-only terminal."""
from __future__ import annotations

from bc250cc.application.system import remote_access, web_access, web_pairing

from ..content import Choice, Field, Gap, Heading, Note, Panel, Spans
from ..i18n import tr
from .base import Page, guarded, switch


def qr_rows(matrix: list[list[bool]]) -> list[list[tuple[str, str]]]:
    """A QR as half blocks, two rows of modules a line: black on white whatever the theme."""
    if len(matrix) % 2:
        matrix = [*matrix, [False] * len(matrix[0])]
    glyphs = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}
    return [[("".join(glyphs[pair] for pair in zip(upper, lower)), "qr")] for upper, lower in zip(matrix[::2], matrix[1::2])]


class RemoteAccessPage(Page):
    key = "remote"
    title = "Remote access"
    interval = 3.0

    def tabs(self, ctx):
        return [("web", tr("Remote access")), ("devices", tr("Connected devices")), ("ssh", "SSH"), ("network", tr("Network diagnostics"))]

    def __init__(self) -> None:
        self._token = ""  # the one-time code the QR carries; never the access key
        self._known: set[str] | None = None  # paired devices, to say when one is new

    def load(self, ctx):
        web = web_access.status()
        return {"web": web, "ssh": remote_access.status(), "pair": self._pair_token(web)}

    def _pair_token(self, web) -> str:
        """A fresh code while a phone could use it: replaced once used or close to expiry."""
        if not (web.get("running") and web.get("lan")):
            return ""
        try:
            age = web_pairing.age(self._token) if self._token else None
            if age is None or age > web_pairing.RENEW_SECONDS:
                self._token = web_pairing.issue()
        except OSError:
            return ""
        return self._token

    def _pairing(self, ctx, web, token, ui):
        """The QR to scan, or what is missing to show one."""
        urls = [str(url) for url in web.get("urls") or [] if str(url).startswith("https://")]
        if not token or not urls:
            return Panel(tr("Scan to connect"), [Note(tr(
                "Start web access and enable the local network to display your QR here."), "dim")])
        rows = qr_rows(web_access.pairing_matrix(f"{urls[ctx.state(self.key).get('address', 0) % len(urls)]}#pair={token}"))
        note = Note(tr("Scan to pair. The code works once and renews by itself."), "dim")
        width = ui._content_box()[1] if hasattr(ui, "_content_box") else 100
        tall = ui._view() if hasattr(ui, "_view") else 40
        if len(rows[0][0][0]) > width or len(rows) + 2 > tall:  # over the whole terminal instead
            return Panel(tr("Scan to connect"), [Choice(tr("Scan to connect") + " ›", lambda ui_: ui_.show_qr(rows)), note])
        return Panel(tr("Scan to connect"), [Spans(rows), note])

    def _addresses(self, ctx, urls):
        """Where it answers; with several, the one the QR carries."""
        secure = [url for url in urls if url.startswith("https://")]
        if len(secure) < 2:
            return [Field(tr("Address"), url) for url in urls]
        state = ctx.state(self.key)
        at = state.get("address", 0) % len(secure)

        def step(_ui, direction=1):
            state["address"] = (at + direction) % len(secure)

        def pick(ui_):
            chosen = ui_.choose(tr("Address"), list(enumerate(secure)))
            if chosen is not None:
                state["address"] = chosen

        return [Choice(tr("Address"), pick, f"< {secure[at]} >", adjust=step)]

    def _greet(self, web, ui) -> None:
        if "devices" not in web:
            return
        current = {str(item.get("id")) for item in web.get("devices") or []}
        if self._known is not None and current - self._known:
            ui.notify(tr("New device paired"), "ok")
        self._known = current

    def build(self, ctx, data, tab, ui):
        data = data or {}
        if tab == "ssh":
            return self._ssh(ctx, data.get("ssh") or {})
        web = data.get("web") or {}
        self._greet(web, ui)
        if tab == "devices":
            return self._devices(web)
        if tab == "network":
            return self._network(ctx, web)

        def run(label, work, danger=False):
            def handler(ui_):
                if ui_.confirm(tr(label), danger=danger):
                    guarded(ui_, tr(label), work)
            return handler

        def port(ui_):
            value = ui_.ask_int("TCP", 1024, 65535, int(web.get("port") or web_access.DEFAULT_PORT))
            if value is not None and ui_.confirm(f"TCP: {value}"):
                guarded(ui_, tr("Remote access"), lambda: web_access.configure(port=value))

        urls = web.get("urls") or [web.get("local_url") or "--"]
        out = [Field(tr("Status"), tr("Active" if web.get("running") else "Stopped")),
                *self._addresses(ctx, [str(url) for url in urls]), Field(tr("Access key"), str(web.get("key") or "--")),
                Choice(tr("Stop web access") if web.get("running") else tr("Start web access"),
                       run("Stop web access" if web.get("running") else "Start web access",
                           web_access.stop if web.get("running") else web_access.start)),
                Choice(tr("New access key"), run("New access key", lambda: (web_access.access_key(renew=True), None)[1], True)),
                switch(tr("Reachable from the local network"), bool(web.get("lan")),
                       run("Reachable from the local network", lambda: web_access.configure(lan=not web.get("lan")))),
                Choice("TCP", port, str(web.get("port") or web_access.DEFAULT_PORT)),
                Note(tr("Changing the TCP port does not open it in the firewall. Use Network diagnostics to configure LAN access."), "dim"),
                Choice(tr("Network diagnostics"), lambda ui_: ui_.show_tab("network"), tr("Firewall and local address"))]
        startup = web.get("autostart") or {}
        out += [switch(tr("Start with the session"), bool(startup.get("enabled")),
                       run("Start with the session", lambda: web_access.set_autostart(not startup.get("enabled"))),
                       enabled=bool(startup.get("supported"))),
                Field("SHA-256", str(web.get("trust_fingerprint") or "--"))]
        return [Panel(tr("Remote access"), out), self._pairing(ctx, web, data.get("pair") or "", ui)]

    def _network(self, ctx, web):
        out = [Heading(tr("Network diagnostics"))]
        if not web.get("lan"):
            return out + [Note(tr("Enable access from the local network before configuring its firewall."), "warn")]
        port = str(web.get("port") or web_access.DEFAULT_PORT)
        firewall = web.get("firewall") or {}
        health = web.get("name_health") or {}
        backend = {"ufw": "UFW", "firewalld": "firewalld"}.get(firewall.get("backend"), firewall.get("backend") or "—")
        messages = {
            "blocked": "The firewall may block access from other devices. Configure LAN access below.",
            "needs_check": "The firewall needs an administrator check before LAN access can be configured.",
            "ready": "Firewall rules allow this port on the detected LAN networks. Connect your phone to the same network.",
            "inactive": "UFW is inactive. If connection fails, check Wi-Fi isolation and other network filters.",
            "unknown": "The firewall could not be checked. LAN connectivity is not verified.",
            "unsupported": "Custom or multiple firewall managers detected. Automatic changes are unavailable.",
            "no_network": "No connected private IPv4 network was detected.",
            "update_helper": "Update or reinstall Control Center to install the LAN firewall helper.",
        }
        networks = ", ".join(firewall.get("networks") or []) or "—"
        out += [Heading(tr("Firewall")), Field(tr("Manager"), backend), Field("TCP", port),
                Field(tr("Local networks"), networks),
                Note(tr(messages.get(firewall.get("state"), messages["unknown"])),
                     "ok" if firewall.get("state") == "ready" else "warn")]
        if firewall.get("backend") == "ufw" and not firewall.get("verified"):
            out.append(Note(tr("This check uses saved UFW configuration. Administrator authorization is required to verify the active rules."), "dim"))
        if firewall.get("repairable"):
            message = tr("Allow this web port only from the connected private networks? Existing firewall rules are preserved. Administrator authorization is required.")
            message += f"\nTCP {port} · {networks}"
            out.append(Choice(tr("Configure LAN firewall"), self._network_repair(
                ctx, "Configure LAN firewall", message, web_access.repair_firewall,
                messages["ready"])))
        name_messages = {
            "resolver_failed": "The local address is advertised, but this computer cannot resolve it. Use the numeric address or repair name resolution.",
            "publication_failed": "The local address is not advertised yet. Use the numeric address or repair local name discovery.",
            "conflict": "The local address points to another device. Use the numeric address.",
            "unavailable": "Local name resolution could not be checked. Use the numeric address.",
            "ready": "The local address works on this computer. Other devices must support local network name resolution.",
            "disabled": "Start web access to check the local address.",
        }
        out += [Gap(), Heading(tr("Local address")),
                Note(tr(name_messages.get(health.get("status"), name_messages["unavailable"])),
                     "ok" if health.get("status") == "ready" else "warn")]
        if health.get("repairable"):
            message = tr("Repair local name discovery and lookup? This may install Avahi and its resolver module, enable the Avahi service and update the system resolver configuration. A configuration backup is saved and failed resolver changes are reverted. Administrator authorization is required.")
            out.append(Choice(tr("Repair local address"), self._network_repair(
                ctx, "Repair local address", message, web_access.repair_local_name, name_messages["ready"])))
        out += [Choice(tr("Refresh diagnostics"), lambda ui_: ui_.refresh())]
        return out

    def _network_repair(self, ctx, label, message, operation, success):
        def handler(ui_):
            if not ui_.confirm(f"{tr(label)}: {message}", danger=True):
                return
            guarded(ui_, tr(label), operation, success=tr(success))
        return handler

    @staticmethod
    def _devices(web):
        out = [Heading(tr("Connected devices"))]
        for item in web.get("devices") or []:
            identifier = str(item["id"])
            allowed = bool(item.get("control"))
            out.extend([Field(str(item.get("agent") or identifier[:8]), str(item.get("address") or "--")),
                        Field(tr("Device code"), identifier[:8]),
                        Field(tr("Permissions"), tr("Hardware control" if allowed else "Monitoring only"))])

            def permissions(ui_, device=identifier, current=allowed):
                if ui_.confirm(f"{tr('Hardware control')}: {device[:8]}", danger=not current):
                    guarded(ui_, tr("Permissions"), lambda: web_access.set_control(device, not current))

            def revoke(ui_, device=identifier):
                if ui_.confirm(f"{tr('Disconnect')}: {device[:8]}", danger=True):
                    guarded(ui_, tr("Disconnect"), lambda: web_access.revoke(device))

            def lifetime(ui_, device=identifier):
                minutes = ui_.ask_int(tr("Custom session duration in minutes"), 1, 525600, 60)
                if minutes is not None:
                    guarded(ui_, tr("Custom session duration in minutes"), lambda: web_access.set_lifetime(device, minutes * 60))

            out.extend([Choice(tr("Monitoring only") if allowed else tr("Allow hardware control"), permissions),
                        Choice(tr("Custom session duration in minutes"), lifetime), Choice(tr("Disconnect"), revoke), Gap()])
        return out if len(out) > 1 else out + [Note(tr("No connected browsers."), "dim")]

    @staticmethod
    def _ssh(ctx, ssh):
        active, boot = bool(ssh.get("active")), bool(ssh.get("enabled"))

        def change(label, **updates):
            def handler(ui_):
                if ui_.confirm(f"SSH: {tr(label)}", danger=True):
                    guarded(ui_, f"SSH · {tr(label)}", lambda: remote_access.configure(**updates))
            return handler

        supported = bool(ssh.get("supported", ssh.get("systemd"))) and bool(ssh.get("unit"))
        addresses = ssh.get("addresses") or []
        port, user = ssh.get("port", 22), ssh.get("user", "")
        return [Heading("SSH"), Field(tr("Status"), tr("Active" if active else "Stopped")),
                Field(tr("Boot persistence"), tr("Enabled" if boot else "Disabled")),
                *[Field(tr("Command"), f"ssh -p {port} {user}@{address}") for address in addresses],
                Note(str(ssh.get("detail") or ""), "dim"),
                Choice(tr("Stop" if active else "Start") + " SSH", change("Stop" if active else "Start", active=not active), enabled=supported),
                Choice(f"{tr('Disable' if boot else 'Enable')} · {tr('Boot persistence')}",
                       change("Disable" if boot else "Enable", boot=not boot), enabled=supported)]
