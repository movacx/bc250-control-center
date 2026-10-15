from __future__ import annotations

from bc250cc.infrastructure import bc250_fsr4


def test_fsr4_launch_options_are_username_independent():
    binary = bc250_fsr4.fsr4_steam_launch_option("")
    source = bc250_fsr4.fsr4_steam_launch_option("debian-podman-source")

    assert binary == 'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/radv-bc250-fsr4-v3.json" %command%'
    assert source.startswith('LD_LIBRARY_PATH="$HOME/.local/share/bc250-fsr4/v3/lib')
    assert '${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}' in source
    assert 'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/' in source
    assert "/home/" not in binary
    assert "/home/" not in source


def test_fsr4_uninstall_invokes_the_official_v3_script(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_uninstall_command(destination)

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert f"bash {destination}/uninstall-v3.sh" in command
    assert 'BC250_FSR4_PREFIX="$HOME/.local/share/bc250-fsr4/v3"' in command
    assert "sudo" not in command
