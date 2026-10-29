"""New versions and problem reports: the desktop's two outward-facing features.

Both go through the same layers as the desktop's updater and report form, so a
version is installed only by the plan that fits this installation and a report
carries the same facts. Everything that touches the network runs in the
console pane or on a background thread, never on the drawing thread.
"""

from __future__ import annotations

import configparser
import os
import threading
from pathlib import Path

from .content import size
from .i18n import tr, tr_format


def update_checks_enabled() -> bool:
    """The desktop's own switch (Settings › Updates), read from its ini file."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    parser = configparser.ConfigParser()
    try:
        parser.read(config / "bc250-control-center" / "ui.conf", encoding="utf-8")
    except configparser.Error:
        return True
    return parser.get("settings", "update_check", fallback="true").strip().lower() in {"1", "true", "yes", "on"}


def check_in_background(ctx, *, force: bool = False) -> None:
    """Ask once, off the drawing thread; a status lands in ``ctx.state("ui")["update"]``.

    The published version is cached for hours below, so this reaches the
    network at most once per window. No network means no status, and nothing
    is said.
    """
    if not force and not update_checks_enabled():
        return

    def check() -> None:
        from bc250cc.application.system.updates import check_for_update

        status = check_for_update(force=force)
        with ctx.lock:
            ctx.state("ui")["update"] = status if status.reachable else None

    threading.Thread(target=check, name="bc250-tui-update-check", daemon=True).start()


def available_version(ctx) -> str:
    status = ctx.state("ui").get("update")
    return str(status.published) if status is not None and status.update_available else ""


def install_update(ctx, family: str):
    """Fetch the release, download what this installation needs and run its installer (console pane)."""
    from bc250cc.application.system.updates import (
        UpdateError,
        detect_install_source,
        download_asset,
        fetch_latest_release,
        plan_update,
    )

    print(tr("Reading the latest release…"))
    release = fetch_latest_release()
    print(tr_format("Version {version} is available", version=release.version))
    plan = plan_update(release, detect_install_source(), os_family=family)
    if plan.kind == "manual":
        raise UpdateError(f"{plan.reason} {release.page_url}".strip())
    package = None
    if plan.downloads:
        package = download_asset(plan.asset, progress=lambda done, total: print(
            f"\r{plan.asset.name}  {size(done)} / {size(total)}", end="", flush=True))
        print()
    return ctx.service.instalar_actualizacion(plan, str(package) if package else None)


def report(ui, *, title: str = "", log: str = "") -> None:
    """The report form, as questions: a problem (or an idea), what happened, a contact.

    ``title``/``log`` come from a failed workflow and are attached as its log.
    The system facts are read while sending, in the console pane.
    """
    from bc250cc.application.system.feedback import reports as form
    from frontends.desktop.core.report_facts import read_report_facts
    from frontends.desktop.i18n import current_language

    kind = form.KIND_PROBLEM if log else ui.choose(tr("Report a problem or suggest an idea"), [
        (form.KIND_PROBLEM, tr("Report this problem")), (form.KIND_IDEA, tr("Suggest an idea"))])
    if kind is None:
        return
    text = ui.ask_text(tr("What went wrong?") if kind == form.KIND_PROBLEM else tr("Suggestions and ideas"), title)
    if not (text or "").strip():
        return
    contact = ui.ask_text(tr("Telegram or Discord username"), "")
    if contact is None or not ui.confirm(tr("Send") + "?"):
        return

    def send() -> str:
        from bc250cc.shared.version import application_version

        facts = read_report_facts()
        fields = {key: facts[key] for key in ("system", "os_release", "firmware", "history", "attachments",
                                               "install", "distribution", "bios", "cores") if key in facts}
        problem = kind == form.KIND_PROBLEM
        document = form.Report(
            kind=kind, summary=text if problem else "", notes="" if problem else text, contact=contact,
            version=str(facts.get("version") or application_version()), opened_from="tui",
            language=current_language(), workflow_title=title if log else "", workflow_log=form.clean_log(log),
            **fields)
        try:
            return f"{tr('Thanks, it was sent')} ({form.submit(document)})"
        except form.ReportError as error:
            message = tr_format("It was not sent: {reason}. What you wrote is still here.",
                                reason=tr(str(error)).rstrip("."))
            if error.saved is not None:
                message += " " + tr_format("A copy was saved to {path}.", path=str(error.saved))
            raise RuntimeError(message) from error

    ok, result = ui.run(tr("Report a problem or suggest an idea"), send)
    ui.notify(str(result), "ok" if ok else "bad")
