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
PACKAGED_MODULE="$(modinfo -n nct6687 2>/dev/null || true)"
SOURCE_AVAILABLE=0
CUSTOM_MODULE_AVAILABLE=0
PACKAGED_MODULE_AVAILABLE=0

[[ -f "$INPUT_SOURCE/Makefile" && -f "$INPUT_SOURCE/nct6687.c" ]] && SOURCE_AVAILABLE=1
[[ -f "$MODULE_PATH" ]] && CUSTOM_MODULE_AVAILABLE=1
[[ -n "$PACKAGED_MODULE" && -r "$PACKAGED_MODULE" ]] && PACKAGED_MODULE_AVAILABLE=1

bold "Bazzite: installing persistent nct6687 loader"
if [[ "$CUSTOM_MODULE_AVAILABLE" -ne 1 && "$PACKAGED_MODULE_AVAILABLE" -ne 1 ]]; then
  error "No usable nct6687 module is available for $KVER"
  error "Run Prepare fan PWM first so the packaged module or a kernel-specific build is available"
  exit 24
fi

as_root install -d -m 0755 "$STATE_DIR" "$SOURCE_DIR" "$MODULE_ROOT/$KVER" /usr/local/sbin
if [[ "$SOURCE_AVAILABLE" -eq 1 ]]; then
  as_root install -m 0644 "$INPUT_SOURCE/Makefile" "$SOURCE_DIR/Makefile"
  as_root install -m 0644 "$INPUT_SOURCE/nct6687.c" "$SOURCE_DIR/nct6687.c"
  if [[ -f "$INPUT_SOURCE/LICENSE" ]]; then
    as_root install -m 0644 "$INPUT_SOURCE/LICENSE" "$SOURCE_DIR/LICENSE"
  fi
else
  warn "nct6687 source is not present at $INPUT_SOURCE; the service will use the packaged module or the prepared current-kernel module"
fi

# rpm-ostree keeps /usr immutable. Prefer the module supplied for the active
# deployment through modprobe. A per-kernel module under /var is a fallback for
# kernels where Bazzite does not ship nct6687, and persisted source can rebuild
# that fallback after a kernel upgrade.
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
MODINFO="$(command -v modinfo || true)"
UDEVADM="$(command -v udevadm || true)"

install -d -m 0755 "$RUNTIME_DIR" "$MODULE_DIR"

module_matches_kernel() {
  [[ -r "$MODULE_PATH" ]] || return 1
  [[ -n "$MODINFO" ]] || return 0
  local vermagic
  vermagic="$($MODINFO -F vermagic "$MODULE_PATH" 2>/dev/null || true)"
  [[ "$vermagic" == "$KVER "* || "$vermagic" == "$KVER"* ]]
}

build_for_current_kernel() {
  [[ -f "$SOURCE_DIR/Makefile" && -f "$SOURCE_DIR/nct6687.c" ]] || {
    echo "ERROR: persisted nct6687 source is missing" >&2
    return 1
  }
  local build_dir="" declared="" candidate vermagic module_release
  for candidate in "/usr/lib/modules/$KVER/build" "/lib/modules/$KVER/build"; do
    [[ -f "$candidate/Makefile" ]] || continue
    if [[ -r "$candidate/include/config/kernel.release" ]]; then
      IFS= read -r declared < "$candidate/include/config/kernel.release" || true
    else
      declared=""
    fi
    if [[ -n "$declared" && "$declared" != "$KVER" ]]; then
      echo "ERROR: kernel-devel mismatch: $candidate belongs to $declared but the running kernel is $KVER" >&2
      continue
    fi
    build_dir="$candidate"
    break
  done
  [[ -n "$build_dir" ]] || {
    echo "ERROR: matching kernel-devel is unavailable for $KVER" >&2
    echo "Update Bazzite, reboot into the matching deployment, then run Prepare PWM driver again." >&2
    return 1
  }
  command -v make >/dev/null 2>&1 || { echo "ERROR: make is unavailable" >&2; return 1; }
  command -v gcc >/dev/null 2>&1 || command -v clang >/dev/null 2>&1 || {
    echo "ERROR: no kernel compiler is available" >&2
    return 1
  }
  echo "Building nct6687 for $KVER with verified headers at $build_dir" >&2
  make -C "$SOURCE_DIR" kver="$KVER" build
  [[ -f "$BUILD_OUTPUT" ]] || { echo "ERROR: build did not produce $BUILD_OUTPUT" >&2; return 1; }
  if [[ -n "$MODINFO" ]]; then
    vermagic="$($MODINFO -F vermagic "$BUILD_OUTPUT" 2>/dev/null || true)"
    module_release="${vermagic%% *}"
    [[ "$module_release" == "$KVER" ]] || {
      echo "ERROR: rebuilt nct6687 has vermagic $module_release, expected $KVER; refusing to install it" >&2
      return 1
    }
  fi
  install -m 0644 "$BUILD_OUTPUT" "$MODULE_PATH"
}

label_module() {
  [[ -r "$MODULE_PATH" ]] || return 0
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

unload_conflicts() {
  "$MODPROBE" -r nct6683 2>/dev/null || true
  "$MODPROBE" -r nct6687 2>/dev/null || true
}

try_packaged_module() {
  [[ -n "$MODINFO" ]] || return 1
  "$MODINFO" -n nct6687 >/dev/null 2>&1 || return 1
  unload_conflicts
  : >"$ERRLOG"
  "$MODPROBE" nct6687 force=true 2>>"$ERRLOG" || "$MODPROBE" nct6687 2>>"$ERRLOG" || return 1
  settle_hwmon
  "$LSMOD" | grep -q '^nct6687 ' && is_ready
}

load_custom_module() {
  : >"$ERRLOG"
  "$INSMOD" "$MODULE_PATH" force=1 2>>"$ERRLOG" || \
    "$INSMOD" "$MODULE_PATH" force=true 2>>"$ERRLOG" || \
    "$INSMOD" "$MODULE_PATH" 2>>"$ERRLOG"
}

if "$LSMOD" | grep -q '^nct6687 '; then
  settle_hwmon
  is_ready && exit 0
fi

if try_packaged_module; then
  echo "OK: loaded the nct6687 module supplied by the active Bazzite deployment" >&2
  exit 0
fi

if ! module_matches_kernel; then
  build_for_current_kernel
fi
label_module

for attempt in $(seq 1 12); do
  unload_conflicts
  if load_custom_module; then
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
if [[ -r "$MODULE_PATH" ]]; then
  ls -lZ "$MODULE_PATH" >&2 2>/dev/null || ls -l "$MODULE_PATH" >&2 || true
fi
echo "ERROR: nct6687 could not be loaded for $KVER" >&2
exit 1
LOADER
as_root chmod 0755 "$LOADER_PATH"

if [[ -f "$MODULE_PATH" ]] && have chcon; then
  as_root chcon -t modules_object_t "$MODULE_PATH" || warn "Could not apply SELinux module label"
fi

as_root tee "$SERVICE_PATH" >/dev/null <<'UNIT'
[Unit]
Description=Load nct6687 for BC250 fan PWM on Bazzite
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
