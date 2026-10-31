"""Follow DHCP and late network availability without restarting browser sessions."""
from __future__ import annotations

import logging
import threading

from bc250cc.application.system import web_access, web_network

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 2


class LanMonitor:
    def __init__(self, server, *, enabled: bool):
        self.server, self.enabled = server, enabled
        self._addresses = None
        self._stop = threading.Event()
        self._thread = None
        self._failed = False

    def refresh(self):
        # Replace the snapshot, including an empty result. Never keep a network
        # allowed just because Wi-Fi disappeared or discovery failed.
        try:
            networks = web_network.home_networks()
        except Exception:
            self.server.allowed_networks = []
            raise
        self.server.allowed_networks = networks
        if not self.server.secure:
            return
        addresses = tuple(sorted(address for address in web_network.addresses()
                                 if web_network.allows(address, self.server.allowed_networks)))
        if addresses != self._addresses:
            certificate = web_access.tls_certificate()
            if not self._stop.is_set():
                self.server.update_certificate(certificate)
                self._addresses = addresses

    def _tick(self):
        try:
            self.refresh()
            self._failed = False
        except Exception:
            # Discovery errors must fail closed. A certificate failure retains
            # the previous valid adapter and is retried on the next tick.
            if not self._failed:
                logger.warning("Could not refresh web LAN state; retrying")
            self._failed = True

    def _watch(self):
        self._tick()
        while not self._stop.wait(REFRESH_SECONDS):
            self._tick()

    def __enter__(self):
        if self.enabled:
            self._thread = threading.Thread(target=self._watch, name="bc250-web-network", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_args):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
