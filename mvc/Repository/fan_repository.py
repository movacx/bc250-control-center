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
        comando_instalar = self._comando_instalar_nct6687()
        if not comando_instalar:
            raise RuntimeError('No compatible installer found for nct6687. Install Fred78290/nct6687d manually, then load nct6687 with force=true.')
        comando = '; '.join([
            'set +e',
            'echo "== BC250 fan control: nct6687 PWM driver =="',
            'echo "nct6687 is an out-of-tree driver. Reboot may be required after install."',
            comando_instalar,
            'echo "== Configuring module preference =="',
            "echo 'blacklist nct6683' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null",
            "echo 'options nct6687 force=true' | sudo tee /etc/modprobe.d/nct6687.conf >/dev/null",
            "sudo rm -f /etc/modules-load.d/nct6683.conf",
            "echo nct6687 | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null",
            'sudo modprobe -r nct6683 2>/dev/null || true',
            'sudo modprobe nct6687 force=true 2>/dev/null || true',
            self._comando_servicio_nct6687_persistente(),
            'sudo systemctl start nct6687-load.service 2>/dev/null || true',
            'echo "== Verification =="',
            'systemctl status nct6687-load.service --no-pager 2>/dev/null || true',
            'lsmod | grep -E "nct6683|nct6687" || true',
            'sensors | sed -n "/nct668/,+45p" || true',
            'echo',
            'if lsmod | grep -q "^nct6687 "; then echo "OK: nct6687 is loaded and nct6687-load.service is enabled for next boot."; else echo "WARN: nct6687 is not loaded yet. Reboot may be required, especially on rpm-ostree/Bazzite or after kernel-devel installation."; fi',
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
            'sudo systemctl disable --now nct6687-load.service 2>/dev/null || true',
            "sudo rm -f /etc/systemd/system/nct6687-load.service",
            "sudo rm -f /usr/local/sbin/bc250-load-nct6687",
            'sudo systemctl daemon-reload 2>/dev/null || true',
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

    def _comando_instalar_nct6687(self):
        tools_dir = shlex.quote(str(self._tool_dir() / 'nct6687d'))
        if self._command_path('paru'):
            return 'sudo pacman -S --needed --noconfirm lm_sensors git base-devel linux-headers dkms || true; paru -S --needed nct6687d-dkms-git'
        if self._command_path('yay'):
            return 'sudo pacman -S --needed --noconfirm lm_sensors git base-devel linux-headers dkms || true; yay -S --needed nct6687d-dkms-git'
        if self._command_path('shelly'):
            return 'sudo pacman -S --needed --noconfirm lm_sensors git base-devel linux-headers dkms || true; shelly aur install nct6687d-dkms-git -b -m'
        if self._es_ostree():
            return self._comando_instalar_nct6687_ostree(tools_dir)
        if self._command_path('dnf'):
            return self._comando_instalar_nct6687_fedora(tools_dir)
        if self._command_path('apt'):
            return self._comando_instalar_nct6687_debian(tools_dir)
        return ''

    def _comando_instalar_lm_sensors(self):
        if self._command_path('pacman'):
            return 'sudo pacman -S --needed --noconfirm lm_sensors || true'
        if self._es_ostree():
            return 'sudo rpm-ostree install --idempotent lm_sensors || true; echo "NOTICE: rpm-ostree may require a reboot before newly layered packages are usable."'
        if self._command_path('dnf'):
            return 'sudo dnf install -y lm_sensors || true'
        if self._command_path('apt'):
            return 'sudo apt update || true; sudo apt install -y lm-sensors || true'
        return 'echo "WARN: no supported package manager found for lm_sensors."'

    def _comando_instalar_nct6687_fedora(self, tools_dir):
        return f'''
echo "== Fedora/Nobara mutable: installing build and sensor dependencies ==";
sudo dnf install -y lm_sensors git make gcc elfutils-libelf-devel "kernel-devel-$(uname -r)" || {{
  echo "WARN: exact kernel-devel package was not installed. Update/reboot or install kernel-devel for $(uname -r).";
}};
echo "== Preparing Fred78290/nct6687d source ==";
mkdir -p "$(dirname {tools_dir})";
if [ -d {tools_dir}/.git ]; then git -C {tools_dir} pull --ff-only || true; else git clone --depth 1 https://github.com/Fred78290/nct6687d {tools_dir}; fi;
if [ ! -d "/lib/modules/$(uname -r)/build" ]; then
  echo "ERROR: /lib/modules/$(uname -r)/build is missing. Install kernel-devel-$(uname -r), reboot if needed, then run Prepare fan PWM again.";
else
  echo "== Building nct6687 for $(uname -r) ==";
  (cd {tools_dir} && make build) && {{
    echo "== Installing nct6687.ko into the running kernel module tree ==";
    sudo install -Dm644 {tools_dir}/"$(uname -r)"/nct6687.ko "/lib/modules/$(uname -r)/kernel/drivers/hwmon/nct6687.ko";
    sudo depmod -a "$(uname -r)";
  }};
fi;
if command -v dracut >/dev/null 2>&1 && [ -d /boot ]; then sudo dracut --force 2>/dev/null || true; fi
'''.strip()

    def _comando_servicio_nct6687_persistente(self):
        return '''
echo "== Installing persistent nct6687 boot loader ==";
sudo install -d /usr/local/sbin;
sudo tee /usr/local/sbin/bc250-load-nct6687 >/dev/null <<'EOF'
#!/usr/bin/env bash
set -u
MODPROBE="$(command -v modprobe || echo /usr/sbin/modprobe)"
INSMOD="$(command -v insmod || echo /usr/sbin/insmod)"
"$MODPROBE" -r nct6683 2>/dev/null || true
if "$MODPROBE" nct6687 force=true 2>/dev/null; then
  exit 0
fi
if [ -r /var/lib/nct6687/nct6687.ko ]; then
  "$INSMOD" /var/lib/nct6687/nct6687.ko force=1 2>/dev/null && exit 0
fi
exit 1
EOF
sudo chmod 0755 /usr/local/sbin/bc250-load-nct6687;
sudo tee /etc/systemd/system/nct6687-load.service >/dev/null <<'EOF'
[Unit]
Description=Load nct6687 SuperIO sensor module for BC250 fan PWM
After=systemd-modules-load.service
Before=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bc250-load-nct6687
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload;
sudo systemctl enable nct6687-load.service
'''.strip()

    def _comando_instalar_nct6687_ostree(self, tools_dir):
        return f'''
echo "== Bazzite/Fedora Atomic: preparing nct6687 PWM support ==";
sudo rpm-ostree install --idempotent lm_sensors git make gcc elfutils-libelf-devel kernel-devel || true;
sudo rpm-ostree install --idempotent akmod-nct6687d || true;
echo "NOTICE: if rpm-ostree layered new packages, reboot and run Prepare fan PWM again.";
echo "== Trying stock/prebuilt nct6687 module first ==";
if sudo modprobe nct6687 force=true 2>/dev/null; then
  echo "OK: prebuilt nct6687 module loaded.";
else
  echo "WARN: prebuilt nct6687 module was not available for this kernel.";
  if [ ! -d "/lib/modules/$(uname -r)/build" ] || ! command -v make >/dev/null 2>&1 || ! command -v gcc >/dev/null 2>&1; then
    echo "ERROR: build tools or kernel-devel are missing. Reboot if rpm-ostree just layered them, then run Prepare fan PWM again.";
  else
    echo "== Building nct6687 for custom/ostree kernel $(uname -r) ==";
    mkdir -p "$(dirname {tools_dir})";
    if [ -d {tools_dir}/.git ]; then git -C {tools_dir} pull --ff-only || true; else git clone --depth 1 https://github.com/Fred78290/nct6687d {tools_dir}; fi;
    (cd {tools_dir} && make build) && {{
      sudo install -Dm644 {tools_dir}/"$(uname -r)"/nct6687.ko /var/lib/nct6687/nct6687.ko;
      sudo tee /etc/systemd/system/nct6687-load.service >/dev/null <<'EOF'
[Unit]
Description=Load nct6687 SuperIO sensor module
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/insmod /var/lib/nct6687/nct6687.ko force=1
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
      sudo systemctl daemon-reload;
      sudo systemctl enable nct6687-load.service;
      sudo modprobe -r nct6683 2>/dev/null || true;
      sudo insmod /var/lib/nct6687/nct6687.ko force=1 2>/dev/null || true;
      echo "OK: custom nct6687 module prepared under /var/lib/nct6687.";
    }};
  fi;
fi
'''.strip()

    def _comando_instalar_nct6687_debian(self, tools_dir):
        return f'''
echo "== Debian/Ubuntu: installing build and sensor dependencies ==";
sudo apt update || true;
sudo apt install -y lm-sensors git make gcc "linux-headers-$(uname -r)" || true;
mkdir -p "$(dirname {tools_dir})";
if [ -d {tools_dir}/.git ]; then git -C {tools_dir} pull --ff-only || true; else git clone --depth 1 https://github.com/Fred78290/nct6687d {tools_dir}; fi;
if [ -d "/lib/modules/$(uname -r)/build" ]; then
  (cd {tools_dir} && make build) && {{
    sudo install -Dm644 {tools_dir}/"$(uname -r)"/nct6687.ko "/lib/modules/$(uname -r)/kernel/drivers/hwmon/nct6687.ko";
    sudo depmod -a "$(uname -r)";
  }};
  sudo update-initramfs -u 2>/dev/null || true;
else
  echo "ERROR: /lib/modules/$(uname -r)/build is missing. Install matching linux headers and run again.";
fi
'''.strip()

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

    def _es_ostree(self):
        datos = self._os_release()
        texto = ' '.join([datos.get('ID', ''), datos.get('ID_LIKE', ''), datos.get('VARIANT_ID', ''), datos.get('NAME', '')]).lower()
        return bool(self._command_path('rpm-ostree') and any(x in texto for x in ['bazzite', 'silverblue', 'kinoite', 'ublue', 'atomic']))
