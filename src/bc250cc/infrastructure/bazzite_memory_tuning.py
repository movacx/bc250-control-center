"""Reviewed, explicit Bazzite zswap and TTM boot transaction.

This module only builds the command shown in the user-visible terminal.  The
caller must obtain an explicit GUI confirmation before launching it.  In
particular, zswap is never enabled without first proving that the dedicated
disk-backed swapfile is active.
"""
from __future__ import annotations

from bc250cc.infrastructure.memory_runtime import TTM_GIB_PRESETS

ZSWAP_POLICIES = {"zswap-16": 16, "zswap-32": 32}
ZRAM_SWAP_POLICIES = {"zram-swap-16": 16}
TTM_DEFAULT = -1
#: The zswap boot arguments this workflow owns. Captured before the first
#: change, removed and restored as one family, so a restore puts back exactly
#: the arguments the image had — the same tuning the mutable adapter applies
#: through sysfs (see privileged/lib/system_setup_memory.py).
ZSWAP_KARG_PATTERN = r"^zswap\.(enabled|compressor|max_pool_percent)="
ZSWAP_KARG_VALID = r"^zswap\.(enabled=(0|1|Y|N|y|n)|compressor=[a-z0-9-]+|max_pool_percent=[0-9]+)$"
ZSWAP_TUNING_KARGS = ("zswap.compressor=lz4", "zswap.max_pool_percent=25")


def build_bazzite_memory_tuning_command(policy: str, ttm_gib: int) -> str:
    """Return an auditable Bazzite-only boot transaction.

    ``current`` restores Bazzite's ZRAM-only default, while ``preserve`` leaves
    swap/compression untouched so TTM can be applied independently.  The
    zswap policies disable Bazzite's zram only on the next boot.
    """
    policy = str(policy or "current")
    if policy not in {"current", "preserve", *ZSWAP_POLICIES, *ZRAM_SWAP_POLICIES}:
        raise ValueError("Unsupported Bazzite memory policy.")
    if type(ttm_gib) is not int or ttm_gib not in {TTM_DEFAULT, 0, *TTM_GIB_PRESETS}:
        raise ValueError("TTM must be unchanged, default, or one of 8, 10, or 12 GiB.")
    lines = [
        "set -Eeuo pipefail",
        "test \"$(id -u)\" -ne 0 || { echo 'ERROR: run this workflow as the Desktop Mode user, not root'; exit 60; }",
        "grep -Eqi \"^ID=['\\\"]?bazzite['\\\"]?$\" /etc/os-release || { echo 'ERROR: this memory workflow is only supported on Bazzite'; exit 61; }",
        "test -e /run/ostree-booted || { echo 'ERROR: the Bazzite image deployment was not detected'; exit 61; }",
        "command -v rpm-ostree >/dev/null 2>&1 || { echo 'ERROR: rpm-ostree is required on Bazzite'; exit 62; }",
        "command -v systemd-escape >/dev/null 2>&1 || { echo 'ERROR: systemd-escape is required'; exit 62; }",
        "bc250_pci=0; for bc250_dev in /sys/bus/pci/devices/*; do if [ \"$(cat \"$bc250_dev/vendor\" 2>/dev/null || true)\" = 0x1002 ] && [ \"$(cat \"$bc250_dev/device\" 2>/dev/null || true)\" = 0x13fe ]; then bc250_pci=1; break; fi; done",
        "test \"$bc250_pci\" -eq 1 || { echo 'ERROR: AMD BC250 PCI hardware was not detected'; exit 62; }",
        "echo '== BC250 Bazzite memory setup =='",
        "echo 'This changes boot configuration and may create a disk swapfile.'",
        "echo 'Close games and memory-heavy workloads before continuing.'",
        "sudo -v",
        "# No backup manager is created: rpm-ostree keeps deployment history and this workflow manages only its fixed paths.",
    ]
    if ttm_gib != 0:
        lines.extend((
            "sudo test -r /sys/module/ttm/parameters/pages_limit || { echo 'ERROR: this kernel does not expose the TTM pages_limit parameter'; exit 69; }",
            "bc250_live_ttm=$(sudo cat /sys/module/ttm/parameters/pages_limit)",
            "[[ \"$bc250_live_ttm\" =~ ^[0-9]+$ ]] || { echo 'ERROR: the live TTM pages_limit value is invalid'; exit 69; }",
            "bc250_page_size=$(getconf PAGESIZE)",
            "[[ \"$bc250_page_size\" =~ ^[0-9]+$ ]] && [ \"$bc250_page_size\" -gt 0 ] || { echo 'ERROR: could not determine kernel page size'; exit 70; }",
        ))
        if ttm_gib > 0:
            lines.extend((
                f"bc250_ttm_bytes=$(({ttm_gib} * 1024 * 1024 * 1024))",
                "(( bc250_ttm_bytes % bc250_page_size == 0 )) || { echo 'ERROR: selected TTM GiB value is not representable in kernel pages'; exit 71; }",
                "bc250_ttm_pages=$((bc250_ttm_bytes / bc250_page_size))",
                "bc250_mem_bytes=$(($(awk '$1==\"MemTotal:\" {print $2}' /proc/meminfo) * 1024))",
                "test \"$bc250_mem_bytes\" -ge \"$bc250_ttm_bytes\" || { echo 'ERROR: selected TTM target exceeds visible physical RAM'; exit 71; }",
            ))
    if policy in ZSWAP_POLICIES:
        lines.extend((
            "sudo test -r /sys/module/zswap/parameters/enabled || { echo 'ERROR: this kernel does not expose zswap control'; exit 72; }",
            "bc250_live_zswap=$(sudo cat /sys/module/zswap/parameters/enabled)",
            "[[ \"$bc250_live_zswap\" =~ ^(Y|N|y|n|0|1)$ ]] || { echo 'ERROR: the live zswap state is invalid'; exit 72; }",
        ))
    if ttm_gib != 0:
        lines.extend((
            "bc250_ttm_state=/etc/bc250-control-center/ttm-kargs.original",
            "sudo install -d -m 0755 /etc/bc250-control-center",
            "if sudo test -e \"$bc250_ttm_state\"; then",
            "  sudo test ! -L \"$bc250_ttm_state\" && sudo test -f \"$bc250_ttm_state\" || { echo 'ERROR: unsafe TTM restoration state'; exit 73; }",
            "  test \"$(sudo stat -c %u \"$bc250_ttm_state\")\" -eq 0 && test \"$(sudo stat -c %a \"$bc250_ttm_state\")\" = 600 || { echo 'ERROR: unprotected TTM restoration state'; exit 73; }",
            "  sudo head -n 1 \"$bc250_ttm_state\" | grep -Fqx '# Managed by BC250 Control Center' || { echo 'ERROR: foreign TTM restoration state was preserved'; exit 73; }",
            "  mapfile -t bc250_original_ttm < <(sudo tail -n +2 \"$bc250_ttm_state\")",
            "else",
            "  bc250_original_ttm=()",
        ))
        if ttm_gib > 0:
            lines.extend((
                "  mapfile -t bc250_original_ttm < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '^ttm\\.pages_limit=' || true)",
                "  for bc250_arg in \"${bc250_original_ttm[@]}\"; do [[ \"$bc250_arg\" =~ ^ttm\\.pages_limit=[0-9]+$ ]] || { echo 'ERROR: refusing malformed pre-existing TTM arguments'; exit 73; }; done",
                "  { printf '%s\\n' '# Managed by BC250 Control Center' \"${bc250_original_ttm[@]}\"; } | sudo tee \"$bc250_ttm_state\" >/dev/null",
                "  sudo chmod 0600 \"$bc250_ttm_state\"",
            ))
        lines.extend((
            "fi",
            "for bc250_arg in \"${bc250_original_ttm[@]}\"; do [[ \"$bc250_arg\" =~ ^ttm\\.pages_limit=[0-9]+$ ]] || { echo 'ERROR: invalid saved TTM argument'; exit 73; }; done",
        ))
    if policy in {"current", *ZSWAP_POLICIES, *ZRAM_SWAP_POLICIES}:
        lines.extend((
            "bc250_zswap_state=/etc/bc250-control-center/zswap-kargs.original",
            "sudo install -d -m 0755 /etc/bc250-control-center",
            "if sudo test -e \"$bc250_zswap_state\"; then",
            "  sudo test ! -L \"$bc250_zswap_state\" && sudo test -f \"$bc250_zswap_state\" || { echo 'ERROR: unsafe zswap restoration state'; exit 74; }",
            "  test \"$(sudo stat -c %u \"$bc250_zswap_state\")\" -eq 0 && test \"$(sudo stat -c %a \"$bc250_zswap_state\")\" = 600 || { echo 'ERROR: unprotected zswap restoration state'; exit 74; }",
            "  sudo head -n 1 \"$bc250_zswap_state\" | grep -Fqx '# Managed by BC250 Control Center' || { echo 'ERROR: foreign zswap restoration state was preserved'; exit 74; }",
            "  mapfile -t bc250_original_zswap < <(sudo tail -n +2 \"$bc250_zswap_state\")",
            "else",
            "  bc250_original_zswap=()",
        ))
        if policy in {**ZSWAP_POLICIES, **ZRAM_SWAP_POLICIES}:
            lines.extend((
                "  mapfile -t bc250_original_zswap < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '" + ZSWAP_KARG_PATTERN + "' || true)",
                "  for bc250_arg in \"${bc250_original_zswap[@]}\"; do [[ \"$bc250_arg\" =~ " + ZSWAP_KARG_VALID + " ]] || { echo 'ERROR: refusing malformed pre-existing zswap arguments'; exit 74; }; done",
                "  { printf '%s\\n' '# Managed by BC250 Control Center' \"${bc250_original_zswap[@]}\"; } | sudo tee \"$bc250_zswap_state\" >/dev/null",
                "  sudo chmod 0600 \"$bc250_zswap_state\"",
            ))
        lines.extend((
            "fi",
            "for bc250_arg in \"${bc250_original_zswap[@]}\"; do [[ \"$bc250_arg\" =~ " + ZSWAP_KARG_VALID + " ]] || { echo 'ERROR: invalid saved zswap argument'; exit 74; }; done",
        ))
    if policy in {**ZSWAP_POLICIES, **ZRAM_SWAP_POLICIES}:
        size_gib = {**ZSWAP_POLICIES, **ZRAM_SWAP_POLICIES}[policy]
        lines.extend((
            "findmnt -no FSTYPE /var | grep -qx btrfs || { echo 'ERROR: BC250 zswap setup currently supports only Btrfs /var; no change was made'; exit 63; }",
            "command -v btrfs >/dev/null 2>&1 || { echo 'ERROR: btrfs-progs is required to create a safe Btrfs swapfile'; exit 64; }",
            "swap_path=/var/swap/bc250-zswap.swap",
            f"swap_bytes=$(({size_gib} * 1024 * 1024 * 1024))",
            "swap_unit=$(systemd-escape --path --suffix=swap \"$swap_path\")",
            "swap_unit_path=\"/etc/systemd/system/$swap_unit\"",
            "available_bytes=$(df -B1 --output=avail /var | tail -n 1 | tr -d ' ')",
            "filesystem_bytes=$(df -B1 --output=size /var | tail -n 1 | tr -d ' ')",
            # 2 GiB, or 5 % of the filesystem when that is more — the reserve
            # the mutable adapter keeps too, so a large disk is never filled
            # to the edge by a swapfile.
            "reserve_bytes=$((filesystem_bytes / 20)); [ \"$reserve_bytes\" -ge 2147483648 ] || reserve_bytes=2147483648",
            "required_bytes=$((swap_bytes + reserve_bytes))",
            "test \"$available_bytes\" -ge \"$required_bytes\" || { echo \"ERROR: insufficient free space; $((reserve_bytes / 1073741824)) GiB must remain free after creating swap\"; exit 65; }",
            "if sudo test -e /var/swap; then",
            "  sudo test ! -L /var/swap && sudo test -d /var/swap || { echo 'ERROR: /var/swap is not a safe directory'; exit 65; }",
            "  test \"$(sudo stat -c %u /var/swap)\" -eq 0 || { echo 'ERROR: /var/swap is not root-owned'; exit 65; }",
            "  test -z \"$(sudo find /var/swap -maxdepth 0 -perm /022 -print)\" || { echo 'ERROR: /var/swap is writable by non-root users'; exit 65; }",
            "else",
            "  sudo install -d -m 0700 /var/swap",
            "fi",
            # /var/swap is mode 0700. A Desktop Mode user cannot traverse it,
            # so an unprivileged test falsely reports an existing file as
            # missing and btrfs then fails with the misleading "File exists".
            "if sudo test -e \"$swap_path\"; then",
            "  sudo test ! -L \"$swap_path\" && sudo test -f \"$swap_path\" || { echo 'ERROR: refusing a symlink or non-regular swapfile'; exit 66; }",
            "  test \"$(sudo stat -c %u \"$swap_path\")\" -eq 0 || { echo 'ERROR: the existing swapfile is not root-owned'; exit 66; }",
            "  test \"$(sudo stat -c %a \"$swap_path\")\" = 600 || { echo 'ERROR: the existing swapfile permissions are not 0600'; exit 66; }",
            "  sudo test -f \"$swap_unit_path\" && sudo grep -Fqx '# Managed by BC250 Control Center' \"$swap_unit_path\" || { echo 'ERROR: an unclaimed swapfile exists at the BC250 path and was preserved'; exit 66; }",
            "  test \"$(sudo stat -c %s \"$swap_path\")\" -eq \"$swap_bytes\" || { echo 'ERROR: the existing BC250 swapfile has a different size; choose its current size or remove it manually only after recovery review'; exit 66; }",
            f"  echo '[INFO] Reusing the existing verified {size_gib} GiB BC250 swapfile'",
            "else",
            f"  echo '[INFO] Creating {size_gib} GiB Btrfs-safe backing swapfile'",
            "  sudo btrfs filesystem mkswapfile --size \"${swap_bytes}\" \"$swap_path\"",
            "fi",
            # A .swap unit name is not arbitrary: systemd requires the escaped
            # path of What=.  The original bc250-swapfile.swap name therefore
            # made systemd reject the unit as malformed.
            "legacy_swap_unit=/etc/systemd/system/bc250-swapfile.swap",
            "if sudo test -e \"$legacy_swap_unit\"; then",
            "  sudo grep -Fqx '# Managed by BC250 Control Center' \"$legacy_swap_unit\" || { echo 'ERROR: existing legacy swap unit is not managed by BC250; it was preserved'; exit 67; }",
            "  echo '[INFO] Replacing the earlier invalid BC250 swap unit with the systemd path-based unit name'",
            "  sudo systemctl disable --now bc250-swapfile.swap >/dev/null 2>&1 || true",
            "  sudo rm -f \"$legacy_swap_unit\"",
            "fi",
            "if sudo test -e \"$swap_unit_path\" && ! sudo grep -Fqx '# Managed by BC250 Control Center' \"$swap_unit_path\"; then echo 'ERROR: existing path-based swap unit is not managed by BC250; it was preserved'; exit 67; fi",
            "sudo tee \"$swap_unit_path\" >/dev/null <<'BC250_SWAP_UNIT'",
            "# Managed by BC250 Control Center",
            "[Unit]",
            "Description=BC250 Control Center disk swap fallback",
            "Before=swap.target",
            "",
            "[Swap]",
            "What=/var/swap/bc250-zswap.swap",
            "Options=pri=-2",
            "",
            "[Install]",
            "WantedBy=swap.target",
            "BC250_SWAP_UNIT",
            "sudo systemctl daemon-reload",
            "sudo systemctl enable --now \"$swap_unit\"",
            "swapon --show --noheadings --output NAME | awk '{print $1}' | grep -Fx \"$swap_path\" >/dev/null || { echo 'ERROR: backing swapfile did not activate; zram and kernel arguments were left unchanged'; exit 67; }",
        ))
        if policy in ZSWAP_POLICIES:
            lines.extend((
                "if test -e /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf && ! sudo grep -Fqx '# Managed by BC250 Control Center' /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf; then echo 'ERROR: existing zram drop-in is not managed by BC250; it was preserved'; exit 68; fi",
                "sudo install -d -m 0755 /etc/systemd/system/systemd-zram-setup@zram0.service.d /etc/bc250-control-center",
                "if sudo test -e /etc/bc250-control-center/zram-disabled && ! sudo grep -Fqx '# Managed by BC250 Control Center' /etc/bc250-control-center/zram-disabled; then echo 'ERROR: existing zram marker is not managed by BC250; it was preserved'; exit 68; fi",
                "sudo tee /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf >/dev/null <<'BC250_ZRAM_DROPIN'",
                "# Managed by BC250 Control Center",
                "[Unit]",
                "ConditionPathExists=!/etc/bc250-control-center/zram-disabled",
                "BC250_ZRAM_DROPIN",
                "printf '%s\\n' '# Managed by BC250 Control Center' | sudo tee /etc/bc250-control-center/zram-disabled >/dev/null",
                "echo '[INFO] zram remains active for this session and will be disabled only after reboot.'",
            ))
        else:
            lines.extend((
                "if sudo test -e /etc/bc250-control-center/zram-disabled; then sudo grep -Fqx '# Managed by BC250 Control Center' /etc/bc250-control-center/zram-disabled || { echo 'ERROR: foreign zram marker was preserved'; exit 68; }; sudo rm -f /etc/bc250-control-center/zram-disabled; fi",
                "if sudo grep -Fqx '# Managed by BC250 Control Center' /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf 2>/dev/null; then sudo rm -f /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf; fi",
                "echo '[INFO] ZRAM is preserved as the fast primary swap; the disk swapfile has lower priority.'",
            ))
    elif policy == "current":
        lines.extend((
            "swap_path=/var/swap/bc250-zswap.swap",
            "swap_unit=$(systemd-escape --path --suffix=swap \"$swap_path\")",
            "swap_unit_path=\"/etc/systemd/system/$swap_unit\"",
            "if sudo test -f \"$swap_unit_path\" && sudo grep -Fqx '# Managed by BC250 Control Center' \"$swap_unit_path\"; then",
            "  sudo test ! -L /var/swap && sudo test -d /var/swap || { echo 'ERROR: unsafe /var/swap directory; managed data was preserved'; exit 68; }",
            "  if sudo test -e \"$swap_path\"; then sudo test ! -L \"$swap_path\" && sudo test -f \"$swap_path\" && test \"$(sudo stat -c %u \"$swap_path\")\" -eq 0 && test \"$(sudo stat -c %a \"$swap_path\")\" = 600 || { echo 'ERROR: unsafe swapfile; managed data was preserved'; exit 68; }; fi",
            "  sudo systemctl disable \"$swap_unit\"",
            "  if awk -v path=\"$swap_path\" 'NR>1 && $1==path {found=1} END {exit !found}' /proc/swaps; then",
            "    bc250_swap_used=$(awk -v path=\"$swap_path\" 'NR>1 && $1==path {print $4}' /proc/swaps)",
            "    bc250_mem_available=$(awk '$1==\"MemAvailable:\" {print $2}' /proc/meminfo)",
            "    if [ \"${bc250_mem_available:-0}\" -le \"$((${bc250_swap_used:-0} + 1048576))\" ]; then echo 'Restore pending: insufficient available RAM. Swapfile preserved; reboot, then retry restore.'; exit 68; fi",
            "    sudo swapoff \"$swap_path\" || { echo 'Restore pending: swapoff failed. Swapfile preserved; reboot, then retry restore.'; exit 68; }",
            "  fi",
            "  if awk -v path=\"$swap_path\" 'NR>1 && $1==path {found=1} END {exit !found}' /proc/swaps; then echo 'ERROR: active swapfile preserved'; exit 68; fi",
            "  sudo rm -f \"$swap_unit_path\" \"$swap_path\"",
            "  echo '[INFO] Removed the BC250-managed disk swapfile and restored Bazzite ZRAM.'",
            "else",
            "  echo '[INFO] No BC250-managed disk swapfile was found; existing swap configuration was preserved.'",
            "fi",
            "if sudo test -f /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf && sudo grep -Fqx '# Managed by BC250 Control Center' /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf; then sudo rm -f /etc/systemd/system/systemd-zram-setup@zram0.service.d/90-bc250-zswap.conf; fi",
            "if sudo test -e /etc/bc250-control-center/zram-disabled; then sudo grep -Fqx '# Managed by BC250 Control Center' /etc/bc250-control-center/zram-disabled || { echo 'ERROR: foreign zram marker was preserved'; exit 68; }; sudo rm -f /etc/bc250-control-center/zram-disabled; fi",
        ))

    lines.extend((
        "bc250_karg_args=()",
        "bc250_remove_ttm_state=0",
        "bc250_remove_zswap_state=0",
    ))
    if ttm_gib > 0:
        lines.extend((
            "mapfile -t bc250_old_kargs < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '^ttm\\.pages_limit=' || true)",
            "for bc250_arg in \"${bc250_old_kargs[@]}\"; do [[ \"$bc250_arg\" =~ ^ttm\\.pages_limit=[0-9]+$ ]] || { echo 'ERROR: refusing malformed current TTM arguments'; exit 75; }; bc250_karg_args+=(\"--delete-if-present=$bc250_arg\"); done",
        ))
    elif ttm_gib == TTM_DEFAULT:
        lines.extend((
            "if sudo test -f \"$bc250_ttm_state\"; then",
            "  mapfile -t bc250_old_kargs < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '^ttm\\.pages_limit=' || true)",
            "  for bc250_arg in \"${bc250_old_kargs[@]}\"; do [[ \"$bc250_arg\" =~ ^ttm\\.pages_limit=[0-9]+$ ]] || { echo 'ERROR: refusing malformed current TTM arguments'; exit 75; }; bc250_karg_args+=(\"--delete-if-present=$bc250_arg\"); done",
            "fi",
        ))
    if policy in ZSWAP_POLICIES:
        lines.extend((
            "mapfile -t bc250_old_zswap < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '" + ZSWAP_KARG_PATTERN + "' || true)",
            "for bc250_arg in \"${bc250_old_zswap[@]}\"; do [[ \"$bc250_arg\" =~ " + ZSWAP_KARG_VALID + " ]] || { echo 'ERROR: refusing malformed current zswap arguments'; exit 75; }; bc250_karg_args+=(\"--delete-if-present=$bc250_arg\"); done",
        ))
        lines.append("bc250_karg_args+=(--append-if-missing=zswap.enabled=1)")
        # The same pool the mutable adapter tunes through sysfs: lz4 and a
        # quarter of RAM. A kernel without lz4 built in keeps its default.
        lines.extend(f"bc250_karg_args+=(--append-if-missing={karg})" for karg in ZSWAP_TUNING_KARGS)
    elif policy in ZRAM_SWAP_POLICIES:
        lines.extend((
            "mapfile -t bc250_old_zswap < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '" + ZSWAP_KARG_PATTERN + "' || true)",
            "for bc250_arg in \"${bc250_old_zswap[@]}\"; do [[ \"$bc250_arg\" =~ " + ZSWAP_KARG_VALID + " ]] || { echo 'ERROR: refusing malformed current zswap arguments'; exit 75; }; bc250_karg_args+=(\"--delete-if-present=$bc250_arg\"); done",
            "bc250_karg_args+=(--append-if-missing=zswap.enabled=0)",
        ))
    elif policy == "current":
        lines.extend((
            "if sudo test -f \"$bc250_zswap_state\"; then",
            "  mapfile -t bc250_old_zswap < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '" + ZSWAP_KARG_PATTERN + "' || true)",
            "  for bc250_arg in \"${bc250_old_zswap[@]}\"; do [[ \"$bc250_arg\" =~ " + ZSWAP_KARG_VALID + " ]] || { echo 'ERROR: refusing malformed current zswap arguments'; exit 75; }; bc250_karg_args+=(\"--delete-if-present=$bc250_arg\"); done",
            "  for bc250_arg in \"${bc250_original_zswap[@]}\"; do bc250_karg_args+=(\"--append-if-missing=$bc250_arg\"); done",
            "  bc250_remove_zswap_state=1",
            "else",
            "  echo '[INFO] No BC250-owned zswap kernel argument exists; pre-existing arguments were preserved.'",
            "fi",
        ))
    if ttm_gib == TTM_DEFAULT:
        lines.extend((
            "if sudo test -f \"$bc250_ttm_state\"; then",
            "  for bc250_arg in \"${bc250_original_ttm[@]}\"; do bc250_karg_args+=(\"--append-if-missing=$bc250_arg\"); done",
            "  bc250_remove_ttm_state=1",
            "  echo '[INFO] Restoring the exact TTM kernel argument captured before BC250 tuning.'",
            "else",
            "  echo '[INFO] No BC250-owned TTM argument exists; pre-existing TTM arguments were preserved.'",
            "fi",
        ))
    elif ttm_gib:
        lines.extend((
            f'echo "[INFO] Setting Dynamic GPU Memory Limit (TTM) to {ttm_gib} GiB using page size $bc250_page_size ($bc250_ttm_pages pages)"',
            "bc250_karg_args+=(\"--append-if-missing=ttm.pages_limit=$bc250_ttm_pages\")",
        ))
    lines.extend((
        "if ((${#bc250_karg_args[@]})); then sudo rpm-ostree kargs \"${bc250_karg_args[@]}\"; fi",
        "if [ \"$bc250_remove_ttm_state\" -eq 1 ]; then sudo rm -f \"$bc250_ttm_state\"; fi",
        "if [ \"$bc250_remove_zswap_state\" -eq 1 ]; then sudo rm -f \"$bc250_zswap_state\"; fi",
        "sudo restorecon -RF /etc/systemd/system /etc/bc250-control-center /var/swap 2>/dev/null || true",
        "echo 'BC250_RESULT status=ok component=memory_tuning code=0 message=boot\\ configuration\\ prepared'",
        "echo 'BC250_REBOOT_REQUIRED=1'",
        "echo '== Finished: reboot required =='",
        "echo 'Reboot once, then open Prepare BC250 system again to verify the active zswap, swapfile and TTM state.'",
    ))
    return "\n".join(lines)
