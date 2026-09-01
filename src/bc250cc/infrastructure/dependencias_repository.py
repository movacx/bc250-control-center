import importlib.util
import platform
import shlex
import shutil
import subprocess
import time
from contextlib import suppress
from copy import deepcopy
from pathlib import Path

from bc250cc.application.preparation.component_engine import (
    component_capabilities,
    normalize_components,
    unavailable_components,
)
from bc250cc.infrastructure.bazzite_async_compute import (
    build_bazzite_async_compute_command,
    probe_bazzite_async_compute,
)
from bc250cc.infrastructure.bazzite_memory_tuning import (
    build_bazzite_memory_tuning_command,
)
from bc250cc.infrastructure.bc250_fsr4 import (
    build_fsr4_v3_bazzite_install_command,
    build_fsr4_v3_debian_install_command,
    build_fsr4_v3_fedora44_install_command,
    build_fsr4_v3_install_command,
    build_fsr4_v3_uninstall_command,
    fsr4_runtime_state,
)
from bc250cc.infrastructure.cachyos_bc250_kernel import (
    build_cachyos_bc250_kernel_command,
    masta_bc250_stack_state,
    masta_bc250_stack_supported,
)
from bc250cc.infrastructure.cu_privileged_backend import (
    GENERIC_CU_BACKEND,
    STEAMOS_CU_BACKEND,
    generic_cu_backend_status,
    steamos_cu_backend_status,
)
from bc250cc.infrastructure.decky_quick_access import (
    build_bazzite_decky_bootstrap_command,
    build_decky_bootstrap_command,
    build_plugin_install_command,
)
from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOLS,
    GitCheckoutReader,
    build_external_checkout_inventory,
)
from bc250cc.infrastructure.external_tools.quick_access_inventory import (
    quick_access_inventory,
)
from bc250cc.infrastructure.fedora_gfx1013 import build_fedora_gfx1013_command
from bc250cc.infrastructure.gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_REVIEWED_VERSION,
    GFX1013_UPSTREAM,
    STEAMOS_GFX1013_SAFE_RADV_REFERENCE,
    STEAMOS_GFX1013_SAFE_RADV_REVIEWED_COMMIT,
    STEAMOS_GFX1013_SAFE_RADV_VERSION,
    STEAMOS_REVIEWED_DRYHOPPED_COMMIT,
    classify_gfx1013_support,
)
from bc250cc.infrastructure.governor_conflicts import (
    CYAN_GOVERNOR,
    GOVERNOR_SPECS,
    OBERON_GOVERNOR,
    detect_incompatible_governors,
    ensure_no_incompatible_governors,
    normalize_governor_preference,
    resolve_gpu_governor,
)
from bc250cc.infrastructure.governor_install_shell import (
    cyan_runtime_verification_command,
    cyan_upstream_runtime_command,
    oberon_install_command,
)
from bc250cc.infrastructure.memory_runtime import read_memory_runtime_state
from bc250cc.infrastructure.preparation_workflow import (
    PreparationContext,
    build_preparation_command,
)
from bc250cc.infrastructure.source_checkout import (
    clone_or_update,
    clone_or_update_branch,
    clone_or_update_commit,
    clone_or_update_commit_with_archive,
    clone_or_update_with_archive,
)
from bc250cc.infrastructure.steamos_amdgpu import (
    build_steamos_amdgpu_diagnostic_command,
    build_steamos_compatibility_command,
)
from bc250cc.infrastructure.steamos_amdgpu_backend import (
    STEAMOS_AMDGPU_BACKEND,
    STEAMOS_AMDGPU_BACKEND_ROOT,
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
    probe_steamos_graphics_runtime,
)
from bc250cc.infrastructure.steamos_shell import wrap_steamos_writable_command
from bc250cc.infrastructure.system_setup import command as system_setup_command
from bc250cc.infrastructure.system_setup import inventory as system_setup_inventory
from bc250cc.infrastructure.tool_inventory import (
    mark_component_installation,
    select_cu_backend,
)
from bc250cc.platform.init.services import detect_init_manager, openrc_preflight
from bc250cc.platform.packages.strategies import create_os_repository
from bc250cc.platform.packages.strategies.detector import read_os_release

CORE_UNLOCK_REPOSITORY = EXTERNAL_TOOLS["core_unlock"].upstream
CORE_UNLOCK_DIRECTORY = "bc250-core-unlock"
CORE_UNLOCK_SCRIPT = "bc250-unlock-cores.py"
CYAN_GOVERNOR_REPOSITORY = EXTERNAL_TOOLS["cyan_smu"].upstream
CYAN_GOVERNOR_DIRECTORY = "cyan-skillfish-governor-smu"
CYAN_GOVERNOR_BRANCH = "smu"
STEAMOS_FIX_REPOSITORY = EXTERNAL_TOOLS["steamos_amdgpu"].upstream
STEAMOS_FIX_REVIEWED_COMMIT = EXTERNAL_TOOLS["steamos_amdgpu"].reviewed_revision
STEAMOS_FIX_DIRECTORY = "bc250-steamos"
STEAMOS_FIX_SUBDIRECTORY = "bc250-audio-fix"
STEAMOS_FIX_SCRIPT = "patch-driver.sh"
STEAMOS_CU_REVIEWED_COMMIT = EXTERNAL_TOOLS["cu_manager_steamos"].reviewed_revision
STANDARD_CU_REVIEWED_COMMIT = EXTERNAL_TOOLS["cu_manager_standard"].reviewed_revision
STEAMOS_SMU_OC_REVIEWED_COMMIT = EXTERNAL_TOOLS["cpu_smu_oc"].reviewed_revision
STEAMOS_CORE_UNLOCK_REVIEWED_COMMIT = EXTERNAL_TOOLS["core_unlock"].reviewed_revision
STEAMOS_CYAN_REVIEWED_COMMIT = EXTERNAL_TOOLS["cyan_smu"].reviewed_revision
CYAN_REVIEWED_RELEASE = "v0.4.12"
# Retain the former SteamOS-specific spelling for callers that still import it.
# The executable release is now fixed on every supported distribution.
STEAMOS_CYAN_REVIEWED_RELEASE = CYAN_REVIEWED_RELEASE
OBERON_REPOSITORY = EXTERNAL_TOOLS["oberon_governor"].upstream
OBERON_REVIEWED_COMMIT = EXTERNAL_TOOLS["oberon_governor"].reviewed_revision
OBERON_YAML_CPP_REVIEWED_COMMIT = "f7320141120f720aecc4c32be25586e7da9eb978"
OBERON_DIRECTORY = "oberon-governor"


class DependenciasRepository:
    @staticmethod
    def _join_shell_commands(commands):
        """Join complete top-level shell fragments without producing `;;`.

        Repository helpers may return a complete compound command ending in `fi;`,
        `done;`, or `esac;`.  Appending another top-level separator blindly turns
        those into invalid Bash such as `fi;; echo ...`.  Normalize only the final
        top-level separator; internal case-arm `;;` tokens are left untouched.
        """
        parts = []
        for command in commands:
            part = str(command or '').strip()
            if not part:
                continue
            if part.endswith(';;'):
                raise ValueError('Top-level shell fragment must not end with a case-arm separator (;;).')
            if part.endswith(';'):
                part = part[:-1].rstrip()
            parts.append(part)
        return '; '.join(parts)

    def _abrir_terminal(self, _command, _title='BC250 Control Center'):
        """TerminalRepository supplies this integration in SistemaRepository."""
        raise NotImplementedError('A terminal integration is required for this workflow.')

    def _os_repository(self):
        return create_os_repository(self)

    def preparar_memoria_bazzite(self, policy: str, ttm_gib: int):
        """Open the explicit, reboot-bound Bazzite memory transaction."""
        os_repository = self._os_repository()
        if os_repository.family != 'bazzite':
            raise RuntimeError('Bazzite memory setup is only available on Bazzite.')
        command = build_bazzite_memory_tuning_command(policy, int(ttm_gib))
        return self._abrir_terminal(command, 'Configurar memoria BC250 en Bazzite')

    def preparar_memoria(self, policy: str, ttm_gib: int):
        if self._os_repository().family == 'bazzite':
            return self.preparar_memoria_bazzite(policy, ttm_gib)
        return self._abrir_terminal(system_setup_command('memory-apply', policy, ttm_gib), 'BC250 Memory & Swap')

    def gestionar_acpi(self, action: str):
        return self._abrir_terminal(system_setup_command(action), 'BC250 ACPI')

    def _hardware_source_checkout_command(self, repository_url, destination, os_repository=None):
        """Require an immutable manifest revision before root-adjacent use."""
        del os_repository  # compatibility with existing strategy callers
        reviewed = {
            spec.upstream: spec.reviewed_revision
            for spec in EXTERNAL_TOOLS.values()
            if spec.automated
            and (spec.hardware_writes or spec.privilege_class != 'userspace')
        }.get(str(repository_url))
        if not reviewed:
            raise ValueError(
                'Hardware source is not registered with an immutable reviewed revision.'
            )
        return self._clone_or_update_commit_command(
            repository_url, destination, reviewed
        )

    def _configured_gpu_governor(self, preference=None):
        if preference is None:
            try:
                preference = self.configuracion.leer_config().get('gpu_governor', 'auto')
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                preference = 'auto'
        preference = normalize_governor_preference(preference)
        return resolve_gpu_governor(self, preference)

    def _cyan_upstream_runtime_command(self, os_repository):
        destination = self._tool_dir() / CYAN_GOVERNOR_DIRECTORY
        installer = (
            os_repository.scripts_root
            / 'common'
            / 'install-cyan-upstream-release.sh'
        )
        checkout = self._clone_or_update_commit_command(
            CYAN_GOVERNOR_REPOSITORY,
            destination,
            STEAMOS_CYAN_REVIEWED_COMMIT,
        )
        return cyan_upstream_runtime_command(
            os_repository,
            destination=destination,
            installer=installer,
            checkout_command=checkout,
            reviewed_release=CYAN_REVIEWED_RELEASE,
        )

    @staticmethod
    def _cyan_runtime_verification_command():
        return cyan_runtime_verification_command()

    def _oberon_install_command(self, os_repository):
        destination = self._tool_dir() / OBERON_DIRECTORY
        return oberon_install_command(
            os_repository,
            destination=destination,
            checkout_command=self._clone_or_update_commit_command(
                OBERON_REPOSITORY, destination, OBERON_REVIEWED_COMMIT
            ),
            yaml_cpp_revision=OBERON_YAML_CPP_REVIEWED_COMMIT,
        )

    @staticmethod
    def _local_updater_path():
        project_root = Path(__file__).resolve().parents[3]
        candidates = (
            project_root / 'scripts' / 'maintenance' / 'update-local.sh',
            Path.home() / '.local/share/bc250-control-center/scripts/maintenance/update-local.sh',
            Path('/usr/local/share/bc250-control-center/scripts/maintenance/update-local.sh'),
            Path('/usr/share/bc250-control-center/scripts/maintenance/update-local.sh'),
            # Compatibility with installations made before scripts were
            # grouped by responsibility.
            Path.home() / '.local/share/bc250-control-center/scripts/update-local.sh',
            Path('/usr/local/share/bc250-control-center/scripts/update-local.sh'),
            Path('/usr/share/bc250-control-center/scripts/update-local.sh'),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def actualizar_aplicacion_local(self):
        updater = self._local_updater_path()
        if updater is None:
            raise RuntimeError(
                'The in-place updater is not installed. Reinstall this version once '
                'with install-local.sh before using application updates.'
            )
        command = f'/usr/bin/bash {shlex.quote(str(updater))}'
        return self._abrir_terminal(command, 'Actualizar BC250 Control Center')

    @staticmethod
    def _quick_access_installer_path():
        """Locate the explicit optional Decky-plugin installer in this build."""
        project_root = Path(__file__).resolve().parents[2]
        candidates = (
            project_root / 'scripts' / 'install-decky-quick-access.sh',
            Path.home() / '.local/share/bc250-control-center/scripts/install-decky-quick-access.sh',
            Path('/usr/local/share/bc250-control-center/scripts/install-decky-quick-access.sh'),
            Path('/usr/share/bc250-control-center/scripts/install-decky-quick-access.sh'),
            # RPM/immutable deployments expose the audited entry point here;
            # the package intentionally does not copy its source scripts tree.
            Path('/usr/bin/bc250-control-center-decky-install'),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def preparar_quick_access_steamos(self, *, install_decky: bool) -> object:
        """Open the explicit Game Mode Decky/BC250 Quick Access workflow.

        This route is intentionally separate from generic preparation.  The
        remote Decky installer is only reachable after GUI *and* terminal
        confirmations; the BC250 plugin remains local and transactional.
        """
        os_repository = self._os_repository()
        family = str(os_repository.info.family)
        installer = self._quick_access_installer_path()
        if installer is None:
            raise RuntimeError(
                'The BC250 Quick Access installer is unavailable in this build. '
                'Reinstall BC250 Control Center before enabling the optional integration.'
            )
        inventory = quick_access_inventory(os_family=family)
        known_game_mode_family = family in {'steamos', 'bazzite', 'cachyos'}
        systemd_bootstrap = getattr(inventory, 'init_system', '') == 'systemd'
        if not inventory.decky_detected and not (known_game_mode_family or systemd_bootstrap):
            raise RuntimeError(
                'Decky Loader bootstrap is unavailable on this init system. '
                'BC250 Control Center can install Decky explicitly on systemd; '
                'other init systems require an existing, independently managed Decky runtime.'
            )
        if bool(install_decky and not inventory.decky_detected):
            command = (
                build_bazzite_decky_bootstrap_command(installer)
                if os_repository.info.family == 'bazzite'
                else build_decky_bootstrap_command(installer)
            )
        else:
            command = build_plugin_install_command(installer)
        self.estado_herramientas_cache = None
        return self._abrir_terminal(command, 'Game Mode Quick Access (Beta)')

    def preparar_kernel_cachyos_bc250(self) -> object:
        """Open the default explicit external BC-250 Arch/CachyOS workflow."""
        return self.preparar_cachyos_bc250('kernel')

    def preparar_cachyos_bc250(self, action: str) -> object:
        """Open one reviewed Arch/CachyOS kernel/Mesa workflow."""
        os_info = self._os_repository().info
        if not masta_bc250_stack_supported(
            distro_id=os_info.distro_id,
            family=os_info.family,
        ):
            raise RuntimeError(
                'The BC-250 kernel/Mesa workflow is available only on plain Arch Linux or CachyOS.'
            )
        action = str(action or '').strip().lower()
        labels = {
            'kernel': 'Instalar kernel BC-250 para Arch/CachyOS',
            'mesa': 'Instalar Mesa BC-250 para Arch/CachyOS',
            'full': 'Instalar kernel y Mesa BC-250 para Arch/CachyOS',
        }
        if action not in labels:
            raise ValueError('Unsupported CachyOS BC-250 action.')
        return self._abrir_terminal(
            build_cachyos_bc250_kernel_command(action),
            labels[action],
        )

    def gestionar_fsr4_bc250(self, action: str) -> object:
        """Run the official upstream FSR4 lifecycle on supported or gated hosts."""
        os_repository = self._os_repository()
        os_info = os_repository.info
        version_id = str(
            getattr(os_info, 'version_id', '')
            or read_os_release().get('VERSION_ID', '')
        ).strip()
        compute_state = (
            self._gfx1013_compute_state(os_repository)
            if os_info.family == 'fedora'
            else {}
        )
        state = fsr4_runtime_state(
            os_info.family,
            os_info.distro_id,
            version_id,
            compute_kernel_ready=bool(compute_state.get('dryhopped_ready')),
        )
        action = str(action or '').strip().lower()
        if action == 'install' and not state.get('installer_available'):
            raise RuntimeError(
                'The official upstream FSR4 V3 runtime is available only on Arch/CachyOS. '
                'Manjaro is experimental and accepted only through mandatory ABI/Vulkan checks; '
                'Fedora 44, Bazzite and Debian/Ubuntu use verified Podman source-build paths. '
                'Fedora also requires the repaired GFX1013 boot to be active.'
            )
        if action not in {'install', 'uninstall'}:
            raise ValueError('Unsupported BC-250 FSR4 action.')
        if action == 'uninstall':
            command_builder = build_fsr4_v3_uninstall_command
        elif state.get('build_mode') == 'bazzite-podman-source':
            command_builder = build_fsr4_v3_bazzite_install_command
        elif state.get('build_mode') == 'debian-podman-source':
            command_builder = build_fsr4_v3_debian_install_command
        elif state.get('build_mode') == 'fedora44-podman-source':
            command_builder = build_fsr4_v3_fedora44_install_command
        else:
            command_builder = build_fsr4_v3_install_command
        self.estado_herramientas_cache = None
        destination = self._tool_dir() / 'bc250-fsr4'
        return self._abrir_terminal(
            command_builder(destination),
            'BC-250 FSR4 V3 (per-game RADV)',
        )

    def gestionar_gfx1013_fedora(self, action: str) -> object:
        """Run the official upstream GFX1013 lifecycle on mutable Fedora."""
        os_repository = self._os_repository()
        state = self._gfx1013_compute_state(os_repository)
        action = str(action or '').strip().lower()
        if os_repository.info.family != 'fedora':
            raise RuntimeError('The direct GFX1013 workflow is available only on Fedora.')
        if action == 'install' and not state.get('direct_installer_allowed'):
            raise RuntimeError('The direct GFX1013 workflow is not offered on this host by upstream policy.')
        if action not in {'install', 'status', 'uninstall'}:
            raise ValueError('Unsupported Fedora GFX1013 action.')
        destination = self._tool_dir() / 'bc250-gfx1013-fix'
        self.estado_herramientas_cache = None
        return self._abrir_terminal(
            build_fedora_gfx1013_command(action, destination),
            'GFX1013 Fedora kernel + Mesa',
        )

    def gestionar_gfx1013_bazzite(self, action: str) -> object:
        """Run the checksum-pinned Bazzite 44 async-compute release."""
        os_repository = self._os_repository()
        state = self._gfx1013_compute_state(os_repository)
        action = str(action or '').strip().lower()
        if os_repository.info.family != 'bazzite':
            raise RuntimeError('The Bazzite async-compute workflow is available only on Bazzite.')
        if action == 'install' and not state.get('direct_installer_allowed'):
            raise RuntimeError(
                'This host does not meet the Bazzite 44 and OGC kernel requirements '
                'of the reviewed async-compute release.'
            )
        if action not in {'install', 'status', 'uninstall'}:
            raise ValueError('Unsupported Bazzite GFX1013 action.')
        self.estado_herramientas_cache = None
        return self._abrir_terminal(
            build_bazzite_async_compute_command(action),
            'GFX1013 async compute for Bazzite',
        )


    def _gfx1013_compute_state(self, os_repository) -> dict:
        """Describe GFX1013 support without performing a kernel/Mesa write.

        DryhoppedIPA's direct installer is a high-impact boot/kernel/Mesa flow.
        Generic dependency preparation must never run it. SteamOS uses the
        separately-audited keyboardspecialist backend for the kernel half.
        """

        os_release = read_os_release()
        version_id = str(os_release.get('VERSION_ID', '')).strip()
        kernel = platform.release()
        policy = classify_gfx1013_support(
            family=os_repository.info.family,
            distro_id=os_repository.info.distro_id,
            version_id=version_id,
            kernel=kernel,
            immutable=os_repository.info.immutable,
        )
        masta_stack = masta_bc250_stack_state(
            distro_id=os_repository.info.distro_id,
            family=os_repository.info.family,
        )
        # MastaG publishes the matching BC-250 kernel and Mesa/RADV packages
        # for both plain Arch and CachyOS. Treat async compute as active only
        # when the running kernel and the repository Mesa pair are both
        # verified; a half-installed stack must remain manual/review-only.
        masta_async_compute_ready = bool(
            masta_stack.get('supported')
            and masta_stack.get('kernel_active')
            and masta_stack.get('mesa_installed')
        )

        state_root = Path('/var/lib/bc250-gfx1013')
        dryhopped_installed = (state_root / 'active.env').is_file()
        try:
            cmdline = Path('/proc/cmdline').read_text(encoding='utf-8', errors='replace')
        except OSError:
            cmdline = ''
        dryhopped_boot_active = 'bc250.gfx1013_v33=1' in cmdline.split()

        steamos_kernel_marker = Path(
            f'/usr/lib/modules/{kernel}/updates/.bc250-gfx1013-fix'
        )
        steamos_kernel_module = Path(
            f'/usr/lib/modules/{kernel}/updates/amdgpu.ko.zst'
        )
        steamos_active_parameter = Path('/sys/module/amdgpu/parameters/bc250_gfx1013_fix')
        steamos_kernel_installed = bool(
            os_repository.info.family == 'steamos'
            and steamos_kernel_marker.is_file()
            and steamos_kernel_module.is_file()
        )
        steamos_kernel_present = bool(
            steamos_kernel_installed and steamos_active_parameter.is_file()
        )
        steamos_kernel_commit = ''
        if steamos_kernel_present:
            try:
                steamos_kernel_commit = steamos_active_parameter.read_text(
                    encoding='utf-8', errors='replace'
                ).strip()
            except OSError:
                steamos_kernel_commit = ''
        steamos_kernel_ready = bool(
            steamos_kernel_present
            and steamos_kernel_commit == STEAMOS_REVIEWED_DRYHOPPED_COMMIT
        )

        # The reviewed SteamOS graphics runtime stores its build products and
        # manifests per user. Validate those hashes without executing mutable
        # checkout scripts; lifecycle actions use the protected staged backend.
        external_steamos_graphics = (
            probe_steamos_graphics_runtime()
            if os_repository.info.family == 'steamos'
            else {}
        )
        external_radv = dict(external_steamos_graphics.get('radv') or {})
        external_fsr4 = dict(external_steamos_graphics.get('fsr4') or {})
        legacy_radv_detected = bool(
            external_steamos_graphics.get('legacy_radv_detected')
        )
        legacy_radv_commit = str(external_radv.get('upstream_commit') or '')

        # rpf16rj v1.1.0 is kept as a reviewed SteamOS RADV reference because
        # it follows current DryhoppedIPA safety guidance: only Mesa patch 0001
        # is enabled, X11+Wayland are built, and the stock 32-bit RADV ICD is
        # retained as a fallback.  Control Center does not install this path
        # automatically; detect an external installation without taking ownership.
        safe_radv_icds = sorted(Path('/opt/bc250-gfx1013').glob('*/share/vulkan/icd.d/radeon_icd.x86_64.json'))
        safe_radv_env = ''
        with suppress(OSError):
            safe_radv_env = Path('/etc/environment').read_text(encoding='utf-8', errors='replace')
        steamos_safe_radv_detected = bool(
            os_repository.info.family == 'steamos'
            and any(path.is_file() for path in safe_radv_icds)
            and 'VK_DRIVER_FILES=' in safe_radv_env
            and '/opt/bc250-gfx1013/' in safe_radv_env
        )

        policy.update({
            'version_id': version_id,
            'kernel': kernel,
            'dryhopped_installed': dryhopped_installed,
            'dryhopped_boot_active': dryhopped_boot_active,
            'dryhopped_ready': bool(
                dryhopped_installed and dryhopped_boot_active
            ),
            'steamos_kernel_ready': steamos_kernel_ready,
            'steamos_kernel_installed': steamos_kernel_installed,
            'steamos_kernel_reboot_pending': bool(
                steamos_kernel_installed and not steamos_kernel_ready
            ),
            'steamos_kernel_commit': steamos_kernel_commit,
            'steamos_expected_commit': STEAMOS_REVIEWED_DRYHOPPED_COMMIT,
            'legacy_steamos_radv_detected': legacy_radv_detected,
            'legacy_steamos_radv_commit': legacy_radv_commit,
            'steamos_external_graphics': external_steamos_graphics,
            'steamos_external_radv_state': str(external_radv.get('state') or 'not-installed'),
            'steamos_external_radv_current': bool(external_radv.get('current')),
            'steamos_external_fsr4_state': str(external_fsr4.get('state') or 'not-installed'),
            'steamos_external_fsr4_current': bool(external_fsr4.get('current')),
            'steamos_safe_radv_detected': steamos_safe_radv_detected,
            'steamos_safe_radv_reference': STEAMOS_GFX1013_SAFE_RADV_REFERENCE,
            'steamos_safe_radv_reference_commit': STEAMOS_GFX1013_SAFE_RADV_REVIEWED_COMMIT,
            'steamos_safe_radv_reference_version': STEAMOS_GFX1013_SAFE_RADV_VERSION,
            'upstream_url': str(policy.get('upstream') or GFX1013_UPSTREAM),
            'upstream_branch': str(policy.get('upstream_branch') or 'main'),
            'upstream_managed': bool(policy.get('upstream_managed', True)),
            'reviewed_commit': str(
                policy.get('reviewed_commit') or GFX1013_REVIEWED_COMMIT
            ),
            'reviewed_version': str(
                policy.get('reviewed_version') or GFX1013_REVIEWED_VERSION
            ),
            'masta_bc250_supported': bool(masta_stack.get('supported')),
            'masta_bc250_kernel_active': bool(masta_stack.get('kernel_active')),
            'masta_bc250_mesa_installed': bool(masta_stack.get('mesa_installed')),
            'masta_async_compute_ready': masta_async_compute_ready,
        })
        if os_repository.info.family == 'bazzite':
            policy.update(probe_bazzite_async_compute())
        return policy

    def estado_herramientas_bc250(self):
        ahora = time.monotonic()
        if self.estado_herramientas_cache is not None and ahora - self.estado_herramientas_cache_time < 10:
            return deepcopy(self.estado_herramientas_cache)

        os_repository = self._os_repository()
        os_info = os_repository.info
        is_steamos = os_info.family == 'steamos'
        cu_probe = self._probe_cu_inventory(is_steamos=is_steamos)
        cu_standard = cu_probe['standard_path']
        cu_steamos = cu_probe['steamos_path']
        standard_path_exists = cu_probe['standard_exists']
        standard_backend = cu_probe['standard_backend']
        steamos_exists = cu_probe['steamos_exists']
        expected_steamos_repo = cu_probe['expected_steamos_repository']
        cu_selection = cu_probe['selection']
        runtime_probe = self._probe_runtime_inventory()
        repository_probe = self._probe_repository_inventory(os_repository)
        platform_probe = self._probe_platform_inventory(
            is_steamos=is_steamos,
            expected_steamos_repo=expected_steamos_repo,
        )
        external_integrations = self._probe_external_integration_inventory()
        smu_path = repository_probe['smu_path']
        cyan_repo = self._tool_dir() / CYAN_GOVERNOR_DIRECTORY
        core_unlock_repo = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        core_unlock_script = core_unlock_repo / CORE_UNLOCK_SCRIPT
        steamos_fix_repo = self._tool_dir() / STEAMOS_FIX_DIRECTORY
        steamos_fix_script = (
            steamos_fix_repo / STEAMOS_FIX_SUBDIRECTORY / STEAMOS_FIX_SCRIPT
        )
        gfx1013_compute = repository_probe['gfx1013_compute']
        fsr4 = repository_probe['fsr4']
        bc250_detect = runtime_probe['bc250_detect']
        governor_probe = self._probe_governor_inventory()
        governor_context = governor_probe['context']
        selected_governor = str(governor_context['selected'])
        conflictos_gpu = list(governor_context['conflicts'])
        optional_dependencies = self._optional_dependency_status(runtime_probe)
        quick_access = quick_access_inventory(os_family=os_info.family).to_dict()
        memory_runtime = read_memory_runtime_state()
        system_setup = system_setup_inventory()
        init_manager = detect_init_manager()
        init_preflight = (
            openrc_preflight(
                commands=[name for name, path in runtime_probe.items() if path],
                has_polkit=bool(runtime_probe.get('pkexec')),
                has_dbus=bool(runtime_probe.get('system_dbus')),
            )
            if init_manager.kind == 'openrc' else {}
        )
        selected_detection = governor_context['detected'].get(selected_governor, {})
        component_capabilities = mark_component_installation(
            self._component_capabilities(os_info),
            {
                'runtime': bool(runtime_probe['python3'] and runtime_probe['git']),
                'governor': bool(
                    selected_detection.get('detected')
                    if selected_detection
                    else governor_probe['command']
                ),
                'cpu_oc': repository_probe['smu_exists'],
                'core_unlock': repository_probe['core_unlock_script_exists'],
                'umr': bool(runtime_probe['umr']),
                'cu_manager': cu_selection.exists,
                'fan_pwm': Path('/sys/module/nct6687').is_dir(),
            },
        )
        resultado = {
            'governor_cmd': governor_probe['command'],
            'governor_pkg': bool(governor_probe['command']),
            'governor_backend': selected_governor,
            'governor_detected_backend': str(
                governor_context.get('detected_backend') or ''
            ),
            'governor_preference': governor_context['preference'],
            'governor_selection_reason': governor_context['reason'],
            'supported_gpu_governors': governor_context['detected'],
            'yay': runtime_probe['yay'],
            'paru': runtime_probe['paru'],
            'git': runtime_probe['git'],
            'umr': runtime_probe['umr'],
            'stress': runtime_probe['stress'],
            'bc250_detect': bc250_detect,
            'cu_manager': cu_selection.manager,
            'cu_manager_kind': cu_selection.kind,
            'cu_manager_backend': cu_selection.backend,
            'cu_manager_repo_url': cu_selection.repository_url,
            'cu_manager_warning': cu_selection.warning,
            'cu_manager_exists': cu_selection.exists,
            'cu_privileged_backend_ready': platform_probe['cu_privileged_ready'],
            'cu_privileged_backend_reason': platform_probe['cu_privileged_reason'],
            'cu_manager_required_backend': cu_selection.required_backend,
            'cu_manager_blocked': cu_selection.blocked,
            'cu_manager_wrong_backend_present': cu_selection.wrong_backend_present,
            'cu_manager_standard_path': cu_standard,
            'cu_manager_steamos_path': cu_steamos,
            'cu_manager_steamos_compat_path': str(expected_steamos_repo / 'bc250-cu-live-manager-bc250.sh'),
            'cu_manager_steamos_compat_ready': platform_probe['cu_compat_ready'],
            'cu_manager_steamos_global_path': cu_probe['steamos_global_path'],
            'cu_manager_standard_exists': standard_path_exists,
            'cu_manager_standard_backend': standard_backend,
            'cu_manager_steamos_exists': steamos_exists,
            'cu_steamos_umr_database': str(self._steamos_umr_database_path()),
            'incompatible_gpu_governors': conflictos_gpu,
            'incompatible_gpu_governor_detected': bool(conflictos_gpu),
            'is_steamos': is_steamos,
            'steamos_game_mode': platform_probe['game_mode'],
            'steamos_game_helper': platform_probe['game_helper'],
            'steamos_game_helper_ready': platform_probe['game_helper_ready'],
            'os_id': os_info.distro_id,
            'os_like': ' '.join(os_info.id_like),
            'os_variant': os_info.variant_id,
            'os_family': os_info.family,
            'os_label': os_info.label,
            'os_immutable': os_info.immutable,
            'masta_bc250_stack_supported': masta_bc250_stack_supported(
                distro_id=os_info.distro_id,
                family=os_info.family,
            ),
            'masta_bc250_stack': self._optional_inventory_probe(
                lambda: masta_bc250_stack_state(
                    distro_id=os_info.distro_id,
                    family=os_info.family,
                ),
                {'supported': False, 'kernel_installed': False,
                 'kernel_active': False, 'mesa_installed': False},
            ),
            'init_manager': init_manager.kind,
            'init_manager_available': init_manager.available,
            'init_manager_detail': init_manager.detail,
            'init_persistence_supported': init_manager.persistence_supported,
            'init_persistence_detail': init_manager.persistence_detail,
            'openrc_preflight': init_preflight,
            'cu_live_repo_path': cu_selection.repository_path,
            'cu_repo_path': cu_selection.repository_path,
            'cu_map_repo_path': '',
            'cu_map_script': '',
            'smu_oc_path': smu_path,
            'smu_oc_exists': repository_probe['smu_exists'],
            'cyan_governor_repo_path': str(cyan_repo),
            'cyan_governor_repo_exists': repository_probe['cyan_exists'],
            'cyan_governor_repo_url': CYAN_GOVERNOR_REPOSITORY,
            'core_unlock_repo_path': str(core_unlock_repo),
            'core_unlock_script': (
                str(core_unlock_script)
                if repository_probe['core_unlock_script_exists']
                else ''
            ),
            'core_unlock_repo_exists': repository_probe['core_unlock_exists'],
            'core_unlock_repo_url': CORE_UNLOCK_REPOSITORY,
            'steamos_fix_applicable': is_steamos,
            'steamos_fix_repo_path': str(steamos_fix_repo),
            'steamos_fix_script': str(steamos_fix_script),
            'steamos_fix_repo_exists': repository_probe['steamos_fix_exists'],
            'steamos_fix_repo_url': STEAMOS_FIX_REPOSITORY,
            'gfx1013_compute': gfx1013_compute,
            'fsr4': fsr4,
            'tools_dir': str(self._tool_dir()),
            'optional_dependencies': optional_dependencies,
            'prepare_components': component_capabilities,
            'quick_access': quick_access,
            'memory_runtime': memory_runtime,
            'system_setup': system_setup,
            'external_integrations': external_integrations,
            'missing_optional_features': [
                item
                for item in optional_dependencies.values()
                if not item.get('feature_available', item['available'])
            ],
        }
        self.estado_herramientas_cache = deepcopy(resultado)
        self.estado_herramientas_cache_time = ahora
        return deepcopy(resultado)

    @staticmethod
    def _optional_inventory_probe(probe, default):
        try:
            return probe()
        except (OSError, RuntimeError, TypeError, ValueError):
            return default

    def _probe_cu_inventory(self, *, is_steamos):
        """Collect CU paths defensively; optional discovery failures stay local."""
        safe = self._optional_inventory_probe
        command = safe(lambda: self._command_path('bc250-cu-live-manager'), '')
        standard = command or safe(
            lambda: self._cu_script_local('bc250-cu-live-manager'), ''
        )
        found = safe(lambda: self._buscar_archivo('bc250-cu-live-manager.sh'), '')
        if found and 'bc250-cu-live-manager-steamos' not in found and not standard:
            standard = found
        steamos_local = safe(
            lambda: self._cu_script_local('bc250-cu-live-manager-steamos'), ''
        )
        steamos_global = safe(lambda: self._cu_steamos_installed_script(command), '')
        steamos = steamos_local or steamos_global

        standard_exists = bool(standard and safe(lambda: Path(standard).exists(), False))
        if standard and not standard_exists:
            standard_exists = bool(safe(lambda: shutil.which(Path(standard).name), ''))
        steamos_exists = bool(steamos and safe(lambda: Path(steamos).exists(), False))
        standard_repository = (
            str(Path(standard).parent)
            if standard_exists
            else safe(
                lambda: self._buscar_directorio_con(
                    'bc250-cu-live-manager.sh', 'bc250-cu-live-manager'
                ),
                '',
            )
        )
        steamos_repository = str(Path(steamos).parent) if steamos_exists else ''
        standard_backend = safe(lambda: self._cu_script_backend(standard), '')
        expected = self._tool_dir() / 'bc250-cu-live-manager-steamos'
        selection = select_cu_backend(
            is_steamos=bool(is_steamos),
            standard_path=standard,
            standard_path_exists=standard_exists,
            standard_backend=standard_backend,
            standard_repository=standard_repository,
            steamos_path=steamos,
            steamos_exists=steamos_exists,
            steamos_repository=steamos_repository,
            expected_steamos_repository=str(expected),
        )
        return {
            'command': command,
            'standard_path': standard,
            'standard_exists': standard_exists,
            'standard_backend': standard_backend,
            'steamos_path': steamos,
            'steamos_global_path': steamos_global,
            'steamos_exists': steamos_exists,
            'expected_steamos_repository': expected,
            'selection': selection,
        }

    def _probe_governor_inventory(self):
        """Resolve the governor without allowing one broken probe to abort inventory."""
        safe = self._optional_inventory_probe
        preference = safe(
            lambda: self.configuracion.leer_config().get('gpu_governor', 'auto'),
            'auto',
        )
        preference = normalize_governor_preference(preference)
        context = safe(lambda: resolve_gpu_governor(self, preference), None)
        if not isinstance(context, dict):
            selected = preference if preference in GOVERNOR_SPECS else CYAN_GOVERNOR
            detected = {
                identifier: {
                    'identifier': identifier,
                    'service': str(spec['service']),
                    'active': False,
                    'enabled': False,
                    'package_installed': False,
                    'binary_path': '',
                    'unit_path': '',
                    'config_path': str(spec['config_path']),
                    'detected': False,
                }
                for identifier, spec in GOVERNOR_SPECS.items()
            }
            context = {
                'preference': preference,
                'selected': selected,
                'reason': 'probe-failed',
                'detected': detected,
                'conflicts': [],
            }
        selected = str(context.get('selected') or CYAN_GOVERNOR)
        if selected not in GOVERNOR_SPECS:
            selected = CYAN_GOVERNOR
            context = dict(context)
            context['selected'] = selected
            context['reason'] = 'probe-failed'
        command = safe(
            lambda: self._command_path(str(GOVERNOR_SPECS[selected]['binary'])),
            '',
        )
        return {'context': context, 'command': command}

    def _probe_runtime_inventory(self):
        """Resolve command availability once and return stable string values."""
        safe = self._optional_inventory_probe
        commands = {
            name: str(safe(lambda name=name: self._command_path(name), '') or '')
            for name in (
                'python3', 'git', 'umr', 'stress', 'bc250-detect', 'yay', 'paru',
                'sensors', 'lspci', 'vulkaninfo', 'pkexec', 'busctl', 'dkms', 'make', 'gcc',
                'openrc-run', 'rc-service', 'rc-update',
            )
        }
        git_probe = getattr(self, '_git_path', None)
        if callable(git_probe):
            commands['git'] = str(safe(git_probe, commands['git']) or commands['git'])
        commands['bc250_detect'] = commands.pop('bc250-detect')
        # Finding the client binary is not evidence that an OpenRC host has a
        # usable system bus.  Cyan owns a name on that bus and every GPU range
        # change is read back through it, so its preflight must distinguish an
        # installed ``busctl`` from a running D-Bus service.
        commands['system_dbus'] = safe(
            lambda: self._system_dbus_ready(commands.get('busctl', '')),
            False,
        )
        return commands

    @staticmethod
    def _system_dbus_ready(busctl_path: object, *, runner=subprocess.run) -> bool:
        executable = str(busctl_path or '').strip()
        if not executable:
            return False
        try:
            result = runner(
                [executable, '--system', 'list'],
                text=True,
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return int(getattr(result, 'returncode', 1)) == 0

    def _probe_repository_inventory(self, os_repository):
        """Inspect optional local source trees without coupling their failures."""
        safe = self._optional_inventory_probe
        tools = self._tool_dir()
        smu_path = str(safe(
            lambda: self._buscar_directorio_con('bc250_detect.py', 'bc250_smu_oc'),
            '',
        ) or '')
        cyan = tools / CYAN_GOVERNOR_DIRECTORY
        core = tools / CORE_UNLOCK_DIRECTORY
        core_script = core / CORE_UNLOCK_SCRIPT
        steamos = tools / STEAMOS_FIX_DIRECTORY
        steamos_script = steamos / STEAMOS_FIX_SUBDIRECTORY / STEAMOS_FIX_SCRIPT
        gfx1013_compute = safe(
            lambda: self._gfx1013_compute_state(os_repository),
            {'supported': False, 'state': 'probe-failed'},
        )
        os_info = getattr(os_repository, 'info', None)
        version_id = str(
            getattr(os_info, 'version_id', '')
            or read_os_release().get('VERSION_ID', '')
        ).strip()
        fsr4 = safe(
            lambda: fsr4_runtime_state(
                getattr(os_info, 'family', ''),
                getattr(os_info, 'distro_id', ''),
                version_id,
                compute_kernel_ready=bool(
                    gfx1013_compute.get('dryhopped_ready')
                ),
            ),
            {'installed': False, 'precompiled_supported': False},
        )
        return {
            'smu_path': smu_path,
            'smu_exists': bool(smu_path and safe(lambda: Path(smu_path).exists(), False)),
            'cyan_exists': bool(safe(lambda: (cyan / 'src/gpu_frequency_fix.rs').is_file(), False)),
            'core_unlock_script_exists': bool(safe(core_script.is_file, False)),
            'core_unlock_exists': bool(
                safe(lambda: (core / '.git').is_dir(), False)
                and safe(core_script.is_file, False)
            ),
            'steamos_fix_exists': bool(
                safe(lambda: (steamos / '.git').is_dir(), False)
                and safe(steamos_script.is_file, False)
            ),
            'gfx1013_compute': gfx1013_compute,
            'fsr4': fsr4,
        }

    def _probe_platform_inventory(self, *, is_steamos, expected_steamos_repo):
        """Inspect SteamOS-only privilege/session readiness as one safe snapshot."""
        if not is_steamos:
            privileged = self._optional_inventory_probe(
                generic_cu_backend_status,
                (False, f'The staged CU backend is missing at {GENERIC_CU_BACKEND}. Run Prepare dependencies.'),
            )
            return {
                'cu_privileged_ready': bool(privileged[0]),
                'cu_privileged_reason': str(privileged[1]),
                'cu_compat_ready': False,
                'game_mode': False,
                'game_helper': '',
                'game_helper_ready': False,
            }

        safe = self._optional_inventory_probe
        fallback = (
            False,
            f'The staged CU backend is missing at {STEAMOS_CU_BACKEND}. '
            'Run Prepare dependencies.',
        )
        privileged = safe(steamos_cu_backend_status, fallback)
        if not (
            isinstance(privileged, tuple)
            and len(privileged) == 2
            and isinstance(privileged[0], bool)
        ):
            privileged = fallback
        mode_probe = getattr(self, '_steamos_game_mode_detected', None)
        helper_probe = getattr(self, '_steamos_game_helper_path', None)
        game_mode = bool(safe(mode_probe, False)) if callable(mode_probe) else False
        game_helper = (
            str(safe(helper_probe, '') or '') if callable(helper_probe) else ''
        )
        compat_script = Path(expected_steamos_repo) / 'bc250-cu-live-manager-bc250.sh'
        return {
            'cu_privileged_ready': privileged[0],
            'cu_privileged_reason': str(privileged[1]),
            'cu_compat_ready': bool(safe(compat_script.exists, False)),
            'game_mode': game_mode,
            'game_helper': game_helper,
            'game_helper_ready': bool(game_mode and game_helper),
        }

    def _probe_external_integration_inventory(self):
        """Expose reviewed checkout evidence without executing any integration."""
        executor = getattr(self, '_ejecutar', None)
        runner = (
            executor if callable(executor)
            else lambda _command, timeout=2: (1, '', 'runner unavailable')
        )
        git = GitCheckoutReader(runner)
        return build_external_checkout_inventory(self._tool_dir(), git)

    @staticmethod
    def _component_capabilities(os_info):
        """Expose a stable UI/backend contract for selective preparation.

        Availability describes whether Control Center owns a preparation path;
        it does not claim that the active kernel or hardware has passed its
        later runtime validation.
        """
        return component_capabilities(os_info)

    def _optional_dependency_status(self, commands=None):
        """Describe Debian/RPM recommended components without treating them as hard failures."""
        command_features = {
            'sensors': ('Hardware sensors', 'lm-sensors is required for temperature, voltage and fan telemetry.'),
            'stress': ('CPU tuning', 'stress is required by bc250_smu_oc to detect active CPU cores.'),
            'git': ('Community tool preparation', 'git is required to clone or update upstream BC-250 tools.'),
            'lspci': ('PCI device details', 'pciutils is required for detailed PCI hardware detection.'),
            'vulkaninfo': ('Vulkan details', 'vulkan-tools is required for Vulkan capability reporting.'),
            'pkexec': ('Privileged actions', 'polkit/pkexec is required for authenticated system changes.'),
            'dkms': ('Fan driver preparation', 'dkms is required to keep the nct6687 fan driver across kernel updates.'),
            'make': ('Driver builds', 'make is required to compile the optional fan kernel module.'),
            'gcc': ('Driver builds', 'gcc is required to compile the optional fan kernel module.'),
        }
        commands = commands or self._probe_runtime_inventory()
        result = {
            command: {
                'component': command,
                'feature': feature,
                'reason': reason,
                'available': bool(commands.get(command, '')),
            }
            for command, (feature, reason) in command_features.items()
        }
        result['python3-evdev'] = {
            'component': 'python3-evdev',
            'feature': 'Enhanced gamepad input backend',
            'reason': (
                'python3-evdev is preferred for controller identification; '
                'the built-in Linux /dev/input/js* fallback remains available without it.'
            ),
            'available': self._optional_inventory_probe(
                lambda: importlib.util.find_spec('evdev') is not None,
                False,
            ),
            'feature_available': True,
        }
        return result

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
        overlay_script = (
            Path(__file__).resolve().parents[3]
            / 'scripts/system/prepare-steamos-telemetry-oc-overlay.py'
        )
        if not overlay_script.is_file():
            raise RuntimeError(
                'The SteamOS high-OC telemetry overlay is missing from this Control Center installation.'
            )
        # The local checkout is deliberately not invoked as root.  The exact
        # reviewed Git tree is staged atomically beneath /usr/libexec first;
        # the app-owned telemetry overlay is then run from its installed,
        # root-owned implementation against that protected tree.
        installed_overlay = Path(
            '/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay'
        )
        overlay_command = (
            f'sudo test -f {shlex.quote(str(installed_overlay))} && '
            f'sudo test ! -L {shlex.quote(str(installed_overlay))} && '
            f'[ "$(sudo stat -c %u:%a {shlex.quote(str(installed_overlay))})" = "0:755" ] || '
            '{ echo "ERROR: installed SteamOS telemetry overlay is unavailable or untrusted; run scripts/install-local.sh from Desktop Mode."; exit 38; }; '
            f'sudo /usr/bin/python3 {shlex.quote(str(installed_overlay))} '
            f'{shlex.quote(str(STEAMOS_AMDGPU_BACKEND_ROOT))}'
        )
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
            telemetry_oc_overlay_command=overlay_command if install else '',
            backend_guard=protected_backend_guard(
                reviewed_revision=STEAMOS_FIX_REVIEWED_COMMIT
            ),
        )


    def preparar_compatibilidad_steamos(self):
        os_repository = self._os_repository()
        if os_repository.info.family != 'steamos':
            raise RuntimeError('The dedicated SteamOS compatibility workflow is available only on SteamOS.')
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

    def detectar_gobernadores_gpu_incompatibles(self):
        try:
            preference = self.configuracion.leer_config().get('gpu_governor', 'auto')
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            preference = 'auto'
        selected = resolve_gpu_governor(self, preference)['selected']
        return detect_incompatible_governors(self, selected)

    @staticmethod
    def _comando_desactivar_gobernadores_incompatibles(conflicts):
        services = sorted({
            str(item.get('service') or '')
            for item in conflicts
            if str(item.get('service') or '').endswith('.service')
        })
        if not services:
            return ''
        quoted = ' '.join(shlex.quote(service) for service in services)
        return (
            f'echo "== Disabling incompatible GPU governors =="; '
            'if [ -f /run/openrc/softlevel ] && command -v rc-service >/dev/null 2>&1; then '
            f'  for service in {quoted}; do key="${{service%.service}}"; '
            '    sudo rc-update del "$key" default 2>/dev/null || true; '
            '    sudo rc-service "$key" stop 2>/dev/null || true; '
            '    if rc-service "$key" status >/dev/null 2>&1; then '
            '      echo "ERROR: $key is still active"; exit 41; '
            '    fi; '
            '  done; '
            'else '
            f'  sudo systemctl disable --now {quoted}; '
            f'  for service in {quoted}; do '
            '    systemctl is-active "$service" >/dev/null 2>&1 && '
            '      { echo "ERROR: $service is still active"; exit 41; } || true; '
            '  done; '
            'fi'
        )

    def instalar_governor(
        self,
        confirmar_conflictos=False,
        desactivar_conflictos=False,
        governor_preference=None,
    ):
        governor_context = self._configured_gpu_governor(governor_preference)
        selected = str(governor_context['selected'])
        preflight = getattr(self, '_require_openrc_governor_preflight', None)
        if callable(preflight):
            preflight(selected)
        conflicts = ensure_no_incompatible_governors(
            self,
            selected=selected,
            confirmed=bool(confirmar_conflictos or desactivar_conflictos),
        )
        os_repository = self._os_repository()
        comando = (
            self._oberon_install_command(os_repository)
            if selected == OBERON_GOVERNOR
            else os_repository.install_governor_command()
        )
        if selected == CYAN_GOVERNOR:
            comando += '; ' + self._cyan_upstream_runtime_command(os_repository)
            comando += '; ' + self._cyan_runtime_verification_command()
        if desactivar_conflictos and conflicts:
            comando = self._comando_desactivar_gobernadores_incompatibles(conflicts) + '; ' + comando
        comando = wrap_steamos_writable_command(comando, family=os_repository.info.family)
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, f'Instalar {selected}')

    def cambiar_governor(self, governor):
        """Install/update and activate exactly one selected GPU governor.

        This keeps the destructive service transition in one terminal workflow:
        an enabled or running alternative is stopped first, then the requested
        governor is prepared and finally its service is enabled and verified.
        A failure in any step aborts the script before the following step runs.
        """
        selected = normalize_governor_preference(governor)
        if selected not in {CYAN_GOVERNOR, OBERON_GOVERNOR}:
            raise ValueError('A supported GPU governor must be selected.')
        preflight = getattr(self, '_require_openrc_governor_preflight', None)
        if callable(preflight):
            preflight(selected)
        conflicts = ensure_no_incompatible_governors(
            self, selected=selected, confirmed=True
        )
        os_repository = self._os_repository()
        install = (
            self._oberon_install_command(os_repository)
            if selected == OBERON_GOVERNOR
            else os_repository.install_governor_command()
        )
        if selected == CYAN_GOVERNOR:
            install += '; ' + self._cyan_upstream_runtime_command(os_repository)
            install += '; ' + self._cyan_runtime_verification_command()
        disable = self._comando_desactivar_gobernadores_incompatibles(conflicts)
        service = str(GOVERNOR_SPECS[selected]['service'])
        activate = self._governor_activation_command(selected, service, '')
        command = self._join_shell_commands((
            disable,
            install,
            activate,
            f'echo "OK: {selected} is the only enabled and active GPU governor."',
        ))
        command = wrap_steamos_writable_command(command, family=os_repository.info.family)
        self.estado_bc250_cache = None
        self.estado_herramientas_cache = None
        return self._abrir_terminal(command, f'Cambiar a {selected}')

    def desinstalar_governor(self, governor):
        selected = normalize_governor_preference(governor)
        if selected not in {CYAN_GOVERNOR, OBERON_GOVERNOR}:
            raise ValueError('A supported GPU governor must be selected for removal.')
        os_repository = self._os_repository()
        spec = GOVERNOR_SPECS[selected]
        service_name = str(spec['service'])
        binary_name = str(spec['binary'])
        service = shlex.quote(service_name)
        package = shlex.quote(str(spec['package']))
        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'bc250_pending_removal=0',
            f'echo "== Removing {selected} =="',
            # Never invoke systemctl merely because it happens to be installed
            # on an OpenRC host.  The root helper verifies the ownership and
            # management marker before removing an OpenRC script.
            'if [ -f /run/openrc/softlevel ] && command -v rc-service >/dev/null 2>&1; then '
            f'sudo /usr/libexec/bc250-control-center/bc250-openrc-service-helper remove {shlex.quote(service_name.removesuffix(".service"))} 2>/dev/null || true; '
            f'else sudo systemctl disable --now {service} 2>/dev/null || true; fi',
        ]
        family = os_repository.info.family
        if family in {'arch', 'manjaro', 'cachyos', 'steamos'}:
            commands.append(
                f'if pacman -Q {package} >/dev/null 2>&1; then '
                f'sudo pacman -Rns --noconfirm {package}; fi'
            )
        elif family in {'fedora'}:
            commands.append(
                f'if rpm -q {package} >/dev/null 2>&1; then sudo dnf remove -y {package}; fi'
            )
        elif family == 'bazzite':
            commands.append(
                f'if rpm -q {package} >/dev/null 2>&1; then '
                f'sudo rpm-ostree uninstall {package}; bc250_pending_removal=1; '
                'echo "PENDING: reboot to finish the layered package removal."; fi'
            )
        elif family in {'debian', 'ubuntu'}:
            commands.append(
                f'if dpkg-query -W -f=\'${{Status}}\' {package} 2>/dev/null | '
                f'grep -q "install ok installed"; then sudo apt-get remove -y {package}; fi'
            )

        if selected == CYAN_GOVERNOR:
            commands.extend([
                'sudo rm -f /usr/local/bin/cyan-skillfish-governor-smu',
                'if [ ! -f /run/openrc/softlevel ]; then '
                'sudo rm -f /etc/systemd/system/cyan-skillfish-governor-smu.service.d/90-bc250-control-center-upstream.conf; '
                'sudo rmdir /etc/systemd/system/cyan-skillfish-governor-smu.service.d 2>/dev/null || true; '
                'if [ -f /var/lib/bc250-control-center/cyan-governor/managed-fallback-unit ]; then '
                'sudo rm -f /usr/local/lib/systemd/system/cyan-skillfish-governor-smu.service '
                '/var/lib/bc250-control-center/cyan-governor/managed-fallback-unit; fi; fi',
            ])
        else:
            commands.extend([
                f'sudo rm -f {shlex.quote(str(Path("/usr/local/bin") / binary_name))}',
                'if [ ! -f /run/openrc/softlevel ]; then '
                f'sudo rm -f {shlex.quote(str(Path("/etc/systemd/system") / service_name))}; fi',
            ])
        commands.extend([
            'if [ ! -f /run/openrc/softlevel ]; then sudo systemctl daemon-reload; fi',
            'if [ "$bc250_pending_removal" -eq 0 ]; then '
            f'bc250_remaining_binary="$(command -v {shlex.quote(binary_name)} 2>/dev/null || true)"; '
            f'if [ -n "$bc250_remaining_binary" ]; then echo "ERROR: {selected} still has an executable at $bc250_remaining_binary"; exit 70; fi; '
            f'if [ -e /etc/init.d/{shlex.quote(service_name.removesuffix(".service"))} ] || '
            f'[ -e /etc/systemd/system/{service} ] || '
            f'[ -e /usr/local/lib/systemd/system/{service} ] || '
            f'[ -e /usr/lib/systemd/system/{service} ] || '
            f'[ -e /lib/systemd/system/{service} ]; then '
            f'echo "ERROR: {selected} still has a service definition installed"; exit 70; fi; fi',
            f'if [ "$bc250_pending_removal" -eq 1 ]; then echo "PENDING: {selected} removal will be verified after reboot."; '
            f'else echo "OK: {selected} was completely removed. Its configuration and cloned source were preserved."; fi',
        ])
        command = self._join_shell_commands(commands)
        command = wrap_steamos_writable_command(command, family=family)
        self.estado_herramientas_cache = None
        return self._abrir_terminal(command, f'Desinstalar {selected}')

    def instalar_cpu_oc(self):
        tools = self.estado_herramientas_bc250()
        if tools['bc250_detect']:
            return True
        if tools['smu_oc_exists']:
            path = shlex.quote(tools['smu_oc_path'])
            cmd = (
                f'chmod -R u+rwX,go+rX,go-w {path}; '
                f'echo "OK: bc250_smu_oc repository found at {path}"; '
                'echo "The app runs bc250_detect.py directly to avoid PEP 668 conflicts."'
            )
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
                self._clone_or_update_commit_with_archive_command(
                    EXTERNAL_TOOLS['cpu_smu_oc'].upstream,
                    destination,
                    STEAMOS_SMU_OC_REVIEWED_COMMIT,
                )
            )
        else:
            runtime = os_repository.prepare_dependencies_command('runtime')
            commands.append(f'command -v git >/dev/null 2>&1 || {{ {runtime}; }}')
            commands.append(self._hardware_source_checkout_command(
                EXTERNAL_TOOLS['cpu_smu_oc'].upstream, destination, os_repository
            ))
        commands.extend([
            # A permissive desktop umask (for example 0002 on Mint) makes a
            # freshly cloned checkout group-writable.  The privileged CPU
            # helper deliberately rejects that boundary, so normalize the
            # user-owned tree before it can be used for detection.
            f'chmod -R u+rwX,go+rX,go-w {shlex.quote(str(destination))}',
            f'test -f {shlex.quote(str(destination / "bc250_detect.py"))} || {{ echo "ERROR: bc250_detect.py was not found"; exit 1; }}',
            f'echo "OK: bc250_smu_oc is ready at {shlex.quote(str(destination))}"',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal(self._join_shell_commands(commands), 'Preparar bc250_smu_oc')

    def instalar_core_unlock(self):
        os_repository = self._os_repository()
        destination = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        script = destination / CORE_UNLOCK_SCRIPT
        destination.parent.mkdir(parents=True, exist_ok=True)
        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'echo "== Preparing official bc250-core-unlock repository =="',
        ]
        if os_repository.info.family != 'bazzite':
            runtime = os_repository.prepare_dependencies_command('runtime')
            commands.append(f'command -v git >/dev/null 2>&1 || {{ {runtime}; }}')
        commands.extend([
            'command -v git >/dev/null 2>&1 || { echo "ERROR: git is required to clone bc250-core-unlock"; exit 29; }',
            self._hardware_source_checkout_command(CORE_UNLOCK_REPOSITORY, destination, os_repository),
            f'test -d {shlex.quote(str(destination / ".git"))} || {{ echo "ERROR: bc250-core-unlock is not a Git clone"; exit 36; }}',
            f'test -f {shlex.quote(str(script))} || {{ echo "ERROR: bc250-unlock-cores.py was not found"; exit 36; }}',
            # A permissive desktop umask (commonly 0002 on Ubuntu/Mint) can
            # produce 0775 after checkout.  The privileged launcher correctly
            # refuses group-writable code, so normalize the upstream executable
            # to its committed security boundary before validating the clone.
            f'chmod 0755 {shlex.quote(str(script))}',
            f'git -C {shlex.quote(str(destination))} diff --quiet -- {shlex.quote(CORE_UNLOCK_SCRIPT)} || {{ echo "ERROR: upstream core unlock script has local modifications"; exit 36; }}',
            f'echo "OK: official bc250-core-unlock clone is ready at {shlex.quote(str(destination))}"',
            f'echo "Source: {CORE_UNLOCK_REPOSITORY}"',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal(self._join_shell_commands(commands), 'Preparar bc250-core-unlock')

    def instalar_cu_manager(self):
        tools = self.estado_herramientas_bc250()
        os_repository = self._os_repository()
        spec = self._cu_manager_spec(os_repository)
        if (
            spec['is_steamos']
            and Path(spec['script']).exists()
            and tools.get('cu_privileged_backend_ready')
        ):
            return True
        if not spec['is_steamos'] and tools['cu_manager_exists']:
            return True

        destination = spec['destination']
        upstream_script = spec['upstream_script']
        script = spec['script']
        prepare_backend = self._steamos_cu_backend_prepare_command(spec)
        destination.parent.mkdir(parents=True, exist_ok=True)
        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'echo "== Preparing bc250-cu-live-manager =="',
        ]
        if os_repository.info.family == 'bazzite':
            commands.append(self._clone_or_update_commit_with_archive_command(
                spec['repository'], destination, spec['reviewed_commit']
            ))
        else:
            runtime = os_repository.prepare_dependencies_command('runtime')
            commands.append(f'command -v git >/dev/null 2>&1 || {{ {runtime}; }}')
            commands.append(self._hardware_source_checkout_command(spec['repository'], destination, os_repository))
        commands.extend([
            f'test -x {shlex.quote(str(upstream_script))} || {{ echo "ERROR: upstream bc250-cu-live-manager.sh was not found"; exit 1; }}',
        ])
        if prepare_backend:
            commands.append(prepare_backend)
        else:
            # Every non-SteamOS action path uses the same protected backend,
            # regardless of whether the host booted systemd or OpenRC.  The
            # former OpenRC-only staging branch let a systemd host finish
            # "Prepare Live Manager" with only the mutable ResourceTools
            # checkout, after which CU controls correctly refused to run.
            commands.append(self._generic_cu_privileged_backend_stage_command(script))
        commands.extend([
            f'chmod 0755 {shlex.quote(str(script))}',
            f'test -x {shlex.quote(str(script))} || {{ echo "ERROR: BC250 SteamOS CU runtime backend was not generated"; exit 1; }}',
        ])
        if spec['is_steamos']:
            commands.extend([
                self._steamos_umr_database_repair_command(),
                wrap_steamos_writable_command(
                    self._steamos_cu_privileged_backend_stage_command(script),
                    family='steamos',
                ),
                wrap_steamos_writable_command(
                    self._steamos_cu_service_backend_update_command(script),
                    family='steamos',
                ),
                self._steamos_cu_status_probe_command(script),
            ])
        commands.append(
            f'echo "OK: 40CU manager is ready at {shlex.quote(str(script))}"'
        )
        self.estado_herramientas_cache = None
        return self._abrir_terminal(self._join_shell_commands(commands), 'Preparar bc250-cu-live-manager')

    def instalar_dependencias_bc250(
        self,
        confirmar_conflictos=False,
        desactivar_conflictos=False,
        governor_preference=None,
        include_pwm=False,
        components=None,
    ):
        os_repository = self._os_repository()
        selected_components = normalize_components(components)
        unavailable = unavailable_components(selected_components, os_repository.info)
        if unavailable:
            if components is None:
                # The default/automatic flow remains useful where only an
                # optional integration is unavailable.  An explicit request
                # still fails clearly instead of silently omitting hardware
                # functionality the caller asked to prepare.
                selected_components = frozenset(
                    key for key in selected_components if key not in unavailable
                )
            else:
                raise RuntimeError(" ".join(unavailable[key] for key in sorted(unavailable)))
        include_pwm = bool(include_pwm and 'fan_pwm' in selected_components)
        governor_context = self._configured_gpu_governor(governor_preference)
        selected_governor = str(governor_context['selected'])
        conflicts = (
            ensure_no_incompatible_governors(
                self,
                selected=selected_governor,
                confirmed=bool(confirmar_conflictos or desactivar_conflictos),
            )
            if 'governor' in selected_components
            else []
        )
        self.estado_herramientas_bc250()
        self._tool_dir().mkdir(parents=True, exist_ok=True)
        paths = self.config_paths()
        cpu_destination = self._tool_dir() / 'bc250_smu_oc'
        core_unlock_destination = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        core_unlock_script = core_unlock_destination / CORE_UNLOCK_SCRIPT
        cu_spec = self._cu_manager_spec(os_repository)
        prepare_cu_backend = self._steamos_cu_backend_prepare_command(cu_spec)

        context = PreparationContext(
            repository=self,
            os_repository=os_repository,
            selected_components=frozenset(selected_components),
            selected_governor=selected_governor,
            conflicts=tuple(conflicts),
            disable_conflicts=bool(desactivar_conflictos),
            include_pwm=include_pwm,
            paths=paths,
            tool_dir=self._tool_dir(),
            cpu_destination=cpu_destination,
            core_repository=CORE_UNLOCK_REPOSITORY,
            core_destination=core_unlock_destination,
            core_script=core_unlock_script,
            cu_spec=cu_spec,
            prepare_cu_backend=prepare_cu_backend,
            cpu_repository=EXTERNAL_TOOLS['cpu_smu_oc'].upstream,
            cpu_reviewed_revision=STEAMOS_SMU_OC_REVIEWED_COMMIT,
            cyan_directory=CYAN_GOVERNOR_DIRECTORY,
            steamos_fix_directory=STEAMOS_FIX_DIRECTORY,
        )
        command = build_preparation_command(context)
        self.estado_herramientas_cache = None
        return self._abrir_terminal(command, 'Preparar dependencias BC250')


    def _clone_or_update_with_archive_command(self, repository_url, destination, branch='main'):
        return clone_or_update_with_archive(repository_url, destination, branch)

    def _clone_or_update_commit_command(self, repository_url, destination, commit):
        """Fetch one reviewed Git commit and leave the worktree detached there.

        High-impact SteamOS hardware integrations must be reproducible.  A
        floating ``git pull`` could otherwise change kernel/register code
        between two Control Center releases without any application change.
        """
        return clone_or_update_commit(repository_url, destination, commit)

    def _clone_or_update_commit_with_archive_command(
        self, repository_url, destination, commit
    ):
        return clone_or_update_commit_with_archive(repository_url, destination, commit)

    def _clone_or_update_command(self, repository_url, destination):
        return clone_or_update(repository_url, destination)

    def _clone_or_update_branch_command(self, repository_url, destination, branch):
        return clone_or_update_branch(repository_url, destination, branch)

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
        os_repository = self._os_repository()
        if self._command_path('umr') and os_repository.info.family != 'steamos':
            # UMR by itself is not enough for the Compute Units page.  Older
            # beta builds returned here even when the protected manager had
            # never been staged, leaving Unlock / Sync permanently disabled
            # on an otherwise clean Arch/CachyOS installation.
            tools = self.estado_herramientas_bc250()
            if tools.get('cu_privileged_backend_ready'):
                return True
        spec = self._cu_manager_spec(os_repository)
        destination = spec['destination']
        upstream_script = spec['upstream_script']
        script = spec['script']
        prepare_backend = self._steamos_cu_backend_prepare_command(spec)
        destination.parent.mkdir(parents=True, exist_ok=True)

        commands = [
            'set -Eeuo pipefail',
            'export LC_ALL=C LANG=C',
            'BC250_REBOOT_REQUIRED=0',
            'echo "== Preparing UMR for BC250 =="',
        ]
        if os_repository.info.family == 'bazzite':
            commands.extend([
                self._clone_or_update_commit_with_archive_command(
                    spec['repository'], destination, spec['reviewed_commit']
                ),
                f'test -x {shlex.quote(str(upstream_script))} || {{ echo "ERROR: upstream 40CU helper is missing"; exit 31; }}',
                *([prepare_backend] if prepare_backend else []),
                f'chmod 0755 {shlex.quote(str(script))}',
                f'test -x {shlex.quote(str(script))} || {{ echo "ERROR: 40CU runtime helper is missing"; exit 31; }}',
                self._generic_cu_privileged_backend_stage_command(script),
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
                self._hardware_source_checkout_command(spec['repository'], destination, os_repository),
                f'test -x {shlex.quote(str(upstream_script))} || {{ echo "ERROR: upstream 40CU helper is missing"; exit 31; }}',
                *([prepare_backend] if prepare_backend else []),
                f'chmod 0755 {shlex.quote(str(script))}',
                f'test -x {shlex.quote(str(script))} || {{ echo "ERROR: 40CU runtime helper is missing"; exit 31; }}',
                os_repository.install_umr_command(str(script)),
                'command -v umr >/dev/null 2>&1 || { echo "ERROR: UMR is still unavailable"; exit 32; }',
            ])
            if os_repository.info.family == 'steamos':
                commands.append(self._steamos_umr_database_repair_command())
                commands.append(wrap_steamos_writable_command(
                    self._steamos_cu_privileged_backend_stage_command(script),
                    family='steamos',
                ))
                commands.append(self._steamos_cu_service_backend_update_command(script))
                commands.append(self._steamos_cu_status_probe_command(script))
            else:
                commands.append(
                    self._generic_cu_privileged_backend_stage_command(script)
                )
        commands.append('if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then echo "== UMR staged; reboot required =="; else echo "== UMR installation verified =="; fi')
        self.estado_herramientas_cache = None
        return self._abrir_terminal(self._join_shell_commands(commands), 'Instalar UMR')

    def _comando_instalar_umr(self, tools=None):
        tools = tools or self.estado_herramientas_bc250()
        script = tools.get('cu_manager') or ''
        if tools.get('is_steamos') and tools.get('cu_manager_steamos_path'):
            script = tools.get('cu_manager_steamos_path') or script
        return self._os_repository().install_umr_command(script)
