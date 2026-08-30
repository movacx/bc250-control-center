#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bc250_install_fan_build_prerequisites() {
  as_root emerge --ask=n --verbose --update --deep --newuse \
    sys-devel/gcc sys-kernel/dkms sys-kernel/linux-headers sys-apps/kmod \
    sys-apps/lm-sensors dev-vcs/git
}
# shellcheck source=../common/prepare-fan-pwm-dkms.sh
source "$SCRIPT_DIR/../common/prepare-fan-pwm-dkms.sh"
