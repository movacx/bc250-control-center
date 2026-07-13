#!/usr/bin/env bash
set -euo pipefail

CONFIG="${BC250_GPU_CONFIG:-/etc/cyan-skillfish-governor-smu/config.toml}"
SERVICE="cyan-skillfish-governor-smu.service"

usage() {
  cat <<'EOF'
BC250 GPU Voltage Lab

Uso:
  bc250-gpu-voltage-lab.sh status
  bc250-gpu-voltage-lab.sh preview <nivel>
  bc250-gpu-voltage-lab.sh apply <nivel>
  bc250-gpu-voltage-lab.sh apply-custom 1850=970 2000=1000 ...
  bc250-gpu-voltage-lab.sh menu

Niveles:
  0 = valores default del governor
  1 = default +10 mV
  2 = default +20 mV
  3 = default +30 mV
  4 = default +40 mV
  5 = default +50 mV
  6 = default +60 mV, capado al techo estable conocido

Regla: nunca supera la curva estable conocida anterior.
EOF
}

python_status() {
  python3 - "$CONFIG" <<'PY'
from pathlib import Path
import re
import sys
config = Path(sys.argv[1])
base = {1850:930, 2000:960, 2050:980, 2100:1000, 2125:1020, 2150:1035, 2200:1050, 2300:1110, 2350:1130, 2400:1150}
stable = {1850:975, 2000:1000, 2050:1020, 2100:1035, 2125:1050, 2150:1085, 2200:1110, 2300:1110, 2350:1130, 2400:1150}
text = config.read_text() if config.exists() else ''
actual = {}
for block in re.findall(r'\[\[safe-points\]\](.*?)(?=\n\[\[safe-points\]\]|\Z)', text, re.S):
    f = re.search(r'^\s*frequency\s*=\s*(\d+)', block, re.M)
    v = re.search(r'^\s*voltage\s*=\s*(\d+)', block, re.M)
    if f and v:
        actual[int(f.group(1))] = int(v.group(1))
print(f'Config: {config}')
print()
print('MHz   actual   default   estable   margen_vs_estable')
print('----  -------  ----------   -------   -----------------')
for freq in [1850, 2000, 2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400]:
    if freq not in actual and freq not in base and freq not in stable:
        continue
    a = actual.get(freq)
    b = base.get(freq)
    s = stable.get(freq)
    margen = '--' if a is None or s is None else f'{a - s:+d} mV'
    print(f'{freq:<4}  {str(a or "--") + " mV":<7}  {str(b or "--") + " mV":<10}   {str(s or "--") + " mV":<7}   {margen}')
PY
}

python_preview() {
  local level="$1"
  LEVEL="$level" python3 - <<'PY'
import os
level = int(os.environ['LEVEL'])
base = {1850:930, 2000:960, 2050:980, 2100:1000, 2125:1020, 2150:1035, 2200:1050, 2300:1110, 2350:1130, 2400:1150}
stable = {1850:975, 2000:1000, 2050:1020, 2100:1035, 2125:1050, 2150:1085, 2200:1110, 2300:1110, 2350:1130, 2400:1150}
print(f'Nivel {level}: default +{level * 10} mV, capado al techo estable')
print('MHz   nuevo   estable')
print('----  ------  -------')
for freq in [1850, 2000, 2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400]:
    nuevo = min(base[freq] + level * 10, stable[freq])
    print(f'{freq:<4}  {nuevo:<6}  {stable[freq]}')
PY
}


busctl_uint() {
  busctl get-property com.cyanskillfish.Governor "$1" com.cyanskillfish.Governor.Range "$2" 2>/dev/null | awk '{print $2}'
}

capture_current_range() {
  RANGE_MIN="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Min || true)"
  RANGE_MAX="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Max || true)"
  if [[ ! "$RANGE_MIN" =~ ^[0-9]+$ || ! "$RANGE_MAX" =~ ^[0-9]+$ ]]; then
    RANGE_MIN=""
    RANGE_MAX=""
  fi
}

restore_current_range() {
  if [[ -z "${RANGE_MIN:-}" || -z "${RANGE_MAX:-}" ]]; then
    echo "Rango anterior no disponible; no se restaura D-Bus."
    return 0
  fi
  echo "Restaurando rango D-Bus anterior: ${RANGE_MIN}-${RANGE_MAX} MHz"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if busctl call com.cyanskillfish.Governor /com/cyanskillfish/Governor com.cyanskillfish.Governor.PerformanceMode SetRange uu "$RANGE_MIN" "$RANGE_MAX" >/dev/null 2>&1; then
      echo "OK: rango restaurado a ${RANGE_MIN}-${RANGE_MAX} MHz"
      return 0
    fi
    sleep 0.5
  done
  echo "AVISO: no se pudo restaurar el rango D-Bus anterior. Revisa el panel GPU."
}

restart_governor_preserving_range() {
  capture_current_range
  if [[ -n "${RANGE_MIN:-}" && -n "${RANGE_MAX:-}" ]]; then
    echo "Rango actual antes del cambio: ${RANGE_MIN}-${RANGE_MAX} MHz"
  fi
  systemctl restart "$SERVICE"
  restore_current_range
  systemctl status "$SERVICE" --no-pager || true
}

apply_level() {
  local level="$1"
  if [[ ! "$level" =~ ^[0-6]$ ]]; then
    echo "ERROR: nivel invalido. Usa 0..6." >&2
    exit 1
  fi
  if [[ $EUID -ne 0 ]]; then
    exec sudo "$0" apply "$level"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: no existe $CONFIG" >&2
    exit 1
  fi
  local backup="${CONFIG}.backup.bcc-voltage-lab-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  echo "Backup creado: $backup"
  LEVEL="$level" CONFIG="$CONFIG" python3 - <<'PY'
from pathlib import Path
import os
import re
config = Path(os.environ['CONFIG'])
level = int(os.environ['LEVEL'])
base = {1850:930, 2000:960, 2050:980, 2100:1000, 2125:1020, 2150:1035, 2200:1050, 2300:1110, 2350:1130, 2400:1150}
stable = {1850:975, 2000:1000, 2050:1020, 2100:1035, 2125:1050, 2150:1085, 2200:1110, 2300:1110, 2350:1130, 2400:1150}
text = config.read_text()

def repl(match):
    block = match.group(0)
    f = re.search(r'(^\s*frequency\s*=\s*)(\d+)', block, re.M)
    v = re.search(r'(^\s*voltage\s*=\s*)(\d+)', block, re.M)
    if not f or not v:
        return block
    freq = int(f.group(2))
    if freq not in base:
        return block
    nuevo = min(base[freq] + level * 10, stable[freq])
    return re.sub(r'(^\s*voltage\s*=\s*)\d+', lambda m: m.group(1) + str(nuevo), block, count=1, flags=re.M)

nuevo_texto = re.sub(r'\[\[safe-points\]\].*?(?=\n\[\[safe-points\]\]|\Z)', repl, text, flags=re.S)
config.write_text(nuevo_texto)
print(f'Aplicado nivel {level}: default +{level * 10} mV, capado al techo estable')
PY
  restart_governor_preserving_range
  echo
  echo "Sugerencia de prueba: no saltes directo a 2200. Prueba por frecuencia y carga corta."
}


apply_custom() {
  if [[ $# -lt 1 ]]; then
    echo "ERROR: especifica valores tipo 1850=970 2000=1000" >&2
    exit 1
  fi
  if [[ $EUID -ne 0 ]]; then
    exec sudo "$0" apply-custom "$@"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: no existe $CONFIG" >&2
    exit 1
  fi
  local backup="${CONFIG}.backup.bcc-voltage-custom-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  echo "Backup creado: $backup"
  CUSTOM_VALUES="$*" CONFIG="$CONFIG" python3 - <<'PY'
from pathlib import Path
import os
import re
config = Path(os.environ['CONFIG'])
allowed = {1850, 2000, 2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400}
updates = {}
for item in os.environ.get('CUSTOM_VALUES', '').split():
    if '=' not in item:
        raise SystemExit(f'Valor invalido: {item}')
    left, right = item.split('=', 1)
    freq = int(left)
    volt = int(right)
    if freq not in allowed:
        raise SystemExit(f'Frecuencia no permitida para lab: {freq}')
    if volt < 600 or volt > 1150:
        raise SystemExit(f'Voltaje fuera de limite seguro para {freq}: {volt} mV. Maximo permitido: 1150 mV')
    updates[freq] = volt
text = config.read_text()

def repl(match):
    block = match.group(0)
    f = re.search(r'(^\s*frequency\s*=\s*)(\d+)', block, re.M)
    v = re.search(r'(^\s*voltage\s*=\s*)(\d+)', block, re.M)
    if not f or not v:
        return block
    freq = int(f.group(2))
    if freq not in updates:
        return block
    return re.sub(r'(^\s*voltage\s*=\s*)\d+', lambda m: m.group(1) + str(updates[freq]), block, count=1, flags=re.M)

nuevo_texto = re.sub(r'\[\[safe-points\]\].*?(?=\n\[\[safe-points\]\]|\Z)', repl, text, flags=re.S)
config.write_text(nuevo_texto)
print('Aplicado nivel personalizado:')
for freq in sorted(updates):
    print(f'  {freq} MHz -> {updates[freq]} mV')
PY
  restart_governor_preserving_range
  echo
  echo "Personalizado aplicado. Limite de seguridad: ningun valor supera 1150 mV."
}

menu() {
  while true; do
    clear || true
    echo "== BC250 GPU Voltage Lab =="
    echo
    python_status || true
    echo
    echo "Elige nivel a aplicar:"
    echo "  1) +10 mV sobre default"
    echo "  2) +20 mV sobre default"
    echo "  3) +30 mV sobre default"
    echo "  4) +40 mV sobre default"
    echo "  5) +50 mV sobre default"
    echo "  6) +60 mV / techo estable conocido"
    echo "  p) previsualizar nivel"
    echo "  q) salir"
    echo
    read -r -p "Opcion: " opt
    case "$opt" in
      [1-6])
        echo
        python_preview "$opt"
        echo
        read -r -p "Aplicar nivel $opt y reiniciar governor? escribe SI: " ok
        if [[ "$ok" == "SI" ]]; then
          "$0" apply "$opt"
          read -r -p "Enter para continuar..." _
        fi
        ;;
      p|P)
        read -r -p "Nivel 0..6: " lvl
        python_preview "$lvl" || true
        read -r -p "Enter para continuar..." _
        ;;
      q|Q) exit 0 ;;
    esac
  done
}

cmd="${1:-menu}"
case "$cmd" in
  status) python_status ;;
  preview) python_preview "${2:-}" ;;
  apply) apply_level "${2:-}" ;;
  apply-custom) shift; apply_custom "$@" ;;
  menu) menu ;;
  -h|--help|help) usage ;;
  *) usage; exit 1 ;;
esac
