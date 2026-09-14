#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_ROOT="${1:-$(dirname "$(dirname "$(dirname "$SCRIPT_PATH")")")}" 
MODE="${2:-full}"

if [[ "$MODE" != "full" && "$MODE" != "--structure-only" ]]; then
  echo "Usage: validate-install-source.sh [PROJECT_ROOT] [--structure-only]" >&2
  exit 2
fi

required=(
  VERSION
  README.md
  LICENSE
  frontends/desktop/main.py
  src/bc250cc/__init__.py
  frontends/desktop/features/gpu/presenter.py
  frontends/desktop/console/__init__.py
  frontends/desktop/console/pty_session.py
  frontends/desktop/console/terminal_screen.py
  privileged/helpers/README.md
  privileged/helpers/bc250-system-setup-helper
  privileged/lib/system_setup_common.py
  privileged/lib/system_setup_memory.py
  privileged/lib/system_setup_acpi.py
  privileged/lib/system_setup_telemetry.py
  privileged/lib/acpi_payload.py
  privileged/lib/governor_toml.py
  privileged/lib/bc250_smu_oc_vendor.zip
  packaging/common/io.github.movacx.bc250-control-center.desktop
  packaging/common/io.github.movacx.bc250-control-center.metainfo.xml
  privileged/policies/io.github.movacx.bc250-control-center.policy
  packaging/common/bc250-control-centerd.service
  privileged/helpers/bc250-core-unlock-helper
  privileged/helpers/bc250-cpu-smu-helper
  privileged/helpers/bc250-gddr6-temp-helper
  privileged/helpers/bc250-gddr6-temp-reader
  privileged/helpers/bc250-cyan-overlay-preflight
  privileged/helpers/bc250-fan-pwm-helper
  privileged/helpers/bc250-governor-config-helper
  privileged/helpers/bc250-openrc-service-helper
  privileged/helpers/bc250-quick-access-helper
  privileged/helpers/bc250-service-helper
  privileged/helpers/bc250-maintenance-helper
  privileged/helpers/bc250-steamos-game-helper
  privileged/helpers/bc250-cu-helper
  scripts/system/bc250-gpu-voltage-lab.sh
  scripts/system/prepare-steamos-cu-backend.py
  scripts/system/prepare-steamos-telemetry-oc-overlay.py
  scripts/system/repair-steamos-umr-database.py
  scripts/system/steamos-root.sh
  scripts/entrypoints/bc250-control-center
  scripts/entrypoints/bc250-control-center-cli
  scripts/entrypoints/bc250-control-centerd
  scripts/install-local.sh
  scripts/install-decky-quick-access.sh
  scripts/uninstall-local.sh
  scripts/maintenance/update-local.sh
  scripts/lib/user-paths.sh
  packaging/common/bc250-package-maintenance
  packaging/common/bc250-control-center.install
  packaging/scripts/build-local-pkg.sh
  packaging/scripts/build-deb.sh
  packaging/scripts/build-rpm.sh
)
for size in 32 48 64 128 256 512 1024; do
  required+=("assets/icons/bc250-control-center-${size}.png")
done

expected_root_scripts=(
  install-decky-quick-access.sh
  install-local.sh
  uninstall-local.sh
)
mapfile -t actual_root_scripts < <(
  find "$PROJECT_ROOT/scripts" -maxdepth 1 -type f -printf '%f\n' | sort
)
if [[ "${actual_root_scripts[*]}" != "${expected_root_scripts[*]}" ]]; then
  echo "ERROR: scripts/ root must contain only the three public installers." >&2
  printf 'Expected: %s\n' "${expected_root_scripts[*]}" >&2
  printf 'Found:    %s\n' "${actual_root_scripts[*]}" >&2
  exit 10
fi

for relative in "${required[@]}"; do
  if [[ ! -f "$PROJECT_ROOT/$relative" ]]; then
    echo "ERROR: required installation source is missing: $relative" >&2
    exit 10
  fi
done

for relative in \
  privileged/helpers/bc250-system-setup-helper \
  privileged/lib/system_setup_common.py \
  privileged/lib/system_setup_memory.py \
  privileged/lib/system_setup_acpi.py \
  privileged/lib/system_setup_telemetry.py \
  privileged/lib/acpi_payload.py \
  privileged/helpers/bc250-core-unlock-helper \
  privileged/helpers/bc250-cpu-smu-helper \
  privileged/helpers/bc250-gddr6-temp-helper \
  privileged/helpers/bc250-gddr6-temp-reader \
  privileged/helpers/bc250-cyan-overlay-preflight \
  privileged/helpers/bc250-fan-pwm-helper \
  privileged/helpers/bc250-governor-config-helper \
  privileged/helpers/bc250-openrc-service-helper \
  privileged/helpers/bc250-quick-access-helper \
  privileged/helpers/bc250-service-helper \
  privileged/helpers/bc250-maintenance-helper \
  privileged/helpers/bc250-steamos-game-helper \
  privileged/helpers/bc250-cu-helper \
  packaging/common/bc250-package-maintenance \
  privileged/lib/bc250_smu_oc_vendor.zip; do
  if [[ -L "$PROJECT_ROOT/$relative" ]]; then
    echo "ERROR: privileged installation source must not be a symbolic link: $relative" >&2
    exit 11
  fi
done

for relative in \
  scripts/install-local.sh scripts/uninstall-local.sh scripts/maintenance/update-local.sh \
  scripts/install-decky-quick-access.sh \
  scripts/qa/validate-install-source.sh scripts/qa/smoke-install-layout.sh \
  scripts/system/steamos-root.sh \
  scripts/lib/user-paths.sh \
  packaging/common/bc250-package-maintenance \
  packaging/scripts/build-local-pkg.sh \
  packaging/scripts/build-rpm.sh \
  packaging/scripts/build-deb.sh \
  packaging/scripts/build-tarball.sh \
  packaging/scripts/stage-package-root.sh \
  packaging/common/os-scripts/common/prepare-fan-pwm-dkms.sh \
  packaging/common/os-scripts/alpine/prepare-dependencies.sh \
  packaging/common/os-scripts/alpine/prepare-fan-pwm.sh \
  packaging/common/os-scripts/gentoo/prepare-dependencies.sh \
  packaging/common/os-scripts/gentoo/prepare-fan-pwm.sh; do
  bash -n "$PROJECT_ROOT/$relative"
done

if [[ "$MODE" == "--structure-only" ]]; then
  echo "OK: BC250 installation source structure and shell syntax are valid."
  exit 0
fi

command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 is required for the complete installation-source preflight." >&2
  exit 12
}

python3 - "$PROJECT_ROOT" <<'PY'
import ast
import pathlib
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

root = pathlib.Path(sys.argv[1]).resolve()
for tree in (root / "src", root / "frontends", root / "privileged"):
    for source in sorted(tree.rglob("*.py")):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
for source in sorted((root / "privileged" / "helpers").iterdir()):
    if source.is_file() and not source.is_symlink() and source.name != "README.md":
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))

archive = root / "privileged" / "lib" / "bc250_smu_oc_vendor.zip"
required_vendor = {"UPSTREAM_COMMIT", "LICENSE", "bc250_apply.py", "bc250_detect.py"}
with zipfile.ZipFile(archive) as bundle:
    corrupt = bundle.testzip()
    if corrupt:
        raise SystemExit(f"ERROR: corrupt CPU/SMU vendor member: {corrupt}")
    names = set(bundle.namelist())
    unsafe = [name for name in names if name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts]
    if unsafe:
        raise SystemExit(f"ERROR: unsafe CPU/SMU vendor member: {unsafe[0]}")
    missing = sorted(required_vendor - names)
    if missing:
        raise SystemExit(f"ERROR: incomplete CPU/SMU vendor archive: {', '.join(missing)}")

license_text = (root / "LICENSE").read_text(encoding="utf-8")
if not license_text.startswith("MIT License\n"):
    raise SystemExit("ERROR: unsupported or unrecognized project LICENSE text")
metadata = ET.parse(
    root / "packaging/common/io.github.movacx.bc250-control-center.metainfo.xml"
).getroot()
if metadata.findtext("project_license") != "MIT":
    raise SystemExit("ERROR: AppStream project license does not match LICENSE (expected MIT)")
version = (root / "VERSION").read_text(encoding="utf-8").strip()
if not re.fullmatch(r"[0-9]+(?:[.][0-9A-Za-z]+)*(?:-[0-9A-Za-z.]+)?", version):
    raise SystemExit("ERROR: VERSION is malformed")
latest_release = metadata.find("./releases/release")
if latest_release is None or latest_release.get("version") != version:
    raise SystemExit("ERROR: VERSION does not match the latest AppStream release")
packaging_markers = {
    "packaging/scripts/build-local-pkg.sh": "license = MIT",
    "packaging/scripts/build-rpm.sh": "License:        MIT",
    "packaging/scripts/build-deb.sh": "Package: bc250-control-center",
}
for relative, marker in packaging_markers.items():
    source = (root / relative).read_text(encoding="utf-8")
    if marker not in source:
        raise SystemExit(f"ERROR: package license metadata does not match MIT: {relative}")
rpm_builder = (root / "packaging/scripts/build-rpm.sh").read_text(encoding="utf-8")
for marker in (
    "python3-pyqt6",
    "_buildhost bc250-control-center.invalid",
    "use_source_date_epoch_as_buildtime 1",
):
    if marker not in rpm_builder:
        raise SystemExit(f"ERROR: RPM release contract is incomplete: {marker}")
PY

decky_source="$PROJECT_ROOT/integrations/decky/bc250-quick-access"
for relative in plugin.json main.py package.json rollup.config.js tsconfig.json README.md src/index.tsx dist/index.js \
    bc250cc/__init__.py bc250cc/domain/__init__.py \
    bc250cc/domain/gpu/__init__.py bc250cc/domain/gpu/profiles.py; do
  if [[ ! -f "$decky_source/$relative" ]]; then
    echo "ERROR: required Decky Quick Access source is missing: integrations/decky/bc250-quick-access/$relative" >&2
    exit 13
  fi
done
python3 - "$decky_source" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
metadata = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
if (
    metadata.get("name") != "BC250 Quick Access"
    or "root" not in metadata.get("flags", [])
    or "_root" not in metadata.get("flags", [])
):
    raise SystemExit("ERROR: Decky Quick Access plugin metadata is incomplete")
package = json.loads((root / "package.json").read_text(encoding="utf-8"))
if package.get("type") != "module" or not isinstance(package.get("version"), str):
    raise SystemExit("ERROR: Decky Quick Access package metadata must select the ESM loader")
bundle = (root / "dist/index.js").read_text(encoding="utf-8")
if not bundle.strip():
    raise SystemExit("ERROR: Decky Quick Access bundle is empty")
for operation in (
    "apply_gpu_profile",
    "apply_gpu_safe_point",
    "apply_cu_table",
    "save_cu_table",
    "install_cu_service",
    "remove_cu_service",
    "apply_fan_channel",
    "apply_cpu_tuning",
    "apply_cpu_scale",
    "install_cpu_service",
    "remove_cpu_service",
):
    if operation not in bundle:
        raise SystemExit(f"ERROR: Decky Quick Access bundle is stale or incomplete: {operation}")
PY

echo "OK: BC250 installation source passed structure, syntax and vendor checks."
