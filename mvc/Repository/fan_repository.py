from pathlib import Path
import os
import shlex
import shutil
import subprocess
import time


class FanRepository:
    def estado_fans_bc250(self):
        sensores = self._leer_sensores_nct()
        modulos = self._modulos_nct()
        coolercontrol = self._estado_coolercontrol()
        return {
            'sensores': sensores,
            'modulos': modulos,
            'coolercontrol': coolercontrol,
            'driver_lectura': bool(modulos.get('nct6683')),
            'driver_control': bool(modulos.get('nct6687')) or any(item.get('pwm_writable') for item in sensores.get('fans', [])),
            'resumen': self._resumen_fan(sensores, modulos, coolercontrol),
        }

    def cargar_nct6683_solo_lectura(self):
        comando = '; '.join([
            'set -e',
            'echo "== BC250 fan sensors: read-only nct6683 =="',
            'echo "This enables temperatures, voltages and fan RPM monitoring only."',
            'sudo modprobe nct6683 || true',
            "echo nct6683 | sudo tee /etc/modules-load.d/nct6683.conf >/dev/null",
            "echo 'options nct6683 force=true' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            'echo "OK: nct6683 configured for read-only monitoring."',
            'echo "Reboot if sensors do not show nct6686-isa-0a20."',
            'sensors | sed -n "/nct668/,+35p" || true',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan sensors')

    def preparar_nct6687_control_pwm(self):
        comando_instalar = self._comando_instalar_nct6687()
        if not comando_instalar:
            raise RuntimeError('No compatible installer found for nct6687d-dkms-git. Install it manually, then load nct6687 with force=true.')
        comando = '; '.join([
            'set +e',
            'echo "== BC250 fan control: nct6687 PWM driver =="',
            'echo "nct6687d-dkms-git is an out-of-tree driver. Reboot may be required after install."',
            comando_instalar,
            'echo "== Configuring module preference =="',
            "echo 'blacklist nct6683' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            "echo 'options nct6687 force=true' | sudo tee /etc/modprobe.d/nct6687.conf >/dev/null",
            "sudo rm -f /etc/modules-load.d/nct6683.conf",
            "echo nct6687 | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null",
            'sudo modprobe -r nct6683 2>/dev/null || true',
            'sudo modprobe nct6687 2>/dev/null || true',
            'echo "== Verification =="',
            'lsmod | grep -E "nct6683|nct6687" || true',
            'sensors | sed -n "/nct668/,+45p" || true',
            'echo "If PWM files remain read-only, reboot and verify the loaded module."',
        ])
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, 'BC250 fan PWM driver')

    def desactivar_nct6687_control_pwm(self):
        comando = '; '.join([
            'set +e',
            'echo "== BC250 fan control: disable nct6687 PWM setup =="',
            'echo "This disables the automatic nct6687 preference and returns to read-only nct6683 monitoring."',
            'echo "The nct6687d package is not removed; only boot/module preference files are changed."',
            "sudo rm -f /etc/modules-load.d/nct6687.conf",
            "sudo rm -f /etc/modprobe.d/nct6687.conf",
            "sudo rm -f /etc/modprobe.d/nct6683.conf",
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

    def instalar_coolercontrol(self):
        comando = self._comando_instalar_coolercontrol()
        if not comando:
            raise RuntimeError('No compatible installer found for CoolerControl. Install coolercontrol manually for your distribution.')
        comando = '; '.join([
            'set +e',
            'echo "== Installing CoolerControl =="',
            comando,
            'sudo systemctl enable --now coolercontrold 2>/dev/null || true',
            'systemctl status coolercontrold --no-pager || true',
            'echo "Launch with: coolercontrol"',
        ])
        return self._abrir_terminal(comando, 'Instalar CoolerControl')

    def abrir_coolercontrol(self):
        if shutil.which('coolercontrol'):
            subprocess.Popen(['coolercontrol'])
            return True
        raise RuntimeError('CoolerControl is not installed. Use Install CoolerControl first.')

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

    def _guardar_fan_pwm_helper(self, helper_code):
        python = self._command_path('python3') or '/usr/bin/python3'
        ruta = self._fan_pwm_helper_path()
        contenido = '#!%s\n# BC250 Control Center fan PWM helper\n%s\n' % (python, helper_code.lstrip())
        ruta.write_text(contenido, encoding='utf-8')
        ruta.chmod(0o755)
        return ruta

    def _iniciar_fan_pwm_helper(self):
        helper_code = r"""
import os
import pathlib
import subprocess
import sys


def write(path, text):
    pathlib.Path(path).write_text(text)


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def find_sensor():
    base = pathlib.Path('/sys/class/hwmon')
    for hwmon in sorted(base.glob('hwmon*')):
        try:
            name = (hwmon / 'name').read_text().strip().lower()
        except Exception:
            name = ''
        if 'nct' in name:
            return hwmon
    return None


def prepare_driver_once():
    try:
        write('/etc/modprobe.d/nct6683.conf', 'blacklist nct6683\n')
        write('/etc/modprobe.d/nct6687.conf', 'options nct6687 force=true\n')
        try:
            os.remove('/etc/modules-load.d/nct6683.conf')
        except FileNotFoundError:
            pass
        write('/etc/modules-load.d/nct6687.conf', 'nct6687\n')
        run(['modprobe', '-r', 'nct6683'])
        run(['modprobe', 'nct6687'])
    except Exception as exc:
        print('WARN driver_prepare ' + str(exc), flush=True)


def apply_pwm(pwm, value):
    sensor = find_sensor()
    if sensor is None:
        return 'ERR No NCT hwmon sensor was found.'
    pwm_path = sensor / ('pwm%s' % pwm)
    enable_path = sensor / ('pwm%s_enable' % pwm)
    if not pwm_path.exists():
        return 'ERR %s does not exist.' % pwm_path
    try:
        if enable_path.exists():
            enable_path.write_text('1\n')
        pwm_path.write_text(str(value) + '\n')
        return 'OK PWM %s %s' % (pwm, value)
    except Exception as exc:
        return 'ERR ' + str(exc)


prepare_driver_once()
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
        if linea.startswith('WARN '):
            linea = self._leer_linea_helper(proceso, timeout=10)
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

    def _escribir_pwm_con_pkexec(self, sensor, pwm, valor):
        ruta_pwm = sensor / f'pwm{pwm}'
        ruta_enable = sensor / f'pwm{pwm}_enable'
        bash = self._command_path('bash') or 'bash'
        comandos = [
            "echo 'blacklist nct6683' > /etc/modprobe.d/nct6683.conf",
            "echo 'options nct6687 force=true' > /etc/modprobe.d/nct6687.conf",
            'rm -f /etc/modules-load.d/nct6683.conf',
            "echo nct6687 > /etc/modules-load.d/nct6687.conf",
            'modprobe -r nct6683 2>/dev/null || true',
            'modprobe nct6687 2>/dev/null || true',
        ]
        if ruta_enable.exists():
            comandos.append(f'echo 1 > {shlex.quote(str(ruta_enable))}')
        comandos.append(f'echo {valor} > {shlex.quote(str(ruta_pwm))}')
        comando = 'set -e; ' + '; '.join(comandos) + '; echo OK'
        return self._ejecutar(['pkexec', bash, '-lc', comando], timeout=90)

    def _asegurar_nct6687_pwm(self):
        bash = self._command_path('bash') or 'bash'
        comando = '; '.join([
            'set -e',
            "echo 'blacklist nct6683' > /etc/modprobe.d/nct6683.conf",
            "echo 'options nct6687 force=true' > /etc/modprobe.d/nct6687.conf",
            'rm -f /etc/modules-load.d/nct6683.conf',
            "echo nct6687 > /etc/modules-load.d/nct6687.conf",
            'modprobe -r nct6683 2>/dev/null || true',
            'modprobe nct6687 2>/dev/null || true',
        ])
        rc, out, err = self._ejecutar(['pkexec', bash, '-lc', comando], timeout=60)
        if rc != 0:
            raise RuntimeError((err or out or 'Could not prepare nct6687 PWM driver.').strip())
        self.estado_herramientas_cache = None
        return True

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

    def _estado_coolercontrol(self):
        rc, out, _ = self._ejecutar(['systemctl', 'is-active', 'coolercontrold'], timeout=2)
        return {
            'cmd': self._command_path('coolercontrol'),
            'service_active': (out.strip() == 'active' and rc == 0),
            'service_state': out.strip() if out else 'unknown',
        }

    def _comando_instalar_nct6687(self):
        if self._command_path('paru'):
            return 'paru -S --needed nct6687d-dkms-git'
        if self._command_path('yay'):
            return 'yay -S --needed nct6687d-dkms-git'
        if self._command_path('shelly'):
            return 'shelly aur install nct6687d-dkms-git -b -m'
        return ''

    def _comando_instalar_coolercontrol(self):
        if self._command_path('paru'):
            return 'paru -S --needed coolercontrol-bin lm_sensors'
        if self._command_path('yay'):
            return 'yay -S --needed coolercontrol-bin lm_sensors'
        if self._command_path('shelly'):
            return 'shelly aur install coolercontrol-bin -b -m; sudo pacman -S --needed lm_sensors || true'
        if self._es_ostree():
            return 'sudo rpm-ostree install coolercontrol lm_sensors; echo "NOTICE: rpm-ostree may require reboot."'
        if self._command_path('dnf'):
            return 'sudo dnf install -y coolercontrol lm_sensors'
        if self._command_path('apt'):
            return 'sudo apt update && sudo apt install -y coolercontrol lm-sensors'
        return ''

    def _resumen_fan(self, sensores, modulos, coolercontrol):
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

    def _es_ostree(self):
        datos = self._os_release()
        texto = ' '.join([datos.get('ID', ''), datos.get('ID_LIKE', ''), datos.get('VARIANT_ID', ''), datos.get('NAME', '')]).lower()
        return bool(self._command_path('rpm-ostree') and any(x in texto for x in ['bazzite', 'silverblue', 'kinoite', 'ublue', 'atomic']))
