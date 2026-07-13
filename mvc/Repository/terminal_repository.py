from pathlib import Path
import os
import shlex
import shutil
import subprocess
import time

class TerminalRepository:
    def _abrir_terminal(self, comando, titulo='BC250 Control Center'):
        inner = shlex.quote(comando)
        wrapped = (
            f'bash -lc {inner}; status=$?; '
            'echo; '
            'echo "== Process finished with exit code $status =="; '
            'echo "You can copy this output if something failed."; '
            'read -r -p "Enter to close..." _'
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

        terminal_env = os.environ.get('TERMINAL', '').strip()
        if terminal_env:
            partes = shlex.split(terminal_env)
            if partes:
                nombre = Path(partes[0]).name
                if nombre in ('ptyxis', 'kgx', 'gnome-console', 'gnome-terminal'):
                    agregar(partes + ['--', 'bash', '-lc', wrapped])
                elif nombre in ('konsole',):
                    agregar(partes + ['--new-tab', '-p', f'tabtitle={titulo}', '-e', 'bash', '-lc', wrapped])
                elif nombre in ('kitty',):
                    agregar(partes + ['--title', titulo, 'bash', '-lc', wrapped])
                elif nombre in ('alacritty', 'rio'):
                    agregar(partes + ['-T', titulo, '-e', 'bash', '-lc', wrapped])
                elif nombre in ('wezterm',):
                    agregar(partes + ['start', '--', 'bash', '-lc', wrapped])
                elif nombre in ('foot', 'footclient'):
                    agregar(partes + ['-T', titulo, 'bash', '-lc', wrapped])
                else:
                    agregar(partes + ['-e', 'bash', '-lc', wrapped])
                    agregar(partes + ['bash', '-lc', wrapped])

        agregar(['xdg-terminal-exec', 'bash', '-lc', wrapped])
        agregar(['ptyxis', '--new-window', '--title', titulo, '--', 'bash', '-lc', wrapped])
        agregar(['ptyxis', '--', 'bash', '-lc', wrapped])
        agregar(['kgx', '--title', titulo, '--', 'bash', '-lc', wrapped])
        agregar(['kgx', '--', 'bash', '-lc', wrapped])
        agregar(['gnome-console', '--', 'bash', '-lc', wrapped])
        agregar(['gnome-terminal', '--title', titulo, '--', 'bash', '-lc', wrapped])
        agregar(['gnome-terminal', '--', 'bash', '-lc', wrapped])
        agregar(['blackbox', '--working-directory', str(Path.home()), '--command', f'bash -lc {shlex.quote(wrapped)}'])
        agregar(['cosmic-term', '-e', 'bash', '-lc', wrapped])
        agregar(['konsole', '--new-tab', '-p', f'tabtitle={titulo}', '-e', 'bash', '-lc', wrapped])
        agregar(['qterminal', '-e', 'bash', '-lc', wrapped])
        agregar(['lxqt-terminal', '-e', 'bash', '-lc', wrapped])
        agregar(['lxterminal', '-e', 'bash', '-lc', wrapped])
        agregar(['tilix', '-e', 'bash', '-lc', wrapped])
        agregar(['terminator', '-x', 'bash', '-lc', wrapped])
        agregar(['xfce4-terminal', '--title', titulo, '--command', f'bash -lc {shlex.quote(wrapped)}'])
        agregar(['mate-terminal', '--title', titulo, '--', 'bash', '-lc', wrapped])
        agregar(['cinnamon-terminal', '--title', titulo, '--', 'bash', '-lc', wrapped])
        agregar(['deepin-terminal', '-e', f'bash -lc {shlex.quote(wrapped)}'])
        agregar(['alacritty', '-T', titulo, '-e', 'bash', '-lc', wrapped])
        agregar(['kitty', '--title', titulo, 'bash', '-lc', wrapped])
        agregar(['wezterm', 'start', '--', 'bash', '-lc', wrapped])
        agregar(['footclient', '-T', titulo, 'bash', '-lc', wrapped])
        agregar(['foot', '-T', titulo, 'bash', '-lc', wrapped])
        agregar(['rio', '-T', titulo, '-e', 'bash', '-lc', wrapped])
        agregar(['st', '-t', titulo, '-e', 'bash', '-lc', wrapped])
        agregar(['urxvt', '-title', titulo, '-e', 'bash', '-lc', wrapped])
        agregar(['xterm', '-T', titulo, '-e', 'bash', '-lc', wrapped])

        for cmd in terminales:
            if not shutil.which(cmd[0]):
                continue
            try:
                proceso = subprocess.Popen(cmd)
                time.sleep(0.25)
                if proceso.poll() is not None and proceso.returncode not in (0, None):
                    continue
                return True
            except Exception:
                continue

        log_dir = Path.home() / '.local' / 'state' / 'bc250-control-center'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f'terminal-fallback-{int(time.time())}.log'
        fallback = (
            f'bash -lc {inner}; status=$?; '
            'echo; '
            'echo "== Process finished with exit code $status =="; '
            f'echo "No graphical terminal found. Log: {shlex.quote(str(log_path))}"; '
            'exit $status'
        )
        with log_path.open('w', encoding='utf-8') as salida:
            salida.write(f'== {titulo} ==\n')
            salida.write(f'Comando: {comando}\n\n')
            salida.flush()
            subprocess.Popen(['bash', '-lc', fallback], stdout=salida, stderr=subprocess.STDOUT)
        return True

