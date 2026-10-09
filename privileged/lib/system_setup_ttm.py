"""The GPU memory limit (TTM ``pages_limit``), one implementation for every host.

Why a boot argument and not the sysfs knob: amdgpu sizes its GTT domain once,
when the driver initialises, from ``ttm_tt_pages_limit()``
(drivers/gpu/drm/amd/amdgpu/amdgpu_ttm.c). On a BC-250 amdgpu loads from the
initramfs, long before any service could write
``/sys/module/ttm/parameters/pages_limit``; a value written there later moves
TTM's global page cap but never the GTT size the driver and Mesa report. So the
value has to be on the kernel command line, and it takes effect at the next
boot, the same way everywhere:

* Arch, CachyOS, Manjaro, Debian, Ubuntu, Fedora, Nobara: the kernel-options
  block this project already manages for mitigations/nosmt/CU unlock
  (Limine, GRUB or grubby, see system_setup_kernel_args.py).
* Bazzite and other rpm-ostree images: ``rpm-ostree kargs``. The arguments
  found before the first change are journalled in
  ``/etc/bc250-control-center/ttm-kargs.original`` -- the same file, in the
  same format, the desktop's Bazzite memory workflow has always used -- so a
  limit set from either place is restored from either place.
* SteamOS (beta): a drop-in in ``/etc/default/grub.d`` and a regenerated
  ``/efi/EFI/steamos/grub.cfg``, kept across updates by a keep list (see
  system_setup_kernel_args.py).

Releases before this one wrote the sysfs knob at boot from
``bc250-memory-setup.service``. That setting is recognised as ours, reported,
and dropped the next time the limit is set or restored.

The desktop and the Decky panel both reach this module through
``bc250-system-setup-helper`` (``ttm-status`` / ``ttm-apply``), so they read
and write one state.
"""
from __future__ import annotations

import os
import re

import system_setup_kernel_args as kernel_args
from system_setup_common import Host, SetupError

GIB = 1024 ** 3
NAME = "ttm.pages_limit"
PARAMETER = "/sys/module/ttm/parameters/pages_limit"
#: The deprecated amdgpu option overrides the TTM limit for the GTT size.
GTT_OVERRIDE = "amdgpu.gttsize"
PRESETS_GIB = (8, 10, 12)
DEFAULT = -1
CMDLINE = "/proc/cmdline"
MEMINFO = "/proc/meminfo"
DRM = "/sys/class/drm"
OSTREE_STATE = "/etc/bc250-control-center/ttm-kargs.original"
OSTREE_MARKER = "# Managed by BC250 Control Center"
_KARG = re.compile(r"ttm\.pages_limit=[0-9]+")
_STEAMOS = (
    "This SteamOS has no GRUB that reads /etc/default/grub.d, so a GPU memory "
    "limit set here would not survive. It needs the ttm.pages_limit kernel argument."
)


def page_size() -> int:
    return int(os.sysconf("SC_PAGE_SIZE"))


def pages_for(gib: int, size: int | None = None) -> int:
    size = size or page_size()
    if type(gib) is not int or gib not in PRESETS_GIB:
        raise SetupError("The GPU memory limit must be 8, 10 or 12 GiB")
    if GIB % size:
        raise SetupError("This kernel's page size cannot express a whole GiB")
    return gib * GIB // size


def _number(text: str) -> int | None:
    text = str(text or "").strip()
    return int(text) if text.isdigit() else None


def _value(tokens, name: str) -> int | None:
    found = None
    for token in tokens:
        if token.startswith(name + "="):
            found = token.split("=", 1)[1]
    return _number(found) if found is not None else None


def physical_ram(host: Host) -> int | None:
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB", host.read(MEMINFO), re.M)
    return int(match[1]) * 1024 if match else None


def _amdgpu(host: Host, attribute: str) -> int | None:
    """One ``mem_info_*`` value of the AMD GPU, in bytes."""
    for device in sorted(host.path(DRM).glob("card*/device")):
        try:
            if (device / "vendor").read_text().strip().lower() != "0x1002":
                continue
            return _number((device / attribute).read_text())
        except OSError:
            continue
    return None


def backend(host: Host) -> tuple[str, str]:
    """How this host keeps a kernel argument, and why not when it cannot."""
    release = host.os_release()
    identifiers = {release.get("ID", ""), *release.get("ID_LIKE", "").split(), release.get("VARIANT_ID", "")}
    if identifiers & {"steamos", "holo"}:
        if kernel_args.backend(host) == "steamos-grub":
            return "steamos-grub", ""
        return "unsupported", _STEAMOS
    if host.path("/run/ostree-booted").exists():
        if host.command("rpm-ostree"):
            return "rpm-ostree", ""
        return "unsupported", "This image-based system has no rpm-ostree to set kernel arguments with."
    if host.immutable_image():
        return "unsupported", "This image-based system has no supported way to set kernel arguments."
    loader = kernel_args.backend(host)
    if loader == "unsupported":
        return "unsupported", (
            "No Limine, GRUB or grubby boot configuration was found; systemd-boot and rEFInd "
            "are not managed. Add the argument shown to the kernel command line yourself."
        )
    return loader, ""


def _legacy(host: Host) -> int | None:
    """A limit an earlier release re-applied through sysfs at every boot."""
    try:
        state = host.state("memory")
    except SetupError:
        return None
    return _number(state.get("ttm_pages")) if state.get("ttm_pages") is not None else None


def _forget_legacy(host: Host) -> None:
    """Drop the old boot-time sysfs write. The live value is left alone: the
    GTT size was fixed at boot anyway, and lowering TTM's cap under a running
    game would only force its buffers out."""
    if _legacy(host) is None:
        return
    import system_setup_memory as memory  # the memory module imports this one

    state = host.state("memory")
    state.pop("ttm_pages", None)
    state.pop("ttm_original", None)
    host.save("memory", state)
    memory.settle_service(host, state)


#: A read of the arguments is quick; only changing them writes a deployment.
#: Together they stay well inside the 240 s the Quick Access helper allows.
OSTREE_READ_SECONDS = 25
OSTREE_WRITE_SECONDS = 170


def _ostree_tokens(host: Host) -> list[str]:
    """Arguments of the deployment the next boot uses."""
    return host.run("rpm-ostree", "kargs", timeout=OSTREE_READ_SECONDS).split()


def _ostree_saved(host: Host) -> list[str] | None:
    """The arguments found before the first change, or None if nothing is ours."""
    path = host.safe(OSTREE_STATE)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise SetupError("The saved TTM arguments are not protected; they were left as they are")
    lines = host.read(OSTREE_STATE).splitlines()
    if not lines or lines[0].strip() != OSTREE_MARKER:
        raise SetupError("The saved TTM arguments belong to another tool; they were left as they are")
    saved = [line.strip() for line in lines[1:] if line.strip()]
    if any(not _KARG.fullmatch(token) for token in saved):
        raise SetupError("The saved TTM arguments are malformed; they were left as they are")
    return saved


def _record(host: Host) -> dict:
    """What the last rpm-ostree change asked the next boot for."""
    try:
        return host.state("ttm")
    except SetupError:
        return {}


def next_boot_ram(host: Host, cmos_uma_mb: int | None) -> int | None:
    """System memory after the next boot, when a new VRAM size is waiting in CMOS.

    The VRAM carve-out comes out of the same 16 GB: a larger VRAM size written
    to CMOS leaves less for the system, and so less room for a GPU memory
    limit, once the board restarts.
    """
    ram = physical_ram(host)
    active = _amdgpu(host, "mem_info_vram_total")
    if ram is None or active is None or not cmos_uma_mb:
        return None
    planned = int(cmos_uma_mb) * 1024 * 1024
    # The firmware rounds the carve-out; differences under 64 MiB are not a new size.
    if abs(planned - active) < 64 * 1024 * 1024:
        return None
    return max(0, ram + active - planned)


def summary(host: Host) -> dict:
    """Whether a limit can be set and which one is ours, without running anything.

    For the memory panel's older fields, which are read on every refresh.
    """
    kind, _reason = backend(host)
    managed_pages = None
    managed = False
    try:
        if kind == "rpm-ostree":
            managed = host.path(OSTREE_STATE).exists()
            record = _record(host)
            managed_pages = _number(record.get("configured_pages")) if managed else None
        elif kind != "unsupported":
            value = kernel_args._values(host.state(kernel_args._STATE_KEY)).get(NAME)
            managed = value is not None
            managed_pages = _number(value)
    except SetupError:
        pass
    return {
        "supported": kind != "unsupported" and host.bc250(),
        "managed": managed,
        "managed_pages": managed_pages,
    }


def status(host: Host, *, next_boot_ram: int | None = None, probe: bool = True,
           ostree_tokens: list[str] | None = None) -> dict:
    """Everything a panel needs to show and offer the limit. Never raises.

    ``probe`` asks rpm-ostree for the next deployment's arguments; without it
    (the desktop's periodic, unprivileged inventory) the last recorded change
    stands in for them. ``ostree_tokens`` are arguments the caller just read.
    """
    kind, reason = backend(host)
    size = page_size()
    command_line = host.read(CMDLINE).split()
    ram = physical_ram(host)
    known = [value for value in (ram, next_boot_ram) if value]
    ceiling = min(known) if known else None
    result = {
        "supported": False,
        "backend": kind,
        "reason": reason,
        "page_size": size,
        "presets_gib": [gib for gib in PRESETS_GIB if ceiling and gib * GIB <= ceiling],
        "manual_arguments": (
            {str(gib): f"{NAME}={gib * GIB // size}" for gib in PRESETS_GIB} if GIB % size == 0 else {}
        ),
        "physical_ram_bytes": ram,
        "next_boot_ram_bytes": next_boot_ram,
        "live_pages": _number(host.read(PARAMETER)),
        "boot_pages": _value(command_line, NAME),
        "configured_pages": None,
        "managed": False,
        "managed_pages": None,
        "external": False,
        "external_pages": None,
        "gtt_total_bytes": _amdgpu(host, "mem_info_gtt_total"),
        "gtt_override": _value(command_line, GTT_OVERRIDE),
        "legacy_pages": _legacy(host),
        "reboot_required": False,
    }
    if not host.bc250():
        result.update(backend="unsupported", reason="AMD BC-250 hardware identity was not detected.")
        return result
    try:
        if kind == "rpm-ostree":
            if probe or ostree_tokens is not None:
                tokens = ostree_tokens if ostree_tokens is not None else _ostree_tokens(host)
                managed = _ostree_saved(host) is not None
                configured = _value(tokens, NAME)
                result["gtt_override"] = result["gtt_override"] or _value(tokens, GTT_OVERRIDE)
            else:
                managed = host.path(OSTREE_STATE).exists()
                record = _record(host)
                configured = (
                    _number(record.get("configured_pages")) if "configured_pages" in record
                    else result["boot_pages"]
                )
            result.update(
                configured_pages=configured,
                managed=managed,
                managed_pages=configured if managed else None,
                # The Bazzite workflow always journalled what it found and put
                # it back on restore, so a value present before is reported
                # but not refused: the first change saves it, restore returns it.
                external=False,
                external_pages=configured if not managed else None,
            )
        elif kind != "unsupported":
            item = kernel_args.status(host)["values"][NAME]
            managed = _number(item["managed"]) if item["managed"] is not None else None
            result.update(
                configured_pages=_number(item["configured"]) if item["configured"] is not None else None,
                managed=managed is not None,
                managed_pages=managed,
                external=bool(item["external"]),
                external_pages=_number(item["external_value"]) if item["external_value"] else None,
            )
    except SetupError as error:
        result.update(reason=str(error), backend="unsupported", supported=False)
        return result
    result["supported"] = kind != "unsupported"
    result["reboot_required"] = result["supported"] and result["configured_pages"] != result["boot_pages"]
    return result


def apply(host: Host, gib: int, *, next_boot_ram: int | None = None) -> dict:
    """Set the limit for the next boot (8, 10 or 12 GiB), or ``DEFAULT``."""
    if type(gib) is not int or gib not in {DEFAULT, *PRESETS_GIB}:
        raise SetupError("The GPU memory limit must be 8, 10 or 12 GiB, or the kernel default")
    if not host.bc250():
        raise SetupError("HARDWARE_CONTEXT: AMD BC-250 hardware identity was not detected.")
    # One read of rpm-ostree serves the status and the change that follows.
    tokens = _ostree_tokens(host) if backend(host)[0] == "rpm-ostree" else None
    current = status(host, next_boot_ram=next_boot_ram, ostree_tokens=tokens)
    if gib == DEFAULT and not current["managed"] and current["legacy_pages"] is not None:
        # Only the old boot-time write to undo, which needs no boot loader.
        _forget_legacy(host)
        return status(host, next_boot_ram=next_boot_ram, ostree_tokens=tokens)
    if not current["supported"]:
        raise SetupError(current["reason"] or "This system cannot keep a GPU memory limit")
    kind = current["backend"]
    if gib != DEFAULT:
        if gib not in current["presets_gib"]:
            raise SetupError(
                f"{gib} GiB is more than the {round((current['next_boot_ram_bytes'] or current['physical_ram_bytes'] or 0) / GIB, 1)} GiB "
                "of system memory the next boot will have; choose a smaller limit or a smaller VRAM size"
            )
        if current["gtt_override"] is not None:
            raise SetupError(
                f"{GTT_OVERRIDE}={current['gtt_override']} is set on this system and overrides the "
                "TTM limit for the GPU; remove it first"
            )
        pages = pages_for(gib)
    elif not current["managed"] and current["legacy_pages"] is None:
        raise SetupError("No GPU memory limit set by Control Center to restore")
    if kind == "rpm-ostree":
        tokens = _apply_ostree(host, gib, tokens or [], pages if gib != DEFAULT else 0)
    else:
        if gib != DEFAULT:
            kernel_args.set_value(host, NAME, str(pages))
        elif current["managed"]:
            kernel_args.set_value(host, NAME, None)
    try:
        _forget_legacy(host)
    except SetupError:
        # The boot argument is saved; the old boot-time write stays reported
        # (legacy_pages) and is dropped by the next change.
        pass
    return status(host, next_boot_ram=next_boot_ram, ostree_tokens=tokens)


def _apply_ostree(host: Host, gib: int, tokens: list[str], pages: int) -> list[str]:
    """Change the limit through rpm-ostree and return the arguments that result."""
    present = [token for token in tokens if token.startswith(NAME + "=")]
    if any(not _KARG.fullmatch(token) for token in present):
        raise SetupError("A malformed ttm.pages_limit argument is present; it was left as it is")
    saved = _ostree_saved(host)
    arguments = [f"--delete-if-present={token}" for token in present]
    created = False
    changed = False
    if gib != DEFAULT:
        if saved is None:
            # Journal what was there before the first change; if rpm-ostree
            # then refuses, the journal goes again, so nothing foreign is ever
            # reported as ours.
            host.write(OSTREE_STATE, "\n".join([OSTREE_MARKER, *present]) + "\n", mode=0o600)
            created = True
        arguments.append(f"--append-if-missing={NAME}={pages}")
        changed = present != [f"{NAME}={pages}"]
    elif saved is not None:
        arguments += [f"--append-if-missing={token}" for token in saved]
        changed = sorted(present) != sorted(saved)
    try:
        if changed:
            host.run("rpm-ostree", "kargs", *arguments, timeout=OSTREE_WRITE_SECONDS)
    except Exception:
        if created:
            host.safe(OSTREE_STATE).unlink(missing_ok=True)
        raise
    if gib == DEFAULT and saved is not None:
        host.safe(OSTREE_STATE).unlink()
    if host.command("restorecon"):
        host.run("restorecon", "-RF", os.path.dirname(OSTREE_STATE), check=False)
    result = _ostree_tokens(host) if changed else tokens
    host.save("ttm", {"configured_pages": _value(result, NAME)})
    return result
