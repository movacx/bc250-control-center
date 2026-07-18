from pathlib import Path
import shlex
import shutil
import time

class DependenciasRepository:
    def estado_herramientas_bc250(self):
        ahora = time.monotonic()
        if self.estado_herramientas_cache is not None and ahora - self.estado_herramientas_cache_time < 10:
            return dict(self.estado_herramientas_cache)
        cu_live = self._command_path('bc250-cu-live-manager') or self._buscar_archivo('bc250-cu-live-manager.sh')
        live_repo = self._buscar_directorio_con('bc250-cu-live-manager.sh', 'bc250-cu-live-manager')
        cu_manager = cu_live
        cu_kind = 'WinnieLV/bc250-cu-live-manager' if cu_live else ''
        smu_path = self._buscar_directorio_con('bc250_detect.py', 'bc250_smu_oc')
        bc250_detect = self._command_path('bc250-detect')
        resultado = {
            'governor_cmd': self._command_path('cyan-skillfish-governor-smu'),
            'governor_pkg': bool(self._command_path('cyan-skillfish-governor-smu')),
            'yay': self._command_path('yay'),
            'paru': self._command_path('paru'),
            'git': self._git_path(),
            'umr': self._command_path('umr'),
            'stress': self._command_path('stress'),
            'bc250_detect': bc250_detect,
            'cu_manager': cu_manager,
            'cu_manager_kind': cu_kind,
            'cu_manager_exists': bool(cu_manager and (Path(cu_manager).exists() or shutil.which(Path(cu_manager).name))),
            'cu_live_repo_path': live_repo,
            'cu_repo_path': live_repo,
            'cu_map_repo_path': '',
            'cu_map_script': '',
            'smu_oc_path': smu_path,
            'smu_oc_exists': bool(smu_path and Path(smu_path).exists()),
            'tools_dir': str(self._tool_dir()),
        }
        self.estado_herramientas_cache = resultado
        self.estado_herramientas_cache_time = ahora
        return dict(resultado)


    def instalar_governor(self):
        if self._command_path('cyan-skillfish-governor-smu'):
            return True
        comando = self._comando_instalar_governor_smu()
        if not comando:
            raise RuntimeError('Could not find a compatible installer for cyan-skillfish-governor-smu')
        return self._abrir_terminal(comando, 'Instalar governor')


    def instalar_cpu_oc(self):
        tools = self.estado_herramientas_bc250()
        if tools['bc250_detect']:
            return True
        if tools['smu_oc_exists']:
            path = shlex.quote(tools['smu_oc_path'])
            cmd = f'echo "OK: bc250_smu_oc repository found at {path}"; echo "It is not installed with pip to avoid PEP 668. The app runs it directly with PYTHONPATH=."'
            return self._abrir_terminal(cmd, 'Preparar bc250_smu_oc')
        if not tools.get('git'):
            raise RuntimeError('Could not find bc250-detect or git to download bc250_smu_oc')
        destino = self._tool_dir() / 'bc250_smu_oc'
        destino.parent.mkdir(parents=True, exist_ok=True)
        qdest = shlex.quote(str(destino))
        git_cmd = shlex.quote(tools.get('git') or 'git')
        cmd = f'mkdir -p {shlex.quote(str(destino.parent))}; if [ -d {qdest}/.git ]; then {git_cmd} -C {qdest} pull --ff-only; else {git_cmd} clone --depth 1 https://github.com/bc250-collective/bc250_smu_oc {qdest}; fi; test -f {qdest}/bc250_detect.py && echo "OK: bc250_smu_oc prepared without pip at {qdest}" || echo "WARN: bc250_detect.py was not found"'
        return self._abrir_terminal(cmd, 'Preparar bc250_smu_oc')



    def instalar_cu_manager(self):
        tools = self.estado_herramientas_bc250()
        if tools['cu_manager_exists']:
            return True
        if not tools.get('git'):
            raise RuntimeError('Could not find local bc250-cu-live-manager or git to download it')
        destino = self._tool_dir() / 'bc250-cu-live-manager'
        destino.parent.mkdir(parents=True, exist_ok=True)
        qdest = shlex.quote(str(destino))
        git_cmd = shlex.quote(tools.get('git') or 'git')
        cmd = f'mkdir -p {shlex.quote(str(destino.parent))}; if [ -d {qdest}/.git ]; then {git_cmd} -C {qdest} pull --ff-only; else {git_cmd} clone --depth 1 https://github.com/WinnieLV/bc250-cu-live-manager {qdest}; fi; chmod +x {qdest}/bc250-cu-live-manager.sh; test -x {qdest}/bc250-cu-live-manager.sh && echo "OK: bc250-cu-live-manager prepared at {qdest}" || echo "WARN: bc250-cu-live-manager.sh was not found"'
        return self._abrir_terminal(cmd, 'Preparar bc250-cu-live-manager')


    def instalar_dependencias_bc250(self):
        tools = self.estado_herramientas_bc250()
        self._tool_dir().mkdir(parents=True, exist_ok=True)
        rutas = self.config_paths()
        cpu_destino = self._tool_dir() / 'bc250_smu_oc'
        cu_destino = self._tool_dir() / 'bc250-cu-live-manager'
        aur_dir = self._tool_dir() / 'aur-cyan-skillfish-governor-smu'
        git_cmd = shlex.quote(tools.get('git') or 'git')
        deps_script = Path(__file__).resolve().parents[1] / 'Resources' / 'scripts' / 'bc250-install-system-deps.sh'
        comandos = [
            'set +e',
            f'mkdir -p {shlex.quote(str(self._tool_dir()))}',
            'export LC_ALL=C LANG=C',
            'echo "== Preparing BC250 dependencies =="',
            'echo',
            'echo "== Universal system dependency installer =="',
            f'if [ -x {shlex.quote(str(deps_script))} ]; then bash {shlex.quote(str(deps_script))} --runtime; else echo "WARN: bc250-install-system-deps.sh was not found"; fi',
            'echo',
            'echo "== Paths used by BC250 Control Center =="',
            f'echo "Data/tools: {shlex.quote(str(self._tool_dir()))}"',
            f'echo "Config: {shlex.quote(rutas.get("config", ""))}"',
            f'echo "Profiles: {shlex.quote(rutas.get("perfiles", ""))}"',
            f'echo "History: {shlex.quote(rutas.get("historial", ""))}"',
            f'echo "Repo CPU OC bc250_smu_oc: {shlex.quote(str(cpu_destino))}"',
            f'echo "Repo 40CU live-manager: {shlex.quote(str(cu_destino))}"',
            f'echo "Repo AUR governor: {shlex.quote(str(aur_dir))}"',
            'echo',
            'echo "== Third-party credits =="',
            'echo "BC250 Control Center integrates community tools from official upstream repositories."',
            'echo "These tools remain property of their respective authors/contributors."',
            'echo "If your terminal/browser has trouble opening multiple links, use: Information > Official repositories."',
            'echo "cyan-skillfish-governor: https://github.com/filippor/cyan-skillfish-governor/tree/smu"',
            'echo "bc250_smu_oc: https://github.com/bc250-collective/bc250_smu_oc"',
            'echo "bc250-cu-live-manager: https://github.com/WinnieLV/bc250-cu-live-manager"',
            'echo "bc250-40cu-unlock reference/docs: https://github.com/duggasco/bc250-40cu-unlock"',
            'echo',
        ]

        comandos.append('command -v cyan-skillfish-governor-smu && echo "OK: cyan-skillfish-governor-smu available" || echo "WARN: governor is not available yet. On Bazzite/rpm-ostree reboot; on Debian/Ubuntu check the upstream .deb install output."')

        if not tools.get('bc250_detect'):
            destino = cpu_destino
            if tools.get('smu_oc_exists'):
                destino_existente = shlex.quote(tools['smu_oc_path'])
                comandos.append('echo "OK: local bc250_smu_oc repository found. pip is not used because of PEP 668; the app runs bc250_detect.py directly."')
                comandos.append(f'test -f {destino_existente}/bc250_detect.py && echo "OK: bc250_detect.py available at {destino_existente}" || echo "WARN: bc250_detect.py is missing at {destino_existente}"')
            else:
                comandos.append('echo "== Cloning/preparing bc250_smu_oc without pip =="')
                comandos.append(f'if command -v git >/dev/null 2>&1; then if [ -d {shlex.quote(str(destino))}/.git ]; then git -C {shlex.quote(str(destino))} pull --ff-only; else git clone --depth 1 https://github.com/bc250-collective/bc250_smu_oc {shlex.quote(str(destino))}; fi; else echo "WARN: git is not available to clone bc250_smu_oc."; fi')
                comandos.append(f'test -f {shlex.quote(str(destino))}/bc250_detect.py && echo "OK: bc250_detect.py ready. The app will run it directly with PYTHONPATH=." || echo "WARN: bc250_detect.py was not found after cloning."')
        else:
            comandos.append('echo "OK: bc250-detect found."')

        if not tools.get('cu_manager_exists'):
            comandos.append('echo "== Cloning bc250-cu-live-manager from WinnieLV =="')
            comandos.append(f'if command -v git >/dev/null 2>&1; then if [ -d {shlex.quote(str(cu_destino))}/.git ]; then git -C {shlex.quote(str(cu_destino))} pull --ff-only; else git clone --depth 1 https://github.com/WinnieLV/bc250-cu-live-manager {shlex.quote(str(cu_destino))}; fi; else echo "WARN: git is not available to clone bc250-cu-live-manager."; fi')
            comandos.append(f'chmod +x {shlex.quote(str(cu_destino))}/bc250-cu-live-manager.sh 2>/dev/null || true')
            comandos.append(f'test -x {shlex.quote(str(cu_destino))}/bc250-cu-live-manager.sh && echo "OK: live-manager ready at {shlex.quote(str(cu_destino))}" || echo "WARN: bc250-cu-live-manager.sh was not found after cloning."')
        else:
            comandos.append(f'echo "OK: 40CU live-manager found ({tools.get("cu_manager_kind")}) at {shlex.quote(str(tools.get("cu_manager", "")))}"')

        comandos.append('command -v stress && echo "OK: stress available for CPU OC" || echo "WARN: stress is missing; CPU OC will not work until it is installed."')

        if not tools.get('umr'):
            comandos.append('echo "== UMR not detected: live-manager can try to install it if you run install-umr =="')
            script_expr = f'{shlex.quote(str(cu_destino))}/bc250-cu-live-manager.sh'
            if tools.get('cu_manager_exists'):
                comandos.append(f'echo "You can install UMR with: sudo {shlex.quote(str(tools.get("cu_manager", "")))} install-umr"')
            else:
                comandos.append(f'test -x {script_expr} && echo "You can install UMR with: sudo {script_expr} install-umr" || true')
        else:
            comandos.append('echo "OK: UMR found."')

        comandos.extend([
            'echo',
            'echo "== Path summary =="',
            f'echo "Tools: {shlex.quote(str(self._tool_dir()))}"',
            f'echo "CPU OC repo: {shlex.quote(str(cpu_destino))}"',
            f'echo "40CU live-manager: {shlex.quote(str(cu_destino))}"',
            f'echo "History JSONL: {shlex.quote(rutas.get("historial", ""))}"',
            'echo',
            'echo "== Finished. Restart the app or open the BC250 view to refresh state. =="',
        ])
        return self._abrir_terminal('; '.join(comandos), 'Preparar dependencias BC250')


    def _comando_instalar_governor_smu(self):
        if self._command_path('pacman'):
            helper = self._command_path('yay') or self._command_path('paru')
            if helper:
                return f'{shlex.quote(helper)} -S --needed cyan-skillfish-governor-smu'
            if self._command_path('makepkg') and self._git_path():
                aur_dir = self._tool_dir() / 'aur-cyan-skillfish-governor-smu'
                git_cmd = shlex.quote(self._git_path())
                qaur = shlex.quote(str(aur_dir))
                return f'if [ -d {qaur}/.git ]; then {git_cmd} -C {qaur} pull --ff-only; else {git_cmd} clone https://aur.archlinux.org/cyan-skillfish-governor-smu.git {qaur}; fi; cd {qaur} && makepkg -si --needed'
        if self._es_ostree():
            return 'sudo dnf -y copr enable filippor/bazzite; sudo rpm-ostree install --idempotent cyan-skillfish-governor-smu; echo "NOTICE: Bazzite/rpm-ostree requires a reboot before enabling the governor."'
        if self._command_path('dnf'):
            return 'sudo dnf -y copr enable filippor/bazzite; sudo dnf -y install cyan-skillfish-governor-smu'
        if self._command_path('apt'):
            return self._comando_instalar_governor_smu_debian()
        return ''


    def _comando_instalar_governor_smu_debian(self):
        return r'''
set +e
echo "== Debian/Ubuntu: installing cyan-skillfish-governor-smu =="
echo "Source: https://github.com/filippor/cyan-skillfish-governor/tree/smu"
echo "Debian Stable is best-effort; a newer kernel/Mesa stack may still be required on some BC-250 setups."
echo "Debian BC-250 docs may require kernel parameter amdgpu.sg_display=0; the app does not edit bootloader settings automatically."
VERSION="${BC250_GOVERNOR_SMU_VERSION:-0.4.11}"
TMPDIR="$(mktemp -d)"
DEB="cyan-skillfish-governor-smu_${VERSION}-1_amd64.deb"
DEB_URL="https://github.com/filippor/cyan-skillfish-governor/releases/download/v${VERSION}/${DEB}"
TAR="cyan-skillfish-governor-smu-v${VERSION}-x86_64-linux.tar.gz"
TAR_URL="https://github.com/filippor/cyan-skillfish-governor/releases/download/v${VERSION}/${TAR}"
sudo apt update || true
sudo apt install -y curl ca-certificates dbus || true
if command -v curl >/dev/null 2>&1 && curl -L --fail -o "$TMPDIR/$DEB" "$DEB_URL"; then
  sudo apt install -y "$TMPDIR/$DEB" || { sudo dpkg -i "$TMPDIR/$DEB" || true; sudo apt -f install -y || true; }
elif command -v curl >/dev/null 2>&1 && curl -L --fail -o "$TMPDIR/$TAR" "$TAR_URL"; then
  echo "WARN: .deb download failed; trying tarball installer."
  cd "$TMPDIR" && tar -xf "$TAR" && cd "cyan-skillfish-governor-smu-v${VERSION}-x86_64-linux" && sudo ./scripts/install.sh
else
  echo "ERROR: could not download cyan-skillfish-governor-smu release assets."
fi
sudo systemctl daemon-reload || true
command -v cyan-skillfish-governor-smu && echo "OK: cyan-skillfish-governor-smu installed. Start it from the app with Enable governor." || echo "WARN: governor is still missing. Check the output above."
'''


    def _comando_instalar_stress(self):
        if self._command_path('pacman'):
            return 'sudo pacman -S --needed stress'
        if self._es_ostree():
            return 'sudo rpm-ostree install --idempotent stress; echo "NOTICE: Bazzite/rpm-ostree requires a reboot before using stress."'
        if self._command_path('apt'):
            return 'sudo apt update && sudo apt install -y stress'
        if self._command_path('dnf'):
            return 'sudo dnf install -y stress'
        if self._command_path('rpm-ostree'):
            return 'sudo rpm-ostree install --idempotent stress; echo "NOTICE: rpm-ostree requires a reboot before using stress."'
        helper = self._command_path('yay') or self._command_path('paru')
        if helper:
            return f'{shlex.quote(helper)} -S --needed stress'
        return ''


    def instalar_stress_cpu(self):
        if self._command_path('stress'):
            return True
        comando = self._comando_instalar_stress()
        if not comando:
            raise RuntimeError('stress was not found and no compatible package manager was detected. Install the stress package manually.')
        self.estado_herramientas_cache = None
        return self._abrir_terminal(f'{comando}; command -v stress && echo "OK: stress available" || echo "ERROR: stress is still not in PATH"', 'Instalar stress para CPU OC')


    def instalar_umr(self):
        if self._command_path('umr'):
            return True
        tools = self.estado_herramientas_bc250()
        comando = self._comando_instalar_umr(tools)
        if not comando:
            raise RuntimeError(
                'UMR is not installed and no compatible package manager was detected. '
                'Use Prepare dependencies to clone bc250-cu-live-manager or install UMR manually.'
            )
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'Instalar UMR')


    def _comando_instalar_umr(self, tools=None):
        tools = tools or self.estado_herramientas_bc250()
        script = tools.get('cu_manager') or ''
        qscript = shlex.quote(script) if script else ''
        helper = tools.get('yay') or tools.get('paru')
        distro = self._os_release()
        os_texto = ' '.join([
            distro.get('ID', ''),
            distro.get('ID_LIKE', ''),
            distro.get('VARIANT_ID', ''),
            distro.get('NAME', ''),
        ]).strip()

        comandos = [
            'set +e',
            'echo "== UMR installer for BC250 Control Center =="',
            f'echo "Detected system: {shlex.quote(os_texto or "unknown")}"',
            'echo "UMR allows bc250-cu-live-manager to read/write AMD registers for the dashboard and 40CU."',
            'echo',
            'if command -v umr >/dev/null 2>&1; then echo "OK: UMR is already installed at $(command -v umr)"; exit 0; fi',
        ]

        if self._command_path('pacman'):
            if helper:
                comandos.append(f'echo "== Arch/Manjaro/CachyOS: installing UMR with {shlex.quote(Path(helper).name)} =="')
                comandos.append(f'{shlex.quote(helper)} -S --needed --noconfirm umr || true')
            comandos.append('if ! command -v umr >/dev/null 2>&1; then echo "== Trying pacman -S umr =="; sudo pacman -S --needed --noconfirm umr || true; fi')
        elif self._es_ostree():
            comandos.append('echo "== rpm-ostree/Bazzite system detected =="')
            comandos.append('sudo rpm-ostree install --idempotent umr || true')
            comandos.append('echo "NOTICE: if rpm-ostree installed UMR, reboot before using 40CU."')
        elif self._command_path('dnf'):
            comandos.append('echo "== Fedora/Nobara: installing UMR with dnf =="')
            comandos.append('sudo dnf install -y umr || true')
        elif self._command_path('apt'):
            comandos.append('echo "== Debian/Ubuntu: trying to install UMR with apt =="')
            comandos.append('sudo apt update || true')
            comandos.append('sudo apt install -y umr || true')

        if qscript:
            comandos.append('if ! command -v umr >/dev/null 2>&1; then echo "== Fallback: using bc250-cu-live-manager install-umr =="; sudo ' + qscript + ' install-umr || true; fi')
        else:
            comandos.append('if ! command -v umr >/dev/null 2>&1; then echo "NOTICE: bc250-cu-live-manager was not found for install-umr fallback."; fi')

        comandos.extend([
            'echo',
            (
                'if command -v umr >/dev/null 2>&1; then '
                'echo "OK: UMR installed at $(command -v umr)"; '
                'umr --version 2>/dev/null || true; '
                'else '
                'echo "UMR is still not in PATH."; '
                'echo "If you are on Bazzite/Fedora Atomic, reboot and reopen the app."; '
                'echo "If you are on Debian/Ubuntu and apt does not provide the package, check UMR documentation or use the live-manager script."; '
                'exit 1; '
                'fi'
            ),
        ])
        return '; '.join(comandos)
