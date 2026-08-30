"""Closed, reviewable Arch/CachyOS BC-250 stack installation workflow.

The packages are intentionally supplied by MastaG's external repository. This
module never accepts a repository URL, package name, or shell fragment from the
UI: the high-impact operation has one reviewed target and is exposed only on
plain Arch Linux or CachyOS, the two layouts documented by upstream.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

CACHYOS_BC250_REPOSITORY = "https://github.com/MastaG/linux-cachyos-bc250"
CACHYOS_BC250_PACMAN_REPOSITORY = "bc250-cachyos"
CACHYOS_BC250_INCLUDE = "/etc/pacman.d/bc250-control-center-bc250-cachyos.conf"
CACHYOS_BC250_PACKAGES = (
    "linux-cachyos-bc250",
    "linux-cachyos-bc250-headers",
)
CACHYOS_BC250_MESA_PACKAGES = ("mesa", "vulkan-radeon")
CACHYOS_BC250_ACTIONS = {"kernel", "mesa", "full"}
MASTA_BC250_SUPPORTED_IDS = frozenset({"arch", "cachyos", "cachy"})


def masta_bc250_stack_supported(*, distro_id: str, family: str) -> bool:
    """Return whether upstream documents this exact pacman layout.

    Arch derivatives intentionally share the generic dependency backend, but
    they do not necessarily share Arch/CachyOS repository priority, package
    versions, signatures, or kernel ABI.  Keep this high-impact workflow
    narrower than the general package-family classifier.
    """

    normalized_id = str(distro_id or "").strip().lower()
    normalized_family = str(family or "").strip().lower()
    return (
        normalized_id in MASTA_BC250_SUPPORTED_IDS
        and normalized_family in {"arch", "cachyos"}
    )


def masta_bc250_stack_state(*, distro_id: str, family: str) -> dict:
    """Return a read-only installation snapshot for the compatibility UI."""

    supported = masta_bc250_stack_supported(
        distro_id=distro_id,
        family=family,
    )
    repository_configured = Path(CACHYOS_BC250_INCLUDE).is_file()

    def installed(package: str) -> bool:
        try:
            result = subprocess.run(
                ("pacman", "-Qq", package),
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout.strip() == package

    kernel_installed = all(installed(package) for package in CACHYOS_BC250_PACKAGES)
    mesa_packages = ("mesa", "vulkan-radeon")
    installed_mesa = all(installed(package) for package in mesa_packages)
    mesa_from_bc250_repository = False
    if repository_configured and installed_mesa:
        try:
            result = subprocess.run(
                ("pacman", "-Sl", CACHYOS_BC250_PACMAN_REPOSITORY),
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
                env={**os.environ, "LANG": "C", "LC_ALL": "C"},
            )
            installed_rows = {
                fields[1]
                for line in result.stdout.splitlines()
                if len(fields := line.split()) >= 4
                and fields[0] == CACHYOS_BC250_PACMAN_REPOSITORY
                and fields[-1] == "[installed]"
            }
            mesa_from_bc250_repository = all(
                package in installed_rows for package in mesa_packages
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return {
        "supported": supported,
        "repository_configured": repository_configured,
        "kernel_installed": kernel_installed,
        "kernel_active": kernel_installed and "bc250" in platform.release().lower(),
        "mesa_installed": mesa_from_bc250_repository,
    }


def build_cachyos_bc250_kernel_command(action: str = "kernel") -> str:
    """Return one fixed Arch/CachyOS BC-250 kernel/Mesa workflow.

    ``kernel`` keeps the current kernel as a boot fallback, ``mesa``
    updates only the stable patched Mesa packages, and ``full`` performs both.
    The repository is external and unsigned by design, so its source and
    ``Optional TrustAll`` policy are repeated before any package transaction.
    """

    action = str(action or "kernel").strip().lower()
    if action not in CACHYOS_BC250_ACTIONS:
        raise ValueError("Unsupported CachyOS BC-250 action.")
    include = CACHYOS_BC250_INCLUDE
    repository = CACHYOS_BC250_PACMAN_REPOSITORY
    selected = []
    if action in {"kernel", "full"}:
        selected.extend(CACHYOS_BC250_PACKAGES)
    if action in {"mesa", "full"}:
        selected.extend(CACHYOS_BC250_MESA_PACKAGES)
    targets = " ".join(f"{repository}/{name}" for name in selected)
    if action == "kernel":
        # This repository also has higher-priority Mesa split packages.  Keep
        # the explicit kernel-only action honest while still performing the
        # full Arch system upgrade required by pacman.
        scope_guard = "bc250_scope_guard=(--ignore 'mesa*,lib32-mesa*,vulkan-*,lib32-vulkan-*,opencl-mesa,lib32-opencl-mesa')"
    elif action == "mesa":
        # An already installed BC-250 kernel must not be upgraded as a side
        # effect of the Mesa-only transaction.
        scope_guard = "bc250_scope_guard=(--ignore 'linux-cachyos-bc250*,linux-cachyos-rc-bc250*,linux-cachyos-bore-bc250*')"
    else:
        scope_guard = "bc250_scope_guard=()"
    # Explicit repository targets (without --needed) also repair a same-version
    # stock installation. Mesa's Vulkan driver is a separate split package.
    mesa_selection = (
        f'''echo "== Installing stable BC-250 patched Mesa and RADV =="
if pacman-conf --repo-list | grep -Fxq multilib || pacman -Qq lib32-glibc >/dev/null 2>&1; then
  bc250_packages+=({repository}/lib32-mesa {repository}/lib32-vulkan-radeon)
else
  echo "[INFO] multilib is unavailable; only the 64-bit Mesa/RADV pair will be installed."
fi'''
        if action in {"mesa", "full"} else ""
    )
    kernel_step = (
        '''pacman -Q linux-cachyos-bc250 linux-cachyos-bc250-headers
printf '%s\\n' nct6687 | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null
echo "BC250_REBOOT_REQUIRED=1"'''
        if action in {"kernel", "full"}
        else ""
    )
    mesa_step = (
        '''pacman -Q mesa vulkan-radeon
echo "[INFO] Log out/restart games after Mesa changes; reboot is recommended when combined with the kernel."'''
        if action in {"mesa", "full"}
        else ""
    )
    return f'''set -euo pipefail
export LANG=C LC_ALL=C
echo "== Arch/CachyOS BC-250 {action} workflow (external upstream) =="
test -r /etc/os-release || {{ echo "ERROR: /etc/os-release is unavailable."; exit 64; }}
. /etc/os-release
case "${{ID:-}}" in
  arch) bc250_anchor='core' ;;
  cachyos|cachy) bc250_anchor='cachyos-v3' ;;
  *) echo "ERROR: This optional workflow is supported only on plain Arch Linux or CachyOS."; exit 64 ;;
esac
command -v pacman >/dev/null 2>&1 || {{ echo "ERROR: pacman is required on Arch/CachyOS."; exit 69; }}
command -v pacman-conf >/dev/null 2>&1 || {{ echo "ERROR: pacman-conf is required to validate repositories."; exit 69; }}
command -v getent >/dev/null 2>&1 || {{ echo "ERROR: getent is required to validate DNS before changing pacman configuration."; exit 69; }}
getent ahosts github.com >/dev/null 2>&1 || {{ echo "ERROR: DNS cannot resolve github.com. Check the network and DNS configuration, then try again. No pacman configuration was changed."; exit 68; }}
echo "[WARN] External source: {CACHYOS_BC250_REPOSITORY}"
echo "[WARN] Its pacman repository uses Optional TrustAll (unsigned packages)."
echo "[INFO] The current kernel is not removed; keep its boot entry as a recovery fallback."
echo "[WARN] Pacman performs a full system upgrade. Other installed packages, including Mesa, may update from this repository."
bc250_packages=({targets})
{scope_guard}
{mesa_selection}
bc250_repo_file="$(mktemp)"
bc250_pacman_conf=''
trap 'rm -f -- "$bc250_repo_file" "$bc250_pacman_conf"' EXIT
bc250_pacman_conf="$(mktemp)"
awk '$0 != "Include = {include}"' /etc/pacman.conf > "$bc250_pacman_conf"
grep -Eq "^[[:space:]]*\\[$bc250_anchor\\][[:space:]]*$" "$bc250_pacman_conf" || {{ echo "ERROR: [$bc250_anchor] was not found; refusing to guess repository priority."; exit 65; }}
# An independently configured copy must be reconciled by the operator, not
# duplicated or removed by this application.
if pacman-conf --repo-list | grep -Fxq '{repository}' && ! grep -Fqx 'Include = {include}' /etc/pacman.conf; then
  echo "ERROR: The BC-250 repository is already configured outside Control Center. Review pacman.conf before continuing."; exit 65
fi
if ! awk -v anchor="$bc250_anchor" -v include_line='Include = {include}' '
  {{
    normalized=$0
    sub(/^[[:space:]]*/, "", normalized)
    sub(/[[:space:]]*$/, "", normalized)
    if (normalized == "[" anchor "]" && !inserted) {{ print include_line; inserted=1 }}
    print
  }}
  END {{ if (!inserted) exit 42 }}
' "$bc250_pacman_conf" > "$bc250_repo_file.inserted"; then
  echo "ERROR: Could not place the BC-250 repository before [$bc250_anchor]."; exit 65
fi
mv "$bc250_repo_file.inserted" "$bc250_pacman_conf"
sudo install -d -m 0755 /var/backups
bc250_backup="$(sudo mktemp -d /var/backups/bc250-pacman.XXXXXX)"
sudo cp -a /etc/pacman.conf "$bc250_backup/pacman.conf"
if sudo test -e '{include}'; then sudo cp -a '{include}' "$bc250_backup/bc250-repository.conf"; fi
echo "[INFO] Original pacman configuration preserved in $bc250_backup"
printf '%s\\n' '[{repository}]' 'SigLevel = Optional TrustAll' 'Server = https://github.com/MastaG/linux-cachyos-bc250/releases/download/repo' > "$bc250_repo_file"
sudo install -D -m 0644 "$bc250_repo_file" "{include}"
sudo install -m 0644 "$bc250_pacman_conf" /etc/pacman.conf
echo "== Installing selected BC-250 packages in one system-upgrade transaction =="
sudo pacman -Syu "${{bc250_scope_guard[@]}}" "${{bc250_packages[@]}}"
for bc250_target in "${{bc250_packages[@]}}"; do
  bc250_name="${{bc250_target#*/}}"
  pacman -Sl '{repository}' | awk -v package="$bc250_name" '
    $1 == "{repository}" && $2 == package && $NF == "[installed]" {{ found=1 }}
    END {{ exit(found ? 0 : 1) }}
  ' || {{ echo "ERROR: $bc250_name was not verified as the installed {repository} build."; exit 74; }}
done
{kernel_step}
{mesa_step}
echo "OK: Arch/CachyOS BC-250 {action} workflow completed. Review package output before rebooting."'''
