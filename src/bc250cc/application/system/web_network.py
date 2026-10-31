"""Local network policy used by the HTTP adapter."""
from bc250cc.infrastructure.web_network import (
    LOCAL_ALIAS,
    addresses,
    allows,
    home_networks,
    local_hostname,
)

__all__ = ['LOCAL_ALIAS', 'addresses', 'allows', 'home_networks', 'local_hostname']
