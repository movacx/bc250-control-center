"""Core-unlock choices for the terminal and browser frontends."""

from __future__ import annotations

import re

from bc250cc.infrastructure.core_unlock_attempts import chosen_mask, record_attempt

__all__ = [
    "CORE_MASK_BOOT_RISK", "CORE_MASK_PICK_HINT", "IGNORE_CORE_MASK_HINT", "IGNORE_CORE_MASK_LABEL",
    "CORE_MASK_READ_TEXT", "CORE_MASK_SEEN", "CORE_MASK_SEEN_TEXT", "CORE_MASK_STANDARD_TEXT", "CORE_MASK_STOCK",
    "CORE_MASK_WARNINGS", "accepted_mask", "chosen_mask", "core_unlock_controls", "is_six_core_mask",
    "record_attempt", "reported_core_mask",
]

CORE_MASK_STOCK = 0x77
#: Masks read on real boards: 0xB7 (R-643035c1, rw-r-r-0644 issue 4), 0xE7
#: (issue 37), 0x7D (R-1bad18d0, rw-r-r-0644 issue 2) and 0xD7 (same issue).
CORE_MASK_STANDARD_TEXT = "0x77 · standard (normal check)"
CORE_MASK_SEEN = (0xB7, 0xE7, 0x7D, 0xD7)
#: What an owner said about a mask, in brackets after it (0xE7: issue 37).
CORE_MASK_WARNINGS = {0xE7: "crashed one board: possibly defective cores"}
CORE_MASK_SEEN_TEXT = "{mask} · not verified"
CORE_MASK_READ_TEXT = "{mask} · read on this board"
#: The sentences shared by the mask list, the force box and both confirmations.
CORE_MASK_PICK_HINT = (
    "Pick the mask the unlock tool reported for this board. It goes ahead only "
    "when the board really reads that mask."
)
CORE_MASK_BOOT_RISK = (
    "A board with another mask may fail to start after the unlock. Unplugging it "
    "for a few seconds brings it back to 6 cores."
)
IGNORE_CORE_MASK_LABEL = "Force a non-standard core mask (-f)"
IGNORE_CORE_MASK_HINT = (
    "The unlock tool refuses boards whose core mask is not 0x77, because a "
    "different mask usually means the factory disabled cores that were "
    "defective. This passes -f to skip that check: all 8 cores are enabled."
)


def is_six_core_mask(mask: int) -> bool:
    """Three enabled cores on each four-core CCX, the only shape the tools accept."""
    return 0 <= mask <= 0xFF and (mask & 0x0F).bit_count() == 3 and (mask & 0xF0).bit_count() == 3


_REPORTED_MASK = re.compile(
    r"core (?:presence )?mask(?: is)?:?\s+0x(?:0{6})?([0-9a-f]{2})\b|mask still 0x([0-9a-f]{2})\b", re.I
)


def reported_core_mask(text: object) -> int | None:
    """The 6-core mask a tool's message names for this board, or None.

    Both tools print the mask they read before refusing, and the boot service
    keeps it in its note; nothing readable without root says it.
    """
    for match in _REPORTED_MASK.finditer(str(text or "")):
        mask = int(match[1] or match[2], 16)
        if is_six_core_mask(mask):
            return mask
    return None


def accepted_mask(core_mask: int | None, force: bool = False) -> int | None:
    """The mask to hand the tool: none when the check is skipped or it is the standard one."""
    return None if force or core_mask in (None, CORE_MASK_STOCK) else int(core_mask)


def core_unlock_controls(unlock: dict) -> dict:
    persistence = unlock.get("persistence") or {}
    installed = bool(persistence.get("boot_service_installed"))
    active = bool(persistence.get("boot_service_active"))
    repair = persistence.get("boot_service_repair")
    supported = bool(unlock.get("persistent_supported"))
    helper = bool(unlock.get("helper_ready"))
    unlocked = bool(unlock.get("unlocked"))
    note = ""
    if active:
        status, action = "In use", "Persistence active"
    elif repair == "outdated":
        status, action = "Update available", "Update persistence"
        note = (
            "The boot service was installed by an earlier version of the tool. "
            "Update installs the current one, which also starts on systems "
            "with SELinux such as Bazzite."
        )
    elif repair:
        status, action = "Needs repair", "Repair persistence"
        note = (
            "The boot service did not run when this system started. "
            "Repair installs it again in a way this system allows."
        )
    elif installed:
        status, action = "Service stopped", "Install persistence again"
        note = str(persistence.get("boot_service_note") or persistence.get("boot_service_status") or "")
    else:
        status = "Not installed"
        action = "Make the unlock permanent" if unlocked else "Install persistence and restart"

    hint = ""
    if not supported:
        hint = "Persistence needs a BC-250 running systemd."
    elif not helper:
        hint = "Reinstall the local application package to install the privileged helper."
    elif not unlock.get("persistent_repository_ready") and not active:
        hint = "The persistence tool is downloaded first, then installed."

    return {
        "installed": installed,
        "offered": supported or installed,
        "status": status,
        "action": action,
        "note": note,
        "hint": hint,
        "temporary_allowed": bool(
            unlock.get("supported_stock_shape") and not unlocked
            and helper and unlock.get("repository_ready")
        ),
        "persist_allowed": bool(
            supported and helper and not active
            and (unlocked or unlock.get("supported_stock_shape"))
        ),
        "remove_allowed": installed and helper,
    }
