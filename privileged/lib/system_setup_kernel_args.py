"""Three reviewed kernel boot options: ``mitigations=off``, ``nosmt`` and
``amdgpu.bc250_cc_write_mode=3``.

Bazzite has its own reversible ``mitigations=off`` card through rpm-ostree;
this is the same choice for mutable distributions, plus ``nosmt``, which
BC-250 owners asked for. The third, ``amdgpu.bc250_cc_write_mode=3``, makes the
BC-250 amdgpu kernel driver unlock all 40 compute units itself, which replaces
umr and the live CU manager; only a kernel that has that module parameter
(linux-cachyos-bc250) is offered it. Only these arguments exist here: the
caller names the set it wants managed, and anything else is refused.

Each boot loader is changed the way the eight-core telemetry repair already
does it:

* Limine (CachyOS): a marked block at the end of ``/etc/default/limine``,
  then ``limine-mkinitcpio``. Removing it leaves the file as it was.
* GRUB (Arch family, Debian, Ubuntu): a managed drop-in in
  ``/etc/default/grub.d``, which their ``grub-mkconfig`` reads; the main
  ``/etc/default/grub`` is never edited.
* grubby (Fedora, Nobara): ``grubby --update-kernel=ALL`` with only the
  arguments this module added, so arguments the owner set are left alone.

An argument already present that this module did not add is reported as
managed elsewhere and never touched. Everything applies at the next boot.
SteamOS is excluded: its updates rewrite the boot configuration.
"""
from __future__ import annotations

import re

from system_setup_common import Host, SetupError

CU_UNLOCK = "amdgpu.bc250_cc_write_mode=3"
#: The module parameter exists only on a kernel that carries the BC-250 patch;
#: on any other kernel the argument would be ignored and never take effect.
CU_UNLOCK_PARAMETER = "/sys/module/amdgpu/parameters/bc250_cc_write_mode"
CU_UNLOCK_PREFIX = "amdgpu.bc250_cc_write_mode="
ARGUMENTS = ("mitigations=off", "nosmt", CU_UNLOCK)
CMDLINE = "/proc/cmdline"
BOOT_ID = "/proc/sys/kernel/random/boot_id"
LIMINE_CONFIG = "/etc/default/limine"
GRUB_CONFIG = "/etc/default/grub"
GRUB_DROPIN = "/etc/default/grub.d/91-bc250-kernel-options.cfg"
GRUB_OUTPUTS = ("/boot/grub/grub.cfg", "/boot/grub2/grub.cfg")
LIMINE_BEGIN = "# BEGIN BC250 KERNEL OPTIONS"
LIMINE_END = "# END BC250 KERNEL OPTIONS"
_LIMINE_BLOCK = re.compile(
    rf"\n\n{re.escape(LIMINE_BEGIN)}\n[^\n]*\n{re.escape(LIMINE_END)}\n"
)
_STATE_KEY = "kernel-options"


def _tokens(text: str) -> set[str]:
    """Words of the uncommented lines, with shell quotes treated as spaces."""
    lines = (line for line in str(text or "").splitlines() if not line.lstrip().startswith("#"))
    return set(" ".join(lines).replace('"', " ").replace("'", " ").split())


def _read_exact(host: Host, name: str) -> str:
    try:
        return host.path(name).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _backend(host: Host) -> str:
    if host.immutable_image() or host.os_release().get("ID") == "steamos":
        # Bazzite keeps its own reviewed card; SteamOS rewrites its boot setup.
        return "unsupported"
    if host.path(LIMINE_CONFIG).is_file() and host.command("limine-mkinitcpio"):
        return "limine"
    if host.distro_family() == "fedora" and host.command("grubby"):
        return "grubby"
    if host.path(GRUB_CONFIG).is_file() and (
        host.command("update-grub") or host.command("grub-mkconfig") or host.command("grub2-mkconfig")
    ):
        return "grub"
    return "unsupported"


def _configured_tokens(host: Host, backend: str) -> set[str]:
    """Every word the boot configuration puts on the command line."""
    if backend == "limine":
        text = host.read(LIMINE_CONFIG)
    elif backend == "grub":
        text = host.read(GRUB_CONFIG) + "\n" + host.read(GRUB_DROPIN)
    elif backend == "grubby":
        text = host.run("grubby", "--info=DEFAULT", check=False)
    else:
        text = ""
    return _tokens(text)


def _configured(host: Host, backend: str) -> set[str]:
    """Arguments the boot configuration asks for, whoever wrote them."""
    tokens = _configured_tokens(host, backend)
    return {argument for argument in ARGUMENTS if argument in tokens}


def _other_cu_mode(tokens: set[str]) -> bool:
    """The write mode set to something other than 3, by somebody else."""
    return any(token.startswith(CU_UNLOCK_PREFIX) and token != CU_UNLOCK for token in tokens)


def status(host: Host) -> dict:
    backend = _backend(host)
    saved = host.state(_STATE_KEY)
    managed = set(saved.get("arguments") or ())
    # Removed by this module on this boot: still active until the reboot, but
    # not somebody else's setting.
    removing = set(saved.get("removed") or ()) if saved.get("boot_id") == host.read(BOOT_ID) else set()
    active = _tokens(host.read(CMDLINE))
    configured_tokens = _configured_tokens(host, backend)
    configured = {argument for argument in ARGUMENTS if argument in configured_tokens}
    # A different write mode, set by hand, would fight this one on the same
    # command line: it counts as somebody else's setting of the same option.
    foreign_cu_mode = _other_cu_mode(configured_tokens) or _other_cu_mode(active)
    arguments = {}
    for argument in ARGUMENTS:
        mine = argument in managed or argument in removing
        external = (argument in configured or argument in active) and not mine
        if argument == CU_UNLOCK and foreign_cu_mode and not mine:
            external = True
        arguments[argument] = {
            "active": argument in active,
            "managed": argument in managed,
            "configured": argument in managed or (argument in configured and not mine),
            "external": external,
        }
    mode = host.read(CU_UNLOCK_PARAMETER).strip()
    return {
        "backend": backend,
        "available": backend != "unsupported" and host.bc250(),
        "arguments": arguments,
        # Whether this kernel has the parameter at all, and what it is set to now.
        "cu_unlock": {
            "supported": host.path(CU_UNLOCK_PARAMETER).exists(),
            "mode": mode,
        },
        "reboot_required": any(
            item["configured"] != item["active"] for item in arguments.values()
        ),
    }


def _regenerate_grub(host: Host) -> None:
    if host.command("update-grub"):
        host.run("update-grub")
        return
    output = next((path for path in GRUB_OUTPUTS if host.path(path).exists()), "")
    if not output:
        raise SetupError("The active GRUB output file could not be identified")
    command = "grub2-mkconfig" if host.command("grub2-mkconfig") else "grub-mkconfig"
    host.run(command, "-o", output)


def apply(host: Host, wanted: list[str] | tuple[str, ...]) -> dict:
    """Make exactly ``wanted`` the set of arguments this module manages."""
    wanted_set = set(wanted)
    if wanted_set - set(ARGUMENTS):
        raise SetupError("Only mitigations=off, nosmt and amdgpu.bc250_cc_write_mode=3 can be managed here")
    if not host.bc250():
        raise SetupError("AMD BC-250 PCI device 1002:13fe was not found")
    current = status(host)
    backend = current["backend"]
    if backend == "unsupported":
        raise SetupError("No supported Limine, GRUB or grubby boot configuration was detected")
    saved = host.state(_STATE_KEY)
    if saved.get("arguments") and saved.get("backend") != backend:
        raise SetupError("The boot loader changed since these options were set; restore them first")
    for argument in wanted_set:
        if current["arguments"][argument]["external"]:
            raise SetupError(f"{argument} is already set outside Control Center and is left as it is")
    if (
        CU_UNLOCK in wanted_set
        and CU_UNLOCK not in set(saved.get("arguments") or ())
        and not current["cu_unlock"]["supported"]
    ):
        # Without the parameter the kernel ignores the argument: it would be
        # written, a reboot asked for, and nothing would change.
        raise SetupError(
            "This kernel has no amdgpu.bc250_cc_write_mode parameter, so the argument would do nothing. "
            "It comes with the BC-250 kernel (linux-cachyos-bc250)."
        )
    previous = set(saved.get("arguments") or ())
    wanted_list = [argument for argument in ARGUMENTS if argument in wanted_set]
    if set(wanted_list) == previous:
        return current

    if backend == "limine":
        original = _read_exact(host, LIMINE_CONFIG)
        updated = _LIMINE_BLOCK.sub("", original).rstrip("\n") + "\n"
        if wanted_list:
            updated = (
                updated.rstrip("\n")
                + f'\n\n{LIMINE_BEGIN}\nKERNEL_CMDLINE[default]+=" {" ".join(wanted_list)}"\n{LIMINE_END}\n'
            )
        try:
            host.write(LIMINE_CONFIG, updated)
            host.run("limine-mkinitcpio")
        except Exception:
            host.write(LIMINE_CONFIG, original)
            raise
    elif backend == "grub":
        before = _read_exact(host, GRUB_DROPIN) if host.path(GRUB_DROPIN).exists() else None
        try:
            if wanted_list:
                host.managed(
                    GRUB_DROPIN,
                    f'GRUB_CMDLINE_LINUX_DEFAULT="${{GRUB_CMDLINE_LINUX_DEFAULT}} {" ".join(wanted_list)}"\n',
                )
            else:
                host.remove_managed(GRUB_DROPIN)
            _regenerate_grub(host)
        except Exception:
            if before is not None:
                host.write(GRUB_DROPIN, before)
            elif host.path(GRUB_DROPIN).exists():
                host.path(GRUB_DROPIN).unlink()
            raise
    else:
        added = [argument for argument in wanted_list if argument not in previous]
        removed = [argument for argument in ARGUMENTS if argument in previous and argument not in wanted_set]
        if added:
            host.run("grubby", "--update-kernel=ALL", f"--args={' '.join(added)}")
        if removed:
            host.run("grubby", "--update-kernel=ALL", f"--remove-args={' '.join(removed)}")

    host.save(_STATE_KEY, {
        "backend": backend,
        "arguments": wanted_list,
        "removed": sorted(previous - set(wanted_list)),
        "boot_id": host.read(BOOT_ID),
    })
    return status(host)
