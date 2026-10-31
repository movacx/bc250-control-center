"""Optional, unprivileged LAN alias tied to the web server's lifetime."""
from __future__ import annotations

import ipaddress
import shutil
import subprocess
import threading

from bc250cc.infrastructure import web_network
from bc250cc.infrastructure.remote_access import addresses


class LanAlias:
    """Avahi owns collision detection; never change the OS hostname or DNS."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._children = {}
        self._thread = None

    def __enter__(self):
        self._publisher = (shutil.which("avahi-publish-address") or shutil.which("avahi-publish")) if self.enabled else None
        if self._publisher:
            self._refresh()
            self._thread = threading.Thread(target=self._watch, daemon=True)
            self._thread.start()
        return self

    def _watch(self):
        while not self._stop.wait(2):
            self._refresh()

    def _refresh(self):
        networks = web_network.home_networks()
        wanted = {ip for ip in addresses() if networks and web_network.allows(ip, networks)
                  and not ipaddress.ip_address(ip).is_loopback}
        with self._lock:
            if self._stop.is_set():
                return
            for ip in list(self._children):
                process = self._children[ip]
                if ip not in wanted or process.poll() is not None:
                    self._end(process)
                    del self._children[ip]
            for ip in sorted(wanted - self._children.keys()):
                try:
                    self._children[ip] = subprocess.Popen(
                        [self._publisher, "--address", "--no-reverse", "--no-fail", web_network.LOCAL_ALIAS, ip],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except OSError:
                    continue  # The IP and machine hostname remain available.

    @staticmethod
    def _end(process):
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def __exit__(self, *_args):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        with self._lock:
            for process in self._children.values():
                self._end(process)
            self._children.clear()
