from pathlib import Path

from bc250cc.platform import PlatformCapabilities


def test_capabilities_use_real_probes_not_distro_name(tmp_path: Path):
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=arch\nNAME="Arch Linux"\n', encoding="utf-8")
    run_root = tmp_path / "run"
    (run_root / "openrc").mkdir(parents=True)
    (run_root / "openrc" / "softlevel").write_text("default\n", encoding="utf-8")
    sysfs = tmp_path / "sys"
    (sysfs / "class/hwmon/hwmon0").mkdir(parents=True)
    (sysfs / "class/hwmon/hwmon0/pwm1_enable").write_text("2\n", encoding="utf-8")

    capabilities = PlatformCapabilities.detect(
        os_release=os_release,
        sysfs_root=sysfs,
        run_root=run_root,
        executable_lookup=lambda command: command == "umr",
    )

    assert capabilities.distro_id == "arch"
    assert capabilities.init_system == "openrc"
    assert capabilities.immutable_root is False
    assert capabilities.umr is True
    assert capabilities.pwm is True


def test_capabilities_detect_decky_using_the_official_homebrew_plugin_root(tmp_path: Path):
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=steamos\n", encoding="utf-8")
    run_root = tmp_path / "run"
    sysfs = tmp_path / "sys"
    decky = tmp_path / "deck-homebrew" / "plugins"
    decky.mkdir(parents=True)

    capabilities = PlatformCapabilities.detect(
        os_release=os_release,
        sysfs_root=sysfs,
        run_root=run_root,
        decky_root=decky,
        executable_lookup=lambda _command: False,
    )

    assert capabilities.decky is True


def test_capabilities_require_a_working_system_bus_not_only_busctl(tmp_path: Path):
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=debian\n", encoding="utf-8")

    unavailable = PlatformCapabilities.detect(
        os_release=os_release,
        sysfs_root=tmp_path / "sys",
        run_root=tmp_path / "run",
        executable_lookup=lambda command: command == "busctl",
        dbus_probe=lambda: False,
    )
    available = PlatformCapabilities.detect(
        os_release=os_release,
        sysfs_root=tmp_path / "sys",
        run_root=tmp_path / "run",
        executable_lookup=lambda command: command == "busctl",
        dbus_probe=lambda: True,
    )

    assert unavailable.dbus is False
    assert available.dbus is True


def test_session_bus_environment_does_not_fake_system_bus_capability(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/stale-session-bus")
    capabilities = PlatformCapabilities.detect(
        os_release=tmp_path / "os-release",
        sysfs_root=tmp_path / "sys",
        run_root=tmp_path / "run",
        executable_lookup=lambda _command: False,
    )
    assert capabilities.dbus is False


def test_broken_injected_dbus_probe_fails_closed(tmp_path: Path):
    def broken_probe():
        raise RuntimeError("probe unavailable")

    capabilities = PlatformCapabilities.detect(
        os_release=tmp_path / "os-release",
        sysfs_root=tmp_path / "sys",
        run_root=tmp_path / "run",
        dbus_probe=broken_probe,
    )
    assert capabilities.dbus is False


def test_capability_constructor_rejects_invalid_state():
    from pytest import raises

    with raises(ValueError):
        PlatformCapabilities("", "systemd", False, False, False, False, False, False)
    with raises(ValueError):
        PlatformCapabilities("arch", "systemd", 1, False, False, False, False, False)
