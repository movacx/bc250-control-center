from __future__ import annotations

import json
import os
import platform
import re
import shlex
import stat
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from bc250cc.domain.fan.persistence import (
    normalize_fan_curve,
    validate_fan_curve_points,
)
from bc250cc.infrastructure.cyan_governor_runtime import (
    detect_cyan_frequency_fix_runtime,
    detect_cyan_metrics_fix_runtime,
)
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS
from bc250cc.infrastructure.governor_conflicts import (
    CYAN_GOVERNOR,
    GOVERNOR_SPECS,
    OBERON_GOVERNOR,
)
from bc250cc.infrastructure.governor_health_policy import (
    classify_cyan_health,
    classify_oberon_health,
)
from bc250cc.infrastructure.gpu.governor_toml import (
    OBERON_SAFE_VOLTAGE_MIN_MV,
    GovernorTomlEditor,
    GovernorTomlError,
    OberonYamlEditor,
    OberonYamlError,
)
from bc250cc.infrastructure.hardware_identity import is_bc250_platform
from bc250cc.infrastructure.persistence.activity_journal import activity_journal
from bc250cc.infrastructure.protected_file_health import (
    ProtectedFileEvidence,
    evaluate_protected_file,
)
from bc250cc.infrastructure.repository_provenance import (
    GitProvenanceEvidence,
    ProvenanceState,
    classify_archive_provenance,
    classify_git_provenance,
    read_bounded_text,
)
from bc250cc.infrastructure.steamos_amdgpu import AmdgpuDecision, classify_amdgpu_status
from bc250cc.infrastructure.steamos_amdgpu_backend import (
    STEAMOS_AMDGPU_BACKEND,
    protected_backend_status_ready,
)
from bc250cc.platform.init.services import (
    detect_init_manager,
    parse_openrc_runlevel,
    parse_openrc_status,
    service_display_name,
    service_key,
)


class HealthRepository:
    """Read-only system audit plus conservative, targeted repair entry points."""

    _HELPERS = (
        Path('/usr/libexec/bc250-control-center/bc250-fan-pwm-helper'),
        Path('/usr/libexec/bc250-control-center/bc250-steamos-game-helper'),
        Path('/usr/libexec/bc250-control-center/bc250-governor-config-helper'),
        Path('/usr/libexec/bc250-control-center/bc250-core-unlock-helper'),
        Path('/usr/libexec/bc250-control-center/bc250-cpu-smu-helper'),
        Path('/usr/libexec/bc250-control-center/bc250-openrc-service-helper'),
    )
    _PROTECTED_PAYLOADS = (
        Path('/usr/libexec/bc250-control-center/lib/bc250_smu_oc_vendor.zip'),
    )
    _REPOSITORIES = (
        ('bc250_smu_oc', EXTERNAL_TOOLS['cpu_smu_oc'].upstream, 'bc250_detect.py', EXTERNAL_TOOLS['cpu_smu_oc'].reviewed_revision),
        ('bc250-core-unlock', EXTERNAL_TOOLS['core_unlock'].upstream, 'bc250-unlock-cores.py', EXTERNAL_TOOLS['core_unlock'].reviewed_revision),
        ('bc250-cu-live-manager', EXTERNAL_TOOLS['cu_manager_standard'].upstream, 'bc250-cu-live-manager.sh', EXTERNAL_TOOLS['cu_manager_standard'].reviewed_revision),
        ('nct6687d', EXTERNAL_TOOLS['nct6687'].upstream, 'Makefile', EXTERNAL_TOOLS['nct6687'].reviewed_revision),
    )
    _RELEVANT_LAUNCHERS = (
        Path('/usr/bin/bc250-control-center'),
        Path('/usr/bin/bc250-control-centerd'),
        Path('/usr/local/bin/bc250-cu-live-manager'),
        Path('/var/usrlocal/bin/bc250-cu-live-manager'),
        Path('/usr/local/bin/cyan-skillfish-governor-smu'),
        Path('/usr/bin/cyan-skillfish-governor-smu'),
        Path('/usr/local/bin/oberon-governor'),
        Path('/usr/bin/oberon-governor'),
    )

    def _health_governor_context(self):
        resolver = getattr(self, '_configured_gpu_governor', None)
        if callable(resolver):
            try:
                return resolver()
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                pass
        return {'selected': CYAN_GOVERNOR, 'preference': 'auto', 'reason': 'default'}

    @staticmethod
    def _health_item(
        identifier, title, status, detail, repair='', data=None, *,
        detail_key='', detail_values=None, repair_key='', repair_values=None,
    ):
        return {
            'id': str(identifier),
            'title': str(title),
            'status': str(status),
            'detail': str(detail),
            'repair': str(repair),
            'data': data if isinstance(data, dict) else {},
            'detail_key': str(detail_key or ''),
            'detail_values': detail_values if isinstance(detail_values, dict) else {},
            'repair_key': str(repair_key or ''),
            'repair_values': repair_values if isinstance(repair_values, dict) else {},
        }

    @staticmethod
    def _classify_service_state(enabled, active, exists, optional, missing_detail):
        if not exists and optional:
            status = 'healthy'
            detail = 'Optional service is not configured.'
        elif not exists:
            status = 'error'
            detail = missing_detail
        elif enabled == 'enabled' and active == 'failed':
            status = 'error'
            detail = 'Service is enabled but failed.'
        elif enabled == 'enabled' and active not in {'active', 'inactive'}:
            status = 'warning'
            detail = f'Service is enabled but its current state is {active or "unknown"}.'
        elif enabled != 'enabled' and active == 'active':
            status = 'warning'
            detail = 'Service is running now but is not enabled at boot.'
        elif enabled != 'enabled':
            status = 'warning' if not optional else 'healthy'
            detail = 'Service is installed but disabled.'
        else:
            status = 'healthy'
            detail = f'Enabled; current state: {active or "unknown"}.'
        detail_key = ''
        detail_values = {}
        if detail.startswith('Service is enabled but its current state is '):
            detail_key = 'Service is enabled but its current state is {state}.'
            detail_values = {'state': active or 'unknown'}
        elif detail.startswith('Enabled; current state: '):
            detail_key = 'Enabled; current state: {state}.'
            detail_values = {'state': active or 'unknown'}
        return status, detail, detail_key, detail_values

    def _service_health(self, service, *, user=False, optional=False):
        init_manager = detect_init_manager()
        if init_manager.kind == 'openrc' and not user:
            key = service_key(service)
            exists = (Path('/etc/init.d') / key).is_file()
            enabled_rc, enabled_out, enabled_err = self._ejecutar(
                ['rc-update', 'show', 'default'], timeout=4
            )
            active_rc, active_out, active_err = self._ejecutar(
                ['rc-service', key, 'status'], timeout=4
            )
            enabled = 'enabled' if parse_openrc_runlevel(enabled_out, key) else 'disabled'
            active = parse_openrc_status(active_rc, active_out or active_err)
            missing_detail = (active_err or enabled_err or 'OpenRC service script was not found.').strip()
            status, detail, detail_key, detail_values = self._classify_service_state(
                enabled, active, exists, optional, missing_detail
            )
            return self._health_item(
                f'service:{key}', service_display_name(key, 'openrc'), status, detail,
                'Restart or reinstall this service.' if status != 'healthy' else '',
                {
                    'exists': exists, 'enabled': enabled, 'active': active,
                    'enabled_rc': enabled_rc, 'active_rc': active_rc,
                    'init_manager': 'openrc',
                },
                detail_key=detail_key, detail_values=detail_values,
            )
        if init_manager.kind != 'systemd':
            return self._health_item(
                f'service:{service}', service, 'healthy' if optional else 'warning',
                init_manager.persistence_detail,
                '',
                {
                    'exists': False, 'enabled': 'unsupported', 'active': 'unknown',
                    'init_manager': init_manager.kind,
                    'persistence_supported': False,
                },
            )
        prefix = ['systemctl'] + (['--user'] if user else [])
        enabled_rc, enabled_out, enabled_err = self._ejecutar(prefix + ['is-enabled', service], timeout=4)
        active_rc, active_out, active_err = self._ejecutar(prefix + ['is-active', service], timeout=4)
        enabled = (enabled_out or '').strip().lower()
        active = (active_out or '').strip().lower()
        exists = enabled not in {'', 'not-found'} or active not in {'', 'unknown'}
        missing_detail = (enabled_err or active_err or 'Service unit was not found.').strip()
        status, detail, detail_key, detail_values = self._classify_service_state(
            enabled, active, exists, optional, missing_detail
        )
        service_data = {
            'exists': exists, 'enabled': enabled, 'active': active,
            'enabled_rc': enabled_rc, 'active_rc': active_rc,
        }
        if service == 'bc250-smu-oc.service' and exists:
            _show_rc, show_out, show_err = self._ejecutar(
                prefix + [
                    'show', service,
                    '--property=Type,ActiveState,SubState,Result,ExecMainStatus,ExecMainCode',
                ],
                timeout=4,
            )
            properties = {}
            for line in (show_out or show_err or '').splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    properties[key.strip()] = value.strip()
            service_data.update({f'systemd_{key}': value for key, value in properties.items()})
            boot_apply_success = bool(
                enabled == 'enabled'
                and active == 'inactive'
                and properties.get('Result', '') in {'', 'success'}
                and properties.get('ExecMainStatus', '') in {'', '0'}
            )
            if boot_apply_success:
                status = 'healthy'
                detail = 'Enabled boot-time apply completed successfully; inactive (dead) is expected after the apply process exits.'
                detail_key = ''
                detail_values = {}
            elif properties.get('Result') not in {None, '', 'success'} or properties.get('ActiveState') == 'failed':
                status = 'error'
                detail = f"CPU OC boot-time apply failed: {properties.get('Result') or properties.get('ActiveState') or 'unknown'}."
                detail_key = ''
                detail_values = {}
        return self._health_item(
            f'service:{service}', service, status, detail,
            'Restart or reinstall this service.' if status != 'healthy' else '',
            service_data,
            detail_key=detail_key, detail_values=detail_values,
        )

    def _repository_health(self, folder, expected_url, required_file, expected_revision=''):
        path = self._tool_dir() / folder
        required = path / required_file
        source_marker = path / '.bc250-source-url'
        if not path.is_dir() or not required.is_file():
            return self._health_item(
                f'repository:{folder}', folder, 'error',
                f'Missing or incomplete repository at {path}.',
                'Clone or repair this community tool repository.',
                detail_key='Missing or incomplete repository at {path}.',
                detail_values={'path': str(path)},
            )
        version = self._repository_version(path)
        if (path / '.git').is_dir():
            return self._git_repository_health(
                folder, path, expected_url, expected_revision, version
            )
        if source_marker.is_file():
            archive = self._archive_repository_health(
                folder, path, expected_url, expected_revision, version
            )
            if archive is not None:
                return archive
        return self._health_item(
            f'repository:{folder}', folder, 'warning',
            f'Tool files exist but source integrity metadata is unavailable at {path}.',
            'Prepare dependencies to restore a verifiable source checkout.',
            {'path': str(path), 'version': version},
            detail_key='Tool files exist but source integrity metadata is unavailable at {path}.',
            detail_values={'path': str(path)},
        )

    def _git_repository_health(self, folder, path, expected_url, expected_revision, version):
        origin_rc, origin_out, origin_error = self._ejecutar(
            ['git', '-C', str(path), 'remote', 'get-url', 'origin'], timeout=5
        )
        fsck_rc, fsck_out, fsck_error = self._ejecutar(
            ['git', '-C', str(path), 'fsck', '--connectivity-only', '--no-progress'], timeout=12
        )
        revision_rc, revision_out, revision_error = 0, '', ''
        if expected_revision:
            revision_rc, revision_out, revision_error = self._ejecutar(
                ['git', '-C', str(path), 'rev-parse', 'HEAD'], timeout=5
            )
        dirty_rc, dirty_out, dirty_error = self._ejecutar(
            ['git', '-C', str(path), 'status', '--porcelain'], timeout=5
        )
        origin = origin_out.strip()
        revision = revision_out.strip().lower()
        accepted = {expected_url, expected_url + '.git'}
        state = classify_git_provenance(GitProvenanceEvidence(
            origin_ok=origin_rc == 0 and origin in accepted,
            connectivity_ok=fsck_rc == 0,
            revision_required=bool(expected_revision),
            revision_ok=revision_rc == 0 and revision == expected_revision.lower(),
            status_readable=dirty_rc == 0,
            dirty=bool(dirty_out.strip()),
        ))
        data = {
            'path': str(path), 'origin': origin, 'version': version,
            'revision': revision, 'expected_revision': expected_revision,
            'provenance_state': state.value,
        }
        if state is ProvenanceState.ORIGIN_INVALID:
            evidence = origin_out or origin_error or 'missing'
            return self._health_item(
                f'repository:{folder}', folder, 'error',
                f'Unexpected or unreadable Git origin: {evidence}.',
                'Review the repository and restore its official origin.', data,
                detail_key='Unexpected or unreadable Git origin: {origin}.',
                detail_values={'origin': evidence},
            )
        if state is ProvenanceState.CONNECTIVITY_INVALID:
            evidence = fsck_error or fsck_out or 'unknown error'
            return self._health_item(
                f'repository:{folder}', folder, 'error',
                f'Git object connectivity check failed: {evidence}.',
                'Back up local changes and recreate this repository.', data,
                detail_key='Git object connectivity check failed: {error}.',
                detail_values={'error': evidence},
            )
        if state is ProvenanceState.REVISION_INVALID:
            evidence = revision or revision_error or 'missing'
            return self._health_item(
                f'repository:{folder}', folder, 'error',
                f'Checkout revision is not the reviewed revision: {evidence}.',
                'Prepare dependencies to restore the reviewed revision.', data,
            )
        if state is ProvenanceState.STATUS_UNREADABLE:
            data['status_error'] = dirty_error
            return self._health_item(
                f'repository:{folder}', folder, 'error',
                'Repository modification state could not be verified.',
                'Back up local changes and prepare dependencies again.', data,
            )
        if state is ProvenanceState.DIRTY:
            data['dirty'] = True
            return self._health_item(
                f'repository:{folder}', folder, 'warning',
                'Repository contains local modifications; automatic updates will preserve and refuse to overwrite them.',
                'Review or save the local repository changes.', data,
            )
        return self._health_item(
            f'repository:{folder}', folder, 'healthy',
            f'Official Git checkout is complete at {path} (version {version}).',
            data=data, detail_key='Official Git checkout is complete at {path}.',
            detail_values={'path': str(path)},
        )

    def _archive_repository_health(self, folder, path, expected_url, expected_revision, version):
        try:
            marker = read_bounded_text(path / '.bc250-source-url').strip()
        except (OSError, UnicodeError, ValueError):
            return None
        archive_revision = ''
        with suppress(OSError, UnicodeError, ValueError):
            archive_revision = read_bounded_text(
                path / '.bc250-source-revision'
            ).strip().lower()
        state = classify_archive_provenance(
            origin_ok=marker in {expected_url, expected_url + '.git'},
            revision_required=bool(expected_revision),
            revision_ok=archive_revision == expected_revision.lower(),
        )
        if state is ProvenanceState.ARCHIVE_ORIGIN_INVALID:
            return None
        data = {
            'path': str(path), 'origin': marker, 'version': version,
            'revision': archive_revision, 'expected_revision': expected_revision,
            'provenance_state': state.value,
        }
        if state is ProvenanceState.ARCHIVE_REVISION_INVALID:
            return self._health_item(
                f'repository:{folder}', folder, 'error',
                'Archive source lacks evidence for the reviewed revision.',
                'Prepare dependencies with immutable revision metadata.', data,
            )
        return self._health_item(
            f'repository:{folder}', folder, 'healthy',
            f'Official archive source is complete at {path} (version {version}).',
            data=data, detail_key='Official archive source is complete at {path}.',
            detail_values={'path': str(path)},
        )

    def _repository_version(self, path):
        """Return a bounded, local-only version identifier for diagnostics."""
        path = Path(path)
        if (path / '.git').is_dir():
            rc, out, _error = self._ejecutar(
                ['git', '-C', str(path), 'describe', '--tags', '--always', '--dirty'],
                timeout=5,
            )
            if rc == 0 and re.fullmatch(r'[A-Za-z0-9._/+~-]{1,160}', out.strip()):
                return out.strip()
        for candidate in ('VERSION', 'version.txt'):
            version_file = path / candidate
            try:
                value = read_bounded_text(version_file, maximum=512).strip()
            except (OSError, UnicodeError, ValueError):
                continue
            if value and len(value) <= 160 and '\n' not in value:
                return value
        return 'unversioned archive'

    def _governor_config_health(self):
        context = self._health_governor_context()
        selected = str(context['selected'])
        path = Path(str(GOVERNOR_SPECS[selected]['config_path']))
        if not path.is_file():
            return self._health_item(
                'config:governor', 'Governor configuration', 'error',
                f'Configuration is missing: {path}.', 'Reinstall the GPU governor configuration.'
                , detail_key='Configuration is missing: {path}.', detail_values={'path': str(path)}
            )
        if selected == OBERON_GOVERNOR:
            try:
                state = OberonYamlEditor(path).state()
            except (OberonYamlError, OSError) as error:
                return self._health_item(
                    'config:governor', 'Oberon YAML', 'error', str(error),
                    'Restore a valid four-endpoint upstream YAML configuration.',
                    {'path': str(path), 'backend': selected},
                )
            decision = classify_oberon_health(
                state,
                voltage_floor_mv=OBERON_SAFE_VOLTAGE_MIN_MV,
            )
            return self._health_item(
                'config:governor', decision.title, decision.status,
                decision.detail, decision.recommendation,
                {'path': str(path), 'backend': selected, 'state': state},
            )

        try:
            editor = GovernorTomlEditor(path)
            migration = editor.legacy_frequency_range_migration()
            frequency_range = editor.frequency_range_state()
            points = editor.safe_point_state()
            telemetry = editor.gpu_telemetry_state()
            # Both telemetry fixes are explicit compatibility switches. A
            # MastaG BC250 kernel is expected to keep both disabled, while an
            # older kernel may request them. Health validates the selected
            # profile; it must not impose a distro-wide default.
            needs_frequency_fix = bool(telemetry.get('fix_frequency'))
            runtime = detect_cyan_frequency_fix_runtime(self)
            runtime.update(detect_cyan_metrics_fix_runtime(self))
            decision = classify_cyan_health(
                migration=migration,
                frequency_range=frequency_range,
                safe_points=points,
                telemetry=telemetry,
                runtime=runtime,
                needs_frequency_fix=needs_frequency_fix,
            )
            if decision.status != 'healthy':
                return self._health_item(
                    'config:governor', decision.title, decision.status,
                    decision.detail, decision.recommendation,
                    {'path': str(path), 'backend': selected, 'telemetry': telemetry,
                     'runtime': runtime, 'migration': migration,
                     'frequency_range': frequency_range,
                     'repair_action': decision.repair_action,
                     'fix_frequency': needs_frequency_fix},
                )
        except (GovernorTomlError, OSError) as error:
            return self._health_item(
                'config:governor', 'Governor TOML', 'error', str(error),
                'Back up the file and restore a valid upstream TOML configuration.'
            )
        return self._health_item(
            'config:governor', decision.title, decision.status,
            decision.detail,
            data={'path': str(path), 'backend': selected, 'frequency_range': frequency_range,
                  'safe_points': list(points), 'telemetry': telemetry,
                  'runtime': runtime},
            detail_key='Valid TOML; range mode: {mode}; {points} safe-points.',
            detail_values={'mode': frequency_range.get('mode'), 'points': len(points)},
        )

    def _cpu_config_health(self):
        config = self._read_cpu_oc_config(Path('/etc/bc250-smu-oc.conf'))
        if not config.get('exists'):
            return self._health_item(
                'config:cpu', 'CPU OC configuration', 'healthy',
                'Persistent CPU overclocking is not configured.', data=config,
            )
        if not config.get('valid'):
            source = self._read_cpu_oc_config(self._tool_dir() / 'bc250_smu_oc/overclock.conf')
            repairable = bool(source.get('valid'))
            return self._health_item(
                'config:cpu', 'CPU OC configuration', 'error',
                str(config.get('error') or 'Invalid CPU OC configuration.'),
                ('Reinstall the last validated generated CPU configuration.' if repairable
                 else 'Apply and test a temporary CPU profile to regenerate a safe source configuration.'),
                data={**config, 'repair_action': 'regenerate-cpu-config' if repairable else '',
                      'safe_source': source if repairable else {}},
            )
        return self._health_item(
            'config:cpu', 'CPU OC configuration', 'healthy',
            f'{config.get("frequency")} MHz, scale {config.get("scale")}, {config.get("max_temperature")} C.',
            data=config,
            detail_key='{frequency} MHz, scale {scale}, {temperature} C.',
            detail_values={'frequency': config.get('frequency'), 'scale': config.get('scale'),
                           'temperature': config.get('max_temperature')},
        )

    def _fan_config_health(self):
        config_path = None
        settings = getattr(self, 'configuracion', None)
        if settings is not None:
            try:
                config_path = Path(settings.config_path())
                if config_path.is_file():
                    json.loads(config_path.read_text(encoding='utf-8', errors='strict'))
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                return self._health_item(
                    'config:fan', 'Fan configuration', 'error',
                    f'The local application configuration is corrupted: {exc}',
                    'Preserve the corrupt file and regenerate safe fan defaults.',
                    {'repair_action': 'regenerate-fan-config',
                     'path': str(config_path or '')},
                )
        try:
            config = self.leer_config_local()
            curve = normalize_fan_curve(config.get('fan_curve') if isinstance(config, dict) else {})
            raw_points = curve.get('points') if isinstance(curve, dict) else None
            points = [
                (item.get('temperature'), item.get('speed'))
                for item in (raw_points or []) if isinstance(item, dict)
            ]
            valid, error = validate_fan_curve_points(points)
        except Exception as exc:
            valid, error, curve = False, str(exc), {}
        if not valid:
            return self._health_item(
                'config:fan', 'Fan configuration', 'error', error,
                'Regenerate safe fan defaults, then open Fans to review the curve.',
                {'repair_action': 'regenerate-fan-config',
                 'path': str(config_path or '')},
            )
        enabled = bool(curve.get('enabled'))
        return self._health_item(
            'config:fan', 'Fan configuration', 'healthy',
            f'Valid {len(points)}-point curve; automatic mode is {"enabled" if enabled else "disabled"}.',
            data={'enabled': enabled, 'points': points},
            detail_key='Valid {points}-point curve; automatic mode is {mode}.',
            detail_values={'points': len(points), 'mode': 'enabled' if enabled else 'disabled'},
        )

    def _compute_units_health(self):
        tools = self.estado_herramientas_bc250()
        if not tools.get('cu_manager_exists'):
            return self._health_item(
                'config:compute-units', 'Compute Unit configuration', 'error',
                str(tools.get('cu_manager_warning') or 'The required live manager is unavailable.'),
                'Prepare the distribution-appropriate Compute Unit live manager.',
            )
        if tools.get('cu_privileged_backend_ready') is False:
            return self._health_item(
                'config:compute-units', 'Compute Unit configuration', 'error',
                str(tools.get('cu_privileged_backend_reason') or 'The privileged CU backend is not trusted.'),
                'Keep CU writes disabled until a packaged root-owned backend passes provenance and recovery validation.',
                {'backend': tools.get('cu_manager_backend'), 'write_actions_locked': True},
            )
        state = self.obtener_estado_cu_cache()
        if not state.get('available'):
            return self._health_item(
                'config:compute-units', 'Compute Unit configuration', 'warning',
                'The live manager is ready, but no validated authorized topology reading is cached yet.',
                'Open Compute Units and authorize Refresh dashboard once.',
                {'backend': tools.get('cu_manager_backend'), 'state': state},
            )
        return self._health_item(
            'config:compute-units', 'Compute Unit configuration', 'healthy',
            f'{state.get("mode")} ({state.get("active_cus")}/{state.get("total_cus")} CUs); boot sync: {state.get("boot_sync")}.',
            data={'backend': tools.get('cu_manager_backend'), 'state': state},
            detail_key='{mode} ({active}/{total} CUs); boot sync: {boot_sync}.',
            detail_values={'mode': state.get('mode'), 'active': state.get('active_cus'),
                           'total': state.get('total_cus'), 'boot_sync': state.get('boot_sync')},
        )

    @staticmethod
    def _parse_cu_service_masks(text):
        match = re.search(r'^\s*BC250_WGP_MASKS\s*=\s*([^#\n]+)', text or '', re.MULTILINE)
        if not match:
            return None
        values = [item.strip() for item in match.group(1).split(',')]
        if len(values) != 4:
            return None
        masks = []
        try:
            for value in values:
                mask = int(value, 0)
                if not 0 <= mask <= 0x1f:
                    return None
                masks.append(mask)
        except ValueError:
            return None
        return masks

    def _cu_installation_health(self):
        init_manager = detect_init_manager()
        if init_manager.kind == 'openrc':
            script = Path('/etc/init.d/bc250-cu-live-manager')
            config = Path('/etc/bc250-cu-live-manager.conf')
            if not script.exists():
                return self._health_item(
                    'installation:compute-units', 'Compute Unit boot installation', 'healthy',
                    'The optional OpenRC Compute Unit boot service is not installed.',
                    data={'init_manager': 'openrc'},
                )
            try:
                metadata = script.stat(follow_symlinks=False)
                text = script.read_text(encoding='utf-8', errors='strict')
            except (OSError, UnicodeError) as error:
                return self._health_item('installation:compute-units', 'Compute Unit boot installation', 'error', f'Could not read {script}: {error}')
            if script.is_symlink() or metadata.st_uid != 0 or metadata.st_mode & 0o022 or 'Managed by BC250 Control Center (OpenRC)' not in text:
                return self._health_item(
                    'installation:compute-units', 'Compute Unit boot installation', 'error',
                    'The OpenRC CU script is unsafe or was modified; it was not removed automatically.',
                    'Review the script manually, then reinstall the Compute Unit service.',
                    {'init_manager': 'openrc', 'script': str(script)},
                )
            if not config.is_file():
                return self._health_item(
                    'installation:compute-units', 'Compute Unit boot installation', 'warning',
                    'The OpenRC service is installed, but no boot WGP table has been saved yet.',
                    data={'init_manager': 'openrc', 'script': str(script)},
                )
            return self._health_item(
                'installation:compute-units', 'Compute Unit boot installation', 'healthy',
                'The native OpenRC CU service and saved table are present.',
                data={'init_manager': 'openrc', 'script': str(script), 'config': str(config)},
            )
        if init_manager.kind != 'systemd':
            return self._health_item(
                'installation:compute-units', 'Compute Unit boot installation', 'healthy',
                init_manager.persistence_detail,
                data={
                    'init_manager': init_manager.kind,
                    'persistence_supported': False,
                },
            )
        unit_candidates = (
            Path('/etc/systemd/system/bc250-cu-live-manager.service'),
            Path('/usr/lib/systemd/system/bc250-cu-live-manager.service'),
        )
        unit = next((path for path in unit_candidates if path.is_file()), None)
        if unit is None:
            return self._health_item(
                'installation:compute-units', 'Compute Unit boot installation', 'healthy',
                'The optional Compute Unit boot service is not installed.',
            )
        try:
            unit_text = unit.read_text(encoding='utf-8', errors='strict')
        except (OSError, UnicodeError) as error:
            return self._health_item(
                'installation:compute-units', 'Compute Unit boot installation', 'error',
                f'Could not read {unit}: {error}',
                'Repair the Compute Unit boot installation.',
                {'repair_action': 'repair-cu-installation', 'unit': str(unit)},
            )
        match = re.search(r'^\s*ExecStart\s*=\s*(\S+)', unit_text, re.MULTILINE)
        executable = Path(match.group(1)) if match and match.group(1).startswith('/') else None
        if executable is None or not executable.is_file() or not os.access(executable, os.X_OK):
            return self._health_item(
                'installation:compute-units', 'Compute Unit boot installation', 'error',
                f'The service points to a missing or non-executable live manager: {executable or "invalid ExecStart"}.',
                'Reinstall only the Compute Unit service binary while preserving its saved table.',
                {'repair_action': 'repair-cu-installation', 'unit': str(unit),
                 'executable': str(executable or '')},
            )
        config = Path('/etc/bc250-cu-live-manager.conf')
        if config.is_file():
            try:
                config_text = config.read_text(encoding='utf-8', errors='strict')
            except (OSError, UnicodeError) as error:
                config_text = ''
                config_error = str(error)
            else:
                config_error = ''
            masks = self._parse_cu_service_masks(config_text)
            if masks is None:
                return self._health_item(
                    'installation:compute-units', 'Compute Unit boot installation', 'error',
                    f'The saved Compute Unit boot table is invalid: {config_error or config}.',
                    'Remove the broken service safely and restore the factory CU layout.',
                    {'repair_action': 'factory-repair-cu', 'unit': str(unit),
                     'config': str(config)},
                )
        else:
            return self._health_item(
                'installation:compute-units', 'Compute Unit boot installation', 'warning',
                'The service is installed, but no boot WGP table has been saved yet.',
                'Open Compute Units and save a validated layout for boot.',
                {'unit': str(unit), 'executable': str(executable)},
            )
        return self._health_item(
            'installation:compute-units', 'Compute Unit boot installation', 'healthy',
            f'Service binary and saved WGP table are valid ({", ".join(hex(item) for item in masks)}).',
            data={'unit': str(unit), 'executable': str(executable), 'masks': masks},
        )

    def _platform_and_binary_health(self):
        platform_detected = is_bc250_platform()
        checks = [self._health_item(
            'platform', 'BC-250 hardware', 'healthy' if platform_detected else 'warning',
            'Compatible BC-250 identifiers detected.' if platform_detected
            else 'BC-250 identifiers were not detected; hardware actions must remain unavailable.',
        )]
        for command in ('python3', 'git', 'pkexec', 'lspci', 'sensors', 'stress', 'umr'):
            path = self._command_path(command)
            checks.append(self._health_item(
                f'binary:{command}', command,
                'healthy' if path else 'error',
                path or f'Required executable {command} was not found.',
                '' if path else 'Prepare dependencies to install the missing runtime component.',
                {'path': path},
                detail_key='' if path else 'Required executable {command} was not found.',
                detail_values={'command': command} if not path else {},
            ))
        return checks

    def _privileged_helper_health(self):
        checks = []
        specs = (
            *((helper, True, 'helper', 'privileged helper') for helper in self._HELPERS),
            *((payload, False, 'payload', 'privileged CPU payload') for payload in self._PROTECTED_PAYLOADS),
        )
        for path, executable, kind, label in specs:
            try:
                metadata = path.stat(follow_symlinks=False)
                evidence = ProtectedFileEvidence(
                    exists=True,
                    is_symlink=stat.S_ISLNK(metadata.st_mode),
                    mode=metadata.st_mode,
                    uid=metadata.st_uid,
                )
            except OSError:
                evidence = ProtectedFileEvidence(False, False, None, None)
            decision = evaluate_protected_file(evidence, executable=executable)
            safe = decision.safe
            checks.append(self._health_item(
                f'{kind}:{path.name}', path.name,
                'healthy' if safe else 'error',
                f'Root-owned protected {label}: {path}.' if safe else f'Missing or insecure {label}: {path} ({decision.reason}).',
                '' if safe else 'Reinstall the privileged application helpers.',
                {'path': str(path), 'uid': decision.uid, 'mode': decision.mode_text,
                 'reason': decision.reason},
                detail_key=(
                    'Root-owned protected helper: {path}.'
                    if safe and executable
                    else 'Missing or insecure privileged helper: {path}.'
                    if executable
                    else ''
                ),
                detail_values={'path': str(path)},
            ))
        return checks

    def _relevant_launcher_health(self):
        checks = []
        for path in self._RELEVANT_LAUNCHERS:
            exists_without_following = os.path.lexists(path)
            if not exists_without_following:
                # Several launchers are backend-specific alternatives; absence
                # is healthy unless an installed unit references one, which is
                # validated separately by _cu_installation_health.
                continue
            is_link = path.is_symlink()
            target_exists = path.exists()
            executable = target_exists and path.is_file() and os.access(path, os.X_OK)
            healthy = target_exists and executable
            if is_link:
                try:
                    target = str(path.resolve(strict=True))
                except OSError:
                    target = '<broken>'
            else:
                target = str(path)
            checks.append(self._health_item(
                f'launcher:{path}', path.name,
                'healthy' if healthy else 'error',
                f'Validated launcher: {path} -> {target}.' if healthy
                else f'Broken or non-executable launcher: {path} -> {target}.',
                '' if healthy else 'Reinstall the component that owns this launcher.',
                {'path': str(path), 'target': target, 'symlink': is_link,
                 'repair_action': 'repair-launchers' if not healthy else ''},
            ))
        return checks

    def _repository_specs(self, family):
        repositories = list(self._REPOSITORIES)
        selected = str(self._health_governor_context()['selected'])
        if selected == CYAN_GOVERNOR:
            repositories.append((
                'cyan-skillfish-governor-smu',
                'https://github.com/filippor/cyan-skillfish-governor',
                'src/gpu_frequency_fix.rs',
                EXTERNAL_TOOLS['cyan_smu'].reviewed_revision,
            ))
        if selected == OBERON_GOVERNOR:
            repositories.append((
                'oberon-governor',
                'https://gitlab.com/mothenjoyer69/oberon-governor',
                'CMakeLists.txt',
                EXTERNAL_TOOLS['oberon_governor'].reviewed_revision,
            ))
        if family == 'steamos':
            repositories[2] = (
                'bc250-cu-live-manager-steamos',
                'https://github.com/F5GO/bc250-cu-live-manager-SteamOS',
                'bc250-cu-live-manager-bc250.sh',
                EXTERNAL_TOOLS['cu_manager_steamos'].reviewed_revision,
            )
            repositories.append((
                'bc250-steamos', 'https://github.com/keyboardspecialist/bc250-steamos',
                'bc250-audio-fix/patch-driver.sh',
                EXTERNAL_TOOLS['steamos_amdgpu'].reviewed_revision,
            ))
        return repositories

    def _repository_health_checks(self, family):
        checks = []
        for spec in self._repository_specs(family):
            item = self._repository_health(*spec)
            if spec[0] == 'nct6687d' and item['status'] == 'error':
                item['status'] = 'warning'
                item['repair'] = 'Prepare the optional nct6687 PWM driver when fan control is required.'
                item['data']['repair_action'] = 'prepare-fan-pwm'
            checks.append(item)
        return checks

    def _governor_conflict_health(self):
        conflicts = self.detectar_gobernadores_gpu_incompatibles()
        selected = str(self._health_governor_context()['selected'])
        return self._health_item(
            'governor:conflicts', 'GPU governor conflicts',
            'error' if conflicts else 'healthy',
            ('Incompatible governors detected: ' + ', '.join(item.get('identifier', '?') for item in conflicts))
            if conflicts else 'No incompatible GPU governor was detected.',
            f'Disable the other governor before enabling {selected}.' if conflicts else '',
            {'conflicts': conflicts, 'selected': selected},
            detail_key='Incompatible governors detected: {governors}' if conflicts else '',
            detail_values={'governors': ', '.join(item.get('identifier', '?') for item in conflicts)} if conflicts else {},
        )

    def _service_and_config_health(self):
        selected = str(self._health_governor_context()['selected'])
        selected_service = str(GOVERNOR_SPECS[selected]['service'])
        other_service = str(GOVERNOR_SPECS[
            OBERON_GOVERNOR if selected == CYAN_GOVERNOR else CYAN_GOVERNOR
        ]['service'])
        checks = [
            self._service_health(selected_service),
            self._service_health(other_service, optional=True),
            self._service_health('bc250-smu-oc.service', optional=True),
            self._service_health('bc250-cu-live-manager.service', optional=True),
            self._service_health('nct6687-load.service', optional=True),
            self._service_health('bc250-control-centerd.service', user=True, optional=True),
            self._governor_config_health(),
            self._cpu_config_health(),
            self._fan_config_health(),
            self._compute_units_health(),
            self._cu_installation_health(),
        ]
        return checks

    def _steamos_patch_health(self):
        backend_ready, backend_reason = self._steamos_amdgpu_backend_status()
        if not backend_ready:
            return self._health_item(
                'steamos:patches', 'SteamOS compatibility patches', 'warning',
                'The protected SteamOS AMDGPU backend is unavailable or untrusted.',
                'Run Prepare SteamOS compatibility from Desktop Mode to stage the reviewed backend before checking or repairing it.',
                {
                    'installed_for_running_kernel': False,
                    'scheduler_policy_verified': False,
                    'scheduler_policy_active': False,
                    'scheduler_policy_runtime_conflict': False,
                    'decision': 'protected-backend-required',
                    'reboot_required': False,
                    'efi_policy_readable': self._steamos_efi_policy_readable(),
                    'status_privileged': False,
                    'status_exit_code': None,
                    'backend_reason': backend_reason,
                },
                detail_key='The protected SteamOS AMDGPU backend is unavailable or untrusted.',
                repair_key=(
                    'Run Prepare SteamOS compatibility from Desktop Mode to stage the reviewed '
                    'backend before checking or repairing it.'
                ),
            )
        result = self._ejecutar(['/usr/bin/bash', str(STEAMOS_AMDGPU_BACKEND), 'status'], timeout=20)
        rc, out, error = result
        efi_readable = self._steamos_efi_policy_readable()
        state = classify_amdgpu_status(
            out,
            privileged=False,
            efi_readable=efi_readable,
            running_release=platform.release(),
            running_cmdline=self._running_kernel_cmdline(),
        )
        ready = state.decision is AmdgpuDecision.READY
        if ready:
            status = 'healthy'
            detail = out
            repair = ''
        elif state.decision is AmdgpuDecision.REBOOT_PENDING:
            status = 'warning'
            detail = (
                'The AMDGPU module and persistent scheduler policy are verified, '
                'but amdgpu.sched_policy=2 is not active in the running boot.'
            )
            repair = 'Reboot when convenient; do not reinstall or rebuild the AMDGPU module.'
        elif state.decision is AmdgpuDecision.KERNEL_STATUS_REQUIRED:
            status = 'warning'
            detail = (
                'The AMDGPU toolkit report cannot be matched to a running kernel '
                'because the kernel release was not observed.'
            )
            repair = (
                'Refresh the SteamOS compatibility status after the running kernel '
                'can be read; do not install or repair from this incomplete evidence.'
            )
            detail_key = (
                'The AMDGPU toolkit report cannot be matched to a running kernel '
                'because the kernel release was not observed.'
            )
            repair_key = (
                'Refresh the SteamOS compatibility status after the running kernel '
                'can be read; do not install or repair from this incomplete evidence.'
            )
        elif state.decision is AmdgpuDecision.LIVE_STATUS_REQUIRED:
            status = 'warning'
            detail = (
                'The AMDGPU module is reported for the running kernel, but the live '
                'kernel command line was not observed.'
            )
            repair = (
                'Refresh the SteamOS compatibility status after /proc/cmdline can be '
                'read; do not install or repair from this incomplete evidence.'
            )
            detail_key = (
                'The AMDGPU module is reported for the running kernel, but the live '
                'kernel command line was not observed.'
            )
            repair_key = (
                'Refresh the SteamOS compatibility status after /proc/cmdline can be '
                'read; do not install or repair from this incomplete evidence.'
            )
        elif state.decision is AmdgpuDecision.PRIVILEGED_CHECK:
            status = 'warning'
            if state.policy_active:
                detail = (
                    'amdgpu.sched_policy=2 is active in the running kernel, but '
                    'persistent EFI policy needs a privileged read-only check.'
                )
                repair = (
                    'Run the explicit SteamOS compatibility check with authorization; '
                    'do not reinstall or rebuild the AMDGPU module.'
                )
            else:
                detail = out or error or 'The AMDGPU module is verified but EFI policy is not readable.'
                repair = 'Use the explicit SteamOS compatibility action to validate or repair only the boot policy.'
        elif state.decision is AmdgpuDecision.REPAIR_POLICY:
            status = 'warning'
            detail = out or error or 'The AMDGPU module is verified but the scheduler boot policy is incomplete.'
            repair = 'Use the explicit SteamOS compatibility action to repair only the boot policy.'
        else:
            status = 'warning'
            detail = out or error or 'SteamOS patches are not installed for the running kernel.'
            repair = 'Review and explicitly install the validated upstream patch for this kernel.'
        if state.decision not in {
            AmdgpuDecision.KERNEL_STATUS_REQUIRED,
            AmdgpuDecision.LIVE_STATUS_REQUIRED,
        }:
            detail_key = ''
            repair_key = ''
        return self._health_item(
            'steamos:patches', 'SteamOS compatibility patches',
            status, detail, repair,
            {
                'installed_for_running_kernel': state.module_verified,
                'scheduler_policy_verified': state.policy_verified,
                'scheduler_policy_active': state.policy_active,
                'scheduler_policy_runtime_conflict': state.runtime_policy_conflict,
                'decision': state.decision.value,
                'reboot_required': state.reboot_required_after_action,
                'efi_policy_readable': efi_readable,
                'status_privileged': False,
                'status_exit_code': rc,
            },
            detail_key=detail_key,
            repair_key=repair_key,
        )

    @staticmethod
    def _steamos_amdgpu_backend_status():
        return protected_backend_status_ready(
            reviewed_revision=EXTERNAL_TOOLS['steamos_amdgpu'].reviewed_revision
        )

    @staticmethod
    def _steamos_efi_policy_readable():
        policy = Path('/efi/EFI/steamos/grub.cfg')
        try:
            return bool(policy.is_file() and os.access(policy, os.R_OK))
        except OSError:
            return False

    @staticmethod
    def _running_kernel_cmdline():
        try:
            return read_bounded_text(Path('/proc/cmdline'), 64 * 1024)
        except (OSError, RuntimeError, ValueError):
            return ''

    def _cachyos_compatibility_health(self):
        """Report the running CachyOS kernel without changing boot state.

        Upstream bc250_smu_oc documents Arch as tested but does not explicitly
        list CachyOS.  Community tooling also distinguishes Deckify from the
        standard CachyOS kernel, while MastaG publishes a BC-250-specific
        kernel/Mesa stack.  This is therefore a diagnostic warning, never an
        automatic kernel replacement.
        """
        kernel = platform.release()
        lower_kernel = kernel.lower()
        package_rc, package_out, _package_error = self._ejecutar(
            ['pacman', '-Q', 'linux-cachyos-bc250'], timeout=6
        )
        bc250_package = package_rc == 0 and bool((package_out or '').strip())
        running_bc250 = 'cachyos-bc250' in lower_kernel or 'bc250' in lower_kernel
        deckify = 'deckify' in lower_kernel

        if bc250_package and running_bc250:
            status = 'healthy'
            detail = (
                f'BC-250-specific CachyOS kernel detected and active: {kernel}. '
                'This community stack includes BC-250 telemetry/compute fixes.'
            )
            repair = ''
        elif deckify:
            status = 'warning'
            detail = (
                f'Deckify-flavoured CachyOS kernel detected: {kernel}. Community BC-250 '
                'tooling distinguishes this kernel from standard/BC-250-specific CachyOS, '
                'and bc250_smu_oc upstream does not explicitly list CachyOS as a tested OS.'
            )
            repair = (
                'Do not replace the kernel automatically. Review the CachyOS BC-250 kernel '
                'option and keep a known-working fallback before changing boot components.'
            )
        elif bc250_package and not running_bc250:
            status = 'warning'
            detail = (
                f'linux-cachyos-bc250 is installed but the running kernel is {kernel}. '
                'Reboot/boot selection may still be pending.'
            )
            repair = 'Boot the intended kernel only after confirming a fallback entry exists.'
        else:
            status = 'warning'
            detail = (
                f'CachyOS kernel detected: {kernel}. bc250_smu_oc upstream explicitly tests '
                'Arch but does not explicitly list CachyOS; treat CPU OC persistence as '
                'community-supported and validate it conservatively.'
            )
            repair = (
                'No automatic kernel change is performed. The MastaG/linux-cachyos-bc250 '
                'kernel/Mesa repository is an optional community compatibility path.'
            )
        return self._health_item(
            'cachyos:kernel', 'CachyOS BC-250 kernel compatibility', status, detail, repair,
            {
                'kernel': kernel,
                'deckify': deckify,
                'linux_cachyos_bc250_installed': bc250_package,
                'linux_cachyos_bc250_running': running_bc250,
                'bc250_smu_oc_cachyos_upstream_tested': False,
                'automatic_kernel_replacement': False,
            },
        )

    def _bazzite_compatibility_health(self):
        rc, out, error = self._ejecutar(['rpm-ostree', 'status', '--json'], timeout=12)
        reference = ''
        if rc == 0:
            try:
                payload = json.loads(out or '{}')
                booted = next(
                    (item for item in payload.get('deployments', []) if item.get('booted')),
                    {},
                )
                reference = str(
                    booted.get('container-image-reference')
                    or booted.get('origin') or ''
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                reference = ''
        community_image = '62fixolab' in reference.lower() and 'bc250' in reference.lower()
        return self._health_item(
            'bazzite:compatibility', 'Bazzite BC-250 compatibility',
            'healthy' if community_image else 'warning',
            (
                f'BC-250 patched Bazzite image detected: {reference}.'
                if community_image else
                'Bazzite is immutable: kernel audio/DisplayPort patches must be supplied by '
                'the active OSTree image. Cyan userspace telemetry is checked separately; '
                'BC250 Control Center will not replace the host kernel automatically.'
            ),
            '' if community_image else (
                'Review the current 62fixolab BC-250 Bazzite image or keep the stock image '
                'and accept that kernel-only audio fixes are not installed by this app.'
            ),
            {'reference': reference, 'community_image': community_image,
             'status_error': error if rc != 0 else ''},
        )

    @staticmethod
    def _health_counts(checks):
        counts = {name: sum(1 for item in checks if item['status'] == name) for name in ('healthy', 'warning', 'error')}
        overall = 'error' if counts['error'] else ('warning' if counts['warning'] else 'healthy')
        return overall, counts

    def health_check(self):
        os_info = self._os_repository().info
        checks = self._platform_and_binary_health()
        checks.extend(self._privileged_helper_health())
        checks.extend(self._relevant_launcher_health())
        checks.extend(self._repository_health_checks(os_info.family))
        checks.append(self._governor_conflict_health())
        checks.extend(self._service_and_config_health())
        if os_info.family == 'steamos':
            checks.append(self._steamos_patch_health())
        elif os_info.family == 'bazzite':
            checks.append(self._bazzite_compatibility_health())
        elif os_info.family == 'cachyos':
            checks.append(self._cachyos_compatibility_health())
        overall, counts = self._health_counts(checks)
        return {
            'overall': overall,
            'counts': counts,
            'checks': checks,
            'distribution': os_info.label,
            'family': os_info.family,
            'kernel': platform.release(),
            'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        }

    @staticmethod
    def _repair_result(health, started, message):
        return {'started': bool(started), 'message': str(message), 'health': health}

    def _repair_steamos_patches(self, health):
        # Kept as a safe compatibility shim for callers from older UI builds.
        # Kernel/initramfs changes require the dedicated dependency-dialog
        # confirmation and are never launched from generic Health Repair.
        return self._repair_result(
            health,
            False,
            'SteamOS kernel compatibility requires the explicit Prepare SteamOS compatibility action; Health Repair will not modify amdgpu or initramfs automatically.',
        )

    def _repair_fan_pwm(self, health):
        started = self.preparar_nct6687_control_pwm()
        return self._repair_result(health, started, 'Fan PWM driver repair started.')

    def _repair_governor_config(self, health):
        governor_check = next(
            (item for item in health['checks'] if item['id'] == 'config:governor'), {}
        )
        governor_repair = (governor_check.get('data') or {}).get('repair_action')
        if governor_repair == 'update-cyan-runtime':
            started = self.instalar_dependencias_bc250()
            return self._repair_result(
                health, started,
                'Reviewed Cyan runtime update and GPU frequency verification started.',
            )
        if governor_repair == 'disable-cyan-metrics-fix':
            # This repair restarts a live governor.  Route it through the GPU
            # repository contract, which reads and restores the current D-Bus
            # range around the restart.  Do not fall through to the historic
            # terminal string below: that path cannot prove the range survived.
            repair = getattr(self, 'desactivar_fix_metricas_gpu_cyan', None)
            if not callable(repair):
                return self._repair_result(
                    health, False,
                    'The protected Cyan metrics repair is unavailable in this installation; no governor restart was attempted.',
                )
            message = str(repair() or 'Cyan metrics overlay repair completed.')
            return self._repair_result(health, True, message)
        if governor_repair not in {
            'clear-frequency-range', 'migrate-legacy-frequency-range',
            'ensure-cyan-telemetry',
        }:
            return None
        helper = Path('/usr/libexec/bc250-control-center/bc250-governor-config-helper')
        if not helper.is_file():
            raise RuntimeError('The privileged governor configuration helper is missing.')
        argument = ''
        if governor_repair == 'ensure-cyan-telemetry':
            argument = ' 1' if bool((governor_check.get('data') or {}).get('fix_frequency')) else ' 0'
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            return self._repair_result(
                health, False,
                f'Governor service repair is not supported on {init_manager.display_name}; no command was run.',
            )
        if init_manager.kind == 'openrc':
            command = (
                f'pkexec {shlex.quote(str(helper))} {shlex.quote(governor_repair)}{argument}; '
                'sudo rc-service cyan-skillfish-governor-smu restart || '
                'sudo rc-service cyan-skillfish-governor-smu start; '
                'rc-service cyan-skillfish-governor-smu status || true'
            )
        else:
            command = (
                f'pkexec {shlex.quote(str(helper))} {shlex.quote(governor_repair)}{argument}; '
                'sudo systemctl try-restart cyan-skillfish-governor-smu.service; '
                'systemctl --no-pager --full status cyan-skillfish-governor-smu.service || true'
            )
        started = self._abrir_terminal(command, 'Reparar configuración del governor')
        return self._repair_result(
            health, started,
            'Governor TOML repair started; unrelated sections and safe-points are preserved.',
        )

    def _repair_helpers(self, health):
        if self._es_ostree():
            return self._repair_result(
                health,
                False,
                'Bazzite keeps /usr immutable. Install or update the matching BC250 Control Center RPM with rpm-ostree, reboot, then run Health again; the local installer cannot repair protected helpers on this deployment.',
            )
        installer = Path(__file__).resolve().parents[2] / 'scripts/install-local.sh'
        if not installer.is_file():
            raise RuntimeError('The local installer required to repair privileged helpers is missing.')
        command = f'/usr/bin/bash {shlex.quote(str(installer))}'
        started = self._abrir_terminal(command, 'Reparar helpers BC250')
        return self._repair_result(health, started, 'Helper repair started.')

    def _repair_cpu_configuration(self, health):
        item = next((check for check in health['checks'] if check['id'] == 'config:cpu'), {})
        if (item.get('data') or {}).get('repair_action') != 'regenerate-cpu-config':
            return None
        command_parts = self.comando_cpu_oc_persistente_embebido()
        command = ' '.join(shlex.quote(str(part)) for part in command_parts)
        started = self._abrir_terminal(command, 'Reparar configuración CPU BC250')
        return self._repair_result(
            health, started,
            'CPU configuration repair started from the last validated generated overclock.conf.',
        )

    def _repair_fan_configuration(self, health):
        item = next((check for check in health['checks'] if check['id'] == 'config:fan'), {})
        if (item.get('data') or {}).get('repair_action') != 'regenerate-fan-config':
            return None
        settings = getattr(self, 'configuracion', None)
        if settings is None:
            raise RuntimeError('The local configuration store is unavailable.')
        # leer_config() preserves unreadable JSON under a .corrupt-* name and
        # atomically writes normalized defaults. No privileged state changes.
        settings.leer_config()
        return self._repair_result(
            health, True,
            'Fan configuration was regenerated locally; review it before enabling the daemon.',
        )

    def _repair_cu_installation(self, health):
        item = next(
            (check for check in health['checks'] if check['id'] == 'installation:compute-units'),
            {},
        )
        action = (item.get('data') or {}).get('repair_action')
        if action not in {'repair-cu-installation', 'factory-repair-cu'}:
            return None
        if action == 'factory-repair-cu':
            self.ejecutar_accion_cu_grafica('factory_repair')
            message = 'Broken CU persistence was removed and the factory live layout was restored.'
        else:
            self.ejecutar_accion_cu_grafica('install_service')
            message = 'The Compute Unit service binary was reinstalled without replacing the saved table.'
        return self._repair_result(health, True, message)

    def _repair_services(self, health, failed):
        allowed = {
            'cyan-skillfish-governor-smu', 'oberon-governor', 'nct6687-load',
        }
        selected = []
        for item in failed:
            if not item.startswith('service:'):
                continue
            try:
                key = service_key(item.split(':', 1)[1])
            except ValueError:
                continue
            if key in allowed and key not in selected:
                selected.append(key)
        if not selected:
            return None
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            return self._repair_result(
                health, False,
                f'Service repair is not supported on {init_manager.display_name}; no command was run.',
            )
        if init_manager.kind == 'openrc':
            quoted = ' '.join(shlex.quote(name) for name in selected)
            command = (
                f'for service in {quoted}; do '
                'sudo rc-service "$service" restart || sudo rc-service "$service" start; '
                'rc-service "$service" status || true; '
                'done'
            )
        else:
            selected_units = [f'{name}.service' for name in selected]
            quoted = ' '.join(shlex.quote(name) for name in selected_units)
            command = (
                f'sudo systemctl daemon-reload; sudo systemctl restart {quoted}; '
                f'systemctl --no-pager --full status {quoted}'
            )
        started = self._abrir_terminal(command, 'Reparar servicios BC250')
        return self._repair_result(health, started, 'Service repair started.')

    def _repair_failed_health(self, health, failed):
        for repairer in (
            self._repair_cpu_configuration,
            self._repair_fan_configuration,
            self._repair_cu_installation,
        ):
            result = repairer(health)
            if result is not None:
                return result
        if any(item.startswith(('binary:', 'repository:')) for item in failed):
            return self._repair_result(
                health, self.instalar_dependencias_bc250(), 'Dependency repair started.'
            )
        if any(item.startswith(('helper:', 'launcher:')) for item in failed):
            return self._repair_helpers(health)
        return self._repair_services(health, failed)

    def _repair_warning_health(self, health, warning_ids):
        # Kernel/initramfs changes on SteamOS are intentionally never launched
        # from the generic Health Repair button. The dependency dialog owns a
        # dedicated, explicit compatibility action with a specific high-impact
        # confirmation. This keeps a harmless health warning from turning into
        # an hours-long kernel build or a reboot-requiring driver replacement.
        if 'repository:nct6687d' in warning_ids:
            return self._repair_fan_pwm(health)
        return None

    def repair_installation(self):
        health = self.health_check()
        failed = {item['id'] for item in health['checks'] if item['status'] == 'error'}
        warning_ids = {item['id'] for item in health['checks'] if item['status'] == 'warning'}
        repairable_warnings = {'repository:nct6687d', 'config:governor'}
        if not failed and not warning_ids.intersection(repairable_warnings):
            if 'steamos:patches' in warning_ids:
                return self._repair_result(
                    health,
                    False,
                    'SteamOS kernel compatibility requires the explicit Prepare SteamOS compatibility action; Health Repair will not modify amdgpu or initramfs automatically.',
                )
            return self._repair_result(health, False, 'No automatic repair is required.')
        governor_result = self._repair_governor_config(health)
        if governor_result is not None:
            return governor_result
        if failed:
            failed_result = self._repair_failed_health(health, failed)
            if failed_result is not None:
                return failed_result
        else:
            warning_result = self._repair_warning_health(health, warning_ids)
            if warning_result is not None:
                return warning_result
        return self._repair_result(
            health, False,
            'The remaining errors require review; no risky hardware or kernel change was started automatically.',
        )

    @staticmethod
    def _read_diagnostic_file(path, limit=262144):
        try:
            data = Path(path).read_text(encoding='utf-8', errors='replace')
            return data[:limit]
        except OSError as error:
            return f'<unavailable: {error}>'

    def _diagnostic_version_sections(self):
        sections = ['', '## Tool versions']
        commands = {
            'cyan-skillfish-governor-smu': ['cyan-skillfish-governor-smu', '--version'],
            'oberon-governor': ['oberon-governor', '--version'],
            'UMR': ['umr', '--version'],
            'Git': ['git', '--version'],
        }
        for label, command in commands.items():
            rc, out, error = self._ejecutar(command, timeout=8)
            sections.append(f'{label}: {(out or error or f"exit {rc}")[:2000]}')
        try:
            tools_root = Path(self._tool_dir())
        except (AttributeError, OSError, TypeError):
            tools_root = Path('/nonexistent/bc250-control-center-tools')
        repositories = {
            'bc250_smu_oc': tools_root / 'bc250_smu_oc',
            'bc250-cu-live-manager': tools_root / 'bc250-cu-live-manager',
            'bc250-cu-live-manager-SteamOS': tools_root / 'bc250-cu-live-manager-steamos',
            'oberon-governor source': tools_root / 'oberon-governor',
        }
        sections.extend(
            f'{label}: {self._repository_version(path)} ({path})'
            for label, path in repositories.items()
            if path.is_dir()
        )
        return sections

    def _diagnostic_hardware_sections(self):
        sections = []
        for title, command in (
            ('CPU information', ['lscpu']),
            ('PCI / GPU information', ['lspci', '-nnk']),
        ):
            rc, out, error = self._ejecutar(command, timeout=8)
            sections.extend(('', f'## {title}', out or error or f'exit {rc}'))
        init_manager = detect_init_manager()
        if init_manager.kind == 'openrc':
            rc, runlevel, runlevel_error = self._ejecutar(
                ['rc-update', 'show', 'default'], timeout=10
            )
            service_lines = []
            for service in (
                'bc250-cu-live-manager', 'bc250-smu-oc',
                'cyan-skillfish-governor-smu', 'nct6687-load', 'oberon-governor',
            ):
                code, out, error = self._ejecutar(
                    ['rc-service', service, 'status'], timeout=5
                )
                enabled = parse_openrc_runlevel(runlevel, service)
                service_lines.append(
                    f'{service}: enabled={enabled} status={parse_openrc_status(code, out or error)}'
                )
            error = runlevel_error
        elif init_manager.kind == 'systemd':
            rc, out, error = self._ejecutar(
                ['systemctl', 'list-unit-files', '--no-pager'], timeout=10
            )
            service_lines = [
                line for line in (out or '').splitlines()
                if any(token in line.lower() for token in ('bc250', 'cyan-skillfish', 'nct6687', 'oberon'))
            ]
        else:
            rc, error = 0, ''
            service_lines = [init_manager.persistence_detail]
        sections.extend((
            '', '## Installed BC250 services',
            '\n'.join(service_lines) or error or f'exit {rc}',
        ))
        return sections

    def _diagnostic_runtime_sections(self):
        sections = []
        for title, reader in (
            ('Compute Unit status (last authorized reading)', self.obtener_estado_cu_cache),
            ('Fan hardware status', self.estado_fans_bc250),
        ):
            try:
                payload = json.dumps(reader(), ensure_ascii=False, indent=2, default=str)
            except Exception as error:
                payload = f'<unavailable: {error}>'
            sections.extend(('', f'## {title}', payload))
        sections.extend(('', '## Recent application events'))
        try:
            events = activity_journal(self.configuracion).listar(100)
            sections.append(json.dumps(events, ensure_ascii=False, indent=2, default=str))
        except Exception as error:
            sections.append(f'<unavailable: {error}>')
        return sections

    def generate_diagnostic_report(self):
        health = self.health_check()
        paths = self.config_paths()
        sections = [
            '# BC250 Control Center diagnostic report',
            f'Generated: {health["generated_at"]}',
            f'Distribution: {health["distribution"]}',
            f'Kernel: {health["kernel"]}',
            f'BIOS vendor: {self._read_diagnostic_file("/sys/class/dmi/id/bios_vendor", 4096).strip()}',
            f'BIOS version: {self._read_diagnostic_file("/sys/class/dmi/id/bios_version", 4096).strip()}',
            f'Product: {self._read_diagnostic_file("/sys/class/dmi/id/product_name", 4096).strip()}',
            '', '## Health summary', json.dumps(health, ensure_ascii=False, indent=2, default=str),
        ]
        sections.extend(self._diagnostic_version_sections())
        context = self._health_governor_context()
        sections.extend((
            '', '## Governor configuration',
            'Both supported formats are included below; secrets are not stored in these files.',
            '', '## GPU governor selection',
            json.dumps(context, ensure_ascii=False, indent=2, default=str),
            '', '## Cyan governor configuration',
            self._read_diagnostic_file('/etc/cyan-skillfish-governor-smu/config.toml'),
            '', '## Oberon governor configuration',
            self._read_diagnostic_file('/etc/oberon-config.yaml'),
        ))
        sections.extend(('', '## CPU OC configuration', self._read_diagnostic_file('/etc/bc250-smu-oc.conf')))
        sections.extend(('', '## Local application configuration', self._read_diagnostic_file(paths.get('config', ''))))
        sections.extend(self._diagnostic_hardware_sections())
        sections.extend(self._diagnostic_runtime_sections())
        report = '\n'.join(sections).rstrip() + '\n'
        state_home = Path(os.environ.get('XDG_STATE_HOME') or (Path.home() / '.local/state'))
        destination = state_home / 'bc250-control-center/diagnostics'
        destination.mkdir(parents=True, exist_ok=True)
        destination.chmod(0o700)
        filename = destination / f'bc250-diagnostic-{datetime.now().strftime("%Y%m%d-%H%M%S")}.txt'
        filename.write_text(report, encoding='utf-8')
        filename.chmod(0o600)
        return {'path': str(filename), 'report': report, 'health': health}
