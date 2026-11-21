"""Optional hardware around the board: case pieces, the TV and the receiver.

Each accessory module pins one upstream release and exposes the same four
things: ``inventory`` (read-only state), ``install_command`` and
``remove_command`` (terminal workflows) and, where it has one, a way to open
its own configuration (for TV control, a test that wakes the TV).
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import hdmi_ac3, hdmi_cec, openlinkhub, thermalright, vram_sensor, vrm_sensor

logger = logging.getLogger(__name__)

ACCESSORIES = ("thermalright", "corsair", "hdmi_ac3", "hdmi_cec", "vram_sensor", "vrm_sensor", "apu_telemetry")
#: Installed through its own workflow (``gestionar_apu_telemetry``), not a
#: terminal command from here; listed for its card's state only.
SERVICE_ACCESSORIES = frozenset({"apu_telemetry"})
#: What TV control adds to install and remove: the TV waking at session start and standing by at power-off.
CEC_AUTOMATION = frozenset({"wake-install", "wake-remove", "poweroff-install", "poweroff-remove"})


def accessory_inventory(family: str, tool_dir: Path, *, distro_id: str = "", immutable: bool = False) -> dict:
    """Each accessory's state, probed on its own.

    One probe that fails (an unexpected exception on a system nobody tested)
    must not blank every card: that accessory reports ``error`` with the
    reason, which is logged, and the others still answer.
    """
    from ..apu_telemetry_service import accessory_state

    probes = {
        "thermalright": lambda: thermalright.inventory(family),
        "corsair": lambda: openlinkhub.inventory(tool_dir),
        "hdmi_ac3": lambda: hdmi_ac3.inventory(family),
        "hdmi_cec": lambda: hdmi_cec.inventory(family, tool_dir),
        "vram_sensor": lambda: vram_sensor.inventory(family),
        "vrm_sensor": lambda: vrm_sensor.inventory(family),
        "apu_telemetry": lambda: accessory_state(family=family, distro_id=distro_id, immutable=immutable),
    }
    states = {}
    for key, probe in probes.items():
        try:
            states[key] = probe()
        except Exception as error:  # noqa: BLE001 - isolated per accessory, and logged
            logger.warning("Accessory probe %s failed on %s", key, family or "unknown", exc_info=True)
            states[key] = {"state": "error", "error": f"{type(error).__name__}: {error}"}
    return states


def accessory_command(component: str, action: str, *, family: str, tool_dir: Path) -> str:
    """The terminal workflow for ``action`` (``install`` or ``remove``)."""
    if component == "hdmi_cec" and action in CEC_AUTOMATION:
        family = str(family or "").strip().lower()
        return {
            "wake-install": lambda: hdmi_cec.wake_install_command(family),
            "wake-remove": hdmi_cec.wake_remove_command,
            "poweroff-install": lambda: hdmi_cec.poweroff_install_command(family),
            "poweroff-remove": lambda: hdmi_cec.poweroff_remove_command(family),
        }[action]()
    if action not in {"install", "remove"}:
        raise ValueError(f"Unsupported accessory action: {action or '--'}")
    if component == "thermalright":
        return (thermalright.install_command if action == "install" else thermalright.remove_command)(family)
    if component == "corsair":
        return (openlinkhub.install_command if action == "install" else openlinkhub.remove_command)(tool_dir)
    if component == "hdmi_ac3":
        return (hdmi_ac3.install_command if action == "install" else hdmi_ac3.remove_command)(family)
    if component == "hdmi_cec":
        return (hdmi_cec.install_command if action == "install" else hdmi_cec.remove_command)(family, tool_dir)
    if component == "vram_sensor":
        return (vram_sensor.install_command if action == "install" else vram_sensor.remove_command)(family)
    if component == "vrm_sensor":
        return (vrm_sensor.install_command if action == "install" else vrm_sensor.remove_command)(family)
    raise ValueError(f"Unsupported accessory: {component or '--'}")
