"""Native Game Mode and Decky stop before PWM writes by a second controller."""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _helper(name):
    loader = SourceFileLoader(name.replace('-', '_') + '_coexistence', str(ROOT / 'privileged/helpers' / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', ['bc250-fan-pwm-helper', 'bc250-quick-access-helper', 'bc250-steamos-game-helper'])
def test_runtime_observation_distinguishes_a_stopped_service_from_a_live_controller(name, tmp_path):
    module = _helper(name)
    module.TOOLKIT_FAN_CGROUP = tmp_path / 'cgroup.events'
    assert not module.toolkit_fan_running()
    module.TOOLKIT_FAN_CGROUP.write_text('populated 0\nfrozen 0\n')
    assert not module.toolkit_fan_running()
    module.TOOLKIT_FAN_CGROUP.write_text('populated 1\nfrozen 0\n')
    assert module.toolkit_fan_running()


@pytest.mark.parametrize('action,args', [('fan-auto', ['2']), ('fan-system', ['balanced']),
                                        ('fan-channel', ['2', '80'])])
def test_native_decky_refuses_takeover_before_loading_any_fan_policy(tmp_path, monkeypatch, action, args):
    module = _helper('bc250-quick-access-helper')
    module.SYSTEM_FAN_EXTERNAL = tmp_path / 'absent-marker'
    module.TOOLKIT_FAN_CGROUP = tmp_path / 'cgroup.events'
    module.TOOLKIT_FAN_CGROUP.write_text('populated 1\n')
    monkeypatch.setattr(module, 'require_runtime', lambda: None)
    monkeypatch.setattr(module, 'load_contract', lambda: None)
    monkeypatch.setattr(module, 'fan_auto', lambda *args: pytest.fail('Must not write PWM'))
    monkeypatch.setattr(module, 'fan_system_preset', lambda *args: pytest.fail('Must not apply a preset'))
    assert module.main(['helper', action, *args]) == 58


@pytest.mark.parametrize('action', ['fan-pwm', 'fan-daemon-pwm', 'fan-pwm-auto'])
def test_game_mode_refuses_pwm_writes_when_toolkit_runs_first(tmp_path, monkeypatch, action):
    module = _helper('bc250-steamos-game-helper')
    module.FAN_EXTERNAL_FILE = tmp_path / 'absent-marker'
    module.TOOLKIT_FAN_CGROUP = tmp_path / 'cgroup.events'
    module.TOOLKIT_FAN_CGROUP.write_text('populated 1\n')
    monkeypatch.setattr(module, 'require_runtime', lambda *args: 0)
    monkeypatch.setattr(module, 'require_fan_daemon_runtime', lambda *args: 0)
    monkeypatch.setattr(module, 'require_persistent_action', lambda *args: 0)
    monkeypatch.setattr(module, 'action_fan_pwm', lambda *args: pytest.fail('Must not write PWM'))
    monkeypatch.setattr(module, 'action_fan_pwm_auto', lambda *args: pytest.fail('Must not write automatic mode'))
    assert module.main(['helper', action, '2', '128']) == 58
