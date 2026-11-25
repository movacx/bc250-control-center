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
import time
from pathlib import Path

from .content import size
from .i18n import tr, tr_format


def desktop_setting(key: str, default: str) -> str:
    """One of the desktop's [settings], read from its ini file without Qt."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    parser = configparser.ConfigParser()
    try:
        parser.read(config / "bc250-control-center" / "ui.conf", encoding="utf-8")
    except configparser.Error:
        return default
    return parser.get("settings", key, fallback=default).strip()


CHECK_EVERY = 30 * 60.0


def update_checks_enabled() -> bool:
    """The desktop's own switch (Settings › Updates)."""
    return desktop_setting("update_check", "true").lower() in {"1", "true", "yes", "on"}


def desktop_temperature_unit() -> str:
    return desktop_setting("temperature_unit", "celsius")


def check_in_background(ctx, *, force: bool = False) -> None:
    """Ask off the drawing thread, and again every half hour: the interface can stay open for days.

    A status lands in ``ctx.state("ui")["update"]``. No network means no
    status, and nothing is said. ``force`` asks once more, now.
    """
    if not force and not update_checks_enabled():
        return

    def check() -> None:
        from bc250cc.application.system.updates import check_for_update

        status = check_for_update(force=force)
        with ctx.lock:
            if status.reachable or force:  # a lost connection does not take back what was already known
                ctx.state("ui")["update"] = status if status.reachable else None

    def keep_checking() -> None:
        while True:
            check()
            if force:
                return
            time.sleep(CHECK_EVERY)

    threading.Thread(target=keep_checking, name="bc250-tui-update-check", daemon=True).start()


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
