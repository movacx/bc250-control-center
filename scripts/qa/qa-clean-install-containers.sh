#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"

declare -A IMAGES=(
  [arch]="docker.io/library/archlinux:base"
  [debian]="docker.io/library/debian:stable-slim"
  [ubuntu]="docker.io/library/ubuntu:24.04"
  [fedora]="registry.fedoraproject.org/fedora:latest"
)

usage() {
  cat <<'EOF'
Usage:
  qa-clean-install-containers.sh --list
  qa-clean-install-containers.sh --image FAMILY --allow-network [--pull]

Clean-install QA is rootless and container-only. It never accesses hardware or
host system paths. Network/package operations require --allow-network, and a
missing image is pulled only when --pull is also explicit.
EOF
}

family=""
allow_network=0
allow_pull=0
list_only=0
minimum_free_kib=$((6 * 1024 * 1024))
while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) list_only=1 ;;
    --image) shift; family="${1:-}" ;;
    --allow-network) allow_network=1 ;;
    --pull) allow_pull=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

if [[ "$list_only" -eq 1 ]]; then
  for key in arch debian ubuntu fedora; do
    printf '%s\t%s\n' "$key" "${IMAGES[$key]}"
  done
  exit 0
fi
if [[ -z "$family" || -z "${IMAGES[$family]:-}" ]]; then
  echo "Select one declared family with --image." >&2
  exit 64
fi
if [[ "$allow_network" -ne 1 ]]; then
  echo "Clean dependency installation requires explicit --allow-network." >&2
  exit 77
fi
command -v podman >/dev/null || { echo "podman is required" >&2; exit 69; }

# Package managers keep both downloaded archives and an overlay transaction
# while PyQt/Qt is installed.  Starting this check with a nearly-full home
# filesystem used to fail halfway through pacman or dnf and left the result
# looking like a BC250 installation failure.  The container remains
# disposable, but its rootless storage lives on the host, so fail before any
# download when there is less than 6 GiB available.
available_kib="$(df -Pk "$ROOT_DIR" | awk 'NR == 2 { print $4 }')"
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( available_kib < minimum_free_kib )); then
  available_gib="$(awk -v kib="${available_kib:-0}" 'BEGIN { printf "%.1f", kib / 1024 / 1024 }')"
  required_gib="$(awk -v kib="$minimum_free_kib" 'BEGIN { printf "%.1f", kib / 1024 / 1024 }')"
  echo "Clean-install QA needs at least ${required_gib} GiB free on the host filesystem; only ${available_gib} GiB is available." >&2
  echo "Free space first, then rerun one declared image at a time." >&2
  exit 75
fi

if command -v pasta >/dev/null 2>&1; then
  network_backend="pasta"
elif command -v slirp4netns >/dev/null 2>&1; then
  network_backend="slirp4netns"
else
  echo "Rootless container networking requires pasta or slirp4netns." >&2
  exit 69
fi

image="${IMAGES[$family]}"
if ! podman image exists "$image"; then
  if [[ "$allow_pull" -ne 1 ]]; then
    echo "Image is not local: $image (add --pull to download it explicitly)." >&2
    exit 78
  fi
  podman pull "$image"
fi

case "$family" in
  arch)
    bootstrap='pacman -Syu --needed --noconfirm --noprogressbar bash python python-pyqt6 qt6-svg python-psutil git'
    ;;
  debian|ubuntu)
    bootstrap='apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq bash python3 python3-pyqt6 libqt6svg6 python3-psutil git'
    ;;
  fedora)
    bootstrap='dnf -q install -y bash python3 python3-pyqt6 qt6-qtsvg python3-psutil git'
    ;;
esac

read -r -d '' validation <<'EOF' || true
set -euo pipefail
mkdir -p /tmp/bc250-home
bash /src/scripts/qa/validate-install-source.sh /src
QT_QPA_PLATFORM=offscreen PYTHONPATH=/src python3 -c 'from PyQt6.QtWidgets import QApplication; import psutil; import frontends.cli'
HOME=/tmp/bc250-home PREFIX=/opt/bc250 BC250_SKIP_PRIVILEGED_HELPER=1 bash /src/scripts/install-local.sh
test "$(cat /opt/bc250/share/bc250-control-center/VERSION)" = "$(cat /src/VERSION)"
/opt/bc250/bin/bc250-control-center-cli --version | grep -F "$(cat /src/VERSION)"
HOME=/tmp/bc250-home /opt/bc250/bin/bc250-control-center-cli --json system > /tmp/system.json
python3 -c 'import json; data=json.load(open("/tmp/system.json")); assert data["family"]'
HOME=/tmp/bc250-home /opt/bc250/bin/bc250-control-center-cli --json qualification template --section compute_units > /tmp/qualification.json
python3 -c 'import json; data=json.load(open("/tmp/qualification.json")); assert data["section"] == "compute_units"; assert data["source_version"] == open("/src/VERSION").read().strip(); assert len(data["checks"]) == 3'
HOME=/tmp/bc250-home /opt/bc250/bin/bc250-control-center-cli --json release-gates > /tmp/release-gates.json
python3 -c 'import json; data=json.load(open("/tmp/release-gates.json")); assert data["schema"] == 2; assert data["public_release_ready"] is False; assert data["qualification_evidence_can_self_certify"] is False'
HOME=/tmp/bc250-home PREFIX=/opt/bc250 bash /src/scripts/uninstall-local.sh --yes --keep-privileged
test ! -e /opt/bc250/bin/bc250-control-center
EOF

echo "Rootless network backend: $network_backend"
podman run --rm --pull=never --network="$network_backend" \
  --security-opt label=disable \
  --volume "$ROOT_DIR:/src:ro" \
  "$image" bash -lc "$bootstrap; $validation"

echo "Clean-install container QA passed for $family ($image)."
