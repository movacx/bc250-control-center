"""Exercise the 3.x protocol with a local fake, never upstream's bridge."""
import json
from pathlib import Path

import pytest

from bc250cc.infrastructure import helixsr as h


@pytest.fixture
def release(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    directory = root / '3.3.0'
    (directory / 'setup').mkdir(parents=True)
    (directory / 'helixsr-scaler').mkdir()
    (directory / 'helixsr-scaler' / 'OptiScaler.dll').write_bytes(b'HelixSR Scaler v2.3.0\0')
    game = tmp_path / 'game'
    game.mkdir()
    (game / 'game.exe').touch()
    script = directory / h.HELIXSR_BRIDGE
    script.write_text('''import json, sys
from pathlib import Path
args = sys.argv[2:]
root = Path(sys.argv[1])
(root / "calls").open("a").write(json.dumps(args) + "\\n")
cmd = args[0]
if cmd == "status":
 print(json.dumps(dict(ok=True, network_ready=False, hlx_ready=True, fg_available=False, k_available=True)))
elif cmd == "games":
 print(json.dumps(dict(ok=True, games=[])))
else:
 way = args[args.index("--way") + 1] if "--way" in args else "fsr"
 print(json.dumps(dict(ok=True, game=dict(installed=way, version="3.3.0", previous=None))))
''')
    monkeypatch.setattr(h, 'helixsr_root', lambda: root)
    monkeypatch.setattr(h, 'helixsr_directory', lambda: directory)
    monkeypatch.setattr(h, '_game', lambda appid: {'appid': appid, 'name': 'Game', 'path': str(game)})
    monkeypatch.setattr(h, '_refuse_running', lambda folder: None)
    monkeypatch.setattr(h, '_refuse_other_helixsr', lambda appid, folder: None)
    return directory, game


def test_fsr_ready_without_network_and_lifecycle(release):
    directory, game = release
    with pytest.raises(h.ActionNeeded):
        h.install_helixsr_bridge('1', 'scaler')
    record = h.install_helixsr_bridge('1', 'fsr')
    assert record['way'] == 'fsr'
    assert h._bridge_records()['1']['folder'] == str(game)
    h.rollback_helixsr_bridge('1')
    h.remove_helixsr_bridge('1')
    assert not h._bridge_records()
    calls = [json.loads(line) for line in (directory / 'calls').read_text().splitlines()]
    assert [c[0] for c in calls] == ['status', 'status', 'install', 'rollback', 'remove']


def test_scaler_version_and_options(release):
    directory, _ = release
    assert h._bundled_scaler_version(directory) == '2.3.0'
    # 3.3's setup knows --vulkan; older 3.x setups do not (R-84a7093e).
    (directory / h.HELIXSR_SETUP).write_text('# --dlss --preset-k --vulkan --rebuild\n')
    command = h.build_helixsr_network_command(options=('preset_k', 'vulkan', 'rebuild'))
    assert '--preset-k --vulkan --rebuild' in command
    with pytest.raises(ValueError):
        h.build_helixsr_network_command(options=('invalid',))


def test_scaler_install_passes_detected_version_and_switches(release):
    directory, _ = release
    script = directory / h.HELIXSR_BRIDGE
    script.write_text(script.read_text().replace('network_ready=False', 'network_ready=True'))
    h.install_helixsr_bridge('1', 'fsr')
    h.install_helixsr_bridge('1', 'scaler')
    calls = [json.loads(line) for line in (directory / 'calls').read_text().splitlines()]
    install = calls[-1]
    assert install[install.index('--scaler-version') + 1] == '2.3.0'
    assert h._bridge_records()['1']['way'] == 'scaler'
    assert h._bridge_records()['1']['previous_version'] == ''


def test_failed_bridge_does_not_create_record(release):
    directory, _ = release
    script = directory / h.HELIXSR_BRIDGE
    script.write_text(script.read_text().replace('print(json.dumps(dict(ok=True, game=', 'print(json.dumps(dict(ok=False, game='))
    with pytest.raises(RuntimeError):
        h.install_helixsr_bridge('1', 'fsr')
    assert h._bridge_records() == {}


@pytest.mark.parametrize("record_fails", [False, True])
def test_native_migration_restores_original_before_bridge_install(release, monkeypatch, record_fails):
    directory, game = release
    target = game / 'amd_fidelityfx_dx12.dll'
    backup = game / 'original.dll'
    target.write_bytes(b'old helixsr')
    backup.write_bytes(b'original')
    h._write_json(h._records_path(), {'1': {'name': 'Game', 'install': str(game), 'files': [{'path': str(target), 'backup': str(backup)}]}})
    monkeypatch.setattr(h, '_is_helixsr', lambda path, *args: Path(path).read_bytes() == b'old helixsr' if Path(path).is_file() else False)
    script = directory / h.HELIXSR_BRIDGE
    script.write_text(script.read_text().replace(
        'print(json.dumps(dict(ok=True, games=[])))',
        f'print(json.dumps(dict(ok=True, games=[dict(folder={str(game)!r}, ways=["scaler", "fsr"])])))'))
    script.write_text(script.read_text().replace('cmd = args[0]', 'cmd = args[0]\nif cmd == "install":\n assert (Path(args[args.index("--game") + 1]) / "amd_fidelityfx_dx12.dll").read_bytes() == b"original"'))
    if record_fails:
        def fail_to_save(*args):
            raise OSError("simulated write failure")

        monkeypatch.setattr(h, "_bridge_save", fail_to_save)
        with pytest.raises(OSError, match="simulated write failure"):
            h.install_helixsr_bridge('1', 'fsr')
        assert target.read_bytes() == b'old helixsr'
        assert backup.read_bytes() == b'original'
        assert '1' in h._records()
        return
    h.install_helixsr_bridge('1', 'fsr')
    assert target.read_bytes() == b'original'
    assert not h._records()
    assert h._bridge_records()['1']['way'] == 'fsr'


def test_status_failure_is_reported(release, monkeypatch):
    directory, _ = release
    info = h.helixsr_release()
    (directory / h.HELIXSR_MARKER).write_text(info['sha256'])
    (directory / h.HELIXSR_SETUP).touch()
    monkeypatch.setattr(h, '_is_helixsr', lambda *args: True)
    monkeypatch.setattr(h, 'helixsr_games', lambda **kwargs: [])
    monkeypatch.setattr(h, '_recorded_scaler_rows', lambda: [])
    monkeypatch.setattr(h, '_bridge_game_rows', lambda status: [])
    monkeypatch.setattr(h, '_run_bridge', lambda *args: (_ for _ in ()).throw(RuntimeError('bridge unavailable')))
    state = h.helixsr_state()
    assert state['status_error'] == 'bridge unavailable'
    assert not state['ready']['network']


def test_settings_only_send_wave_size_to_scaler_games(release):
    directory, game = release
    h._write_json(h._bridge_records_path(), {
        '1': {'name': 'Scaler', 'folder': str(game), 'way': 'scaler'},
        '2': {'name': 'FSR', 'folder': str(game), 'way': 'fsr'},
    })
    result = h.save_helixsr_settings({'Scaler:HelixSR.WaveSize': '32'})
    calls = [json.loads(line) for line in (directory / 'calls').read_text().splitlines()]
    settings = [call for call in calls if call[0] == 'settings-set']
    assert len(settings) == 1
    assert json.loads(settings[0][settings[0].index('--values') + 1]) == {'HelixSR.WaveSize': '32'}
    assert result['games'] == 1


def test_record_save_failure_reports_bridge_success(release, monkeypatch):
    directory, game = release
    monkeypatch.setattr(h, '_bridge_save', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(RuntimeError, match='Bridge installed HelixSR.*record could not be saved'):
        h.install_helixsr_bridge('1', 'fsr')
    assert json.loads((directory / 'calls').read_text().splitlines()[-1])[0] == 'install'
    assert not h._bridge_records()


def test_update_all_counts_each_bridge_game_once(release, monkeypatch):
    rows = [dict(appid='1', name='Game', managed_by='bridge', outdated=True, installed_way='fsr'),
            dict(appid='2', name='Current', managed_by='bridge', outdated=False, installed_way='scaler'),
            dict(appid='3', name='Legacy', managed_by='app-2x', outdated=True, installed_way=None)]
    monkeypatch.setattr(h, 'helixsr_state', lambda: dict(layout='3', status_error='', bridge_games=rows, version='3.3.0'))
    calls = []
    monkeypatch.setattr(h, 'install_helixsr_bridge', lambda appid, way: calls.append((appid, way)))
    assert h.update_all_helixsr_games()['updated'] == ['Game', 'Legacy']
    assert calls == [('1', 'fsr'), ('3', 'fsr')]


def test_scaler_under_another_name_gets_steams_dll_override(release, monkeypatch):
    directory, game = release
    script = directory / h.HELIXSR_BRIDGE
    script.write_text(script.read_text().replace('network_ready=False', 'network_ready=True').replace(
        'game=dict(installed=way, version="3.3.0", previous=None)',
        'game=dict(installed=way, version="3.3.0", previous=None, scaler_dll="winmm.dll", '
        'launch_options=\'WINEDLLOVERRIDES="winmm=n,b" %command%\')'))
    overrides = []
    monkeypatch.setattr(h, 'add_dll_override', lambda appid, dll: overrides.append((appid, dll)))
    result = h.install_helixsr_bridge('1', 'scaler')
    assert overrides == [('1', 'winmm')]
    assert result['launch_option_added'] and not result['launch_option_error']
    # HLX FSR 4 needs no launch option.
    overrides.clear()
    h.install_helixsr_bridge('1', 'fsr')
    assert overrides == []


def test_a_never_picked_release_stays_the_installed_one(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    (root / '2.0.0').mkdir(parents=True)
    (root / '2.0.0' / h.HELIXSR_MARKER).write_text('x')
    monkeypatch.setattr(h, 'helixsr_root', lambda: root)
    # 2.0.0 is installed and nothing was picked: it stays, 3.3.0 is the update.
    assert h.helixsr_release()['tag'] == 'v2.0.0'
    assert h._newer_release(h.helixsr_release())['tag'] == 'v3.3.0'
    h.select_helixsr_release('v3.3.0')
    assert h.helixsr_release()['tag'] == 'v3.3.0'


def test_fresh_install_defaults_to_the_newest_reviewed(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'helixsr_root', lambda: tmp_path / 'empty')
    assert h.helixsr_release()['tag'] == h.HELIXSR_TAG == 'v3.3.0'


def test_remove_reaches_legacy_and_unrecorded_games(release, monkeypatch):
    directory, game = release
    removed = []
    monkeypatch.setattr(h, 'remove_helixsr_game', lambda appid: removed.append(('native', appid)) or {'game': 'N'})
    monkeypatch.setattr(h, 'remove_helixsr_scaler', lambda appid: removed.append(('scaler', appid)) or {'game': 'S'})
    h._write_json(h._records_path(), {'10': {'name': 'N', 'files': []}})
    h._write_json(h._scaler_records_path(), {'11': {'name': 'S'}})
    h.remove_helixsr_bridge('10')
    h.remove_helixsr_bridge('11')
    assert removed == [('native', '10'), ('scaler', '11')]
    # Put in by HelixSR's setup or Desktop: no record, the bridge by folder.
    h.remove_helixsr_bridge('12')
    calls = [json.loads(line) for line in (directory / 'calls').read_text().splitlines()]
    assert calls[-1] == ['remove', '--game', str(game)]


def test_saved_wave_size_reaches_a_new_scaler_game(release):
    directory, game = release
    script = directory / h.HELIXSR_BRIDGE
    # As upstream's bridge declares it (the app reads these constants from it).
    script.write_text("SCALER_SETTINGS = {'HelixSR.WaveSize': ('auto', '64', '32'), 'HelixSR.QuickFlow': ('off', 'fast')}\n"
                      "SCALER_DEFAULTS = {'HelixSR.WaveSize': 'auto', 'HelixSR.QuickFlow': 'off'}\n"
                      + script.read_text().replace('network_ready=False', 'network_ready=True'))
    h._write_json(h._settings_path(), {'Scaler:HelixSR.WaveSize': '32'})
    h.install_helixsr_bridge('1', 'scaler')
    calls = [json.loads(line) for line in (directory / 'calls').read_text().splitlines()]
    assert calls[-1][0] == 'settings-set'
    assert json.loads(calls[-1][calls[-1].index('--values') + 1]) == {'HelixSR.WaveSize': '32'}


def test_games_scan_is_cached_and_forgotten_after_a_change(release, monkeypatch):
    directory, game = release
    monkeypatch.setattr(h, 'installed_steam_game_folders', lambda home=None: [{'appid': '1', 'name': 'Game', 'path': str(game)}])
    h._forget_bridge_games()
    h._bridge_game_rows({})
    h._bridge_game_rows({})
    calls = [json.loads(line)[0] for line in (directory / 'calls').read_text().splitlines()]
    assert calls.count('games') == 1
    h.install_helixsr_bridge('1', 'fsr')
    h._bridge_game_rows({})
    calls = [json.loads(line)[0] for line in (directory / 'calls').read_text().splitlines()]
    assert calls.count('games') == 2


def test_legacy_games_are_always_outdated(release, monkeypatch):
    directory, game = release
    monkeypatch.setattr(h, 'installed_steam_game_folders', lambda home=None: [{'appid': '1', 'name': 'Game', 'path': str(game)}])
    h._write_json(h._records_path(), {'1': {'name': 'Game', 'install': str(game), 'files': []}})
    h._forget_bridge_games()
    row = next(row for row in h._bridge_game_rows({}) if row['appid'] == '1')
    assert row['managed_by'] == 'app-2x' and row['outdated'] and row['legacy_way'] == 'fsr'


def test_upgrade_picks_the_release_only_once_it_is_installed(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    (root / '2.0.0').mkdir(parents=True)
    (root / '2.0.0' / h.HELIXSR_MARKER).write_text('x')
    monkeypatch.setattr(h, 'helixsr_root', lambda: root)
    command = h.build_helixsr_upgrade_command('v3.3.0')
    # Nothing picked yet on disk: a cancelled install keeps 2.0.0 in use.
    assert not h._selection_path().exists()
    assert h.helixsr_release()['tag'] == 'v2.0.0'
    assert 'HelixSR-3.3.0.zip' in command
    placed = command.index('mv -- "$bc250_stage"')
    pick = command.index(str(h._selection_path()))
    old_removed = command.index('Removing the HelixSR')
    network = command.index('Building HelixSR')
    # Picked once the new release is in place, before the old one is removed.
    assert placed < pick < old_removed < network


def test_upgrade_restores_an_earlier_pick(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    root.mkdir()
    monkeypatch.setattr(h, 'helixsr_root', lambda: root)
    h.select_helixsr_release('v2.0.0')
    before = h._selection_path().read_bytes()
    h.build_helixsr_upgrade_command('v3.3.0')
    assert h._selection_path().read_bytes() == before


def test_steam_shortcuts_reach_the_bridge_scan(release, monkeypatch):
    directory, game = release
    monkeypatch.setattr(h, 'installed_steam_game_folders', lambda home=None: [])
    monkeypatch.setattr(h, 'steam_shortcut_game_folders', lambda home=None: [
        {'appid': 'Shortcut_1', 'name': 'Shortcut', 'path': str(game)}])
    h._forget_bridge_games()
    rows = h._bridge_game_rows({})
    assert [row['appid'] for row in rows] == ['Shortcut_1']
    calls = [json.loads(line) for line in (directory / 'calls').read_text().splitlines()]
    assert calls[-1] == ['games', '--folder', str(game)]


def test_bridge_install_refusal_restores_old_integration_and_backup(release, monkeypatch):
    directory, game = release
    target = game / 'amd_fidelityfx_dx12.dll'
    backup = game / 'original.dll'
    target.write_bytes(b'old helixsr')
    backup.write_bytes(b'original')
    h._write_json(h._records_path(), {'1': {'name': 'Game', 'install': str(game), 'files': [{'path': str(target), 'backup': str(backup)}]}})
    monkeypatch.setattr(h, '_is_helixsr', lambda path, *args: Path(path).read_bytes() == b'old helixsr' if Path(path).is_file() else False)
    script = directory / h.HELIXSR_BRIDGE
    script.write_text(script.read_text().replace(
        'print(json.dumps(dict(ok=True, games=[])))',
        f'print(json.dumps(dict(ok=True, games=[dict(folder={str(game)!r}, ways=["scaler", "fsr"])])))'))
    script.write_text(script.read_text().replace(
        'cmd = args[0]',
        'cmd = args[0]\nif cmd == "install":\n print(json.dumps(dict(ok=False, error="Game has anti-cheat (EasyAntiCheat): only with --anticheat-ok yes")))\n sys.exit(0)'))
    with pytest.raises(RuntimeError, match='anti-cheat'):
        h.install_helixsr_bridge('1', 'fsr')
    assert target.read_bytes() == b'old helixsr'
    assert backup.read_bytes() == b'original'
    assert h._bridge_records() == {}
    assert '1' in h._records()


def test_a_refused_way_keeps_the_helixsr2_install(release, monkeypatch):
    """The bridge is asked before HelixSR 2's files leave the game."""
    directory, game = release
    script = directory / h.HELIXSR_BRIDGE
    script.write_text(script.read_text().replace(
        'print(json.dumps(dict(ok=True, games=[])))',
        f'print(json.dumps(dict(ok=True, games=[dict(folder={str(game)!r}, ways=["scaler"])])))'))
    h._write_json(h._records_path(), {'1': {'name': 'Game', 'install': str(game), 'files': []}})
    monkeypatch.setattr(h, '_record_state', lambda record: 'installed')
    removed = []
    monkeypatch.setattr(h, 'remove_helixsr_game', lambda appid: removed.append(appid) or {})
    with pytest.raises(h.ActionNeeded, match="current HelixSR was kept"):
        h.install_helixsr_bridge('1', 'fsr')
    assert removed == []


def test_wine_that_cannot_run_is_reported_not_used():
    """R-a45942d4: Proton's wine passed test -x in Toolbx and could not start."""
    script = h._wine_check()
    assert '--version' in script
    assert "cannot be executed here" in script



def test_a_failed_bridge_scan_keeps_the_helixsr2_install(release, monkeypatch):
    """Only a yes from the bridge lets HelixSR 2's files go."""
    directory, game = release
    h._write_json(h._records_path(), {'1': {'name': 'Game', 'install': str(game), 'files': []}})
    monkeypatch.setattr(h, '_record_state', lambda record: 'installed')
    removed = []
    monkeypatch.setattr(h, 'remove_helixsr_game', lambda appid: removed.append(appid) or {})
    with pytest.raises(h.ActionNeeded, match="current HelixSR was kept"):
        h.install_helixsr_bridge('1', 'fsr')  # the fake lists no game
    assert removed == []
