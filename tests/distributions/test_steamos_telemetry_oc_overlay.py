import runpy
import subprocess
from pathlib import Path

from bc250cc.infrastructure.gpu.governor_toml import GOVERNOR_DEFAULT_SAFE_POINTS
from bc250cc.infrastructure.steamos_amdgpu import build_steamos_compatibility_command

OVERLAY = Path("scripts/system/prepare-steamos-telemetry-oc-overlay.py")


def _reviewed_build_script() -> str:
    return (
        "#!/bin/bash\n"
        "GFXCLK_SOURCE_SHA=572014e03cff22fb57f21121e8e8722f11d3d99822ee86e60fbfe50ed6e76f30\n"
        "        SCLK_SOURCE_SHA=fdb9c3fff8a9ff813cdc37907dace041f89f6db15158c56a4bd8f238352b6e42\n"
        'step "apply GFX1013 compute-queue lifecycle patches"\n'
    )


def test_overlay_stages_once_and_keeps_the_kernel_control_limit_untouched(tmp_path):
    namespace = runpy.run_path(str(OVERLAY))
    root = tmp_path / "bc250-steamos"
    build = root / "bc250-audio-fix/build.sh"
    build.parent.mkdir(parents=True)
    build.write_text(_reviewed_build_script(), encoding="utf-8")
    build.chmod(0o755)

    assert namespace["apply_overlay"](root) is True
    staged = build.read_text(encoding="utf-8")
    assert namespace["OVERLAY_MARKER"] in staged
    assert "BC250_TELEMETRY_GFXCLK_MIN" in staged
    assert "BC250_TELEMETRY_GFXCLK_MAX" in staged
    assert f"{namespace['TELEMETRY_OC_MIN_MHZ']}" in staged
    assert f"{namespace['TELEMETRY_OC_MAX_MHZ']}" in staged
    assert namespace["TELEMETRY_OC_MIN_MHZ"] == min(
        frequency for frequency, _voltage in GOVERNOR_DEFAULT_SAFE_POINTS
    )
    assert namespace["TELEMETRY_OC_MAX_MHZ"] == max(
        frequency for frequency, _voltage in GOVERNOR_DEFAULT_SAFE_POINTS
    )
    assert "CYAN_SKILLFISH_SCLK_MAX" in staged
    assert staged.index(namespace["OVERLAY_MARKER"]) < staged.index(
        'step "apply GFX1013 compute-queue lifecycle patches"'
    )
    assert namespace["apply_overlay"](root) is False
    parsed = subprocess.run(
        ["bash", "-n", str(build)], capture_output=True, text=True, check=False
    )
    assert parsed.returncode == 0, parsed.stderr


def test_overlay_upgrades_the_attested_high_only_r181_fragment(tmp_path):
    namespace = runpy.run_path(str(OVERLAY))
    root = tmp_path / "bc250-steamos"
    build = root / "bc250-audio-fix/build.sh"
    build.parent.mkdir(parents=True)
    legacy = (
        f"{namespace['OVERLAY_MARKER']}\n"
        f"# {namespace['LEGACY_OVERLAY_RESULT_SHA']}\n"
    )
    build.write_text(
        _reviewed_build_script().replace(
            'step "apply GFX1013 compute-queue lifecycle patches"',
            legacy + 'step "apply GFX1013 compute-queue lifecycle patches"',
        ),
        encoding="utf-8",
    )
    build.chmod(0o755)

    assert namespace["apply_overlay"](root) is True
    upgraded = build.read_text(encoding="utf-8")
    assert namespace["LEGACY_OVERLAY_RESULT_SHA"] not in upgraded
    assert namespace["OVERLAY_RESULT_SHA"] in upgraded
    assert "BC250_TELEMETRY_GFXCLK_MIN" in upgraded


def test_overlay_rejects_an_unreviewed_build_script(tmp_path):
    namespace = runpy.run_path(str(OVERLAY))
    root = tmp_path / "bc250-steamos"
    build = root / "bc250-audio-fix/build.sh"
    build.parent.mkdir(parents=True)
    build.write_text('step "apply GFX1013 compute-queue lifecycle patches"\n', encoding="utf-8")
    build.chmod(0o755)

    try:
        namespace["apply_overlay"](root)
    except RuntimeError as error:
        assert "drifted" in str(error)
    else:
        raise AssertionError("unreviewed upstream build script was modified")


def test_explicit_install_path_stages_overlay_but_read_only_path_does_not():
    command = build_steamos_compatibility_command(
        script=Path("/tools/bc250-audio-fix/patch-driver.sh"),
        boot_config=Path("/tools/bc250-audio-fix/boot-config.sh"),
        checkout_command="checkout-reviewed-toolkit",
        install=True,
        telemetry_oc_overlay_command="stage-telemetry-overlay",
    )
    assert "stage-telemetry-overlay; export BC250_CONTROL_CENTER_OC_TELEMETRY=1" in command
    assert command.index("stage-telemetry-overlay") < command.rindex(
        "/usr/bin/bash /tools/bc250-audio-fix/patch-driver.sh"
    )

    readonly = build_steamos_compatibility_command(
        script=Path("/tools/bc250-audio-fix/patch-driver.sh"),
        boot_config=Path("/tools/bc250-audio-fix/boot-config.sh"),
        checkout_command="checkout-reviewed-toolkit",
        install=False,
        telemetry_oc_overlay_command="stage-telemetry-overlay",
    )
    assert "stage-telemetry-overlay" not in readonly
    assert "BC250_CONTROL_CENTER_OC_TELEMETRY=1" not in readonly


def test_overlay_accepts_only_the_reviewed_steamos_24_5_composition():
    namespace = runpy.run_path(str(OVERLAY))

    assert namespace["STEAMOS_24_5_KERNEL_COMMIT"] == (
        "b2f7cfe85e45b7e1ddb04ca8b280aca19add1100"
    )
    assert namespace["STEAMOS_24_5_SCLK_SOURCE_SHA"] == (
        "16578119d29855f47bec42b772d2ad03b8f3d690aa3df1106ad1411a04ca7d94"
    )
    assert namespace["STEAMOS_24_5_OVERLAY_RESULT_SHA"] == (
        "32b553a07f073881521c508ad9f40f7b86a91d7f8cbea032b084b3c998a62f19"
    )
