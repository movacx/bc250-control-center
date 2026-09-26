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
    assert "must remain free after creating swap" in command
    assert "reserve_bytes=$((filesystem_bytes / 20))" in command
    # The pool is tuned the same way the mutable adapter tunes it.
    assert "--append-if-missing=zswap.compressor=lz4" in command
    assert "--append-if-missing=zswap.max_pool_percent=25" in command
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


def test_restore_captures_and_returns_the_whole_zswap_argument_family():
    """A restore must put back tuning arguments the image had, not only enabled=."""
    from bc250cc.infrastructure.bazzite_memory_tuning import ZSWAP_KARG_VALID

    command = build_bazzite_memory_tuning_command("current", 0)
    assert "zswap\\.(enabled|compressor|max_pool_percent)=" in command
    script = (
        'for a in zswap.compressor=zstd "zswap.compressor=lz4;reboot"; do '
        f'if [[ "$a" =~ {ZSWAP_KARG_VALID} ]]; then echo "ok $a"; else echo "no $a"; fi; done'
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.stdout.splitlines() == ["ok zswap.compressor=zstd", "no zswap.compressor=lz4;reboot"]


def test_kernel_default_ttm_is_selectable_on_bazzite_after_a_generic_refresh(qtbot):
    """GitHub issue #14: the option stayed greyed out until a restart.

    A refresh that ran before the inventory had recognised Bazzite went
    through the generic adapter, which greys "Kernel default" out until it has
    a TTM change of its own to undo. The Bazzite refresh after it reused the
    same item list and never enabled the entry again.
    """
    from frontends.desktop.components.system_setup_controls import (
        update_memory_controls,
    )
    from frontends.desktop.pages.dashboard import DashboardPage

    page = DashboardPage(object())
    qtbot.addWidget(page)
    owner = next(
        widget for widget in (page, *page.findChildren(object))
        if hasattr(widget, "ttm_limit_combo") and hasattr(widget, "memory_policy_combo")
    )
    generic = {"os_family": "arch", "system_setup": {"helper_available": True, "memory": {
        "supported": True, "policies": ["preserve"], "ttm_available": True,
        "ttm_restore_available": False,
    }}}
    update_memory_controls(owner, generic)
    assert not owner.ttm_limit_combo.model().item(1).isEnabled()

    update_memory_controls(owner, {"os_family": "bazzite", "memory_runtime": {"physical_ram_bytes": 16 * 1024 ** 3}})

    assert owner.ttm_limit_combo.itemData(1) == -1
    assert owner.ttm_limit_combo.model().item(1).isEnabled()
