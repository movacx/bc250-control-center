#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bc250_install_fan_build_prerequisites() {
  as_root apk add --no-progress build-base dkms linux-headers kmod lm_sensors git
}
# shellcheck source=../common/prepare-fan-pwm-dkms.sh
source "$SCRIPT_DIR/../common/prepare-fan-pwm-dkms.sh"
