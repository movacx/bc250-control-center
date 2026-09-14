#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 DESTDIR" >&2
  exit 64
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DESTDIR="$(realpath -m -- "$1")"

if [[ "$DESTDIR" == / || -z "$DESTDIR" ]]; then
  echo "Refusing unsafe package staging root: $DESTDIR" >&2
  exit 64
fi

bash "$ROOT_DIR/scripts/qa/validate-install-source.sh" "$ROOT_DIR"
install -d -m755 \
  "$DESTDIR/usr/share/bc250-control-center" \
  "$DESTDIR/usr/share/bc250-control-center/scripts" \
  "$DESTDIR/usr/share/bc250-control-center/integrations/decky" \
  "$DESTDIR/usr/share/bc250-control-center/packaging/common" \
  "$DESTDIR/usr/share/doc/bc250-control-center" \
  "$DESTDIR/usr/bin" \
  "$DESTDIR/usr/lib/systemd/user" \
  "$DESTDIR/usr/libexec/bc250-control-center" \
  "$DESTDIR/usr/libexec/bc250-control-center/lib" \
  "$DESTDIR/usr/share/applications" \
  "$DESTDIR/usr/share/metainfo" \
  "$DESTDIR/usr/share/polkit-1/actions"

cp -a -- "$ROOT_DIR/src" "$DESTDIR/usr/share/bc250-control-center/src"
cp -a -- "$ROOT_DIR/frontends" "$DESTDIR/usr/share/bc250-control-center/frontends"
cp -a -- "$ROOT_DIR/privileged" "$DESTDIR/usr/share/bc250-control-center/privileged"
cp -a -- "$ROOT_DIR/assets" "$DESTDIR/usr/share/bc250-control-center/assets"
cp -a -- "$ROOT_DIR/scripts/system" "$DESTDIR/usr/share/bc250-control-center/scripts/system"
cp -a -- "$ROOT_DIR/packaging/common/os-scripts" \
  "$DESTDIR/usr/share/bc250-control-center/packaging/common/os-scripts"
cp -a -- "$ROOT_DIR/integrations/decky/bc250-quick-access" \
  "$DESTDIR/usr/share/bc250-control-center/integrations/decky/bc250-quick-access"
# The source tree may contain private working-copy permissions (for example
# 0600 locale JSON files).  Everything under /usr/share is runtime data read
# by the desktop user, so normalize the staged copy to public read/traverse
# access while preserving executability of scripts that were already marked
# executable.
chmod -R a+rX "$DESTDIR/usr/share/bc250-control-center"
rm -rf -- "$DESTDIR/usr/share/bc250-control-center/integrations/decky/bc250-quick-access/node_modules"
find "$DESTDIR/usr/share/bc250-control-center/integrations/decky/bc250-quick-access" \
  -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$DESTDIR/usr/share/bc250-control-center/integrations/decky/bc250-quick-access" \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$DESTDIR/usr/share/bc250-control-center/src" "$DESTDIR/usr/share/bc250-control-center/frontends" \
  "$DESTDIR/usr/share/bc250-control-center/privileged" \
  "$DESTDIR/usr/share/bc250-control-center/scripts/system" \
  "$DESTDIR/usr/share/bc250-control-center/packaging/common/os-scripts" \
  -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$DESTDIR/usr/share/bc250-control-center/src" "$DESTDIR/usr/share/bc250-control-center/frontends" \
  "$DESTDIR/usr/share/bc250-control-center/privileged" \
  "$DESTDIR/usr/share/bc250-control-center/scripts/system" \
  "$DESTDIR/usr/share/bc250-control-center/packaging/common/os-scripts" \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

install -m644 "$ROOT_DIR/README.md" "$DESTDIR/usr/share/doc/bc250-control-center/README.md"
install -m644 "$ROOT_DIR/LICENSE" "$DESTDIR/usr/share/doc/bc250-control-center/LICENSE"
install -m644 "$ROOT_DIR/docs/THIRD_PARTY_NOTICES.md" "$DESTDIR/usr/share/doc/bc250-control-center/THIRD_PARTY_NOTICES.md"
install -D -m644 "$ROOT_DIR/packaging/common/50-bc250-system-setup-uninstall.hook" \
  "$DESTDIR/usr/share/libalpm/hooks/50-bc250-system-setup-uninstall.hook"
install -m644 "$ROOT_DIR/VERSION" "$DESTDIR/usr/share/bc250-control-center/VERSION"
for launcher in bc250-control-center bc250-control-center-cli bc250-control-centerd; do
  install -m755 "$ROOT_DIR/scripts/entrypoints/$launcher" "$DESTDIR/usr/bin/$launcher"
done
install -m755 "$ROOT_DIR/scripts/install-decky-quick-access.sh" \
  "$DESTDIR/usr/bin/bc250-control-center-decky-install"
install -m755 \
  "$ROOT_DIR/scripts/system/bc250-gpu-voltage-lab.sh" \
  "$DESTDIR/usr/libexec/bc250-control-center/bc250-gpu-voltage-lab.sh"
install -m755 \
  "$ROOT_DIR/scripts/system/prepare-steamos-telemetry-oc-overlay.py" \
  "$DESTDIR/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay"
install -m755 \
  "$ROOT_DIR/packaging/common/bc250-package-maintenance" \
  "$DESTDIR/usr/libexec/bc250-control-center/bc250-package-maintenance"
install -m644 \
  "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.desktop" \
  "$DESTDIR/usr/share/applications/io.github.movacx.bc250-control-center.desktop"
install -m644 \
  "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.metainfo.xml" \
  "$DESTDIR/usr/share/metainfo/io.github.movacx.bc250-control-center.metainfo.xml"
install -m644 \
  "$ROOT_DIR/packaging/common/bc250-control-centerd.service" \
  "$DESTDIR/usr/lib/systemd/user/bc250-control-centerd.service"
install -m644 \
  "$ROOT_DIR/privileged/policies/io.github.movacx.bc250-control-center.policy" \
  "$DESTDIR/usr/share/polkit-1/actions/io.github.movacx.bc250-control-center.policy"

for helper in \
  bc250-system-setup-helper \
  bc250-cu-helper \
  bc250-fan-pwm-helper \
  bc250-cyan-overlay-preflight \
  bc250-steamos-game-helper \
  bc250-governor-config-helper \
  bc250-quick-access-helper \
  bc250-core-unlock-helper \
  bc250-cpu-smu-helper \
  bc250-gddr6-temp-helper \
  bc250-gddr6-temp-reader \
  bc250-openrc-service-helper \
  bc250-service-helper \
  bc250-maintenance-helper; do
  install -m755 \
    "$ROOT_DIR/privileged/helpers/$helper" \
    "$DESTDIR/usr/libexec/bc250-control-center/$helper"
done
# The preflight helper is useless unless systemd runs it before Cyan starts.
# install-local.sh has always written this drop-in; packaged installs shipped
# the helper and nothing that calls it, so on every distribution installed from
# a package the stale-bind-mount failure it exists to prevent still happened.
# A vendor drop-in under /usr/lib leaves /etc free for the administrator, and
# systemd ignores it harmlessly when Cyan is not installed.
install -Dm644 \
  "$ROOT_DIR/packaging/common/91-bc250-control-center-overlay-preflight.conf" \
  "$DESTDIR/usr/lib/systemd/system/cyan-skillfish-governor-smu.service.d/91-bc250-control-center-overlay-preflight.conf"

for setup_module in system_setup_common.py system_setup_memory.py system_setup_acpi.py system_setup_telemetry.py acpi_payload.py bc250_contract.py; do
  install -m644 "$ROOT_DIR/privileged/lib/$setup_module" "$DESTDIR/usr/libexec/bc250-control-center/lib/$setup_module"
done
install -m644 \
  "$ROOT_DIR/privileged/lib/bc250_smu_oc_vendor.zip" \
  "$DESTDIR/usr/libexec/bc250-control-center/lib/bc250_smu_oc_vendor.zip"
install -m644 \
  "$ROOT_DIR/privileged/lib/governor_toml.py" \
  "$DESTDIR/usr/libexec/bc250-control-center/lib/governor_toml.py"
# These directories contain root-executed helpers and imported Python modules.
# Set their modes explicitly: when they are created only as intermediate
# install(1) components, a desktop umask such as 0002 can otherwise leave them
# group-writable and the helpers correctly refuse to trust their own payload.
chmod 0755 \
  "$DESTDIR/usr/libexec/bc250-control-center" \
  "$DESTDIR/usr/libexec/bc250-control-center/lib"

for source in "$ROOT_DIR"/assets/icons/bc250-control-center-*.png; do
  size="${source##*-}"
  size="${size%.png}"
  install -D -m644 "$source" \
    "$DESTDIR/usr/share/icons/hicolor/${size}x${size}/apps/bc250-control-center.png"
done
install -D -m644 "$ROOT_DIR/assets/icons/bc250-control-center.png" \
  "$DESTDIR/usr/share/pixmaps/bc250-control-center.png"

python3 -m compileall -q \
  "$DESTDIR/usr/share/bc250-control-center/src" \
  "$DESTDIR/usr/share/bc250-control-center/frontends" \
  "$DESTDIR/usr/share/bc250-control-center/privileged"
find "$DESTDIR/usr/share/bc250-control-center/src" "$DESTDIR/usr/share/bc250-control-center/frontends" \
  "$DESTDIR/usr/share/bc250-control-center/privileged" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$DESTDIR/usr/share/bc250-control-center/src" "$DESTDIR/usr/share/bc250-control-center/frontends" \
  "$DESTDIR/usr/share/bc250-control-center/privileged" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

echo "Package root staged at $DESTDIR"
