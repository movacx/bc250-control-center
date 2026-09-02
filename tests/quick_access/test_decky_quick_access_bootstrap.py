from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.decky_quick_access import (
    DECKY_OFFICIAL_INSTALLER_URL,
    DECKY_OFFICIAL_PRERELEASE_INSTALLER_URL,
    STEAM_RENAMED_INIT_API_BUILD,
    build_bazzite_decky_bootstrap_command,
    build_decky_bootstrap_command,
    build_plugin_install_command,
)
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


def test_decky_bootstrap_is_reviewable_after_gui_confirmation(tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    command = build_decky_bootstrap_command(installer)

    assert DECKY_OFFICIAL_INSTALLER_URL in command
    assert DECKY_OFFICIAL_PRERELEASE_INSTALLER_URL in command
    assert str(STEAM_RENAMED_INIT_API_BUILD) in command
    assert "decky_supports_renamed_init_api" in command
    assert "curl --fail --location --proto '=https' --tlsv1.2" in command
    assert "chmod 0700 \"$workspace/decky-install.sh\"" in command
    assert "sha256sum \"$workspace/decky-install.sh\"" in command
    assert "Approval was already confirmed in BC250 Control Center" in command
    assert 'sudo env UID=0 SUDO_USER="$decky_user" /usr/bin/bash' in command
    assert "read -r approval" not in command
    assert "| sh" not in command
    assert "test -d \"$HOME/homebrew/plugins\"" in command
    assert str(installer) in command


def test_plugin_repair_command_is_local_only(tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    command = build_plugin_install_command(installer)

    assert "Installing / repairing BC250 Quick Access" in command
    assert "curl" not in command
    assert "exec /usr/bin/bash" in command
    assert str(installer) in command


def test_bazzite_bootstrap_uses_distribution_native_ujust_path(tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    command = build_bazzite_decky_bootstrap_command(installer)

    assert "ujust setup-decky install" in command
    assert "ujust setup-decky status" in command
    assert 'test "${ID:-}" = bazzite' in command
    assert "--preflight-immutable-host" in command
    assert 'test -d "$HOME/homebrew/plugins"' in command
    assert 'test -x "$HOME/homebrew/services/PluginLoader"' in command
    assert "setup-decky recipe is unavailable" in command
    assert DECKY_OFFICIAL_INSTALLER_URL in command
    assert "curl --fail --location --proto '=https' --tlsv1.2" in command
    assert 'sudo env UID=0 SUDO_USER="$decky_user" /usr/bin/bash' in command


def test_immutable_preflight_runs_before_existing_decky_is_required():
    source = (Path(__file__).resolve().parents[2] / "scripts/install-decky-quick-access.sh").read_text(encoding="utf-8")

    preflight = source.index('if [[ "${1:-}" == "--preflight-immutable-host" ]]')
    decky_directory_check = source.index('if [[ ! -d "$PLUGIN_ROOT" || -L "$PLUGIN_ROOT" ]]')
    assert preflight < decky_directory_check


class _QuickAccessRepository(DependenciasRepository):
    def __init__(self, family):
        self.family = family
        self.opened = []
        self.estado_herramientas_cache = object()

    def _os_repository(self):
        return SimpleNamespace(info=SimpleNamespace(family=self.family))

    def _abrir_terminal(self, command, title):
        self.opened.append((command, title))
        return "terminal"


def test_repository_routes_missing_decky_to_explicit_bootstrap(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=False),
    )
    repository = _QuickAccessRepository("steamos")

    assert repository.preparar_quick_access_steamos(install_decky=True) == "terminal"
    command, title = repository.opened[0]
    assert title == "Game Mode Quick Access (Beta)"
    assert "Approval was already confirmed in BC250 Control Center" in command
    assert repository.estado_herramientas_cache is None


def test_repository_explicit_decky_action_updates_an_existing_loader(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=True),
    )
    repository = _QuickAccessRepository("steamos")

    repository.preparar_quick_access_steamos(install_decky=True)
    command, _title = repository.opened[0]
    assert "Game Mode Quick Access Beta" in command
    assert DECKY_OFFICIAL_INSTALLER_URL in command
    assert DECKY_OFFICIAL_PRERELEASE_INSTALLER_URL in command


def test_repository_accepts_bazzite_when_decky_capability_is_present(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=True),
    )
    repository = _QuickAccessRepository("bazzite")

    assert repository.preparar_quick_access_steamos(install_decky=False) == "terminal"
    assert repository.opened[0][1] == "Game Mode Quick Access (Beta)"


def test_repository_routes_missing_decky_to_bazzite_native_setup(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=False),
    )
    repository = _QuickAccessRepository("bazzite")

    assert repository.preparar_quick_access_steamos(install_decky=True) == "terminal"
    command, _title = repository.opened[0]
    assert "ujust setup-decky install" in command
    assert DECKY_OFFICIAL_INSTALLER_URL in command


def test_repository_accepts_cachyos_handheld_when_decky_capability_is_present(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=True),
    )
    repository = _QuickAccessRepository("cachyos")

    assert repository.preparar_quick_access_steamos(install_decky=False) == "terminal"
    assert repository.opened[0][1] == "Game Mode Quick Access (Beta)"


def test_repository_routes_missing_decky_on_cachyos_to_official_bootstrap(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=False, init_system="systemd"),
    )
    repository = _QuickAccessRepository("cachyos")

    assert repository.preparar_quick_access_steamos(install_decky=True) == "terminal"
    command, _title = repository.opened[0]
    assert DECKY_OFFICIAL_INSTALLER_URL in command
    assert "ujust setup-decky" not in command


def test_repository_routes_missing_decky_on_generic_systemd_to_official_bootstrap(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=False, init_system="systemd"),
    )
    repository = _QuickAccessRepository("arch")

    assert repository.preparar_quick_access_steamos(install_decky=True) == "terminal"
    command, _title = repository.opened[0]
    assert DECKY_OFFICIAL_INSTALLER_URL in command
    assert "ujust setup-decky" not in command


def test_repository_requires_existing_decky_off_systemd(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=False, init_system="openrc"),
    )
    repository = _QuickAccessRepository("arch")

    with pytest.raises(RuntimeError, match="unavailable on this init system"):
        repository.preparar_quick_access_steamos(install_decky=False)


def test_repository_accepts_existing_decky_on_other_systemd_distribution(monkeypatch, tmp_path):
    installer = tmp_path / "install-decky-quick-access.sh"
    installer.touch(mode=0o755)
    monkeypatch.setattr(
        _QuickAccessRepository,
        "_quick_access_installer_path",
        staticmethod(lambda: installer),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.quick_access_inventory",
        lambda **_kwargs: SimpleNamespace(decky_detected=True),
    )
    repository = _QuickAccessRepository("arch")

    assert repository.preparar_quick_access_steamos(install_decky=False) == "terminal"
