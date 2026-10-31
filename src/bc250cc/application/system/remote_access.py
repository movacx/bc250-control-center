"""Remote access (the SSH server) for the frontends."""

from bc250cc.infrastructure.remote_access import configure, set_enabled, status

__all__ = ["configure", "set_enabled", "status"]
