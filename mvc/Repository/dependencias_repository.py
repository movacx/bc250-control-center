from pathlib import Path
import shlex
import shutil
import time

from mvc.Repository.Os_repository import create_os_repository


class DependenciasRepository:
    def _os_repository(self):
        return create_os_repository(self)

    def estado_herramientas_bc250(self):
        ahora = time.monotonic()
        if self.estado_herramientas_cache is not None and ahora - self.estado_herramientas_cache_time < 10:
            return dict(self.estado_herramientas_cache)

        os_repository = self._os_repository()
        os_info = os_repository.info
        is_steamos = os_info.family == 'steamos'
        cu_standard = self._command_path('bc250-cu-live-manager') or self._cu_script_local('bc250-cu-live-manager')
        encontrado = self._buscar_archivo('bc250-cu-live-manager.sh')
        if encontrado and 'bc250-cu-live-manager-steamos' not in encontrado and not cu_standard:
            cu_standard = encontrado
        cu_steamos = self._cu_script_local('bc250-cu-live-manager-steamos')
        standard_repo = str(Path(cu_standard).parent) if cu_standard and Path(cu_standard).exists() else self._buscar_directorio_con('bc250-cu-live-manager.sh', 'bc250-cu-live-manager')
        steamos_repo = str(Path(cu_steamos).parent) if cu_steamos and Path(cu_steamos).exists() else ''

        standard_exists = bool(
            cu_standard and (Path(cu_standard).exists() or shutil.which(Path(cu_standard).name))
        )
        steamos_exists = bool(cu_steamos and Path(cu_steamos).exists())
        expected_steamos_repo = self._tool_dir() / 'bc250-cu-live-manager-steamos'

        if is_steamos:
            # SteamOS is an exceptional backend: the normal WinnieLV manager is
            # intentionally never selected, even when it is installed globally
            # or left behind by an older application version.  Its UMR database
            # cannot be assumed to work with the SteamOS/Neptune environment.
            cu_manager = cu_steamos if steamos_exists else ''
            cu_kind = 'F5GO/bc250-cu-live-manager-SteamOS'
            cu_backend = 'steamos'
            cu_repo = steamos_repo or str(expected_steamos_repo)
            cu_repo_url = 'https://github.com/F5GO/bc250-cu-live-manager-SteamOS'
            if steamos_exists:
                cu_warning = ''
            elif standard_exists:
                cu_warning = (
                    'SteamOS requires the F5GO SteamOS 40CU backend. A standard WinnieLV installation '
                    'was detected and has been ignored to prevent incompatible register operations. '
                    'Use Prepare dependencies or Prepare Live Manager before using any 40CU action.'
                )
            else:
                cu_warning = (
                    'SteamOS requires the F5GO SteamOS 40CU backend. Use Prepare dependencies or '
                    'Prepare Live Manager before using any 40CU action.'
                )
        else:
            cu_manager = cu_standard
            cu_kind = 'WinnieLV/bc250-cu-live-manager' if standard_exists else ''
            cu_backend = 'standard'
            cu_repo = standard_repo
            cu_repo_url = 'https://github.com/WinnieLV/bc250-cu-live-manager'
            cu_warning = ''

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
            'cu_manager_backend': cu_backend,
            'cu_manager_repo_url': cu_repo_url,
            'cu_manager_warning': cu_warning,
            'cu_manager_exists': steamos_exists if is_steamos else standard_exists,
            'cu_manager_required_backend': 'steamos' if is_steamos else 'standard',
            'cu_manager_blocked': bool(is_steamos and not steamos_exists),
            'cu_manager_wrong_backend_present': bool(is_steamos and standard_exists),
            'cu_manager_standard_path': cu_standard,
            'cu_manager_steamos_path': cu_steamos,
            'cu_manager_standard_exists': standard_exists,
            'cu_manager_steamos_exists': steamos_exists,
            'cu_steamos_umr_database': '/var/lib/bc250-cu-live-manager/umr/database',
            'is_steamos': is_steamos,
            'os_id': os_info.distro_id,
            'os_like': ' '.join(os_info.id_like),
            'os_variant': os_info.variant_id,
            'os_family': os_info.family,
            'os_label': os_info.label,
            'os_immutable': os_info.immutable,
            'cu_live_repo_path': cu_repo,
            'cu_repo_path': cu_repo,
            'cu_map_repo_path': '',
            'cu_map_script': '',
            'smu_oc_path': smu_path,
            'smu_oc_exists': bool(smu_path and Path(smu_path).exists()),
            'tools_dir': str(self._tool_dir()),
        }
        self.estado_herramientas_cache = resultado
        self.estado_herramientas_cache_time = ahora
        return dict(resultado)

    def _es_steamos(self, os_info=None):
        if os_info is not None:
            texto = ' '.join([
                os_info.get('ID', ''), os_info.get('ID_LIKE', ''), os_info.get('VARIANT_ID', ''),
                os_info.get('NAME', ''), os_info.get('PRETTY_NAME', ''),
            ]).lower()
            return any(token in texto for token in ('steamos', 'steamdeck', 'holo'))
        return self._os_repository().info.family == 'steamos'

    def _cu_script_local(self, carpeta):
        ruta = self._tool_dir() / carpeta / 'bc250-cu-live-manager.sh'
        return str(ruta) if ruta.exists() else ''

    def _cu_manager_spec(self, os_repository=None):
        os_repository = os_repository or self._os_repository()
        is_steamos = os_repository.info.family == 'steamos'
        folder = 'bc250-cu-live-manager-steamos' if is_steamos else 'bc250-cu-live-manager'
        repository = (
            'https://github.com/F5GO/bc250-cu-live-manager-SteamOS'
            if is_steamos
            else 'https://github.com/WinnieLV/bc250-cu-live-manager'
        )
        destination = self._tool_dir() / folder
        return {
            'is_steamos': is_steamos,
            'folder': folder,
            'repository': repository,
            'destination': destination,
            'script': destination / 'bc250-cu-live-manager.sh',
        }

    @staticmethod
    def _accept_reboot_required(command, message):
        """Treat the rpm-ostree pending-deployment exit code as success."""
        return (
            'bc250_step_status=0; set +e; '
            + command
            + '; bc250_step_status=$?; set -e; '
            + 'if [ "$bc250_step_status" -eq 20 ]; then '
            + 'BC250_REBOOT_REQUIRED=1; echo '
            + shlex.quote(message)
            + '; elif [ "$bc250_step_status" -ne 0 ]; then exit "$bc250_step_status"; fi'
        )

    def instalar_governor(self):
        if self._command_path('cyan-skillfish-governor-smu'):
            return True
        comando = self._os_repository().install_governor_command()
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'Instalar governor')

    def instalar_cpu_oc(self):
        tools = self.estado_herramientas_bc250()
        if tools['bc250_detect']:
            return True
        if tools['smu_oc_exists']:
            path = shlex.quote(tools['smu_oc_path'])
            cmd = f'echo "OK: bc250_smu_oc repository found at {path}"; echo "The app runs bc250_detect.py directly to avoid PEP 668 conflicts."'
            return self._abrir_terminal(cmd, 'Preparar bc250_smu_oc')

        os_repository = self._os_repository()
        destination = self._tool_dir() / 'bc250_smu_oc'
        destination.parent.mkdir(parents=True, exist_ok=True)
        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'echo "== Preparing bc250_smu_oc =="',
        ]
        if os_repository.info.family == 'bazzite':
            commands.append(
                self._clone_or_update_with_archive_command(
                    'https://github.com/bc250-collective/bc250_smu_oc', destination
                )
            )
        else:
            runtime = os_repository.prepare_dependencies_command('runtime')
            commands.append(f'command -v git >/dev/null 2>&1 || {{ {runtime}; }}')
            commands.append(self._clone_or_update_command('https://github.com/bc250-collective/bc250_smu_oc', destination))
        commands.extend([
            f'test -f {shlex.quote(str(destination / "bc250_detect.py"))} || {{ echo "ERROR: bc250_detect.py was not found"; exit 1; }}',
            f'echo "OK: bc250_smu_oc is ready at {shlex.quote(str(destination))}"',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal('; '.join(commands), 'Preparar bc250_smu_oc')

    def instalar_cu_manager(self):
        tools = self.estado_herramientas_bc250()
        os_repository = self._os_repository()
        spec = self._cu_manager_spec(os_repository)
        if spec['is_steamos'] and tools.get('cu_manager_steamos_exists'):
            return True
        if not spec['is_steamos'] and tools['cu_manager_exists']:
            return True

        destination = spec['destination']
        script = spec['script']
        destination.parent.mkdir(parents=True, exist_ok=True)
        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'echo "== Preparing bc250-cu-live-manager =="',
        ]
        if os_repository.info.family == 'bazzite':
            commands.append(self._clone_or_update_with_archive_command(spec['repository'], destination))
        else:
            runtime = os_repository.prepare_dependencies_command('runtime')
            commands.append(f'command -v git >/dev/null 2>&1 || {{ {runtime}; }}')
            commands.append(self._clone_or_update_command(spec['repository'], destination))
        commands.extend([
            f'chmod 0755 {shlex.quote(str(script))}',
            f'test -x {shlex.quote(str(script))} || {{ echo "ERROR: bc250-cu-live-manager.sh was not found"; exit 1; }}',
            f'echo "OK: 40CU manager is ready at {shlex.quote(str(script))}"',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal('; '.join(commands), 'Preparar bc250-cu-live-manager')

    def instalar_dependencias_bc250(self):
        os_repository = self._os_repository()
        self.estado_herramientas_bc250()
        self._tool_dir().mkdir(parents=True, exist_ok=True)
        paths = self.config_paths()
        cpu_destination = self._tool_dir() / 'bc250_smu_oc'
        cu_spec = self._cu_manager_spec(os_repository)
        cu_destination = cu_spec['destination']
        cu_script = cu_spec['script']
        immutable_pending = os_repository.info.family == 'bazzite'

        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'BC250_REBOOT_REQUIRED=0',
            f'mkdir -p {shlex.quote(str(self._tool_dir()))}',
            'echo "== Preparing BC250 dependencies =="',
            f"printf '%s\\n' {shlex.quote(f'Detected strategy: {os_repository.info.family} ({os_repository.info.label})')}",
        ]

        if immutable_pending:
            commands.extend([
                'echo "== Preparing BC250 user-space tools before the rpm-ostree reboot =="',
                self._clone_or_update_with_archive_command(
                    'https://github.com/bc250-collective/bc250_smu_oc', cpu_destination
                ),
                f'test -f {shlex.quote(str(cpu_destination / "bc250_detect.py"))} || {{ echo "ERROR: bc250_detect.py is missing"; exit 30; }}',
                self._clone_or_update_with_archive_command(cu_spec['repository'], cu_destination),
                f'chmod 0755 {shlex.quote(str(cu_script))}',
                f'test -x {shlex.quote(str(cu_script))} || {{ echo "ERROR: 40CU manager script is missing"; exit 31; }}',
                self._accept_reboot_required(
                    os_repository.prepare_dependencies_command('all', cu_manager_script=str(cu_script)),
                    'The Bazzite deployment was staged successfully. Reboot once to activate the host packages.',
                ),
            ])
        else:
            commands.extend([
                os_repository.prepare_dependencies_command('runtime'),
                os_repository.prepare_dependencies_command('governor'),
                'command -v git >/dev/null 2>&1 || { echo "ERROR: git is unavailable after dependency preparation"; exit 29; }',
                'echo "== Preparing bc250_smu_oc source =="',
                self._clone_or_update_command('https://github.com/bc250-collective/bc250_smu_oc', cpu_destination),
                f'test -f {shlex.quote(str(cpu_destination / "bc250_detect.py"))} || {{ echo "ERROR: bc250_detect.py is missing"; exit 30; }}',
                'echo "== Preparing 40CU live manager =="',
                self._clone_or_update_command(cu_spec['repository'], cu_destination),
                f'chmod 0755 {shlex.quote(str(cu_script))}',
                f'test -x {shlex.quote(str(cu_script))} || {{ echo "ERROR: 40CU manager script is missing"; exit 31; }}',
                os_repository.install_umr_command(str(cu_script)),
                'command -v umr >/dev/null 2>&1 || { echo "ERROR: UMR is still unavailable"; exit 32; }',
                'command -v cyan-skillfish-governor-smu >/dev/null 2>&1 || { echo "ERROR: cyan-skillfish-governor-smu is unavailable"; exit 33; }',
            ])

        commands.extend([
            'echo',
            'echo "== BC250 dependency verification =="',
            'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then echo "PENDING: host packages will be verified after reboot."; else for cmd in python3 git stress lspci sensors pkexec; do command -v "$cmd" >/dev/null 2>&1 && echo "OK: $cmd -> $(command -v "$cmd")" || { echo "ERROR: missing $cmd"; exit 34; }; done; python3 -c "import PyQt6, psutil" || { echo "ERROR: Python GUI dependencies are unavailable"; exit 35; }; fi',
            f"printf '%s\\n' {shlex.quote(f'Tools: {self._tool_dir()}')}",
            f"printf '%s\\n' {shlex.quote(f'Config: {paths.get("config", "")}')}",
            f"printf '%s\\n' {shlex.quote(f'Profiles: {paths.get("perfiles", "")}')}",
            f"printf '%s\\n' {shlex.quote(f'History: {paths.get("historial", "")}')}",
            f"printf '%s\\n' {shlex.quote(f'CPU OC repo: {cpu_destination}')}",
            f"printf '%s\\n' {shlex.quote(f'40CU repo: {cu_destination}')}",
            'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then echo "== Finished: reboot required =="; else echo "== Finished successfully =="; fi',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal('; '.join(commands), 'Preparar dependencias BC250')

    def _clone_or_update_with_archive_command(self, repository_url, destination, branch='main'):
        qdest = shlex.quote(str(destination))
        qparent = shlex.quote(str(destination.parent))
        qurl = shlex.quote(repository_url)
        archive_url = shlex.quote(f'{repository_url.rstrip("/")}/archive/refs/heads/{branch}.tar.gz')
        return (
            f'mkdir -p {qparent}; '
            f'if command -v git >/dev/null 2>&1; then '
            f'if [ -d {qdest}/.git ]; then git -C {qdest} pull --ff-only; '
            f'else rm -rf {qdest}; git clone --depth 1 {qurl} {qdest}; fi; '
            f'elif command -v tar >/dev/null 2>&1 && (command -v curl >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1); then '
            f'tmpdir="$(mktemp -d)"; '
            f"if command -v curl >/dev/null 2>&1; then curl --fail --location --retry 3 {archive_url} -o \"$tmpdir/source.tar.gz\"; else python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' {archive_url} \"$tmpdir/source.tar.gz\"; fi; "
            f'rm -rf {qdest}; mkdir -p {qdest}; '
            f'tar -xzf "$tmpdir/source.tar.gz" --strip-components=1 -C {qdest}; '
            f"printf '%s\\n' {qurl} > {qdest}/.bc250-source-url; "
            f'rm -rf "$tmpdir"; '
            f'else echo "ERROR: git or tar with curl/python3 is required to fetch {repository_url}"; exit 29; fi'
        )

    def _clone_or_update_command(self, repository_url, destination):
        qdest = shlex.quote(str(destination))
        qparent = shlex.quote(str(destination.parent))
        qurl = shlex.quote(repository_url)
        return (
            f'mkdir -p {qparent}; '
            f'if [ -d {qdest}/.git ]; then '
            f'git -C {qdest} pull --ff-only; '
            f'else rm -rf {qdest}; git clone --depth 1 {qurl} {qdest}; fi'
        )

    def _comando_instalar_governor_smu(self):
        return self._os_repository().install_governor_command()

    def _comando_instalar_stress(self):
        return self._os_repository().install_stress_command()

    def instalar_stress_cpu(self):
        if self._command_path('stress'):
            return True
        comando = self._comando_instalar_stress()
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'Instalar stress para CPU OC')

    def instalar_umr(self):
        if self._command_path('umr'):
            return True
        os_repository = self._os_repository()
        spec = self._cu_manager_spec(os_repository)
        destination = spec['destination']
        script = spec['script']
        destination.parent.mkdir(parents=True, exist_ok=True)

        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'BC250_REBOOT_REQUIRED=0',
            'echo "== Preparing UMR for BC250 =="',
        ]
        if os_repository.info.family == 'bazzite':
            commands.extend([
                self._clone_or_update_with_archive_command(spec['repository'], destination),
                f'chmod 0755 {shlex.quote(str(script))}',
                f'test -x {shlex.quote(str(script))} || {{ echo "ERROR: 40CU fallback helper is missing"; exit 31; }}',
                self._accept_reboot_required(
                    os_repository.install_umr_command(str(script)),
                    'UMR was staged in a new Bazzite deployment. Reboot once to activate it.',
                ),
                'if [ "$BC250_REBOOT_REQUIRED" = "0" ]; then command -v umr >/dev/null 2>&1 || { echo "ERROR: UMR is still unavailable"; exit 32; }; fi',
            ])
        else:
            runtime = os_repository.prepare_dependencies_command('runtime')
            commands.extend([
                f'command -v git >/dev/null 2>&1 || {{ {runtime}; }}',
                self._clone_or_update_command(spec['repository'], destination),
                f'chmod 0755 {shlex.quote(str(script))}',
                f'test -x {shlex.quote(str(script))} || {{ echo "ERROR: 40CU fallback helper is missing"; exit 31; }}',
                os_repository.install_umr_command(str(script)),
                'command -v umr >/dev/null 2>&1 || { echo "ERROR: UMR is still unavailable"; exit 32; }',
            ])
        commands.append('if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then echo "== UMR staged; reboot required =="; else echo "== UMR installation verified =="; fi')
        self.estado_herramientas_cache = None
        return self._abrir_terminal('; '.join(commands), 'Instalar UMR')

    def _comando_instalar_umr(self, tools=None):
        tools = tools or self.estado_herramientas_bc250()
        script = tools.get('cu_manager') or ''
        if tools.get('is_steamos') and tools.get('cu_manager_steamos_path'):
            script = tools.get('cu_manager_steamos_path') or script
        return self._os_repository().install_umr_command(script)
