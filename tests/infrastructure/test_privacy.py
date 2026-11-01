"""A diagnosis is pasted in public: it must not say who or where, and it must still read as a diagnosis."""

from __future__ import annotations

import pytest

from bc250cc.infrastructure import privacy, system_diagnostics


@pytest.fixture(autouse=True)
def _a_known_machine(monkeypatch):
    """A machine and an owner the tests know, never the real ones."""
    privacy.reset_cache()
    monkeypatch.setattr(privacy, "_personal", lambda: {
        "hosts": {"kitchen-pc"},
        "users": {"marta", "invitado"},
        "real": {"Marta Quesada Rojas"},
        "wifi": {"CasaDeMarta5G"},
        "machine_id": "0123456789abcdef0123456789abcdef",
    })
    yield
    privacy.reset_cache()


def clean(text):
    return privacy.redact_machine(text)


# --------------------------------------------------------------------- addresses

@pytest.mark.parametrize("text, expected", [
    ("inet 192.168.1.50/24 brd 192.168.1.255", "inet <ip>/24 brd <ip>"),
    ("peer 8.8.8.8 and 203.0.113.7", "peer <ip> and <ip>"),
    ("gateway 10.0.0.1", "gateway <ip>"),
])
def test_ipv4_addresses_go_private_and_public(text, expected):
    assert clean(text) == expected


@pytest.mark.parametrize("text", [
    "listening on 127.0.0.1:631",
    "package 2.4.11.1-1 and 1:2.0.0.1",
    "kernel 7.2.9-ogc3.1.fc44.x86_64",
    "mesa 26.2.5-1.fc44",
])
def test_versions_and_the_loopback_are_not_taken_for_addresses(text):
    assert clean(text) == text


@pytest.mark.parametrize("address", [
    "2001:db8:85a3::8a2e:370:7334",
    "fe80::1ff:fe23:4567:890a",
    "2a02:8071:5c90:1c00:21a:2bff:fe3c:4d5e",
    "fd00::12",
])
def test_ipv6_addresses_go(address):
    assert clean(f"inet6 {address}/64 scope global") == "inet6 <ip>/64 scope global"


def test_a_link_local_address_with_its_interface_goes_whole():
    assert clean("link fe80::1ff:fe23:4567:890a%wlan0 up") == "link <ip> up"


@pytest.mark.parametrize("text", [
    "12:00:01.250 2000Mhz busy=99%",
    "pci 0000:00:08.1: BAR 0",
    "::1 localhost",
    "default via :: dev lo",
    "[  332.654962] kernel: hello",
])
def test_clocks_pci_addresses_and_the_loopback_are_not_ipv6(text):
    assert clean(text) == text


def test_mac_addresses_go():
    assert clean("link/ether 3c:a8:2a:1b:4f:90 brd ff:ff:ff:ff:ff:ff") == "link/ether <mac> brd <mac>"


# -------------------------------------------------------------------- identifiers

def test_filesystem_and_partition_uuids_go():
    text = (
        "BTRFS info (device sda5): last unmount of filesystem 7a2f5d1e-90b4-4c7a-8d6e-1f3b2a4c5d6e\n"
        "root=UUID=0b7cd8f1-3e2a-4f6b-9a10-2c4d5e6f7a8b rw\n"
        "/dev/sda10 ext4 21G /run/media/someone/16c5619d-02a7-4c3b-b9e1-6a5276bb977b"
    )
    out = clean(text)
    assert out.count("<uuid>") == 3
    assert "7a2f5d1e" not in out and "0b7cd8f1" not in out and "16c5619d" not in out
    assert "last unmount of filesystem <uuid>" in out and "root=UUID=<uuid> rw" in out


def test_the_graphics_drivers_own_ids_stay_because_they_say_which_build_not_whose():
    text = (
        "deviceUUID         = 0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0\n"
        "driverUUID         = 11223344-5566-7788-99aa-bbccddeeff00\n"
        "pipelineCacheUUID  = 99887766-5544-3322-1100-ffeeddccbbaa"
    )
    assert clean(text) == text


def test_the_machine_id_and_its_journal_folder_go():
    out = clean("49M\t/var/log/journal/0123456789abcdef0123456789abcdef\nmachine id 0123456789ABCDEF0123456789ABCDEF")
    assert "0123456789abcdef" not in out.lower()
    assert out.count("<machine-id>") == 2
    # Any machine-id in the journal's folder, not only this one's.
    assert clean("/var/log/journal/ffffffffffffffffffffffffffffffff/system.journal") == "/var/log/journal/<machine-id>/system.journal"


def test_steam_account_ids_go():
    out = clean("~/.local/share/Steam/userdata/1094057967/config/localconfig.vdf and 76561198012345678")
    assert "1094057967" not in out and "76561198012345678" not in out
    assert out.count("<steam-id>") == 2


@pytest.mark.parametrize("line, expected", [
    ("Serial Number: S3EVNX0M123456", "Serial Number: <serial>"),
    ("product_serial=ABC123XYZ789", "product_serial=<serial>"),
    ("ID_SERIAL=Samsung_SSD_860_S3Z9NB0K123456", "ID_SERIAL=<serial>"),
    ("ID_SERIAL_SHORT=S3Z9NB0K123456", "ID_SERIAL_SHORT=<serial>"),
    ("Chassis Serial: 00000042", "Chassis Serial: <serial>"),
])
def test_serial_numbers_go_and_their_label_stays(line, expected):
    assert clean(line) == expected


def test_a_driver_called_serial_is_not_a_serial_number():
    assert clean("serial8250: ttyS0 at I/O 0x3f8") == "serial8250: ttyS0 at I/O 0x3f8"


def test_email_addresses_go():
    assert clean("Author: Marta <marta.q@example.org>") != "Author: Marta <marta.q@example.org>"
    assert "marta.q@example.org" not in clean("contact marta.q@example.org please")
    # Not an address: no domain.
    assert clean("login deck@bazzite") == "login deck@bazzite"


# ------------------------------------------------------------------ people and machine

def test_the_machine_name_the_accounts_and_the_real_name_go():
    out = clean(
        "Hostname: kitchen-pc\n"
        "session opened for user marta by (uid=0)\n"
        "[sudo] password for invitado\n"
        "owner: Marta Quesada Rojas"
    )
    assert "kitchen-pc" not in out and "marta" not in out.lower() and "invitado" not in out
    assert "Quesada" not in out
    assert "<host>" in out and "<user>" in out and "<name>" in out


def test_a_saved_wifi_name_goes():
    out = clean('NetworkManager: connection "CasaDeMarta5G" activated; ssid CasaDeMarta5G')
    assert "CasaDeMarta5G" not in out and out.count("<network>") == 2


def test_default_host_names_and_generic_accounts_stay_because_they_name_no_one(monkeypatch):
    monkeypatch.setattr(privacy, "_personal", lambda: {
        "hosts": set(), "users": set(), "real": set(), "wifi": set(), "machine_id": "",
    })
    text = "Bazzite on bazzite, user deck, root"
    assert clean(text) == text


def test_home_folders_still_become_a_tilde():
    assert clean("/var/home/someone/Documentos/x and /home/other/y") == "~/Documentos/x and ~/y"


# ------------------------------------------------------------------- the whole thing

def test_redacting_twice_changes_nothing():
    text = (
        "inet 192.168.1.50/24 inet6 fe80::1ff:fe23:4567:890a%wlan0 3c:a8:2a:1b:4f:90\n"
        "filesystem 7a2f5d1e-90b4-4c7a-8d6e-1f3b2a4c5d6e host kitchen-pc user marta\n"
        "Serial Number: S3EVNX0M123456 /var/log/journal/0123456789abcdef0123456789abcdef"
    )
    once = clean(text)
    assert clean(once) == once


def test_nothing_that_names_the_owner_survives_in_a_realistic_diagnosis():
    secrets = [
        "kitchen-pc", "marta", "invitado", "Marta Quesada", "CasaDeMarta5G", "192.168.1.50", "203.0.113.7",
        "2a02:8071:5c90:1c00", "3c:a8:2a:1b:4f:90", "7a2f5d1e-90b4-4c7a-8d6e-1f3b2a4c5d6e",
        "0123456789abcdef0123456789abcdef", "1094057967", "76561198012345678", "S3EVNX0M123456", "marta.q@example.org",
    ]
    diagnosis = f"""
== Kernel ==
7.2.9-ogc3.1.fc44.x86_64  host kitchen-pc
== Previous boot ==
sshd[812]: Accepted publickey for marta from 203.0.113.7 port 51244
== Storage ==
/dev/sda3 btrfs 40G /run/media/marta/7a2f5d1e-90b4-4c7a-8d6e-1f3b2a4c5d6e
49M\t/var/log/journal/0123456789abcdef0123456789abcdef
== Network ==
wlan0: associated with CasaDeMarta5G, link/ether 3c:a8:2a:1b:4f:90, inet 192.168.1.50/24
inet6 2a02:8071:5c90:1c00:21a:2bff:fe3c:4d5e/64
== Hardware ==
Serial Number: S3EVNX0M123456
== Steam ==
/home/marta/.local/share/Steam/userdata/1094057967/config and 76561198012345678
git author: Marta Quesada Rojas <marta.q@example.org>
invitado logged in
"""
    out = clean(diagnosis)
    leaked = [secret for secret in secrets if secret.lower() in out.lower()]
    assert leaked == []
    # And it still reads as a diagnosis.
    assert "7.2.9-ogc3.1.fc44.x86_64" in out and "== Previous boot ==" in out and "btrfs 40G" in out
    assert "Accepted publickey" in out and "associated with" in out


# --------------------------------------------------- every way a diagnosis leaves the app

def test_the_short_diagnosis_the_terminal_prints_is_redacted_too():
    text = system_diagnostics.collect_diagnostics(
        [("Network", lambda: "wlan0 inet 192.168.1.50/24 host kitchen-pc fe80::1ff:fe23:4567:890a")],
    )
    assert "192.168.1.50" not in text and "kitchen-pc" not in text and "fe80::1ff" not in text


def test_the_text_settings_copies_for_a_report_is_redacted_too():
    from frontends.desktop.core.diagnostic_history import diagnostic_report

    text = diagnostic_report([("Network", "192.168.1.50 on CasaDeMarta5G")], [])
    assert "192.168.1.50" not in text and "CasaDeMarta5G" not in text


def test_the_full_attachments_a_report_carries_are_redacted_too(monkeypatch):
    from bc250cc.infrastructure import report_attachments

    state = (("Network", lambda: "ip 192.168.1.50 host kitchen-pc"),)
    real_state = report_attachments.collect_system_state
    monkeypatch.setattr(report_attachments, "STATE_SECTIONS", state)
    # The function binds its sections when it is defined: hand them over explicitly.
    monkeypatch.setattr(report_attachments, "collect_system_state", lambda: real_state(state))
    monkeypatch.setattr(report_attachments.diag, "SECTIONS", (("Kernel", lambda: "root=UUID=7a2f5d1e-90b4-4c7a-8d6e-1f3b2a4c5d6e"),))
    sections = dict(report_attachments.collect_attachments())
    assert "<ip>" in sections["Network"] and "<host>" in sections["Network"]
    assert "7a2f5d1e" not in sections["Kernel"]
