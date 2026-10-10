"""ACPI through a separate boot entry, not a rewrite of the user's initramfs.

Initial qualification: Arch/CachyOS/Manjaro, GRUB simple Linux entries or
systemd-boot Type #1. UKI, Secure Boot, unknown layouts and foreign fixes are
intentionally diagnostic-only. The original boot entry is the recovery route.

Bazzite (beta) boots its ostree deployments through GRUB's blscfg, which
puts the ``early_initrd`` variable of grubenv in front of every entry's
initrd: the route upstream documents for Universal Blue
(GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"), set here with
grub2-editenv instead of regenerating Bazzite's bootupd GRUB configuration.
The recovery route is a submenu in /boot/grub2/custom.cfg that lists the same
entries without the tables.

SteamOS (beta) generates its classic GRUB menu with grub-mkconfig into
/efi/EFI/steamos/grub.cfg, which reads /etc/default/grub.d. The tables go in
through GRUB's own early-initrd list: a drop-in sets
GRUB_EARLY_INITRD_LINUX_CUSTOM="bc250-acpi.cpio" and the archive sits beside
the kernel in /boot, the route keyboardspecialist/bc250-steamos (public
domain) uses. The new menu is written beside the old one and replaces it only
once every initrd line loads the archive before the initramfs. Each SteamOS
image (A/B) has its own /boot and its own menu, so the other image keeps
booting with the stock tables: that is the recovery route. A SteamOS update
brings a /boot without the archive; the drop-in is kept by the update's keep
list, and the installation reads as needing a repair until the archive is
written again.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shlex
import struct
import textwrap

import system_setup_kernel_args as kernel_args
from acpi_payload import SHA256, SUPERSEDED, SUPERSEDED_CPU_TABLES, VERSION, archive
from system_setup_common import MARKER, STATE, Host, SetupError

GRUB_SCRIPT = "/etc/grub.d/09_bc250_acpi"
GRUB_CONFIG = "/etc/default/grub"
GRUB_OUTPUT = "/boot/grub/grub.cfg"
GRUB_BLOCK = "\n# BEGIN BC250 ACPI DEFAULT\nGRUB_DEFAULT=bc250-acpi\n# END BC250 ACPI DEFAULT\n"
EFI_GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
PROBE_SCHEMA = 3
UPSTREAM_URL = "https://github.com/e-tho/bc250-acpi-fix"
BAZZITE_GRUBENV = "/boot/grub2/grubenv"
BAZZITE_GRUBCFG = "/boot/grub2/grub.cfg"
BAZZITE_CUSTOM = "/boot/grub2/custom.cfg"
#: Relative to each kernel's folder (/ostree/<deployment>/), so /boot's root.
BAZZITE_EARLY_INITRD = "../../bc250-acpi.cpio"
#: Upstream's own manual install for Universal Blue.
BAZZITE_UPSTREAM_PAYLOAD = "/boot/acpi_override.cpio"
BAZZITE_BEGIN = "# BEGIN BC250 ACPI RECOVERY"
BAZZITE_END = "# END BC250 ACPI RECOVERY"
BAZZITE_RECOVERY = (
    f"{BAZZITE_BEGIN}\n"
    "# Managed by BC250 Control Center. Every Bazzite entry above loads the BC250\n"
    "# ACPI tables (early_initrd in grubenv); these are the same entries without them.\n"
    "submenu 'Bazzite without the BC250 ACPI tables (recovery)' --id bc250-acpi-recovery {\n"
    "  unset early_initrd\n"
    "  blscfg\n"
    "}\n"
    f"{BAZZITE_END}\n"
)
_BAZZITE_BLOCK = re.compile(rf"\n?{re.escape(BAZZITE_BEGIN)}\n.*?{re.escape(BAZZITE_END)}\n", re.S)
STEAMOS_DROPIN = "/etc/default/grub.d/92-bc250-acpi.cfg"
STEAMOS_KEEP = "/etc/atomic-update.conf.d/bc250-control-center-acpi.conf"
STEAMOS_PAYLOAD = "/boot/bc250-acpi.cpio"
STEAMOS_DROPIN_LINE = 'GRUB_EARLY_INITRD_LINUX_CUSTOM="bc250-acpi.cpio"\n'
#: keyboardspecialist/bc250-steamos's own ACPI install: its drop-in, its
#: archive and the service that writes the archive back after an update.
STEAMOS_FOREIGN = (
    "/etc/default/grub.d/bc250-acpi.cfg",
    "/boot/acpi_override.cpio",
    "/etc/systemd/system/bc250-acpi-heal.service",
)


def _steamos_host(host: Host) -> bool:
    return host.steamos() and host.path("/run/systemd/system").is_dir()


def _initrd_entries(menu: str) -> list[list[str]]:
    """The images of every initrd line, ``steamenv_boot initrd`` included."""
    entries = []
    for line in menu.splitlines():
        words = line.split()
        if words[:1] == ["steamenv_boot"]:
            words = words[1:]
        if words and words[0].startswith("initrd"):
            entries.append(words[1:])
    return entries


def _steamos_owned(host: Host) -> bool:
    """Our drop-in is there, whether or not the journal survived."""
    return host.read(STEAMOS_DROPIN).startswith(MARKER.strip())


def _steamos_foreign_early_initrd(host: Host) -> str:
    """A GRUB configuration file, other than ours, that sets an early initrd."""
    candidates = [GRUB_CONFIG, *sorted(
        "/etc/default/grub.d/" + path.name for path in host.path("/etc/default/grub.d").glob("*.cfg")
    )]
    for name in candidates:
        if name == STEAMOS_DROPIN and _steamos_owned(host):
            continue
        for line in host.read(name).splitlines():
            if not line.lstrip().startswith("#") and "GRUB_EARLY_INITRD_LINUX_CUSTOM" in line:
                return name
    return ""


def _steamos_plan(host: Host) -> dict:
    if not host.command("grub-mkconfig") or not kernel_args.grub_reads_dropins(host):
        raise SetupError("SteamOS's grub-mkconfig does not read /etc/default/grub.d")
    output = host.path(kernel_args.STEAMOS_GRUB_OUTPUT)
    if output.is_symlink() or not output.is_file():
        raise SetupError(f"SteamOS's boot menu ({kernel_args.STEAMOS_GRUB_OUTPUT}) was not found")
    menu = host.read(kernel_args.STEAMOS_GRUB_OUTPUT)
    if not menu:
        raise SetupError("SteamOS's boot menu could not be read; use Check status")
    initrds = _initrd_entries(menu)
    if not kernel_args._kernel_entries(menu) or not initrds:
        raise SetupError("SteamOS's boot menu has no kernel entry with an initramfs")
    for images in initrds:
        if not images or any(not image.startswith("/boot/") or ".." in image.split("/") for image in images):
            raise SetupError("A SteamOS boot entry loads its initramfs from outside /boot")
    return {"backend": "steamos-grub", "mount": "/boot"}


def _steamos_menu_loads_tables(menu: str) -> bool:
    """Every initrd line loads the archive, before any initramfs image."""
    initrds = _initrd_entries(menu)
    if not initrds:
        return False
    for images in initrds:
        if STEAMOS_PAYLOAD not in images:
            return False
        position = images.index(STEAMOS_PAYLOAD)
        if any("initramfs" in image for image in images[:position]):
            return False
    return True


def _steamos_regenerate(host: Host, *, tables: bool) -> None:
    """A new menu beside SteamOS's, put in place only when it is right."""
    staged = host.path(kernel_args.STEAMOS_GRUB_STAGED)
    if staged.is_symlink():
        raise SetupError(f"Refusing symbolic link: {kernel_args.STEAMOS_GRUB_STAGED}")
    try:
        staged.unlink(missing_ok=True)
        host.run("grub-mkconfig", "-o", kernel_args.STEAMOS_GRUB_STAGED)
        try:
            generated = staged.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise SetupError("grub-mkconfig wrote no readable boot menu") from error
        if not kernel_args._kernel_entries(generated) or not _initrd_entries(generated):
            raise SetupError("grub-mkconfig produced no kernel entries; the boot menu was left as it was")
        if tables and not _steamos_menu_loads_tables(generated):
            raise SetupError(
                "SteamOS's grub-mkconfig did not load the ACPI tables in every boot entry; "
                "the boot menu was left as it was"
            )
        if not tables and any(STEAMOS_PAYLOAD in images for images in _initrd_entries(generated)):
            raise SetupError("SteamOS's boot menu still loads the ACPI tables; it was left as it was")
        os.replace(staged, host.path(kernel_args.STEAMOS_GRUB_OUTPUT))
    finally:
        staged.unlink(missing_ok=True)


def _steamos_put_payload(host: Host) -> None:
    payload = host.safe(STEAMOS_PAYLOAD)
    if payload.exists() and hashlib.sha256(payload.read_bytes()).hexdigest() not in {SHA256, *SUPERSEDED}:
        raise SetupError(f"Modified ACPI payload preserved for manual review: {STEAMOS_PAYLOAD}")
    host.write(STEAMOS_PAYLOAD, archive())


def _steamos_install(host: Host) -> None:
    """Archive, drop-in and keep list, then a verified menu; all undone on failure."""
    had_payload = host.path(STEAMOS_PAYLOAD).exists()
    had_dropin = host.path(STEAMOS_DROPIN).exists()
    had_keep = host.path(STEAMOS_KEEP).exists()
    try:
        _steamos_put_payload(host)
        host.managed(STEAMOS_DROPIN, STEAMOS_DROPIN_LINE)
        host.managed(STEAMOS_KEEP, STEAMOS_DROPIN + "\n")
        _steamos_regenerate(host, tables=True)
    except Exception:
        if not had_dropin:
            host.remove_managed(STEAMOS_DROPIN)
        if not had_keep:
            host.remove_managed(STEAMOS_KEEP)
        if not had_payload:
            host.path(STEAMOS_PAYLOAD).unlink(missing_ok=True)
        raise


def _steamos_uninstall(host: Host) -> None:
    """The drop-in goes first, so the archive is only removed once nothing loads it."""
    if host.path(STEAMOS_DROPIN).exists():
        host.remove_managed(STEAMOS_DROPIN)
    try:
        _steamos_regenerate(host, tables=False)
    except Exception:
        host.managed(STEAMOS_DROPIN, STEAMOS_DROPIN_LINE)
        raise
    host.remove_managed(STEAMOS_KEEP)
    payload = host.safe(STEAMOS_PAYLOAD)
    if payload.exists():
        if hashlib.sha256(payload.read_bytes()).hexdigest() not in {SHA256, *SUPERSEDED}:
            raise SetupError("Modified ACPI payload preserved for manual review")
        payload.unlink()


def _steamos_needs_repair(host: Host) -> bool:
    """After a SteamOS update: the drop-in is kept, the archive or menu is not.

    Only answered when /boot can be listed; otherwise the caller keeps the
    status it already had rather than guessing.
    """
    if not os.access(host.path("/boot"), os.R_OK | os.X_OK):
        return False
    payload = host.path(STEAMOS_PAYLOAD)
    try:
        intact = payload.is_file() and hashlib.sha256(payload.read_bytes()).hexdigest() in {SHA256, *SUPERSEDED}
    except OSError:
        return False
    menu = host.read(kernel_args.STEAMOS_GRUB_OUTPUT)
    return not intact or (bool(menu) and not _steamos_menu_loads_tables(menu))


def _grubenv_early_initrd(host: Host) -> str | None:
    """The ``early_initrd`` grubenv sets, "" for none, None when unreadable."""
    try:
        listing = host.run("grub2-editenv", BAZZITE_GRUBENV, "list")
    except SetupError:
        return None
    for line in listing.splitlines():
        if line.startswith("early_initrd="):
            return line.split("=", 1)[1]
    return ""


def _bazzite_plan(host: Host) -> dict:
    if not host.command("grub2-editenv"):
        raise SetupError("grub2-editenv is missing")
    entries = sorted(host.path("/boot/loader/entries").glob("ostree-*.conf"))
    if not entries:
        raise SetupError("No ostree boot entries were found in /boot/loader/entries")
    for entry in entries:
        linux = re.search(r"^linux\s+(\S+)\s*$", entry.read_text(encoding="utf-8", errors="replace"), re.M)
        # Exactly two folders deep, so ../../ is the root of /boot.
        if not linux or not re.fullmatch(r"/ostree/[A-Za-z0-9_.+-]+/vmlinuz-[A-Za-z0-9_.+-]+", linux[1]):
            raise SetupError("An ostree boot entry has an unexpected kernel path")
    menu = host.read(BAZZITE_GRUBCFG)
    if not menu:
        raise SetupError("The GRUB configuration could not be read; use Check status")
    if "blscfg" not in menu:
        raise SetupError("GRUB does not read the ostree boot entries through blscfg")
    if "early_initrd" in menu:
        raise SetupError("Bazzite's GRUB configuration sets early_initrd itself and would override this fix")
    if "custom.cfg" not in menu:
        raise SetupError("Bazzite's GRUB configuration does not read custom.cfg, so no recovery entry can be added")
    current = _grubenv_early_initrd(host)
    if current is None:
        raise SetupError("grubenv could not be read")
    return {"backend": "bazzite-bls", "mount": "/boot", "early_initrd": BAZZITE_EARLY_INITRD,
            "env_early_initrd": current}


def _boot_writable(host: Host) -> bool:
    """Remount a read-only /boot (bootc) for the change; True when it was."""
    for line in host.read("/proc/mounts").splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == "/boot" and "ro" in fields[3].split(","):
            host.run("mount", "-o", "remount,rw", "/boot")
            return True
    return False


def _bazzite_install(host: Host, payload: str) -> dict:
    """The payload, a recovery submenu, then the variable that loads the tables."""
    remounted = _boot_writable(host)
    custom = host.safe(BAZZITE_CUSTOM)
    created = not custom.exists()
    try:
        host.write(payload, archive())
        base = "" if created else custom.read_text(encoding="utf-8")
        if BAZZITE_BEGIN in base:
            raise SetupError("An untracked BC250 recovery block already exists in custom.cfg")
        if base and not base.endswith("\n"):
            base += "\n"
        host.write(BAZZITE_CUSTOM, base + BAZZITE_RECOVERY, mode=0o600)
        host.run("grub2-editenv", BAZZITE_GRUBENV, "set", f"early_initrd={BAZZITE_EARLY_INITRD}")
        if _grubenv_early_initrd(host) != BAZZITE_EARLY_INITRD:
            raise SetupError("grubenv did not keep early_initrd")
    finally:
        if remounted:
            host.run("mount", "-o", "remount,ro", "/boot", check=False)
    return {"custom_created": created}


def _bazzite_uninstall(host: Host, state: dict) -> None:
    remounted = _boot_writable(host)
    try:
        current = _grubenv_early_initrd(host)
        if current == BAZZITE_EARLY_INITRD:
            host.run("grub2-editenv", BAZZITE_GRUBENV, "unset", "early_initrd")
        elif current:
            raise SetupError("grubenv's early_initrd was changed by someone else; it was left as it is")
        custom = host.safe(BAZZITE_CUSTOM)
        if custom.exists():
            text = custom.read_text(encoding="utf-8")
            if BAZZITE_BEGIN in text:
                remaining = _BAZZITE_BLOCK.sub("", text, count=1)
                if BAZZITE_BEGIN in remaining or BAZZITE_END in remaining:
                    raise SetupError("The BC250 recovery block in custom.cfg was edited; manual recovery required")
                if state.get("custom_created") and not remaining.strip():
                    custom.unlink()
                else:
                    host.write(BAZZITE_CUSTOM, remaining, mode=0o600)
        payload = host.safe("/boot/bc250-acpi.cpio")
        if payload.exists():
            if hashlib.sha256(payload.read_bytes()).hexdigest() not in {SHA256, *SUPERSEDED}:
                raise SetupError("Modified ACPI payload preserved for manual review")
            payload.unlink()
    finally:
        if remounted:
            host.run("mount", "-o", "remount,ro", "/boot", check=False)


def efi_string(host: Host, name: str) -> str:
    try:
        return host.path(f"/sys/firmware/efi/efivars/{name}-{EFI_GUID}").read_bytes()[4:].decode("utf-16-le").rstrip("\0")
    except (OSError, UnicodeError):
        return ""


def kernel_support(host: Host) -> bool:
    try:
        config = gzip.decompress(host.path("/proc/config.gz").read_bytes()).decode()
    except (OSError, ValueError, EOFError):
        config = host.read("/boot/config-" + os.uname().release)
    return "CONFIG_ACPI_TABLE_UPGRADE=y" in config.splitlines()


def table_status(host: Host) -> tuple[str, list[str]]:
    tables = []
    installed = set()
    foreign = False
    cpu_tables = 0
    outdated_cpu = False
    expected = {}
    cpio = archive()
    offset = 0
    while offset + 110 <= len(cpio):
        header = cpio[offset:offset + 110]
        length = int(header[54:62], 16)
        name_length = int(header[94:102], 16)
        name = cpio[offset + 110:offset + 110 + name_length - 1].decode()
        start = (offset + 110 + name_length + 3) & ~3
        data = cpio[start:start + length]
        offset = (start + length + 3) & ~3
        if name == "TRAILER!!!":
            break
        if length:
            expected[data[16:24].decode("ascii").strip("\0 ")] = hashlib.sha256(data).digest()
    for path in host.path("/sys/firmware/acpi/tables").glob("SSDT*"):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) < 36:
            continue
        oem = data[10:16].decode("ascii", errors="replace").strip("\0 ")
        name = data[16:24].decode("ascii", errors="replace").strip("\0 ")
        revision = struct.unpack_from("<I", data, 24)[0]
        tables.append(f"{oem}:{name}:{revision}")
        if name == "AMD CPU":
            cpu_tables += 1
            outdated_cpu = outdated_cpu or hashlib.sha256(data).hexdigest() in SUPERSEDED_CPU_TABLES
        if (oem, name) in {("AMD", "AMD CPU"), ("HACK", "PSTATES"), ("HACK", "STUBS")}:
            if hashlib.sha256(data).digest() == expected.get(name):
                installed.add(name)
        if name in {"P_CST3", "PSTATES", "STUBS"} or (name == "AMD CPU" and revision >= 2):
            foreign = True
    if installed == {"AMD CPU", "PSTATES", "STUBS"} and cpu_tables == 1:
        return "active", tables
    # An earlier pinned release: its idle table changed, the other two did not.
    if installed == {"PSTATES", "STUBS"} and cpu_tables == 1 and outdated_cpu:
        return "outdated", tables
    return ("foreign" if foreign else "stock" if "AMD:AMD CPU:1" in tables else "unknown"), tables


def boot_plan(host: Host) -> dict:
    if host.bazzite():
        return _bazzite_plan(host)
    if _steamos_host(host):
        return _steamos_plan(host)
    # A systemd-stub image means the initrd is embedded in a UKI, even when
    # GRUB chainloads it. Injecting an external early CPIO would require a
    # separate, signed/reproducible UKI rebuild and is not this integration.
    stub = efi_string(host, "StubInfo")
    image = efi_string(host, "LoaderImageIdentifier")
    if stub and "systemd-stub" in stub.lower() and image.lower().endswith(".efi"):
        raise SetupError("The current kernel is an EFI/UKI image; ACPI injection is not yet qualified for UKI rebuilds")
    # Type #1 only: reuse the selected entry, preserving its kernel/options.
    selected = efi_string(host, "LoaderEntrySelected")
    if selected == "bc250-acpi.conf":
        selected = host.state("acpi").get("original_entry", "")
    if selected and re.fullmatch(r"[A-Za-z0-9_.+-]+\.conf", selected):
        for mount in ("/boot", "/efi", "/boot/efi"):
            entry = f"{mount}/loader/entries/{selected}"
            text = host.read(entry)
            if text and re.search(r"^linux\s+", text, re.M) and not re.search(r"^efi\s+", text, re.M):
                paths = re.findall(r"^(?:linux|initrd)\s+(\S+)\s*$", text, re.M)
                if not paths or any(not p.startswith("/") or ".." in p.split("/") or
                                    not host.path(mount + p).is_file() for p in paths):
                    raise SetupError("The selected boot entry has unsupported image paths")
                default = efi_string(host, "LoaderEntryDefault")
                if not re.fullmatch(r"[A-Za-z0-9_.+@*?-]*", default):
                    raise SetupError("Unsupported systemd-boot default")
                return {"backend": "systemd-boot", "mount": mount, "original_entry": selected,
                        "original_default": default, "entry_text": text}
    # A selected UKI must not accidentally fall back to an unrelated GRUB installation.
    if selected:
        raise SetupError("Only conventional systemd-boot Type #1 entries are qualified; UKI is not supported")
    if not host.path(GRUB_OUTPUT).is_file() or not host.command("grub-mkconfig"):
        raise SetupError("No supported bootloader layout was identified")
    boot_image = re.search(r"(?:^|\s)BOOT_IMAGE=(\S+)", host.read("/proc/cmdline"))
    if not boot_image:
        raise SetupError("Cannot identify the running kernel's GRUB entry")
    basename = boot_image[1].rsplit("/", 1)[-1]
    filesystem = json.loads(host.run("findmnt", "--json", "--target", "/boot", "-o", "TARGET,FSROOT,UUID,FSTYPE"))["filesystems"][0]
    uuid, mount, fsroot = filesystem.get("uuid", ""), filesystem["target"], filesystem.get("fsroot", "/")
    if not uuid or not re.fullmatch(r"[a-zA-Z0-9-]+", uuid):
        raise SetupError("Boot filesystem UUID is unavailable")
    # GRUB's filesystem-relative path may include a Btrfs subvolume prefix.
    boot_relative = fsroot.rstrip("/") + "/" + os.path.relpath("/boot", mount).strip(".")
    boot_relative = "/" + boot_relative.strip("/")
    if not re.fullmatch(r"/[a-zA-Z0-9_/@.+-]*", boot_relative):
        raise SetupError("Unsupported boot filesystem path")
    linux = None
    for line in host.read(GRUB_OUTPUT).splitlines():
        stripped = line.strip()
        if stripped.startswith("menuentry "):
            linux = None
        if re.match(r"^linux\s+", stripped):
            parts = shlex.split(stripped)
            linux = parts if parts[1].rsplit("/", 1)[-1] == basename else None
        if linux and re.match(r"^initrd\s+", stripped):
            initrd = shlex.split(stripped)[1:]
            tokens = linux[1:] + initrd
            if any(not re.fullmatch(r"[A-Za-z0-9_/@.,:=+%-]+", token) for token in tokens):
                raise SetupError("Complex GRUB commands require manual review")
            for image in [linux[1], *initrd]:
                if not image.startswith(boot_relative.rstrip("/") + "/") or ".." in image.split("/"):
                    raise SetupError("Boot images must reside in the identified /boot filesystem")
                suffix = image[len(boot_relative.rstrip("/")):]
                if not host.path("/boot" + suffix).is_file():
                    raise SetupError("An image referenced by GRUB is missing")
            return {"backend": "grub", "mount": "/boot", "uuid": uuid,
                    "linux": linux, "initrd": initrd,
                    "cpio_grub": boot_relative.rstrip("/") + "/bc250-acpi.cpio"}
    raise SetupError("No simple GRUB entry matches the running kernel")


def _requirement(key: str, title: str, passed: bool, detected: str,
                 required: str, resolution: str = "") -> dict:
    """Return a stable, JSON-safe diagnostic item for UI and terminal clients."""
    return {
        "id": key,
        "title": title,
        "passed": bool(passed),
        "detected": detected,
        "required": required,
        "resolution": "" if passed else resolution,
    }


def compatibility_requirements(host: Host, state: dict, live: str) -> list[dict]:
    """Inspect every ACPI prerequisite instead of stopping at the first failure.

    This is explanatory output only. ``status()`` remains the authorization
    boundary and repeats its full fail-closed validation before installation.
    """
    requirements = []

    bc250 = host.bc250()
    steamos = _steamos_host(host)
    mutable = host.mutable_systemd() or host.bazzite() or steamos
    host_details = []
    host_details.append("AMD BC-250 PCI device found" if bc250 else "AMD BC-250 PCI device not found")
    host_details.append("mutable systemd host" if mutable else "immutable, non-systemd, or unsupported host")
    requirements.append(_requirement(
        "host", "BC-250 hardware and writable system",
        bc250 and mutable, "; ".join(host_details),
        "An AMD BC-250 running a mutable systemd-based installation.",
        "Run this check on the BC-250 itself. Immutable images and systems without systemd are inspection-only.",
    ))

    os_release = host.read("/etc/os-release")
    distro_match = re.search(r'^ID=["\']?([^"\'\n]+)', os_release, re.M)
    pretty_match = re.search(r'^PRETTY_NAME=["\']?([^"\'\n]+)', os_release, re.M)
    distro = distro_match.group(1).lower() if distro_match else "unknown"
    pretty = pretty_match.group(1) if pretty_match else distro
    distro_ok = distro in {"arch", "cachyos", "manjaro"} or host.bazzite() or steamos
    requirements.append(_requirement(
        "distribution", "Qualified Linux distribution", distro_ok,
        pretty or "Distribution could not be identified",
        "Arch Linux, CachyOS, Manjaro, Bazzite (beta) or SteamOS (beta).",
        "Use the ACPI tool only from a qualified Arch-family installation. Other distributions remain inspection-only.",
    ))

    try:
        kernel_ok = kernel_support(host)
    except (OSError, ValueError, EOFError):
        kernel_ok = False
    requirements.append(_requirement(
        "kernel", "Kernel ACPI table upgrade support", kernel_ok,
        "CONFIG_ACPI_TABLE_UPGRADE=y" if kernel_ok else "CONFIG_ACPI_TABLE_UPGRADE=y was not confirmed",
        "A running kernel built with CONFIG_ACPI_TABLE_UPGRADE=y.",
        "Install and boot a kernel that enables ACPI table upgrades, then run this check again.",
    ))

    efi = host.path("/sys/firmware/efi")
    secure_ok = True
    secure_detected = "Legacy/BIOS boot; Secure Boot is not active"
    secure_resolution = "Disable Secure Boot in firmware before using this unsigned ACPI boot payload."
    if efi.exists():
        try:
            variables = list((efi / "efivars").glob("SecureBoot-*"))
            if variables:
                enabled = any(path.read_bytes()[4:5] != b"\0" for path in variables)
                secure_ok = not enabled
                secure_detected = "enabled" if enabled else "disabled"
            else:
                provisioning = tuple((efi / "efivars").glob("SetupMode-*")) + tuple((efi / "efivars").glob("PK-*"))
                secure_ok = not provisioning
                secure_detected = ("state is incomplete or unavailable" if provisioning
                                   else "not implemented by this firmware")
                secure_resolution = "Confirm that Secure Boot is disabled in firmware, then run the check again."
        except OSError:
            secure_ok = False
            secure_detected = "state could not be read"
            secure_resolution = "Run Check status with administrator authorization and confirm Secure Boot is disabled."
    requirements.append(_requirement(
        "secure-boot", "Secure Boot state", secure_ok, secure_detected,
        "Secure Boot disabled, unsupported by firmware, or a legacy BIOS boot.", secure_resolution,
    ))

    lockdown = host.read("/sys/kernel/security/lockdown")
    lockdown_ok = not lockdown or "[none]" in lockdown
    requirements.append(_requirement(
        "lockdown", "Kernel lockdown", lockdown_ok,
        lockdown or "inactive / interface not exposed",
        "Kernel lockdown must be inactive.",
        "Boot without integrity or confidentiality lockdown before installing the ACPI payload.",
    ))

    tables_ok = bool(state) or live == "stock"
    table_names = {"stock": "stock BC-250 tables", "active": "BC250 Control Center payload is active",
                   "foreign": "tables modified by another ACPI fix", "unknown": "stock tables could not be confirmed",
                   "outdated": "an earlier release of the BC250 ACPI fix is active"}
    requirements.append(_requirement(
        "tables", "ACPI table state", tables_ok, table_names.get(live, live),
        "Unmodified stock BC-250 ACPI tables, or this application's tracked installation.",
        "Remove or review any previous ACPI override first. Never stack two ACPI fixes.",
    ))

    conflicts = []
    if not state:
        for directory in ("/etc/initcpio/acpi_override", "/usr/lib/initcpio/acpi_override"):
            if any(host.path(directory).glob("*.aml")):
                conflicts.append(directory + "/*.aml")
        if "GRUB_EARLY_INITRD_LINUX_CUSTOM" in host.read(GRUB_CONFIG):
            conflicts.append("GRUB_EARLY_INITRD_LINUX_CUSTOM")
        if host.bazzite() and host.path(BAZZITE_UPSTREAM_PAYLOAD).exists():
            conflicts.append(BAZZITE_UPSTREAM_PAYLOAD)
        if steamos:
            conflicts.extend(name for name in STEAMOS_FOREIGN if host.path(name).exists())
            foreign = _steamos_foreign_early_initrd(host)
            if foreign and "GRUB_EARLY_INITRD_LINUX_CUSTOM" not in conflicts:
                conflicts.append(f"GRUB_EARLY_INITRD_LINUX_CUSTOM ({foreign})")
    requirements.append(_requirement(
        "conflicts", "Existing ACPI override conflicts", not conflicts,
        ", ".join(conflicts) if conflicts else ("installation tracked by BC250 Control Center" if state else "none found"),
        "No untracked AML override or custom GRUB early-initrd injection.",
        "Review and remove the previous override using the tool that installed it, then check again.",
    ))

    try:
        plan = boot_plan(host)
        boot_ok = True
        boot_detected = ("conventional GRUB kernel + external initramfs" if plan["backend"] == "grub"
                         else "Bazzite GRUB with ostree boot entries (blscfg)" if plan["backend"] == "bazzite-bls"
                         else "SteamOS GRUB menu generated from /etc/default/grub.d" if plan["backend"] == "steamos-grub"
                         else "systemd-boot Type #1 kernel + external initramfs")
        boot_resolution = ""
    except (SetupError, OSError, ValueError, KeyError, IndexError) as exc:
        boot_ok = False
        boot_detected = str(exc)
        if "EFI/UKI" in boot_detected or "UKI" in boot_detected:
            boot_resolution = ("Keep the current UKI as a recovery option, generate an external initramfs image "
                               "(kept separate from the kernel), "
                               "and boot the conventional GRUB or systemd-boot Type #1 entry before retrying.")
        elif "running kernel's GRUB entry" in boot_detected:
            boot_resolution = "Boot the conventional GRUB entry that loads vmlinuz and an external initramfs, then retry."
        else:
            boot_resolution = ("Configure and boot either a simple GRUB entry or a systemd-boot Type #1 entry "
                               "that uses separate kernel and initramfs files.")
    requirements.append(_requirement(
        "boot", "Supported boot layout", boot_ok, boot_detected,
        "Conventional GRUB or systemd-boot Type #1 with separate kernel and initramfs files.", boot_resolution,
    ))
    return requirements


def installation_summary(result: dict) -> tuple[str, str]:
    summaries = {
        "active": ("ACTIVE", "The ACPI fix is installed and active. No installation is needed."),
        "pending-reboot": ("REBOOT REQUIRED", "The ACPI fix is installed. Reboot to activate it, then check status."),
        "not-active": ("NOT ACTIVE", "The ACPI fix is installed but its tables are not active. Boot the BC250 ACPI entry, then check status."),
        "incomplete": ("INCOMPLETE", "The ACPI installation is incomplete. Review its status and uninstall before retrying."),
        "outdated": ("UPDATE AVAILABLE", f"The installed ACPI fix is an earlier release whose C3 idle state can freeze the board. Use Update correction to install v{VERSION}, then reboot."),
        "managed-elsewhere": ("MANAGED EXTERNALLY", "ACPI tables are supplied by firmware or another tool. Do not install a second fix."),
        "needs-repair": ("REPAIR REQUIRED", "A SteamOS update replaced /boot, so this image boots without the ACPI tables. Use Repair correction, then reboot."),
    }
    if result.get("status") == "not-installed" and not result.get("installed"):
        if result.get("available"):
            return "READY", "The ACPI fix is not installed. Installation is available."
        return "BLOCKED", "The ACPI fix is not installed. Resolve the compatibility issues before installing."
    return summaries.get(result.get("status"), (
        "CHECK REQUIRED", "ACPI installation status is unconfirmed. Run Check status with administrator authorization.",
    ))


def requirements_report(result: dict, *, width: int = 78) -> str:
    """Render the privileged compatibility result as a novice-friendly box."""
    width = max(68, min(int(width), 96))
    inner = width - 2
    lines = ["┌" + "─" * inner + "┐"]

    def row(text: str = "") -> None:
        lines.append("│" + text[:inner].ljust(inner) + "│")

    def wrapped(prefix: str, value: str) -> None:
        available = inner - len(prefix) - 1
        chunks = textwrap.wrap(str(value), width=max(24, available), break_long_words=False,
                               break_on_hyphens=False) or [""]
        row(" " + prefix + chunks[0])
        continuation = " " * (len(prefix) + 1)
        for chunk in chunks[1:]:
            row(continuation + chunk)

    row(" BC250 ACPI FIX · COMPATIBILITY CHECK")
    row(" Read-only inspection · No system setting was changed")
    lines.append("├" + "─" * inner + "┤")
    requirements = result.get("requirements") or []
    short_titles = {
        "host": "Hardware and system",
        "distribution": "Linux distribution",
        "kernel": "Kernel ACPI support",
        "secure-boot": "Secure Boot",
        "lockdown": "Kernel lockdown",
        "tables": "ACPI tables",
        "conflicts": "Override conflicts",
        "boot": "Boot layout",
    }
    failed = []
    for item in requirements:
        passed = bool(item.get("passed"))
        mark = "✓" if passed else "✕"
        title = short_titles.get(item.get("id"), item.get("title", "Requirement"))
        detected = str(item.get("detected", "unknown"))
        prefix = f" {mark} {title}: "
        wrapped(prefix, detected)
        if not passed:
            failed.append(item)
    lines.append("├" + "─" * inner + "┤")
    passed = sum(bool(item.get("passed")) for item in requirements)
    total = len(requirements)
    verdict, summary = installation_summary(result)
    row(f" {verdict} · {passed}/{total} requirements passed")
    if failed:
        row()
        row(" WHAT YOU NEED TO FIX")
        for item in failed:
            wrapped(" Required: ", item.get("required", ""))
            wrapped(" Next step: ", item.get("resolution", "Review the detected state."))
    else:
        row(" All compatibility requirements were detected successfully.")
    row()
    wrapped(" Documentation: ", UPSTREAM_URL)
    wrapped(" ", summary)
    lines.append("└" + "─" * inner + "┘")
    return "\n".join(lines)


def _steamos_recovered_state(host: Host) -> dict:
    """The journal for an installation whose journal did not survive.

    The journal lives in /var; the drop-in, carried over by SteamOS's keep
    list and marked as ours, is the proof that the installation is ours.
    """
    if _steamos_host(host) and _steamos_owned(host):
        return {"backend": "steamos-grub", "mount": "/boot", "phase": "installed",
                "payload": STEAMOS_PAYLOAD, "entry": STEAMOS_DROPIN, "sha256": SHA256}
    return {}


def status(host: Host, *, cached: bool = True) -> dict:
    state = host.state("acpi") or _steamos_recovered_state(host)
    steamos = _steamos_host(host)
    live, tables = table_status(host)
    result = {"available": False, "installed": bool(state), "status": "not-installed",
              "tables": tables, "version": VERSION, "reason": "", "backend": ""}
    result["cpufreq_driver"] = host.read("/sys/devices/system/cpu/cpufreq/policy0/scaling_driver")
    result["cpuidle_driver"] = host.read("/sys/devices/system/cpu/cpuidle/current_driver")
    if state:
        result["status"] = ("active" if live == "active" else
                            "pending-reboot" if state.get("boot_id") == host.read("/proc/sys/kernel/random/boot_id")
                            else "not-active")
        if state.get("phase") != "installed":
            result["status"] = "incomplete"
        elif state.get("backend") == "steamos-grub" and live != "active" and _steamos_needs_repair(host):
            result["status"] = "needs-repair"
    elif live in {"active", "foreign", "outdated"}:
        result["status"] = "managed-elsewhere"
    try:
        bazzite = host.bazzite() and host.path("/run/systemd/system").is_dir()
        if not (host.mutable_systemd() or bazzite or steamos) or not host.bc250():
            raise SetupError("Requires a supported mutable systemd distribution and BC250 hardware")
        os_release = host.read("/etc/os-release")
        if not (bazzite or steamos) and not re.search(r'^ID=["\']?(arch|cachyos|manjaro)["\']?$', os_release, re.M):
            raise SetupError("ACPI installation is qualified for Arch, CachyOS, Manjaro, Bazzite and SteamOS layouts")
        if not kernel_support(host):
            raise SetupError("ACPI_TABLE_UPGRADE support could not be confirmed for the running kernel")
        efi = host.path("/sys/firmware/efi")
        if efi.exists():
            variables = list((efi / "efivars").glob("SecureBoot-*"))
            if variables and any(p.read_bytes()[4:5] != b"\0" for p in variables):
                raise SetupError("Secure Boot is enabled; signed boot configurations require separate qualification")
            if not variables:
                # Older BC250 firmware can expose UEFI/efivarfs without
                # implementing Secure Boot at all. Treat absence as
                # unsupported only when no provisioning variables exist.
                provisioning = tuple((efi / "efivars").glob("SetupMode-*")) + tuple((efi / "efivars").glob("PK-*"))
                if provisioning:
                    raise SetupError("Secure Boot state is incomplete; signed boot configurations require separate qualification")
        lockdown = host.read("/sys/kernel/security/lockdown")
        if lockdown and "[none]" not in lockdown:
            raise SetupError("Kernel lockdown is active")
        if not state and live != "stock":
            raise SetupError("Stock ACPI tables not confirmed, or firmware/another tool already supplies a fix")
        if not state:
            for directory in ("/etc/initcpio/acpi_override", "/usr/lib/initcpio/acpi_override"):
                if any(host.path(directory).glob("*.aml")):
                    raise SetupError("Existing ACPI injection must be reviewed before installing another fix")
            if "GRUB_EARLY_INITRD_LINUX_CUSTOM" in host.read(GRUB_CONFIG):
                raise SetupError("Existing early initrd configuration requires manual conflict review")
            if bazzite and host.path(BAZZITE_UPSTREAM_PAYLOAD).exists():
                raise SetupError("Upstream's manual install (/boot/acpi_override.cpio) is present; remove it first")
            if steamos:
                for name in STEAMOS_FOREIGN:
                    if host.path(name).exists():
                        raise SetupError(f"Another SteamOS toolkit already installs ACPI tables ({name}); remove it first")
                if _steamos_foreign_early_initrd(host):
                    raise SetupError("Existing early initrd configuration requires manual conflict review")
        plan = boot_plan(host)
        if plan["backend"] == "bazzite-bls" and not state and plan.get("env_early_initrd"):
            raise SetupError("grubenv already loads an early initrd; review it before installing another")
        result.update(available=True, backend=plan["backend"])
    except (SetupError, OSError, ValueError, KeyError, IndexError) as exc:
        result["reason"] = str(exc)
    result["requirements"] = compatibility_requirements(host, state, live)
    # /boot is commonly 0700. A desktop read must not need root every refresh.
    # Only an explicitly requested privileged check creates this bounded cache;
    # install() always repeats the full inspection as root before writing.
    if cached and os.geteuid() != 0:
        probe = host.state("acpi-probe")
        if (probe.get("schema") == PROBE_SCHEMA
                and probe.get("boot_id") == host.read("/proc/sys/kernel/random/boot_id")
                and probe.get("kernel") == os.uname().release
                and probe.get("phase") == state.get("phase")):
            result.update(available=bool(probe.get("available")),
                          backend=probe.get("backend", ""), reason=probe.get("reason", ""),
                          status=probe.get("status", result["status"]), tables=probe.get("tables", []),
                          requirements=probe.get("requirements", result["requirements"]), cached_probe=True)
        elif live == "unknown":
            result.update(available=False, status="needs-check",
                          reason="Use Check status to inspect protected ACPI tables and boot files")
    # Decided by the journal alone, so neither a cached probe nor unreadable
    # tables can hide it: what is on disk is an earlier pinned payload.
    installed_version = SUPERSEDED.get(state.get("sha256", "")) if state else None
    if installed_version and state.get("phase") == "installed":
        result.update(status="outdated", update_available=True, installed_version=installed_version)
    return result


def check(host: Host) -> dict:
    result = status(host, cached=False)
    host.save("acpi-probe", {key: result[key] for key in ("available", "backend", "reason", "status", "tables", "requirements")} | {
        "boot_id": host.read("/proc/sys/kernel/random/boot_id"), "kernel": os.uname().release,
        "phase": host.state("acpi").get("phase"), "schema": PROBE_SCHEMA,
    })
    return result


def install(host: Host) -> dict:
    host.require_host(steamos=True, bazzite=True)
    host.safe(STATE)
    current = status(host, cached=False)
    if current["installed"]:
        raise SetupError("ACPI setup already exists; check its status or uninstall before retrying")
    if not current["available"]:
        raise SetupError(current["reason"])
    plan = boot_plan(host)
    mount = plan["mount"]
    payload = mount + "/bc250-acpi.cpio"
    if plan["backend"] == "steamos-grub":
        state = {**plan, "phase": "preparing", "boot_id": host.read("/proc/sys/kernel/random/boot_id"),
                 "payload": STEAMOS_PAYLOAD, "entry": STEAMOS_DROPIN, "sha256": SHA256}
        host.save("acpi", state)
        try:
            _steamos_install(host)
        except Exception:
            # Everything it wrote was taken back; so is the journal.
            host.safe(f"{STATE}/acpi.json").unlink(missing_ok=True)
            raise
        state["phase"] = "installed"
        host.save("acpi", state)
        return check(host)
    if plan["backend"] == "bazzite-bls":
        if host.safe(payload).exists():
            raise SetupError(f"Existing file preserved: {payload}")
        state = {**plan, "phase": "preparing", "boot_id": host.read("/proc/sys/kernel/random/boot_id"),
                 "payload": payload, "entry": BAZZITE_CUSTOM, "sha256": SHA256}
        host.save("acpi", state)
        try:
            state.update(_bazzite_install(host, payload))
            state["phase"] = "installed"
            host.save("acpi", state)
        except Exception:
            try:
                uninstall(host)
            except Exception:
                state["phase"] = "incomplete"
                host.save("acpi", state)
            raise
        return check(host)
    entry = (mount + "/loader/entries/bc250-acpi.conf") if plan["backend"] == "systemd-boot" else GRUB_SCRIPT
    for name in (payload, entry):
        if host.safe(name).exists():
            raise SetupError(f"Existing file preserved: {name}")
    state = {**plan, "phase": "preparing", "boot_id": host.read("/proc/sys/kernel/random/boot_id"),
             "payload": payload, "entry": entry, "sha256": SHA256}
    host.save("acpi", state)
    try:
        host.write(payload, archive())
        if plan["backend"] == "systemd-boot":
            text = re.sub(r"^title\s+.*$", "title BC250 ACPI (original entry retained)", plan["entry_text"], flags=re.M)
            text = re.sub(r"^(linux\s+.*)$", r"\1\ninitrd /bc250-acpi.cpio", text, count=1, flags=re.M)
            host.managed(entry, text + "\n")
            host.run("bootctl", "set-default", "bc250-acpi.conf")
        else:
            body = ("menuentry 'BC250 ACPI (original entry retained)' --id bc250-acpi {\n"
                    f" search --no-floppy --fs-uuid --set=root {plan['uuid']}\n "
                    + " ".join(plan["linux"]) + "\n initrd " + plan["cpio_grub"] + " "
                    + " ".join(plan["initrd"]) + "\n}\n")
            # A fixed here-document, no interpolation or execution of config data.
            host.write(entry, "#!/bin/sh\n" + MARKER + "cat <<'BC250_ACPI_ENTRY'\n" + body + "BC250_ACPI_ENTRY\n", mode=0o755)
            original = host.read(GRUB_CONFIG)
            if "BEGIN BC250 ACPI DEFAULT" in original:
                raise SetupError("An untracked BC250 GRUB block already exists")
            host.write(f"{STATE}/grub-before-acpi", host.path(GRUB_CONFIG).read_bytes())
            host.write(GRUB_CONFIG, host.path(GRUB_CONFIG).read_text() + GRUB_BLOCK)
            host.run("grub-mkconfig", "-o", GRUB_OUTPUT)
            generated = host.read(GRUB_OUTPUT)
            if "--id bc250-acpi" not in generated or plan["cpio_grub"] not in generated:
                raise SetupError("GRUB did not include the ACPI entry; restoring the original default")
        state["phase"] = "installed"
        host.save("acpi", state)
    except Exception:
        # Keep a journal and original entry even when rollback generation fails.
        try:
            uninstall(host)
        except Exception:
            state["phase"] = "incomplete"
            host.save("acpi", state)
        raise
    return check(host)


def update(host: Host) -> dict:
    """Replace an earlier pinned payload in place; the boot entry is unchanged.

    The entry already loads ``bc250-acpi.cpio`` from the journaled mount, so
    only that file and the journal's digest change.
    """
    host.require_host(steamos=True, bazzite=True)
    host.safe(STATE)
    state = host.state("acpi") or _steamos_recovered_state(host)
    if not state:
        raise SetupError("No ACPI installation owned by Control Center")
    if state.get("phase") != "installed":
        raise SetupError("The ACPI installation is incomplete; uninstall before retrying")
    if state.get("backend") == "steamos-grub" and _steamos_needs_repair(host):
        # A SteamOS update brought a /boot without the archive: write it
        # again (the current release) and regenerate the verified menu.
        _steamos_put_payload(host)
        host.managed(STEAMOS_DROPIN, STEAMOS_DROPIN_LINE)
        host.managed(STEAMOS_KEEP, STEAMOS_DROPIN + "\n")
        _steamos_regenerate(host, tables=True)
        host.save("acpi", state | {"sha256": SHA256, "boot_id": host.read("/proc/sys/kernel/random/boot_id")})
        return check(host)
    if state.get("sha256") == SHA256:
        raise SetupError(f"The ACPI fix is already at v{VERSION}")
    if state.get("sha256") not in SUPERSEDED:
        raise SetupError("The installed ACPI payload is not a release this application recognizes")
    mount = state.get("mount")
    if mount not in {"/boot", "/efi", "/boot/efi"}:
        raise SetupError("Invalid ACPI installation journal")
    payload = mount + "/bc250-acpi.cpio"
    path = host.safe(payload)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != state["sha256"]:
        raise SetupError("Modified or missing ACPI payload preserved for manual review")
    host.write(payload, archive())
    host.save("acpi", state | {"sha256": SHA256, "boot_id": host.read("/proc/sys/kernel/random/boot_id")})
    return check(host)


def uninstall(host: Host) -> dict:
    host.safe(STATE)
    state = host.state("acpi") or _steamos_recovered_state(host)
    if not state:
        raise SetupError("No ACPI installation owned by Control Center")
    # Never take arbitrary deletion paths from a manifest, even root-owned.
    mount = state.get("mount")
    if mount not in {"/boot", "/efi", "/boot/efi"}:
        raise SetupError("Invalid ACPI installation journal")
    if state.get("backend") == "systemd-boot":
        entry = mount + "/loader/entries/bc250-acpi.conf"
        if efi_string(host, "LoaderEntryDefault") == "bc250-acpi.conf":
            original = state.get("original_default", "")
            if not re.fullmatch(r"[A-Za-z0-9_.+@*?-]*", original):
                raise SetupError("Invalid saved boot default")
            host.run("bootctl", "set-default", original)
        host.remove_managed(entry)
    elif state.get("backend") == "bazzite-bls":
        _bazzite_uninstall(host, state)
    elif state.get("backend") == "steamos-grub":
        _steamos_uninstall(host)
    elif state.get("backend") == "grub":
        text = host.path(GRUB_CONFIG).read_text()
        if GRUB_BLOCK in text:
            host.write(GRUB_CONFIG, text.replace(GRUB_BLOCK, ""))
        elif "BEGIN BC250 ACPI DEFAULT" in text:
            raise SetupError("The BC250 GRUB block was edited; manual recovery required")
        path = host.safe(GRUB_SCRIPT)
        if path.exists():
            if MARKER.strip() not in host.read(GRUB_SCRIPT).splitlines():
                raise SetupError("GRUB entry belongs to another tool")
            path.unlink()
        host.run("grub-mkconfig", "-o", GRUB_OUTPUT)
    else:
        raise SetupError("Invalid ACPI boot backend")
    payload = host.safe(mount + "/bc250-acpi.cpio")
    if payload.exists():
        if hashlib.sha256(payload.read_bytes()).hexdigest() not in {SHA256, *SUPERSEDED}:
            raise SetupError("Modified ACPI payload preserved for manual review")
        payload.unlink()
    host.safe(f"{STATE}/acpi.json").unlink(missing_ok=True)
    probe = host.safe(f"{STATE}/acpi-probe.json")
    if probe.exists():
        probe.unlink()
    return {"status": "removed-pending-reboot", "installed": False}
