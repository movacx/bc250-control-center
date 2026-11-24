"""What each compatibility action changes, as every interface asks about it: (title, text, button, tone)."""

from __future__ import annotations

GFX1013_SOURCE = {
    "install": (
        "Build and install the GFX1013 fix",
        "This builds DryhoppedIPA's V33 amdgpu patches for the running kernel and RADV with the compute-queue patch, then installs them beside the stock driver and Mesa, which stay untouched. amdgpu is then loaded by a small boot service: if a boot with the fix does not reach the desktop, the next boot uses the stock driver and switches the fix off by itself. To skip it for one boot, press e in the boot menu and add bc250.gfx1013=0. Building needs your password, an internet connection and 15-30 minutes.",
        "Build and install",
        "orange",
    ),
    "rebuild": (
        "Rebuild for this kernel",
        "The kernel was updated, so the patched module has to be built again for it. The private RADV stays as it is. This takes a few minutes and a restart.",
        "Rebuild",
        "blue",
    ),
    "enable": (
        "Switch the GFX1013 fix on",
        "The patched driver is used again from the next boot, with the same automatic fallback if that boot fails.",
        "Switch on",
        "blue",
    ),
    "disable": (
        "Switch the GFX1013 fix off",
        "The stock amdgpu and system Mesa are used from the next boot. The fix stays installed and can be switched on again.",
        "Switch off",
        "blue",
    ),
    "uninstall": (
        "Remove the GFX1013 fix",
        "Removes the patched module, the private RADV and the boot service, and rebuilds the initramfs. The stock driver is used from the next boot.",
        "Remove",
        "orange",
    ),
}

VAAPI = {
    "install": (
        "Install hardware video",
        "Downloads simpmix's VA-API driver at a reviewed version, checks it, and builds it in a container: about 5 minutes and a few hundred MB the first time. It is switched on only after it starts and offers H.264 and HEVC. Programs that use VA-API (Sunshine, OBS, Steam Remote Play, ffmpeg, browsers) then encode and decode with it. For streaming while you play, choose H.264: HEVC encodes mostly on the CPU. Log out and back in afterwards.",
        "Build and install",
        "orange",
    ),
    "install32": (
        "Add the 32-bit video driver",
        "Steam Remote Play and Steam Link are 32-bit programs and use software video without a 32-bit driver. This installs the signed 32-bit libraries (on SteamOS it turns the read-only protection off for the install and back on), builds the 32-bit driver in a container from the same reviewed source, checks it starts on this GPU, and only then adds it beside the 64-bit one. A SteamOS update removes the 32-bit libraries; this button then reads Repair 32-bit driver and brings them back without rebuilding. Log out and back in afterwards.",
        "Add",
        "orange",
    ),
    "flatpak": (
        "Allow Flatpak apps to use hardware video",
        "Flatpak apps (GPU Screen Recorder, OBS, Steam) run in a sandbox that cannot see the driver, so they list H.264 as not available. This gives them read-only access to the driver folder and the two libva variables, for your user only. Restart those apps afterwards.",
        "Allow",
        "orange",
    ),
    "uninstall": (
        "Remove hardware video",
        "Removes the driver and the two files that switch it on. Programs go back to software video from the next login.",
        "Remove",
        "orange",
    ),
}

RADV_ASYNC = {
    "install": (
        "Build and install async compute",
        "This builds RADV with the GFX1013 compute-queue patch from tri3gubki-ops' Bazzite release and installs it as a second Vulkan driver beside the system Mesa, which stays untouched. Kernel 7.2 or newer needs no patched amdgpu for it: its amdgpu is the one that release runs on. New sessions use it: log out and back in, and games need no launch options. If the desktop does not come back, press e in the boot menu and add bc250.async=0. Building needs your password, an internet connection and 10-20 minutes.",
        "Build and install",
        "orange",
    ),
    "enable": (
        "Switch async compute on",
        "Sessions started from now on use the patched RADV. Log out and back in to apply.",
        "Switch on",
        "blue",
    ),
    "disable": (
        "Switch async compute off",
        "Sessions started from now on use the system driver. The patched RADV stays installed, and one game can still use it with the launch option bc250cc-async-compute run %command%.",
        "Switch off",
        "blue",
    ),
    "uninstall": (
        "Remove async compute",
        "Removes the patched RADV, its test tools and the session switch. The system driver is used from the next login.",
        "Remove",
        "orange",
    ),
}

MASTAG_TRUST = "This is not a standard dependency. It adds MastaG's external pacman repository, whose packages are unsigned (Optional TrustAll). Continue only if you trust that upstream repository."
MASTAG_BUNDLE = "The bundle brings its own Dolby 5.1 output and its own CEC service. If Control Center's 5.1 output or TV control is set up, remove those first: two of each get in each other's way."
MESA_PPA = "This adds the kisak-mesa PPA (ppa:kisak/kisak-mesa), a third-party source, in its own source file after checking that its signing key is the expected one, and updates Mesa and, if present, its 32-bit libraries from it. Other packages are not touched. To go back, delete the source file and key and downgrade Mesa; the terminal prints the commands. Restart afterwards. Needs your password and an internet connection."
DEBIAN_KERNEL = "Debian 13 ships a kernel and a Mesa that do not know the BC-250 GPU, so the desktop is drawn by the CPU. This adds the Debian backports suite in its own source file and installs from it a newer Mesa, a newer kernel with its headers and the GPU firmware. The current kernel stays installed and in the boot menu under Advanced options. Restart afterwards, then build the GFX1013 fix from this same card. Needs your password and an internet connection."
DEBIAN_MESA = "Debian 13 ships a Mesa that does not know the BC-250 GPU, so the desktop is drawn by the CPU. This adds the Debian backports suite in its own source file and installs the newer Mesa from it. Restart afterwards. Needs your password and an internet connection."
DECKY_BOOTSTRAP = "Decky Loader is an external third-party root-plugin service. This Beta workflow downloads its official stable installer to a temporary file and displays its SHA-256 in the terminal before it runs. Your confirmation in this dialog authorizes that explicit action. BC250 then installs only its local Quick Access panel. Continue?"
