import subprocess

import pytest

from bc250cc.infrastructure.bazzite_memory_tuning import (
    build_bazzite_memory_tuning_command,
)


def test_zswap_policy_builds_a_btrfs_backed_reboot_transaction():
    command = build_bazzite_memory_tuning_command("zswap-16", 8)

    assert "btrfs filesystem mkswapfile" in command
    assert "systemd-escape --path --suffix=swap" in command
    assert 'swap_unit_path="/etc/systemd/system/$swap_unit"' in command
    assert 'enable --now "$swap_unit"' in command
    assert "Options=pri=-2" in command
    assert "if sudo test -e \"$swap_path\"; then" in command
    assert "at least 1 GiB must remain" in command
    assert "refusing a symlink or non-regular swapfile" in command
    assert "unclaimed swapfile" in command
    assert "zswap.enabled=1" in command
    assert "getconf PAGESIZE" in command
    assert "ttm.pages_limit=$bc250_ttm_pages" in command
    assert "selected TTM target exceeds visible physical RAM" in command
    assert "ttm-kargs.original" in command
    assert "zswap-kargs.original" in command
    assert "zram remains active for this session" in command
    assert subprocess.run(["bash", "-n", "-c", command]).returncode == 0


def test_preserve_policy_does_not_change_zswap_when_only_ttm_is_requested():
    command = build_bazzite_memory_tuning_command("preserve", 12)

    assert "zswap.enabled=1" not in command
    assert "^zswap\\.enabled=" not in command
    assert "bc250_ttm_bytes=$((12 * 1024 * 1024 * 1024))" in command


def test_restore_uses_only_the_exact_ttm_state_owned_by_bc250():
    command = build_bazzite_memory_tuning_command("current", -1)

    assert 'if sudo test -f "$bc250_ttm_state"; then' in command
    assert "for bc250_arg in \"${bc250_original_ttm[@]}\"" in command
    assert "pre-existing TTM arguments were preserved" in command
    assert "ttm.pages_limit=$bc250_ttm_pages" not in command


def test_current_policy_restores_saved_zswap_and_preserves_foreign_state():
    command = build_bazzite_memory_tuning_command("current", 0)

    assert 'if sudo test -f "$bc250_zswap_state"; then' in command
    assert "${bc250_original_zswap[@]}" in command
    assert "pre-existing arguments were preserved" in command
    assert "foreign zram marker was preserved" in command
    assert "unsafe /var/swap directory" in command
    assert "unsafe swapfile; managed data was preserved" in command
    assert subprocess.run(["bash", "-n", "-c", command]).returncode == 0


@pytest.mark.parametrize("policy, ttm", [("zram", 8), ("zswap-16", 9), ("zswap-64", 8), ("preserve", -2)])
def test_memory_transaction_rejects_unreviewed_choices(policy, ttm):
    with pytest.raises(ValueError):
        build_bazzite_memory_tuning_command(policy, ttm)
