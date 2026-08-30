"""Explicit init adapters used by application services and frontends."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from bc250cc.platform.init import InitSystem, detect_init_system


class InitService:
    def __init__(self, *, init_system: InitSystem | None = None) -> None:
        self.init_system = init_system or detect_init_system()

    def _run(self, command: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError as error:
            raise RuntimeError(f"Required init command is not installed: {command[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Init command timed out after {timeout}s: {command[0]}") from error


class SystemdUserService(InitService):
    def command(self, *arguments: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
        if self.init_system is not InitSystem.SYSTEMD:
            raise RuntimeError("The optional daemon requires an active systemd user manager.")
        if shutil.which("systemctl") is None:
            raise RuntimeError("systemctl is not available on this system.")
        return self._run(("systemctl", "--user", *arguments), timeout)


class OpenRCService(InitService):
    def command(self, service: str, action: str, *, timeout: int = 15) -> subprocess.CompletedProcess[str]:
        if self.init_system is not InitSystem.OPENRC:
            raise RuntimeError("OpenRC is not the active init system.")
        if shutil.which("rc-service") is None:
            raise RuntimeError("rc-service is not available on this OpenRC system.")
        return self._run(("rc-service", service, action), timeout)
