#!/usr/bin/env bash
set -euo pipefail

CONFIG="${BC250_GPU_CONFIG:-/etc/cyan-skillfish-governor-smu/config.toml}"
SERVICE="cyan-skillfish-governor-smu.service"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CURVE_EDITOR="${BC250_GOVERNOR_TOML_EDITOR:-${SCRIPT_DIR}/../../Repository/governor_toml.py}"

usage() {
  cat <<'EOF'
BC250 GPU Voltage Lab

Uso:
  bc250-gpu-voltage-lab.sh status
  bc250-gpu-voltage-lab.sh preview <nivel>
  bc250-gpu-voltage-lab.sh apply <nivel>
  bc250-gpu-voltage-lab.sh apply-custom 500=700 1850=970 2000=1000 ...
  bc250-gpu-voltage-lab.sh menu

Niveles:
  0 = valores default del governor
  3 = default +30 mV en cada punto desde 2000 MHz
  6 = default +60 mV en cada punto desde 2000 MHz

El nivel 0 restaura los 17 voltajes originales, incluidos los puntos comentados.
EOF
}

python_status() {
  python3 "$CURVE_EDITOR" status "$CONFIG"
}

python_preview() {
  local level="$1"
  python3 "$CURVE_EDITOR" preview-voltage-level "$level"
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

require_current_range() {
  if ! systemctl is-active --quiet "$SERVICE"; then
    echo "ERROR: el governor debe estar activo antes de cambiar la curva de voltaje." >&2
    return 1
  fi
  capture_current_range
  if [[ -z "${RANGE_MIN:-}" || -z "${RANGE_MAX:-}" ]]; then
    echo "ERROR: no se pudo leer el rango D-Bus actual; no se modificó la curva." >&2
    return 1
  fi
  echo "Rango protegido antes del cambio: ${RANGE_MIN}-${RANGE_MAX} MHz"
}

restore_current_range() {
  if [[ -z "${RANGE_MIN:-}" || -z "${RANGE_MAX:-}" ]]; then
    echo "ERROR: rango anterior no disponible; no se puede confirmar una restauración segura." >&2
    return 1
  fi
  echo "Restaurando rango D-Bus anterior: ${RANGE_MIN}-${RANGE_MAX} MHz"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    local allowed_min allowed_max target_min target_max
    allowed_min="$(busctl_uint /com/cyanskillfish/Governor/Range/Allowed Min || true)"
    allowed_max="$(busctl_uint /com/cyanskillfish/Governor/Range/Allowed Max || true)"
    if [[ "$allowed_min" =~ ^[0-9]+$ && "$allowed_max" =~ ^[0-9]+$ ]]; then
      target_min="$RANGE_MIN"
      target_max="$RANGE_MAX"
      (( target_min < allowed_min )) && target_min="$allowed_min"
      (( target_min > allowed_max )) && target_min="$allowed_max"
      (( target_max < allowed_min )) && target_max="$allowed_min"
      (( target_max > allowed_max )) && target_max="$allowed_max"
      (( target_min > target_max )) && target_min="$target_max"
    else
      sleep 0.5
      continue
    fi
    if busctl call com.cyanskillfish.Governor /com/cyanskillfish/Governor com.cyanskillfish.Governor.PerformanceMode SetRange uu "$target_min" "$target_max" >/dev/null 2>&1; then
      local current_min current_max
      current_min="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Min || true)"
      current_max="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Max || true)"
      if [[ "$current_min" == "$target_min" && "$current_max" == "$target_max" ]]; then
        if [[ "$target_min" != "$RANGE_MIN" || "$target_max" != "$RANGE_MAX" ]]; then
          echo "AVISO: el rango anterior excede los puntos activos; se limito de forma segura."
        fi
        echo "OK: rango restaurado y verificado en ${target_min}-${target_max} MHz"
        return 0
      fi
    fi
    sleep 0.5
  done
  echo "ERROR: no se pudo restaurar el rango D-Bus anterior. No inicies una carga GPU." >&2
  return 1
}

restart_governor_preserving_range() {
  systemctl restart "$SERVICE"
  restore_current_range
  systemctl status "$SERVICE" --no-pager || true
}

apply_level() {
  local level="$1"
  if [[ "$level" != "0" && "$level" != "3" && "$level" != "6" ]]; then
    echo "ERROR: nivel invalido. Usa 0, 3 o 6." >&2
    exit 1
  fi
  if [[ $EUID -ne 0 ]]; then
    exec sudo "$0" apply "$level"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: no existe $CONFIG" >&2
    exit 1
  fi
  require_current_range
  local backup="${CONFIG}.backup.bcc-voltage-lab-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  echo "Backup creado: $backup"
  python3 "$CURVE_EDITOR" apply-voltage-level "$CONFIG" "$level"
  restart_governor_preserving_range
  echo
  echo "Sugerencia de prueba: no saltes directo a 2200. Prueba por frecuencia y carga corta."
}


apply_custom() {
  if [[ $# -lt 1 ]]; then
    echo "ERROR: especifica valores tipo 500=700 1850=970 2000=1000" >&2
    exit 1
  fi
  if [[ $EUID -ne 0 ]]; then
    exec sudo "$0" apply-custom "$@"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: no existe $CONFIG" >&2
    exit 1
  fi
  require_current_range
  local backup="${CONFIG}.backup.bcc-voltage-custom-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  echo "Backup creado: $backup"
  python3 "$CURVE_EDITOR" apply-custom-voltage "$CONFIG" "$@"
  restart_governor_preserving_range
  echo
  echo "Personalizado aplicado. Limite del editor: 600-1210 mV."
}

menu() {
  while true; do
    clear || true
    echo "== BC250 GPU Voltage Lab =="
    echo
    python_status || true
    echo
    echo "Elige nivel a aplicar:"
    echo "  0) restaurar curva original completa"
    echo "  3) +30 mV sobre default"
    echo "  6) +60 mV sobre default"
    echo "  p) previsualizar nivel"
    echo "  q) salir"
    echo
    read -r -p "Opcion: " opt
    case "$opt" in
      0|3|6)
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
        read -r -p "Nivel 0, 3 o 6: " lvl
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
