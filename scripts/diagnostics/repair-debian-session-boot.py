#!/usr/bin/env python3
"""Apply the reviewed Debian rEFInd/X11 repair from this checkout as root."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "privileged/lib"))
import system_setup_kernel_args as kernel  # noqa: E402 - requires the source path configured above
from system_setup_common import Host, SetupError  # noqa: E402 - requires the source path configured above


def main():
    if os.geteuid() != 0:
        raise SetupError("Run this script with sudo from the Debian installation")
    host = Host()
    if host.distro_family() != "debian" or not host.bc250():
        raise SetupError("This repair requires Debian and an AMD BC-250")
    if kernel.backend(host) != "refind":
        raise SetupError("Direct rEFInd boot was not detected; no changes made")
    profile = host.read("/etc/profile.d/zz-bc250-control-center-vaapi.sh")
    marker = "# Managed by BC250 Control Center: VA-API video driver"
    target = "/etc/X11/Xsession.d/95bc250-vaapi"
    if not profile.startswith(marker):
        raise SetupError("The BC250-owned VA-API profile is missing")
    previous = host.read(target)
    if previous and not previous.startswith(marker):
        raise SetupError("The Xsession hook belongs to another tool")
    result = kernel.apply(host, ["mitigations=off", "nosmt", "loglevel=0"])
    host.write(target, profile + "\n")
    print("Saved rEFInd boot options and the Debian X11 VA-API hook.")
    print("Reboot once, then open Control Center again.")
    print("Kernel options:", result["arguments"])


if __name__ == "__main__":
    try:
        main()
    except SetupError as error:
        sys.exit(str(error))
