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

Besides those fixed switches the same block carries one argument with a value,
``ttm.pages_limit=<pages>`` (the GPU memory limit, see system_setup_ttm.py).
It is set and removed on its own, never as part of the switches above, and a
value somebody else put on the command line is reported, never replaced.

Upstream GRUB only reads ``/etc/default/grub``; the ``/etc/default/grub.d``
directory is a Debian/Ubuntu addition. Where ``grub-mkconfig`` does not read
it, the options go in a marked block at the end of ``/etc/default/grub``
instead, removed again without touching anything else in the file.
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
#: Arguments that carry a value, and the only values each may have.
VALUE_ARGUMENTS = {"ttm.pages_limit": re.compile(r"[1-9][0-9]{0,9}")}
CMDLINE = "/proc/cmdline"
BOOT_ID = "/proc/sys/kernel/random/boot_id"
LIMINE_CONFIG = "/etc/default/limine"
GRUB_CONFIG = "/etc/default/grub"
GRUB_DROPIN = "/etc/default/grub.d/91-bc250-kernel-options.cfg"
GRUB_OUTPUTS = ("/boot/grub/grub.cfg", "/boot/grub2/grub.cfg")
GRUB_MKCONFIG = (
    "/usr/sbin/grub-mkconfig", "/usr/bin/grub-mkconfig", "/sbin/grub-mkconfig",
    "/usr/sbin/grub2-mkconfig", "/usr/bin/grub2-mkconfig", "/sbin/grub2-mkconfig",
)
LIMINE_BEGIN = "# BEGIN BC250 KERNEL OPTIONS"
LIMINE_END = "# END BC250 KERNEL OPTIONS"
_LIMINE_BLOCK = re.compile(
    rf"\n\n{re.escape(LIMINE_BEGIN)}\n[^\n]*\n{re.escape(LIMINE_END)}\n"
)
#: The same marked block, at the end of /etc/default/grub.
_GRUB_BLOCK = _LIMINE_BLOCK
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


#: Which boot loader this host's options would go through, for other modules.
backend = _backend


def grub_reads_dropins(host: Host) -> bool:
    """Whether this GRUB's ``grub-mkconfig`` sources ``/etc/default/grub.d``.

    Debian and Ubuntu patch it in; upstream GRUB, which Arch and its
    derivatives ship, reads ``/etc/default/grub`` only. When no script can be
    found the drop-in is assumed, which is what every earlier release did.
    """
    for name in GRUB_MKCONFIG:
        path = host.path(name)
        if path.is_file():
            return "default/grub.d" in _read_exact(host, name)
    return True


def _configured_tokens(host: Host, backend: str) -> set[str]:
    """Every word the boot configuration puts on the command line."""
    if backend == "limine":
        text = host.read(LIMINE_CONFIG)
    elif backend == "grub":
        text = host.read(GRUB_CONFIG)
        if grub_reads_dropins(host):
            text += "\n" + host.read(GRUB_DROPIN)
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


def _values(saved: dict) -> dict[str, str]:
    """The valued arguments this module manages, only in their allowed form."""
    values = saved.get("values") or {}
    if not isinstance(values, dict):
        return {}
    return {
        name: str(value) for name, value in values.items()
        if name in VALUE_ARGUMENTS and VALUE_ARGUMENTS[name].fullmatch(str(value))
    }


def _managed_tokens(arguments, values: dict[str, str]) -> list[str]:
    """What the managed block holds, in a stable order."""
    fixed = [argument for argument in ARGUMENTS if argument in set(arguments or ())]
    return fixed + [f"{name}={values[name]}" for name in VALUE_ARGUMENTS if name in values]


def _value_of(tokens, name: str) -> str | None:
    """The value the kernel would use: the last occurrence wins."""
    found = None
    for token in tokens:
        if token.startswith(name + "="):
            found = token.split("=", 1)[1]
    return found


def status(host: Host) -> dict:
    backend = _backend(host)
    saved = host.state(_STATE_KEY)
    managed = set(saved.get("arguments") or ())
    values = _values(saved)
    # Removed by this module on this boot: still active until the reboot, but
    # not somebody else's setting.
    removing = set(saved.get("removed") or ()) if saved.get("boot_id") == host.read(BOOT_ID) else set()
    command_line = host.read(CMDLINE).split()
    active = set(command_line)
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
    value_items = {}
    for name in VALUE_ARGUMENTS:
        mine_token = f"{name}={values[name]}" if name in values else ""
        ours = {mine_token, *removing} - {""}
        foreign_configured = [t for t in configured_tokens if t.startswith(name + "=") and t not in ours]
        foreign_active = [t for t in command_line if t.startswith(name + "=") and t not in ours]
        configured_value = values.get(name) or _value_of(foreign_configured, name)
        value_items[name] = {
            "managed": values.get(name),
            # What the next boot asks for, whoever set it.
            "configured": configured_value,
            # What this boot started with.
            "active": _value_of(command_line, name),
            "external": bool(foreign_configured or foreign_active),
            "external_value": _value_of(foreign_configured, name) or _value_of(foreign_active, name),
        }
    mode = host.read(CU_UNLOCK_PARAMETER).strip()
    return {
        "backend": backend,
        "available": backend != "unsupported" and host.bc250(),
        "arguments": arguments,
        "values": value_items,
        # Whether this kernel has the parameter at all, and what it is set to now.
        "cu_unlock": {
            "supported": host.path(CU_UNLOCK_PARAMETER).exists(),
            "mode": mode,
        },
        "reboot_required": any(
            item["configured"] != item["active"] for item in arguments.values()
        ) or any(
            item["configured"] != item["active"] for item in value_items.values()
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


def _block(tokens: list[str], line: str) -> str:
    return f"\n\n{LIMINE_BEGIN}\n{line}\n{LIMINE_END}\n" if tokens else ""


def _write(host: Host, backend: str, tokens: list[str], previous: list[str]) -> None:
    """Put exactly ``tokens`` in the managed place, or put everything back."""
    if backend == "limine":
        original = _read_exact(host, LIMINE_CONFIG)
        updated = _LIMINE_BLOCK.sub("", original).rstrip("\n") + "\n"
        if tokens:
            updated = updated.rstrip("\n") + _block(
                tokens, f'KERNEL_CMDLINE[default]+=" {" ".join(tokens)}"'
            )
        try:
            host.write(LIMINE_CONFIG, updated)
            host.run("limine-mkinitcpio")
        except Exception:
            host.write(LIMINE_CONFIG, original)
            raise
    elif backend == "grub":
        line = f'GRUB_CMDLINE_LINUX_DEFAULT="${{GRUB_CMDLINE_LINUX_DEFAULT}} {" ".join(tokens)}"'
        dropin_before = _read_exact(host, GRUB_DROPIN) if host.path(GRUB_DROPIN).exists() else None
        main_before = _read_exact(host, GRUB_CONFIG)
        # Whichever place this GRUB does not read is emptied, so a block left
        # by an earlier release in the other place cannot linger.
        main_after = _GRUB_BLOCK.sub("", main_before)
        use_dropin = grub_reads_dropins(host)
        try:
            if tokens and use_dropin:
                host.managed(GRUB_DROPIN, line + "\n")
            else:
                host.remove_managed(GRUB_DROPIN)
            if tokens and not use_dropin:
                main_after = main_after.rstrip("\n") + _block(tokens, line)
            if main_after != main_before:
                host.write(GRUB_CONFIG, main_after)
            _regenerate_grub(host)
        except Exception:
            if dropin_before is not None:
                host.write(GRUB_DROPIN, dropin_before)
            elif host.path(GRUB_DROPIN).exists():
                host.path(GRUB_DROPIN).unlink()
            if _read_exact(host, GRUB_CONFIG) != main_before:
                host.write(GRUB_CONFIG, main_before)
            raise
    else:
        added = [token for token in tokens if token not in previous]
        removed = [token for token in previous if token not in tokens]
        if added:
            host.run("grubby", "--update-kernel=ALL", f"--args={' '.join(added)}")
        if removed:
            host.run("grubby", "--update-kernel=ALL", f"--remove-args={' '.join(removed)}")


def _prepare(host: Host) -> tuple[dict, str, dict]:
    if not host.bc250():
        raise SetupError("AMD BC-250 PCI device 1002:13fe was not found")
    current = status(host)
    backend = current["backend"]
    if backend == "unsupported":
        raise SetupError("No supported Limine, GRUB or grubby boot configuration was detected")
    saved = host.state(_STATE_KEY)
    if (saved.get("arguments") or _values(saved)) and saved.get("backend") != backend:
        raise SetupError("The boot loader changed since these options were set; restore them first")
    return current, backend, saved


def _commit(host: Host, backend: str, saved: dict, arguments: list[str], values: dict[str, str]) -> dict:
    previous = _managed_tokens(saved.get("arguments"), _values(saved))
    tokens = _managed_tokens(arguments, values)
    if tokens == previous:
        return status(host)
    _write(host, backend, tokens, previous)
    boot_id = host.read(BOOT_ID)
    # Removals add up within one boot: taking a second option off must not
    # make the first one, still on this boot's command line, look foreign.
    removed = set(previous) - set(tokens)
    if saved.get("boot_id") == boot_id:
        removed |= set(saved.get("removed") or ())
    removed -= set(tokens)
    host.save(_STATE_KEY, {
        "backend": backend,
        "arguments": [argument for argument in ARGUMENTS if argument in set(arguments)],
        "values": {name: values[name] for name in VALUE_ARGUMENTS if name in values},
        "removed": sorted(removed),
        "boot_id": boot_id,
    })
    return status(host)


def apply(host: Host, wanted: list[str] | tuple[str, ...]) -> dict:
    """Make exactly ``wanted`` the set of switches this module manages."""
    wanted_set = set(wanted)
    if wanted_set - set(ARGUMENTS):
        raise SetupError("Only mitigations=off, nosmt and amdgpu.bc250_cc_write_mode=3 can be managed here")
    current, backend, saved = _prepare(host)
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
    wanted_list = [argument for argument in ARGUMENTS if argument in wanted_set]
    return _commit(host, backend, saved, wanted_list, _values(saved))


def set_value(host: Host, name: str, value: str | None) -> dict:
    """Manage ``name=value`` in the same block, or take it out with ``None``.

    The switches above are left exactly as they are.
    """
    if name not in VALUE_ARGUMENTS:
        raise SetupError("Only ttm.pages_limit can be given a value here")
    if value is not None and not VALUE_ARGUMENTS[name].fullmatch(str(value)):
        raise SetupError(f"Invalid value for {name}")
    current, backend, saved = _prepare(host)
    if value is not None and current["values"][name]["external"]:
        raise SetupError(
            f"{name}={current['values'][name]['external_value']} is already set outside "
            "Control Center and is left as it is"
        )
    values = _values(saved)
    if value is None:
        values.pop(name, None)
    else:
        values[name] = str(value)
    return _commit(host, backend, saved, list(saved.get("arguments") or ()), values)
