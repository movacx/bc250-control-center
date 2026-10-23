"""SteamOS compute-unit backend and compatibility commands of the dependency repository."""

import shlex
from pathlib import Path

from bc250cc.infrastructure.cu_privileged_backend import (
    STEAMOS_CU_BACKEND,
)
from bc250cc.infrastructure.dependencias_constants import (
    STANDARD_CU_REVIEWED_COMMIT,
    STEAMOS_CU_REVIEWED_COMMIT,
    STEAMOS_FIX_DIRECTORY,
    STEAMOS_FIX_REPOSITORY,
    STEAMOS_FIX_REVIEWED_COMMIT,
    STEAMOS_FIX_SUBDIRECTORY,
)
from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOLS,
)
from bc250cc.infrastructure.governor_conflicts import (
    CYAN_GOVERNOR,
    GOVERNOR_SPECS,
    OBERON_GOVERNOR,
)
from bc250cc.infrastructure.steamos_amdgpu import (
    build_steamos_amdgpu_diagnostic_command,
    build_steamos_compatibility_command,
    gpu_points_above_module_limit,
)
from bc250cc.infrastructure.steamos_amdgpu_backend import (
    STEAMOS_AMDGPU_AUDIO_FIX_ROOT,
    STEAMOS_AMDGPU_BACKEND,
    STEAMOS_AMDGPU_BOOT_CONFIG,
    protected_backend_guard,
    stage_backend_command,
)
from bc250cc.infrastructure.steamos_cu_shell import (
    cu_backend_prepare_command,
    cu_env_shell,
    database_repair_command,
    generic_privileged_backend_stage_command,
    privileged_backend_stage_command,
    service_backend_update_command,
    status_probe_command,
    umr_database_path,
)
from bc250cc.infrastructure.steamos_graphics_runtime import (
    build_steamos_graphics_command,
)
from bc250cc.infrastructure.steamos_shell import wrap_steamos_writable_command


class SteamosDependenciesMixin:
    """Methods of ``DependenciasRepository`` that deal with SteamOS and its CU backend."""

    def _es_steamos(self, os_info=None):
        if os_info is not None:
            texto = ' '.join([
                os_info.get('ID', ''), os_info.get('ID_LIKE', ''), os_info.get('VARIANT_ID', ''),
                os_info.get('NAME', ''), os_info.get('PRETTY_NAME', ''),
            ]).lower()
            return any(token in texto for token in ('steamos', 'steamdeck', 'holo'))
        return self._os_repository().info.family == 'steamos'

    def _cu_script_local(self, carpeta):
        base = self._tool_dir() / carpeta
        nombres = ['bc250-cu-live-manager.sh']
        if carpeta == 'bc250-cu-live-manager-steamos':
            nombres.insert(0, 'bc250-cu-live-manager-bc250.sh')
        for nombre in nombres:
            ruta = base / nombre
            if ruta.exists():
                return str(ruta)
        return ''

    def _cu_script_backend(self, ruta):
        if not ruta:
            return ''
        try:
            path = Path(ruta)
            if not path.is_file():
                return ''
            texto = path.read_text(encoding='utf-8', errors='ignore')[:262144]
        except OSError:
            return ''
        if 'UMR_DATABASE_PATH' in texto and (
            'ensure_umr_database' in texto
            or 'umr_database_default_path' in texto
            or 'bc250-cu-live-manager-SteamOS' in texto
        ):
            return 'steamos'
        if 'BC-250 live CU/WGP manager' in texto and 'enable-wgp' in texto and 'write-service-table' in texto:
            return 'standard'
        return ''

    def _cu_steamos_installed_script(self, preferred=''):
        candidatos = []
        if preferred:
            candidatos.append(Path(preferred))
        candidatos.extend([
            Path('/usr/local/bin/bc250-cu-live-manager'),
            Path('/var/usrlocal/bin/bc250-cu-live-manager'),
            Path('/var/lib/bc250-cu-live-manager/umr/bc250-cu-live-manager'),
        ])
        vistos = set()
        for ruta in candidatos:
            try:
                resolved = ruta.expanduser().resolve()
            except OSError:
                resolved = ruta.expanduser()
            if str(resolved) in vistos:
                continue
            vistos.add(str(resolved))
            if self._cu_script_backend(resolved) == 'steamos':
                return str(resolved)
        return ''

    def _cu_manager_spec(self, os_repository=None):
        os_repository = os_repository or self._os_repository()
        is_steamos = os_repository.info.family == 'steamos'
        folder = 'bc250-cu-live-manager-steamos' if is_steamos else 'bc250-cu-live-manager'
        repository = (
            EXTERNAL_TOOLS['cu_manager_steamos'].upstream
            if is_steamos
            else EXTERNAL_TOOLS['cu_manager_standard'].upstream
        )
        destination = self._tool_dir() / folder
        upstream_script = destination / 'bc250-cu-live-manager.sh'
        runtime_script = (
            destination / 'bc250-cu-live-manager-bc250.sh'
            if is_steamos
            else upstream_script
        )
        return {
            'is_steamos': is_steamos,
            'folder': folder,
            'repository': repository,
            'reviewed_commit': (
                STEAMOS_CU_REVIEWED_COMMIT
                if is_steamos else STANDARD_CU_REVIEWED_COMMIT
            ),
            'destination': destination,
            'upstream_script': upstream_script,
            'script': runtime_script,
        }

    def _steamos_cu_backend_prepare_command(self, spec):
        patcher = Path(__file__).resolve().parents[3] / 'scripts' / 'system' / 'prepare-steamos-cu-backend.py'
        return cu_backend_prepare_command(spec, patcher)

    def _steamos_umr_database_path(self):
        # SteamOS /var is only a few hundred MiB on many images. The complete
        # UMR database is kept in the user's large /home-backed data directory
        # so atomic refreshes cannot fill /var and corrupt cyan_skillfish.asic.
        return umr_database_path(self._tool_dir())


    def _steamos_cu_env_shell(self):
        repair = Path(__file__).resolve().parents[3] / 'scripts' / 'system' / 'repair-steamos-umr-database.py'
        return cu_env_shell(self._steamos_umr_database_path(), repair)


    def _steamos_umr_database_repair_command(self, check_only=False):
        repair = Path(__file__).resolve().parents[3] / 'scripts' / 'system' / 'repair-steamos-umr-database.py'
        return database_repair_command(
            self._steamos_umr_database_path(), repair, check_only=check_only
        )


    def _steamos_cu_service_backend_update_command(self, script):
        _ = script
        return service_backend_update_command(STEAMOS_CU_BACKEND)

    def _steamos_cu_privileged_backend_stage_command(self, script):
        return privileged_backend_stage_command(script, self._steamos_umr_database_path())

    def _generic_cu_privileged_backend_stage_command(self, script):
        return generic_privileged_backend_stage_command(script)


    def _steamos_cu_status_probe_command(self, script):
        # Validate the exact protected executable used by the desktop Polkit
        # helper.  Probing the user-owned F5GO checkout can succeed while a
        # stale /usr/libexec copy still makes every GUI action fail.
        _ = script
        return status_probe_command(
            STEAMOS_CU_BACKEND,
            environment_shell=self._steamos_cu_env_shell(),
            check_database_command=self._steamos_umr_database_repair_command(check_only=True),
        )

    def _steamos_compatibility_stage_command(self, *, install=True):
        """Stage/check, or explicitly install, the audited SteamOS kernel fixes.

        Generic dependency preparation only clones the reviewed SteamOS toolkit
        and reports status. ``install=True`` is reserved for the explicit
        compatibility action/Health Repair because it can rebuild amdgpu,
        regenerate initramfs and require a reboot.

        SteamOS can regenerate its GRUB file as a side effect of the final
        mkinitcpio pass. The reviewed upstream installer writes/validates the
        scheduler policy *before* that pass, so a good module can be left with
        a missing amdgpu.sched_policy=2 afterwards. Control Center therefore
        reapplies the upstream boot-config transaction after mkinitcpio and can
        repair that policy alone without rebuilding an already verified module.
        """
        destination = self._tool_dir() / STEAMOS_FIX_DIRECTORY
        script = STEAMOS_AMDGPU_BACKEND
        boot_config = STEAMOS_AMDGPU_BOOT_CONFIG
        # The toolkit is built exactly as reviewed. Earlier builds staged an
        # app-owned overlay that widened the module's GPU clock telemetry to
        # 2400 MHz; the governor editors now keep the GPU within the module's
        # own 2230 MHz instead (``gpu_frequency_ceiling``).
        #
        # Upstream's patch-driver is intentionally a normal-user build
        # workflow: it creates its lock, dependency cache and kernel tree next
        # to the script.  The protected /usr/libexec stage must therefore be
        # used only for root-facing validation/install scripts.  Build in the
        # pinned ResourceTools checkout, then copy only the two attested build
        # products into the protected stage before invoking its root-owned
        # installer.
        user_audio_root = destination / STEAMOS_FIX_SUBDIRECTORY
        q_user_audio = shlex.quote(str(user_audio_root))
        q_protected_audio = shlex.quote(str(STEAMOS_AMDGPU_AUDIO_FIX_ROOT))
        build_install_command = '; '.join((
            f'sudo /usr/bin/bash {q_protected_audio}/ensure-build-prereqs.sh',
            'echo; echo "== Downloading exact Valve kernel sources and build dependencies =="; '
            'echo "[INFO] This step can remain quiet for several minutes while Git is working. Do not close this window; the process is still running."',
            f'/usr/bin/bash {q_user_audio}/fetch-sources.sh',
            'echo "[OK] Kernel sources and build dependencies are ready."; echo; '
            'echo "== Building the BC250 AMDGPU module =="; '
            'echo "[INFO] Configuration and compilation can take a while. Do not close this window; compiler output will appear as work progresses."',
            # build.sh exits 75 when the kernel tree is not in a state it
            # recognises, typically one patched by an earlier toolkit
            # revision. Like upstream's patch-driver, clean the tree (cached
            # downloads are kept) and build once more.
            f'bc250_build_rc=0; /usr/bin/bash {q_user_audio}/build.sh || bc250_build_rc=$?',
            'if [ "$bc250_build_rc" = 75 ]; then '
            'echo "[INFO] The kernel tree was prepared by an earlier toolkit revision; cleaning it and building again. Cached downloads are kept."; '
            f'/usr/bin/bash {q_user_audio}/clean.sh; '
            f'/usr/bin/bash {q_user_audio}/fetch-sources.sh; '
            f'/usr/bin/bash {q_user_audio}/build.sh; '
            'elif [ "$bc250_build_rc" != 0 ]; then exit "$bc250_build_rc"; fi',
            f'for artifact in amdgpu.ko.zst amdgpu.gfx1013.attestation; do '
            f'source_artifact={q_user_audio}/$artifact; '
            'test -f "$source_artifact" && test ! -L "$source_artifact" && '
            '[ "$(stat -c %u "$source_artifact")" = "$(id -u)" ] && '
            '! find "$source_artifact" -prune -perm /022 -print -quit | grep -q . || '
            '{ echo "ERROR: SteamOS build produced an unsafe artifact: $source_artifact"; exit 38; }; '
            f'sudo install -o root -g root -m 0644 "$source_artifact" {q_protected_audio}/$artifact; '
            'done',
            f'sudo /usr/bin/bash {q_protected_audio}/install.sh',
        ))
        if install:
            checkout_command = self._clone_or_update_commit_command(
                STEAMOS_FIX_REPOSITORY, destination, STEAMOS_FIX_REVIEWED_COMMIT
            ) + '; ' + wrap_steamos_writable_command(
                stage_backend_command(
                    destination,
                    STEAMOS_FIX_REVIEWED_COMMIT,
                    subtree=STEAMOS_FIX_SUBDIRECTORY,
                ),
                family='steamos',
            )
        else:
            # Diagnostics must never clone, stage or invoke user-writable
            # ResourceTools. They inspect only a previously staged runtime.
            checkout_command = ':'
        return build_steamos_compatibility_command(
            script=script,
            boot_config=boot_config,
            checkout_command=checkout_command,
            install=install,
            module_install_command=build_install_command if install else '',
            backend_guard=protected_backend_guard(
                reviewed_revision=STEAMOS_FIX_REVIEWED_COMMIT
            ),
        )


    def _steamos_module_frequency_blocker(self):
        return gpu_points_above_module_limit(
            cyan_config=Path(GOVERNOR_SPECS[CYAN_GOVERNOR]['config_path']),
            oberon_config=Path(GOVERNOR_SPECS[OBERON_GOVERNOR]['config_path']),
        )

    def preparar_compatibilidad_steamos(self):
        os_repository = self._os_repository()
        if os_repository.info.family != 'steamos':
            raise RuntimeError('The dedicated SteamOS compatibility workflow is available only on SteamOS.')
        blocker = self._steamos_module_frequency_blocker()
        if blocker:
            raise RuntimeError(blocker)
        command = self._join_shell_commands((
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            self._steamos_compatibility_stage_command(install=True),
        ))
        # The reviewed upstream patch-driver owns its privileged windows: its
        # prerequisite installer and amdgpu installer both restore SteamOS
        # read-only protection with EXIT traps.  Do not keep /usr writable
        # during the potentially long kernel build.
        self.estado_herramientas_cache = None
        return self._abrir_terminal(command, 'Preparar compatibilidad SteamOS BC250')

    def gestionar_graficos_steamos(self, action):
        """Install, verify or remove the matched SteamOS RADV/FSR4 stage."""
        os_repository = self._os_repository()
        if os_repository.info.family != 'steamos':
            raise RuntimeError(
                'The dedicated SteamOS graphics workflow is available only on SteamOS.'
            )
        action = str(action or '').strip().lower()
        destination = self._tool_dir() / STEAMOS_FIX_DIRECTORY
        if action == 'status':
            checkout_command = ':'
        else:
            checkout_command = self._clone_or_update_commit_command(
                STEAMOS_FIX_REPOSITORY,
                destination,
                STEAMOS_FIX_REVIEWED_COMMIT,
            ) + '; ' + wrap_steamos_writable_command(
                stage_backend_command(
                    destination,
                    STEAMOS_FIX_REVIEWED_COMMIT,
                    subtree=STEAMOS_FIX_SUBDIRECTORY,
                ),
                family='steamos',
            )
        command = self._join_shell_commands((
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            build_steamos_graphics_command(
                action,
                checkout_command=checkout_command,
                backend_guard=protected_backend_guard(
                    reviewed_revision=STEAMOS_FIX_REVIEWED_COMMIT
                ),
            ),
        ))
        self.estado_herramientas_cache = None
        titles = {
            'status': 'Estado de gráficos SteamOS BC250',
            'install': 'Instalar Mesa RADV SteamOS BC250',
            'install-fsr4': 'Instalar FSR4 SteamOS BC250',
            'uninstall': 'Desinstalar Mesa RADV SteamOS BC250',
            'uninstall-fsr4': 'Desinstalar FSR4 SteamOS BC250',
        }
        if action not in titles:
            raise ValueError(f'Unsupported SteamOS graphics action: {action}')
        return self._abrir_terminal(command, titles[action])

    def diagnostico_steamos(self):
        """Run Control Center's native SteamOS checks without toolkit ownership."""
        os_repository = self._os_repository()
        if os_repository.info.family != 'steamos':
            raise RuntimeError('SteamOS toolkit diagnostics are available only on SteamOS.')
        patch_status = STEAMOS_AMDGPU_BACKEND
        cu_spec = self._cu_manager_spec(os_repository)
        cu_script = cu_spec['script']
        command = self._join_shell_commands((
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'echo "== Native BC250 Control Center SteamOS diagnostics =="',
            'echo "[INFO] Community toolkits are references; this report validates Control Center-owned paths and services."',
            'echo "== Active kernel and scheduler =="',
            'printf "Kernel: %s\\n" "$(uname -r)"',
            build_steamos_amdgpu_diagnostic_command(
                script=patch_status,
                backend_guard=protected_backend_guard(
                    reviewed_revision=STEAMOS_FIX_REVIEWED_COMMIT
                ),
            ),
            'echo "== Control Center services =="',
            'for unit in cyan-skillfish-governor-smu.service bc250-cu-live-manager.service nct6687-load.service bc250-smu-oc.service; do enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"; active="$(systemctl is-active "$unit" 2>/dev/null || true)"; printf "%s: enabled=%s active=%s\\n" "$unit" "${enabled:-not-found}" "${active:-not-found}"; done',
            'echo "== Control Center UMR / CU backend =="',
            f'test -x {shlex.quote(str(cu_script))} || {{ echo "ERROR: Control Center SteamOS CU backend is missing"; exit 39; }}',
            self._steamos_cu_status_probe_command(cu_script),
            'echo "== NCT hardware monitor =="',
            'if [ -r /sys/class/hwmon ]; then for node in /sys/class/hwmon/hwmon*/name; do [ -r "$node" ] && printf "%s: %s\\n" "${node%/name}" "$(cat "$node")"; done; fi',
            'echo "[OK] Native SteamOS diagnostics completed; no system setting was changed."',
        ))
        return self._abrir_terminal(command, 'Diagnóstico SteamOS BC250')

    # Compatibility alias for controllers from builds that briefly exposed the
    # upstream-oriented name. The implementation is fully native.
    diagnostico_toolkit_steamos = diagnostico_steamos
