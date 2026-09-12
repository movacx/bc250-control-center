"""Persistent repair for the BC-250 eight-core AMDGPU metrics layout."""
from __future__ import annotations

import re

from system_setup_common import STATE, Host, SetupError

ARGUMENT = "amdgpu.cs_legacy_8core_metrics=1"
PARAMETER = "/sys/module/amdgpu/parameters/cs_legacy_8core_metrics"
CMDLINE = "/proc/cmdline"
LIMINE_CONFIG = "/etc/default/limine"
GRUB_CONFIG = "/etc/default/grub"
GRUB_DROPIN = "/etc/default/grub.d/90-bc250-telemetry.cfg"
GRUB_OUTPUTS = ("/boot/grub/grub.cfg", "/boot/grub2/grub.cfg")
LIMINE_BEGIN = "# BEGIN BC250 8-CORE TELEMETRY"
LIMINE_END = "# END BC250 8-CORE TELEMETRY"
_LIMINE_MANAGED_BLOCK = re.compile(
    rf"\n\n{re.escape(LIMINE_BEGIN)}\nKERNEL_CMDLINE\[default\]\+=\"{re.escape(ARGUMENT)}\"\n{re.escape(LIMINE_END)}\n?"
)
_ARGUMENT_RE = re.compile(r"(?:^|\s)amdgpu\.cs_legacy_8core_metrics=([^\s\"']+)")


def _enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "y", "yes", "true"}


def _physical_cores(host: Host) -> int:
    cores = set()
    for cpu in host.path("/sys/devices/system/cpu").glob("cpu[0-9]*"):
        core = host.read("/" + str((cpu / "topology/core_id").relative_to(host.root)))
        package = host.read("/" + str((cpu / "topology/physical_package_id").relative_to(host.root))) or "0"
        if core.isdigit() and package.lstrip("-").isdigit():
            cores.add((package, core))
    return len(cores)


def _configured_value(text: str) -> str:
    matches = _ARGUMENT_RE.findall(str(text or ""))
    return matches[-1] if matches else ""


def _read_exact(host: Host, name: str) -> str:
    try:
        return host.path(name).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _backend(host: Host) -> str:
    if host.path(LIMINE_CONFIG).is_file() and host.command("limine-mkinitcpio"):
        return "limine"
    if host.immutable_image() and host.command("rpm-ostree"):
        return "rpm-ostree"
    if host.path(GRUB_CONFIG).is_file() and (
        host.command("update-grub") or host.command("grub-mkconfig") or host.command("grub2-mkconfig")
    ):
        return "grub"
    return "unsupported"


def status(host: Host) -> dict:
    cores = _physical_cores(host)
    active = _enabled(host.read(PARAMETER))
    backend = _backend(host)
    configured = False
    if backend == "limine":
        configured = _enabled(_configured_value(host.read(LIMINE_CONFIG)))
    elif backend == "grub":
        configured = _enabled(_configured_value(host.read(GRUB_DROPIN)))
    elif backend == "rpm-ostree":
        configured = _enabled(_configured_value(host.run("rpm-ostree", "kargs", check=False)))
    required = bool(host.bc250() and cores == 8 and not active)
    return {
        "hardware": host.bc250(),
        "physical_cores": cores,
        "kernel_parameter": host.read(PARAMETER) or "unavailable",
        "active": active,
        "configured": configured,
        "backend": backend,
        "required": required,
        "available": required and backend != "unsupported",
        "reboot_required": configured and not active,
        "status": "active" if active else "pending-reboot" if configured else "repair-required" if required else "not-required",
    }


def _reject_conflict(text: str) -> None:
    value = _configured_value(text)
    if value and not _enabled(value):
        raise SetupError("A conflicting amdgpu.cs_legacy_8core_metrics kernel argument already exists")


def _regenerate_grub(host: Host) -> None:
    if host.command("update-grub"):
        host.run("update-grub")
        return
    output = next((path for path in GRUB_OUTPUTS if host.path(path).exists()), "")
    if not output:
        raise SetupError("The active GRUB output file could not be identified")
    command = "grub2-mkconfig" if host.command("grub2-mkconfig") else "grub-mkconfig"
    host.run(command, "-o", output)


def _clear_state(host: Host) -> None:
    path = host.path(f"{STATE}/telemetry.json")
    if path.exists():
        path.unlink()


def apply(host: Host) -> dict:
    current = status(host)
    if not current["hardware"]:
        raise SetupError("AMD BC-250 PCI device 1002:13fe was not found")
    if current["physical_cores"] != 8:
        raise SetupError("Eight physical BC-250 CPU cores must be active before enabling this metrics layout")
    if current["active"]:
        return current
    if current["configured"]:
        return current
    backend = current["backend"]
    if backend == "unsupported":
        raise SetupError("No supported Limine, GRUB or rpm-ostree boot configuration was detected")

    state_path = host.path(f"{STATE}/telemetry.json")
    if state_path.exists() and host.state("telemetry"):
        raise SetupError("An existing telemetry repair transaction must be restored or rebooted first")

    if backend == "limine":
        original = _read_exact(host, LIMINE_CONFIG)
        _reject_conflict(original)
        host.save("telemetry", {"backend": backend, "original": original})
        updated = (
            original.rstrip()
            + f'\n\n{LIMINE_BEGIN}\nKERNEL_CMDLINE[default]+="{ARGUMENT}"\n{LIMINE_END}\n'
        )
        try:
            host.write(LIMINE_CONFIG, updated)
            host.run("limine-mkinitcpio")
        except Exception:
            host.write(LIMINE_CONFIG, original)
            _clear_state(host)
            raise
    elif backend == "grub":
        existing = host.read(GRUB_DROPIN)
        _reject_conflict(existing)
        host.save("telemetry", {"backend": backend})
        host.managed(
            GRUB_DROPIN,
            f'GRUB_CMDLINE_LINUX_DEFAULT="${{GRUB_CMDLINE_LINUX_DEFAULT}} {ARGUMENT}"\n',
        )
        try:
            _regenerate_grub(host)
        except Exception:
            host.remove_managed(GRUB_DROPIN)
            _clear_state(host)
            raise
    else:
        before = host.run("rpm-ostree", "kargs", check=False)
        _reject_conflict(before)
        host.save("telemetry", {"backend": backend, "argument_preexisting": False})
        try:
            host.run("rpm-ostree", "kargs", f"--append-if-missing={ARGUMENT}")
        except Exception:
            _clear_state(host)
            raise

    result = status(host)
    result["configured"] = True
    result["reboot_required"] = True
    result["status"] = "pending-reboot"
    return result


def restore(host: Host) -> dict:
    saved = host.state("telemetry")
    if not saved:
        raise SetupError("No BC250 eight-core telemetry repair is recorded")
    backend = saved.get("backend")
    if backend == "limine":
        current = _read_exact(host, LIMINE_CONFIG)
        host.write(LIMINE_CONFIG, _LIMINE_MANAGED_BLOCK.sub("\n", current))
        host.run("limine-mkinitcpio")
    elif backend == "grub":
        host.remove_managed(GRUB_DROPIN)
        _regenerate_grub(host)
    elif backend == "rpm-ostree":
        host.run("rpm-ostree", "kargs", f"--delete-if-present={ARGUMENT}")
    else:
        raise SetupError("Invalid telemetry repair journal")
    _clear_state(host)
    result = status(host)
    result["reboot_required"] = True
    result["status"] = "removed-pending-reboot"
    return result
