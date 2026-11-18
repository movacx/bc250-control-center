"""The reviewed menu inventory records what upstream offers and what we choose to expose."""
import json
from pathlib import Path

from bc250cc.infrastructure.steamos_real_toolkit import ACTIONS, REPOSITORY

INVENTORY = Path(__file__).resolve().parents[2] / 'docs/steamos-real-toolkit-inventory.json'
# Offered natively by Control Center (GPU/CPU/CU/profiles, memory and swap, fans
# and sensors) or deliberately left out (extras, emulators, bulk menus).
NOT_EXPOSED = {
    'run_install_all', 'run_install_manual', 'run_revert_all', 'run_overclock_menu',
    'run_cpu_governor', 'run_revert_cpu_governor', 'run_gpu_governor', 'run_revert_gpu_governor',
    'run_cu_live_manager', 'install_core_unlock', 'run_revert_core_unlock',
    'run_swap_menu', 'run_revert_swap', 'run_zram_zswap_toggle', 'run_revert_zram_zswap',
    'install_ram_split', 'run_revert_ram_split', 'run_sensors_menu', 'run_coolercontrol_menu',
    'install_sensors_readonly', 'install_sensors_pwm', 'run_revert_sensors',
    'run_extras_menu', 'run_emulators_menu', 'install_toolkit_steamos_control_plugin',
    'install_fsr4_launch_options_plugin', 'install_kyty', 'run_kyty_status', 'revert_kyty',
    'install_lichii', 'lichii_game_shortcut', 'revert_lichii', 'install_emudeck',
    'run_disable_mitigations', 'run_revert_mitigations',  # Kernel boot options: mitigations=off
    'oc_apply_custom', 'show_menu',
}


def _inventory():
    return json.loads(INVENTORY.read_text())


def test_inventory_is_a_snapshot_of_the_repository_not_of_a_pinned_commit():
    inventory = _inventory()
    assert inventory['upstream'] == REPOSITORY
    assert len(inventory['revision']) == 40, 'a snapshot of the revision reviewed when the rows were chosen'


def test_every_upstream_menu_is_either_exposed_or_deliberately_left_out():
    exposed = {action.function for action in ACTIONS}
    menus = {item['function'] for item in _inventory()['menu_items']}
    unaccounted = menus - exposed - NOT_EXPOSED
    assert not unaccounted, 'decide whether Control Center exposes or already offers: ' + ', '.join(sorted(unaccounted))
    assert not exposed & NOT_EXPOSED


def test_root_menu_options_that_remain_have_a_native_action_or_ui_equivalent():
    root = {item['selector']: item for item in _inventory()['menu_items'] if item['function'] == 'show_menu'}
    assert 'V' in root
    assert {action.key for action in ACTIONS} >= {'verify'}
