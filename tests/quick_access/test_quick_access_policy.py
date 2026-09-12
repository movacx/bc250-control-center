from pathlib import Path

import pytest

from bc250cc.domain.cpu import FREQUENCY_RANGE
from bc250cc.infrastructure.quick_access_policy import (
    CPU_QAM_FREQUENCIES,
    CPU_QAM_MAX_ESTIMATED_VID_MV,
    CPU_QAM_SCALES,
    CPU_SAVED_PROFILE_ACTION,
    CU_MODES,
    FAN_SYSTEM_PRESETS,
    GPU_PROFILES,
    QAM_FAN_CHANNELS,
    QAM_FAN_MAX_PERCENT,
    QAM_FAN_MIN_PERCENT,
    cu_mode,
    fan_system_preset,
    gpu_profile,
    safe_fan_channel,
    safe_fan_percent,
)

ROOT = Path(__file__).resolve().parents[2]


def test_quick_access_gpu_profiles_are_named_and_conservative():
    assert [(item.key, item.minimum_mhz, item.maximum_mhz) for item in GPU_PROFILES] == [
        ("balanced", 500, 1500),
        ("gaming", 1000, 1850),
        ("benchmark", 1000, 2000),
    ]
    assert gpu_profile("benchmark").maximum_mhz == 2000
    with pytest.raises(ValueError):
        gpu_profile("2400")


def test_quick_access_cu_modes_cannot_become_a_command_channel():
    assert CU_MODES == (24, 26, 28, 30, 32, 34, 36, 38, 40)
    assert cu_mode("32") == 32
    assert cu_mode(40) == 40
    with pytest.raises(ValueError):
        cu_mode("install-service")
    with pytest.raises(ValueError):
        cu_mode(25)


@pytest.mark.parametrize("value", [2, "3", 4, "5"])
def test_quick_access_fan_restore_validates_channel(value):
    assert safe_fan_channel(value) == int(value)


@pytest.mark.parametrize("value", [0, 1, 2.5, 6, 12, "02", "x", None, True])
def test_quick_access_fan_restore_rejects_unsafe_channel(value):
    with pytest.raises(ValueError):
        safe_fan_channel(value)


def test_quick_access_manual_fan_percentage_is_thermally_bounded():
    assert QAM_FAN_CHANNELS == (2, 3, 4, 5)
    assert (QAM_FAN_MIN_PERCENT, QAM_FAN_MAX_PERCENT) == (20, 100)
    assert safe_fan_percent("20") == 20
    assert safe_fan_percent(100) == 100
    for value in (0, 19, 20.5, 101, "020", "x", None, True):
        with pytest.raises(ValueError):
            safe_fan_percent(value)


def test_quick_access_cpu_domain_is_finite_and_fans_are_named_presets():
    assert CPU_SAVED_PROFILE_ACTION == "apply-saved-profile"
    assert CPU_QAM_FREQUENCIES == tuple(range(FREQUENCY_RANGE[0], FREQUENCY_RANGE[1] + 1, 50))
    assert CPU_QAM_SCALES == tuple(range(-50, 1))
    assert CPU_QAM_MAX_ESTIMATED_VID_MV == 1325
    assert FAN_SYSTEM_PRESETS == {
        "quiet": ("Quiet · 40%", 102),
        "balanced": ("Balanced · 60%", 153),
        "boost": ("Boost · 80%", 204),
        "automatic": ("Automatic", None),
    }
    assert fan_system_preset("balanced")[1] == 153
    with pytest.raises(ValueError):
        fan_system_preset("255")


def test_decky_plugin_and_helper_keep_a_finite_root_protocol():
    helper = (ROOT / "privileged/helpers/bc250-quick-access-helper").read_text(encoding="utf-8")
    backend = (ROOT / "integrations/decky/bc250-quick-access/main.py").read_text(encoding="utf-8")
    frontend = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    bundle = (ROOT / "integrations/decky/bc250-quick-access/dist/index.js").read_text(encoding="utf-8")
    manifest = (ROOT / "integrations/decky/bc250-quick-access/plugin.json").read_text(encoding="utf-8")

    assert '"root"' in manifest
    assert '"_root"' in manifest

    assert 'GPU_PROFILES = {' in helper
    assert 'CU_TARGETS = tuple(range(24, 41, 2))' in helper
    assert 'shell=True' not in helper
    assert 'gpu-voltage' not in helper
    assert 'apply-custom' not in helper
    assert '"cu-save"' in helper
    assert '"cu-service"' in helper
    assert 'def cu_install_service()' in helper
    assert 'def cu_remove_service()' in helper
    assert 'apply_gpu_profile' in backend
    assert 'apply_gpu_safe_point' in backend
    assert 'apply_cu_mode' in backend
    assert 'apply_cu_table' in backend
    assert 'apply_system_fan_preset' in backend
    assert 'apply_fan_channel' in backend
    assert 'apply_saved_cpu_profile' in backend
    assert 'apply_cpu_tuning' in backend
    assert 'apply_cpu_scale' in backend
    assert 'async def cpu_telemetry' in backend
    assert 'PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent' in backend
    assert 'from bc250cc.domain.gpu.profiles import profiles_payload' in backend
    assert 'install_cpu_service' in backend
    assert 'remove_cpu_service' in backend
    assert 'applyGpuProfile' in frontend
    assert 'applyGpuSafePoint' in frontend
    assert 'applyCuTable' in frontend
    assert 'saveCuTable' in frontend
    assert 'installCuService' in frontend
    assert 'removeCuService' in frontend
    assert 'applySavedCpuProfile' not in frontend
    assert 'applyCpuTuning' in frontend
    assert 'applyCpuScale' in frontend
    assert 'getCpuTelemetry' in frontend
    assert 'installCpuService' in frontend
    assert 'removeCpuService' in frontend
    assert 'cpu-apply-saved' in helper
    assert 'cpu-detect' in helper
    assert 'cpu-scale' in helper
    assert 'cpu-telemetry' in helper
    assert 'cpu-service' in helper
    assert 'fan-system' in helper
    assert 'fan-channel' in helper
    assert 'cu-table' in helper
    assert 'SYSTEM_FAN_CHANNELS = tuple(range(3, 9))' in helper
    assert 'QAM_FAN_CHANNELS = (2, 3, 4, 5)' in helper
    assert '"ok": True' in helper
    assert 'HELPER_PROTOCOL = 13' in helper
    assert 'HELPER_PROTOCOL = 13' in backend
    assert 'save_cu_table' in backend
    assert 'install_cu_service' in backend
    assert 'remove_cu_service' in backend
    assert 'def _trusted_helper()' in backend
    assert 'def _verified_status(self)' in backend
    assert 'def _run_verified(self' in backend
    assert 'Focusable' in frontend
    assert 'onActivate' in frontend
    assert 'cu_masks' in frontend
    assert 'gpu_core_mhz' in frontend
    assert 'gpu_voltage_mv' in frontend
    assert 'gpu_temperature_c' in frontend
    assert 'gpu_allowed_range' in frontend
    # The filter that used to be here excluded a "recovery" profile no
    # generator ever emitted and the helper rejected outright. Both sides
    # dropped it; what matters is that the profiles come from the payload.
    assert 'activeGpuProfiles' in frontend
    assert 'gpu_safe_point_ceilings' in frontend
    assert 'gpu_cooldown_seconds' not in frontend
    assert 'fan_channel_options' in frontend
    assert 'fanWiring' in frontend
    assert 'wiring_uncertain' in frontend
    assert 'qam_fan_channel_state' in helper
    assert 'gpu_temperature_c' in helper
    assert 'gpu_voltage_mv' in helper
    assert 'gpu_safe_point_ceilings' in helper
    assert 'gpu-safe-point' in helper
    assert 'recent_actions' not in frontend
    assert 'liveScenes' not in frontend
    assert 'Selecting a scene changes no hardware' not in frontend
    assert 'function Action' in frontend
    assert 'cuTargets' not in frontend
    assert 'flow-children="grid"' in frontend
    assert 'NavEntryPositionPreferences' in frontend
    assert 'helper_protected' in frontend
    assert 'MAX_RECENT_ACTIONS = 10' in backend
    assert 'cpuFrequency' in frontend
    assert 'cpuVoltage' in frontend
    assert 'cpu_frequency_mhz' in frontend
    assert 'function CuMatrix' in frontend
    assert 'wait_for_cyan_range' in helper
    cu_editor = frontend.split('function CuMatrix', 1)[1].split('function Content', 1)[0]
    assert 'cuRows.flatMap' in cu_editor
    assert cu_editor.count('flow-children="grid"') == 1
    assert 'function OverviewItem' not in frontend
    assert '<OverviewItem' not in frontend
    assert 'function RecentActivity' not in frontend
    assert 'PanelSection' not in frontend
    for operation in (
        "apply_gpu_profile",
        "apply_gpu_safe_point",
        "apply_cu_table",
        "save_cu_table",
        "install_cu_service",
        "remove_cu_service",
        "apply_fan_channel",
        "apply_cpu_tuning",
        "apply_cpu_scale",
        "install_cpu_service",
        "remove_cpu_service",
    ):
        assert operation in bundle


def test_decky_frontend_uses_native_buttons_for_every_gamepad_selector_and_cu_cell():
    frontend = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")

    # QAM's native Button owns A/click delivery. Focusable is kept only for
    # directional containers; selection remains inline and independent from
    # popup/MenuItem callback differences across Steam client builds.
    assert "DropdownItem" not in frontend
    assert "showContextMenu" not in frontend
    assert "function PadButton" in frontend
    assert "<Button" in frontend
    assert "focusable" in frontend
    assert "onClick={activate}" in frontend
    assert "onOKButton={activate}" in frontend
    assert "onGamepadFocus={() => setFocused(true)}" in frontend
    assert "onGamepadBlur={() => setFocused(false)}" in frontend
    # Controller focus must remain visible without reintroducing the heavy
    # double halo that made QAM selection look like a custom web control.
    assert "border: focused ?" in frontend
    assert "boxShadow: focused ?" in frontend
    assert "tokens.colors.focus" in frontend
    assert 'flow-children="grid"' in frontend
    # A high TOML button is not painted selected optimistically. It becomes
    # orange only when the helper has returned the verified live range.
    assert "setHighSelection(point.frequency)" not in frontend
    assert "setHighSelection(result.gpu_range[1])" in frontend
    assert 'flow-children="down"' in frontend
    assert "function SectionTitle" in frontend


def test_qam_compact_header_starts_directly_with_gpu_after_a_clean_top_margin():
    frontend = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    content = frontend.split('return <Focusable flow-children="down"', 1)[1]

    # The duplicate brand header and passive dashboard consumed scarce QAM
    # space. GPU now starts the useful content after one deliberate top inset.
    assert ">BC</div>" not in content
    assert "CONTROL CENTER" not in content
    assert "{stale ? text.stale : text.live}" not in content
    assert "function DashboardScrollAnchor" not in frontend
    assert "<DashboardScrollAnchor />" not in content
    assert "function OverviewItem" not in frontend
    assert 'padding: "12px 14px 72px"' in content
    assert content.index('<SectionTitle kind="gpu"') < content.index('<SectionTitle kind="cu"')


def test_qam_action_rows_keep_identical_geometry_when_buttons_are_disabled():
    frontend = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    pad_button = frontend.split("function PadButton", 1)[1].split("function SectionTitle", 1)[0]

    # A disabled action used to become a raw content-box div, adding padding
    # outside the declared height and visibly colliding with the next module.
    assert 'if (disabled) return <div' not in pad_button
    assert 'disabled={disabled}' in pad_button
    assert 'focusable={!disabled}' in pad_button
    assert 'boxSizing: "border-box"' in frontend
    assert 'function ActionRow' in frontend
    assert 'height: 36' in frontend
    assert 'minHeight: 78' in frontend

    cu_section = frontend.split('<SectionTitle kind="cu"', 1)[1].split('<SectionTitle kind="cpu"', 1)[0]
    assert cu_section.count("<ActionRow") >= 3
    assert '<ActionRow marginBottom={6}>' in cu_section


def test_qam_cpu_sliders_use_real_detector_inputs_and_native_gamepad_steps():
    frontend = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    backend = (ROOT / "integrations/decky/bc250-quick-access/main.py").read_text(encoding="utf-8")
    helper = (ROOT / "privileged/helpers/bc250-quick-access-helper").read_text(encoding="utf-8")

    assert "function CompactSlider" in frontend
    assert 'showValue={false}' in frontend
    assert 'validValues="steps"' in frontend
    # The steps and bounds are no longer written here. They arrive with the
    # state, because the panel's own copy said the CPU floor was 3500 MHz
    # against a real 3100 — and then clamped a saved 3200 profile up to 3500
    # and re-applied it. See test_the_panel_has_no_bounds_of_its_own.py.
    assert 'step={cpuStep}' in frontend
    assert 'step={vidStep}' in frontend
    assert 'step={1}' in frontend
    assert 'min={vidMin}' in frontend and 'max={vidMax}' in frontend
    assert 'min={scaleMin}' in frontend and 'max={scaleMax}' in frontend
    assert "estimatedVid" not in frontend
    assert "nearestScale" not in frontend
    assert "ToggleField" in frontend
    assert "cpuManual" in frontend
    assert "applyCpuScale(cpuFrequency, cpuScale)" in frontend
    assert "applySavedCpuProfile" not in frontend


    assert '"cpu-detect"' in backend
    assert '"cpu-scale"' in backend
    assert '"cpu-detect"' in helper
    assert '"cpu-scale"' in helper
    assert '"detect-qam"' in helper
    assert '"apply-qam-scale"' in helper
    # The compact visual concept has no passive telemetry card, legacy stack of
    # PanelSection/module cards or session-history panel.
    assert "function OverviewItem" not in frontend
    assert "function RecentActivity" not in frontend
    assert "liveFanPercent" not in frontend
    assert "showModal(" in frontend
    assert "<ConfirmModal" in frontend
    assert 'GPU · ${governorName || text.advanced}' in frontend
    assert "applyGpuSafePoint(point.frequency)" in frontend
    assert 'title={isSpanish ? "Estado del sistema" : "System status"}' not in frontend
    assert 'state.cpu_tuning_source === "detector-required" ? text.cpuNeedsDetection' in frontend
    assert "actionDescription={copy.liveRefresh}" not in frontend
    assert "PanelSection" not in frontend

    cu_editor = frontend.split("function CuMatrix", 1)[1].split("function Content", 1)[0]
    assert cu_editor.count('flow-children="grid"') == 1
    assert 'navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD}' in cu_editor
    assert "preferredFocus={row === 0 && wgp === 0}" in cu_editor
    assert "<PadButton" in cu_editor
    assert "minimum();" in cu_editor
    assert "WGP ${wgp}" in cu_editor
    assert '"D+"' in cu_editor


def test_qam_cpu_keeps_requested_frequency_separate_from_safe_detector_result():
    frontend = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    bundle = (ROOT / "integrations/decky/bc250-quick-access/dist/index.js").read_text(encoding="utf-8")

    assert "detectedCpu.requested_frequency === detectedCpu.frequency" in frontend
    assert "detectedCpu.requested_frequency === detectedCpu.frequency" in bundle
    assert "!manualFrequencyReady" in frontend
    assert "!manualFrequencyReady" in bundle
    assert "activeCpu?.frequency === detectedCpu.frequency" in frontend
    assert "activeCpu?.frequency === detectedCpu.frequency" in bundle
    assert "setCpuFrequency(detectedCpu.frequency)" not in frontend
    assert "setCpuFrequency(detectedCpu.frequency)" not in bundle
    assert "manualScaleDescription" in frontend
    assert "manualScaleDescription" in bundle


def test_decky_theme_preserves_the_current_desktop_dark_orange_visual_concept():
    theme = (ROOT / "integrations/decky/bc250-quick-access/src/theme.ts").read_text(encoding="utf-8")

    # The accepted visual concept uses Desktop graphite, orange for deliberate
    # selections/actions, amber for pending attention, and blue only for focus.
    for color in ("#0F0F0F", "#171717", "#242424", "#F2F2F2", "#F0A45D", "#6E9FFF"):
        assert color in theme
    assert "var(--gp" not in theme
    assert 'selection: "#38291D"' in theme
    assert 'action_hover: "#F0A45D"' in theme
    assert 'amber: "#E0A83E"' in theme


def test_decky_installer_is_explicit_and_does_not_install_decky_loader():
    source = (ROOT / "scripts/install-decky-quick-access.sh").read_text(encoding="utf-8")
    local_installer = (ROOT / "scripts/install-local.sh").read_text(encoding="utf-8")
    assert 'install-decky-quick-access.sh" \\' in local_installer
    assert 'integrations/decky/bc250-quick-access/$decky_runtime' in local_installer
    assert 'for decky_runtime in plugin.json package.json main.py dist/index.js \\' in local_installer
    assert 'bc250cc/domain/gpu/profiles.py' in local_installer
    assert 'decky-installer/releases' not in local_installer
    assert 'INSTALL_DECKY_BETA' not in local_installer
    assert 'Decky Loader plugin directory was not found' in source
    assert 'It does not install Decky Loader' in source
    assert 'bc250-quick-access-helper' in source
    assert '/usr/share/bc250-control-center/integrations/decky/bc250-quick-access' in source
    assert 'run this installer as the Desktop Mode user, not as root' in source
    assert 'Decky itself is a separate trusted root-plugin environment' in source
    assert 'sudo chown -R root:root "$PLUGIN_DEST"' not in source
    assert 'sudo install -Dm755 "$HELPER_SOURCE" "$HELPER_DEST"' in source
    assert 'IMMUTABLE_OSTREE=1' in source
    assert 'does not contain the protected helpers from this BC250 build' in source
    assert 'Install or update the BC250 Control Center RPM deployment' in source
    assert 'for relative in plugin.json package.json main.py dist/index.js \\' in source
    assert 'bc250cc/domain/gpu/profiles.py' in source
    assert 'Decky v3 selects its ESM frontend loader' in source
    assert 'sudo install -Dm644 -- "$source_path" "$plugin_stage/$relative"' in source
    assert 'plugin_stage="$(sudo mktemp -d /var/tmp/bc250-decky-stage.XXXXXX)"' in source
    assert 'sudo mv -- "$plugin_stage" "$PLUGIN_DEST"' in source
    assert 'sudo chmod 0755 "$plugin_stage"' in source
    assert 'installed Decky plugin directory is not root-owned mode 0755' in source
    assert 'cleanup_stale_plugin_transactions' in source
    assert '"$PLUGIN_ROOT"/.bc250-decky-stage.*' in source
    assert 'sudo systemctl restart plugin_loader.service' in source
    assert 'command -v systemctl >/dev/null 2>&1' in source
    assert 'This init system has no systemctl integration for Decky reload' in source
    assert 'Reloading Decky Plugin Loader so it forgets any previous BC250 bundle path' in source
    assert 'node_modules' not in source
    assert 'refusing to replace a symbolic-link Quick Access helper' in source


def test_distribution_staging_includes_qam_without_development_dependencies():
    staging = (ROOT / "packaging/scripts/stage-package-root.sh").read_text(encoding="utf-8")
    assert 'integrations/decky/bc250-quick-access' in staging
    assert 'bc250-control-center-decky-install' in staging
    assert 'bc250-quick-access/node_modules' in staging


def test_packaged_quick_access_installer_is_discoverable_from_immutable_builds():
    source = (ROOT / "src/bc250cc/infrastructure/dependencias_repository.py").read_text(encoding="utf-8")
    assert "Path('/usr/bin/bc250-control-center-decky-install')" in source
