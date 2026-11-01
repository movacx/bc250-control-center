"""Browser-session operations exposed to the HTTP adapter."""
from bc250cc.infrastructure.web_devices import (
    MAX_SESSION_SECONDS,
    devices,
    identity,
    register,
    revoke,
    revoke_all,
    session,
)

__all__ = ['MAX_SESSION_SECONDS', 'devices', 'identity', 'register', 'revoke', 'revoke_all', 'session']
