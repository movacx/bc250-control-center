"""Optional hardware around the board: case pieces, the TV and the receiver.

Each accessory module pins one upstream release and exposes the same four
things: ``inventory`` (read-only state), ``install_command`` and
``remove_command`` (terminal workflows) and, where it has one, a way to open
its own configuration (for TV control, a test that wakes the TV).
"""

from __future__ import annotations

from pathlib import Path

from . import hdmi_ac3, hdmi_cec, openlinkhub, thermalright

ACCESSORIES = ("thermalright", "corsair", "hdmi_ac3", "hdmi_cec")
#: What TV control adds to install and remove: the TV waking at session start and standing by at power-off.
CEC_AUTOMATION = frozenset({"wake-install", "wake-remove", "poweroff-install", "poweroff-remove"})


def accessory_inventory(family: str, tool_dir: Path) -> dict:
    return {
        "thermalright": thermalright.inventory(family),
        "corsair": openlinkhub.inventory(tool_dir),
        "hdmi_ac3": hdmi_ac3.inventory(family),
        "hdmi_cec": hdmi_cec.inventory(family, tool_dir),
    }


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
    raise ValueError(f"Unsupported accessory: {component or '--'}")
