from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_game_mode_accepts_cyan_compatibility_action_shape():
    source = (ROOT / "privileged/helpers/bc250-steamos-game-helper").read_text()
    assert "action == 'set-cyan-compatibility'" in source
    assert "values[0] in {'smu', 'kernel'}" in source
    assert "values[1] in {'busy-flag', 'process', 'kernel'}" in source


def test_decky_bootstrap_prepares_jq_before_official_installer():
    from bc250cc.infrastructure.decky_quick_access import build_decky_bootstrap_command

    command = build_decky_bootstrap_command("/tmp/install-local.sh")
    assert "command -v jq" in command
    assert "pacman -S --needed --noconfirm jq" in command


def test_oberon_builder_contains_current_gcc_compatibility_patch():
    source = (ROOT / "src/bc250cc/infrastructure/governor_install_shell.py").read_text()
    assert "yaml_cpp_emitter" in source
    assert "#include <cstdint>" in source


def test_dependency_scripts_declare_decky_and_dbus_runtime_requirements():
    scripts_root = ROOT / "packaging/common/os-scripts"
    for family in ("arch", "debian", "fedora", "bazzite", "steamos", "alpine", "gentoo"):
        source = (scripts_root / family / "prepare-dependencies.sh").read_text()
        assert "jq" in source, family
        assert "verify_command jq" in source, family


def test_bazzite_reboot_notice_is_explicit_and_trilingual():
    source = (
        ROOT / "packaging/common/os-scripts/bazzite/prepare-dependencies.sh"
    ).read_text(encoding="utf-8")
    assert "REBOOT REQUIRED / REINICIO REQUERIDO / ТРЕБУЕТСЯ ПЕРЕЗАГРУЗКА" in source
    assert "run ONLY 'NCT sensors and PWM'" in source
    assert "ejecuta ÚNICAMENTE 'NCT sensors and PWM'" in source
    assert "запустите ТОЛЬКО 'NCT sensors and PWM'" in source


def test_debian_governor_keeps_openrc_away_from_systemd_for_busctl():
    source = (ROOT / "packaging/common/os-scripts/debian/prepare-dependencies.sh").read_text()
    assert "if bc250_openrc_active" in source
    assert "apt-get install -y elogind" in source
    assert "apt-get install -y systemd" in source
    assert "verify_command busctl" in source
