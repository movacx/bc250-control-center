"""Everything a phone needs to connect, found and put right as one action.

The pieces are the same ones offered separately (web access, the local
network, the firewall, the local name), in the order each needs the one
before. What is already right is never touched.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from bc250cc.application.system import web_access
from bc250cc.shared.errors import ActionNeeded

START, LAN, FIREWALL, NAME = "start", "lan", "firewall", "name"
#: How each step reads, with the words of its own button.
LABELS = {START: "Start web access", LAN: "Reachable from the local network",
          FIREWALL: "Configure LAN firewall", NAME: "Repair local address"}
#: A name just published takes a moment to resolve: only what is still wrong then is repaired.
NAME_SECONDS = 12.0


def pending(status: dict) -> list[str]:
    """What is missing now and can be put right. Firewall and name are only known once the rest is on."""
    steps = []
    if not status.get("lan") or not status.get("tls", True):
        steps.append(LAN)  # first, so the server starts once and already as wanted
    if not status.get("running"):
        steps.append(START)
    if steps:
        return steps
    if (status.get("firewall") or {}).get("repairable"):
        steps.append(FIREWALL)
    if (status.get("name_health") or {}).get("repairable"):
        steps.append(NAME)
    return steps


def may_follow(steps: list[str]) -> bool:
    """Whether the firewall and the name are still to be looked at after ``steps``."""
    return START in steps or LAN in steps


def _settled_name(status: Callable[[], dict], sleep: Callable[[float], None], clock: Callable[[], float]) -> dict:
    end = clock() + NAME_SECONDS
    state = status()
    while (state.get("name_health") or {}).get("repairable") and clock() < end:
        sleep(1.0)
        state = status()
    return state


def apply(say: Callable[[str], None] = lambda step: None, *, status=None, sleep=time.sleep, clock=time.monotonic) -> dict:
    """Do what is missing, in order; the first failure ends it and says why.

    ``say`` gets each step as it starts. Returns the final status.
    """
    status = status or web_access.status
    state = status()
    if not state.get("lan") or not state.get("tls", True):
        say(LAN)
        web_access.configure(lan=True, tls=True)
        state = status()
    if not state.get("running"):
        say(START)
        web_access.start()
        state = status()
    if not state.get("running"):
        raise ActionNeeded("Remote access could not start, even after Control Center tried to repair it. "
                           "Restart the computer and try again. If it still does not start, send a problem "
                           "report from Black Box: it includes the details.")
    if (state.get("firewall") or {}).get("repairable"):
        say(FIREWALL)
        result = web_access.repair_firewall() or {}
        if result.get("state") == "blocked":
            raise ActionNeeded("LAN firewall repair could not finish. Check its status before retrying.")
    if (_settled_name(status, sleep, clock).get("name_health") or {}).get("repairable"):
        say(NAME)
        web_access.repair_local_name()
    return status()
