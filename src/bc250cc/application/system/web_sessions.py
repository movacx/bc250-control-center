"""Browser-session operations exposed to the HTTP adapter."""
from bc250cc.infrastructure.web_devices import (
    MAX_SESSION_SECONDS,
    PERMANENT_SECONDS,
    approve,
    devices,
    identity,
    is_permanent,
    register,
    revoke,
    revoke_all,
    session,
)

__all__ = ['MAX_SESSION_SECONDS', 'PERMANENT_SECONDS', 'approve', 'devices', 'identity', 'is_permanent',
           'register', 'revoke', 'revoke_all', 'session']
