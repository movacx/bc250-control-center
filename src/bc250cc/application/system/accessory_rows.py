"""What every frontend says about an accessory, a sensor driver or the sleep row."""

from __future__ import annotations

STATES = {
    "unsupported": ("Not available here", "gray", ""),
    "not-installed": ("Not installed", "gray", "Install"),
    "reboot-required": ("Restart required", "orange", ""),
    "update-available": ("Update available", "blue", "Update"),
    # Once it works, opening it is what the owner came for; a reinstall
    # is Remove and Install.
    "relogin-required": ("Log out to finish", "orange", ""),
    "installed": ("Installed", "blue", ""),
    "active": ("Active", "green", ""),
    "managed-elsewhere": ("Installed another way", "blue", ""),
    # Its probe failed on this system; the reason is in the app log.
    "error": ("Could not check", "orange", ""),
}
NOTES = {
    ("thermalright", "unsupported"): "TRCC publishes packages for Arch, CachyOS, Manjaro, Fedora, Bazzite, Debian and Ubuntu. SteamOS is not covered yet.",
    ("thermalright", "reboot-required"): "TRCC is in the next deployment. Restart, then open the configuration once and save a theme.",
    ("thermalright", "installed"): "Open the configuration once and save a theme; the display then follows it by itself.",
    ("corsair", "unsupported"): "OpenLinkHub is published for x86_64 only.",
    ("corsair", "relogin-required"): "Installed. Log out and back in (or restart) once, so this account can reach the Corsair devices.",
    ("corsair", "managed-elsewhere"): "OpenLinkHub is already installed on this system outside Control Center, so it is left as it is.",
    ("hdmi_ac3", "unsupported"): "Needs PipeWire with WirePlumber 0.5 or newer and the BC-250 HDMI audio function.",
    ("hdmi_ac3", "reboot-required"): "The encoder is in the next deployment. Restart, then press Install again to switch the output to 5.1.",
    ("hdmi_ac3", "installed"): "Configured, but another output is in use. Press Use 5.1 output to switch back to it.",
    ("hdmi_ac3", "managed-elsewhere"): "Another toolkit already switches the AC-3 profile on, so it is left as it is.",
    ("hdmi_cec", "managed-elsewhere"): "MastaG's bc250-cec already runs on this CEC adapter, so it is left as it is. Two CEC services on one adapter get in each other's way; remove bc250-cec first to use this one.",
    ("hdmi_cec", "unsupported"): "The running kernel was built without CEC over DisplayPort.",
    ("vram_sensor", "unsupported"): "Needs an Arch-based system (Arch, CachyOS, Manjaro) on a BC-250 with BIOS P3.00: the driver patches the SMU at addresses reviewed for that BIOS only.",
    ("vram_sensor", "managed-elsewhere"): "Your kernel already includes this driver (MastaG's BC-250 kernels do), so there is nothing to build.",
    ("vrm_sensor", "unsupported"): "Builds on Arch-based systems (Arch, CachyOS, Manjaro) on a BC-250.",
    ("apu_telemetry", "managed-elsewhere"): "Installed with BC250-Telemetry's own installer, so Control Center leaves it alone.",
    ("apu_telemetry", "installed"): "Installed, but no regulator answers over I2C yet. Check the wiring of the modification.",
    ("vrm_sensor", "managed-elsewhere"): "Your kernel already includes this driver (MastaG's BC-250 kernels do), so there is nothing to build.",
    ("vrm_sensor", "installed"): "Installed, but the regulator does not answer through the fan chip. Run sudo dmesg | grep bc250_vrm to see why.",
    ("vrm_sensor", "update-available"): "This copy was built by an earlier version of Control Center. Press Update to build it again with the current fixes.",
    ("vram_sensor", "update-available"): "This copy was built by an earlier version of Control Center. Press Update to build it again with the current fixes.",
    ("vram_sensor", "installed"): "Installed, but this BIOS keeps the SMU locked, so the driver waits. Press Monitor live on the dashboard once after each power-on: Control Center patches the SMU and the driver reads from then on.",
}
#: What the configure button reads as, per accessory; empty hides it.
CONFIGURE = {
    "thermalright": "Open configuration",
    "corsair": "Open control panel",
    "hdmi_ac3": "",
    "hdmi_cec": "Open TV control",
    "vram_sensor": "",
    "vrm_sensor": "",
    "apu_telemetry": "",
}

#: What installing it does to the board, said before anything runs.
REAL_SLEEP_INSTALL = (
    "It changes the boot and, on BIOS P3.00, one BIOS option, which is put back when you remove it. "
    "If the board does not wake up, unplug it for 30 seconds. Only a USB device in a blue port wakes it."
)
REAL_SLEEP_POWER_OFF = (
    "Power off changes too: a gamepad or a USB device can then turn the computer on. "
    "Its row lets you go back to the normal power off."
)
REAL_SLEEP_REMOVE = "Suspend goes back to how the system had it, and the BIOS option returns to its earlier value."


def removal_text(accessory: str) -> str:
    # Removing takes the program away; the owner's own themes and profiles
    # stay, which the question says. Audio and TV settings have no profiles:
    # what Control Center added goes, nothing else.
    if accessory == "real_sleep":
        return REAL_SLEEP_REMOVE
    if accessory in {"vram_sensor", "vrm_sensor"}:
        return (
            "The driver and its DKMS build are removed. Its readings stop showing until you "
            "install it again; dkms and the kernel headers stay."
        )
    if accessory in {"hdmi_ac3", "hdmi_cec"}:
        return (
            "The settings Control Center added are removed and the previous behaviour returns. "
            "Packages installed for it stay."
        )
    return (
        "The program and the service Control Center set up for it are removed. "
        "Your own themes and profiles are kept."
    )
