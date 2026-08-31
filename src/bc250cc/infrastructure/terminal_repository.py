from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from bc250cc.infrastructure.terminal_plan import terminal_candidates, workflow_wrapper
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
            "{ printf '\\n== Process finished with exit code %s ==\\n' \"$status\"; "
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

    def _abrir_terminal(self, comando, titulo="BC250 Control Center"):
        state_dir = self._terminal_state_dir()
        run_id = time.time_ns()
        status_path = state_dir / f"status-{run_id}.txt"
        log_path = state_dir / f"workflow-{run_id}.log"
        wrapped = workflow_wrapper(comando, status_path, log_path)
        launch_path = state_dir / f"launch-{run_id}.sh"
        launch_path.write_text(
            "#!/usr/bin/env bash\n" + wrapped + "\n",
            encoding="utf-8",
        )
        launch_path.chmod(0o700)
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
