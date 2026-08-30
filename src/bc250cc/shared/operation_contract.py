"""Stable result and failure contract for system-facing BC250 operations."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

RESULT_PREFIX = "BC250_RESULT"


class OperationExit(IntEnum):
    OK = 0
    REBOOT_REQUIRED = 20
    KERNEL_HEADERS = 21
    KERNEL_MODULE = 22
    PERSISTENCE = 24
    SOURCE_FETCH = 29
    CPU_OC_SOURCE = 30
    CU_MANAGER = 31
    UMR = 32
    GOVERNOR = 33
    RUNTIME_COMMAND = 34
    PYTHON_RUNTIME = 35
    CORE_UNLOCK = 36
    UMR_DATABASE = 37
    STEAMOS_AMDGPU = 38
    STEAMOS_DIAGNOSTIC = 39
    CONCURRENT_OPERATION = 40
    GOVERNOR_CONFLICT = 41
    OBERON_DEPENDENCY = 52
    OBERON_BUILD = 53
    CYAN_RUNTIME = 61
    CYAN_DBUS = 62
    STEAMOS_ROOT_STATE = 70
    STEAMOS_ROOT_RESTORE = 71


_SAFE_NEXT_ACTIONS = {
    OperationExit.REBOOT_REQUIRED: "Reboot when convenient, then run check mode.",
    OperationExit.KERNEL_HEADERS: "Install headers matching the running kernel exactly; do not load the module.",
    OperationExit.KERNEL_MODULE: "Keep the existing module/state and inspect the exported log before retrying.",
    OperationExit.CONCURRENT_OPERATION: "Wait for the other BC250 operation to finish, then retry.",
    OperationExit.STEAMOS_AMDGPU: "Do not reboot based on this failed run; inspect status and rollback instructions first.",
    OperationExit.STEAMOS_ROOT_RESTORE: "Run sudo steamos-readonly enable from Desktop Mode before other maintenance.",
}


@dataclass(frozen=True)
class OperationEvent:
    status: str
    component: str
    code: int
    message: str = ""

    @property
    def successful(self) -> bool:
        return self.status == "ok" and self.code == 0


@dataclass(frozen=True)
class OperationReport:
    exit_code: int | None
    events: tuple[OperationEvent, ...]
    log_path: str = ""

    @property
    def successful(self) -> bool:
        return self.exit_code == 0 and all(event.successful for event in self.events)

    @property
    def has_structured_evidence(self) -> bool:
        """Whether the workflow emitted at least one machine-readable event.

        A zero shell exit status still matters for older/general terminal
        commands, so ``successful`` deliberately keeps its historic meaning.
        System-changing workflows, however, should require this stronger
        signal before a UI labels an operation as verified.
        """

        return bool(self.events)

    @property
    def verified_success(self) -> bool:
        """True only for a zero exit with complete successful BC250 evidence."""

        return self.successful and self.has_structured_evidence

    @property
    def component_failures(self) -> tuple[OperationEvent, ...]:
        """Return contradictory/non-success event evidence without guessing."""

        return tuple(event for event in self.events if not event.successful)

    @property
    def reboot_required(self) -> bool:
        return self.exit_code == OperationExit.REBOOT_REQUIRED

    @property
    def safe_next_action(self) -> str:
        if self.exit_code == 0:
            if self.verified_success:
                return "No further system action is required; keep the exported workflow log for recovery evidence."
            if self.component_failures:
                return "A component reported failure despite the shell exit status; inspect the workflow log before retrying or changing system state."
            return "The command exited successfully without structured BC250 evidence; inspect the workflow log before treating the system state as verified."
        try:
            code = OperationExit(self.exit_code)
        except (TypeError, ValueError):
            return "Inspect the operation log before retrying or changing system state."
        return _SAFE_NEXT_ACTIONS.get(
            code, "Correct the reported component failure, then run check mode before apply."
        )


def parse_result_line(line: str) -> OperationEvent | None:
    """Parse one shell-escaped BC250_RESULT line without executing it."""
    try:
        fields = shlex.split(str(line).strip(), posix=True)
    except ValueError:
        return None
    if not fields or fields[0] != RESULT_PREFIX:
        return None
    values: dict[str, str] = {}
    for field in fields[1:]:
        if "=" not in field:
            return None
        key, value = field.split("=", 1)
        if key not in {"status", "component", "code", "message"}:
            continue
        values[key] = value
    if not values.get("status") or not values.get("component"):
        return None
    try:
        code = int(values.get("code", "0"))
    except ValueError:
        return None
    return OperationEvent(
        status=values["status"],
        component=values["component"],
        code=code,
        message=values.get("message", ""),
    )


def parse_operation_log(path: str | Path, *, exit_code: int | None = None) -> OperationReport:
    log_path = Path(path)
    events: list[OperationEvent] = []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        event = parse_result_line(line)
        if event is not None:
            events.append(event)
    return OperationReport(exit_code=exit_code, events=tuple(events), log_path=str(log_path))
