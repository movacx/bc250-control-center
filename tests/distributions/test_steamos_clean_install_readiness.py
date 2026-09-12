from __future__ import annotations

import subprocess
from pathlib import Path

import bc250cc.infrastructure.dependencias_repository as dependencies_module
from bc250cc.infrastructure.dependencias_repository import (
    STEAMOS_CORE_UNLOCK_REVIEWED_COMMIT,
    STEAMOS_CU_REVIEWED_COMMIT,
    STEAMOS_FIX_REVIEWED_COMMIT,
    STEAMOS_SMU_OC_REVIEWED_COMMIT,
    DependenciasRepository,
)
from bc250cc.platform.packages.strategies.factory import create_os_repository


class SteamHost:
    def __init__(self, root: Path):
        self.root = root

    def _os_release(self):
        return {
            "ID": "steamos",
            "ID_LIKE": "arch",
            "VERSION_ID": "3.9",
            "PRETTY_NAME": "SteamOS 3.9",
        }

    def _command_path(self, _name):
        return ""

    def _tool_dir(self):
        return self.root / "ResourceTools"


def _repository(tmp_path: Path, monkeypatch):
    host = SteamHost(tmp_path)
    os_repository = create_os_repository(host)
    repository = DependenciasRepository()
    repository.estado_herramientas_cache = None
    repository._configured_gpu_governor = lambda _preference=None: {
        "selected": "cyan-skillfish-governor-smu"
    }
    repository._os_repository = lambda: os_repository
    repository.estado_herramientas_bc250 = lambda: {}
    repository._tool_dir = host._tool_dir
    repository.config_paths = lambda: {
        "config": str(tmp_path / "config.json"),
        "perfiles": str(tmp_path / "profiles.json"),
        "historial": str(tmp_path / "history.jsonl"),
    }
    repository._governor_config_helper_path = lambda: (
        "/usr/libexec/bc250-control-center/bc250-governor-config-helper"
    )
    repository._comando_preparar_nct6687_control_pwm = lambda: 'echo "prepare pwm"'
    repository._abrir_terminal = lambda command, _title: command
    monkeypatch.setattr(
        dependencies_module,
        "ensure_no_incompatible_governors",
        lambda *args, **kwargs: [],
    )
    return repository


def test_steamos_prepare_everything_is_userspace_first_and_reproducible(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    command = repository.instalar_dependencias_bc250(include_pwm=True)

    # Generic user-space preparation does not clone, inspect or mutate the
    # separate kernel compatibility backend.
    assert "Building and installing the validated SteamOS fixes" not in command
    assert "patch-driver.sh" not in command
    assert STEAMOS_FIX_REVIEWED_COMMIT not in command
    assert "bc250-mesh-shader.sh" not in command
    assert f"/usr/bin/bash {tmp_path}/ResourceTools/bc250-steamos/bc250-mesh-shader.sh" not in command

    # Hardware-facing source checkouts are pinned on SteamOS so a clean install
    # is reproducible and cannot silently start running a newer upstream commit.
    for commit in (
        STEAMOS_CU_REVIEWED_COMMIT,
        STEAMOS_SMU_OC_REVIEWED_COMMIT,
        STEAMOS_CORE_UNLOCK_REVIEWED_COMMIT,
    ):
        assert commit in command

    # The full workflow is protected by the SteamOS root-state guard.
    assert "with-steamos-writable-root.sh" in command
    result = subprocess.run(
        ["bash", "-n", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_explicit_steamos_compatibility_action_is_separate_and_pinned(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    command = repository.preparar_compatibilidad_steamos()

    assert STEAMOS_FIX_REVIEWED_COMMIT in command
    assert "Building and installing the validated SteamOS fixes" in command
    assert "Staging protected SteamOS AMDGPU backend" in command
    assert "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/patch-driver.sh" in command
    assert "bc250-update-persistence.sh bc250-storage.sh" in command
    assert "archive --format=tar" in command
    # Only the atomic root-owned staging operation opens /usr.  The long
    # upstream build runs afterwards from the protected copy, not directly
    # from ResourceTools.
    assert "with-steamos-writable-root.sh" in command
    assert "sudo /usr/bin/bash /usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/install.sh" in command
    assert f"/usr/bin/bash {tmp_path}/ResourceTools/bc250-steamos/bc250-audio-fix/fetch-sources.sh" in command
    assert f"/usr/bin/bash {tmp_path}/ResourceTools/bc250-steamos/bc250-audio-fix/build.sh" in command
    assert f"sudo /usr/bin/bash {tmp_path}/ResourceTools" not in command
    assert "Do not close this window; the process is still running." in command
    assert "Configuration and compilation can take a while." in command
    assert f"sudo /usr/bin/bash {tmp_path}/ResourceTools/bc250-steamos" not in command
    assert "bc250-mesh-shader.sh" in command
    assert "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-mesh-shader.sh" in command
    result = subprocess.run(
        ["bash", "-n", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_steamos_graphics_status_never_updates_or_executes_the_checkout(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    command = repository.gestionar_graficos_steamos("status")

    assert "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-mesh-shader.sh status-json" in command
    assert "git clone" not in command
    assert "archive --format=tar" not in command
    assert f"/usr/bin/bash {tmp_path}/ResourceTools" not in command


def test_steamos_graphics_install_stages_the_pin_before_protected_setup(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    command = repository.gestionar_graficos_steamos("install")

    assert STEAMOS_FIX_REVIEWED_COMMIT in command
    assert "archive --format=tar" in command
    assert "bc250-mesh-shader.sh setup" in command
    assert "/usr/libexec/bc250-control-center/steamos-amdgpu-backend" in command
    assert f"/usr/bin/bash {tmp_path}/ResourceTools" not in command
    result = subprocess.run(
        ["bash", "-n", "-c", command], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_steamos_toolkit_inventory_is_read_only_and_pinned(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    command = repository.diagnostico_steamos()

    assert " status" in command
    assert "patch-driver.sh status" in command
    assert "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-audio-fix/patch-driver.sh" in command
    assert "protected SteamOS AMDGPU backend is unavailable or untrusted" in command
    # The expected revision is checked against the root-owned stage marker;
    # it is not used to refresh or execute a ResourceTools checkout.
    assert STEAMOS_FIX_REVIEWED_COMMIT in command
    assert "git clone" not in command
    assert "git archive" not in command
    assert "ResourceTools/bc250-steamos" not in command
    assert "initramfs" not in command
    assert "steamos-readonly disable" not in command
    assert "Native BC250 Control Center SteamOS diagnostics" in command
    assert "bc250-toolkit.sh status" not in command
    assert "amdgpu.sched_policy=2" in command
    assert "reboot is pending" in command
    assert "/tmp/bc250-steamos-reconciled-amdgpu.last" not in command
    assert "bc250-amdgpu-diagnostic.XXXXXX" in command
    assert "UMR_DATABASE_PATH" in command
    result = subprocess.run(
        ["bash", "-n", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_steamos_umr_selector_is_derived_from_the_validated_database(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    selector = repository._steamos_cu_env_shell()
    assert "--print-selector" in selector
    assert 'export UMR_ASIC="${UMR_ASIC:-$(' in selector
    assert "UMR_ASIC=cyan_skillfish.gfx1010" not in selector
    assert "UMR_ASIC=cyan_skillfish.gfx1013" not in selector


def test_steamos_fan_source_is_pinned_and_root_guarded():
    source = Path(
        "packaging/common/os-scripts/steamos/prepare-fan-pwm.sh"
    ).read_text(encoding="utf-8")
    assert "163ffdcc3928a2bb04acdf9607e45f98eeb46b8a" in source
    assert "bc250_steamos_unlock_root" in source
    assert "bc250_steamos_restore_root" in source
    assert "bc250_stage_reviewed_git_tree" in source
    assert "checkout --detach FETCH_HEAD" not in source


def test_install_local_restores_steamos_root_state_on_exit():
    source = Path("scripts/install-local.sh").read_text(encoding="utf-8")
    assert "steamos-root.sh" in source
    assert "bc250_steamos_unlock_root" in source
    assert "bc250_steamos_restore_root" in source


def test_new_steamos_workflow_copy_is_translated_in_every_supported_language():
    from frontends.desktop.i18n.interface_catalog import INTERFACE_TRANSLATIONS

    keys = (
        "Install or update the SteamOS user-space/runtime components, Cyan, UMR and BC-250 tools. The high-impact amdgpu/initramfs compatibility repair stays a separate explicit action.",
        "Check SteamOS compatibility",
        "Prepare SteamOS compatibility",
        "Prepare SteamOS kernel compatibility",
        "This explicit SteamOS repair builds and installs a kernel-matched amdgpu override for DisplayPort/audio, GPU telemetry and GFX1013 compute-queue support. It regenerates initramfs and requires a reboot. If exact headers are unavailable, the upstream fallback can require about 40 GiB of temporary space. The legacy mesh/task RADV path is not installed.",
        "Opened the explicit SteamOS kernel compatibility workflow. Review the terminal result and reboot only when it reports a successful installation.",
        "SteamOS compatibility",
        "Could not prepare SteamOS compatibility",
        "Running kernel",
        "Kernel change",
        "amdgpu override + initramfs",
        "Not installed",
        "Reboot",
        "Required after installation",
    )
    from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
    for key in keys:
        assert key in INTERFACE_TRANSLATIONS, key
        for language in SUPPORTED_LANGUAGES:
            assert tr(key, language).strip(), (key, language)
            if language != "en" and key != "amdgpu override + initramfs":
                assert tr(key, language) != key, (key, language)


def test_gfx1013_steamos_state_copy_distinguishes_kernel_half_from_complete_async_compute():
    from frontends.desktop.i18n.interface_catalog import INTERFACE_TRANSLATIONS

    keys = (
        "Async compute detected",
        "Kernel half ready",
        "A GFX1013 RADV path was detected, but the verified SteamOS kernel compute repair is not active. Do not use the patched RADV driver until the kernel half is active; upstream warns that Mesa without the kernel repair can hang the GPU.",
        "The verified SteamOS kernel repair and an external GFX1013 RADV path were both detected. Control Center can report this combination but does not take ownership of the external RADV files.",
        "The SteamOS kernel compute repair is active, but GFX1013 async compute is not complete until a matching Mesa/RADV compute patch is installed. Control Center does not install the legacy mesh/task path.",
    )
    from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
    for key in keys:
        assert key in INTERFACE_TRANSLATIONS
        for language in SUPPORTED_LANGUAGES:
            assert tr(key, language).strip()
            if language != "en":
                assert tr(key, language) != key


def test_steamos_cyan_uses_verified_release_instead_of_aur_package_layer():
    source = Path(
        "packaging/common/os-scripts/steamos/prepare-dependencies.sh"
    ).read_text(encoding="utf-8")
    runtime_block = source.split("install_runtime() {", 1)[1].split("}\n", 1)[0]
    governor_block = source.split("install_governor() {", 1)[1].split("}\n", 1)[0]
    assert "ensure_aur_helper" not in runtime_block
    assert "install_aur_package cyan-skillfish-governor-smu" not in governor_block
    assert "verified official upstream release" in governor_block


def test_install_local_helper_window_does_not_refresh_pacman_when_gui_deps_exist():
    source = Path("scripts/install-local.sh").read_text(encoding="utf-8")
    helper = source.split("install_privileged_pwm_components() {", 1)[1]
    steamos_window = helper.split("if is_steamos_install_local; then", 1)[1].split("\n  fi\n", 1)[0]
    assert "bc250_steamos_unlock_root" in steamos_window
    assert "prepare_steamos_pacman_install_local" not in steamos_window
    assert 'install_privileged_pwm_components\nif is_steamos_install_local; then\n  restore_steamos_install_root 0' in source


def test_clean_steamos_cyan_is_staged_before_binary_guard(tmp_path, monkeypatch):
    """Regression for R21: a clean SteamOS host starts with no Cyan binary."""
    repository = _repository(tmp_path, monkeypatch)
    command = repository.instalar_dependencias_bc250(include_pwm=True)

    stage = command.index("== Preparing official Cyan SMU frequency-reporting fix ==")
    binary = command.index("bc250_cyan_binary=/usr/local/bin/cyan-skillfish-governor-smu")
    guard = command.index('test -x "$bc250_cyan_binary"')
    assert stage < binary < guard
    assert "Cyan frequency-fix binary is missing" in command
    assert "command -v cyan-skillfish-governor-smu" not in command[stage:guard]


def test_steamos_cyan_source_and_release_are_pinned_for_reproducible_clean_install(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    command = repository.instalar_dependencias_bc250(include_pwm=False)

    assert dependencies_module.STEAMOS_CYAN_REVIEWED_COMMIT in command
    assert f"BC250_CYAN_RELEASE_TAG={dependencies_module.STEAMOS_CYAN_REVIEWED_RELEASE}" in command
    assert dependencies_module.STEAMOS_CYAN_REVIEWED_RELEASE == "v0.4.12"
