"""Local web ownership and SSH controls for a keyboard-only terminal."""
from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

from bc250cc.application.system import (
    remote_access,
    web_access,
    web_pairing,
    web_setup,
)

from ..content import (
    Choice,
    Field,
    Gap,
    Info,
    Note,
    Pad,
    PadCell,
    PadRow,
    Panel,
    Spans,
    Split,
)
from ..i18n import tr, tr_format
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
        width = ui._content_box()[1] if hasattr(ui, "_content_box") else 142
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
            return self._devices(ctx, web, ui)
        if tab == "network":
            return self._network(ctx, web)

        def run(label, work, danger=False):
            def handler(ui_):
                if ui_.confirm(tr(label), danger=danger):
                    guarded(ui_, tr(label), work)
            return handler

        def port(ui_):
            current = int(web.get("port") or web_access.DEFAULT_PORT)
            value = ui_.ask_int("TCP", 1024, 65535, current)
            if value is not None and value != current and ui_.confirm(f"TCP: {value}"):
                guarded(ui_, tr("Remote access"), lambda: web_access.configure(port=value))

        running, lan = bool(web.get("running")), bool(web.get("lan"))
        startup = web.get("autostart") or {}
        badge, badge_tone = tr("Active" if running else "Stopped"), "ok" if running else "dim"
        reach = tr("Access is limited to this computer and its home network." if lan else "This computer only")
        notice = self._notice(web)
        controls = [*self._prepare(web), switch(tr("Remote access"), running,
                           run("Stop web access" if running else "Start web access", web_access.stop if running else web_access.start),
                           info=Info(tr("Control and monitor this board from a browser on your home network."))),
                    switch(tr("Reachable from the local network"), lan,
                           run("Reachable from the local network", lambda: web_access.configure(lan=not lan, tls=True)),
                           info=Info(tr("HTTPS is required for home-network access. No router ports or public tunnels are configured by this application."))),
                    switch(tr("Start with the session"), bool(startup.get("enabled")),
                           run("Start with the session", lambda: web_access.set_autostart(not startup.get("enabled"))),
                           enabled=bool(startup.get("supported")),
                           info=Info(blocked=tr("Not available") if not startup.get("supported") else "")),
                    Field(tr("Access key"), str(web.get("key") or "--")),
                    Choice(tr("New access key"), run("New access key", lambda: (web_access.access_key(renew=True), None)[1], True),
                           info=Info(risk=tr("A paired device keeps hardware control until you disconnect it or create a new access key."))),
                    Choice("TCP", port, f"{web.get('port') or web_access.DEFAULT_PORT} ›",
                           info=Info(tr("Changing the TCP port does not open it in the firewall. Use Network diagnostics to configure LAN access.")))]
        urls = web.get("urls") or [web.get("local_url") or "--"]
        pairing = self._pairing(ctx, web, data.get("pair") or "", ui)
        controls += self._addresses(ctx, [str(url) for url in urls])
        certificate_help = tr("Save this board's public CA certificate and transfer it privately to your phone. Check its SHA-256 fingerprint before trusting it. Android: install it as a CA certificate. iPhone/iPad: install the profile, then enable full trust in Certificate Trust Settings. Trust it only on devices you own.")

        def certificate(ui_):
            target = ui_.ask_text(tr("Save public certificate"), str(Path.home() / "BC250-local-authority.crt"))
            if not target:
                return
            destination = Path(target).expanduser()
            if destination.exists() and not ui_.confirm(tr("Save public certificate") + f": {destination}", danger=True):
                return

            def save():
                source = web_access.trust_certificate()
                if source.resolve() != destination.resolve():
                    shutil.copyfile(source, destination)
                return tr("Public certificate saved. The private key stays on this board.")

            guarded(ui_, tr("Save public certificate"), save)

        certificates = Panel(tr("Verify HTTPS on your phone"), [
            Choice("SHA-256 ›",
                   lambda ui_: ui_.show_text(tr("Verify HTTPS on your phone"), str(web.get("trust_fingerprint") or "--") + "\n\n" + certificate_help)),
            Choice(tr("Save public certificate"), certificate, info=Info(certificate_help))])
        status = [*([Note(reach, "dim")] if running else []), *([Note(tr(notice), "warn" if running else "dim")] if notice else [])]
        width = ui._content_box()[1] if hasattr(ui, "_content_box") else 142
        if width < 102:
            return [Panel(tr("Remote access"), status, badge=badge, badge_tone=badge_tone), pairing, Panel(tr("Settings"), controls), certificates]
        return [Panel(tr("Remote access"), [*status, *controls], badge=badge, badge_tone=badge_tone), pairing, certificates]

    @staticmethod
    def _prepare(web):
        """One action for everything a phone still needs, listed before it is done."""
        steps = web_setup.pending(web)
        if not steps:
            return []
        labels = [tr(web_setup.LABELS[step]) for step in steps]
        firewall, name = (tr("Allow this web port only from the connected private networks? Existing firewall rules are preserved. Administrator authorization is required."),
                          tr("Repair local name discovery and lookup? This may install Avahi and its resolver module, enable the Avahi service and update the system resolver configuration. A configuration backup is saved and failed resolver changes are reverted. Administrator authorization is required."))
        follow = web_setup.may_follow(steps)
        question = tr("Control Center does these steps in order and stops at the first that fails:") + "\n" \
            + "\n".join(f"{number}. {label}" for number, label in enumerate(labels, 1))
        if follow:
            question += "\n" + tr("Firewall and local address are checked at the end and fixed only if needed.")
        if follow or web_setup.FIREWALL in steps:
            question += f"\n· {tr('Configure LAN firewall')}: {firewall}"
        if follow or web_setup.NAME in steps:
            question += f"\n· {tr('Repair local address')}: {name}"

        def prepare(ui_):
            if ui_.confirm(f"{tr('Prepare the connection')}: {question}", danger=True):
                def work():
                    web_setup.apply(lambda step: print(f"== {tr(web_setup.LABELS[step])} ==", flush=True))
                    return tr("The connection is ready: scan the code with your phone.")

                guarded(ui_, tr("Prepare the connection"), work)

        return [Choice(tr("Prepare the connection"), prepare, tone="primary", id="prepare",
                       info=Info(tr("Firewall and local address are checked at the end and fixed only if needed."))),
                Note(" · ".join(labels), "dim"), Gap()]

    @staticmethod
    def _notice(web):
        if not web.get("running"):
            return "Start web access to pair a phone."
        if not web.get("lan"):
            return "Turn on local network access below so phones can connect."
        state = (web.get("firewall") or {}).get("state")
        if state in {"blocked", "needs_check", "update_helper"}:
            return "The firewall may be blocking other devices. Use Configure LAN firewall."
        if state == "no_network":
            return "No connected private network was detected. Connect this board to your Wi-Fi or cable."
        return ""

    def _network(self, ctx, web):
        lan = bool(web.get("lan"))
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
        if not lan:
            return [Panel(tr("Network diagnostics"), [
                *self._prepare(web), Note(tr("Enable access from the local network before configuring its firewall."), "dim")],
                badge=tr("Disabled"))]
        firewall_state = tr({"ready": "Ready", "blocked": "Blocked", "inactive": "Inactive"}.get(firewall.get("state"), "Not verified"))
        name_ready = health.get("status") == "ready"
        firewall_blocks = [Field(tr("Manager"), backend), Field("TCP", port),
                Field(tr("Local networks"), networks),
                Note(tr(messages.get(firewall.get("state"), messages["unknown"])))]
        if firewall.get("backend") == "ufw" and not firewall.get("verified"):
            firewall_blocks.append(Note(tr("This check uses saved UFW configuration. Administrator authorization is required to verify the active rules."), "dim"))
        if firewall.get("repairable"):
            message = tr("Allow this web port only from the connected private networks? Existing firewall rules are preserved. Administrator authorization is required.")
            message += f"\nTCP {port} · {networks}"
            firewall_blocks.append(Choice(tr("Configure LAN firewall"), self._network_repair(
                ctx, "Configure LAN firewall", message, web_access.repair_firewall,
                messages["ready"]), tone="primary", info=Info(risk=message)))
        name_messages = {
            "resolver_failed": "The local address is advertised, but this computer cannot resolve it. Use the numeric address or repair name resolution.",
            "publication_failed": "The local address is not advertised yet. Use the numeric address or repair local name discovery.",
            "conflict": "The local address points to another device. Use the numeric address.",
            "unavailable": "Local name resolution could not be checked. Use the numeric address.",
            "ready": "The local address works on this computer. Other devices must support local network name resolution.",
            "disabled": "Start web access to check the local address.",
        }
        name_blocks = [Note(tr(name_messages.get(health.get("status"), name_messages["unavailable"])))]
        if health.get("repairable"):
            message = tr("Repair local name discovery and lookup? This may install Avahi and its resolver module, enable the Avahi service and update the system resolver configuration. A configuration backup is saved and failed resolver changes are reverted. Administrator authorization is required.")
            name_blocks.append(Choice(tr("Repair local address"), self._network_repair(
                ctx, "Repair local address", message, web_access.repair_local_name, name_messages["ready"]), tone="primary", info=Info(risk=message)))
        both = self._prepare(web) if len(web_setup.pending(web)) > 1 else []
        return [*([Panel(tr("Network and connection"), both)] if both else []),
                Panel(tr("Firewall"), firewall_blocks, badge=firewall_state,
                      badge_tone="ok" if firewall.get("state") == "ready" else "warn"),
                Panel(tr("Local address"), name_blocks, badge=tr("Ready" if name_ready else "Not available"),
                      badge_tone="ok" if name_ready else "warn")]

    def _network_repair(self, ctx, label, message, operation, success):
        def handler(ui_):
            if not ui_.confirm(f"{tr(label)}: {message}", danger=True):
                return
            guarded(ui_, tr(label), operation, success=tr(success))
        return handler

    def _devices(self, ctx, web, ui):
        devices = web.get("devices") or []
        if not devices:
            return [Panel(tr("Connected devices"), [Note(tr("No connected browsers.")),
                    Note(tr("Connect your phone to the same Wi-Fi and scan the code. It pairs right away with full hardware control, with no key to type."))])]
        state = ctx.state(self.key)
        selected = next((i for i, item in enumerate(devices) if item["id"] == state.get("device")), 0)
        state["device"] = devices[selected]["id"]

        def place(row, _column=0):
            state["device"] = devices[row]["id"]

        def move(dr, dc):
            row = next((i for i, item in enumerate(devices) if item["id"] == state["device"]), selected) + dr
            if dc or not 0 <= row < len(devices):
                return False
            place(row)
            return True

        def opened(ui_):
            ui_.show_text(tr("Device"), "\n".join(
                f"{header}: {value}" for header, value in zip(headers, values(
                    next(device for device in devices if device["id"] == state["device"])))
            ))

        width = ui._content_box()[1] if hasattr(ui, "_content_box") else 100
        headers = [tr(key) for key in ("IP address", "Permissions", "Status", "Last activity", "Session")]
        shown = list(range(5)) if width >= 120 else [0, 2]
        now = time.time()

        def timestamp(value):
            return datetime.fromtimestamp(float(value)).astimezone().strftime("%d/%m %H:%M") if value else "--"

        def values(item):
            seen = item.get("seen")
            return [str(item.get("address") or "--"), tr("Hardware control" if item.get("control") else "Monitoring only"),
                    tr("Active" if now - float(seen) <= 15 else "Idle") if seen else "--", timestamp(seen),
                    tr("Permanent") if web_access.is_permanent(item) and not item.get("duration_seconds") else timestamp(web_access.deadline(item))]

        rows = [PadRow(self._device_name(item), [PadCell(values(item)[i]) for i in shown]) for item in devices]
        table = Pad([headers[i] for i in shown], rows, (selected, 0), move, opened,
                    place=place, corner=tr("Device"), whole=True)
        item = devices[selected]
        identifier, allowed = str(item["id"]), bool(item.get("control"))

        def permissions(ui_):
            if ui_.confirm(f"{tr('Hardware control')}: {identifier[:8]}", danger=not allowed):
                guarded(ui_, tr("Permissions"), lambda: web_access.set_control(identifier, not allowed))

        def revoke(ui_):
            if ui_.confirm(f"{tr('Disconnect')}: {identifier[:8]}", danger=True):
                guarded(ui_, tr("Disconnect"), lambda: web_access.revoke(identifier))

        def revoke_all(ui_):
            if ui_.confirm(tr("Disconnect all devices"), danger=True):
                guarded(ui_, tr("Disconnect all devices"), web_access.revoke_all)

        def lifetime(ui_):
            options = [(0, tr("Permanent")), *[(minutes, tr(label)) for minutes, label in (
                (15, "15 minutes"), (30, "30 minutes"), (60, "1 hour"), (480, "8 hours"),
                (1440, "24 hours"), (10080, "7 days"), (43200, "30 days"))], (-1, tr("Custom"))]
            minutes = ui_.choose(tr("Session expiry"), options)
            if minutes == -1:
                minutes = ui_.ask_int(tr("Custom session duration in minutes"), 1, 525600, 60)
            if minutes is None:
                return
            if minutes == 0:
                message = tr("Permanent") + " · " + tr("Allow hardware control") + f": {identifier[:8]}"
                if ui_.confirm(message, danger=True):
                    guarded(ui_, tr("Session expiry"), lambda: web_access.approve(identifier))
            else:
                guarded(ui_, tr("Session expiry"), lambda: web_access.set_lifetime(identifier, minutes * 60))

        controls = Panel(self._device_name(item), [
            switch(tr("Hardware control"), allowed, permissions, info=Info(
                tr("Hardware control lets this device change clocks, power and fans."),
                tr("A paired device keeps hardware control until you disconnect it or create a new access key."))),
            Choice(tr("Session expiry"), lifetime, values(item)[4] + " ›", info=Info(
                tr("The selected duration starts now and replaces the inactivity limit for this session."),
                tr("Permanent sessions also enable hardware control."))),
            Choice(tr("Disconnect"), revoke, info=Info(undo=tr(
                "Connect your phone to the same Wi-Fi and scan the code. It pairs right away with full hardware control, with no key to type."))),
            Choice(tr("Disconnect all devices"), revoke_all, tone="bad", info=Info(undo=tr(
                "Connect your phone to the same Wi-Fi and scan the code. It pairs right away with full hardware control, with no key to type.")))])
        detail = [Field(tr("Device code"), identifier[:8]),
                  Note(tr_format("Session started: {time}", time=timestamp(item.get("created"))))]
        detail += [Field(header, value) for i, (header, value) in enumerate(zip(headers, values(item))) if i not in shown]
        return [Panel(tr("Connected devices"), [table], badge=str(len(devices)), wide=True), Split([controls], [Panel(tr("Device"), detail)], ratio=0.55, minimum=84)]

    @staticmethod
    def _device_name(item):
        agent = str(item.get("agent") or "")
        platform = next((name for marker, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                        ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux")) if marker in agent), tr("Browser"))
        browser = next((name for marker, name in (("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
                       ("Safari/", "Safari")) if marker in agent), "")
        return " · ".join(part for part in (platform, browser) if part)

    @staticmethod
    def _ssh(ctx, ssh):
        active, boot = bool(ssh.get("active")), bool(ssh.get("enabled"))

        def change(label, **updates):
            def handler(ui_):
                if ui_.confirm(f"SSH: {tr(label)}", danger=True):
                    guarded(ui_, f"SSH · {tr(label)}", lambda: remote_access.configure(**updates))
            return handler

        supported = bool(ssh.get("supported", ssh.get("systemd"))) and bool(ssh.get("unit"))
        risk = tr("Use it only on a network you trust, and do not open the SSH port to the internet.")
        explanation = tr("SSH gives remote terminal access to your Linux account and files.")
        if not supported:
            missing = (tr("No SSH server is installed. Install the openssh-server package first.") if not ssh.get("unit")
                       else str(ssh.get("detail") or tr("Not available")))
            return [Panel("SSH", [Note(missing), Note(explanation, "dim"), Note(risk, "dim")], badge=tr("Not available"))]
        port, user = ssh.get("port") or 22, str(ssh.get("user") or "")
        commands = []
        for address in ssh.get("addresses") or []:
            host = f"[{address}]" if ":" in address and not address.startswith("[") else address
            commands.append(Note(f"ssh -p {port} {user + '@' if user else ''}{host}"))
        return [Panel("SSH", [
            switch(tr("SSH server"), active, change("Stop" if active else "Start", active=not active), info=Info(explanation, risk)),
            switch(tr("Boot persistence"), boot, change("Disable" if boot else "Enable", boot=not boot), info=Info(explanation, risk))],
                      badge=tr("Active" if active else "Stopped"), badge_tone="ok" if active else "dim"),
                *([Panel(tr("Command"), commands)] if commands else [])]
