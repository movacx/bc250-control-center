"""The reviewed menu inventory must stay reachable through the native index."""
import json
from pathlib import Path

from bc250cc.infrastructure.steamos_real_toolkit import (
    ACTIONS,
    ENTRYPOINT_SHA256,
    REPOSITORY,
    REVISION,
)


def test_every_reviewed_menu_has_an_explicit_native_entry_or_documented_parent():
    inventory = json.loads((Path(__file__).resolve().parents[2]
                            / 'docs/steamos-real-toolkit-inventory.json').read_text())
    assert inventory['upstream'] == REPOSITORY
    assert inventory['revision'] == REVISION
    assert inventory['start_sha256'] == ENTRYPOINT_SHA256
    native = {action.function for action in ACTIONS}
    # Custom CPU/GPU combinations are inside the profiles menu. Root options
    # are checked individually below; the manual menu is not their parent.
    parents = {'oc_apply_custom': 'run_overclock_menu'}
    menus = {item['function'] for item in inventory['menu_items']}
    assert menus - native - {'show_menu'} == parents.keys()
    assert set(parents.values()) <= native


def test_each_root_menu_option_has_a_native_action_or_non_privileged_ui_equivalent():
    inventory = json.loads((Path(__file__).resolve().parents[2]
                            / 'docs/steamos-real-toolkit-inventory.json').read_text())
    actions = {'1': 'install-all', '2': 'manual', '3': 'profiles', '4': 'revert-all',
               '5': 'extras', '6': 'emulators', 'V': 'verify'}
    # I: each component has Open upstream project; G: management's What's new
    # route; 0: close/return in native UI or the unchanged upstream submenu.
    ui = {'I': 'steamos_graphics_upstream', 'G': 'steamos_toolkit_changelog', '0': 'native-close'}
    root = {item['selector'] for item in inventory['menu_items'] if item['function'] == 'show_menu'}
    assert root == actions.keys() | ui.keys()
    assert set(actions.values()) <= {action.key for action in ACTIONS}
