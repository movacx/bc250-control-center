from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
import shlex
import shutil
import subprocess
import time


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TerminalLaunchResult:
    """Evidence that an authenticated workflow was handed to a terminal."""

    terminal: str
    title: str
    pid: int | None
    status_file: str


class TerminalRepository:
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
        script_path = directory / f"manual-{time.time_ns()}.sh"
        script_path.write_text(
            "#!/usr/bin/env bash\n"
            "set -o pipefail\n"
            f"printf '%s\\n' {shlex.quote('== ' + titulo + ' ==')}\n"
            f"{comando}\n"
            "status=$?\n"
            "printf '\\n== Process finished with exit code %s ==\\n' \"$status\"\n"
            "exit \"$status\"\n",
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        return script_path

    def _abrir_terminal(self, comando, titulo="BC250 Control Center"):
        comando = str(comando or "").strip()
        if not comando:
            raise RuntimeError("The requested terminal workflow is empty.")

        state_dir = self._terminal_state_dir()
        status_path = state_dir / f"status-{time.time_ns()}.txt"
        inner = shlex.quote(comando)
        quoted_status = shlex.quote(str(status_path))
        wrapped = (
            f"bash -lc {inner}; status=$?; "
            f"printf '%s\\n' \"$status\" > {quoted_status}; "
            "echo; "
            "echo \"== Process finished with exit code $status ==\"; "
            "echo \"You can copy this output if something failed.\"; "
            "read -r -p \"Enter to close...\" _; "
            "exit \"$status\""
        )

        terminales = []
        vistos = set()

        def agregar(cmd):
            if not cmd or not cmd[0]:
                return
            clave = tuple(cmd)
            if clave in vistos:
                return
            vistos.add(clave)
            terminales.append(cmd)

        terminal_env = os.environ.get("TERMINAL", "").strip()
        if terminal_env:
            partes = shlex.split(terminal_env)
            if partes:
                nombre = Path(partes[0]).name
                if nombre in ("ptyxis", "kgx", "gnome-console", "gnome-terminal"):
                    agregar(partes + ["--", "bash", "-lc", wrapped])
                elif nombre in ("konsole",):
                    agregar(partes + ["--new-tab", "-p", f"tabtitle={titulo}", "-e", "bash", "-lc", wrapped])
                elif nombre in ("kitty",):
                    agregar(partes + ["--title", titulo, "bash", "-lc", wrapped])
                elif nombre in ("alacritty", "rio"):
                    agregar(partes + ["-T", titulo, "-e", "bash", "-lc", wrapped])
                elif nombre in ("wezterm",):
                    agregar(partes + ["start", "--", "bash", "-lc", wrapped])
                elif nombre in ("foot", "footclient"):
                    agregar(partes + ["-T", titulo, "bash", "-lc", wrapped])
                else:
                    agregar(partes + ["-e", "bash", "-lc", wrapped])
                    agregar(partes + ["bash", "-lc", wrapped])

        agregar(["xdg-terminal-exec", "bash", "-lc", wrapped])
        agregar(["ptyxis", "--new-window", "--title", titulo, "--", "bash", "-lc", wrapped])
        agregar(["ptyxis", "--", "bash", "-lc", wrapped])
        agregar(["kgx", "--title", titulo, "--", "bash", "-lc", wrapped])
        agregar(["kgx", "--", "bash", "-lc", wrapped])
        agregar(["gnome-console", "--", "bash", "-lc", wrapped])
        agregar(["gnome-terminal", "--title", titulo, "--", "bash", "-lc", wrapped])
        agregar(["gnome-terminal", "--", "bash", "-lc", wrapped])
        agregar(["blackbox", "--working-directory", str(Path.home()), "--command", f"bash -lc {shlex.quote(wrapped)}"])
        agregar(["cosmic-term", "-e", "bash", "-lc", wrapped])
        agregar(["konsole", "--new-tab", "-p", f"tabtitle={titulo}", "-e", "bash", "-lc", wrapped])
        agregar(["konsole", "-p", f"tabtitle={titulo}", "-e", "bash", "-lc", wrapped])
        agregar(["qterminal", "-e", "bash", "-lc", wrapped])
        agregar(["lxqt-terminal", "-e", "bash", "-lc", wrapped])
        agregar(["lxterminal", "-e", "bash", "-lc", wrapped])
        agregar(["tilix", "-e", "bash", "-lc", wrapped])
        agregar(["terminator", "-x", "bash", "-lc", wrapped])
        agregar(["xfce4-terminal", "--title", titulo, "--command", f"bash -lc {shlex.quote(wrapped)}"])
        agregar(["mate-terminal", "--title", titulo, "--", "bash", "-lc", wrapped])
        agregar(["cinnamon-terminal", "--title", titulo, "--", "bash", "-lc", wrapped])
        agregar(["deepin-terminal", "-e", f"bash -lc {shlex.quote(wrapped)}"])
        agregar(["alacritty", "-T", titulo, "-e", "bash", "-lc", wrapped])
        agregar(["kitty", "--title", titulo, "bash", "-lc", wrapped])
        agregar(["wezterm", "start", "--", "bash", "-lc", wrapped])
        agregar(["footclient", "-T", titulo, "bash", "-lc", wrapped])
        agregar(["foot", "-T", titulo, "bash", "-lc", wrapped])
        agregar(["rio", "-T", titulo, "-e", "bash", "-lc", wrapped])
        agregar(["st", "-t", titulo, "-e", "bash", "-lc", wrapped])
        agregar(["urxvt", "-title", titulo, "-e", "bash", "-lc", wrapped])
        agregar(["xterm", "-T", titulo, "-e", "bash", "-lc", wrapped])

        launch_errors: list[str] = []
        for cmd in terminales:
            executable = shutil.which(cmd[0])
            if not executable:
                continue
            try:
                proceso = subprocess.Popen(cmd, start_new_session=True)
                time.sleep(0.35)
                return_code = proceso.poll()
                if return_code not in (0, None):
                    launch_errors.append(f"{cmd[0]} exited with code {return_code}")
                    continue
                return TerminalLaunchResult(
                    terminal=cmd[0],
                    title=titulo,
                    pid=proceso.pid,
                    status_file=str(status_path),
                )
            except OSError as error:
                launch_errors.append(f"{cmd[0]}: {error}")

        manual_script = self._manual_terminal_script(comando, titulo)
        detail = f" Attempts: {'; '.join(launch_errors)}" if launch_errors else ""
        raise RuntimeError(
            "No supported graphical terminal could be opened. "
            f"The workflow was saved to {manual_script}. Run it manually with: bash {manual_script}.{detail}"
        )
