"""About: this build, its folders, what is new, the project and everything it builds on."""

from __future__ import annotations

import os
from pathlib import Path

from bc250cc.shared.version import __version__
from frontends.desktop.core.developer_note_text import (
    KOFI_URL,
    PARAGRAPHS,
    SIGNATURE,
    THANKS,
    TITLE,
    WHEN,
)
from frontends.desktop.core.official_repositories import OFFICIAL_REPOSITORIES
from frontends.desktop.i18n import project_overview

from ..content import Choice, Field, Info, Note, Panel
from ..i18n import tr, tr_format
from ..support import available_version, check_in_background, install_update
from .base import Page, guarded, os_family

TABS = (("about", "About"), ("updates", "What's new"), ("overview", "Project overview"), ("repositories", "Official repositories"))


class AboutPage(Page):
    key = "about"
    title = "About"
    loads = False

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def build(self, ctx, data, tab, ui):
        return {"updates": self._updates, "overview": self._overview, "repositories": self._repositories}.get(tab, self._about)(ctx)

    def _about(self, ctx):
        status, newer = ctx.state("ui").get("update"), available_version(ctx)
        if newer:
            state, tone = tr_format("Version {version} is available", version=newer), "warn"
        elif status is not None:
            state, tone = tr("You have the latest version."), "ok"
        else:  # not asked yet, switched off, or no network: nothing to claim
            state, tone = "", ""
        home = Path.home()
        data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "bc250-control-center"
        logs = Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "bc250-control-center"
        config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "bc250-control-center"
        note = "\n\n".join([tr(TITLE) + ". " + tr(WHEN), *(tr(part) for part in PARAGRAPHS), tr(THANKS), SIGNATURE])
        return [
            Panel("BC250 Control Center", [
                Field(tr("Version"), f"{__version__}  ·  {state}" if state else __version__, tone),
                *([Choice(tr("Update now"), lambda ui_: self._update(ctx, ui_), tone="primary"),
                   Choice(tr("What's new"), lambda ui_: ui_.show_tab("updates"))] if newer else []),
                Choice(tr("Check for updates"), lambda ui_: self._check(ctx, ui_))]),
            Panel(tr("Application"), [
                Field(tr("Configuration folder"), str(config)), Field(tr("Data folder"), str(data)),
                Field(tr("State and logs"), str(logs)), Field(tr("System data"), "/var/lib/bc250-control-center")]),
            Panel(tr(TITLE), [Note(tr(WHEN), "warn"), Choice(tr("Details") + " ›", lambda ui_: ui_.show_text(tr(TITLE), note)),
                              Field("Ko-fi", KOFI_URL), Field("Discord", "@_movacx")]),
            Panel("GitHub", [Note("https://github.com/movacx/bc250-control-center")])]

    @staticmethod
    def _check(ctx, ui):
        check_in_background(ctx, force=True)
        ui.notify(tr("Checking…"))

    @staticmethod
    def _update(ctx, ui):
        newer = available_version(ctx)
        if newer and ui.confirm(f"{tr('Update now')}: {__version__} → {newer}"):
            guarded(ui, tr("Update now"), lambda: install_update(ctx, os_family(ctx)[0]))

    def _updates(self, ctx):
        state = ctx.state(self.key)

        def read(ui_):
            from bc250cc.application.system.updates import fetch_latest_release

            ok, result = ui_.run(tr("What's new"), fetch_latest_release)
            if ok:
                state["release"] = result

        release = state.get("release")
        if release is None:
            return [Panel(tr("What's new"), [Choice(tr("Check for updates"), read)])]
        # Markdown marks say nothing in a terminal; the words do.
        notes = [line.replace("**", "").replace("`", "").replace("### ", "").replace("## ", "").replace("# ", "") for line in
                 release.notes.splitlines()]
        return [Panel(release.title or release.version, [
            Field(tr("Version"), f"{release.version}  ·  {str(release.published_at)[:10]}"),
            *[Note(line or " ") for line in notes],
            Choice(tr("Update now"), lambda ui_: self._update(ctx, ui_), enabled=bool(available_version(ctx))),
            Choice(tr("Refresh"), read)], wide=True)]

    @staticmethod
    def _overview(ctx):
        blocks = [block.strip() for block in project_overview().split("\n\n") if block.strip()]
        out = [Panel(tr("Project overview"), [Note(blocks[0])], wide=True)] if blocks else []
        for block in blocks[1:]:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            heading = lines[0].rstrip(":") if lines and not lines[0].startswith("•") else ""
            out.append(Panel(heading or "BC250", [Note(line) for line in lines[1 if heading else 0:]]))
        return out

    @staticmethod
    def _repositories(ctx):
        return [Panel(tr("Official repositories"), [
            Choice(tr(name), lambda ui_, n=name, u=url: ui_.show_text(tr(n), u), repository, id=url, info=Info(url))
            for name, repository, url in OFFICIAL_REPOSITORIES], subtitle=tr(
                "BC250 Control Center does not own these tools. They are installed, cloned, or used as credited reference "
                "implementations according to each integration."), badge=str(len(OFFICIAL_REPOSITORIES)), wide=True)]
