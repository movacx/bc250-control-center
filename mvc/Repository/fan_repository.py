from pathlib import Path
import os
import shlex
import shutil
import stat
import subprocess
import time


class FanRepository:
    def estado_fans_bc250(self):
        sensores = self._leer_sensores_nct()
        modulos = self._modulos_nct()
        return {
            'sensores': sensores,
            'modulos': modulos,
            'driver_lectura': bool(modulos.get('nct6683')),
            'driver_control': bool(modulos.get('nct6687')) or any(item.get('pwm_writable') for item in sensores.get('fans', [])),
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
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan sensors')

    def preparar_nct6687_control_pwm(self):
        comando_instalar = self._comando_instalar_nct6687().strip().rstrip(';')
        if not comando_instalar:
            raise RuntimeError('No compatible installer found for nct6687. Install Fred78290/nct6687d manually, then load nct6687 with force=true.')
        comando_servicio = self._comando_servicio_nct6687_persistente().strip().rstrip(';')
        comando = '; '.join([
            'set -Eeuo pipefail',
            'echo "== BC250 fan control: nct6687 PWM driver =="',
            'echo "nct6687 is an out-of-tree driver. Reboot may be required after install."',
            comando_instalar,
            'echo "== Configuring module preference =="',
            "echo 'blacklist nct6683' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            "echo 'options nct6687 force=true' | sudo tee /etc/modprobe.d/nct6687.conf >/dev/null",
            "printf 'blacklist nct6683\\noptions nct6687 force=true\\n' | sudo tee /etc/modprobe.d/sensors.conf >/dev/null",
            "sudo rm -f /etc/modules-load.d/nct6683.conf",
            "echo nct6687 | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null",
            "echo nct6687 | sudo tee /etc/modules-load.d/99-sensors.conf >/dev/null",
            'sudo modprobe -r nct6683 2>/dev/null || true',
            'sudo modprobe nct6687 force=true 2>/dev/null || sudo modprobe nct6687 2>/dev/null || true',
            comando_servicio,
            'sudo systemctl reset-failed nct6687-load.service 2>/dev/null || true',
            'sudo systemctl restart nct6687-load.service 2>/dev/null || sudo systemctl start nct6687-load.service 2>/dev/null || true',
            'echo "== Verification =="',
            'systemctl status nct6687-load.service --no-pager 2>/dev/null || true',
            'lsmod | grep -E "nct6683|nct6687" || true',
            'sensors | sed -n "/nct668/,+45p" || true',
            'echo',
            '''bc250_nct6687_ready() { for n in /sys/class/hwmon/hwmon*/name; do [ -r "$n" ] || continue; name="$(cat "$n" 2>/dev/null || true)"; case "$name" in nct668*|nct67*|nct*) dir="${n%/name}"; ls "$dir"/fan*_input "$dir"/pwm* >/dev/null 2>&1 && return 0 ;; esac; done; sensors 2>/dev/null | awk '/nct6686-isa/{seen=1} seen && /(Fan|fan|pwm)[ #0-9]*:/ {ok=1} END{exit ok?0:1}'; }''',
            'if bc250_nct6687_ready; then echo "OK: nct6687 is loaded and the NCT fan/PWM hwmon is ready."; else echo "ERROR: nct6687 is not exposing the NCT fan/PWM hwmon yet. Check the service log below."; journalctl -u nct6687-load.service -b --no-pager | tail -120 2>/dev/null || true; exit 1; fi',
            'echo "If PWM files remain read-only after a successful check, reboot once and verify the loaded module."',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan PWM driver')

    def desactivar_nct6687_control_pwm(self):
        comando = '; '.join([
            'set +e',
            'echo "== BC250 fan control: disable nct6687 PWM setup =="',
            'echo "This disables the automatic nct6687 preference and returns to read-only nct6683 monitoring."',
            'echo "The nct6687d package is not removed; only boot/module preference files are changed."',
            'sudo systemctl disable --now nct6687-load.service 2>/dev/null || true',
            "sudo rm -f /etc/systemd/system/nct6687-load.service",
            "sudo rm -f /usr/local/sbin/bc250-load-nct6687",
            'sudo systemctl daemon-reload 2>/dev/null || true',
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
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan PWM disable')

    def aplicar_pwm_fan(self, pwm, valor):
        pwm = int(pwm)
        valor = int(valor)
        if pwm < 1 or pwm > 12:
            raise RuntimeError('Invalid PWM channel.')
        if valor < 0 or valor > 255:
            raise RuntimeError('PWM value must be between 0 and 255.')
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Cannot authenticate PWM write from the GUI.')
        if not self._command_path('python3'):
            raise RuntimeError('python3 was not found. It is required for the PWM helper.')
        sensor = self._sensor_nct_principal()
        if not sensor:
            raise RuntimeError('No NCT hwmon sensor was found.')
        ruta_pwm = sensor / f'pwm{pwm}'
        if not ruta_pwm.exists():
            raise RuntimeError(f'{ruta_pwm} does not exist.')
        salida = self._escribir_pwm_con_helper(pwm, valor)
        return {'pwm': pwm, 'valor': valor, 'salida': salida}

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
        except Exception:
            pass
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
                pass
        return ruta

    def _iniciar_fan_pwm_helper(self):
        helper_code = r"""
import pathlib
import sys


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


def apply_pwm(pwm, value):
    sensor = find_sensor()
    if sensor is None:
        return 'ERR No NCT hwmon sensor was found.'
    pwm_path = sensor / ('pwm%s' % pwm)
    enable_path = sensor / ('pwm%s_enable' % pwm)
    if not pwm_path.is_file():
        return 'ERR %s does not exist.' % pwm_path
    try:
        if enable_path.is_file():
            enable_path.write_text('1\n')
        pwm_path.write_text(str(value) + '\n')
        return 'OK PWM %s %s' % (pwm, value)
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
        if len(parts) != 2:
            raise ValueError('Expected PWM channel and value.')
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
        try:
            proceso = subprocess.Popen(
                ['pkexec', str(helper_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as error:
            raise RuntimeError(str(error))
        linea = self._leer_linea_helper(proceso, timeout=90)
        if not linea:
            error = self._leer_stderr_helper(proceso)
            self._fan_pwm_helper = None
            raise RuntimeError(error or 'PWM helper did not start.')
        if linea != 'READY':
            error = self._leer_stderr_helper(proceso)
            self._fan_pwm_helper = None
            raise RuntimeError((linea + '\n' + error).strip())
        self._fan_pwm_helper = proceso
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
        except Exception:
            pass



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
        for archivo in sorted(sensor.glob('fan*_input')):
            indice = self._numero_archivo(archivo.name)
            rpm = self._leer_entero(archivo)
            pwm_archivo = sensor / f'pwm{indice}'
            pwm = self._leer_entero(pwm_archivo) if pwm_archivo.exists() else None
            salida['fans'].append({
                'index': indice,
                'label': self._fan_label_bc250(indice, self._modulos_nct()),
                'rpm': rpm,
                'pwm': pwm,
                'pwm_path': str(pwm_archivo) if pwm_archivo.exists() else '',
                'pwm_writable': os.access(pwm_archivo, os.W_OK) if pwm_archivo.exists() else False,
                'pwm_root_writable': self._root_puede_escribir(pwm_archivo) if pwm_archivo.exists() else False,
                'pwm_mode': self._modo_archivo(pwm_archivo) if pwm_archivo.exists() else '',
            })
        for archivo in sorted(sensor.glob('pwm[0-9]*')):
            if archivo.name.endswith('_enable'):
                continue
            indice = self._numero_archivo(archivo.name)
            salida['pwms'].append({
                'index': indice,
                'value': self._leer_entero(archivo),
                'path': str(archivo),
                'writable': os.access(archivo, os.W_OK),
                'root_writable': self._root_puede_escribir(archivo),
                'mode': self._modo_archivo(archivo),
            })
        for label in sorted(sensor.glob('temp*_label')):
            indice = self._numero_archivo(label.name)
            entrada = sensor / f'temp{indice}_input'
            valor = self._leer_entero(entrada)
            salida['temps'].append({
                'index': indice,
                'label': self._leer_texto(label) or label.name,
                'temp': None if valor is None else valor / 1000,
            })
        return salida

    def _sensor_nct_principal(self):
        candidatos = []
        for carpeta in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
            nombre = self._leer_texto(carpeta / 'name') or ''
            if 'nct' in nombre.lower():
                candidatos.append(carpeta)
        return candidatos[0] if candidatos else None

    def _modulos_nct(self):
        texto = ''
        try:
            texto = Path('/proc/modules').read_text(errors='ignore')
        except Exception:
            pass
        return {
            'nct6683': any(line.startswith('nct6683 ') for line in texto.splitlines()),
            'nct6687': any(line.startswith('nct6687 ') or line.startswith('nct6687d ') for line in texto.splitlines()),
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
        if not sensores.get('chip'):
            return 'No NCT sensor detected. Configure nct6683 for read-only monitoring or nct6687 for PWM control.'
        if pwm_write or modulos.get('nct6687'):
            return f'{sensores.get("chip")} detected. PWM control path is available or nct6687 is loaded.'
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
            r = subprocess.run(comando, text=True, capture_output=True, timeout=timeout)
            return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()
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
