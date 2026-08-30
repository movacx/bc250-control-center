import subprocess
from pathlib import Path

import pytest

import bc250cc.infrastructure.dependencias_repository as dependencies_module
from bc250cc.infrastructure.dependencias_repository import (
    STANDARD_CU_REVIEWED_COMMIT,
    STEAMOS_SMU_OC_REVIEWED_COMMIT,
    DependenciasRepository,
)
from bc250cc.infrastructure.governor_conflicts import CYAN_GOVERNOR, OBERON_GOVERNOR
from bc250cc.platform.packages.strategies.factory import create_os_repository

DISTROS = (
    ("arch", {"ID": "arch", "PRETTY_NAME": "Arch Linux"}, False),
    ("manjaro", {"ID": "manjaro", "ID_LIKE": "arch", "PRETTY_NAME": "Manjaro"}, False),
    ("cachyos", {"ID": "cachyos", "ID_LIKE": "arch", "PRETTY_NAME": "CachyOS"}, False),
    ("debian", {"ID": "debian", "PRETTY_NAME": "Debian GNU/Linux"}, False),
    ("ubuntu", {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu"}, False),
    ("mint", {"ID": "linuxmint", "ID_LIKE": "ubuntu debian", "PRETTY_NAME": "Linux Mint"}, False),
    ("fedora", {"ID": "fedora", "PRETTY_NAME": "Fedora Linux"}, False),
    ("nobara", {"ID": "nobara", "ID_LIKE": "fedora", "PRETTY_NAME": "Nobara Linux"}, False),
    (
        "bazzite",
        {"ID": "bazzite", "ID_LIKE": "fedora", "VARIANT_ID": "bazzite", "PRETTY_NAME": "Bazzite"},
        True,
    ),
    (
        "kinoite",
        {"ID": "fedora", "ID_LIKE": "fedora", "VARIANT_ID": "kinoite", "PRETTY_NAME": "Fedora Kinoite"},
        True,
    ),
    ("steamos", {"ID": "steamos", "ID_LIKE": "arch", "PRETTY_NAME": "SteamOS"}, False),
    ("alpine", {"ID": "alpine", "PRETTY_NAME": "Alpine Linux"}, False),
    ("gentoo", {"ID": "gentoo", "PRETTY_NAME": "Gentoo Linux"}, False),
)

PRE_EXTRACTION_COMMAND_SHA256 = {
    # The reviewed generic CU backend is root-staged on all mutable and
    # immutable desktop families. Keep this command corpus exact so future
    # packaging edits cannot silently change a privileged preparation flow.
    ("arch", CYAN_GOVERNOR): "77e2c723b8e04a08a0b8b5e51ab4af80587300f908151d9f283763de4339ed5a",
    ("arch", OBERON_GOVERNOR): "4ab1949b026358d6a2f3f9432997306b6276c0e9cf6b3e10008106740505d6c4",
    ("manjaro", CYAN_GOVERNOR): "c09a6f64abc634be11668cb0f003a5e33e6fe9622239f9a08a9d16e7d9d1e892",
    ("manjaro", OBERON_GOVERNOR): "ab5d2f00e8e42aaa8228336fb8c6ba81f6e13be035ccfbdce63b60b952653ea5",
    ("cachyos", CYAN_GOVERNOR): "b30757721668fa011caa34ac3ff9f6e7ee786b111cbf36a4179e1e622290c6d7",
    ("cachyos", OBERON_GOVERNOR): "9e8d3f892146e0ec98be9bd7a1fad7c02a02ae271f1d499ec10c0b4567bee20a",
    ("debian", CYAN_GOVERNOR): "ec24b5e61d1c477d1a2741f38c5cb24a6ccd09368f3fdcd1d5f8549a26d4bdd6",
    ("debian", OBERON_GOVERNOR): "d1fe53910bc1090cc02733a62bcfc824aece628fe03cabaf7fceb86ceabafbba",
    ("ubuntu", CYAN_GOVERNOR): "5933b983a9cb84df8a1075877823c923da84abc9b5805884141195d1dd9a57c2",
    ("ubuntu", OBERON_GOVERNOR): "9145ec1587b0583c5f38f08e15b96f2977c1ecdf4474ee27901a8909f5d30906",
    ("mint", CYAN_GOVERNOR): "84345645fa03509860deb3f95d9c14f857ea911e18149faf400ea5fec41ff9d5",
    ("mint", OBERON_GOVERNOR): "ed902214707b7974d26428137ba886fa20adbf612c055098bb7d8f100887171b",
    ("fedora", CYAN_GOVERNOR): "ac04ffc145548c60879fb55a71b475012ab07592adf4b314823f6fda5d0edf2a",
    ("fedora", OBERON_GOVERNOR): "facca4f57bf739b71ba313aaf4c692699f51c76ca66d46b8ab223769c62a70cc",
    ("nobara", CYAN_GOVERNOR): "7e7eb8b2fe5eb3e456e9264b792c0a8a84eccd5b051ac2dc758f255b6457e88a",
    ("nobara", OBERON_GOVERNOR): "f50a5acf2927fbadb9071e10c8921afd4574793560449dcebb778126a675b20c",
    ("bazzite", CYAN_GOVERNOR): "dbccedd87610fbe9bf0cc00010a6247a6ed0b5f373f59add875f40fb1ea494c6",
    ("bazzite", OBERON_GOVERNOR): "4a3f131963765a35d47e930990a5cb36addc45894b4ce22c386b7c33ebcd3eba",
    ("kinoite", CYAN_GOVERNOR): "c107707a4666da7b88af0c5c38698dfa1d92bff7ddb80f8ef913bda653ffdc20",
    ("kinoite", OBERON_GOVERNOR): "f62283130d84083496d690312e44dda0b920d628b65dbb05920db867d75860d0",
    ("steamos", CYAN_GOVERNOR): "509fb5c6b35fe0fa803b1739d55f10ff6e33155a0b287913eced01aeeee5109d",
    ("steamos", OBERON_GOVERNOR): "f7ba661e15aee276cf174dbf126547ca3e620a5377e66c24f5adf998b687c42f",
    ("alpine", CYAN_GOVERNOR): "62407f922390e5e4a6b1e966d4048db331069c6c1805f3f838a0b47885935ff7",
    ("alpine", OBERON_GOVERNOR): "5a95b90d9525c75bd887b1d096a490dc9a62b2a391b508a8b0331c74ae263ff9",
    ("gentoo", CYAN_GOVERNOR): "daf4dd7922cf3290ab8c16bf0bf585e3eaf99674e67580921f515a83ed12fefd",
    ("gentoo", OBERON_GOVERNOR): "e337374ed7dc83c11259837e60418dc16eccceabe8a8dd8217ea3643efb70168",
}


class FakeHost:
    def __init__(self, release, root: Path, has_rpm_ostree: bool):
        self.release = release
        self.root = root
        self.has_rpm_ostree = has_rpm_ostree

    def _os_release(self):
        return self.release

    def _command_path(self, name):
        if name == "rpm-ostree" and self.has_rpm_ostree:
            return "/usr/bin/rpm-ostree"
        return ""

    def _tool_dir(self):
        return self.root / "ResourceTools"


def _bash_syntax(command: str):
    return subprocess.run(
        ["bash", "-n", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )


def _build_prepare_command(tmp_path, release, has_rpm_ostree, governor, monkeypatch, components=None):
    host = FakeHost(release, tmp_path, has_rpm_ostree)
    os_repository = create_os_repository(host)
    repository = DependenciasRepository()
    repository.estado_herramientas_cache = None
    repository._configured_gpu_governor = lambda _preference=None: {"selected": governor}
    repository._os_repository = lambda: os_repository
    repository.estado_herramientas_bc250 = lambda: {}
    repository._tool_dir = host._tool_dir
    repository.config_paths = lambda: {
        "config": str(tmp_path / "config.json"),
        "perfiles": str(tmp_path / "profiles.json"),
        "historial": str(tmp_path / "history.jsonl"),
    }
    repository._governor_config_helper_path = lambda: "/usr/libexec/bc250-control-center/bc250-governor-config-helper"
    repository._comando_preparar_nct6687_control_pwm = lambda: 'echo "prepare pwm"'
    repository._abrir_terminal = lambda command, _title: command
    monkeypatch.setattr(
        dependencies_module,
        "ensure_no_incompatible_governors",
        lambda *args, **kwargs: [],
    )
    return repository.instalar_dependencias_bc250(
        governor_preference=governor,
        include_pwm=True,
        components=components,
    )


@pytest.mark.parametrize("governor", (CYAN_GOVERNOR, OBERON_GOVERNOR))
@pytest.mark.parametrize("_name,release,has_rpm_ostree", DISTROS)
def test_complete_prepare_command_is_valid_bash_for_every_supported_distribution(
    tmp_path,
    monkeypatch,
    _name,
    release,
    has_rpm_ostree,
    governor,
):
    command = _build_prepare_command(
        tmp_path / _name / governor,
        release,
        has_rpm_ostree,
        governor,
        monkeypatch,
    )

    assert "fi;;" not in command
    assert ";; echo" not in command
    # Generic Prepare dependencies must never cross the boot/kernel/Mesa
    # integration boundary for DryhoppedIPA. SteamOS uses its separately
    # audited kernel backend; legacy mesh/task RADV is never invoked here.
    assert "DryhoppedIPA/bc250-gfx1013-fix" not in command
    assert "bc250-mesh-shader.sh" not in command
    # The Bazzite-specific protected-path contract is asserted below.  The
    # generated command is otherwise validated syntactically for every route.
    result = _bash_syntax(command)
    assert result.returncode == 0, f"{_name}/{governor}: {result.stderr}"


def test_steamos_prepare_honors_selected_user_space_components(tmp_path, monkeypatch):
    release = {"ID": "steamos", "ID_LIKE": "arch", "PRETTY_NAME": "SteamOS"}
    command = _build_prepare_command(
        tmp_path, release, False, CYAN_GOVERNOR, monkeypatch,
        components={"runtime", "cpu_oc"},
    )

    assert "Preparing bc250_smu_oc source" in command
    assert "chmod -R u+rwX,go+rX,go-w" in command
    assert "Preparing official bc250-core-unlock source" not in command
    assert "Preparing 40CU live manager" not in command
    assert "Preparing official Cyan SMU" not in command
    assert "prepare pwm" not in command
    assert "patch-driver.sh status" not in command
    assert "bc250-audio-fix" not in command
    assert "--component stress" in command
    result = _bash_syntax(command)
    assert result.returncode == 0, result.stderr


def test_runtime_only_does_not_prepare_stress(tmp_path, monkeypatch):
    command = _build_prepare_command(
        tmp_path,
        {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu"},
        False,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime"},
    )
    assert "--component stress" not in command


def test_alpine_rejects_explicit_cpu_oc_before_constructing_a_terminal_workflow(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="CPU OC is unavailable on Alpine"):
        _build_prepare_command(
            tmp_path,
            {"ID": "alpine", "PRETTY_NAME": "Alpine Linux"},
            False,
            CYAN_GOVERNOR,
            monkeypatch,
            components={"runtime", "cpu_oc"},
        )


def test_alpine_default_preparation_skips_only_the_unavailable_cpu_component(tmp_path, monkeypatch):
    command = _build_prepare_command(
        tmp_path,
        {"ID": "alpine", "PRETTY_NAME": "Alpine Linux"},
        False,
        CYAN_GOVERNOR,
        monkeypatch,
        components=None,
    )

    assert "scripts/alpine/prepare-dependencies.sh" in command
    assert "--component stress" not in command
    assert _bash_syntax(command).returncode == 0


def test_gentoo_runtime_preparation_constructs_a_valid_portage_command(tmp_path, monkeypatch):
    command = _build_prepare_command(
        tmp_path,
        {"ID": "gentoo", "PRETTY_NAME": "Gentoo Linux"},
        False,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime"},
    )

    assert "scripts/gentoo/prepare-dependencies.sh" in command
    assert "--component runtime" in command
    assert _bash_syntax(command).returncode == 0


def test_steamos_runtime_only_does_not_cross_optional_backend_boundaries(
    tmp_path, monkeypatch
):
    command = _build_prepare_command(
        tmp_path,
        {"ID": "steamos", "ID_LIKE": "arch", "PRETTY_NAME": "SteamOS"},
        False,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime"},
    )

    for unexpected in (
        "Preparing bc250_smu_oc source",
        "Preparing official bc250-core-unlock source",
        "Preparing 40CU",
        "install-umr",
        "Preparing official Cyan SMU",
        "prepare pwm",
        "patch-driver.sh",
        "bc250-audio-fix",
    ):
        assert unexpected not in command
    assert _bash_syntax(command).returncode == 0


def test_steamos_umr_and_cu_manager_stages_remain_independent(tmp_path, monkeypatch):
    release = {"ID": "steamos", "ID_LIKE": "arch", "PRETTY_NAME": "SteamOS"}
    umr_only = _build_prepare_command(
        tmp_path / "umr", release, False, CYAN_GOVERNOR, monkeypatch,
        components={"runtime", "umr"},
    )
    cu_manager = _build_prepare_command(
        tmp_path / "cu", release, False, CYAN_GOVERNOR, monkeypatch,
        components={"runtime", "cu_manager"},
    )

    assert "Preparing 40CU backend required for UMR validation" in umr_only
    assert "Updated installed CU service backend" not in umr_only
    assert "Verifying SteamOS 40CU UMR selector" not in umr_only
    assert "Preparing 40CU live manager" in cu_manager
    assert "Updated installed CU service backend" in cu_manager
    assert "Verifying SteamOS 40CU UMR selector" in cu_manager
    assert "patch-driver.sh" not in umr_only + cu_manager
    assert _bash_syntax(umr_only).returncode == 0
    assert _bash_syntax(cu_manager).returncode == 0


def test_cachyos_umr_only_leaves_the_protected_cu_backend_ready(tmp_path, monkeypatch):
    command = _build_prepare_command(
        tmp_path,
        {"ID": "cachyos", "ID_LIKE": "arch", "PRETTY_NAME": "CachyOS"},
        False,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime", "umr"},
    )

    assert "Preparing 40CU backend required for UMR validation" in command
    assert "Staging protected generic CU backend" in command
    assert "/var/lib/bc250-control-center/bc250-cu-live-manager" in command
    assert _bash_syntax(command).returncode == 0


def test_bazzite_cpu_source_uses_exact_commit_even_without_git(tmp_path, monkeypatch):
    command = _build_prepare_command(
        tmp_path,
        {
            "ID": "bazzite",
            "ID_LIKE": "fedora",
            "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        True,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime", "cpu_oc"},
    )

    assert STEAMOS_SMU_OC_REVIEWED_COMMIT in command
    assert ".bc250-source-revision" in command
    assert "bc250_smu_oc/archive/refs/heads/main.tar.gz" not in command


def test_bazzite_standard_cu_source_is_pinned_and_write_actions_stay_separate(
    tmp_path, monkeypatch
):
    command = _build_prepare_command(
        tmp_path,
        {
            "ID": "bazzite",
            "ID_LIKE": "fedora",
            "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        True,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime", "cu_manager"},
    )

    assert STANDARD_CU_REVIEWED_COMMIT in command
    assert ".bc250-source-revision" in command
    assert "bc250-cu-live-manager/archive/refs/heads/main.tar.gz" not in command
    assert " enable all" not in command
    assert " stock-dispatch" not in command
    assert " apply-service" not in command


def test_mutable_distribution_standard_cu_checkout_is_detached_at_reviewed_commit(
    tmp_path, monkeypatch
):
    command = _build_prepare_command(
        tmp_path,
        {"ID": "fedora", "PRETTY_NAME": "Fedora Linux"},
        False,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime", "cu_manager"},
    )

    assert f"fetch --depth 1 origin {STANDARD_CU_REVIEWED_COMMIT}" in command
    assert "checkout --detach --force FETCH_HEAD" in command
    assert "git -C" in command
    assert " pull --ff-only" not in command
    assert "Staging protected generic CU backend" in command


def test_generic_cu_preparation_promotes_the_reviewed_backend_to_bazzite_varlib(
    tmp_path, monkeypatch
):
    command = _build_prepare_command(
        tmp_path,
        {
            "ID": "bazzite", "ID_LIKE": "fedora", "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        True,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime", "cu_manager"},
    )

    assert "Staging protected generic CU backend" in command
    assert "/var/lib/bc250-control-center/bc250-cu-live-manager" in command
    assert "/usr/libexec/bc250-control-center/bc250-cu-live-manager" not in command


def test_bazzite_preparation_layers_umr_when_umr_is_selected(tmp_path, monkeypatch):
    command = _build_prepare_command(
        tmp_path,
        {
            "ID": "bazzite", "ID_LIKE": "fedora", "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        True,
        CYAN_GOVERNOR,
        monkeypatch,
        components={"runtime", "umr", "cu_manager"},
    )

    assert "--component umr" in command
    assert "UMR was staged in the Bazzite deployment" in command
    assert "Staging protected generic CU backend" in command
    assert "/var/lib/bc250-control-center/bc250-cu-live-manager" in command
    assert _bash_syntax(command).returncode == 0


def test_bazzite_defers_pwm_module_build_until_the_layered_dkms_deployment_is_booted(
    tmp_path, monkeypatch
):
    command = _build_prepare_command(
        tmp_path,
        {
            "ID": "bazzite", "ID_LIKE": "fedora", "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        True,
        CYAN_GOVERNOR,
        monkeypatch,
    )

    assert "fan PWM preparation will run after the Bazzite reboot activates dkms" in command
    assert 'if [ "$BC250_REBOOT_REQUIRED" = "1" ]' in command
    assert _bash_syntax(command).returncode == 0


def test_bazzite_standalone_cpu_cu_and_umr_workflows_use_reviewed_archives(
    tmp_path
):
    host = FakeHost(
        {
            "ID": "bazzite",
            "ID_LIKE": "fedora",
            "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        tmp_path,
        True,
    )
    os_repository = create_os_repository(host)
    repository = DependenciasRepository()
    repository._os_repository = lambda: os_repository
    repository._tool_dir = host._tool_dir
    repository._command_path = lambda _name: ""
    repository.estado_herramientas_bc250 = lambda: {
        "bc250_detect": "",
        "smu_oc_exists": False,
        "cu_manager_exists": False,
    }
    repository._abrir_terminal = lambda command, _title: command

    cpu = repository.instalar_cpu_oc()
    cu = repository.instalar_cu_manager()
    umr = repository.instalar_umr()

    assert STEAMOS_SMU_OC_REVIEWED_COMMIT in cpu
    assert STANDARD_CU_REVIEWED_COMMIT in cu
    assert STANDARD_CU_REVIEWED_COMMIT in umr
    assert "Staging protected generic CU backend" in umr
    assert "/var/lib/bc250-control-center/bc250-cu-live-manager" in umr
    for command in (cpu, cu, umr):
        assert ".bc250-source-revision" in command
        assert "/archive/refs/heads/main.tar.gz" not in command


def test_cachyos_installed_umr_still_repairs_a_missing_protected_backend(tmp_path):
    host = FakeHost(
        {"ID": "cachyos", "ID_LIKE": "arch", "PRETTY_NAME": "CachyOS"},
        tmp_path,
        False,
    )
    os_repository = create_os_repository(host)
    repository = DependenciasRepository()
    repository._os_repository = lambda: os_repository
    repository._tool_dir = host._tool_dir
    repository._command_path = lambda name: "/usr/bin/umr" if name == "umr" else ""
    repository.estado_herramientas_bc250 = lambda: {
        "cu_privileged_backend_ready": False,
    }
    repository._abrir_terminal = lambda command, _title: command

    command = repository.instalar_umr()

    assert "Staging protected generic CU backend" in command
    assert "/var/lib/bc250-control-center/bc250-cu-live-manager" in command
    assert _bash_syntax(command).returncode == 0


def test_all_distribution_shell_scripts_are_valid_bash():
    scripts = sorted(Path("packaging/common/os-scripts").rglob("*.sh"))
    assert scripts
    failures = []
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures.append(f"{script}: {result.stderr}")
    assert failures == []
