"""GDDR6 readiness: reuse the desktop's guards, never start hardware on a read."""
from dataclasses import fields

from frontends.desktop.core.gddr6_monitor import LIVE_SESSION_SECONDS, Gddr6Reading


def readiness(service) -> dict:
    status = service.estado_gddr6_memory_temp()
    status = status if isinstance(status, dict) else {}
    values = {field.name: status[field.name] for field in fields(Gddr6Reading) if field.name in status}
    external = status.get("external") or {}
    values.update(external_state=str(external.get("state") or ""), manual_override=False,
                  patch_active=bool(status.get("patch_active") or external.get("state") == "active"))
    reading = Gddr6Reading(**values)
    can_monitor = reading.can_monitor and reading.helper_ready
    return {**status, "can_monitor": can_monitor,
            "blocker": reading.blocker() if not can_monitor else "",
            "session_seconds": LIVE_SESSION_SECONDS}


class Gddr6Page:
    interval = 15.0

    def load(self, ctx):
        return readiness(ctx.service)
