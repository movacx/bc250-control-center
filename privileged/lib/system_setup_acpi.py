"""ACPI through a separate boot entry, not a rewrite of the user's initramfs.

Initial qualification: Arch/CachyOS/Manjaro, GRUB simple Linux entries or
systemd-boot Type #1. UKI, Secure Boot, unknown layouts and foreign fixes are
intentionally diagnostic-only. The original boot entry is the recovery route.
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

from acpi_payload import SHA256, archive
from system_setup_common import MARKER, STATE, Host, SetupError

GRUB_SCRIPT = "/etc/grub.d/09_bc250_acpi"
GRUB_CONFIG = "/etc/default/grub"
GRUB_OUTPUT = "/boot/grub/grub.cfg"
GRUB_BLOCK = "\n# BEGIN BC250 ACPI DEFAULT\nGRUB_DEFAULT=bc250-acpi\n# END BC250 ACPI DEFAULT\n"
EFI_GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
PROBE_SCHEMA = 3
UPSTREAM_URL = "https://github.com/e-tho/bc250-acpi-fix"


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
        if (oem, name) in {("AMD", "AMD CPU"), ("HACK", "PSTATES"), ("HACK", "STUBS")}:
            if hashlib.sha256(data).digest() == expected.get(name):
                installed.add(name)
        if name in {"P_CST3", "PSTATES", "STUBS"} or (name == "AMD CPU" and revision >= 2):
            foreign = True
    if installed == {"AMD CPU", "PSTATES", "STUBS"} and cpu_tables == 1:
        return "active", tables
    return ("foreign" if foreign else "stock" if "AMD:AMD CPU:1" in tables else "unknown"), tables


def boot_plan(host: Host) -> dict:
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
        if stripped.startswith("linux "):
            parts = shlex.split(stripped)
            linux = parts if parts[1].rsplit("/", 1)[-1] == basename else None
        if linux and stripped.startswith("initrd "):
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
    mutable = host.mutable_systemd()
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
    distro_ok = distro in {"arch", "cachyos", "manjaro"}
    requirements.append(_requirement(
        "distribution", "Qualified Linux distribution", distro_ok,
        pretty or "Distribution could not be identified",
        "Arch Linux, CachyOS, or Manjaro.",
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
                   "foreign": "tables modified by another ACPI fix", "unknown": "stock tables could not be confirmed"}
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
    verdict = "READY" if result.get("available") else "BLOCKED"
    row(f" {verdict} · {passed}/{total} requirements passed")
    if failed:
        row()
        row(" WHAT YOU NEED TO FIX")
        for item in failed:
            wrapped(" Required: ", item.get("required", ""))
            wrapped(" Next step: ", item.get("resolution", "Review the detected state."))
    else:
        row(" All installation requirements were detected successfully.")
    row()
    wrapped(" Documentation: ", UPSTREAM_URL)
    row(" Check again after any change. Install only when the result is READY.")
    lines.append("└" + "─" * inner + "┘")
    return "\n".join(lines)


def status(host: Host, *, cached: bool = True) -> dict:
    state = host.state("acpi")
    live, tables = table_status(host)
    result = {"available": False, "installed": bool(state), "status": "not-installed",
              "tables": tables, "version": "1.1.0", "reason": "", "backend": ""}
    result["cpufreq_driver"] = host.read("/sys/devices/system/cpu/cpufreq/policy0/scaling_driver")
    result["cpuidle_driver"] = host.read("/sys/devices/system/cpu/cpuidle/current_driver")
    if state:
        result["status"] = ("active" if live == "active" else
                            "pending-reboot" if state.get("boot_id") == host.read("/proc/sys/kernel/random/boot_id")
                            else "not-active")
        if state.get("phase") != "installed":
            result["status"] = "incomplete"
    elif live in {"active", "foreign"}:
        result["status"] = "managed-elsewhere"
    try:
        if not host.mutable_systemd() or not host.bc250():
            raise SetupError("Requires a supported mutable systemd distribution and BC250 hardware")
        os_release = host.read("/etc/os-release")
        if not re.search(r'^ID=["\']?(arch|cachyos|manjaro)["\']?$', os_release, re.M):
            raise SetupError("ACPI installation is initially qualified only for Arch, CachyOS and Manjaro layouts")
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
        plan = boot_plan(host)
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
    return result


def check(host: Host) -> dict:
    result = status(host, cached=False)
    host.save("acpi-probe", {key: result[key] for key in ("available", "backend", "reason", "status", "tables", "requirements")} | {
        "boot_id": host.read("/proc/sys/kernel/random/boot_id"), "kernel": os.uname().release,
        "phase": host.state("acpi").get("phase"), "schema": PROBE_SCHEMA,
    })
    return result


def install(host: Host) -> dict:
    host.require_host()
    host.safe(STATE)
    current = status(host, cached=False)
    if current["installed"]:
        raise SetupError("ACPI setup already exists; check its status or uninstall before retrying")
    if not current["available"]:
        raise SetupError(current["reason"])
    plan = boot_plan(host)
    mount = plan["mount"]
    payload = mount + "/bc250-acpi.cpio"
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


def uninstall(host: Host) -> dict:
    host.safe(STATE)
    state = host.state("acpi")
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
        if hashlib.sha256(payload.read_bytes()).hexdigest() != SHA256:
            raise SetupError("Modified ACPI payload preserved for manual review")
        payload.unlink()
    host.safe(f"{STATE}/acpi.json").unlink()
    probe = host.safe(f"{STATE}/acpi-probe.json")
    if probe.exists():
        probe.unlink()
    return {"status": "removed-pending-reboot", "installed": False}
