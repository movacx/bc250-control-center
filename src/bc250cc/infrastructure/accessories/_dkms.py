"""Hexxeh's BC-250 kernel drivers, built with DKMS on Arch-based systems.

bc250-vrm (power delivery) and bc250-memory (VRAM temperature) ship the same
way: a few C files, a dkms.conf and a Makefile that always builds with clang.
This builds either one from a pinned, checksummed revision, with a Makefile
that uses the compiler each kernel was built with, so Arch's and Manjaro's
GCC kernels work as well as CachyOS's clang ones. MastaG's BC-250 kernels
already carry both drivers; the installer then builds nothing.
"""

from __future__ import annotations

import hashlib
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ._shared import command_output, shell_header

#: Distribution families that build them: Arch and what is built on it.
FAMILIES = frozenset({"arch", "cachyos", "manjaro", "endeavouros", "garuda"})
BOARD_NAME = "AMD BC-250"

#: Left in the installed source: which Control Center build it is. A copy
#: without it, or with another, was built by an older version and is offered
#: as an update, so a fix in the installer reaches the boards that already
#: have the driver.
BUILD_MARKER = "bc250-control-center.build"

#: Picks the compiler the kernel was built with, for whichever kernel DKMS
#: hands it, instead of upstream's fixed LLVM=1.
MAKEFILE = """\
# Written by BC250 Control Center: build with the compiler this kernel used.
KDIR ?= /lib/modules/$(shell uname -r)/build
LLVM_FLAG := $(if $(shell grep -s '^CONFIG_CC_IS_CLANG=y' $(KDIR)/.config),LLVM=1)

all:
\t$(MAKE) -C $(KDIR) M=$(CURDIR) $(LLVM_FLAG) modules

clean:
\t$(MAKE) -C $(KDIR) M=$(CURDIR) $(LLVM_FLAG) clean
"""


@dataclass(frozen=True)
class Driver:
    """One of Hexxeh's drivers, pinned to the revision Control Center reviewed."""

    title: str
    package: str
    version: str
    module: str
    hwmon: str
    repository: str
    revision: str
    #: Upstream file -> reviewed SHA-256, everything that goes into the build.
    sources: Mapping[str, str]
    kbuild: str
    #: The hwmon attribute and divisor shown once it reads, and its unit.
    reading: tuple[str, int, str] = ("temp1_input", 1000, "°C")
    #: Lower-case BIOS versions it may be installed on; empty means any.
    bios: frozenset[str] = frozenset()
    #: Extra checks, in bash, run before anything is installed.
    preflight: tuple[str, ...] = field(default=())
    #: What the owner reads when it is installed but gives no reading.
    silent_hint: str = ""
    #: Changes made to the verified source before it is built: (file, sed
    #: expression, text that must be there afterwards[, bash condition]). The
    #: check after each one stops the install if the line it expects is not
    #: where it was; a condition limits it to the machines that need it.
    patches: tuple[tuple[str, ...], ...] = field(default=())

    @property
    def build_id(self) -> str:
        """Changes whenever what this installer builds changes."""
        recipe = "\0".join((self.revision, self.kbuild, MAKEFILE, self.dkms_conf(), repr(self.patches)))
        return hashlib.sha256(recipe.encode()).hexdigest()[:16]

    def installed_build(self) -> str:
        return read(self.source_directory / BUILD_MARKER).split(" ")[0] if self.source_directory.is_dir() else ""

    @property
    def source_directory(self) -> Path:
        return Path(f"/usr/src/{self.package}-{self.version}")

    def dkms_conf(self) -> str:
        return (
            f'PACKAGE_NAME="{self.package}"\n'
            f'PACKAGE_VERSION="{self.version}"\n'
            f'BUILT_MODULE_NAME[0]="{self.module}"\n'
            'DEST_MODULE_LOCATION[0]="/kernel/drivers/hwmon"\n'
            'AUTOINSTALL="yes"\n'
            'MAKE[0]="make KDIR=${kernel_source_dir}"\n'
            'CLEAN="make KDIR=${kernel_source_dir} clean"\n'
        )


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def hwmon_reading(root: Path, name: str, attribute: str, divisor: int) -> float | None:
    """The driver's first reading, or None when no device of that name reads."""
    try:
        entries = sorted(root.glob("hwmon*"))
    except OSError:
        return None
    for entry in entries:
        if read(entry / "name") != name:
            continue
        try:
            return int(read(entry / attribute)) / divisor
        except ValueError:
            return None
    return None


def module_file(module: str) -> str:
    """Where the kernel would load the driver from, or ``""`` when it has none."""
    return command_output(["modinfo", "-F", "filename", module])


def built_into_kernel(filename: str) -> bool:
    """The running kernel ships the driver itself (MastaG's kernels do)."""
    return bool(filename) and "/updates/" not in filename and "/extra/" not in filename


def is_current(driver: Driver, installed_build: str, reading: float | None) -> bool:
    """Whether the installed copy is what this installer builds today.

    A copy from before the build mark existed counts as current while it
    reads: it works, and rebuilding it would change nothing the owner sees.
    One that does not read, or carries another mark, is offered as an update.
    """
    if installed_build:
        return installed_build == driver.build_id
    return reading is not None


def state(*, family: str, board: bool, bios_ok: bool, built_in: bool, installed: bool,
          reading: float | None, current: bool = True) -> str:
    """The accessory state the cards and the power readings window show."""
    if built_in:
        return "managed-elsewhere"
    if installed and not current:
        return "update-available"
    if installed:
        return "active" if reading is not None else "installed"
    if family not in FAMILIES or not board or not bios_ok:
        return "unsupported"
    return "not-installed"


def _patch_line(name: str, expression: str, expected: str, condition: str = "") -> str:
    line = (
        f"sed -i {shlex.quote(expression)} \"$bc250_src/{name}\" && grep -qF {shlex.quote(expected)} "
        f"\"$bc250_src/{name}\" || {{ echo 'ERROR: {name} changed upstream; Control Center did not patch it. "
        "Nothing was installed.'; exit 29; }"
    )
    return f"if {condition}; then {line}; fi" if condition else line


def _write(path: str, content: str) -> str:
    return f"printf '%s' {shlex.quote(content)} > {path}"


def install_command(driver: Driver, family: str, *, board_name_path: Path, bios_version_path: Path,
                    hwmon_root: Path) -> str:
    family = str(family or "").strip().lower()
    if family not in FAMILIES:
        raise RuntimeError(
            f"{driver.title} is built with DKMS on Arch, CachyOS, Manjaro and other Arch-based systems only."
        )
    directory = driver.source_directory
    attribute, divisor, unit = driver.reading
    checks = "\n".join(
        f"printf '%s  %s\\n' {digest} \"$bc250_src/{name}\" | sha256sum --check --status "
        f"|| {{ echo 'ERROR: {name} is not the file Control Center reviewed. Nothing was installed.'; exit 29; }}"
        for name, digest in driver.sources.items()
    )
    files = " ".join(f'"$bc250_src/{name}"' for name in ("Kbuild", "Makefile", "dkms.conf", *driver.sources))
    commands = shell_header(f"{driver.title} · {driver.package} {driver.version} by Liam McLoughlin (Hexxeh)")
    commands.append(
        f"[ \"$(cat {board_name_path} 2>/dev/null)\" = {shlex.quote(BOARD_NAME)} ] "
        "|| { echo 'ERROR: this is not an AMD BC-250 board; the driver only works there.'; exit 64; }"
    )
    if driver.bios:
        allowed = "|".join(sorted(driver.bios))
        commands += [
            f"bc250_bios=\"$(cat {bios_version_path} 2>/dev/null)\"",
            f"case \"${{bc250_bios,,}}\" in {allowed}) ;; *) "
            "echo \"ERROR: BIOS ${bc250_bios:-unknown} is not supported. The driver patches the SMU firmware at "
            "fixed addresses that were reviewed for BIOS P3.00 only; on another BIOS it could hang the board.\"; "
            "exit 65 ;; esac",
        ]
    commands += list(driver.preflight)
    commands += [
        'bc250_kernel="$(uname -r)"',
        # MastaG's kernels carry the driver already: building a second copy
        # would only shadow it.
        f"bc250_current=\"$(modinfo -F filename {driver.module} 2>/dev/null || true)\"",
        'if [ -n "$bc250_current" ] && [[ "$bc250_current" != */updates/* && "$bc250_current" != */extra/* ]]; then',
        f"  echo 'OK: this kernel already includes {driver.module}. Nothing to build; loading it.'",
        f"  sudo modprobe {driver.module} || true",
        "  exit 0",
        "fi",
        # The headers package is the running kernel's own, whatever its name
        # (linux, linux-cachyos, linux612...).
        'bc250_owner="$(pacman -Qqo "/usr/lib/modules/$bc250_kernel/vmlinuz" 2>/dev/null || true)"',
        '[ -n "$bc250_owner" ] || { echo "ERROR: no package owns the running kernel $bc250_kernel, so its headers '
        'cannot be installed. Boot a kernel from your distribution and press Install again."; exit 66; }',
        # Never let this install move the headers past the kernel: with --needed
        # pacman still upgrades them to the repository's newer version, and the
        # DKMS hook then drops every module built for the running kernel
        # (2026-11-21: linux 7.3.4 with linux-headers 7.3.5). Checked before
        # anything is installed; the Compatibility row repairs it.
        'bc250_packages=(dkms git base-devel)',
        'if [ ! -e "/usr/lib/modules/$bc250_kernel/build/Makefile" ]; then',
        '  bc250_kver="$(pacman -Q "$bc250_owner" | awk \'{print $2}\')"',
        '  bc250_repo="$(LC_ALL=C pacman -Si "${bc250_owner}-headers" 2>/dev/null | awk -F\': \' \'/^Version/{print $2; exit}\' || true)"',
        '  if [ "$bc250_repo" != "$bc250_kver" ]; then',
        '    echo "ERROR: the running kernel ($bc250_owner $bc250_kver) has no headers, and the repository only has '
        '${bc250_repo:-none}. Nothing was installed. Open Additional settings › Compatibility › Kernel headers and '
        'press Repair: it updates the kernel and its headers together."',
        '    exit 67',
        '  fi',
        '  bc250_packages+=("${bc250_owner}-headers")',
        'fi',
        # A clang-built kernel (CachyOS) has to build its modules with clang.
        "if grep -qi clang /proc/version; then bc250_packages+=(clang llvm lld); fi",
        'echo "Installing ${bc250_packages[*]}..."',
        'sudo pacman -S --needed --noconfirm "${bc250_packages[@]}"',
        '[ -d "/usr/lib/modules/$bc250_kernel/build" ] || { echo "ERROR: the headers installed are for another '
        'version of $bc250_owner than the running $bc250_kernel. Update the system (sudo pacman -Syu), restart '
        'into the new kernel and press Install again."; exit 67; }',
        'bc250_stage="$(mktemp -d /tmp/bc250-driver.XXXXXX)"',
        "trap 'rm -rf -- \"$bc250_stage\"' EXIT",
        'bc250_src="$bc250_stage/src"',
        f"git clone --quiet {driver.repository} \"$bc250_src\"",
        f"git -C \"$bc250_src\" checkout --quiet --detach {driver.revision}",
        f"[ \"$(git -C \"$bc250_src\" rev-parse HEAD)\" = {driver.revision} ] "
        "|| { echo 'ERROR: the source is not at the reviewed revision. Nothing was installed.'; exit 29; }",
        checks,
        *(_patch_line(*patch) for patch in driver.patches),
        _write('"$bc250_src/Kbuild"', driver.kbuild),
        _write('"$bc250_src/Makefile"', MAKEFILE),
        _write('"$bc250_src/dkms.conf"', driver.dkms_conf()),
        # An earlier build of this version goes first, so an update is clean.
        f"sudo dkms remove {driver.package}/{driver.version} --all >/dev/null 2>&1 || true",
        f"sudo rm -rf -- {directory}",
        f"sudo install -d -m 0755 {directory}",
        f"sudo install -m 0644 {files} {directory}/",
        f"printf '%s\\n' {shlex.quote(driver.build_id)} | sudo tee {directory}/{BUILD_MARKER} >/dev/null",
        f"sudo dkms add {driver.package}/{driver.version}",
        f'sudo dkms install {driver.package}/{driver.version} -k "$bc250_kernel"',
        # An older copy still in memory would keep running instead of this one.
        f"sudo modprobe -r {driver.module} 2>/dev/null || true",
        f"sudo modprobe {driver.module} || true",
        "bc250_reading=''",
        "for _ in 1 2 3 4 5; do",
        f"  for bc250_hwmon in {hwmon_root}/hwmon*; do",
        f"    if [ \"$(cat \"$bc250_hwmon/name\" 2>/dev/null)\" = {driver.hwmon} ]; then",
        f'      bc250_reading="$(cat "$bc250_hwmon/{attribute}" 2>/dev/null || true)"',
        "    fi",
        "  done",
        '  [ -n "$bc250_reading" ] && break',
        "  sleep 1",
        "done",
        'if [ -n "$bc250_reading" ]; then',
        f'  echo "OK: first reading $((bc250_reading / {divisor})) {unit}. The driver loads by itself at every boot '
        'and is rebuilt with each kernel update."',
        "else",
        "  echo '[WARN] The driver is installed but is not reading yet. Its kernel messages:'",
        f"  sudo dmesg | grep -i {driver.module} | tail -n 5 || true",
    ]
    if driver.silent_hint:
        commands.append(f"  echo {shlex.quote('[WARN] ' + driver.silent_hint)}")
    commands.append("fi")
    return "\n".join(commands)


def remove_command(driver: Driver, family: str, *, after: Iterable[str] = ()) -> str:
    family = str(family or "").strip().lower()
    if family not in FAMILIES:
        raise RuntimeError(f"{driver.title} was not installed by Control Center on this distribution.")
    commands = shell_header(f"{driver.title} · remove {driver.package}")
    commands += [
        f"sudo modprobe -r {driver.module} 2>/dev/null || true",
        f"if dkms status {driver.package}/{driver.version} 2>/dev/null | grep -q .; then "
        f"sudo dkms remove {driver.package}/{driver.version} --all; fi",
        f"sudo rm -rf -- {driver.source_directory}",
        *after,
    ]
    return "\n".join(commands)
