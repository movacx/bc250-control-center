"""Bounded system setup primitives. No work is performed at import time.

The injected root/runner are for isolated tests, never exposed by the helper CLI.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

MARKER = "# Managed by BC250 Control Center\n"
HELPER = "/usr/libexec/bc250-control-center/bc250-system-setup-helper"
STATE = "/var/lib/bc250-control-center/system-setup"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "HOME": "/root"}


class SetupError(RuntimeError):
    pass


class Host:
    def __init__(self, root: Path = Path("/"), runner=None):
        self.root = root
        self.runner = runner

    def path(self, name: str) -> Path:
        if not name.startswith("/") or ".." in Path(name).parts:
            raise SetupError("Invalid internal path")
        return self.root / name.lstrip("/")

    def read(self, name: str) -> str:
        try:
            return self.path(name).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return ""

    def command(self, name: str) -> bool:
        if self.runner is not None:
            return True
        return shutil.which(name, path=ENV["PATH"]) is not None

    def run(self, *args: str, check: bool = True) -> str:
        if self.runner is not None:
            return self.runner(*args, check=check)
        executable = shutil.which(args[0], path=ENV["PATH"])
        if not executable:
            raise SetupError(f"Required command is missing: {args[0]}")
        try:
            result = subprocess.run([executable, *args[1:]], env=ENV, cwd="/",
                                    capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise SetupError(f"{args[0]} timed out; check status before retrying") from exc
        if check and result.returncode:
            raise SetupError(f"{args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout.strip()

    def safe(self, name: str) -> Path:
        path = self.path(name)
        for part in (path, *path.parents):
            if part.is_symlink():
                raise SetupError(f"Refusing symbolic link: {part}")
            if part.exists() and self.root == Path("/"):
                info = part.stat()
                if info.st_uid != 0 or info.st_mode & 0o022 or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                    raise SetupError(f"Path is not protected by root: {part}")
            if part == self.root:
                break
        return path

    def write(self, name: str, data: str | bytes, *, mode: int = 0o644) -> None:
        path = self.safe(name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.safe(name)
        raw = data.encode() if isinstance(data, str) else data
        fd, temp = tempfile.mkstemp(prefix=".bc250-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp, mode)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def managed(self, name: str, data: str) -> None:
        path = self.safe(name)
        if path.exists() and not self.read(name).startswith(MARKER.strip()):
            raise SetupError(f"Existing configuration belongs to another tool: {name}")
        self.write(name, MARKER + data)

    def remove_managed(self, name: str) -> None:
        path = self.safe(name)
        if path.exists():
            if not self.read(name).startswith(MARKER.strip()):
                raise SetupError(f"Foreign configuration preserved: {name}")
            path.unlink()

    def state(self, key: str) -> dict:
        try:
            data = json.loads(self.read(f"{STATE}/{key}.json") or "{}")
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return data
        except (ValueError, TypeError) as exc:
            raise SetupError(f"Invalid {key} setup state; refusing to overwrite it") from exc

    def save(self, key: str, state: dict) -> None:
        self.write(f"{STATE}/{key}.json", json.dumps(state, sort_keys=True, indent=2) + "\n")

    def os_release(self) -> dict[str, str]:
        """Return the non-executable subset of os-release used for routing.

        os-release is shell-like, but it must never be sourced by a privileged
        helper.  Distribution identifiers are restricted by the specification
        to simple lower-case tokens; keeping only those values also makes a
        malformed image fail closed.
        """
        values = {}
        for line in self.read("/etc/os-release").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key in {"ID", "ID_LIKE", "VARIANT_ID", "IMAGE_ID"}:
                    values[key] = value.strip().strip('\"\'').lower()
        return values

    def immutable_image(self) -> bool:
        values = self.os_release()
        image_tokens = set()
        for key in ("ID", "VARIANT_ID", "IMAGE_ID"):
            image_tokens.update(filter(None, re.split(r"[^a-z0-9]+", values.get(key, ""))))
        immutable_tokens = {
            "bazzite", "steamos", "holo", "ublue", "universal-blue",
            "silverblue", "kinoite", "sericea", "onyx", "atomic", "bootc",
        }
        return self.path("/run/ostree-booted").exists() or bool(image_tokens & immutable_tokens)

    def distro_family(self) -> str:
        """Identify a supported mutable family through ID and ID_LIKE."""
        values = self.os_release()
        identifiers = {values.get("ID", ""), *values.get("ID_LIKE", "").split()}
        if identifiers & {"arch", "archlinux", "cachyos", "manjaro", "endeavouros", "garuda"}:
            return "arch"
        if identifiers & {"debian", "ubuntu", "linuxmint", "pop"}:
            return "debian"
        if identifiers & {"fedora", "rhel", "nobara", "ultramarine"}:
            return "fedora"
        return "unsupported"

    def mutable_systemd(self) -> bool:
        return (self.distro_family() != "unsupported"
                and not self.immutable_image()
                and self.path("/run/systemd/system").is_dir())

    def bc250(self) -> bool:
        for device in self.path("/sys/bus/pci/devices").glob("*"):
            try:
                if ((device / "vendor").read_text().strip() == "0x1002"
                        and (device / "device").read_text().strip() == "0x13fe"):
                    return True
            except OSError:
                continue
        return False

    def require_host(self) -> None:
        """Refuse with the reason, not with the list of requirements.

        Four different situations produced one sentence naming all four, which
        on Gentoo or Alpine — both first-class elsewhere in this project — read
        as "your distribution is wrong" when the real answer is that this
        subsystem writes systemd units and those hosts run OpenRC.
        """
        if not self.bc250():
            raise SetupError(
                "HARDWARE_CONTEXT: AMD BC-250 hardware identity was not detected."
            )
        if self.immutable_image():
            raise SetupError(
                "This operation writes to /etc and /usr, which are read-only on an "
                "image-based system. Layer the change with rpm-ostree instead."
            )
        if not self.path("/run/systemd/system").is_dir():
            raise SetupError(
                "Swap, zram, TTM and ACPI persistence are installed as systemd units, "
                "and this host does not run systemd. Live tuning is unaffected; only "
                "applying it at boot is unavailable."
            )
        if self.distro_family() == "unsupported":
            raise SetupError(
                "This operation uses distribution-specific package and boot layouts, "
                "and only the Arch, Debian and Fedora families have a reviewed one."
            )

    def writable_parameter(self, name: str) -> bool:
        try:
            return bool(self.path(name).stat().st_mode & stat.S_IWUSR)
        except OSError:
            return False

    def parameter(self, name: str, value: str) -> None:
        if not self.writable_parameter(name):
            raise SetupError(f"Kernel parameter is not writable: {name}")
        self.path(name).write_text(value + "\n", encoding="ascii")
        actual = self.read(name).lower()
        expected = value.lower()
        if actual != expected and {actual, expected} not in ({"y", "1"}, {"n", "0"}):
            raise SetupError(f"Kernel did not accept {name}")
