"""Local web ownership and SSH controls for a keyboard-only terminal."""
from __future__ import annotations

import time

from bc250cc.application.system import remote_access, web_access

from ..content import Choice, Field, Gap, Heading, Note
from ..i18n import tr
from .base import Page, guarded

PRIVACY_SECONDS = 300


class RemoteAccessPage(Page):
    key = "remote"
    title = "Remote access"
    interval = 3.0

    def tabs(self, ctx):
        return [("web", tr("Remote access")), ("devices", tr("Connected devices")), ("ssh", "SSH")]

    def load(self, ctx):
        return {"web": web_access.status(), "ssh": remote_access.status()}

    def build(self, ctx, data, tab, ui):
        data = data or {}
        state = ctx.state(self.key)
        if time.monotonic() >= state.get("visible_until", 0):
            return [Heading(tr("Information protected")), Note(tr("Access keys, codes and devices are hidden."), "dim"),
                    Choice(tr("Show information"), lambda ui_: state.update(
                        visible_until=time.monotonic() + PRIVACY_SECONDS))]
        out = [Choice(tr("Lock view"), lambda ui_: state.update(visible_until=0)), Gap()]
        if tab == "ssh":
            return out + self._ssh(ctx, data.get("ssh") or {})
        web = data.get("web") or {}
        if tab == "devices":
            return out + self._devices(web)

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
        out += [Heading(tr("Remote access")), Field(tr("Status"), tr("Active" if web.get("running") else "Stopped")),
                *[Field(tr("Address"), str(url)) for url in urls], Field(tr("Access key"), str(web.get("key") or "--")),
                Choice(tr("Stop web access") if web.get("running") else tr("Start web access"),
                       run("Stop web access" if web.get("running") else "Start web access",
                           web_access.stop if web.get("running") else web_access.start)),
                Choice(tr("New access key"), run("New access key", lambda: (web_access.access_key(renew=True), None)[1], True)),
                Choice(f"[{'x' if web.get('lan') else ' '}] {tr('Reachable from the local network')}",
                       run("Reachable from the local network", lambda: web_access.configure(lan=not web.get("lan")))),
                Choice("TCP", port, str(web.get("port") or web_access.DEFAULT_PORT))]
        startup = web.get("autostart") or {}
        out += [Choice(f"[{'x' if startup.get('enabled') else ' '}] {tr('Start with the session')}",
                       run("Start with the session", lambda: web_access.set_autostart(not startup.get("enabled"))),
                       enabled=bool(startup.get("supported"))),
                Field("SHA-256", str(web.get("trust_fingerprint") or "--"))]
        return out

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
                if ui_.confirm(tr(label), danger=True):
                    guarded(ui_, tr(label), lambda: remote_access.configure(**updates))
            return handler

        supported = bool(ssh.get("supported", ssh.get("systemd"))) and bool(ssh.get("unit"))
        addresses = ssh.get("addresses") or []
        port, user = ssh.get("port", 22), ssh.get("user", "")
        return [Heading("SSH"), Field(tr("Status"), tr("Active" if active else "Stopped")),
                Field(tr("Boot persistence"), tr("Enabled" if boot else "Disabled")),
                *[Field(tr("Command"), f"ssh -p {port} {user}@{address}") for address in addresses],
                Note(str(ssh.get("detail") or ""), "dim"),
                Choice(tr("Stop SSH" if active else "Start SSH"),
                       change("Stop SSH" if active else "Start SSH", active=not active), enabled=supported),
                Choice(tr("Disable SSH at boot" if boot else "Enable SSH at boot"),
                       change("Disable SSH at boot" if boot else "Enable SSH at boot", boot=not boot), enabled=supported)]
