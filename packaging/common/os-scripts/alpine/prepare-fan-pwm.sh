#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bc250_install_fan_build_prerequisites() {
  # The reviewed nct6687d workflow installs through "make dkms/install", and
  # Alpine packages akms rather than DKMS. Stop with that reason instead of
  # apk's "dkms (no such package)".
  if ! have dkms; then
    error "Alpine packages akms, not DKMS; the nct6687d PWM driver workflow needs DKMS and is unavailable here."
    exit 69
  fi
  as_root apk add --no-progress build-base linux-headers kmod lm_sensors git
}
# shellcheck source=../common/prepare-fan-pwm-dkms.sh
source "$SCRIPT_DIR/../common/prepare-fan-pwm-dkms.sh"
