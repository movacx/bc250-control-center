"""Which compatibility rows each distribution gets. Shared by the desktop and the terminal interface."""

from __future__ import annotations

#: Where the SteamOS toolkit's own row replaces ours. Ours stays visible for
#: anyone who already has it installed, so it can still be updated or removed.
SUPERSEDED_WHEN = frozenset({"", "not-installed", "unsupported", "managed-elsewhere", "hardware-vcn", "unknown"})

#: ACPI states that mean this application put something there.
NATIVE_ACPI_PRESENT = frozenset({"active", "pending-reboot", "not-active", "incomplete",
                                 "outdated", "needs-repair", "needs-check"})


def distribution_group(family: str) -> str:
    family = str(family or "").strip().lower()
    if family in {"arch", "cachyos", "manjaro"}:
        return "arch"
    if family in {"ubuntu", "debian"}:
        return "debian"
    if family in {"steamos", "bazzite", "fedora"}:
        return family
    return "other"


def acpi_offered(group: str, status: str) -> bool:
    """SteamOS uses the toolkit's ACPI row; ours stays there only while one of ours is in place."""
    return status in NATIVE_ACPI_PRESENT if group == "steamos" else group in {"arch", "bazzite"}


def native_row_offered(group: str, state: str) -> bool:
    """A row of ours that the SteamOS toolkit also has (VA-API, AC-3, HDMI-CEC)."""
    return group != "steamos" or state not in SUPERSEDED_WHEN
