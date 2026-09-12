from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bc250cc.infrastructure.terminal_plan import (
    _evidence_capture_shell,
    _evidence_render_shell,
    exit_explanation_shell,
    terminal_candidates,
    workflow_wrapper,
)
from bc250cc.shared.operation_contract import parse_operation_log

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TerminalLaunchResult:
    """Evidence that an authenticated workflow was handed to a terminal."""

    terminal: str
    title: str
    pid: int | None
    status_file: str
    log_file: str


@dataclass(frozen=True)
class EmbeddedTerminalRequest:
    """Everything a host needs to run one workflow inside its own window."""

    argv: tuple[str, ...]
    title: str
    status_file: str
    log_file: str
    launch_file: str


_embedded_launcher: Callable[[EmbeddedTerminalRequest], TerminalLaunchResult | None] | None = None


def set_embedded_terminal_launcher(
    launcher: Callable[[EmbeddedTerminalRequest], TerminalLaunchResult | None] | None,
) -> None:
    """Register a host that can run workflows without a separate window.

    The desktop shell installs its console panel here at start-up. Nothing else
    changes: the workflow text, the log file and the status file are identical
    either way, so the thirty-seven call sites and everything that waits on
    their status files stay exactly as they were. A host that is busy or that
    cannot take the workflow returns None, and the external terminals are then
    tried in the usual order.
    """
    global _embedded_launcher
    _embedded_launcher = launcher


def embedded_terminal_launcher():
    return _embedded_launcher


class TerminalRepository:
    @staticmethod
    def leer_resultado_terminal(log_file, exit_code=None):
        """Read structured workflow evidence without executing or mutating anything."""
        return parse_operation_log(log_file, exit_code=exit_code)

    def _terminal_state_dir(self) -> Path:
        state_home = os.environ.get("XDG_STATE_HOME", "").strip()
        root = Path(state_home) if state_home else Path.home() / ".local" / "state"
        directory = root / "bc250-control-center" / "terminal"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            logger.debug("Could not restrict terminal workflow state directory permissions", exc_info=True)
        return directory

    def _manual_terminal_script(self, comando: str, titulo: str) -> Path:
        directory = self._terminal_state_dir()
        run_id = time.time_ns()
        script_path = directory / f"manual-{run_id}.sh"
        log_path = directory / f"workflow-{run_id}.log"
        inner = shlex.quote(str(comando or '').strip())
        pipeline = shlex.quote(
            f"bash -lc {inner} 2>&1 | tee {shlex.quote(str(log_path))}"
        )
        script_path.write_text(
            "#!/usr/bin/env bash\n"
            "set -o pipefail\n"
            f"printf '%s\\n' {shlex.quote('== ' + titulo + ' ==')}\n"
            f"bash -o pipefail -c {pipeline}\n"
            "status=$?\n"
            f"{_evidence_capture_shell(log_path)}\n"
            "{ printf '\\n== Process finished with exit code %s ==\\n' \"$status\"; "
            f"{exit_explanation_shell()}; "
            f"{_evidence_render_shell()}; "
            f"printf '%s\\n' {shlex.quote('Full log saved to: ' + str(log_path))}; "
            f"}} 2>&1 | tee -a {shlex.quote(str(log_path))}\n"
            "exit \"$status\"\n",
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        return script_path

    @staticmethod
    def _launch_terminal_candidates(candidates):
        errors: list[str] = []
        for cmd in candidates:
            if not shutil.which(cmd[0]):
                continue
            try:
                process = subprocess.Popen(cmd, start_new_session=True)
                time.sleep(0.35)
                return_code = process.poll()
                if return_code not in (0, None):
                    errors.append(f"{cmd[0]} exited with code {return_code}")
                    continue
                return cmd[0], process.pid, errors
            except OSError as error:
                errors.append(f"{cmd[0]}: {error}")
        return "", None, errors

    @staticmethod
    def _write_launch_script(
        path: Path, comando, status_path: Path, log_path: Path, *, hold: bool
    ) -> Path:
        wrapped = workflow_wrapper(comando, status_path, log_path, hold=hold)
        path.write_text("#!/usr/bin/env bash\n" + wrapped + "\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    def _try_embedded_terminal(
        self, comando, titulo: str, state_dir: Path, run_id: int,
        status_path: Path, log_path: Path,
    ):
        """Offer the workflow to the in-application console, if one is listening."""
        launcher = embedded_terminal_launcher()
        if launcher is None:
            return None
        launch_path = self._write_launch_script(
            state_dir / f"embedded-{run_id}.sh", comando, status_path, log_path, hold=False
        )
        request = EmbeddedTerminalRequest(
            argv=("bash", str(launch_path)),
            title=str(titulo),
            status_file=str(status_path),
            log_file=str(log_path),
            launch_file=str(launch_path),
        )
        try:
            return launcher(request)
        except Exception:
            # The console failing must never cost the user the workflow; fall
            # through to the terminal emulators that were always used here.
            logger.exception("The embedded terminal could not run the workflow")
            return None

    def _abrir_terminal(self, comando, titulo="BC250 Control Center"):
        state_dir = self._terminal_state_dir()
        run_id = time.time_ns()
        status_path = state_dir / f"status-{run_id}.txt"
        log_path = state_dir / f"workflow-{run_id}.log"
        embedded = self._try_embedded_terminal(
            comando, titulo, state_dir, run_id, status_path, log_path
        )
        if embedded is not None:
            return embedded
        launch_path = self._write_launch_script(
            state_dir / f"launch-{run_id}.sh", comando, status_path, log_path, hold=True
        )
        # Some terminal launchers inspect and expand command-line environment
        # references before Bash receives them. Keep the complex reviewed
        # workflow in a private script and pass the terminal a simple path.
        launch_command = f"exec bash {shlex.quote(str(launch_path))}"
        candidates = terminal_candidates(
            launch_command,
            titulo,
            terminal_env=os.environ.get("TERMINAL", ""),
            home=Path.home(),
        )
        terminal, pid, launch_errors = self._launch_terminal_candidates(candidates)
        if terminal:
            return TerminalLaunchResult(
                terminal=terminal,
                title=titulo,
                pid=pid,
                status_file=str(status_path),
                log_file=str(log_path),
            )

        detail = f" Attempts: {'; '.join(launch_errors)}" if launch_errors else ""
        raise RuntimeError(
            "No supported graphical terminal could be opened. "
            f"The workflow was saved to {launch_path}. "
            f"Run it manually with: bash {launch_path}.{detail}"
        )
