import configparser
import hashlib
import os
import shlex
import tempfile
import time
from pathlib import Path

import psutil

from bc250cc.infrastructure.core_unlock_trust import (
    REVIEWED_REVISION as CORE_UNLOCK_REVIEWED_REVISION,
)
from bc250cc.infrastructure.core_unlock_trust import (
    REVIEWED_SCRIPT_SHA256 as CORE_UNLOCK_REVIEWED_SCRIPT_SHA256,
)
from bc250cc.infrastructure.cpu_command_policy import (
    build_detect_command,
    build_disable_command,
    build_scale_command,
    validate_detection_target,
    validate_scale_target,
)
from bc250cc.infrastructure.cpu_detection_policy import classify_cpu_detection
from bc250cc.infrastructure.cpu_live_test_policy import classify_cpu_live_test
from bc250cc.infrastructure.cpu_oc_config import estimated_vid as estimate_cpu_vid
from bc250cc.infrastructure.cpu_oc_config import read_cpu_oc_config
from bc250cc.infrastructure.cpu_persistence_state import (
    classify_cpu_persistence_service,
)
from bc250cc.infrastructure.cpu_runtime_snapshot import read_cpu_runtime_snapshot
from bc250cc.infrastructure.cpu_telemetry import build_cpu_telemetry
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS
from bc250cc.infrastructure.hardware_identity import is_bc250_platform
from bc250cc.platform.init.services import (
    detect_init_manager,
    parse_openrc_runlevel,
    parse_openrc_status,
    service_key,
)

CORE_UNLOCK_REPOSITORY = EXTERNAL_TOOLS['core_unlock'].upstream
CORE_UNLOCK_DIRECTORY = 'bc250-core-unlock'
CORE_UNLOCK_SCRIPT = 'bc250-unlock-cores.py'
CORE_UNLOCK_ORIGINS = {
    CORE_UNLOCK_REPOSITORY,
    f'{CORE_UNLOCK_REPOSITORY}.git',
}

class CPURepository:
    _CPU_OC_SYSTEM_CONFIG = Path('/etc/bc250-smu-oc.conf')
    _CPU_OC_SERVICE = 'bc250-smu-oc.service'
    _SCALE_OVERRIDE_CONFIRM_DELTA = 2
    _SCALE_OVERRIDE_EXTREME_DELTA = 6
    _SCALE_UPSTREAM_MIN = -50
    _SCALE_UPSTREAM_MAX = 0
    _VID_UPSTREAM_MAX = 1325

    @staticmethod
    def _estimated_vid(frequency, scale):
        """Return the voltage-curve estimate used by upstream bc250_smu_oc.

        The persistent backend stores a scale, not the VID limit originally
        supplied to ``bc250_detect``.  Keep the distinction explicit so the UI
        never presents this calculated value as a measured voltage.
        """
        return estimate_cpu_vid(frequency, scale)

    @staticmethod
    def _read_cpu_oc_config(path):
        return read_cpu_oc_config(path)

    @staticmethod
    def estado_cpu_qam_runtime():
        """Read QAM's verified live profile without acquiring root authority."""
        return read_cpu_runtime_snapshot() or {}

    def _last_cpu_oc_target(self, config):
        settings = getattr(self, 'configuracion', None)
        if settings is None or not config.get('valid'):
            return {}
        try:
            root = settings.leer_config()
        except (OSError, ValueError, TypeError):
            return {}
        target = root.get('cpu_oc_last_target') if isinstance(root, dict) else None
        if not isinstance(target, dict):
            return {}
        try:
            frequency = int(target.get('frequency'))
            vid = int(target.get('vid'))
            temperature = int(target.get('temperature'))
        except (TypeError, ValueError):
            return {}
        if not (
            frequency == int(config['frequency'])
            and temperature == int(config['max_temperature'])
            and 950 <= vid <= 1325
        ):
            return {}
        return {'target_vid': vid, 'vid_source': 'saved-ui-target'}

    @classmethod
    def _scale_override_analysis(cls, frequency, reference_scale, requested_scale):
        """Validate a scale override against the value detected upstream.

        ``scale`` is an input to the upstream voltage curve, not a harmless UI
        preference. A less-negative value can materially increase estimated
        VID. Accept the real upstream -50..0 domain, reject candidates above
        the upstream VID ceiling, and expose the delta so the UI can require
        explicit confirmation instead of silently clamping the user's value.
        """
        try:
            frequency = int(frequency)
            reference_scale = int(reference_scale)
            requested_scale = int(requested_scale)
        except (TypeError, ValueError) as error:
            raise ValueError('CPU scale values must be integers') from error
        if not 3500 <= frequency <= 4200:
            raise ValueError('CPU frequency must be between 3500 and 4200 MHz')
        if not -50 <= reference_scale <= 0 or not -50 <= requested_scale <= 0:
            raise ValueError('CPU scale override must be between -50 and 0')

        allowed_min = cls._SCALE_UPSTREAM_MIN
        allowed_max = cls._SCALE_UPSTREAM_MAX
        delta = requested_scale - reference_scale
        reference_vid = cls._estimated_vid(frequency, reference_scale)
        requested_vid = cls._estimated_vid(frequency, requested_scale)
        estimated_delta = (
            requested_vid - reference_vid
            if requested_vid is not None and reference_vid is not None
            else None
        )
        within_upstream_scale = allowed_min <= requested_scale <= allowed_max
        within_upstream_vid = requested_vid is None or requested_vid <= cls._VID_UPSTREAM_MAX
        less_negative = delta > 0
        return {
            'frequency': frequency,
            'reference_scale': reference_scale,
            'requested_scale': requested_scale,
            'delta_steps': delta,
            'absolute_delta_steps': abs(delta),
            'allowed_min': allowed_min,
            'allowed_max': allowed_max,
            'allowed': bool(within_upstream_scale and within_upstream_vid),
            'blocked_reason': (
                '' if within_upstream_scale and within_upstream_vid
                else (
                    f'estimated VID ~{requested_vid} mV exceeds the upstream 1325 mV ceiling'
                    if within_upstream_scale and requested_vid is not None
                    else 'scale is outside the upstream -50..0 range'
                )
            ),
            'less_negative': less_negative,
            'requires_extra_confirmation': (
                abs(delta) > cls._SCALE_OVERRIDE_CONFIRM_DELTA or less_negative
            ),
            'requires_extreme_confirmation': (
                abs(delta) > cls._SCALE_OVERRIDE_EXTREME_DELTA
                or (requested_vid is not None and requested_vid > 1300)
            ),
            'reference_estimated_vid': reference_vid,
            'requested_estimated_vid': requested_vid,
            'estimated_vid_delta': estimated_delta,
        }

    def _remembered_scale_reference(self, parsed):
        """Return the original detected scale without drifting after overrides.

        The generated file is edited in place by the optional override.  Store
        both the original detected value and our last written value.  If the
        file later contains a different scale, ``bc250-detect`` regenerated it
        and that new value becomes the reference.
        """
        current = int(parsed['scale'])
        settings = getattr(self, 'configuracion', None)
        if settings is None:
            return current
        try:
            root = settings.leer_config()
        except (OSError, ValueError, TypeError):
            return current
        context = root.get('cpu_oc_scale_context') if isinstance(root, dict) else None
        valid_context = isinstance(context, dict)
        try:
            valid_context = valid_context and (
                int(context.get('frequency')) == int(parsed['frequency'])
                and int(context.get('temperature')) == int(parsed['max_temperature'])
                and int(context.get('last_written_scale')) == current
                and -50 <= int(context.get('detected_scale')) <= 0
            )
        except (TypeError, ValueError):
            valid_context = False
        if valid_context:
            return int(context['detected_scale'])
        self._store_scale_context(parsed, detected_scale=current, last_written_scale=current)
        return current

    def _store_scale_context(self, parsed, *, detected_scale, last_written_scale):
        settings = getattr(self, 'configuracion', None)
        if settings is None:
            return
        context = {
            'frequency': int(parsed['frequency']),
            'temperature': int(parsed['max_temperature']),
            'detected_scale': int(detected_scale),
            'last_written_scale': int(last_written_scale),
        }
        try:
            settings.guardar_config({'cpu_oc_scale_context': context})
        except (OSError, ValueError, TypeError):
            # A failure to remember UI context must never bypass validation:
            # the immediate parsed scale remains the conservative reference.
            return

    @staticmethod
    def _cpu_oc_config_digest(path):
        """Return a digest for the exact upstream detection result on disk.

        A detection run rewrites ``overclock.conf`` as it finds safe steps.
        Binding persistence to the exact bytes from the completed run prevents
        a later throttled/older/manual result from silently becoming the scale
        reference shown to the user.
        """
        path = Path(path)
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise RuntimeError(f'Could not fingerprint CPU OC configuration: {error}') from error
        if len(payload) > 64 * 1024:
            raise RuntimeError('CPU OC configuration is unexpectedly large.')
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _current_boot_id():
        """Return Linux's current boot identity without invoking a subprocess."""
        try:
            value = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
        except OSError:
            return ''
        return value if len(value) <= 128 else ''

    def registrar_resultado_deteccion_cpu(self, target=None):
        """Snapshot the exact ``bc250-detect`` result that just completed.

        ``bc250-detect`` may legitimately produce different scale/frequency
        results between thermally different runs.  Persist a run identity, not
        merely a remembered numeric scale, so the next boot-persistence action
        can prove which completed run it is installing.
        """
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError('The local bc250_smu_oc repository was not found. Use Prepare dependencies first.')
        config = Path(tools['smu_oc_path']) / 'overclock.conf'
        parsed = self._read_cpu_oc_config(config)
        if not parsed.get('valid'):
            raise RuntimeError(parsed.get('error') or 'overclock.conf is invalid after bc250-detect')

        target = target if isinstance(target, dict) else {}
        digest = self._cpu_oc_config_digest(config)
        snapshot = {
            'run_id': str(time.time_ns()),
            'recorded_at_epoch_ns': time.time_ns(),
            'boot_id': self._current_boot_id(),
            'config_path': str(config),
            # Keep the immutable detector output fingerprint separately from
            # the expected current config. A user-approved scale override is
            # allowed to change the latter without losing the identity of the
            # stress-tested detection run that remains the safety reference.
            'detected_config_sha256': digest,
            'config_sha256': digest,
            'frequency': int(parsed['frequency']),
            'scale': int(parsed['scale']),
            'current_scale': int(parsed['scale']),
            'temperature': int(parsed['max_temperature']),
            'estimated_vid': parsed.get('estimated_vid'),
        }
        for source, destination in (
            ('frequency', 'requested_frequency'),
            ('vid', 'requested_vid'),
            ('temperature', 'requested_temperature'),
        ):
            try:
                value = int(target[source])
            except (KeyError, TypeError, ValueError):
                continue
            snapshot[destination] = value

        settings = getattr(self, 'configuracion', None)
        if settings is not None:
            settings.guardar_config({
                'cpu_oc_detection_run': snapshot,
                'cpu_oc_scale_context': {
                    'frequency': int(parsed['frequency']),
                    'temperature': int(parsed['max_temperature']),
                    'detected_scale': int(parsed['scale']),
                    'last_written_scale': int(parsed['scale']),
                },
                # A fresh detector run invalidates every previously applied
                # manual scale candidate, even when the numeric values happen
                # to be identical. Boot persistence must bind to this run.
                'cpu_oc_scale_live_test': {},
            })
        return dict(snapshot)

    def estado_resultado_deteccion_cpu(self):
        """Return the last recorded detection run and whether it still matches disk."""
        tools = self.estado_herramientas_bc250()
        config = (
            Path(tools['smu_oc_path']) / 'overclock.conf'
            if tools.get('smu_oc_exists')
            else None
        )
        parsed = self._read_cpu_oc_config(config) if config is not None else {
            'exists': False, 'valid': False, 'error': 'bc250_smu_oc repository is unavailable.'
        }
        settings = getattr(self, 'configuracion', None)
        root = {}
        if settings is not None:
            try:
                root = settings.leer_config()
            except (OSError, ValueError, TypeError):
                root = {}
        snapshot = root.get('cpu_oc_detection_run') if isinstance(root, dict) else None
        snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
        digest = ''
        if parsed.get('valid') and config is not None:
            try:
                digest = self._cpu_oc_config_digest(config)
            except RuntimeError:
                digest = ''
        return classify_cpu_detection(snapshot, parsed, digest, self._current_boot_id())

    def _persistence_scale_reference(self, parsed, config):
        """Resolve the safe reference and reject a stale recorded run.

        Backward compatibility is intentionally retained for users who ran
        upstream ``bc250-detect`` outside Control Center: when no app snapshot
        exists, the current valid ``overclock.conf`` is accepted as an external
        result.  Once Control Center has recorded a run, however, a mismatch is
        never silently accepted.
        """
        state = self.estado_resultado_deteccion_cpu()
        snapshot = state.get('snapshot') or {}
        if state.get('recorded'):
            if not state.get('matches_current_config'):
                raise RuntimeError(
                    'The CPU detection result changed after the last completed bc250-detect run. '
                    'Run the temporary CPU detection again before enabling persistence so the '
                    'exact frequency, scale and temperature being installed can be verified.'
                )
            if not state.get('detector_evidence_pristine'):
                raise RuntimeError(
                    'This detection record comes from an older Control Center build that modified '
                    'the detector overclock.conf in place after a scale override. Run bc250-detect '
                    'once more with this version to create pristine detector evidence before testing '
                    'or enabling persistence.'
                )
            return int(snapshot['scale']), 'recorded-detection-run', state
        return self._remembered_scale_reference(parsed), 'external-current-config', state

    def evaluar_override_escala_cpu(self, scale_override, frequency_override=None):
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError('The local bc250_smu_oc repository was not found. Use Prepare dependencies first.')
        config = Path(tools['smu_oc_path']) / 'overclock.conf'
        parsed = self._read_cpu_oc_config(config)
        if not parsed.get('valid'):
            raise RuntimeError(parsed.get('error') or 'overclock.conf is invalid')
        reference, reference_source, detection_state = self._persistence_scale_reference(parsed, config)
        if not detection_state.get('recorded') or not (detection_state.get('snapshot') or {}):
            raise RuntimeError(
                'Manual CPU scale testing requires a bc250-detect run recorded by Control Center. '
                'Run bc250-detect from this page first so the manual test can be bound to exact detector evidence.'
            )
        candidate_frequency = (
            int(parsed['frequency']) if frequency_override is None else int(frequency_override)
        )
        analysis = self._scale_override_analysis(candidate_frequency, reference, scale_override)
        analysis['detected_frequency'] = int(parsed['frequency'])
        analysis['config_path'] = str(config)
        analysis['reference_source'] = reference_source
        analysis['detection_run'] = detection_state.get('snapshot') or {}
        if not analysis['allowed']:
            raise ValueError(
                'CPU scale override is unsafe: '
                f"{analysis['requested_scale']} requested; {analysis.get('blocked_reason') or 'outside validated limits'}. "
                f"Detected reference is {analysis['reference_scale']}."
            )
        return analysis

    def evaluar_aplicacion_manual_cpu(self, frequency, scale, temperature):
        """Validate a direct, temporary CPU scale without detector evidence.

        This path is intentionally session-only.  It uses the same absolute
        upstream limits as the privileged helper, but cannot later authorize
        boot persistence because no automatic detector reference exists.
        """
        target = validate_scale_target(frequency, scale, temperature)
        return {
            'frequency': target.frequency,
            'scale': target.scale,
            'temperature': target.temperature,
            'estimated_vid': target.estimated_vid,
            'requires_confirmation': True,
            'persistence_eligible': False,
            'reference_source': 'manual-direct',
        }

    @staticmethod
    def _write_cpu_candidate_config(path, *, frequency, scale, temperature):
        """Write an exact CPU config candidate without touching detector output.

        ``overclock.conf`` is evidence from ``bc250-detect`` and must remain
        byte-for-byte stable after a recorded run. Manual live tests and boot
        persistence use separate candidate files so a scale experiment can
        never silently mutate the detector result that authorizes it.
        """
        path = Path(path)
        target = validate_scale_target(frequency, scale, temperature)

        parser = configparser.ConfigParser(interpolation=None)
        parser['overclock'] = {
            'frequency': str(target.frequency),
            'scale': str(target.scale),
            'max_temperature': str(target.temperature),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f'.{path.name}.', suffix='.tmp', dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
                parser.write(file)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return CPURepository._read_cpu_oc_config(path)

    def _live_scale_test_state(self):
        settings = getattr(self, 'configuracion', None)
        if settings is None:
            return {}
        try:
            root = settings.leer_config()
        except (OSError, ValueError, TypeError):
            return {}
        state = root.get('cpu_oc_scale_live_test') if isinstance(root, dict) else None
        return dict(state) if isinstance(state, dict) else {}

    def registrar_prueba_escala_cpu(
        self, scale_override, frequency_override=None, temperature_override=None
    ):
        """Record a successful *live apply* of an exact manual scale candidate.

        Success here means the helper applied the requested values and exited
        cleanly. It deliberately does not claim long-term stability. The UI
        still asks the user to complete their real workload/stress validation
        before enabling boot persistence.
        """
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError('The local bc250_smu_oc repository was not found. Use Prepare dependencies first.')
        config = Path(tools['smu_oc_path']) / 'overclock.conf'
        parsed = self._read_cpu_oc_config(config)
        if not parsed.get('valid'):
            raise RuntimeError(parsed.get('error') or 'overclock.conf is invalid')
        reference, reference_source, detection_state = self._persistence_scale_reference(parsed, config)
        if not detection_state.get('recorded') or not (detection_state.get('snapshot') or {}):
            raise RuntimeError(
                'Manual CPU scale testing requires a bc250-detect run recorded by Control Center. '
                'Run bc250-detect from this page first so the manual test can be bound to exact detector evidence.'
            )
        candidate_frequency = (
            int(parsed['frequency']) if frequency_override is None else int(frequency_override)
        )
        candidate_temperature = (
            int(parsed['max_temperature'])
            if temperature_override is None else int(temperature_override)
        )
        analysis = self._scale_override_analysis(candidate_frequency, reference, scale_override)
        if not analysis['allowed']:
            raise ValueError(analysis.get('blocked_reason') or 'CPU scale override is unsafe')
        self._write_cpu_candidate_config(
            Path(tools['smu_oc_path']) / 'overclock.live.conf',
            frequency=candidate_frequency,
            scale=analysis['requested_scale'],
            temperature=candidate_temperature,
        )
        snapshot = detection_state.get('snapshot') or {}
        live_state = {
            'test_id': str(time.time_ns()),
            'applied_at_epoch_ns': time.time_ns(),
            'boot_id': self._current_boot_id(),
            'detection_run_id': str(snapshot.get('run_id') or 'external-current-config'),
            'detected_config_sha256': str(
                snapshot.get('detected_config_sha256')
                or detection_state.get('current_sha256')
                or self._cpu_oc_config_digest(config)
            ),
            'frequency': candidate_frequency,
            'temperature': candidate_temperature,
            'detected_frequency': int(parsed['frequency']),
            'detected_temperature': int(parsed['max_temperature']),
            'detected_scale': int(reference),
            'scale': int(scale_override),
            'estimated_vid': analysis.get('requested_estimated_vid'),
            'estimated_vid_delta': analysis.get('estimated_vid_delta'),
            'reference_source': reference_source,
            'persistence_eligible': True,
            'result': 'applied-live',
        }
        settings = getattr(self, 'configuracion', None)
        if settings is not None:
            settings.guardar_config({'cpu_oc_scale_live_test': live_state})
        return dict(live_state)

    def estado_prueba_escala_cpu(
        self, scale_override=None, frequency_override=None, temperature_override=None
    ):
        """Return whether a live scale test still belongs to the current detection."""
        state = self._live_scale_test_state()
        detection = self.estado_resultado_deteccion_cpu()
        return classify_cpu_live_test(
            state,
            detection,
            self._current_boot_id(),
            requested_scale=scale_override,
            requested_frequency=frequency_override,
            requested_temperature=temperature_override,
        )

    def preparar_evidencia_persistencia_escala_cpu(
        self, scale_override, frequency_override, temperature_override
    ):
        """Promote same-boot direct evidence from the previous UI revision.

        The one-button manual workflow briefly recorded every successful
        direct apply as session-only, even when a pristine detector result was
        already available.  At the user's explicit Save-for-boot action we can
        safely bind that legacy record without touching hardware: it must be
        an exact, same-boot successful apply and the current detector evidence
        must still pass the normal immutable-config checks.
        """
        state = self.estado_prueba_escala_cpu(
            scale_override, frequency_override, temperature_override
        )
        if state.get('valid_for_persistence'):
            return state
        if not (
            state.get('direct_manual')
            and state.get('active_in_current_session')
            and state.get('exact_scale')
            and state.get('exact_frequency')
            and state.get('exact_temperature')
        ):
            return state
        try:
            self.registrar_prueba_escala_cpu(
                scale_override, frequency_override, temperature_override
            )
        except (OSError, RuntimeError, ValueError, configparser.Error) as exc:
            state['promotion_error'] = str(exc)
            return state
        return self.estado_prueba_escala_cpu(
            scale_override, frequency_override, temperature_override
        )

    def _core_unlock_repository_state(self, repository):
        script = repository / CORE_UNLOCK_SCRIPT
        if not (repository / '.git').is_dir() or not script.is_file():
            return '', False, False
        rc, out, _err = self._ejecutar(
            ['git', '-C', str(repository), 'remote', 'get-url', 'origin'],
            timeout=3,
        )
        origin = out.strip() if rc == 0 else ''
        rc, out, _err = self._ejecutar(
            ['git', '-C', str(repository), 'status', '--porcelain', '--untracked-files=all'],
            timeout=3,
        )
        clean = rc == 0 and not out.strip()
        rc_head, head, _err = self._ejecutar(
            ['git', '-C', str(repository), 'rev-parse', 'HEAD'],
            timeout=3,
        )
        try:
            script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
        except OSError:
            script_hash = ''
        revision_matches = (
            rc_head == 0
            and head.strip() == CORE_UNLOCK_REVIEWED_REVISION
            and script_hash == CORE_UNLOCK_REVIEWED_SCRIPT_SHA256
        )
        return origin, clean, revision_matches

    def _cpu_smu_helper_path(self):
        """Return the installed root-owned CPU/SMU execution boundary."""
        candidates = (
            Path('/usr/libexec/bc250-control-center/bc250-cpu-smu-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-cpu-smu-helper'),
        )
        for candidate in candidates:
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                continue
            if os.access(candidate, os.X_OK):
                return str(candidate)
        return ''

    def _missing_cpu_smu_helper_message(self) -> str:
        if self._es_ostree():
            return (
                'The protected CPU/SMU helper is missing from this immutable Bazzite deployment. '
                'Install or update the matching BC250 Control Center RPM with rpm-ostree, reboot, '
                'then reopen Control Center. install-local.sh cannot place protected helpers in '
                'Bazzite\'s immutable /usr tree.'
            )
        return (
            'The protected root-owned CPU/SMU helper is not installed. Reinstall the matching '
            'BC250 Control Center system package, or run scripts/install-local.sh once from this '
            'build on a mutable distribution, then reopen Control Center.'
        )

    def _core_unlock_helper_path(self):
        candidates = (
            Path('/usr/libexec/bc250-control-center/bc250-core-unlock-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-core-unlock-helper'),
        )
        for candidate in candidates:
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                continue
            if os.access(candidate, os.X_OK):
                return str(candidate)
        return ''

    def estado_desbloqueo_nucleos_cpu(self):
        logical = os.cpu_count() or 0
        physical = psutil.cpu_count(logical=False) or 0
        hardware_detected = is_bc250_platform()
        repository = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        script = repository / CORE_UNLOCK_SCRIPT
        origin, clean, revision_matches = self._core_unlock_repository_state(repository)
        repository_ready = bool(
            origin in CORE_UNLOCK_ORIGINS
            and clean
            and revision_matches
        )
        try:
            cpuinfo_text = Path('/proc/cpuinfo').read_text(encoding='utf-8', errors='replace')
        except OSError:
            cpuinfo_text = ''
        telemetry = build_cpu_telemetry(
            cpuinfo_text,
            psutil.cpu_percent(interval=None, percpu=True),
        )
        governor_services = ('cyan-skillfish-governor-smu.service', 'oberon-governor.service')
        init_manager = detect_init_manager()
        active_governors = [
            service for service in governor_services
            if self._service_state(service, 'active', init_manager.kind) == 'active'
        ]
        enabled_governors = [
            service for service in governor_services
            if self._service_state(service, 'enabled', init_manager.kind) == 'enabled'
        ]
        return {
            'physical_cores': int(physical),
            'logical_cpus': int(logical),
            'unlocked': physical >= 8 and logical >= 16,
            'supported_stock_shape': hardware_detected and physical == 6 and logical == 12,
            'hardware_detected': hardware_detected,
            'helper_ready': bool(self._core_unlock_helper_path()),
            'repository_ready': repository_ready,
            'repository_path': str(repository),
            'script_path': str(script) if script.is_file() else '',
            'repository_origin': origin,
            'repository_clean': clean,
            'repository_revision_matches': revision_matches,
            'reference_url': CORE_UNLOCK_REPOSITORY,
            'integration': 'official-upstream-clone',
            'volatile_after_power_off': True,
            'processor': telemetry['processor'],
            'cores': telemetry['cores'],
            'governor_active': bool(active_governors),
            'governor_enabled': bool(enabled_governors),
            'active_gpu_governors': active_governors,
            'enabled_gpu_governors': enabled_governors,
            'init_manager': init_manager.kind,
        }

    def comando_desbloquear_nucleos_cpu(self):
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            raise RuntimeError(
                f'CPU core unlock is not supported on {init_manager.display_name}: '
                'Control Center cannot safely stop persistent GPU governors or coordinate reboot.'
            )
        helper = self._core_unlock_helper_path()
        if not helper:
            raise RuntimeError(
                'The privileged CPU core unlock helper is not installed. '
                'Reinstall BC250 Control Center before using this action.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. It is required for CPU core unlock.')
        repository = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        script = repository / CORE_UNLOCK_SCRIPT
        if not (repository / '.git').is_dir() or not script.is_file():
            raise RuntimeError(
                'The official bc250-core-unlock repository is not prepared. '
                'Clone it from the CPU page before using this action.'
            )
        origin, clean, revision_matches = self._core_unlock_repository_state(repository)
        if origin not in CORE_UNLOCK_ORIGINS or not clean or not revision_matches:
            raise RuntimeError(
                'The official bc250-core-unlock clone did not pass origin, revision, and integrity validation.'
            )
        if script.is_symlink():
            raise RuntimeError('The upstream CPU core unlock script must not be a symbolic link.')
        metadata = script.stat(follow_symlinks=False)
        if metadata.st_uid != os.getuid():
            raise RuntimeError('The upstream CPU core unlock script does not belong to the desktop user.')
        if metadata.st_mode & 0o022:
            # Ubuntu/Mint commonly use umask 0002, which can leave a clean Git
            # checkout executable as 0775. Removing only group/other write bits
            # is a safe, local self-repair and does not alter tracked contents.
            script.chmod(metadata.st_mode & ~0o022)
            metadata = script.stat(follow_symlinks=False)
        if metadata.st_mode & 0o022:
            raise RuntimeError('The upstream CPU core unlock script permissions could not be secured.')
        return ['pkexec', helper, '--repo', str(repository), '--reboot']

    def ejecutar_cpu_oc_temporal(self, frecuencia, vid, temp=90):
        """Launch the same protected detector path used by the embedded UI.

        Older releases launched the user checkout's ``bc250_detect.py`` from
        a terminal.  Depending on how that upstream script elevated itself,
        its default configuration could land under root's home
        (``/var/roothome`` on some immutable systems), leaving the desktop
        persistence flow unable to find its evidence.  Keep the terminal UX,
        but make its execution and config destination identical to the
        root-owned helper contract.
        """
        target = validate_detection_target(frecuencia, vid, temp)
        frecuencia, vid, temp = target.frequency, target.vid, target.temperature
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError(
                'The local bc250_smu_oc repository was not found. Use Prepare dependencies first so '
                'bc250-detect and persistence share the same ResourceTools/overclock.conf.'
            )
        if not tools.get('stress'):
            stress_cmd = self._comando_instalar_stress()
            if not stress_cmd:
                raise RuntimeError('stress is missing. bc250_smu_oc needs it to detect active cores. Install the stress package and try again.')
            if self._es_ostree():
                comando = (
                    'echo "== stress is missing: installing dependency required by bc250_smu_oc =="; '
                    f'{stress_cmd}; '
                    'echo; '
                    'echo "== REBOOT REQUIRED =="; '
                    'echo "Bazzite/rpm-ostree prepared stress for the next boot."; '
                    'echo "Reboot with: systemctl reboot"; '
                    'echo "After reboot, run CPU OC again."'
                )
                return self._abrir_terminal(comando, 'Install stress for CPU OC')
            return self._abrir_terminal(
                'echo "== stress is missing: installing dependency required by bc250_smu_oc =="; '
                f'{stress_cmd}; command -v stress || exit 1; '
                'echo "Dependency installed. Start the CPU OC test again."',
                'Install stress for CPU OC',
            )

        command = self.comando_cpu_oc_temporal_embebido(frecuencia, vid, temp)
        return self._abrir_terminal(
            ' '.join(shlex.quote(str(argument)) for argument in command),
            f'CPU OC {frecuencia} MHz',
        )



    def comando_cpu_oc_temporal_embebido(self, frecuencia, vid, temp=90):
        target = validate_detection_target(frecuencia, vid, temp)
        frecuencia, vid, temp = target.frequency, target.vid, target.temperature
        if self._usar_steamos_game_helper():
            return self._comando_steamos_game_helper('cpu-oc-temp', frecuencia, vid, temp)
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to use the embedded console with graphical authentication.')

        tools = self.estado_herramientas_bc250()
        if not tools.get('stress'):
            raise RuntimeError('stress is missing. Press Prepare dependencies or install the stress package before using CPU OC.')
        if not tools.get('smu_oc_exists'):
            raise RuntimeError(
                'The local bc250_smu_oc repository was not found. Use Prepare dependencies first so '
                'bc250-detect and persistence share the same ResourceTools/overclock.conf.'
            )
        helper = self._cpu_smu_helper_path()
        if not helper:
            raise RuntimeError(self._missing_cpu_smu_helper_message())
        config_path = Path(tools['smu_oc_path']) / 'overclock.conf'
        return build_detect_command('pkexec', helper, target, config_path)


    def comando_cpu_scale_live_embebido(
        self, scale_override, confirm_scale_jump=False,
        frequency_override=None, temperature_override=None,
    ):
        """Apply an exact manual scale through the root-owned CPU helper.

        The user's ResourceTools checkout remains useful for detector evidence,
        but no Python code from that writable checkout is executed with root
        authority. ``overclock.live.conf`` is an audit/staging artifact only;
        the privileged helper rebuilds the exact numeric candidate itself.
        """
        if self._usar_steamos_game_helper():
            raise RuntimeError(
                'Manual CPU scale live testing currently requires Desktop Mode. '
                'The passwordless Game Mode helper intentionally does not accept arbitrary scale overrides.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to authenticate live CPU scale tests.')
        helper = self._cpu_smu_helper_path()
        if not helper:
            raise RuntimeError(self._missing_cpu_smu_helper_message())
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError('The local bc250_smu_oc repository was not found. Use Prepare dependencies first.')

        repo = Path(tools['smu_oc_path'])
        detected_config = repo / 'overclock.conf'
        parsed = self._read_cpu_oc_config(detected_config)
        if not parsed.get('valid'):
            raise RuntimeError(parsed.get('error') or 'overclock.conf is invalid')

        reference_scale, _reference_source, detection_state = self._persistence_scale_reference(
            parsed, detected_config
        )
        if not detection_state.get('recorded') or not (detection_state.get('snapshot') or {}):
            raise RuntimeError(
                'Manual CPU scale testing requires a bc250-detect run recorded by Control Center. '
                'Run bc250-detect from this page first.'
            )
        candidate_frequency = (
            int(parsed['frequency']) if frequency_override is None else int(frequency_override)
        )
        candidate_temperature = (
            int(parsed['max_temperature'])
            if temperature_override is None else int(temperature_override)
        )
        analysis = self._scale_override_analysis(candidate_frequency, reference_scale, scale_override)
        if not analysis['allowed']:
            raise ValueError(
                'CPU scale override is unsafe: '
                f"{analysis['requested_scale']} requested; {analysis.get('blocked_reason') or 'outside validated limits'}."
            )
        if analysis['requires_extra_confirmation'] and not confirm_scale_jump:
            raise ValueError('CPU scale live test requires explicit confirmation for this voltage-curve change')

        live_config = repo / 'overclock.live.conf'
        candidate = self._write_cpu_candidate_config(
            live_config,
            frequency=candidate_frequency,
            scale=analysis['requested_scale'],
            temperature=candidate_temperature,
        )
        target = validate_scale_target(
            candidate['frequency'], candidate['scale'], candidate['max_temperature']
        )
        return build_scale_command('pkexec', helper, 'apply-live', target)

    def comando_cpu_oc_manual_embebido(
        self, frequency, scale, temperature=90, confirm_manual=False,
    ):
        """Apply frequency + exact scale directly for the current session."""
        analysis = self.evaluar_aplicacion_manual_cpu(
            frequency, scale, temperature
        )
        if not confirm_manual:
            raise ValueError(
                'Direct manual CPU scale application requires explicit confirmation'
            )
        if self._usar_steamos_game_helper():
            raise RuntimeError(
                'Direct manual CPU scale currently requires Desktop Mode. '
                'The passwordless Game Mode helper does not accept arbitrary scale values.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError(
                'polkit/pkexec was not found. Install polkit to authenticate manual CPU tuning.'
            )
        helper = self._cpu_smu_helper_path()
        if not helper:
            raise RuntimeError(self._missing_cpu_smu_helper_message())
        target = validate_scale_target(
            analysis['frequency'], analysis['scale'], analysis['temperature']
        )
        return build_scale_command('pkexec', helper, 'apply-live', target)

    def registrar_aplicacion_manual_cpu(self, frequency, scale, temperature=90):
        """Record a successful direct live apply and bind safe detector evidence.

        Direct application deliberately remains available without running the
        detector first.  When a pristine ``bc250-detect`` record does exist,
        however, the exact live candidate can reuse the normal evidence path
        and become eligible for boot persistence.  A missing, stale or unsafe
        detector reference must never turn a hardware success into a failure;
        in that case the apply remains session-only.
        """
        target = validate_scale_target(frequency, scale, temperature)
        try:
            return self.registrar_prueba_escala_cpu(
                target.scale, target.frequency, target.temperature
            )
        except (OSError, RuntimeError, ValueError, configparser.Error) as exc:
            persistence_blocker = str(exc)
        live_state = {
            'test_id': str(time.time_ns()),
            'applied_at_epoch_ns': time.time_ns(),
            'boot_id': self._current_boot_id(),
            'detection_run_id': '',
            'detected_config_sha256': '',
            'frequency': target.frequency,
            'temperature': target.temperature,
            'scale': target.scale,
            'estimated_vid': target.estimated_vid,
            'reference_source': 'manual-direct',
            'persistence_eligible': False,
            'persistence_blocker': persistence_blocker,
            'result': 'applied-live',
        }
        settings = getattr(self, 'configuracion', None)
        if settings is not None:
            settings.guardar_config({'cpu_oc_scale_live_test': live_state})
        return dict(live_state)


    def comando_cpu_oc_persistente_embebido(
        self, scale_override=None, confirm_scale_jump=False,
        frequency_override=None, temperature_override=None,
    ):
        game_mode = self._usar_steamos_game_helper()
        if game_mode and scale_override is not None:
            raise RuntimeError(
                'Manual CPU scale persistence from Game Mode is not available through the '
                'passwordless helper. Apply and validate the exact manual candidate in '
                'Desktop Mode, then install the service there.'
            )
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            raise RuntimeError(
                f'CPU boot persistence is not supported on {init_manager.display_name}. '
                'Temporary CPU tuning remains available.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to authenticate persistent changes.')
        helper = self._cpu_smu_helper_path()
        if not helper:
            raise RuntimeError(self._missing_cpu_smu_helper_message())
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError('The local bc250_smu_oc repository was not found. Use Prepare dependencies first.')

        repo = Path(tools['smu_oc_path'])
        detected_config = repo / 'overclock.conf'
        if not detected_config.exists():
            raise RuntimeError('overclock.conf was not found. First apply and test a temporary CPU OC with bc250-detect.')

        parsed = self._read_cpu_oc_config(detected_config)
        if not parsed.get('valid'):
            raise RuntimeError(parsed.get('error') or 'overclock.conf is invalid')
        _reference_scale, _reference_source, detection_state = self._persistence_scale_reference(
            parsed, detected_config
        )
        install_values = dict(parsed)

        if scale_override is not None:
            analysis = self.evaluar_override_escala_cpu(scale_override, frequency_override)
            if analysis['requires_extra_confirmation'] and not confirm_scale_jump:
                raise ValueError('CPU scale persistence requires explicit confirmation for this voltage-curve change')
            candidate_frequency = (
                int(parsed['frequency']) if frequency_override is None else int(frequency_override)
            )
            candidate_temperature = (
                int(parsed['max_temperature'])
                if temperature_override is None else int(temperature_override)
            )
            live_state = self.estado_prueba_escala_cpu(
                scale_override, candidate_frequency, candidate_temperature
            )
            if not live_state.get('valid_for_persistence'):
                raise RuntimeError(
                    'This manual scale has not been applied live against the current bc250-detect run. '
                    'Apply the selected manual OC temporarily, verify stability, then enable boot persistence.'
                )
            install_source = repo / 'overclock.persist.conf'
            install_values = self._write_cpu_candidate_config(
                install_source,
                frequency=candidate_frequency,
                scale=analysis['requested_scale'],
                temperature=candidate_temperature,
            )

        target = validate_scale_target(
            install_values['frequency'],
            install_values['scale'],
            install_values['max_temperature'],
        )
        if game_mode:
            return self._comando_steamos_game_helper(
                'cpu-oc-service', 'install',
                target.frequency, target.scale, target.temperature,
            )
        return build_scale_command('pkexec', helper, 'install-boot', target)


    def estado_cpu_oc_persistente(self):
        """Return the real boot-persistence state without touching hardware.

        The CPU page refreshes this method together with passive telemetry.  It
        must therefore remain a read-only repository contract: inspect the
        generated config and systemd metadata, but never start/stop/apply the
        service as a side effect of a refresh.

        ``bc250-smu-oc.service`` is installed by the hardened helper as a
        one-shot unit.  A successful one-shot is expected to be
        ``inactive (dead)`` after it exits; that state is healthy when systemd
        reports Result=success / ExecMainStatus=0.
        """
        init_manager = detect_init_manager()
        servicio = 'bc250-smu-oc' if init_manager.kind == 'openrc' else self._CPU_OC_SERVICE
        if init_manager.kind == 'openrc':
            service_path = Path('/etc/init.d') / servicio
            existe_servicio = service_path.is_file() and not service_path.is_symlink()
            config = self._read_cpu_oc_config(self._CPU_OC_SYSTEM_CONFIG)
            config.update(self._last_cpu_oc_target(config))
            existe_config = bool(config.get('exists'))
            rc_enabled, out_enabled, err_enabled = self._ejecutar(['rc-update', 'show', 'default'], timeout=3)
            rc_active, out_active, err_active = self._ejecutar(['rc-service', servicio, 'status'], timeout=3)
            habilitado = 'enabled' if parse_openrc_runlevel(out_enabled, servicio) else 'disabled'
            activo = parse_openrc_status(rc_active, out_active or err_active)
            # OpenRC's one-shot script has no systemd Result/ExecMainStatus.
            # Presence of a validated profile plus enablement is the only safe
            # boot-persistence claim; we do not pretend it was applied now.
            result = 'failed' if activo == 'failed' else ''
            service_state = classify_cpu_persistence_service(
                habilitado, activo,
                {'ActiveState': activo, 'Result': result},
                out_active or err_active or '', existe_config,
            )
            return {
                'service': servicio,
                'exists': existe_servicio,
                'config_exists': existe_config,
                'active': activo,
                'enabled': habilitado,
                **service_state,
                'status_code': rc_active,
                'status_text': out_active or err_active or '',
                'config': config,
                'config_valid': bool(config.get('valid')),
                'config_error': str(config.get('error') or ''),
                'init_manager': 'openrc',
                'persistence_supported': True,
                'persistence_detail': init_manager.persistence_detail,
                'enabled_status_code': rc_enabled,
                'enabled_status_text': out_enabled or err_enabled or '',
            }
        if init_manager.kind != 'systemd':
            config = self._read_cpu_oc_config(self._CPU_OC_SYSTEM_CONFIG)
            config.update(self._last_cpu_oc_target(config))
            detail = init_manager.persistence_detail
            return {
                'service': '',
                'exists': False,
                'config_exists': bool(config.get('exists')),
                'active': 'unknown',
                'enabled': 'unsupported',
                'active_state': 'unknown',
                'sub_state': '',
                'result': '',
                'exec_status': '',
                'exec_code': '',
                'oneshot_ok': False,
                'applied': False,
                'applied_this_boot': False,
                'ui_state': 'Persistence unsupported',
                'ui_detail': detail,
                'last_start': '',
                'last_exit': '',
                'status_code': None,
                'status_text': detail,
                'config': config,
                'config_valid': bool(config.get('valid')),
                'config_error': str(config.get('error') or ''),
                'init_manager': init_manager.kind,
                'persistence_supported': False,
                'persistence_detail': detail,
            }
        service_paths = (
            Path('/etc/systemd/system') / servicio,
            Path('/usr/lib/systemd/system') / servicio,
            Path('/lib/systemd/system') / servicio,
        )
        existe_servicio = any(path.exists() for path in service_paths)

        config = self._read_cpu_oc_config(self._CPU_OC_SYSTEM_CONFIG)
        config.update(self._last_cpu_oc_target(config))
        existe_config = bool(config.get('exists'))

        activo = self._systemctl_valor(['is-active', servicio])
        habilitado = self._systemctl_valor(['is-enabled', servicio])
        codigo, salida, error = self._ejecutar(
            ['systemctl', 'status', servicio, '--no-pager', '--lines=8'],
            timeout=3,
        )
        texto = salida or error or ''
        props = self._systemctl_show(servicio)
        service_state = classify_cpu_persistence_service(
            habilitado, activo, props, texto, existe_config
        )

        return {
            'service': servicio,
            'exists': existe_servicio,
            'config_exists': existe_config,
            'active': activo,
            'enabled': habilitado,
            **service_state,
            'status_code': codigo,
            'status_text': texto,
            'config': config,
            'config_valid': bool(config.get('valid')),
            'config_error': str(config.get('error') or ''),
            'init_manager': init_manager.kind,
            'persistence_supported': True,
            'persistence_detail': init_manager.persistence_detail,
        }


    def comando_cpu_oc_desactivar_persistente_embebido(self):
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            raise RuntimeError(
                f'CPU boot persistence is not supported on {init_manager.display_name}; '
                'no service action was run.'
            )
        if self._usar_steamos_game_helper():
            return self._comando_steamos_game_helper('cpu-oc-service', 'remove')
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to disable the persistent service.')
        helper = self._cpu_smu_helper_path()
        if not helper:
            raise RuntimeError(self._missing_cpu_smu_helper_message())
        return build_disable_command('pkexec', helper)


    def _systemctl_valor(self, argumentos):
        codigo, salida, error = self._ejecutar(['systemctl', *argumentos], timeout=2)
        texto = (salida or error or '').strip()
        if texto:
            return texto.splitlines()[0].strip()
        return 'unknown' if codigo else 'ok'

    def _service_state(self, service, state, manager=None):
        """Read a BC250 service through its active init-system contract."""
        manager = manager or detect_init_manager().kind
        if manager == 'systemd':
            return self._systemctl_valor(['is-active' if state == 'active' else 'is-enabled', service])
        if manager != 'openrc':
            return 'unknown'
        key = service_key(service)
        if state == 'active':
            code, out, err = self._ejecutar(['rc-service', key, 'status'], timeout=2)
            return parse_openrc_status(code, out or err)
        _code, out, _err = self._ejecutar(['rc-update', 'show', 'default'], timeout=2)
        return 'enabled' if parse_openrc_runlevel(out, key) else 'disabled'

    def _systemctl_show(self, servicio):
        props = [
            'ActiveState', 'SubState', 'UnitFileState', 'Result',
            'ExecMainStatus', 'ExecMainCode', 'ExecMainStartTimestamp', 'ExecMainExitTimestamp'
        ]
        _codigo, salida, error = self._ejecutar(['systemctl', 'show', servicio, '--property=' + ','.join(props)], timeout=2)
        datos = {}
        texto = salida or error or ''
        for linea in texto.splitlines():
            if '=' not in linea:
                continue
            clave, valor = linea.split('=', 1)
            datos[clave.strip()] = valor.strip()
        return datos
