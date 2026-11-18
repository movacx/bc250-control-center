"""Decky fan commands fail before configuration or PWM writes on native conflict."""
import asyncio
import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import steamos_real_toolkit_decky as adapter


def _adapt(monkeypatch, name, source):
    data = source.encode()
    monkeypatch.setitem(adapter._DIGESTS, name, hashlib.sha256(data).hexdigest())
    return adapter.adapt_decky_payload(name, data)


@pytest.mark.parametrize('operation', ['set_fan_mode', 'save_profile', 'select_profile', 'delete_profile'])
def test_native_fan_conflict_prevents_decky_configuration_changes(monkeypatch, operation):
    methods = '\n'.join('    async def ' + name + '(self):\n        self.changed = True\n'
                        for name in ('set_fan_mode', 'save_profile', 'select_profile', 'delete_profile'))
    namespace = {}
    exec(_adapt(monkeypatch, 'main.py', 'class Plugin:\n' + methods), namespace)
    plugin = namespace['Plugin']()
    calls = []
    async def run(*args):
        calls.append(args)
        raise RuntimeError('native fan controller owns this hardware')
    plugin._run = run
    with pytest.raises(RuntimeError, match='native fan controller'):
        asyncio.run(getattr(plugin, operation)())
    assert not hasattr(plugin, 'changed')
    assert calls == [adapter._CHECK]


def test_native_fan_conflict_prevents_pwm_write(monkeypatch, tmp_path):
    pwm = tmp_path / 'pwm1'
    pwm.write_text('123\n')
    source = 'def write_fan(percent, automatic=False):\n    pwm.write_text(str(percent))\n'
    namespace = {'pwm': pwm}
    exec(_adapt(monkeypatch, 'fan_manager.py', source), namespace)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=79, stderr='Native service present')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='Native service present'):
        namespace['write_fan'](50)
    assert pwm.read_text() == '123\n'
    assert calls == [(adapter._CHECK,)]


def test_no_native_conflict_preserves_the_original_pwm_operation(monkeypatch, tmp_path):
    pwm = tmp_path / 'pwm1'
    namespace = {'pwm': pwm}
    exec(_adapt(monkeypatch, 'fan_manager.py',
                'def write_fan(percent, automatic=False):\n    pwm.write_text(str(percent))\n'), namespace)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    namespace['write_fan'](60)
    assert pwm.read_text() == '60'


def test_unreviewed_plugin_source_cannot_be_adapted():
    with pytest.raises(ValueError, match='differs from reviewed source'):
        adapter.adapt_decky_payload('main.py', b'changed source')
