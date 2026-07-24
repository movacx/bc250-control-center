#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KERNEL_RELEASE="$(uname -r)"

bold "${BC250_OS_LABEL:-Debian family}: preparing nct6687 PWM driver"
as_root apt-get update
as_root apt-get install -y lm-sensors git build-essential dkms dh-dkms kmod "linux-headers-$KERNEL_RELEASE"
if [[ ! -e "/lib/modules/$KERNEL_RELEASE/build/Makefile" && ! -e "/usr/lib/modules/$KERNEL_RELEASE/build/Makefile" ]]; then
  error "Matching kernel headers are missing for $KERNEL_RELEASE"
  exit 21
fi
clone_or_update https://github.com/Fred78290/nct6687d "$SOURCE_DIR"
(
  cd "$SOURCE_DIR"
  as_root make dkms/install
)
as_root depmod -a "$KERNEL_RELEASE"
modinfo nct6687 >/dev/null 2>&1 || { error "nct6687 DKMS installation did not produce a module for $KERNEL_RELEASE"; exit 22; }
info "nct6687 DKMS module installed for $KERNEL_RELEASE"
