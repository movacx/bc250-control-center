"""SteamOS plugin inspection follows the actual upstream artifact layout."""
import json

from bc250cc.infrastructure.external_tools.quick_access_inventory import (
    real_toolkit_inventory,
)


def test_toolkit_plugin_does_not_require_the_other_plugins_helper(tmp_path):
    plugin = tmp_path / 'homebrew/plugins/Toolkit SteamOS Control'
    for name in ['main.py', 'fan_manager.py', 'dist/index.js']:
        path = plugin / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# fixture, never executed')
    (plugin / 'plugin.json').write_text(json.dumps({'name': 'Toolkit SteamOS Control'}))
    result = real_toolkit_inventory(home=tmp_path, environ={})
    assert result.ready and result.plugin_present
    assert result.provider == 'steamos-real-toolkit'
    assert result.protocol_compatible is None and not result.helper_required
    (plugin / 'fan_manager.py').unlink()
    assert not real_toolkit_inventory(home=tmp_path, environ={}).ready


def test_old_plugin_is_not_misidentified_as_real_toolkit(tmp_path):
    old = tmp_path / 'homebrew/plugins/bc250-quick-access'
    old.mkdir(parents=True)
    (old / 'plugin.json').write_text('{}')
    state = real_toolkit_inventory(home=tmp_path, environ={})
    assert not state.plugin_present and not state.ready


def test_symlink_plugin_payload_is_not_reported_ready(tmp_path):
    root = tmp_path / 'homebrew/plugins'
    root.mkdir(parents=True)
    (root / 'Toolkit SteamOS Control').symlink_to(tmp_path / 'other', target_is_directory=True)
    assert not real_toolkit_inventory(home=tmp_path, environ={}).ready
