"""A Quick Access plugin already installed keeps working after an update.

The plugin lives in ~/homebrew/plugins and is only replaced when its owner
reinstalls it from Desktop Mode; the package update replaces the helper and
the shared contract under it. The plugin compares its own copies of a few
contract values with the installed contract (``_contract_disagreement``) and
refuses every action when one differs. 1.21.2 dropped 2048 MiB from the VRAM
presets, and every 1.21.0 and 1.21.1 plugin answered "Reinstall both from
Desktop Mode" to everything. The values below are what those releases'
``main.py`` compares, read from the tags.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bc250cc.shared import contract  # noqa: E402

PLUGIN = ROOT / "integrations" / "decky" / "bc250-quick-access"
INSTALLED_CONTRACT = ROOT / "privileged" / "lib" / "bc250_contract.py"

#: Per release: contract revision, helper protocol, CPU ladder (first, last,
#: count), CU modes and VRAM presets, as that release's plugin checks them.
RELEASED_PLUGINS = {
    "1.21.0": (1, 21, (3100, 4200, 23), (24, 26, 28, 30, 32, 34, 36, 38, 40),
               (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)),
    "1.21.1": (1, 21, (3100, 4200, 23), (24, 26, 28, 30, 32, 34, 36, 38, 40),
               (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)),
    "1.21.2": (1, 21, (3100, 4200, 23), (24, 26, 28, 30, 32, 34, 36, 38, 40),
               (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)),
    "1.21.3": (1, 21, (3100, 4200, 23), (24, 26, 28, 30, 32, 34, 36, 38, 40),
               (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)),
}


@pytest.mark.parametrize("release", sorted(RELEASED_PLUGINS))
def test_the_contract_still_agrees_with_an_installed_plugin(release):
    revision, protocol, ladder, cu_modes, vram = RELEASED_PLUGINS[release]
    cpu = contract.cpu_frequency_ladder()
    assert contract.CONTRACT_REVISION == revision
    assert contract.QUICK_ACCESS_PROTOCOL == protocol
    assert (cpu[0], cpu[-1], len(cpu)) == ladder
    assert contract.cu_targets() == cu_modes
    assert contract.VRAM_SIZE_PRESETS_MB == vram


def test_2048_mib_is_listed_for_old_plugins_but_never_offered():
    assert 2048 in contract.VRAM_SIZE_PRESETS_MB
    assert 2048 not in contract.vram_size_choices()
    assert set(contract.vram_size_choices()) == (
        set(contract.VRAM_SIZE_PRESETS_MB) - set(contract.VRAM_SIZE_BLOCKED_MB)
    )


class _RootOwned(type(Path())):
    """The installed contract is root-owned; a checkout's copy is not."""

    def lstat(self):
        real = os.lstat(self)
        return os.stat_result((
            stat.S_IFREG | 0o644, real.st_ino, real.st_dev, real.st_nlink, 0, 0,
            real.st_size, int(real.st_atime), int(real.st_mtime), int(real.st_ctime),
        ))

    def stat(self, **_kwargs):
        return self.lstat()


def test_this_plugin_agrees_with_the_contract_it_ships_with(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-settings-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    monkeypatch.syspath_prepend(str(PLUGIN))
    spec = importlib.util.spec_from_file_location("bc250_quick_access_agreement", PLUGIN / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CONTRACT_PATH", _RootOwned(INSTALLED_CONTRACT))

    assert module.Plugin._contract_disagreement() == ""


def test_the_plugin_refuses_a_blocked_size_even_though_it_is_listed(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-settings-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    monkeypatch.syspath_prepend(str(PLUGIN))
    spec = importlib.util.spec_from_file_location("bc250_quick_access_vram", PLUGIN / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin = module.Plugin()
    ran = []
    monkeypatch.setattr(plugin, "_run_single_operation", lambda *args, **_kwargs: ran.append(args))

    import asyncio

    result = asyncio.run(plugin.apply_vram_size(2048))

    assert result["ok"] is False and result["error"] == "Unsupported VRAM size."
    assert result["error_code"] == "QUICK_ACCESS_INVALID_REQUEST"
    assert ran == []
