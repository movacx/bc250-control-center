import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.steamos_graphics_runtime import (
    STEAMOS_GRAPHICS_ACTIONS,
    _graphics_status_report_command,
    build_steamos_graphics_command,
)


@pytest.mark.parametrize(
    ("action", "fragment"),
    (
        ("status", "status-json"),
        ("install", " setup"),
        ("install-fsr4", "setup --fsr4"),
        ("uninstall", " uninstall"),
        ("uninstall-fsr4", "uninstall --fsr4"),
    ),
)
def test_steamos_graphics_actions_use_only_the_protected_backend(action, fragment):
    protected = Path(
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-mesh-shader.sh"
    )
    command = build_steamos_graphics_command(
        action,
        checkout_command="echo STAGE_REVIEWED_TREE",
        backend_guard="test -x PROTECTED_BACKEND",
        script=protected,
    )

    assert fragment in command
    assert str(protected) in command
    assert "test -x PROTECTED_BACKEND" in command
    assert "steamos|steamdeck|holo" in command
    assert "/ResourceTools/" not in command
    if action == "status":
        assert "STAGE_REVIEWED_TREE" not in command
        assert command.count("status-json") == 1
    else:
        assert "STAGE_REVIEWED_TREE" in command
        assert command.count("status-json") == 1


def test_steamos_graphics_action_surface_is_finite_and_rejects_empty_guards():
    assert STEAMOS_GRAPHICS_ACTIONS == {
        "status", "install", "install-fsr4", "uninstall", "uninstall-fsr4"
    }
    with pytest.raises(ValueError):
        build_steamos_graphics_command("shell", backend_guard="true")
    with pytest.raises(ValueError):
        build_steamos_graphics_command("install", backend_guard="")


def test_graphics_status_is_rendered_as_a_readable_summary(tmp_path):
    backend = tmp_path / "graphics-status.sh"
    backend.write_text(
        "#!/usr/bin/bash\n"
        "printf '%s\\n' '{\"scriptAvailable\":true,\"runtimeState\":\"ready\","
        "\"mesaVersion\":\"mesa-26.2.0\",\"configValid\":true,"
        "\"icdPath\":\"/home/deck/radeon_icd.json\",\"kernelReady\":true,"
        "\"schedulerConfigured\":true,\"schedulerActive\":true,\"globalEnabled\":false,"
        "\"restartRequired\":true,\"fsr4State\":\"not-installed\",\"games\":[],\"error\":null}'\n",
        encoding="utf-8",
    )
    backend.chmod(0o755)

    result = subprocess.run(
        ["bash", "-c", _graphics_status_report_command(backend, system_helper=None)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Backend script         Available" in result.stdout
    assert "Graphics runtime       Ready" in result.stdout
    assert "Mesa version           mesa-26.2.0" in result.stdout
    assert "ICD configuration      Valid" in result.stdout
    assert "Scheduler active       Active" in result.stdout
    assert "Restart required       Yes" in result.stdout
    assert "FSR4                   Not Installed" in result.stdout
    assert "ICD manifest\n  /home/deck/radeon_icd.json" in result.stdout
    assert "[WARN] Restart is required" in result.stdout
    assert result.stdout.startswith("== Graphics stack ==")
    assert "== Verified fixes ==" in result.stdout
    assert "AMDGPU DP audio compatibility quirk" in result.stdout
    assert "RADV GFX1013 mesh/task shaders (restart required)" in result.stdout
    assert "{\"runtimeState\"" not in result.stdout


def test_graphics_status_includes_extended_bc250_telemetry(tmp_path):
    graphics = tmp_path / "graphics.sh"
    graphics.write_text(
        "#!/usr/bin/bash\n"
        "printf '%s\\n' '{\"scriptAvailable\":true,\"runtimeState\":\"ready\","
        "\"mesaVersion\":\"mesa-26.2.0\",\"configValid\":true,\"kernelReady\":true,"
        "\"schedulerConfigured\":true,\"schedulerActive\":true,\"globalEnabled\":true,"
        "\"restartRequired\":false,\"fsr4State\":\"not-installed\",\"games\":[],\"error\":null}'\n",
        encoding="utf-8",
    )
    graphics.chmod(0o755)
    helper = tmp_path / "helper"
    helper.write_text(
        "#!/usr/bin/bash\n"
        "printf '%s\\n' '{\"ok\":true,\"protocol\":13,\"cu_active_cus\":24,"
        "\"cu_total_cus\":40,\"cu_masks\":[7,7,7,7],\"cu_service_enabled\":false,"
        "\"gpu_governor_label\":\"Cyan Skillfish\",\"gpu_range\":[1000,1850],"
        "\"gpu_governor_active\":true,\"gpu_performance_enabled\":true,"
        "\"gpu_core_mhz\":1000,\"gpu_voltage_mv\":799,\"gpu_memory_clock_mhz\":800,"
        "\"gpu_vram_used_mib\":2048,\"gpu_vram_total_mib\":16384,"
        "\"gpu_busy_percent\":42,\"gpu_temperature_c\":61.5,\"cpu_frequency_mhz\":3489,"
        "\"cpu_temperature_c\":55.5,\"cpu_active_profile\":{\"mode\":\"automatic\","
        "\"frequency\":3500,\"estimated_vid\":1100,\"scale\":-20,\"temperature\":90},"
        "\"cpu_service_enabled\":true,"
        "\"system_fan_preset\":\"balanced\",\"system_fan_duty\":153,"
        "\"system_fan_channels\":[2,3,4,5],\"fan_channel_options\":["
        "{\"channel\":2,\"rpm\":1800},{\"channel\":3,\"rpm\":1450}]}'\n",
        encoding="utf-8",
    )
    helper.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo = fake_bin / "sudo"
    sudo.write_text(
        "#!/usr/bin/bash\n"
        "if [ \"${1:-}\" = stat ]; then echo '0:755'; exit 0; fi\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    sudo.chmod(0o755)

    result = subprocess.run(
        [
            "bash", "-c",
            _graphics_status_report_command(graphics, system_helper=helper),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    assert "Active CUs             24 / 40" in result.stdout
    assert "Active WGP masks       0x07 0x07 0x07 0x07" in result.stdout
    assert "Governor               Cyan Skillfish" in result.stdout
    assert "Governor active        Active" in result.stdout
    assert "Performance mode       Enabled" in result.stdout
    assert "Core clock             1000 MHz" in result.stdout
    assert "VRAM usage             2048 / 16384 MiB" in result.stdout
    assert "CPU OC active          Active" in result.stdout
    assert "Target clock           3500 MHz" in result.stdout
    assert "Estimated VID          1100 mV" in result.stdout
    assert "Scale                  -20" in result.stdout
    assert "Boot service           Enabled" in result.stdout
    assert "Fan preset             Balanced" in result.stdout
    assert "Fan output             60% (PWM 153)" in result.stdout
    assert "Fan speeds             PWM 2: 1800 RPM, PWM 3: 1450 RPM" in result.stdout
