#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"

STATE_DIR="/var/lib/bc250-control-center"
SOURCE_DIR="$STATE_DIR/nct6687d-src"
MODULE_ROOT="$STATE_DIR/kernel-modules"
LOADER_PATH="/usr/local/sbin/bc250-load-nct6687"
SERVICE_PATH="/etc/systemd/system/nct6687-load.service"
INPUT_SOURCE="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KVER="$(uname -r)"
MODULE_PATH="$MODULE_ROOT/$KVER/nct6687.ko"

bold "Bazzite: installing persistent nct6687 loader"
[[ -f "$INPUT_SOURCE/Makefile" && -f "$INPUT_SOURCE/nct6687.c" ]] || {
  error "nct6687 source is unavailable at $INPUT_SOURCE"
  exit 24
}
[[ -f "$MODULE_PATH" ]] || {
  error "The kernel-specific module is unavailable at $MODULE_PATH"
  exit 24
}

as_root install -d -m 0755 "$STATE_DIR" "$SOURCE_DIR" "$MODULE_ROOT/$KVER" /usr/local/sbin
as_root install -m 0644 "$INPUT_SOURCE/Makefile" "$SOURCE_DIR/Makefile"
as_root install -m 0644 "$INPUT_SOURCE/nct6687.c" "$SOURCE_DIR/nct6687.c"
if [[ -f "$INPUT_SOURCE/LICENSE" ]]; then
  as_root install -m 0644 "$INPUT_SOURCE/LICENSE" "$SOURCE_DIR/LICENSE"
fi

# rpm-ostree keeps /usr immutable. The loader builds and loads a per-kernel
# module from /var, which survives deployments and kernel upgrades.
as_root tee "$LOADER_PATH" >/dev/null <<'LOADER'
#!/usr/bin/env bash
set -Eeuo pipefail

STATE_DIR="/var/lib/bc250-control-center"
SOURCE_DIR="$STATE_DIR/nct6687d-src"
MODULE_ROOT="$STATE_DIR/kernel-modules"
RUNTIME_DIR="/run/bc250-control-center"
KVER="$(uname -r)"
MODULE_DIR="$MODULE_ROOT/$KVER"
MODULE_PATH="$MODULE_DIR/nct6687.ko"
BUILD_OUTPUT="$SOURCE_DIR/$KVER/nct6687.ko"
ERRLOG="$RUNTIME_DIR/nct6687-load.err"
MODPROBE="$(command -v modprobe || echo /usr/sbin/modprobe)"
INSMOD="$(command -v insmod || echo /usr/sbin/insmod)"
LSMOD="$(command -v lsmod || echo /usr/sbin/lsmod)"
UDEVADM="$(command -v udevadm || true)"

install -d -m 0755 "$RUNTIME_DIR" "$MODULE_DIR"

module_matches_kernel() {
  [[ -r "$MODULE_PATH" ]] || return 1
  command -v modinfo >/dev/null 2>&1 || return 0
  local vermagic
  vermagic="$(modinfo -F vermagic "$MODULE_PATH" 2>/dev/null || true)"
  [[ "$vermagic" == "$KVER "* || "$vermagic" == "$KVER"* ]]
}

build_for_current_kernel() {
  [[ -f "$SOURCE_DIR/Makefile" && -f "$SOURCE_DIR/nct6687.c" ]] || {
    echo "ERROR: persisted nct6687 source is missing" >&2
    return 1
  }
  [[ -f "/lib/modules/$KVER/build/Makefile" ]] || {
    echo "ERROR: matching kernel-devel is unavailable for $KVER" >&2
    return 1
  }
  command -v make >/dev/null 2>&1 || { echo "ERROR: make is unavailable" >&2; return 1; }
  command -v gcc >/dev/null 2>&1 || command -v clang >/dev/null 2>&1 || {
    echo "ERROR: no kernel compiler is available" >&2
    return 1
  }
  echo "Building nct6687 for $KVER" >&2
  make -C "$SOURCE_DIR" kver="$KVER" build
  [[ -f "$BUILD_OUTPUT" ]] || { echo "ERROR: build did not produce $BUILD_OUTPUT" >&2; return 1; }
  install -m 0644 "$BUILD_OUTPUT" "$MODULE_PATH"
}

label_module() {
  if command -v chcon >/dev/null 2>&1; then
    chcon -t modules_object_t "$MODULE_PATH" || true
  fi
}

settle_hwmon() {
  if [[ -n "$UDEVADM" ]]; then
    "$UDEVADM" trigger --subsystem-match=hwmon 2>/dev/null || true
    "$UDEVADM" settle --timeout=15 2>/dev/null || true
  fi
  sleep 1
}

is_ready() {
  local name_file name dir
  for name_file in /sys/class/hwmon/hwmon*/name; do
    [[ -r "$name_file" ]] || continue
    name="$(cat "$name_file" 2>/dev/null || true)"
    case "$name" in
      nct668*|nct67*|nct*)
        dir="${name_file%/name}"
        if compgen -G "$dir/fan*_input" >/dev/null && compgen -G "$dir/pwm*" >/dev/null; then
          echo "OK: NCT fan/PWM hwmon ready at $dir ($name)" >&2
          return 0
        fi
        ;;
    esac
  done
  return 1
}

load_module() {
  : >"$ERRLOG"
  "$INSMOD" "$MODULE_PATH" force=1 2>>"$ERRLOG" || \
    "$INSMOD" "$MODULE_PATH" force=true 2>>"$ERRLOG" || \
    "$INSMOD" "$MODULE_PATH" 2>>"$ERRLOG"
}

if "$LSMOD" | grep -q '^nct6687 '; then
  settle_hwmon
  is_ready && exit 0
fi

if ! module_matches_kernel; then
  build_for_current_kernel
fi
label_module

for attempt in $(seq 1 12); do
  "$MODPROBE" -r nct6683 2>/dev/null || true
  "$MODPROBE" -r nct6687 2>/dev/null || true
  if load_module; then
    settle_hwmon
    if "$LSMOD" | grep -q '^nct6687 ' && is_ready; then
      exit 0
    fi
  fi
  sleep 2
done

cat "$ERRLOG" >&2 2>/dev/null || true
if command -v mokutil >/dev/null 2>&1; then mokutil --sb-state >&2 || true; fi
if command -v getenforce >/dev/null 2>&1; then echo "SELinux: $(getenforce)" >&2; fi
ls -lZ "$MODULE_PATH" >&2 2>/dev/null || ls -l "$MODULE_PATH" >&2 || true
echo "ERROR: nct6687 could not be loaded for $KVER" >&2
exit 1
LOADER
as_root chmod 0755 "$LOADER_PATH"

if have chcon; then
  as_root chcon -t modules_object_t "$MODULE_PATH" || warn "Could not apply SELinux module label"
fi

as_root tee "$SERVICE_PATH" >/dev/null <<'UNIT'
[Unit]
Description=Build and load nct6687 for BC250 fan PWM on Bazzite
Documentation=https://github.com/Fred78290/nct6687d
After=local-fs.target systemd-udevd.service systemd-modules-load.service
Wants=systemd-udevd.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
RuntimeDirectory=bc250-control-center
RuntimeDirectoryMode=0755
ExecStartPre=/usr/bin/sleep 5
ExecStart=/usr/local/sbin/bc250-load-nct6687
TimeoutStartSec=180
RemainAfterExit=yes
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT
as_root systemctl daemon-reload
as_root systemctl enable nct6687-load.service
as_root systemctl reset-failed nct6687-load.service || true
as_root systemctl restart nct6687-load.service || warn "nct6687 service did not become ready immediately; final verification will show its journal"
