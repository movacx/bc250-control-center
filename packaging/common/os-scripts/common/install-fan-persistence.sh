#!/usr/bin/env bash
set -Eeuo pipefail
echo "== Installing persistent nct6687 boot loader ==";
echo "Please wait and do not close this terminal. Configuring the boot loader can take up to one minute.";
sudo install -d /usr/local/sbin;
sudo tee /usr/local/sbin/bc250-load-nct6687 >/dev/null <<'EOF'
#!/usr/bin/env bash
set -u
MODPROBE="$(command -v modprobe || echo /usr/sbin/modprobe)"
INSMOD="$(command -v insmod || echo /usr/sbin/insmod)"
LSMOD="$(command -v lsmod || echo /usr/sbin/lsmod)"
DEPMOD="$(command -v depmod || echo /usr/sbin/depmod)"
UDEVADM="$(command -v udevadm || true)"
DMESG="$(command -v dmesg || true)"
MODINFO="$(command -v modinfo || true)"
RUNTIME_DIR="/run/bc250-control-center"
install -d -m 0755 "$RUNTIME_DIR"
ERRLOG="$RUNTIME_DIR/nct6687-load.err"
KVER="$(uname -r)"
VAR_KO="/var/lib/nct6687/nct6687.ko"
TREE_KO=""
for p in \
  "/usr/lib/modules/$KVER/kernel/drivers/hwmon/nct6687.ko" \
  "/lib/modules/$KVER/kernel/drivers/hwmon/nct6687.ko"; do
  [ -r "$p" ] && TREE_KO="$p" && break
done

settle_hwmon() {
  if [ -n "$UDEVADM" ]; then
    "$UDEVADM" trigger --subsystem-match=hwmon 2>/dev/null || true
    "$UDEVADM" settle --timeout=15 2>/dev/null || true
  fi
  sleep 1
}

is_ready() {
  for n in /sys/class/hwmon/hwmon*/name; do
    [ -r "$n" ] || continue
    name="$(cat "$n" 2>/dev/null || true)"
    case "$name" in
      nct668*|nct67*|nct*)
        dir="${n%/name}"
        if ls "$dir"/fan*_input "$dir"/pwm* >/dev/null 2>&1; then
          echo "OK: NCT hwmon ready at $dir ($name)" >&2
          return 0
        fi
      ;;
    esac
  done
  if command -v sensors >/dev/null 2>&1; then
    sensors 2>/dev/null | awk '/nct6686-isa/{seen=1} seen && /(Fan|fan|pwm)[ #0-9]*:/ {ok=1} END{exit ok?0:1}' && return 0
  fi
  return 1
}

unload_all() {
  "$MODPROBE" -r nct6683 2>/dev/null || true
  "$MODPROBE" -r nct6687 2>/dev/null || true
}

module_matches_kernel() {
  local module_path="$1" vermagic module_release
  [ -r "$module_path" ] || return 1
  [ -n "$MODINFO" ] || return 0
  vermagic="$($MODINFO -F vermagic "$module_path" 2>/dev/null || true)"
  module_release="${vermagic%% *}"
  if [ "$module_release" != "$KVER" ]; then
    echo "WARN: ignoring $module_path because its vermagic is ${module_release:-unknown}, not $KVER" >&2
    return 1
  fi
  return 0
}

try_ready_after_load() {
  settle_hwmon
  if is_ready; then
    exit 0
  fi
  return 1
}

if "$LSMOD" | grep -q '^nct6687 '; then
  if try_ready_after_load; then exit 0; fi
  echo "WARN: nct6687 was loaded but no NCT fan/PWM hwmon appeared; reloading." >&2
  unload_all
fi

if [ -n "$TREE_KO" ]; then
  "$DEPMOD" -a "$KVER" 2>/dev/null || true
fi

attempt=1
while [ "$attempt" -le 60 ]; do
  : > "$ERRLOG"
  unload_all

  if module_matches_kernel "$VAR_KO"; then
    echo "Trying $VAR_KO, attempt $attempt/60" >&2
    "$INSMOD" "$VAR_KO" force=1 2>>"$ERRLOG" || "$INSMOD" "$VAR_KO" force=true 2>>"$ERRLOG" || "$INSMOD" "$VAR_KO" 2>>"$ERRLOG" || true
    if "$LSMOD" | grep -q '^nct6687 ' && try_ready_after_load; then exit 0; fi
    unload_all
  fi

  if [ -n "$TREE_KO" ] && module_matches_kernel "$TREE_KO"; then
    echo "Trying kernel tree module $TREE_KO, attempt $attempt/60" >&2
    "$INSMOD" "$TREE_KO" force=1 2>>"$ERRLOG" || "$INSMOD" "$TREE_KO" force=true 2>>"$ERRLOG" || "$INSMOD" "$TREE_KO" 2>>"$ERRLOG" || true
    if "$LSMOD" | grep -q '^nct6687 ' && try_ready_after_load; then exit 0; fi
    unload_all
  fi

  echo "Trying modprobe nct6687, attempt $attempt/60" >&2
  "$MODPROBE" nct6687 force=true 2>>"$ERRLOG" || "$MODPROBE" nct6687 2>>"$ERRLOG" || true
  if "$LSMOD" | grep -q '^nct6687 ' && try_ready_after_load; then exit 0; fi

  if [ -s "$ERRLOG" ]; then
    cat "$ERRLOG" >&2
  fi
  echo "nct6687 fan/PWM hwmon is not ready yet; boot retry $attempt/60" >&2
  attempt=$((attempt + 1))
  sleep 2
done

echo "ERROR: could not expose nct6687 fan/PWM hwmon after boot retries" >&2
echo "== nct6687-load diagnostics ==" >&2
"$LSMOD" | grep -E 'nct6683|nct6687' >&2 || true
for n in /sys/class/hwmon/hwmon*/name; do [ -r "$n" ] && echo "$n: $(cat "$n" 2>/dev/null)" >&2; done
if [ -n "$DMESG" ]; then
  "$DMESG" 2>/dev/null | grep -Ei 'nct668|superio|hwmon|ACPI' | tail -80 >&2 || true
fi
[ -s "$ERRLOG" ] && cat "$ERRLOG" >&2
exit 1
EOF
sudo chmod 0755 /usr/local/sbin/bc250-load-nct6687;
if [ -f /var/lib/nct6687/nct6687.ko ]; then
  echo "== Applying SELinux kernel-module label when available ==";
  sudo chcon -t modules_object_t /var/lib/nct6687/nct6687.ko 2>/dev/null || true;
  sudo restorecon -v /var/lib/nct6687/nct6687.ko 2>/dev/null || true;
fi;
sudo install -d -m 0755 /var/lib/bc250-control-center;
FAN_PWM_HELPER=/usr/libexec/bc250-control-center/bc250-fan-pwm-helper
if [ -f /run/openrc/softlevel ] \
  && command -v openrc-run >/dev/null 2>&1 \
  && command -v rc-update >/dev/null 2>&1 \
  && command -v rc-service >/dev/null 2>&1; then
  OPENRC_HELPER=/usr/libexec/bc250-control-center/bc250-openrc-service-helper
  [ -x "$OPENRC_HELPER" ] || { echo "ERROR: protected BC250 OpenRC service helper is missing; reinstall Control Center." >&2; exit 1; }
  sudo "$OPENRC_HELPER" install nct6687-load
  sudo rc-service nct6687-load restart 2>/dev/null || sudo rc-service nct6687-load start 2>/dev/null || true
  if [ -x "$FAN_PWM_HELPER" ]; then
    echo "== Installing boot-time fan PWM restore (no password needed after this) ==";
    sudo "$OPENRC_HELPER" install bc250-fan-pwm-restore
    sudo rc-service bc250-fan-pwm-restore restart 2>/dev/null || sudo rc-service bc250-fan-pwm-restore start 2>/dev/null || true
  fi
elif [ ! -d /run/systemd/system ] || ! command -v systemctl >/dev/null 2>&1; then
  # runit, s6, dinit and sysvinit reach here. Writing a systemd unit for them
  # leaves a file in /etc/systemd/system that nothing will ever read, and then
  # fails at systemctl. Say what did and did not happen instead: the module
  # itself is already built and installed above, so fan control works for this
  # session; only loading it automatically at boot is missing.
  echo "== This system does not run systemd or OpenRC ==";
  echo "The nct6687 module is installed and fan control works now.";
  echo "Automatic loading at boot is not configured: add 'nct6687' to your";
  echo "init system's module list, or run bc250-load-nct6687 at startup.";
else
sudo tee /etc/systemd/system/nct6687-load.service >/dev/null <<'EOF'
[Unit]
Description=Load nct6687 SuperIO sensor module for BC250 fan PWM
After=local-fs.target systemd-udevd.service systemd-udev-settle.service systemd-modules-load.service multi-user.target graphical.target
Wants=systemd-udev-settle.service systemd-modules-load.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
RuntimeDirectory=bc250-control-center
RuntimeDirectoryMode=0755
ExecStartPre=/usr/bin/sleep 20
ExecStart=/usr/local/sbin/bc250-load-nct6687
TimeoutStartSec=300
RemainAfterExit=yes
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload || true;
sudo systemctl enable nct6687-load.service || true;
sudo systemctl reset-failed nct6687-load.service 2>/dev/null || true;
sudo systemctl restart nct6687-load.service 2>/dev/null || sudo systemctl start nct6687-load.service 2>/dev/null || true
if [ -x "$FAN_PWM_HELPER" ]; then
  echo "== Installing boot-time fan PWM restore (no password needed after this) ==";
# nct6687-load.service runs after graphical.target so its 20 s wait never
# delays the login screen. A unit that is WantedBy=multi-user.target and ordered
# after it closes an ordering cycle (multi-user.target is implicitly ordered
# after the units it wants), and systemd then silently drops this job at boot.
# Ordering it after multi-user.target as well tells systemd not to add that
# implicit edge.
sudo tee /etc/systemd/system/bc250-fan-pwm-restore.service >/dev/null <<EOF
[Unit]
Description=Restore the last BC250 fan PWM duty at boot
After=nct6687-load.service multi-user.target
Requires=nct6687-load.service
ConditionPathExists=/var/lib/bc250-control-center/fan-last-applied.json

[Service]
Type=oneshot
ExecStart=$FAN_PWM_HELPER --restore-boot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload || true;
  sudo systemctl enable bc250-fan-pwm-restore.service || true;
  sudo systemctl reset-failed bc250-fan-pwm-restore.service 2>/dev/null || true;
  sudo systemctl restart bc250-fan-pwm-restore.service 2>/dev/null || sudo systemctl start bc250-fan-pwm-restore.service 2>/dev/null || true
fi
fi
