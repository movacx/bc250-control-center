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
  ``/etc/default/grub.d`` when this ``grub-mkconfig`` reads it, otherwise a
  marked block in ``/etc/default/grub`` (see below).
* grubby (Fedora, Nobara): ``grubby --update-kernel=ALL`` with only the
  arguments this module added, so arguments the owner set are left alone.

An argument already present that this module did not add is reported as
managed elsewhere and never touched. Everything applies at the next boot.

SteamOS (beta) takes the GPU memory limit, ``mitigations=off`` and ``nosmt``, the way
keyboardspecialist/bc250-steamos (public domain) sets the first: the same
drop-in in ``/etc/default/grub.d``, ``grub-mkconfig`` into a new file beside
``/efi/EFI/steamos/grub.cfg`` that replaces it only once every kernel entry
carries the argument, and the drop-in named in ``/etc/atomic-update.conf.d``
so an update keeps it. ``/etc/default/grub`` itself belongs to the image and is
never edited. The CU unlock stays off SteamOS.

Besides those fixed switches the same block carries one argument with a value,
``ttm.pages_limit=<pages>`` (the GPU memory limit, see system_setup_ttm.py).
It is set and removed on its own, never as part of the switches above, and a
value somebody else put on the command line is reported, never replaced.

Whether ``grub-mkconfig`` reads ``/etc/default/grub.d`` depends on the GRUB
build, not on the distribution: Debian and Ubuntu have always patched it in,
upstream GRUB gained it in its newest releases (Arch ships that today), and
older upstream builds (Manjaro or CachyOS on an older GRUB, for example) read
``/etc/default/grub`` only. The script itself is inspected; where it does not
read the directory, the options go in a marked block at the end of
``/etc/default/grub`` instead, taken out again byte for byte.
"""
from __future__ import annotations

import os
import re

from system_setup_common import Host, SetupError

CU_UNLOCK = "amdgpu.bc250_cc_write_mode=3"
#: The module parameter exists only on a kernel that carries the BC-250 patch;
#: on any other kernel the argument would be ignored and never take effect.
CU_UNLOCK_PARAMETER = "/sys/module/amdgpu/parameters/bc250_cc_write_mode"
CU_UNLOCK_PREFIX = "amdgpu.bc250_cc_write_mode="
ARGUMENTS = ("mitigations=off", "nosmt", CU_UNLOCK)
#: What SteamOS's boot menu takes among the switches.
STEAMOS_ARGUMENTS = ("mitigations=off", "nosmt")
#: Arguments that carry a value, and the only values each may have.
VALUE_ARGUMENTS = {"ttm.pages_limit": re.compile(r"[1-9][0-9]{0,9}")}
CMDLINE = "/proc/cmdline"
SMT_CONTROL = "/sys/devices/system/cpu/smt/control"
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
#: The marked block, with the single line break that separates it from what
#: came before. Taking it out removes exactly what putting it in added, so a
#: file that ended in a newline (or in several) comes back byte for byte.
_LIMINE_BLOCK = re.compile(
    rf"(?:^|\n){re.escape(LIMINE_BEGIN)}\n[^\n]*\n{re.escape(LIMINE_END)}\n"
)
#: The same marked block, at the end of /etc/default/grub.
_GRUB_BLOCK = _LIMINE_BLOCK
_STATE_KEY = "kernel-options"
STEAMOS_GRUB_OUTPUT = "/efi/EFI/steamos/grub.cfg"
STEAMOS_GRUB_STAGED = "/efi/EFI/steamos/.bc250-grub.cfg.new"
STEAMOS_KEEP = "/etc/atomic-update.conf.d/bc250-control-center-boot.conf"


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
    if host.steamos():
        # Only a GRUB that reads the drop-in directory: SteamOS's own
        # /etc/default/grub belongs to the image and is never edited.
        if host.command("grub-mkconfig") and grub_reads_dropins(host):
            return "steamos-grub"
        return "unsupported"
    if host.immutable_image():
        # Bazzite keeps its own reviewed card.
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
    elif backend == "steamos-grub":
        # What the next boot reads; the drop-in when the EFI partition is not
        # readable from here (the unprivileged inventory).
        text = host.read(STEAMOS_GRUB_OUTPUT) or (
            host.read(GRUB_CONFIG) + "\n" + host.read(GRUB_DROPIN)
        )
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


def _stale(host: Host, backend: str, saved: dict, configured_tokens: set[str] | None = None) -> set[str]:
    """Managed tokens the boot configuration does not actually carry.

    Only for the file-based loaders, whose files can be read back: a drop-in
    that an earlier release put where this GRUB never reads it, or a block the
    owner deleted by hand, would otherwise count as set and never be redone.
    """
    if backend not in ("limine", "grub", "steamos-grub"):
        return set()
    managed = set(_managed_tokens(saved.get("arguments"), _values(saved)))
    if not managed:
        return set()
    if configured_tokens is None:
        configured_tokens = _configured_tokens(host, backend)
    return managed - configured_tokens


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
    # SMT switched off while the system runs (bc250-steamos' cpu-smt, or by
    # hand) is not on the command line, but it is just as active: it counts
    # as somebody else's setting, never as "Enabled".
    if host.read(SMT_CONTROL).strip() in {"off", "forceoff"}:
        active.add("nosmt")
    configured_tokens = _configured_tokens(host, backend)
    configured = {argument for argument in ARGUMENTS if argument in configured_tokens}
    stale = _stale(host, backend, saved, configured_tokens)
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
            "configured": (argument in managed and argument not in stale)
            or (argument in configured and not mine),
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
            "configured": None if mine_token in stale else configured_value,
            # What this boot started with.
            "active": _value_of(command_line, name),
            "external": bool(foreign_configured or foreign_active),
            "external_value": _value_of(foreign_configured, name) or _value_of(foreign_active, name),
        }
    mode = host.read(CU_UNLOCK_PARAMETER).strip()
    return {
        "backend": backend,
        "available": backend != "unsupported" and host.bc250(),
        # The switches this host's boot loader takes; SteamOS not the CU unlock.
        "allowed": list(STEAMOS_ARGUMENTS if backend == "steamos-grub" else ARGUMENTS),
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
    return f"\n{LIMINE_BEGIN}\n{line}\n{LIMINE_END}\n" if tokens else ""


def _with_block(text: str, pattern, tokens: list[str], line: str) -> str:
    """``text`` without any managed block, plus a fresh one when ``tokens`` is set.

    A file that does not end in a newline gets one first (a block cannot start
    mid-line); nothing else about the file is touched.
    """
    base = pattern.sub("", text)
    if not tokens:
        return base
    if base and not base.endswith("\n"):
        base += "\n"
    return base + _block(tokens, line)


def _write(host: Host, backend: str, tokens: list[str], previous: list[str]) -> None:
    """Put exactly ``tokens`` in the managed place, or put everything back."""
    if backend == "limine":
        original = _read_exact(host, LIMINE_CONFIG)
        updated = _with_block(
            original, _LIMINE_BLOCK, tokens, f'KERNEL_CMDLINE[default]+=" {" ".join(tokens)}"'
        )
        try:
            if updated != original:
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
        use_dropin = grub_reads_dropins(host)
        main_after = _with_block(
            main_before, _GRUB_BLOCK, [] if use_dropin else tokens, line
        )
        try:
            if tokens and use_dropin:
                host.managed(GRUB_DROPIN, line + "\n")
            else:
                host.remove_managed(GRUB_DROPIN)
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
    elif backend == "steamos-grub":
        _write_steamos_grub(host, tokens, previous)
    else:
        added = [token for token in tokens if token not in previous]
        removed = [token for token in previous if token not in tokens]
        # Remove first: grubby matches an argument by name, so adding the new
        # value of ttm.pages_limit and then removing the old one could take the
        # new one out again.
        if removed:
            host.run("grubby", "--update-kernel=ALL", f"--remove-args={' '.join(removed)}")
        if added:
            host.run("grubby", "--update-kernel=ALL", f"--args={' '.join(added)}")


def _kernel_entries(menu: str) -> list[list[str]]:
    """The words of every kernel line of a generated GRUB menu.

    SteamOS does not write ``linux /vmlinuz...`` itself: its entries call a
    helper, ``steamenv_boot linux /vmlinuz... <arguments>`` (the same lines
    keyboardspecialist/bc250-steamos validates).
    """
    entries = []
    for line in menu.splitlines():
        words = line.split()
        if words and (words[0].startswith("linux")
                      or (words[0] == "steamenv_boot" and len(words) > 1 and words[1].startswith("linux"))):
            entries.append(words)
    return entries


def _write_steamos_grub(host: Host, tokens: list[str], previous: list[str]) -> None:
    """The drop-in, then a regenerated menu that replaces SteamOS's only when right."""
    output = host.path(STEAMOS_GRUB_OUTPUT)
    staged = host.path(STEAMOS_GRUB_STAGED)
    if output.is_symlink() or not output.is_file():
        raise SetupError(f"SteamOS's boot menu ({STEAMOS_GRUB_OUTPUT}) was not found")
    if staged.is_symlink():
        raise SetupError(f"Refusing symbolic link: {STEAMOS_GRUB_STAGED}")
    line = f'GRUB_CMDLINE_LINUX_DEFAULT="${{GRUB_CMDLINE_LINUX_DEFAULT}} {" ".join(tokens)}"'
    dropin_before = _read_exact(host, GRUB_DROPIN) if host.path(GRUB_DROPIN).exists() else None
    keep_before = _read_exact(host, STEAMOS_KEEP) if host.path(STEAMOS_KEEP).exists() else None
    gone = [token for token in previous if token not in tokens]
    try:
        if tokens:
            host.managed(GRUB_DROPIN, line + "\n")
            host.managed(STEAMOS_KEEP, GRUB_DROPIN + "\n")
        else:
            host.remove_managed(GRUB_DROPIN)
        staged.unlink(missing_ok=True)
        host.run("grub-mkconfig", "-o", STEAMOS_GRUB_STAGED)
        try:
            generated = staged.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise SetupError("grub-mkconfig wrote no readable boot menu") from error
        entries = _kernel_entries(generated)
        if not entries:
            raise SetupError("grub-mkconfig produced no kernel entries; the boot menu was left as it was")
        for words in entries:
            # A valued argument at most once: with two, the kernel would take
            # whichever comes last.
            repeated = any(sum(word.startswith(name + "=") for word in words) > 1
                           for name in VALUE_ARGUMENTS)
            if (repeated or any(token not in words for token in tokens)
                    or any(token in words for token in gone)):
                raise SetupError(
                    "SteamOS's grub-mkconfig did not carry the change into every kernel entry; "
                    "the boot menu was left as it was"
                )
        os.replace(staged, output)
        if not tokens:
            host.remove_managed(STEAMOS_KEEP)
    except Exception:
        staged.unlink(missing_ok=True)
        if dropin_before is not None:
            host.write(GRUB_DROPIN, dropin_before)
        elif host.path(GRUB_DROPIN).exists():
            host.path(GRUB_DROPIN).unlink()
        if keep_before is not None:
            host.write(STEAMOS_KEEP, keep_before)
        elif host.path(STEAMOS_KEEP).exists():
            host.path(STEAMOS_KEEP).unlink()
        raise


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
    if tokens == previous and not _stale(host, backend, saved):
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
    if backend == "steamos-grub" and wanted_set - set(STEAMOS_ARGUMENTS):
        raise SetupError("On SteamOS only mitigations=off, nosmt and the GPU memory limit are set here")
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
