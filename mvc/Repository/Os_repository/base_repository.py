from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from .detector import OSInfo

if TYPE_CHECKING:
    from typing import Protocol

    class RepositoryHost(Protocol):
        def _command_path(self, name: str) -> str: ...
        def _tool_dir(self) -> Path: ...


class BaseOSRepository:
    family = "unsupported"
    dependency_script = ""
    fan_script = ""
    fan_persistence_script = "common/install-fan-persistence.sh"

    def __init__(self, host: "RepositoryHost", info: OSInfo):
        self.host = host
        self.info = info

    @property
    def scripts_root(self) -> Path:
        return Path(__file__).resolve().parent / "scripts"

    def command_path(self, name: str) -> str:
        return self.host._command_path(name)

    def tool_dir(self) -> Path:
        return self.host._tool_dir()

    def _script_path(self, relative_path: str) -> Path:
        if not relative_path:
            raise RuntimeError(f"{self.info.label} does not provide this operation")
        path = self.scripts_root / relative_path
        if not path.is_file():
            raise RuntimeError(f"Missing OS integration script: {path}")
        return path

    def _script_command(self, relative_path: str, *args: str, env: dict[str, str] | None = None) -> str:
        path = self._script_path(relative_path)
        assignments = []
        for key, value in sorted((env or {}).items()):
            assignments.append(f"{key}={shlex.quote(str(value))}")
        argv = ["bash", str(path), *args]
        return " ".join([*assignments, *(shlex.quote(item) for item in argv)])

    def prepare_dependencies_command(self, component: str = "all", *, cu_manager_script: str = "") -> str:
        env = {
            "BC250_OS_LABEL": self.info.label,
            "BC250_OS_FAMILY": self.info.family,
            "BC250_TOOLS_DIR": str(self.tool_dir()),
            "BC250_CU_MANAGER_SCRIPT": cu_manager_script,
        }
        return self._script_command(self.dependency_script, "--component", component, env=env)

    def install_governor_command(self) -> str:
        return self.prepare_dependencies_command("governor")

    def install_stress_command(self) -> str:
        return self.prepare_dependencies_command("stress")

    def install_umr_command(self, cu_manager_script: str = "") -> str:
        return self.prepare_dependencies_command("umr", cu_manager_script=cu_manager_script)

    def install_lm_sensors_command(self) -> str:
        return self.prepare_dependencies_command("sensors")

    def install_fan_pwm_command(self, tools_dir: str) -> str:
        return self._script_command(
            self.fan_script,
            env={
                "BC250_OS_LABEL": self.info.label,
                "BC250_OS_FAMILY": self.info.family,
                "BC250_NCT6687_SOURCE_DIR": tools_dir,
            },
        )

    def install_fan_persistence_command(self, tools_dir: str) -> str:
        return self._script_command(
            self.fan_persistence_script,
            env={
                "BC250_OS_LABEL": self.info.label,
                "BC250_OS_FAMILY": self.info.family,
                "BC250_NCT6687_SOURCE_DIR": tools_dir,
            },
        )
