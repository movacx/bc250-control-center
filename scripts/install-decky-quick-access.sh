#!/usr/bin/env bash
# Install the optional, prebuilt BC250 Decky plugin.  This never installs
# Decky Loader itself and never runs as part of the main app installer.
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT_DIR="$(dirname "$(dirname "$SCRIPT_PATH")")"
if [[ ! -d "$ROOT_DIR/integrations/decky/bc250-quick-access" && \
      -d /usr/share/bc250-control-center/integrations/decky/bc250-quick-access ]]; then
  # Distribution packages install this optional bundle below the application
  # share directory rather than beside /usr/bin.
  ROOT_DIR="/usr/share/bc250-control-center"
fi
PLUGIN_SOURCE="$ROOT_DIR/integrations/decky/bc250-quick-access"
PLUGIN_NAME="bc250-quick-access"
PLUGIN_ROOT="${DECKY_PLUGIN_ROOT:-$HOME/homebrew/plugins}"
PLUGIN_DEST="$PLUGIN_ROOT/$PLUGIN_NAME"

# Every protected file is verified byte for byte with cmp after it is staged.
# cmp belongs to diffutils, which a minimal Arch, CachyOS or openSUSE system
# need not have; without it the checks below used to report a mismatch that
# did not exist and roll the installation back.
if ! command -v cmp >/dev/null 2>&1; then
  echo "Error: the cmp command (package diffutils) is required to verify the installed files." >&2
  echo "Install diffutils with your package manager, then run this installer again." >&2
  exit 2
fi
IMMUTABLE_OSTREE=0
if [[ -e /run/ostree-booted ]]; then
  IMMUTABLE_OSTREE=1
fi

usage() {
  cat <<'USAGE'
Install the optional BC250 Quick Access plugin for an existing Decky Loader.

Usage: ./scripts/install-decky-quick-access.sh

Environment:
  DECKY_PLUGIN_ROOT=/path/to/plugins   Override the detected Decky plugins directory.

The script installs the Decky-managed plugin and the finite root-owned BC250
helper. It does not install Decky Loader, enable boot services, or alter
GPU/CU state. Decky itself is a separate trusted root-plugin environment.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${EUID}" -eq 0 ]]; then
  echo "Error: run this installer as the Desktop Mode user, not as root." >&2
  exit 2
fi
if [[ ! -f "$PLUGIN_SOURCE/plugin.json" || ! -f "$PLUGIN_SOURCE/package.json" || \
      ! -f "$PLUGIN_SOURCE/main.py" || ! -f "$PLUGIN_SOURCE/dist/index.js" ]]; then
  echo "Error: the prebuilt BC250 Decky plugin is missing. Build the repository release artifacts first." >&2
  exit 3
fi
HELPER_SOURCE="$ROOT_DIR/privileged/helpers/bc250-quick-access-helper"
HELPER_DEST="/usr/libexec/bc250-control-center/bc250-quick-access-helper"
HELPER_PARENT="$(dirname "$HELPER_DEST")"
CPU_HELPER_SOURCE="$ROOT_DIR/privileged/helpers/bc250-cpu-smu-helper"
CPU_HELPER_DEST="/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"
CPU_VENDOR_SOURCE="$ROOT_DIR/privileged/lib/bc250_smu_oc_vendor.zip"
CPU_VENDOR_DEST="/usr/libexec/bc250-control-center/lib/bc250_smu_oc_vendor.zip"
CPU_VENDOR_PARENT="$(dirname "$CPU_VENDOR_DEST")"
GOVERNOR_HELPER_SOURCE="$ROOT_DIR/privileged/helpers/bc250-governor-config-helper"
GOVERNOR_HELPER_DEST="/usr/libexec/bc250-control-center/bc250-governor-config-helper"
GOVERNOR_EDITOR_SOURCE="$ROOT_DIR/privileged/lib/governor_toml.py"
GOVERNOR_EDITOR_DEST="/usr/libexec/bc250-control-center/lib/governor_toml.py"
CONTRACT_SOURCE="$ROOT_DIR/privileged/lib/bc250_contract.py"
CONTRACT_DEST="/usr/libexec/bc250-control-center/lib/bc250_contract.py"
if [[ ! -x "$HELPER_SOURCE" || ! -x "$CPU_HELPER_SOURCE" || ! -f "$CPU_VENDOR_SOURCE" || \
      ! -x "$GOVERNOR_HELPER_SOURCE" || ! -f "$GOVERNOR_EDITOR_SOURCE" ]]; then
  echo "Error: Quick Access CPU/helper payload is missing or not executable." >&2
  exit 6
fi

immutable_helper_guidance() {
  cat >&2 <<'GUIDANCE'

========================================================================
IMPORTANT: BAZZITE LOCAL-INSTALL LIMITATION
========================================================================
BC250 Quick Access needs protected helpers under /usr/libexec.

On immutable Bazzite, ./install-local.sh installs the app in your home
directory, but it cannot install those protected helpers into /usr. This is
expected and is NOT a Decky Loader failure.

Install or update the matching BC250 Control Center RPM with rpm-ostree,
reboot once, then run Quick Access installation again.

Packages and instructions:
https://github.com/movacx/bc250-control-center
========================================================================
GUIDANCE
}

# Bazzite and other rpm-ostree systems cannot safely receive executable root
# helpers from this user-run installer.  Check the packaged deployment *before*
# the GUI bootstrap downloads/installs Decky, so an incomplete BC250 package
# never leaves the user with Decky installed but no BC250 panel.
if [[ "${1:-}" == "--preflight-immutable-host" ]]; then
  if [[ "$IMMUTABLE_OSTREE" -eq 0 ]]; then
    echo "OK: mutable host; Quick Access helpers will be handled by the normal installer."
    exit 0
  fi
  if sudo test -L "$HELPER_PARENT" || \
     ! sudo test -d "$HELPER_PARENT" || \
     [[ "$(sudo stat -c '%u:%a' "$HELPER_PARENT")" != "0:755" ]] || \
     sudo test -L "$CPU_VENDOR_PARENT" || \
     ! sudo test -d "$CPU_VENDOR_PARENT" || \
     [[ "$(sudo stat -c '%u:%a' "$CPU_VENDOR_PARENT")" != "0:755" ]] || \
     ! sudo test -f "$HELPER_DEST" || ! sudo test -f "$CPU_HELPER_DEST" || \
     ! sudo test -f "$CPU_VENDOR_DEST" || ! sudo test -f "$GOVERNOR_HELPER_DEST" || \
     ! sudo test -f "$GOVERNOR_EDITOR_DEST" || ! sudo test -f "$CONTRACT_DEST" || \
     ! sudo cmp -s "$HELPER_SOURCE" "$HELPER_DEST" || \
     ! sudo cmp -s "$CPU_HELPER_SOURCE" "$CPU_HELPER_DEST" || \
     ! sudo cmp -s "$CPU_VENDOR_SOURCE" "$CPU_VENDOR_DEST" || \
     ! sudo cmp -s "$GOVERNOR_HELPER_SOURCE" "$GOVERNOR_HELPER_DEST" || \
     ! sudo cmp -s "$GOVERNOR_EDITOR_SOURCE" "$GOVERNOR_EDITOR_DEST" || \
     ! sudo cmp -s "$CONTRACT_SOURCE" "$CONTRACT_DEST"; then
    echo "ERROR: this immutable deployment is missing the exact protected helpers for this BC250 build." >&2
    echo "Install/update the matching BC250 Control Center RPM with rpm-ostree, reboot, then retry Quick Access." >&2
    immutable_helper_guidance
    exit 8
  fi
  echo "OK: immutable BC250 protected helpers are present and match this build."
  exit 0
fi

# The bootstrap calls --preflight-immutable-host before Decky is installed.
# Validate the plugin directory only for the actual BC250 plugin deployment;
# otherwise a clean system is trapped in a circular "install Decky first"
# failure before Bazzite's native installer gets a chance to run.
if [[ ! -d "$PLUGIN_ROOT" || -L "$PLUGIN_ROOT" ]]; then
  echo "Error: Decky Loader plugin directory was not found at $PLUGIN_ROOT." >&2
  echo "Install Decky Loader first, then rerun this script from Desktop Mode." >&2
  exit 4
fi
PLUGIN_ROOT="$(realpath -e -- "$PLUGIN_ROOT")"
PLUGIN_DEST="$PLUGIN_ROOT/$PLUGIN_NAME"
case "$PLUGIN_DEST" in
  "$PLUGIN_ROOT/$PLUGIN_NAME") ;;
  *) echo "Error: unsafe Decky plugin destination." >&2; exit 5 ;;
esac

cleanup_stale_plugin_transactions() {
  # Decky scans every child directory in its plugin root. A failed transaction
  # staged below that root can therefore be mistaken for another plugin and
  # collide with BC250's manifest. Only remove our exact direct-child names;
  # never traverse or clean arbitrary Decky plugins.
  local stale_path stale_name
  for stale_path in "$PLUGIN_ROOT"/.bc250-decky-stage.* "$PLUGIN_ROOT"/.bc250-decky-backup.*; do
    [[ -e "$stale_path" || -L "$stale_path" ]] || continue
    stale_name="${stale_path##*/}"
    case "$stale_name" in
      .bc250-decky-stage.*|.bc250-decky-backup.*) ;;
      *) continue ;;
    esac
    echo "Removing stale BC250 Decky transaction entry: $stale_name"
    sudo rm -rf -- "$stale_path"
  done
}

cleanup_stale_plugin_transactions

# A root-owned leaf under Decky's user-writable plugin parent is not a real
# protection boundary. Keep the plugin in Decky's managed location and limit
# elevation to BC250's fixed /usr/libexec helper. The stage must live outside
# Decky's scanned plugin root or Decky can try to load it mid-transaction.
plugin_stage="$(sudo mktemp -d /var/tmp/bc250-decky-stage.XXXXXX)"
sudo chmod 0700 "$plugin_stage"
# Decky needs the frontend/backend files plus the tiny immutable policy runtime.
# `package.json` is not development
# metadata here: Decky v3 selects its ESM frontend loader from its
# `"type": "module"` value. Omitting it makes Decky eval the modern bundle as
# a legacy IIFE and fail at its final `export default`. Do not deploy source,
# source map, package manager metadata or development dependencies alongside
# a root Decky plugin.  A tiny explicit payload is easier to inspect and
# prevents an accidental release archive from expanding the runtime surface.
for relative in plugin.json package.json main.py dist/index.js \
    bc250cc/__init__.py bc250cc/domain/__init__.py \
    bc250cc/domain/gpu/__init__.py bc250cc/domain/gpu/profiles.py; do
  source_path="$PLUGIN_SOURCE/$relative"
  if [[ ! -f "$source_path" || -L "$source_path" ]]; then
    echo "Error: Decky runtime source is incomplete or contains symbolic links: $relative" >&2
    sudo rm -rf -- "$plugin_stage"
    exit 7
  fi
  sudo install -Dm644 -- "$source_path" "$plugin_stage/$relative"
done
if sudo find "$plugin_stage" -type l -print -quit | grep -q . || \
   ! sudo test -f "$plugin_stage/plugin.json" || \
   ! sudo test -f "$plugin_stage/package.json" || \
   ! sudo test -f "$plugin_stage/main.py" || \
   ! sudo test -f "$plugin_stage/dist/index.js" || \
   ! sudo test -f "$plugin_stage/bc250cc/domain/gpu/profiles.py"; then
  echo "Error: staged Decky runtime payload is incomplete or contains symbolic links." >&2
  sudo rm -rf -- "$plugin_stage"
  exit 7
fi
if ! sudo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$plugin_stage" python3 -c \
  'from bc250cc.domain.gpu.profiles import profiles_payload; assert profiles_payload(1000, 2000, governor="oberon")'; then
  echo "Error: bundled Quick Access BC250 policy runtime cannot be imported." >&2
  sudo rm -rf -- "$plugin_stage"
  exit 7
fi
# Decky owns this root-managed plugin tree, but Desktop Mode must be able to
# read the fixed runtime files for the non-mutating deployment inventory.
# The directory stays root-owned; mode 0755 permits inspection, never writes.
sudo chmod 0755 "$plugin_stage"

backup="$(sudo mktemp -d /var/tmp/bc250-decky-backup.XXXXXX)"
sudo chmod 0700 "$backup"
had_plugin=0
had_helper=0
had_cpu_helper=0
had_cpu_vendor=0
plugin_replaced=0
helper_replaced=0
cpu_helper_replaced=0
cpu_vendor_replaced=0

restore() {
  local status=$?
  if [[ "$status" -ne 0 ]]; then
    echo "Decky installation failed; restoring the previous plugin state." >&2
    if [[ "$plugin_replaced" -eq 1 ]]; then
      sudo rm -rf -- "$PLUGIN_DEST"
      if [[ "$had_plugin" -eq 1 ]]; then
        sudo mv -- "$backup/previous-plugin" "$PLUGIN_DEST" || \
          echo "Warning: could not restore the previous Decky plugin payload." >&2
      fi
    fi
    # Never remove a pre-existing helper merely because a preflight check
    # failed.  A helper is rolled back only after this invocation started to
    # replace it, keeping the installer transaction non-destructive.
    if [[ "$helper_replaced" -eq 1 ]]; then
      sudo rm -f -- "$HELPER_DEST"
      if [[ "$had_helper" -eq 1 ]]; then
        sudo cp -a -- "$backup/previous-helper" "$HELPER_DEST"
      fi
    fi
    if [[ "$cpu_helper_replaced" -eq 1 ]]; then
      sudo rm -f -- "$CPU_HELPER_DEST"
      if [[ "$had_cpu_helper" -eq 1 ]]; then
        sudo cp -a -- "$backup/previous-cpu-helper" "$CPU_HELPER_DEST"
      fi
    fi
    if [[ "$cpu_vendor_replaced" -eq 1 ]]; then
      sudo rm -f -- "$CPU_VENDOR_DEST"
      if [[ "$had_cpu_vendor" -eq 1 ]]; then
        sudo cp -a -- "$backup/previous-cpu-vendor" "$CPU_VENDOR_DEST"
      fi
    fi
  fi
  if [[ -n "$plugin_stage" ]]; then
    sudo rm -rf -- "$plugin_stage"
  fi
  sudo rm -rf -- "$backup"
  exit "$status"
}
trap restore EXIT

if sudo test -L "$HELPER_PARENT" || \
   ! sudo test -d "$HELPER_PARENT" || \
   [[ "$(sudo stat -c '%u:%a' "$HELPER_PARENT")" != "0:755" ]]; then
  if [[ "$IMMUTABLE_OSTREE" -eq 1 ]]; then
    echo "Error: the packaged BC250 protected-helper directory is missing or untrusted." >&2
    echo "Install or update the BC250 Control Center RPM deployment, reboot, then retry Quick Access." >&2
    immutable_helper_guidance
  else
    echo "Error: the BC250 protected-helper directory is missing or untrusted. Run scripts/install-local.sh first." >&2
  fi
  exit 8
fi
if sudo test -L "$CPU_VENDOR_PARENT" || \
   ! sudo test -d "$CPU_VENDOR_PARENT" || \
   [[ "$(sudo stat -c '%u:%a' "$CPU_VENDOR_PARENT")" != "0:755" ]]; then
  if [[ "$IMMUTABLE_OSTREE" -eq 1 ]]; then
    echo "Error: the packaged BC250 protected vendor directory is missing or untrusted." >&2
    echo "Install or update the BC250 Control Center RPM deployment, reboot, then retry Quick Access." >&2
    immutable_helper_guidance
  else
    echo "Error: the BC250 protected vendor directory is missing or untrusted. Run scripts/install-local.sh first." >&2
  fi
  exit 8
fi
if sudo test -L "$HELPER_DEST"; then
  echo "Error: refusing to replace a symbolic-link Quick Access helper." >&2
  exit 8
fi
if [[ -e "$HELPER_DEST" || -L "$HELPER_DEST" ]]; then
  sudo cp -a -- "$HELPER_DEST" "$backup/previous-helper"
  had_helper=1
fi
if sudo test -L "$CPU_HELPER_DEST" || sudo test -L "$CPU_VENDOR_DEST"; then
  echo "Error: refusing to replace a symbolic-link CPU payload." >&2
  exit 8
fi
if [[ -e "$CPU_HELPER_DEST" || -L "$CPU_HELPER_DEST" ]]; then
  sudo cp -a -- "$CPU_HELPER_DEST" "$backup/previous-cpu-helper"
  had_cpu_helper=1
fi
if [[ -e "$CPU_VENDOR_DEST" || -L "$CPU_VENDOR_DEST" ]]; then
  sudo cp -a -- "$CPU_VENDOR_DEST" "$backup/previous-cpu-vendor"
  had_cpu_vendor=1
fi

if [[ "$IMMUTABLE_OSTREE" -eq 1 ]]; then
  # /usr belongs to the rpm-ostree deployment. Never bypass its transaction
  # from a user-run Decky installer; require the packaged helpers to match the
  # application build and install only the plugin below Decky's /home tree.
  if ! sudo test -f "$HELPER_DEST" || ! sudo test -f "$CPU_HELPER_DEST" || \
     ! sudo test -f "$CPU_VENDOR_DEST" || ! sudo test -f "$GOVERNOR_HELPER_DEST" || \
     ! sudo test -f "$GOVERNOR_EDITOR_DEST" || ! sudo test -f "$CONTRACT_DEST" || \
     ! sudo cmp -s "$HELPER_SOURCE" "$HELPER_DEST" || \
     ! sudo cmp -s "$CPU_HELPER_SOURCE" "$CPU_HELPER_DEST" || \
     ! sudo cmp -s "$CPU_VENDOR_SOURCE" "$CPU_VENDOR_DEST" || \
     ! sudo cmp -s "$GOVERNOR_HELPER_SOURCE" "$GOVERNOR_HELPER_DEST" || \
     ! sudo cmp -s "$GOVERNOR_EDITOR_SOURCE" "$GOVERNOR_EDITOR_DEST" || \
     ! sudo cmp -s "$CONTRACT_SOURCE" "$CONTRACT_DEST"; then
    echo "Error: the immutable Bazzite deployment does not contain the protected helpers from this BC250 build." >&2
    echo "Install or update the BC250 Control Center RPM deployment, reboot, then retry Quick Access." >&2
    immutable_helper_guidance
    exit 8
  fi
  echo "Verified packaged BC250 helpers in the immutable rpm-ostree deployment."
else
  helper_replaced=1
  sudo install -Dm755 "$HELPER_SOURCE" "$HELPER_DEST"
  cpu_helper_replaced=1
  sudo install -Dm755 "$CPU_HELPER_SOURCE" "$CPU_HELPER_DEST"
  cpu_vendor_replaced=1
  sudo install -Dm644 "$CPU_VENDOR_SOURCE" "$CPU_VENDOR_DEST"
fi
if ! sudo cmp -s "$HELPER_SOURCE" "$HELPER_DEST"; then
  echo "Error: installed Quick Access helper does not match this build." >&2
  exit 8
fi
if ! sudo test ! -L "$HELPER_DEST" || \
   [[ "$(sudo stat -c '%u:%a' "$HELPER_DEST")" != "0:755" ]]; then
  echo "Error: installed Quick Access helper is not root-owned mode 0755." >&2
  exit 8
fi

# Protocol 9 delegates frequency+VID calibration, detector-bound manual
# CPU scaling and fail-closed Cyan/Oberon GPU governor selection.
# scale tests to the audited CPU helper. Mutable hosts deploy that helper in
# this transaction; immutable Bazzite hosts reached this point only after the
# equivalent packaged payload was verified byte-for-byte above.
if ! sudo cmp -s "$CPU_HELPER_SOURCE" "$CPU_HELPER_DEST" || \
   ! sudo cmp -s "$CPU_VENDOR_SOURCE" "$CPU_VENDOR_DEST" || \
   ! sudo cmp -s "$GOVERNOR_HELPER_SOURCE" "$GOVERNOR_HELPER_DEST" || \
   ! sudo cmp -s "$GOVERNOR_EDITOR_SOURCE" "$GOVERNOR_EDITOR_DEST"; then
  echo "Error: installed protected CPU payload does not match this build." >&2
  echo "Run scripts/install-local.sh first so Quick Access and its GPU editor are deployed together." >&2
  exit 8
fi
if ! sudo test ! -L "$CPU_HELPER_DEST" || \
   ! sudo test ! -L "$CPU_VENDOR_DEST" || \
   ! sudo test ! -L "$GOVERNOR_HELPER_DEST" || \
   ! sudo test ! -L "$GOVERNOR_EDITOR_DEST" || \
   [[ "$(sudo stat -c '%u:%a' "$CPU_HELPER_DEST")" != "0:755" ]] || \
   [[ "$(sudo stat -c '%u:%a' "$CPU_VENDOR_DEST")" != "0:644" ]] || \
   [[ "$(sudo stat -c '%u:%a' "$GOVERNOR_HELPER_DEST")" != "0:755" ]] || \
   [[ "$(sudo stat -c '%u:%a' "$GOVERNOR_EDITOR_DEST")" != "0:644" ]]; then
  echo "Error: installed CPU helper/vendor ownership or permissions are unsafe." >&2
  exit 8
fi

if [[ -e "$PLUGIN_DEST" || -L "$PLUGIN_DEST" ]]; then
  sudo mv -- "$PLUGIN_DEST" "$backup/previous-plugin"
  had_plugin=1
fi
plugin_replaced=1
sudo mv -- "$plugin_stage" "$PLUGIN_DEST"
plugin_stage=""
if [[ "$(sudo stat -c '%u:%a' "$PLUGIN_DEST")" != "0:755" ]]; then
  echo "Error: installed Decky plugin directory is not root-owned mode 0755." >&2
  exit 8
fi
echo "Installed Decky-managed BC250 Quick Access payload at $PLUGIN_DEST"
echo "Installed protected BC250 helper at $HELPER_DEST"
echo "Installed protected BC250 CPU detector at $CPU_HELPER_DEST"

# Decky keeps the Python plugin object and its frontend bundle path in memory.
# Re-entering Game Mode reconnects Steam's CEF UI, but it does not necessarily
# restart plugin_loader.  Without this reload, a repaired plugin can continue
# to serve a now-removed transaction directory such as
# .bc250-decky-stage.XXXXXX.  Reload only Decky's own service after a fully
# committed transaction; it neither touches BC250 hardware state nor starts a
# service that was deliberately stopped by the user.
if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1 && \
   sudo systemctl is-active --quiet plugin_loader.service; then
  echo "Reloading Decky Plugin Loader so it forgets any previous BC250 bundle path..."
  if sudo systemctl restart plugin_loader.service && \
     sudo systemctl is-active --quiet plugin_loader.service; then
    echo "Decky Plugin Loader reloaded. Return to Game Mode and open Quick Access."
  else
    echo "Warning: BC250 Quick Access was installed, but Decky Plugin Loader could not be reloaded." >&2
    echo "Restart Steam/Game Mode or reboot before opening the BC250 panel." >&2
  fi
elif [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
  echo "Decky Plugin Loader is not active. The BC250 panel is installed and will load when Decky starts."
else
  echo "BC250 Quick Access is installed. This init system has no systemctl integration for Decky reload."
  echo "Restart Decky, Steam/Game Mode, or the host before opening the BC250 panel."
fi
