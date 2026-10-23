"""What the GPU, CPU and Fans pages say after exporting profiles to Decky.

The export only writes a file under /etc; whether anything reads it depends
on Decky and the BC250 Quick Access plugin being installed, which the export
itself never checks. The pages look at the plugin inventory after writing,
so "exported" is not claimed for a panel that does not exist yet.
"""

from __future__ import annotations

from typing import Callable, Iterable

from ..i18n import tr, tr_format


def export_and_check_plugin(controller, export: Callable[[], object]) -> bool | None:
    """Runs ``export`` (in the worker), then reports whether the plugin is there.

    ``None`` means the inventory could not be read; the export still happened.
    """
    export()
    probe = getattr(controller, "estado_quick_access_decky", None)
    if probe is None:
        return None
    try:
        inventory = probe()
    except Exception:  # noqa: BLE001 - the export already succeeded
        return None
    if not isinstance(inventory, dict):
        return None
    return bool(inventory.get("decky_detected") and inventory.get("plugin_present"))


def export_message(plugin_installed: bool | None, notes: Iterable[str] = ()) -> str:
    if plugin_installed is False:
        message = tr(
            "Profiles saved for Decky Quick Access, but the plugin is not installed yet. "
            "Its panel will use them once BC250 Quick Access is installed."
        )
    else:
        message = tr("Profiles exported to Decky Quick Access.")
    return " ".join((message, *notes))


def export_tone(plugin_installed: bool | None) -> str:
    return "blue" if plugin_installed is False else "green"


def fan_export_notes(raised: Iterable[tuple[str, int, int]]) -> list[str]:
    """Which fans the Decky presets drive, and any speed lifted to its floor."""
    notes = [tr(
        "In Game Mode each preset sets every active system fan (PWM3–PWM8) "
        "together and never PWM2, not just the channel selected here."
    )]
    for name, requested, published in raised:
        notes.append(tr_format(
            "{name}: {requested} % → {published} % in Decky.",
            name=name, requested=requested, published=published,
        ))
    return notes
