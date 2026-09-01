from pathlib import Path

import pytest

from bc250cc.infrastructure.cpu_repository import CPURepository
from bc250cc.infrastructure.cu_repository import CURepository
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.governor_conflicts import GovernorConflictError
from bc250cc.infrastructure.gpu.governor_toml import (
    GOVERNOR_DEFAULT_SAFE_POINTS,
    voltage_profile,
)
from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.infrastructure.sistema_repository import SistemaRepository
from bc250cc.platform.init.services import InitManagerState


def test_installer_blocks_before_opening_terminal_when_oberon_is_active(monkeypatch):
    class Config:
        @staticmethod
        def leer_config():
            return {"gpu_governor": "cyan-skillfish-governor-smu"}

    class Repository(DependenciasRepository):
        estado_herramientas_cache = None
        configuracion = Config()

        def _ejecutar(self, command, timeout=3):
            if command == ["systemctl", "is-active", "oberon-governor.service"]:
                return 0, "active", ""
            return 1, "", "not found"

        def _abrir_terminal(self, *_args):
            raise AssertionError("installation must not start without confirmation")

    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts.shutil.which", lambda _name: None)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )
    with pytest.raises(GovernorConflictError, match="green screen"):
        Repository().instalar_governor()


def test_governor_removal_is_scoped_and_preserves_configuration():
    calls = []

    class Repository(DependenciasRepository):
        estado_herramientas_cache = None

        def _os_repository(self):
            info = type("Info", (), {"family": "debian"})()
            return type("OSRepository", (), {"info": info})()

        def _abrir_terminal(self, command, title=""):
            calls.append((command, title))
            return "terminal"

    assert Repository().desinstalar_governor("oberon-governor") == "terminal"
    command, title = calls[0]
    assert "systemctl disable --now oberon-governor.service" in command
    assert "apt-get remove -y oberon-governor" in command
    assert "rm -f /usr/local/bin/oberon-governor" in command
    assert "still has an executable" in command
    assert "was completely removed" in command
    assert "apt-get remove -y oberon-governor; fi" in command
    assert "/etc/oberon-config.yaml" not in command
    assert "bc250-core-unlock" not in command
    assert title == "Desinstalar oberon-governor"


def test_governor_removal_rejects_auto_or_unknown_selection():
    with pytest.raises(ValueError):
        DependenciasRepository().desinstalar_governor("auto")
    with pytest.raises(ValueError):
        DependenciasRepository().desinstalar_governor("anything; reboot")


def test_governor_switch_disables_the_other_service_before_activation(monkeypatch):
    captured = {}

    class Repository(DependenciasRepository):
        estado_herramientas_cache = None
        estado_bc250_cache = None

        @staticmethod
        def _os_repository():
            info = type("Info", (), {"family": "arch"})()
            return type(
                "OSRepository",
                (), {"info": info, "install_governor_command": staticmethod(lambda: "echo install-cyan")},
            )()

        @staticmethod
        def _cyan_upstream_runtime_command(_repository):
            return "echo install-cyan-runtime"

        @staticmethod
        def _cyan_runtime_verification_command():
            return "echo verify-cyan"

        @staticmethod
        def _governor_activation_command(_selected, _service, _prefix):
            return "echo activate-selected"

        @staticmethod
        def _abrir_terminal(command, title):
            captured.update(command=command, title=title)
            return command

    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.ensure_no_incompatible_governors",
        lambda *_args, **_kwargs: [{"service": "oberon-governor.service"}],
    )

    command = Repository().cambiar_governor("cyan")

    assert "systemctl disable --now oberon-governor.service" in command
    assert command.index("disable --now oberon-governor.service") < command.index("install-cyan")
    assert command.index("install-cyan") < command.index("activate-selected")
    assert "only enabled and active GPU governor" in command
    assert captured["title"] == "Cambiar a cyan-skillfish-governor-smu"


@pytest.mark.parametrize(
    ("family", "package_command"),
    (
        ("ubuntu", "apt-get remove -y oberon-governor"),
        ("debian", "apt-get remove -y oberon-governor"),
        ("arch", "pacman -Rns --noconfirm oberon-governor"),
        ("manjaro", "pacman -Rns --noconfirm oberon-governor"),
        ("cachyos", "pacman -Rns --noconfirm oberon-governor"),
        ("fedora", "dnf remove -y oberon-governor"),
    ),
)
def test_governor_removal_uses_the_distribution_family_package_manager(family, package_command):
    commands = []

    class Repository(DependenciasRepository):
        estado_herramientas_cache = None

        def _os_repository(self):
            info = type("Info", (), {"family": family})()
            return type("OSRepository", (), {"info": info})()

        def _abrir_terminal(self, command, _title=""):
            commands.append(command)
            return True

    assert Repository().desinstalar_governor("oberon-governor") is True
    assert package_command in commands[0]


@pytest.mark.parametrize(
    ("family", "dependency_command"),
    (
        ("debian", "apt-get install -y"),
        ("ubuntu", "apt-get install -y"),
        ("arch", "pacman -S --needed"),
        ("manjaro", "pacman -S --needed"),
        ("cachyos", "pacman -S --needed"),
        ("fedora", "dnf install -y"),
    ),
)
def test_oberon_build_supports_every_mutable_distribution_family(tmp_path, family, dependency_command):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path
    os_repository = type(
        "OSRepository",
        (),
        {"info": type("Info", (), {"family": family, "label": family})()},
    )()

    command = repository._oberon_install_command(os_repository)

    assert dependency_command in command
    assert "gitlab.com/mothenjoyer69/oberon-governor" in command


def test_optional_recommends_report_unavailable_features(monkeypatch):
    repository = DependenciasRepository()
    monkeypatch.setattr(
        repository,
        "_command_path",
        lambda name: "/usr/bin/sensors" if name == "sensors" else "",
        raising=False,
    )
    monkeypatch.setattr("bc250cc.infrastructure.dependencias_repository.importlib.util.find_spec", lambda _name: None)
    status = repository._optional_dependency_status()
    assert status["sensors"]["available"] is True
    assert status["stress"]["available"] is False
    assert "CPU tuning" == status["stress"]["feature"]
    assert status["python3-evdev"]["available"] is False
    assert status["python3-evdev"]["feature_available"] is True
    assert status["python3-evdev"]["feature"] == "Enhanced gamepad input backend"


def test_gpu_profile_is_runtime_only_and_does_not_rewrite_persistent_toml():
    events = []

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return 500, 2000

        def _editar_governor_toml(self, *_args):
            raise AssertionError("a live profile must not rewrite persistent TOML")

        def _apply_cyan_runtime_range(self, minimum, maximum):
            events.append(("runtime", minimum, maximum))
            return "ok"

    assert Repository().aplicar_perfil_gpu(1000, 2000) == "ok"
    assert events == [("runtime", 1000, 2000)]


def test_gpu_profile_preserves_persistent_floor_while_applying_runtime_range():
    events = []

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return 500, 2000

        def _apply_cyan_runtime_range(self, minimum, maximum):
            events.append((minimum, maximum))
            return "ok"

    assert Repository().aplicar_perfil_gpu(1000, 1850) == "ok"
    assert events == [(1000, 1850)]


def test_gpu_profile_below_2000_does_not_mutate_high_point_configuration():
    events = []

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return 500, 2400

        def _apply_cyan_runtime_range(self, minimum, maximum):
            events.append((minimum, maximum))
            return "ok"

    assert Repository().aplicar_perfil_gpu(1000, 1850) == "ok"
    assert events == [(1000, 1850)]


def test_gpu_profile_reloads_cyan_once_before_applying_enabled_high_safe_point(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[frequency-range]\nmin = 500\nmax = 2000\n\n"
        "[[safe-points]]\nfrequency = 500\nvoltage = 700\n\n"
        "[[safe-points]]\nfrequency = 2000\nvoltage = 960\n\n"
        "[[safe-points]]\nfrequency = 2200\nvoltage = 1050\n",
        encoding="utf-8",
    )
    events = []

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return 500, 2000

        def _cyan_runtime_config_path(self, *, require_managed=False):
            return config

        def _reload_cyan_for_high_range(self, minimum, maximum):
            events.append(("reload", minimum, maximum))
            return True

        def _apply_cyan_runtime_range(self, minimum, maximum):
            events.append(("runtime", minimum, maximum))
            return "ok"

    assert Repository().aplicar_perfil_gpu(1000, 2200) == "ok"
    assert events == [
        ("reload", 1000, 2200),
        ("runtime", 1000, 2200),
    ]


def test_high_range_reload_requires_active_cyan_and_only_restarts_for_toml_reload():
    events = []

    class InactiveRepository(GPURepository):
        def _service_is_active(self, service):
            events.append(("active", service))
            return False

    with pytest.raises(RuntimeError, match="Cyan is not active"):
        InactiveRepository()._reload_cyan_for_high_range(1000, 2200)
    assert events == [("active", InactiveRepository._GOVERNOR_SERVICE)]

    class AlreadyLoadedRepository(GPURepository):
        def _service_is_active(self, service):
            return True

        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return 500, 2400

    assert AlreadyLoadedRepository()._reload_cyan_for_high_range(1000, 2200) is None

    ranges = iter(((500, 2000), (500, 2400)))

    class RestartedRepository(GPURepository):
        def _service_is_active(self, service):
            return True

        def _restart_governor_if_active(self, service):
            events.append(("restart", service))
            return True

        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return next(ranges)

    assert RestartedRepository()._reload_cyan_for_high_range(1000, 2200) is None
    assert ("restart", RestartedRepository._GOVERNOR_SERVICE) in events


def test_persistent_gpu_floor_does_not_change_runtime_dbus_range():
    events = []

    class Repository(GPURepository):
        def _leer_rango_governor(self, kind):
            assert kind == "Allowed"
            return 500, 2400

        def _editar_governor_toml(self, action, *arguments):
            events.append((action, *arguments))
            return "updated"

        def aplicar_rango_bc250(self, *_args):
            raise AssertionError("a persistent floor must not send a D-Bus range")

    message = Repository().fijar_piso_gpu_persistente(500)

    assert events == [("set-frequency-floor", 500)]
    assert "500 MHz" in message


def _active_governor_curve(values):
    return "\n".join(
        "\n".join(
            (
                "[[safe-points]]",
                f"frequency = {frequency}",
                f"voltage = {values[frequency]}",
                "",
            )
        )
        for frequency, _original in GOVERNOR_DEFAULT_SAFE_POINTS
    )


def test_repository_no_longer_imposes_control_center_level_three_curve(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    defaults = dict(GOVERNOR_DEFAULT_SAFE_POINTS)
    config.write_text(_active_governor_curve(defaults), encoding="utf-8")
    calls = []

    class FakeEngine:
        def __init__(self, _repository):
            pass

        def apply_range(self, minimum, maximum):
            calls.append((minimum, maximum))
            return type("Result", (), {
                "as_dict": lambda self: {},
                "current_min": minimum,
                "current_max": maximum,
                "hardware_verification": "pending-load",
                "observed_frequency": None,
            })()

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _cyan_runtime_config_path(self, *, require_managed=False):
            return config

        def estado_bc250(self, forzar=False):
            return {}

    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.CyanGpuEngine", FakeEngine)
    result = Repository().aplicar_rango_bc250(1000, 2200)

    assert calls == [(1000, 2200)]
    assert result["gpu_operation"] == {}


def test_repository_accepts_valid_interpolated_high_range_without_exact_safe_point(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(_active_governor_curve(voltage_profile(3)), encoding="utf-8")
    calls = []

    class FakeEngine:
        def __init__(self, _repository):
            pass

        def apply_range(self, minimum, maximum):
            calls.append((minimum, maximum))
            return type("Result", (), {
                "as_dict": lambda self: {"mode": "adaptive-range"},
                "current_min": minimum,
                "current_max": maximum,
                "hardware_verification": "pending-load",
                "observed_frequency": None,
            })()

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _cyan_runtime_config_path(self, *, require_managed=False):
            return config

        def estado_bc250(self, forzar=False):
            return {"current_min": 1000, "current_max": 2175}

    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.CyanGpuEngine", FakeEngine)
    result = Repository().aplicar_rango_bc250(1000, 2175)

    assert calls == [(1000, 2175)]
    assert result["gpu_operation"]["mode"] == "adaptive-range"


def test_repository_does_not_send_setrange_while_cyan_allowed_dbus_is_unavailable(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n\n"
        "[[safe-points]]\nfrequency = 1850\nvoltage = 930\n",
        encoding="utf-8",
    )
    commands = []

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _cyan_runtime_config_path(self, *, require_managed=False):
            return config

        def _leer_rango_governor(self, kind):
            return None

        def _ejecutar(self, command, timeout=3):
            commands.append(command)
            return 0, "", ""

    with pytest.raises(RuntimeError, match="Allowed range is unavailable"):
        Repository().aplicar_rango_bc250(1000, 1850)

    assert all(command[:2] == ["systemctl", "show"] for command in commands)
    assert not any("setrange" in " ".join(command).lower() for command in commands)


def test_governor_restart_is_blocked_while_oberon_is_active(monkeypatch):
    class Config:
        @staticmethod
        def leer_config():
            return {"gpu_governor": "cyan-skillfish-governor-smu"}

    class Repository(GPURepository):
        configuracion = Config()
        def _command_path(self, name):
            return f"/usr/bin/{name}"

        def _ejecutar(self, command, timeout=3):
            if command == ["systemctl", "is-active", "oberon-governor.service"]:
                return 0, "active", ""
            return 1, "", "not found"

        def _abrir_terminal(self, *_args):
            raise AssertionError("restart must not start")

    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts.shutil.which", lambda _name: None)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )
    with pytest.raises(GovernorConflictError):
        Repository().controlar_governor("reiniciar")


def test_governor_activation_recovers_a_core_unlock_service_mask(monkeypatch):
    captured = {}

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return "cyan-skillfish-governor-smu"

        def _command_path(self, _name):
            return "/usr/local/bin/cyan-skillfish-governor-smu"

        def _abrir_terminal(self, command, title):
            captured.update(command=command, title=title)
            return "terminal"

    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.ensure_no_incompatible_governors",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: InitManagerState("systemd", True, "test"),
    )

    assert Repository().controlar_governor("activar") == "terminal"
    command = captured["command"]
    assert command.index("systemctl unmask") < command.index("systemctl enable --now")
    assert "systemctl reset-failed cyan-skillfish-governor-smu.service" in command
    assert "journalctl -b -u cyan-skillfish-governor-smu.service -n 80" in command
    assert captured["title"] == "Activar cyan-skillfish-governor-smu"


def test_external_numeric_values_cannot_be_injected_into_privileged_commands():
    with pytest.raises((TypeError, ValueError)):
        CPURepository().comando_cpu_oc_temporal_embebido("3500; reboot", 1050, 90)
    with pytest.raises((TypeError, ValueError)):
        GPURepository().aplicar_laboratorio_voltaje_gpu_personalizado({"2050; reboot": 1000})


def test_40cu_reference_is_not_an_installed_or_cloned_dependency():
    dependency_source = Path("src/bc250cc/infrastructure/dependencias_repository.py").read_text(encoding="utf-8")
    # Inspect only packaging/install source. Generated package trees and binary
    # archives can legitimately embed the README/third-party notices and are not
    # installer instructions.
    ignored_parts = {"out", "pkg", "src", "release", "packages"}
    install_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in ("scripts", "packaging")
        for path in Path(root).rglob("*")
        if path.is_file()
        and not ignored_parts.intersection(path.parts)
        and path.suffix not in {".rpm", ".deb", ".zst", ".gz", ".pyc", ".pyo"}
    )
    assert "duggasco/bc250-40cu-unlock" not in dependency_source
    assert "duggasco/bc250-40cu-unlock" not in install_sources


def test_core_unlock_is_an_official_cloned_dependency():
    dependency_source = Path("src/bc250cc/infrastructure/dependencias_repository.py").read_text(
        encoding="utf-8"
    )
    manifest_source = Path("src/bc250cc/infrastructure/external_tools/catalog.py").read_text(encoding="utf-8")
    assert "https://github.com/rw-r-r-0644/bc250-core-unlock" in manifest_source
    assert 'EXTERNAL_TOOLS["core_unlock"].upstream' in dependency_source
    assert "_hardware_source_checkout_command(CORE_UNLOCK_REPOSITORY" in dependency_source
    assert "bc250-unlock-cores.py" in dependency_source


def test_steamos_fixes_are_installed_only_when_running_kernel_is_not_ready(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path

    command = repository._steamos_compatibility_stage_command()

    assert "keyboardspecialist/bc250-steamos" in command
    assert "patch-driver.sh status" in command
    # The module check evaluates every status line for the running release;
    # one affirmative line cannot hide a contradictory upstream report.
    assert 'awk -v release="$running_release"' in command
    assert 'installed, metrics and compute aware' in command
    assert "--cg" not in command
    assert "/build.sh;" in command
    assert "/install.sh;" in command
    assert f"sudo /usr/bin/bash {tmp_path}" not in command
    assert "BC250_REBOOT_REQUIRED=1" in command
    assert command.index("patch-driver.sh status") < command.index("/build.sh;")


def test_changed_40cu_output_format_produces_clear_error():
    repository = CURepository()
    malformed = """
    CUs active & routed: 40 / 40
    | upstream changed this table completely |
    """
    state = repository.parsear_dashboard_cu(malformed, source="live")
    assert state["available"] is False
    assert "could not be parsed" in state["parse_error"]

    repository.obtener_dashboard_cu = lambda: malformed
    with pytest.raises(RuntimeError, match="could not be parsed"):
        repository.obtener_estado_cu()


def test_standard_cu_backend_gets_bounded_umr_selector_fallback():
    repository = CURepository()
    repository._command_path = lambda name: f"/usr/bin/{name}"
    shell = repository._exportar_env_cu({
        "cu_manager_backend": "standard",
        "is_steamos": False,
        "umr": "/usr/bin/umr",
    })
    assert "cyan_skillfish.gfx1013" in shell
    assert "umr -lb" in shell
    assert "mmSPI_PG_ENABLE_STATIC_WGP_MASK" in shell
    assert "while IFS= read -r bc250_candidate" in shell


def test_community_research_and_bazzite_sources_are_credited_without_becoming_dependencies():
    readme = Path("README.md").read_text(encoding="utf-8")
    notices = Path("docs/THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    dependency_source = Path("src/bc250cc/infrastructure/dependencias_repository.py").read_text(
        encoding="utf-8"
    )

    for project in (
        "DryhoppedIPA/bc250-gfx1013-fix",
        "rpf16rj/bc250-steamos-real-toolkit",
        "redbeard1083/bc250-toolkit",
        "62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images",
    ):
        assert project in readme or project in notices
    assert "DryhoppedIPA/bc250-gfx1013-fix" not in dependency_source
    assert "rpf16rj/bc250-steamos-real-toolkit" not in dependency_source
    assert "redbeard1083/bc250-toolkit" not in dependency_source
    assert "62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images" not in dependency_source


@pytest.mark.parametrize("gc_block", ("gfx1010", "gfx1013"))
def test_steamos_cu_backend_derives_static_selector_without_scan(tmp_path, gc_block):
    database = tmp_path / "umr-db"
    database.mkdir()
    (database / "cyan_skillfish.asic").write_text(
        f"cyan_skillfish soc15 10 1 256 1\n{gc_block} GC 0 {gc_block}.reg\n",
        encoding="utf-8",
    )
    (database / f"{gc_block}.reg").write_text(
        "mmCC_GC_SHADER_ARRAY_CONFIG\n"
        "mmSPI_PG_ENABLE_STATIC_WGP_MASK\n"
        "mmRLC_PG_ALWAYS_ON_WGP_MASK\n",
        encoding="utf-8",
    )
    repository = CURepository()
    repository._tool_dir = lambda: tmp_path / "tools"
    shell = repository._exportar_env_cu({
        "cu_manager_backend": "steamos",
        "is_steamos": True,
        "cu_steamos_umr_database": str(database),
    })
    assert f"UMR_ASIC=cyan_skillfish.{gc_block}" in shell
    assert "-lb" not in shell


def test_busctl_properties_require_the_expected_typed_format():
    repository = object.__new__(SistemaRepository)
    repository._ejecutar = lambda *_args, **_kwargs: (0, "u 1850", "")
    assert repository._dbus_uint_property("/", "iface", "Max") == 1850
    repository._ejecutar = lambda *_args, **_kwargs: (0, "unexpected Max=1850", "")
    assert repository._dbus_uint_property("/", "iface", "Max") is None
    repository._ejecutar = lambda *_args, **_kwargs: (0, "b true", "")
    assert repository._dbus_bool_property("/", "iface", "Enabled") is True
    repository._ejecutar = lambda *_args, **_kwargs: (0, "Enabled: true", "")
    assert repository._dbus_bool_property("/", "iface", "Enabled") is None
