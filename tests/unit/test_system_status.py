from bc250cc.application.system import SystemStatus
from bc250cc.platform import PlatformCapabilities


def test_system_status_is_a_typed_capability_payload():
    capabilities = PlatformCapabilities(
        distro_id="arch",
        init_system="openrc",
        immutable_root=False,
        dbus=True,
        sysfs=True,
        umr=False,
        pwm=True,
        decky=False,
    )
    status = SystemStatus.from_capabilities(capabilities)

    assert status.to_dict() == {
        "distro_id": "arch",
        "init_system": "openrc",
        "immutable_root": False,
        "dbus": True,
        "sysfs": True,
        "umr": False,
        "pwm": True,
        "decky": False,
    }


def test_system_status_rejects_untyped_source():
    try:
        SystemStatus.from_capabilities(object())
    except TypeError:
        pass
    else:
        raise AssertionError("untyped capability source was accepted")


def test_system_status_constructor_rejects_invalid_state():
    try:
        SystemStatus("", "systemd", False, False, False, False, False, False)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid system status was accepted")
