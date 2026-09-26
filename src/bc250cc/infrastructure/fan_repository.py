import json
import logging
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

from bc250cc.infrastructure.fan_transport import (
    PWMTransport,
    PWMTransportSignals,
    select_pwm_transport,
    validate_pwm_request,
)
from bc250cc.infrastructure.governor_config_request import plan_governor_config_request
from bc250cc.infrastructure.polkit_session import normalize_polkit_error, pkexec_argv
from bc250cc.infrastructure.steamos_shell import wrap_steamos_writable_command
from bc250cc.infrastructure.system_fan_control import read_system_fan_control
from bc250cc.platform.init.services import detect_init_manager
from bc250cc.shared.failure_text import describe_failure

logger = logging.getLogger(__name__)

# The NCT6687 controller can acknowledge ``pwmN_enable=1`` before the manual
# duty register is ready.  A direct desktop-mode write must therefore use the
# same phased settle/retry behaviour as the privileged helpers.
PWM_MODE_SETTLE_SECONDS = 0.20
PWM_VERIFY_ATTEMPTS = 6
PWM_VERIFY_INTERVAL_SECONDS = 0.05
PWM_DUTY_VERIFY_ATTEMPTS = 16
PWM_DUTY_VERIFY_INTERVAL_SECONDS = 0.10


class FanRepository:
    def estado_fans_bc250(self):
        sensores = self._leer_sensores_nct()
        modulos = self._modulos_nct()
        pwm_ready = any(
            item.get('writable') or item.get('root_writable')
            for item in sensores.get('pwms', [])
        ) or any(
            item.get('pwm_writable') or item.get('pwm_root_writable')
            for item in sensores.get('fans', [])
        )
        return {
            'sensores': sensores,
            'modulos': modulos,
            'driver_lectura': bool(modulos.get('nct6683')),
            # Loading nct6687 alone is not proof that PWM control is usable.
            # nct6683 can win the device, or the hwmon can be incomplete.
            'driver_control': bool(pwm_ready),
            'resumen': self._resumen_fan(sensores, modulos),
        }

    def cargar_nct6683_solo_lectura(self):
        comando_instalar = self._comando_instalar_lm_sensors()
        comando = '; '.join([
            'set +e',
            'echo "== BC250 fan sensors: read-only nct6683 =="',
            'echo "This enables temperatures, voltages and fan RPM monitoring only."',
            comando_instalar,
            'echo "== Configuring read-only module =="',
            'sudo modprobe -r nct6687 2>/dev/null || true',
            'sudo modprobe nct6683 force=true || true',
            "echo nct6683 | sudo tee /etc/modules-load.d/nct6683.conf >/dev/null",
            "echo 'options nct6683 force=true' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            "sudo rm -f /etc/modules-load.d/nct6687.conf",
            "sudo rm -f /etc/modprobe.d/nct6687.conf",
            'if command -v dracut >/dev/null 2>&1 && [ -d /boot ]; then sudo dracut --force 2>/dev/null || true; fi',
            'if command -v mkinitcpio >/dev/null 2>&1; then sudo mkinitcpio -P 2>/dev/null || true; fi',
            'echo "OK: nct6683 configured for read-only monitoring."',
            'echo "Reboot if sensors do not show nct6686-isa-0a20."',
            'sensors | sed -n "/nct668/,+35p" || true',
        ])
        comando = wrap_steamos_writable_command(comando, family=self._os_repository().info.family)
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan sensors')

    def _nct_service_commands(self) -> dict[str, str]:
        """The service commands for the init manager that is actually running.

        These were five separate copies of the same
        ``[ -f /run/openrc/softlevel ] && ... ; else systemctl ...`` written
        inline in generated bash, in a file that already imports
        ``detect_init_manager`` and uses it twice. Each copy could drift on its
        own, none of them handled runit/s6/dinit, and the detection they
        performed had already been performed in Python moments earlier.
        """
        openrc = detect_init_manager().kind == "openrc"
        helper_path = "/usr/libexec/bc250-control-center/bc250-openrc-service-helper"
        if openrc:
            return {
                "restart": (
                    "sudo rc-service nct6687-load restart 2>/dev/null "
                    "|| sudo rc-service nct6687-load start 2>/dev/null || true"
                ),
                "status": "rc-service nct6687-load status 2>/dev/null || true",
                "logs": "rc-service nct6687-load status 2>/dev/null || true",
                "remove": (
                    f"sudo {helper_path} remove nct6687-load 2>/dev/null || true"
                ),
                "reload": "true",
            }
        return {
            "restart": (
                "sudo systemctl reset-failed nct6687-load.service 2>/dev/null || true; "
                "sudo systemctl restart nct6687-load.service 2>/dev/null "
                "|| sudo systemctl start nct6687-load.service 2>/dev/null || true"
            ),
            "status": "systemctl status nct6687-load.service --no-pager 2>/dev/null || true",
            "logs": (
                "journalctl -u nct6687-load.service -b --no-pager | tail -120 "
                "2>/dev/null || true"
            ),
            "remove": (
                "sudo systemctl disable --now nct6687-load.service 2>/dev/null || true; "
                "sudo rm -f /etc/systemd/system/nct6687-load.service"
            ),
            "reload": "sudo systemctl daemon-reload 2>/dev/null || true",
        }

    def _comando_preparar_nct6687_control_pwm(self):
        servicios = self._nct_service_commands()
        os_repository = self._os_repository()
        comando_instalar = os_repository.install_fan_pwm_command(
            str(self._tool_dir() / 'nct6687d')
        ).strip().rstrip(';')
        if not comando_instalar:
            raise RuntimeError(
                'No compatible installer found for nct6687. Install Fred78290/nct6687d manually, '
                'then load nct6687 with force=true.'
            )
        comando_servicio = os_repository.install_fan_persistence_command(
            str(self._tool_dir() / 'nct6687d')
        ).strip().rstrip(';')
        comandos = [
            'echo "== BC250 fan control: nct6687 PWM driver =="',
            'echo "nct6687 is an out-of-tree driver. Reboot may be required after install."',
        ]
        if os_repository.info.family == 'bazzite':
            comandos.extend([
                (
                    'bc250_step_status=0; set +e; '
                    + comando_instalar
                    + '; bc250_step_status=$?; set -e; '
                    + 'if [ "$bc250_step_status" -eq 20 ]; then '
                    + 'BC250_REBOOT_REQUIRED=1; '
                    + 'echo "The Bazzite fan build dependencies were staged successfully."; '
                    + 'elif [ "$bc250_step_status" -ne 0 ]; then exit "$bc250_step_status"; fi'
                ),
                (
                    'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then '
                    'echo "Reboot once, then press Prepare PWM driver again to build for the active kernel."; '
                    'exit 0; fi'
                ),
            ])
        else:
            comandos.append(comando_instalar)

        comandos.extend([
            'echo "== Configuring module preference =="',
            'echo "Please wait and do not close this terminal. Configuring the boot loader can take up to one minute."',
            "echo 'blacklist nct6683' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            "echo 'options nct6687 force=true' | sudo tee /etc/modprobe.d/nct6687.conf >/dev/null",
            "printf 'blacklist nct6683\\noptions nct6687 force=true\\n' | sudo tee /etc/modprobe.d/sensors.conf >/dev/null",
            "sudo rm -f /etc/modules-load.d/nct6683.conf",
            "echo nct6687 | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null",
            "echo nct6687 | sudo tee /etc/modules-load.d/99-sensors.conf >/dev/null",
            'sudo modprobe -r nct6683 2>/dev/null || true',
            'sudo modprobe nct6687 force=true 2>/dev/null || sudo modprobe nct6687 2>/dev/null || true',
            comando_servicio,
            servicios['restart'],
            'echo "== Verification =="',
            servicios['status'],
            'lsmod | grep -E "nct6683|nct6687" || true',
            'sensors | sed -n "/nct668/,+45p" || true',
            'echo',
            '''bc250_nct6687_ready() { for n in /sys/class/hwmon/hwmon*/name; do [ -r "$n" ] || continue; name="$(cat "$n" 2>/dev/null || true)"; case "$name" in nct668*|nct67*|nct*) dir="${n%/name}"; ls "$dir"/fan*_input "$dir"/pwm* >/dev/null 2>&1 && return 0 ;; esac; done; sensors 2>/dev/null | awk '/nct6686-isa/{seen=1} seen && /(Fan|fan|pwm)[ #0-9]*:/ {ok=1} END{exit ok?0:1}'; }''',
            'if bc250_nct6687_ready; then echo "OK: nct6687 is loaded and the NCT fan/PWM hwmon is ready."; '
            'else echo "ERROR: nct6687 is not exposing the NCT fan/PWM hwmon yet."; '
            f"{servicios['logs']}; exit 1; fi",
            'echo "If PWM files remain read-only after a successful check, reboot once and verify the loaded module."',
        ])
        return '; '.join(comandos)

    def preparar_nct6687_control_pwm(self):
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            raise RuntimeError(
                f'NCT6687 boot persistence is not supported on {init_manager.display_name}. '
                'Live fan/RPM/PWM discovery remains available; no service command was generated.'
            )
        comando = '; '.join((
            'set -Eeuo pipefail',
            'BC250_REBOOT_REQUIRED=0',
            self._comando_preparar_nct6687_control_pwm(),
        ))
        comando = wrap_steamos_writable_command(comando, family=self._os_repository().info.family)
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan PWM driver')

    def desactivar_nct6687_control_pwm(self):
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            raise RuntimeError(
                f'NCT6687 service removal is not supported on {init_manager.display_name}; '
                'no system service or module preference was changed.'
            )
        servicios = self._nct_service_commands()
        openrc = detect_init_manager().kind == 'openrc'
        helper_path = '/usr/libexec/bc250-control-center/bc250-openrc-service-helper'
        # The system fan control service (GitHub #15) drives the same PWM
        # channels; without the driver it has nothing to follow, so it goes
        # together with the boot restore and its policy.
        remove_restore = (
            f'sudo {helper_path} remove bc250-fan-pwm-restore 2>/dev/null || true; '
            f'sudo {helper_path} remove bc250-fan-control 2>/dev/null || true'
            if openrc else (
                'sudo systemctl disable --now bc250-fan-pwm-restore.service 2>/dev/null || true; '
                'sudo rm -f /etc/systemd/system/bc250-fan-pwm-restore.service; '
                'sudo systemctl disable --now bc250-fan-control.service 2>/dev/null || true; '
                'sudo rm -f /etc/systemd/system/bc250-fan-control.service'
            )
        )
        comando = '; '.join([
            'set +e',
            'echo "== BC250 fan control: disable nct6687 PWM setup =="',
            'echo "This disables the automatic nct6687 preference and returns to read-only nct6683 monitoring."',
            'echo "The nct6687d package is not removed; only boot/module preference files are changed."',
            servicios['remove'],
            remove_restore,
            'sudo rm -f /var/lib/bc250-control-center/fan-last-applied.json',
            'sudo rm -f /var/lib/bc250-control-center/fan-policy.json',
            "sudo rm -f /usr/local/sbin/bc250-load-nct6687",
            servicios['reload'],
            "sudo rm -f /etc/modules-load.d/nct6687.conf",
            "sudo rm -f /etc/modules-load.d/99-sensors.conf",
            "sudo rm -f /etc/modprobe.d/nct6687.conf",
            "sudo rm -f /etc/modprobe.d/nct6683.conf",
            "sudo rm -f /etc/modprobe.d/sensors.conf",
            "echo 'options nct6683 force=true' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            "echo nct6683 | sudo tee /etc/modules-load.d/nct6683.conf >/dev/null",
            'sudo modprobe -r nct6687 2>/dev/null || true',
            'sudo modprobe nct6683 2>/dev/null || true',
            'echo "== Verification =="',
            'lsmod | grep -E "nct6683|nct6687" || true',
            'sensors | sed -n "/nct668/,+35p" || true',
            'echo "If the module state does not change immediately, reboot."',
        ])
        comando = wrap_steamos_writable_command(
            comando, family=self._os_repository().info.family
        )
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan PWM disable')

    @staticmethod
    def _write_pwm_attribute(path, value):
        flags = os.O_WRONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError('PWM attribute is not a regular sysfs file')
            content = str(value).encode('ascii')
            written = 0
            while written < len(content):
                count = os.write(descriptor, content[written:])
                if count <= 0:
                    raise OSError('PWM attribute write made no progress')
                written += count
        finally:
            os.close(descriptor)

    def _wait_for_pwm_state(self, pwm, *, value=None, enable=None):
        """Read a PWM channel until the requested hardware state settles.

        ``pwmN_enable`` and ``pwmN`` are separate controller registers.  The
        NCT6687 can briefly expose the previous duty after changing from
        automatic to manual mode, so a single immediate readback is not a
        reliable verification.  This remains deliberately bounded: callers
        get a measured failure instead of an unbounded UI stall.
        """
        expected_value = None if value is None else int(value)
        expected_enable = None if enable is None else int(enable)
        started = time.monotonic()
        observed = None
        for attempt in range(1, PWM_VERIFY_ATTEMPTS + 1):
            observed = self.leer_pwm_fan(pwm)
            value_matches = expected_value is None or observed.get('value') == expected_value
            enable_matches = expected_enable is None or observed.get('enable') == expected_enable
            if value_matches and enable_matches:
                observed['verification_attempts'] = attempt
                observed['verification_elapsed_ms'] = round((time.monotonic() - started) * 1000, 1)
                return observed
            if attempt < PWM_VERIFY_ATTEMPTS:
                time.sleep(PWM_VERIFY_INTERVAL_SECONDS)

        detail = []
        if expected_value is not None:
            detail.append(f'duty {expected_value}')
        if expected_enable is not None:
            detail.append(f'enable {expected_enable}')
        actual_value = None if observed is None else observed.get('value')
        actual_enable = None if observed is None else observed.get('enable')
        raise RuntimeError(
            f'PWM {pwm} did not settle to {" and ".join(detail)} after '
            f'{PWM_VERIFY_ATTEMPTS} attempts/{(time.monotonic() - started) * 1000:.1f} ms '
            f'(readback duty={actual_value!r}, enable={actual_enable!r}).'
        )

    def _apply_direct_pwm(self, sensor, pwm, value):
        enable = sensor / f'pwm{pwm}_enable'
        was_automatic = False
        if enable.is_file() and os.access(enable, os.W_OK):
            was_automatic = self._leer_entero(enable) == 2
            self._write_pwm_attribute(enable, '1\n')
            # Do not send a duty value while the controller is still in its
            # automatic-to-manual transition.
            time.sleep(PWM_MODE_SETTLE_SECONDS)
            try:
                self._wait_for_pwm_state(pwm, enable=1)
            except RuntimeError as error:
                rollback = ''
                if was_automatic:
                    try:
                        self._write_pwm_attribute(enable, '2\n')
                        self._wait_for_pwm_state(pwm, enable=2)
                        rollback = ' Previous automatic mode was restored.'
                    except (OSError, RuntimeError) as rollback_error:
                        rollback = f' Previous automatic-mode rollback failed: {rollback_error}.'
                raise RuntimeError(f'{error}{rollback}') from error

        # Re-write between bounded readbacks: on NCT6687 a duty sent during
        # the transition may be ignored even though the attribute write
        # returned successfully.
        started = time.monotonic()
        confirmed = None
        for attempt in range(1, PWM_DUTY_VERIFY_ATTEMPTS + 1):
            self._write_pwm_attribute(sensor / f'pwm{pwm}', f'{value}\n')
            time.sleep(PWM_DUTY_VERIFY_INTERVAL_SECONDS)
            confirmed = self.leer_pwm_fan(pwm)
            if confirmed.get('value') == value:
                confirmed['verification_attempts'] = attempt
                confirmed['verification_elapsed_ms'] = round((time.monotonic() - started) * 1000, 1)
                break
        else:
            rollback = ''
            if was_automatic:
                try:
                    self._write_pwm_attribute(enable, '2\n')
                    self._wait_for_pwm_state(pwm, enable=2)
                    rollback = ' Previous automatic mode was restored.'
                except (OSError, RuntimeError) as error:
                    rollback = f' Previous automatic-mode rollback failed: {error}.'
            raise RuntimeError(
                f'PWM {pwm} did not retain duty {value} after {PWM_DUTY_VERIFY_ATTEMPTS} '
                f'attempts/{(time.monotonic() - started) * 1000:.1f} ms '
                f'(readback was {confirmed.get("value") if confirmed else None!r}).{rollback}'
            )
        return {
            'pwm': pwm, 'valor': value, 'salida': f'OK PWM {pwm} {value}',
            'verified': confirmed,
        }

    def aplicar_pwm_fan(self, pwm, valor):
        pwm, valor = validate_pwm_request(pwm, valor)
        daemon_helper = self._usar_steamos_fan_daemon_helper()
        game_helper = not daemon_helper and self._usar_steamos_game_helper()
        initial = (
            select_pwm_transport(PWMTransportSignals(
                daemon_helper=daemon_helper, game_helper=game_helper,
            ))
            if daemon_helper or game_helper else None
        )
        if initial is PWMTransport.DAEMON_HELPER:
            output = self._ejecutar_steamos_fan_daemon_helper(pwm, valor, timeout=120)
            self.estado_herramientas_cache = None
            return self._resultado_pwm_con_lectura(pwm, valor, output)
        if initial is PWMTransport.GAME_HELPER:
            output = self._ejecutar_steamos_game_helper('fan-pwm', pwm, valor, timeout=120)
            self.estado_herramientas_cache = None
            return self._resultado_pwm_con_lectura(pwm, valor, output)

        sensor = self._sensor_nct_principal()
        path = sensor / f'pwm{pwm}' if sensor else None
        writable = bool(path and path.exists() and os.access(path, os.W_OK))
        route = select_pwm_transport(PWMTransportSignals(
            sensor_present=bool(sensor),
            channel_present=bool(path and path.exists()),
            channel_writable=writable,
            pkexec_present=bool(self._command_path('pkexec')) if not writable else False,
            python_present=bool(self._command_path('python3')) if not writable else False,
        ))
        if route is PWMTransport.DIRECT:
            try:
                return self._apply_direct_pwm(sensor, pwm, valor)
            except OSError:
                logger.debug(
                    'Direct user-writable PWM path failed; falling back to the privileged helper',
                    exc_info=True,
                )
                select_pwm_transport(PWMTransportSignals(
                    sensor_present=True, channel_present=True,
                    pkexec_present=bool(self._command_path('pkexec')),
                    python_present=bool(self._command_path('python3')),
                ))
        output = self._escribir_pwm_con_helper(pwm, valor)
        return self._resultado_pwm_con_lectura(pwm, valor, output)

    def restaurar_pwm_automatico(self, pwm):
        """Return one NCT channel to firmware automatic mode and verify it.

        Linux hwmon defines value ``2`` as automatic control for this driver.
        This is deliberately a separate operation from a duty write so callers
        cannot accidentally claim rollback while leaving manual mode enabled.
        """
        try:
            pwm = int(pwm)
        except (TypeError, ValueError):
            raise RuntimeError('Invalid PWM channel.') from None
        if pwm < 1 or pwm > 12:
            raise RuntimeError('Invalid PWM channel.')

        if self._usar_steamos_game_helper():
            output = self._ejecutar_steamos_game_helper('fan-pwm-auto', pwm, timeout=120)
        else:
            sensor = self._sensor_nct_principal()
            enable = sensor / f'pwm{pwm}_enable' if sensor else None
            if enable and enable.is_file() and os.access(enable, os.W_OK):
                self._write_pwm_attribute(enable, '2\n')
                output = f'OK PWM {pwm} AUTO'
            else:
                output = self._escribir_pwm_auto_con_helper(pwm)

        confirmed = self._wait_for_pwm_state(pwm, enable=2)
        self.estado_herramientas_cache = None
        return {'pwm': pwm, 'salida': output, 'verified': confirmed, 'automatic': True}

    def _resultado_pwm_con_lectura(self, pwm, valor, salida):
        """Attach a bounded, settled hwmon verification to helper writes.

        The privileged helpers acknowledge that a sysfs write was accepted, but
        an NCT6687 can still expose its previous duty briefly while switching
        from firmware automatic mode to manual PWM.  Returning that first
        stale read as a successful result made callers persist a fan profile
        that the controller had not actually accepted.  Keep the helper's
        acknowledgement for diagnostics, but only provide ``verified`` after
        the same bounded settle check used by the direct transport.
        """
        result = {
            'pwm': int(pwm), 'valor': int(valor), 'salida': salida,
            'verified': None,
        }
        try:
            sensor = self._sensor_nct_principal()
            enable_path = sensor / f'pwm{int(pwm)}_enable' if sensor else None
            expected_enable = 1 if enable_path and enable_path.is_file() else None
            result['verified'] = self._wait_for_pwm_state(
                pwm,
                value=valor,
                enable=expected_enable,
            )
        except RuntimeError as error:
            # Preserve helper acknowledgement while exposing a failed passive
            # verification.  Callers can show an actionable error without
            # reopening authentication or claiming that hardware changed.
            result['verification_error'] = str(error)
        return result

    def leer_pwm_fan(self, pwm):
        """Read one PWM channel without authentication for daemon verification."""
        try:
            pwm = int(pwm)
        except (TypeError, ValueError):
            raise RuntimeError('Invalid PWM channel.') from None
        if pwm < 1 or pwm > 12:
            raise RuntimeError('Invalid PWM channel.')
        sensor = self._sensor_nct_principal()
        if not sensor:
            raise RuntimeError('No NCT hwmon sensor was found.')
        path = sensor / f'pwm{pwm}'
        if not path.is_file():
            raise RuntimeError(f'{path} does not exist.')
        value = self._leer_entero(path)
        if value is None or value < 0 or value > 255:
            raise RuntimeError(f'{path} did not expose a valid PWM value.')
        enable_path = sensor / f'pwm{pwm}_enable'
        enable = self._leer_entero(enable_path) if enable_path.is_file() else None
        return {
            'pwm': pwm,
            'value': int(value),
            'percent': round(int(value) * 100 / 255),
            'path': str(path),
            'sensor_path': str(sensor),
            'enable': enable,
        }

    def _escribir_pwm_con_helper(self, pwm, valor):
        proceso = self._obtener_fan_pwm_helper()
        try:
            proceso.stdin.write(f'{int(pwm)} {int(valor)}\n')
            proceso.stdin.flush()
        except Exception:
            self.cerrar_fan_pwm_helper()
            proceso = self._obtener_fan_pwm_helper()
            proceso.stdin.write(f'{int(pwm)} {int(valor)}\n')
            proceso.stdin.flush()
        respuesta = self._leer_linea_helper(proceso, timeout=60)
        if not respuesta:
            error = self._leer_stderr_helper(proceso)
            self.cerrar_fan_pwm_helper()
            raise RuntimeError(error or 'PWM helper did not respond.')
        if respuesta.startswith('ERR '):
            raise RuntimeError(respuesta[4:].strip())
        if respuesta.startswith('OK'):
            self.estado_herramientas_cache = None
            return respuesta
        raise RuntimeError(respuesta)

    def _comando_fan_helper(self, linea, *, timeout=60):
        """Send one line to the persistent root helper session and return its reply."""
        proceso = self._obtener_fan_pwm_helper()
        try:
            proceso.stdin.write(f'{linea}\n')
            proceso.stdin.flush()
        except Exception:
            self.cerrar_fan_pwm_helper()
            proceso = self._obtener_fan_pwm_helper()
            proceso.stdin.write(f'{linea}\n')
            proceso.stdin.flush()
        respuesta = self._leer_linea_helper(proceso, timeout=timeout)
        if not respuesta:
            error = self._leer_stderr_helper(proceso)
            self.cerrar_fan_pwm_helper()
            raise RuntimeError(error or 'PWM helper did not respond.')
        if respuesta.startswith('ERR '):
            raise RuntimeError(respuesta[4:].strip())
        if respuesta.startswith('OK'):
            return respuesta
        raise RuntimeError(respuesta)

    def _requerir_helper_control_sistema(self):
        if self._fan_pwm_packaged_helper_path() is None:
            raise RuntimeError(
                'System fan control needs the installed, root-owned BC250 fan helper. '
                'Reinstall BC250 Control Center.'
            )
        # A development session may still hold the embedded helper, which
        # knows nothing about policies; start the packaged one instead.
        proceso = getattr(self, '_fan_pwm_helper', None)
        if proceso is not None and getattr(self, '_fan_pwm_helper_embedded', False):
            self.cerrar_fan_pwm_helper()

    def estado_control_fan_sistema(self):
        """Read-only: what the root fan service is doing, with no prompt."""
        snapshot = read_system_fan_control()
        snapshot['available'] = bool(
            self._fan_pwm_packaged_helper_path() is not None
            and detect_init_manager().kind in {'systemd', 'openrc'}
        )
        return snapshot

    def sincronizar_control_fan_sistema(self, politica):
        """Copy the desktop fan policy to the root service (or clear it)."""
        self._requerir_helper_control_sistema()
        if politica is None:
            return {'salida': self._comando_fan_helper('POLICY-CLEAR')}
        payload = json.dumps(politica, sort_keys=True, separators=(',', ':'))
        salida = self._comando_fan_helper(f'POLICY {payload}')
        return {'salida': salida, 'digest': salida.rsplit(' ', 1)[-1]}

    def activar_control_fan_sistema(self, politica):
        if politica is None:
            raise RuntimeError('Save a fan curve or preset before enabling system fan control.')
        resultado = self.sincronizar_control_fan_sistema(politica)
        resultado['servicio'] = self._comando_fan_helper('CONTROL ENABLE', timeout=150)
        return resultado

    def desactivar_control_fan_sistema(self):
        self._requerir_helper_control_sistema()
        return {'servicio': self._comando_fan_helper('CONTROL DISABLE', timeout=150)}

    def exportar_perfiles_fan_decky(self, profiles):
        """Publish the three fan profiles for Decky Quick Access's presets.

        Display names and speeds only, written by the same small root
        metadata writer the GPU and CPU exports use; no fan is touched here,
        and the Decky helper bounds every speed again before it applies one.
        """
        request = plan_governor_config_request("set-decky-fan-profiles", (list(profiles),))
        helper = self._governor_config_helper_path()
        if not helper:
            raise RuntimeError(
                "The privileged governor configuration helper is not installed. "
                "Reinstall BC250 Control Center locally or from its package before exporting."
            )
        rc, out, err = self._ejecutar(request.argv(helper), timeout=120)
        if rc != 0:
            if "Unsupported governor configuration action" in f"{out}\n{err}":
                # A helper installed by an older build: every other export
                # still works, this one needs the matching helper.
                raise RuntimeError(
                    "The installed privileged helper is older than this application. "
                    "Reinstall BC250 Control Center to export fan profiles to Decky."
                )
            raise RuntimeError(describe_failure(rc, out, err))
        return (out or "").strip()

    def _escribir_pwm_auto_con_helper(self, pwm):
        proceso = self._obtener_fan_pwm_helper()
        try:
            proceso.stdin.write(f'AUTO {int(pwm)}\n')
            proceso.stdin.flush()
        except Exception:
            self.cerrar_fan_pwm_helper()
            proceso = self._obtener_fan_pwm_helper()
            proceso.stdin.write(f'AUTO {int(pwm)}\n')
            proceso.stdin.flush()
        respuesta = self._leer_linea_helper(proceso, timeout=60)
        if not respuesta:
            error = self._leer_stderr_helper(proceso)
            self.cerrar_fan_pwm_helper()
            raise RuntimeError(error or 'PWM helper did not respond.')
        if respuesta.startswith('ERR '):
            raise RuntimeError(respuesta[4:].strip())
        if respuesta.startswith('OK'):
            return respuesta
        raise RuntimeError(respuesta)

    def _obtener_fan_pwm_helper(self):
        proceso = getattr(self, '_fan_pwm_helper', None)
        if proceso is not None and proceso.poll() is None:
            return proceso
        return self._iniciar_fan_pwm_helper()

    def _fan_pwm_helper_path(self):
        cache = os.environ.get('XDG_CACHE_HOME')
        base = Path(cache) if cache else Path.home() / '.cache'
        carpeta = base / 'bc250-control-center'
        carpeta.mkdir(parents=True, exist_ok=True)
        try:
            carpeta.chmod(0o700)
        except OSError:
            logger.debug("Could not restrict permissions on the fan helper cache directory", exc_info=True)
        return carpeta / 'bc250-fan-pwm-control-helper'

    def _fan_pwm_packaged_helper_path(self):
        candidates = []
        configured = os.environ.get('BC250_FAN_PWM_HELPER', '').strip()
        if configured:
            candidates.append(Path(configured))
        candidates.extend([
            Path('/usr/libexec/bc250-control-center/bc250-fan-pwm-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-fan-pwm-helper'),
        ])
        for candidate in candidates:
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                continue
            if os.access(candidate, os.X_OK):
                return candidate
        return None

    def _guardar_fan_pwm_helper(self, helper_code):
        python = self._command_path('python3') or '/usr/bin/python3'
        ruta = self._fan_pwm_helper_path()
        contenido = '#!%s\n# BC250 Control Center fan PWM helper\n%s\n' % (python, helper_code.lstrip())
        temporal = ruta.with_name(f'.{ruta.name}.{os.getpid()}.tmp')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(temporal, flags, 0o700)
            with os.fdopen(fd, 'w', encoding='utf-8') as archivo:
                archivo.write(contenido)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, ruta)
            ruta.chmod(0o700)
        finally:
            try:
                temporal.unlink()
            except FileNotFoundError:
                logger.debug("Temporary fan helper was already removed")
        return ruta

    def _iniciar_fan_pwm_helper(self):
        helper_code = r"""
import pathlib
import sys
import time


PWM_MODE_VERIFY_ATTEMPTS = 10
PWM_MODE_VERIFY_INTERVAL_SECONDS = 0.05
PWM_MODE_SETTLE_SECONDS = 0.15
PWM_DUTY_VERIFY_ATTEMPTS = 16
PWM_DUTY_VERIFY_INTERVAL_SECONDS = 0.10


def find_sensor():
    base = pathlib.Path('/sys/class/hwmon')
    for hwmon in sorted(base.glob('hwmon*')):
        try:
            name = (hwmon / 'name').read_text().strip().lower()
        except Exception:
            name = ''
        if name.startswith(('nct668', 'nct67', 'nct')):
            return hwmon
    return None


def wait_for_value(path, expected, retry_payload=None, attempts=1, interval=0.05):
    observed = ''
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        observed = path.read_text().strip()
        if observed == expected:
            return True, observed, attempt
        if attempt < attempts:
            time.sleep(interval)
            if retry_payload is not None:
                path.write_text(retry_payload)
    return False, observed, attempts


def restore_previous_automatic(enable_path, was_automatic):
    if not was_automatic or enable_path is None:
        return ''
    try:
        enable_path.write_text('2\n')
        restored, observed, _attempts = wait_for_value(
            enable_path, '2', attempts=PWM_MODE_VERIFY_ATTEMPTS,
            interval=PWM_MODE_VERIFY_INTERVAL_SECONDS,
        )
    except Exception as exc:
        return ' Previous automatic-mode rollback failed: %s.' % exc
    if restored:
        return ' Previous automatic mode was restored.'
    return ' Previous automatic-mode rollback read-back was %r.' % observed


def apply_pwm(pwm, value):
    sensor = find_sensor()
    if sensor is None:
        return 'ERR No NCT hwmon sensor was found.'
    pwm_path = sensor / ('pwm%s' % pwm)
    enable_path = sensor / ('pwm%s_enable' % pwm)
    if not pwm_path.is_file():
        return 'ERR %s does not exist.' % pwm_path
    was_automatic = False
    try:
        if enable_path.is_file():
            was_automatic = enable_path.read_text().strip() == '2'
            enable_path.write_text('1\n')
            ready, observed, attempts = wait_for_value(
                enable_path, '1', attempts=PWM_MODE_VERIFY_ATTEMPTS,
                interval=PWM_MODE_VERIFY_INTERVAL_SECONDS,
            )
            if not ready:
                rollback = restore_previous_automatic(enable_path, was_automatic)
                return 'ERR PWM %s manual-mode read-back was %r after %s attempts.%s' % (
                    pwm, observed, attempts, rollback,
                )
            time.sleep(PWM_MODE_SETTLE_SECONDS)
        payload = str(value) + '\n'
        pwm_path.write_text(payload)
        ready, observed, attempts = wait_for_value(
            pwm_path, str(value), retry_payload=payload,
            attempts=PWM_DUTY_VERIFY_ATTEMPTS,
            interval=PWM_DUTY_VERIFY_INTERVAL_SECONDS,
        )
        if not ready:
            rollback = restore_previous_automatic(
                enable_path if enable_path.is_file() else None,
                was_automatic,
            )
            return 'ERR PWM %s duty read-back was %r after %s attempts.%s' % (
                pwm, observed, attempts, rollback,
            )
        return 'OK PWM %s %s' % (pwm, value)
    except Exception as exc:
        return 'ERR ' + str(exc)


def restore_auto(pwm):
    sensor = find_sensor()
    if sensor is None:
        return 'ERR No NCT hwmon sensor was found.'
    enable_path = sensor / ('pwm%s_enable' % pwm)
    if not enable_path.is_file():
        return 'ERR %s does not exist; automatic mode cannot be restored.' % enable_path
    try:
        enable_path.write_text('2\n')
        restored, confirmed, attempts = wait_for_value(
            enable_path, '2', attempts=PWM_MODE_VERIFY_ATTEMPTS,
            interval=PWM_MODE_VERIFY_INTERVAL_SECONDS,
        )
        if not restored:
            return "ERR PWM %s automatic-mode readback was %r after %s attempts, expected 2." % (pwm, confirmed, attempts)
        return 'OK PWM %s AUTO' % pwm
    except Exception as exc:
        return 'ERR ' + str(exc)


print('READY', flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    if line == 'EXIT':
        print('BYE', flush=True)
        break
    try:
        parts = line.split()
        if len(parts) == 2 and parts[0] == 'AUTO':
            pwm = int(parts[1])
            if pwm < 1 or pwm > 12:
                print('ERR Invalid PWM channel.', flush=True)
                continue
            print(restore_auto(pwm), flush=True)
            continue
        if len(parts) != 2:
            raise ValueError('Expected PWM channel and value, or AUTO and channel.')
        pwm = int(parts[0])
        value = int(parts[1])
        if pwm < 1 or pwm > 12:
            print('ERR Invalid PWM channel.', flush=True)
            continue
        if value < 0 or value > 255:
            print('ERR PWM value must be between 0 and 255.', flush=True)
            continue
        print(apply_pwm(pwm, value), flush=True)
    except Exception as exc:
        print('ERR ' + str(exc), flush=True)
"""
        helper_path = self._fan_pwm_packaged_helper_path()
        if helper_path is None:
            source_path = Path(__file__).resolve()
            installed_system_wide = any(
                str(source_path).startswith(prefix)
                for prefix in ('/usr/share/bc250-control-center/', '/usr/local/share/bc250-control-center/')
            )
            if installed_system_wide:
                raise RuntimeError(
                    'The root-owned BC250 PWM helper is missing or has unsafe permissions. '
                    'Reinstall the BC250 Control Center package.'
                )
            # Development/user-local fallback. This path exists for source testing;
            # packaged installations fail closed instead of running user-owned code.
            helper_path = self._guardar_fan_pwm_helper(helper_code)
            embedded = True
        else:
            embedded = False
        try:
            proceso = subprocess.Popen(
                pkexec_argv('pkexec', str(helper_path)),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as error:
            raise RuntimeError(str(error)) from error
        linea = self._leer_linea_helper(proceso, timeout=90)
        if not linea:
            error = self._leer_stderr_helper(proceso)
            self._fan_pwm_helper = None
            raise RuntimeError(normalize_polkit_error(['pkexec'], error) or 'PWM helper did not start.')
        if linea != 'READY':
            error = self._leer_stderr_helper(proceso)
            self._fan_pwm_helper = None
            raise RuntimeError((linea + '\n' + error).strip())
        self._fan_pwm_helper = proceso
        self._fan_pwm_helper_embedded = embedded
        return proceso

    def _leer_linea_helper(self, proceso, timeout=60):
        inicio = time.monotonic()
        while time.monotonic() - inicio < timeout:
            if proceso.poll() is not None:
                try:
                    return (proceso.stdout.readline() or '').strip()
                except Exception:
                    return ''
            try:
                import select
                listo, _, _ = select.select([proceso.stdout], [], [], 0.1)
                if listo:
                    return (proceso.stdout.readline() or '').strip()
            except Exception:
                time.sleep(0.1)
        return ''

    def _leer_stderr_helper(self, proceso):
        try:
            import select
            partes = []
            while True:
                listo, _, _ = select.select([proceso.stderr], [], [], 0)
                if not listo:
                    break
                linea = proceso.stderr.readline()
                if not linea:
                    break
                partes.append(linea.strip())
            return '\n'.join(partes).strip()
        except Exception:
            return ''

    def cerrar_fan_pwm_helper(self):
        proceso = getattr(self, '_fan_pwm_helper', None)
        self._fan_pwm_helper = None
        if proceso is None:
            return
        try:
            if proceso.poll() is None:
                proceso.stdin.write('EXIT\n')
                proceso.stdin.flush()
                proceso.terminate()
        except (BrokenPipeError, OSError):
            logger.debug("Fan PWM helper was already closed or unavailable", exc_info=True)



    def _parece_permiso_denegado(self, out, err):
        texto = f'{out}\n{err}'.lower()
        return any(x in texto for x in ['permission denied', 'permiso denegado', 'read-only file system', 'solo lectura'])

    def _leer_sensores_nct(self):
        self._buscar_sensores()
        salida = {'chip': '', 'path': '', 'fans': [], 'temps': [], 'pwms': []}
        sensor = self._sensor_nct_principal()
        if not sensor:
            return salida
        salida['chip'] = self._leer_texto(sensor / 'name') or sensor.name
        salida['path'] = str(sensor)
        modulos = self._modulos_nct()
        for archivo in sorted(sensor.glob('fan*_input')):
            salida['fans'].append(self._nct_fan_entry(sensor, archivo, modulos))
        for archivo in sorted(sensor.glob('pwm[0-9]*')):
            if archivo.name.endswith('_enable'):
                continue
            salida['pwms'].append(self._nct_pwm_entry(archivo))
        for label in sorted(sensor.glob('temp*_label')):
            salida['temps'].append(self._nct_temp_entry(sensor, label))
        return salida

    def _nct_fan_entry(self, sensor, input_path, modules):
        index = self._numero_archivo(input_path.name)
        pwm_path = sensor / f'pwm{index}'
        pwm_present = pwm_path.is_file()
        enable_path = sensor / f'pwm{index}_enable'
        enable_present = enable_path.is_file()
        return {
            'index': index,
            'label': self._fan_label_bc250(index, modules),
            'rpm': self._leer_entero(input_path),
            'pwm': self._leer_entero(pwm_path) if pwm_present else None,
            'pwm_path': str(pwm_path) if pwm_present else '',
            'pwm_writable': bool(pwm_present and os.access(pwm_path, os.W_OK)),
            'pwm_root_writable': bool(pwm_present and self._root_puede_escribir(pwm_path)),
            'pwm_mode': self._modo_archivo(pwm_path) if pwm_present else '',
            'pwm_enable': self._leer_entero(enable_path) if enable_present else None,
            'pwm_enable_path': str(enable_path) if enable_present else '',
            'pwm_enable_writable': bool(enable_present and os.access(enable_path, os.W_OK)),
            'pwm_enable_root_writable': bool(enable_present and self._root_puede_escribir(enable_path)),
        }

    def _nct_pwm_entry(self, path):
        return {
            'index': self._numero_archivo(path.name),
            'value': self._leer_entero(path),
            'path': str(path),
            'writable': os.access(path, os.W_OK),
            'root_writable': self._root_puede_escribir(path),
            'mode': self._modo_archivo(path),
        }

    def _nct_temp_entry(self, sensor, label_path):
        index = self._numero_archivo(label_path.name)
        value = self._leer_entero(sensor / f'temp{index}_input')
        return {
            'index': index,
            'label': self._leer_texto(label_path) or label_path.name,
            'temp': None if value is None else value / 1000,
        }

    def _sensor_nct_principal(self):
        base = Path(getattr(self, '_fan_hwmon_root', '/sys/class/hwmon'))
        candidatos = []
        try:
            carpetas = sorted(base.glob('hwmon*'))
        except OSError:
            logger.debug("Could not enumerate hwmon devices", exc_info=True)
            return None
        for carpeta in carpetas:
            nombre = self._leer_texto(carpeta / 'name') or ''
            if 'nct' in nombre.lower():
                candidatos.append((self._nct_sensor_score(carpeta), carpeta))
        if not candidatos:
            return None
        # A writable control node is more useful than an earlier read-only NCT
        # node. Remaining fields prefer the richest telemetry surface; path is
        # the deterministic tie-breaker across kernel enumeration order.
        candidatos.sort(key=lambda item: (
            -item[0][0], -item[0][1], -item[0][2], -item[0][3], item[1].name
        ))
        return candidatos[0][1]

    def _nct_sensor_score(self, sensor):
        try:
            pwms = [
                path for path in sensor.glob('pwm[0-9]*')
                if not path.name.endswith('_enable') and path.is_file()
            ]
            fans = [path for path in sensor.glob('fan*_input') if path.is_file()]
            temperatures = [path for path in sensor.glob('temp*_input') if path.is_file()]
        except OSError:
            return 0, 0, 0, 0
        writable = any(
            os.access(path, os.W_OK) or self._root_puede_escribir(path)
            for path in pwms
        )
        return int(writable), len(pwms), len(fans), len(temperatures)

    def _modulos_nct(self):
        texto = ''
        try:
            texto = Path('/proc/modules').read_text(errors='ignore')
        except OSError:
            logger.debug("Could not inspect /proc/modules for NCT drivers", exc_info=True)
        return {
            'nct6683': any(line.startswith('nct6683 ') for line in texto.splitlines()),
            'nct6687': any(line.startswith(('nct6687 ', 'nct6687d ')) for line in texto.splitlines()),
            'raw': '\n'.join(line for line in texto.splitlines() if line.startswith(('nct6683 ', 'nct6687 ', 'nct6687d '))),
        }

    def _comando_instalar_nct6687(self):
        tools_dir = str(self._tool_dir() / 'nct6687d')
        return self._os_repository().install_fan_pwm_command(tools_dir)

    def _comando_instalar_lm_sensors(self):
        return self._os_repository().install_lm_sensors_command()


    def _comando_servicio_nct6687_persistente(self):
        tools_dir = str(self._tool_dir() / 'nct6687d')
        return self._os_repository().install_fan_persistence_command(tools_dir)





    def _resumen_fan(self, sensores, modulos):
        fans = sensores.get('fans') or []
        activos = [f for f in fans if f.get('rpm')]
        pwm_write = [f for f in fans if f.get('pwm_writable') or f.get('pwm_root_writable')]
        pwm_write.extend(
            p for p in sensores.get('pwms', [])
            if p.get('writable') or p.get('root_writable')
        )
        if not sensores.get('chip'):
            return 'No NCT sensor detected. Configure nct6683 for read-only monitoring or nct6687 for PWM control.'
        if pwm_write:
            return f'{sensores.get("chip")} detected. Writable PWM control path is available.'
        if modulos.get('nct6687'):
            return f'{sensores.get("chip")} detected and nct6687 is loaded, but no writable PWM path is exposed.'
        return f'{sensores.get("chip")} detected. Read-only mode likely: {len(activos)} fan(s) reporting RPM, PWM files not writable.'

    def _fan_label_bc250(self, indice, modulos=None):
        modulos = modulos or {}
        if modulos.get('nct6687'):
            nombres = {
                1: 'CPU Fan',
                2: 'Pump Fan / J4003 Fan 1',
                3: 'System Fan #1 / J4003 Fan 2',
                4: 'System Fan #2 / J4003 Fan 3',
                5: 'System Fan #3 / J4003 Fan 4',
                6: 'System Fan #4 / J4003 Fan 5',
                7: 'System Fan #5',
                8: 'System Fan #6',
            }
        else:
            nombres = {
                1: 'Fan 1 / CPU Fan',
                2: 'Pump Fan / J4003 Fan 1',
                3: 'System Fan #1 / J4003 Fan 2',
                4: 'System Fan #2 / J4003 Fan 3',
                5: 'System Fan #3 / J4003 Fan 4',
            }
        return nombres.get(indice, f'Fan {indice}')

    def _root_puede_escribir(self, ruta):
        try:
            modo = Path(ruta).stat().st_mode & 0o222
            return bool(modo)
        except Exception:
            return False

    def _numero_archivo(self, nombre):
        import re
        m = re.search(r'(\d+)', nombre)
        return int(m.group(1)) if m else 0

    def _modo_archivo(self, ruta):
        try:
            return oct(Path(ruta).stat().st_mode & 0o777)
        except Exception:
            return ''
    def _leer_texto(self, ruta):
        try:
            return Path(ruta).read_text().strip()
        except Exception:
            return None

    def _leer_entero(self, ruta):
        valor = self._leer_texto(ruta)
        if valor is None:
            return None
        try:
            return int(valor)
        except Exception:
            return None

    def _buscar_sensores(self):
        self.hwmons = []
        for carpeta in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
            nombre = self._leer_texto(carpeta / 'name') or carpeta.name
            self.hwmons.append((nombre, carpeta))

    def _ejecutar(self, comando, timeout=2):
        try:
            r = subprocess.run(comando, text=True, capture_output=True, timeout=timeout, check=False)
            return (
                r.returncode,
                (r.stdout or '').strip(),
                normalize_polkit_error(comando, (r.stderr or '').strip()),
            )
        except Exception as error:
            return 1, '', str(error)

    def _command_path(self, nombre):
        return shutil.which(nombre) or ''

    def _os_release(self):
        datos = {}
        for ruta in [Path('/etc/os-release'), Path('/usr/lib/os-release')]:
            if not ruta.exists():
                continue
            try:
                for linea in ruta.read_text(encoding='utf-8').splitlines():
                    if '=' not in linea or linea.startswith('#'):
                        continue
                    clave, valor = linea.split('=', 1)
                    datos[clave] = valor.strip().strip('"')
                break
            except Exception:
                continue
        return datos
