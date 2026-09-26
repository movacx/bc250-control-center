"""Distribution-native connectivity and printing support.

This module deliberately does not pretend that a generic out-of-tree kernel
driver exists.  It inventories the active kernel bindings and offers only
official distribution packages for firmware, Bluetooth, CUPS and driverless
IPP.  Device-specific modules such as AIC8800 remain an explicit, separately
reviewed integration.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from bc250cc.platform.init.services import detect_init_manager
from bc250cc.platform.packages.strategies.detector import detect_os_info

_CONNECTIVITY_PACKAGES = {
    "arch": ("linux-firmware", "usbutils", "iw", "bluez", "bluez-utils"),
    "manjaro": ("linux-firmware", "usbutils", "iw", "bluez", "bluez-utils"),
    "cachyos": ("linux-firmware", "usbutils", "iw", "bluez", "bluez-utils"),
    "fedora": ("linux-firmware", "usbutils", "iw", "bluez"),
    "bazzite": ("linux-firmware", "usbutils", "iw", "bluez"),
    "ubuntu": ("linux-firmware", "usbutils", "iw", "bluez", "rfkill"),
    # Debian's Wi-Fi and Bluetooth firmware lives in non-free-firmware (see
    # _DEBIAN_FIRMWARE); only the free part is certain to be available.
    "debian": ("firmware-linux-free", "usbutils", "iw", "bluez", "rfkill"),
}

#: The firmware USB Wi-Fi and Bluetooth adapters load, as Debian splits it.
#: Every one lives in the non-free-firmware component. Debian 12 installs
#: enable it by default, upgraded and minimal systems often do not, and a
#: release that lacks one of these (firmware-mediatek before Debian 13) just
#: skips it: the workflow installs only what the repositories offer.
_DEBIAN_FIRMWARE = (
    "firmware-misc-nonfree",
    "firmware-realtek",
    "firmware-iwlwifi",
    "firmware-atheros",
    "firmware-brcm80211",
    "firmware-mediatek",
    "firmware-libertas",
)
#: Only added, as its own file, after the user says yes in the terminal. The
#: user's own sources are never edited, and removing the file undoes it.
DEBIAN_FIRMWARE_SOURCE = "/etc/apt/sources.list.d/bc250-non-free-firmware.sources"

_PRINTING_PACKAGES = {
    "arch": (
        "cups",
        "cups-filters",
        "ghostscript",
        "gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
    "manjaro": (
        "cups",
        "cups-filters",
        "ghostscript",
        "gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
    "cachyos": (
        "cups",
        "cups-filters",
        "ghostscript",
        "gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
    "fedora": (
        "cups",
        "cups-filters",
        "ghostscript",
        "gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane-backends",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
    "bazzite": (
        "cups",
        "cups-filters",
        "ghostscript",
        "gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane-backends",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
    "ubuntu": (
        "cups",
        "cups-filters",
        "ghostscript",
        "printer-driver-gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane-utils",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
    "debian": (
        "cups",
        "cups-filters",
        "ghostscript",
        "printer-driver-gutenprint",
        "foomatic-db",
        "hplip",
        "ipp-usb",
        "sane-utils",
        "sane-airscan",
        "simple-scan",
        "system-config-printer",
    ),
}


def supported_driver_components(family: str) -> tuple[str, ...]:
    family = str(family or "").strip().lower()
    return tuple(
        component
        for component, catalog in (
            ("connectivity", _CONNECTIVITY_PACKAGES),
            ("printing", _PRINTING_PACKAGES),
        )
        if family in catalog
    )


#: Keeps the names this release's repositories actually offer. A package
#: that a given release lacks (ipp-usb before Debian 11, firmware-mediatek
#: before 13) used to fail the whole apt-get install with "Unable to locate
#: package"; it is now skipped and named. No pipe into grep: under pipefail
#: an early grep exit would turn a SIGPIPE into a false "not available".
_APT_RESOLVE = (
    'bc250_resolve() { resolved=(); unavailable=(); local package policy; '
    'for package in "$@"; do policy="$(apt-cache policy "$package" 2>/dev/null || true)"; '
    'case "$policy" in *"Candidate: (none)"*|"") unavailable+=("$package") ;; '
    '*Candidate:*) resolved+=("$package") ;; *) unavailable+=("$package") ;; esac; done; }'
)


def _apt_commands(package_args: str) -> tuple[str, ...]:
    return (
        "sudo apt-get update",
        _APT_RESOLVE,
        f"bc250_resolve {package_args}",
        (
            'if ((${#unavailable[@]})); then echo "[INFO] Not offered by this release, '
            'skipped: ${unavailable[*]}"; fi'
        ),
        (
            'if ((${#resolved[@]})); then sudo apt-get install --no-install-recommends "${resolved[@]}"; '
            "else echo '[WARN] None of the reviewed packages is offered by the configured repositories.'; fi"
        ),
    )


def _debian_firmware_commands() -> tuple[str, ...]:
    """Wi-Fi and Bluetooth firmware from non-free-firmware, asked for once.

    Installed when the component is already enabled. When it is not, the
    terminal says so and asks; only on Debian itself and only on a yes is a
    separate source file added for this release. Derivatives (Devuan, Kali,
    Raspberry Pi OS...) have their own archives and only get the explanation.
    """
    firmware = " ".join(shlex.quote(package) for package in _DEBIAN_FIRMWARE)
    offer = _DEBIAN_FIRMWARE_OFFER.replace("@COUNT@", str(len(_DEBIAN_FIRMWARE))).replace(
        "@SOURCE@", DEBIAN_FIRMWARE_SOURCE
    )
    return (
        f"bc250_resolve {firmware}",
        offer,
        f"bc250_resolve {firmware}",
        (
            'if ((${#resolved[@]})); then sudo apt-get install --no-install-recommends "${resolved[@]}"; '
            'echo "[INFO] Unplug and replug USB adapters so they load the new firmware."; fi'
        ),
    )


#: Runs when none of the firmware is offered, which means the component is
#: off. @COUNT@ and @SOURCE@ are filled in; the rest is plain bash.
_DEBIAN_FIRMWARE_OFFER = """\
if ((${#unavailable[@]} == @COUNT@)); then
  echo "[INFO] Wi-Fi and Bluetooth firmware (Intel, Realtek, MediaTek, Atheros, Broadcom) is in the Debian non-free-firmware component, which is not enabled here."
  distro=""; codename=""
  if test -r /etc/os-release; then
    distro="$(. /etc/os-release; printf %s "${ID:-}")"
    codename="$(. /etc/os-release; printf %s "${VERSION_CODENAME:-}")"
  fi
  if [ "$distro" = debian ] && [ -n "$codename" ] && [ -r /usr/share/keyrings/debian-archive-keyring.gpg ]; then
    answer=""
    read -r -p "Enable non-free-firmware for $codename in its own source file? [y/N] " answer || answer=""
    case "$answer" in
      [yY]*)
        suites="$codename"
        case "$codename" in sid|unstable) ;; *) suites="$codename $codename-updates" ;; esac
        printf 'Types: deb\\nURIs: http://deb.debian.org/debian\\nSuites: %s\\nComponents: non-free-firmware\\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\\n' "$suites" | sudo tee @SOURCE@ >/dev/null
        echo "[INFO] Added @SOURCE@. Delete it to undo."
        sudo apt-get update
        ;;
      *) echo "[INFO] Left as it is. Enable non-free-firmware in the APT sources to add this firmware later." ;;
    esac
  else
    echo "[INFO] Enable non-free-firmware in the APT sources of this system to add it."
  fi
fi"""


def build_driver_support_command(component: str, family: str, init_kind: str) -> str:
    """Return an idempotent, reviewable distro-package workflow."""

    component = str(component or "").strip().lower()
    family = str(family or "").strip().lower()
    init_kind = str(init_kind or "unknown").strip().lower()
    catalogs = {
        "connectivity": _CONNECTIVITY_PACKAGES,
        "printing": _PRINTING_PACKAGES,
    }
    if component not in catalogs:
        raise ValueError(f"Unsupported driver component: {component or '--'}")
    packages = catalogs[component].get(family)
    if not packages:
        raise RuntimeError(
            "No reviewed distribution-native driver workflow is available for "
            f"{family or 'this distribution'}."
        )

    package_args = " ".join(shlex.quote(package) for package in packages)
    commands = [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        'echo "== BC250 Control Center: distribution-native device support =="',
        'echo "[INFO] No third-party kernel driver will be downloaded or executed."',
    ]
    if family in {"arch", "manjaro", "cachyos"}:
        commands.append(f"sudo pacman -S --needed {package_args}")
    elif family in {"ubuntu", "debian"}:
        commands.extend(_apt_commands(package_args))
        if component == "connectivity" and family == "debian":
            commands.extend(_debian_firmware_commands())
    elif family == "fedora":
        commands.append(f"sudo dnf install -y {package_args}")
    elif family == "bazzite":
        commands.extend(
            (
                f"packages=({package_args})",
                'missing=(); for package in "${packages[@]}"; do rpm -q "$package" >/dev/null 2>&1 || missing+=("$package"); done',
                (
                    'if ((${#missing[@]})); then sudo rpm-ostree install --idempotent "${missing[@]}"; '
                    "echo 'BC250_REBOOT_REQUIRED=1'; "
                    "echo '[INFO] Reboot into the new deployment before evaluating newly layered components.'; "
                    "else echo '[INFO] All reviewed packages are already present in this deployment.'; fi"
                ),
            )
        )

    if component == "connectivity" and family != "bazzite":
        if init_kind == "systemd":
            commands.append(
                "sudo systemctl enable --now bluetooth.service 2>/dev/null || true"
            )
        elif init_kind == "openrc":
            commands.append(
                "if test -x /etc/init.d/bluetooth; then sudo rc-update add bluetooth default; "
                "sudo rc-service bluetooth start; else echo '[INFO] No OpenRC Bluetooth service script was installed.'; fi"
            )
        else:
            commands.append(
                f"echo {shlex.quote(f'[WARN] Packages were installed, but Bluetooth service persistence is not automated for {init_kind}.')}"
            )
    elif component == "printing" and family != "bazzite":
        if init_kind == "systemd":
            commands.extend(
                (
                    "sudo systemctl enable --now cups.socket 2>/dev/null || sudo systemctl enable --now cups.service",
                    "sudo systemctl enable --now ipp-usb.service 2>/dev/null || true",
                )
            )
        elif init_kind == "openrc":
            commands.extend(
                (
                    (
                        "if test -x /etc/init.d/cupsd; then sudo rc-update add cupsd default; sudo rc-service cupsd start; "
                        "elif test -x /etc/init.d/cups; then sudo rc-update add cups default; sudo rc-service cups start; "
                        "else echo '[WARN] No OpenRC CUPS service script was installed.'; fi"
                    ),
                    (
                        "if test -x /etc/init.d/ipp-usb; then sudo rc-update add ipp-usb default; sudo rc-service ipp-usb start; "
                        "else echo '[INFO] ipp-usb has no OpenRC service script on this distribution.'; fi"
                    ),
                )
            )
        else:
            commands.append(
                f"echo {shlex.quote(f'[WARN] Packages were installed, but service persistence is not automated for {init_kind}.')}"
            )
    commands.append('echo "OK: distribution-native device support workflow completed."')
    return "\n".join(commands)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _driver_name(device: Path) -> str:
    try:
        return device.joinpath("driver").resolve(strict=True).name
    except OSError:
        return ""


class DriversRepository:
    """Read-only inventory plus explicitly confirmed package workflows."""

    @staticmethod
    def _driver_run(argv: list[str], timeout: float = 2.0) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except (OSError, subprocess.TimeoutExpired):
            return 127, "", "unavailable"

    @staticmethod
    def _network_inventory(root: Path = Path("/sys/class/net")) -> list[dict[str, str]]:
        devices: list[dict[str, str]] = []
        for interface in sorted(root.glob("*")):
            if interface.name == "lo":
                continue
            device = interface / "device"
            wireless = (interface / "wireless").exists() or (
                device / "ieee80211"
            ).exists()
            devices.append(
                {
                    "name": interface.name,
                    "kind": "wifi" if wireless else "ethernet",
                    "driver": _driver_name(device),
                    "address": _read_text(interface / "address"),
                    "state": _read_text(interface / "operstate") or "unknown",
                }
            )
        return devices

    @staticmethod
    def _usb_inventory(
        root: Path = Path("/sys/bus/usb/devices"),
    ) -> list[dict[str, object]]:
        devices: list[dict[str, object]] = []
        for device in sorted(root.glob("*")):
            vendor = _read_text(device / "idVendor").lower()
            product_id = _read_text(device / "idProduct").lower()
            if not vendor or not product_id:
                continue
            # USB interface directories are siblings of the physical device
            # (for example ``1-2:1.0``), not children of it.
            interface_classes: set[str] = set()
            for candidate in root.glob(f"{device.name}:*/bInterfaceClass"):
                value = _read_text(candidate).lower()
                if value:
                    interface_classes.add(value)
            product = _read_text(device / "product")
            manufacturer = _read_text(device / "manufacturer")
            devices.append(
                {
                    "id": f"{vendor}:{product_id}",
                    "name": " ".join(
                        part for part in (manufacturer, product) if part
                    ).strip()
                    or f"USB {vendor}:{product_id}",
                    "printer": "07" in interface_classes,
                    "bluetooth": "e0" in interface_classes,
                    "aic8800_candidate": f"{vendor}:{product_id}" == "1111:1111",
                }
            )
        return devices

    def driver_inventory(self) -> dict[str, object]:
        info = detect_os_info(has_rpm_ostree=bool(shutil.which("rpm-ostree")))
        init = detect_init_manager()
        network = self._network_inventory()
        usb = self._usb_inventory()
        _code, queues_output, _error = self._driver_run(["lpstat", "-e"])
        queues = [line.strip() for line in queues_output.splitlines() if line.strip()]
        bluetooth_controllers = sorted(
            path.name for path in Path("/sys/class/bluetooth").glob("hci*")
        )
        return {
            "distribution": info.label,
            "family": info.family,
            "immutable": info.immutable,
            "init_manager": init.kind,
            "supported_components": supported_driver_components(info.family),
            "network": network,
            "usb_printers": [item for item in usb if item["printer"]],
            "bluetooth_controllers": bluetooth_controllers,
            "printing": {
                "cups_tools": bool(shutil.which("lpstat") and shutil.which("lpinfo")),
                "ipp_usb": bool(shutil.which("ipp-usb")),
                "gui": bool(
                    shutil.which("system-config-printer")
                    or shutil.which("systemsettings")
                ),
                "queues": queues,
            },
            "aic8800": {
                "loaded": Path("/sys/module/aic8800_fdrv").exists(),
                "candidate_detected": any(item["aic8800_candidate"] for item in usb),
                "posture": "reference-only",
            },
        }

    def install_driver_support(self, component: str) -> object:
        info = detect_os_info(has_rpm_ostree=bool(shutil.which("rpm-ostree")))
        init = detect_init_manager()
        command = build_driver_support_command(component, info.family, init.kind)
        title = (
            "Connectivity support"
            if component == "connectivity"
            else "Printing and scanning"
        )
        return self._abrir_terminal(command, title)
