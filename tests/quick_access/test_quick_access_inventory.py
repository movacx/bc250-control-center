from pathlib import Path

from bc250cc.infrastructure.external_tools.quick_access_inventory import (
    quick_access_inventory,
)
from bc250cc.platform.init.services import InitManagerState


def _root_owned(path: Path, *, executable: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("HELPER_PROTOCOL = 12\n", encoding="utf-8")
    path.chmod(0o755 if executable else 0o644)


def test_quick_access_inventory_requires_game_mode_family_and_existing_decky(tmp_path, monkeypatch):
    helper = tmp_path / "libexec" / "helper"
    _root_owned(helper, executable=True)
    # The test process is not root. Simulate only ownership evidence, keeping
    # every filesystem path local and read-only after setup.
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(module, "_protected_regular", lambda path, **_kwargs: path.is_file())
    monkeypatch.setattr(
        module,
        "detect_init_manager",
        lambda: InitManagerState("unknown", False, "test unknown init"),
    )

    unsupported = quick_access_inventory(
        os_family="arch", home=tmp_path / "home", environ={}, helper_path=helper,
    )
    assert unsupported.supported is False
    assert unsupported.ready is False
    assert "existing Decky Loader" in unsupported.next_action

    steamos = quick_access_inventory(
        os_family="steamos", home=tmp_path / "home", environ={}, helper_path=helper,
    )
    assert steamos.supported is True
    assert steamos.decky_detected is False
    assert steamos.ready is False
    assert "Install Decky" in steamos.next_action

    bazzite = quick_access_inventory(
        os_family="bazzite", home=tmp_path / "home", environ={}, helper_path=helper,
    )
    assert bazzite.supported is True
    assert bazzite.ready is False
    assert "Install Decky" in bazzite.next_action

    cachyos = quick_access_inventory(
        os_family="cachyos", home=tmp_path / "home", environ={}, helper_path=helper,
    )
    assert cachyos.supported is True
    assert cachyos.ready is False
    assert "Install Decky" in cachyos.next_action


def test_quick_access_inventory_offers_bootstrap_on_generic_systemd_independent_of_packages(tmp_path, monkeypatch):
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(
        module,
        "detect_init_manager",
        lambda: InitManagerState("systemd", True, "test systemd"),
    )

    for family in ("arch", "debian", "fedora", "unknown"):
        inventory = quick_access_inventory(
            os_family=family,
            home=tmp_path / family,
            environ={},
            helper_path=tmp_path / "helper",
        )
        assert inventory.supported is True
        assert inventory.controls_supported is True
        assert inventory.decky_detected is False
        assert inventory.next_action == "Install Decky + Quick Access (Beta)"


def test_quick_access_inventory_reports_ready_only_for_complete_safe_payload(tmp_path, monkeypatch):
    home = tmp_path / "home"
    root = home / "homebrew" / "plugins"
    plugin = root / "bc250-quick-access"
    for path in (plugin / "plugin.json", plugin / "package.json", plugin / "main.py", plugin / "dist" / "index.js"):
        _root_owned(path)
    _root_owned(plugin / "bc250cc/domain/gpu/profiles.py")
    helper = tmp_path / "libexec" / "helper"
    _root_owned(helper, executable=True)
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(module, "_protected_regular", lambda path, **_kwargs: path.is_file())

    inventory = quick_access_inventory(
        os_family="steamos", home=home, environ={}, helper_path=helper,
    )
    assert inventory.ready is True
    assert inventory.plugin_present is True
    assert inventory.plugin_safe is True
    assert inventory.helper_protected is True
    assert "ready" in inventory.next_action.lower()

    bazzite = quick_access_inventory(
        os_family="bazzite", home=home, environ={}, helper_path=helper,
    )
    assert bazzite.ready is True

    cachyos = quick_access_inventory(
        os_family="cachyos", home=home, environ={}, helper_path=helper,
    )
    assert cachyos.ready is True

    # A distro name does not block a real Decky capability. Control Center
    # installs only its local plugin and does not claim upstream Decky support.
    arch = quick_access_inventory(
        os_family="arch", home=home, environ={}, helper_path=helper,
    )
    assert arch.supported is True
    assert arch.decky_detected is True
    assert arch.ready is True

    helper.write_text("HELPER_PROTOCOL = 11\n", encoding="utf-8")
    outdated = quick_access_inventory(os_family="arch", home=home, environ={}, helper_path=helper)
    assert not outdated.ready
    assert not outdated.protocol_compatible
    assert "Reinstall" in outdated.next_action


def test_protocol_inventory_does_not_execute_plugin_and_rejects_dynamic_values(tmp_path):
    from bc250cc.infrastructure.external_tools.quick_access_inventory import (
        _declared_protocol,
    )

    source = tmp_path / "main.py"
    source.write_text("raise RuntimeError('must never execute')\nHELPER_PROTOCOL = 12\n")
    assert _declared_protocol(source) == 12
    for declaration in ("int('12')", "True", "None"):
        source.write_text(f"HELPER_PROTOCOL = {declaration}\n")
        assert _declared_protocol(source) is None


def test_quick_access_inventory_requires_package_metadata_for_modern_decky_loader(tmp_path, monkeypatch):
    home = tmp_path / "home"
    plugin = home / "homebrew" / "plugins" / "bc250-quick-access"
    for path in (plugin / "plugin.json", plugin / "main.py", plugin / "dist" / "index.js"):
        _root_owned(path)
    helper = tmp_path / "libexec" / "helper"
    _root_owned(helper, executable=True)
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(module, "_protected_regular", lambda path, **_kwargs: path.is_file())

    inventory = quick_access_inventory(
        os_family="steamos", home=home, environ={}, helper_path=helper,
    )

    assert inventory.plugin_present is False
    assert inventory.ready is False
    assert "installer" in inventory.next_action.lower()


def test_quick_access_inventory_rejects_a_symlinked_decky_payload(tmp_path, monkeypatch):
    home = tmp_path / "home"
    plugin = home / "homebrew" / "plugins" / "bc250-quick-access"
    plugin.mkdir(parents=True)
    target = tmp_path / "outside.js"
    target.write_text("payload", encoding="utf-8")
    _root_owned(plugin / "plugin.json")
    _root_owned(plugin / "package.json")
    _root_owned(plugin / "main.py")
    (plugin / "dist").mkdir()
    (plugin / "dist" / "index.js").symlink_to(target)
    helper = tmp_path / "libexec" / "helper"
    _root_owned(helper, executable=True)
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(module, "_protected_regular", lambda path, **_kwargs: path.is_file())

    inventory = quick_access_inventory(
        os_family="steamos", home=home, environ={}, helper_path=helper,
    )

    assert inventory.plugin_present is True
    assert inventory.plugin_safe is False
    assert inventory.ready is False
    assert "verification failed" in inventory.next_action


def test_quick_access_inventory_never_reports_a_symlinked_plugin_root_as_ready(tmp_path, monkeypatch):
    home = tmp_path / "home"
    real_root = tmp_path / "real-plugins"
    plugin = real_root / "bc250-quick-access"
    for path in (plugin / "plugin.json", plugin / "package.json", plugin / "main.py", plugin / "dist" / "index.js"):
        _root_owned(path)
    plugin_root_link = home / "homebrew" / "plugins"
    plugin_root_link.parent.mkdir(parents=True)
    plugin_root_link.symlink_to(real_root, target_is_directory=True)
    helper = tmp_path / "libexec" / "helper"
    _root_owned(helper, executable=True)
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(module, "_protected_regular", lambda path, **_kwargs: path.is_file())

    inventory = quick_access_inventory(
        os_family="steamos", home=home, environ={}, helper_path=helper,
    )

    assert inventory.decky_detected is True
    assert inventory.decky_plugin_root_safe is False
    assert inventory.plugin_present is True
    assert inventory.plugin_safe is False
    assert inventory.ready is False
    assert "not a symbolic link" in inventory.next_action


def test_quick_access_inventory_treats_an_unreadable_decky_payload_as_unverified(tmp_path, monkeypatch):
    home = tmp_path / "home"
    root = home / "homebrew" / "plugins"
    plugin = root / "bc250-quick-access"
    for path in (plugin / "plugin.json", plugin / "package.json", plugin / "main.py", plugin / "dist" / "index.js"):
        _root_owned(path)
    helper = tmp_path / "libexec" / "helper"
    _root_owned(helper, executable=True)
    import bc250cc.infrastructure.external_tools.quick_access_inventory as module
    monkeypatch.setattr(module, "_protected_regular", lambda path, **_kwargs: path.is_file())
    payloads = {plugin / "plugin.json", plugin / "package.json", plugin / "main.py", plugin / "dist" / "index.js"}
    original_stat = Path.stat

    def deny_plugin_payload(self, *args, **kwargs):
        if self in payloads:
            raise PermissionError("Decky payload is root-managed")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_plugin_payload)
    inventory = quick_access_inventory(
        os_family="steamos", home=home, environ={}, helper_path=helper,
    )

    assert inventory.plugin_present is False
    assert inventory.ready is False
    assert "installer" in inventory.next_action.lower()
