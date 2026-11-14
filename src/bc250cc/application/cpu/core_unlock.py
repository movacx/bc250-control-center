"""Core-unlock choices for the terminal and browser frontends."""

from __future__ import annotations


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
