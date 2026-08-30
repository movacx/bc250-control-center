from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.governor_conflicts import (
    CYAN_GOVERNOR,
    OBERON_GOVERNOR,
    GovernorConflictError,
    detect_incompatible_governors,
    resolve_gpu_governor,
)
from bc250cc.infrastructure.gpu.governor_toml import (
    GovernorTomlEditor,
    OberonYamlEditor,
    OberonYamlError,
)
from bc250cc.infrastructure.gpu_repository import GPURepository

UPSTREAM_YAML = """opps:
  - frequency:
    - min: 1000
    - max: 2000
  - voltage:
    - min: 1000
    - max: 1000
metadata: keep-this
"""


class FakeRepository:
    def __init__(self, states=(), binaries=()):
        self.states = dict(states)
        self.binaries = set(binaries)

    def _ejecutar(self, command, timeout=3):
        return self.states.get(tuple(command), (1, "", "not found"))

    def _command_path(self, name):
        return f"/usr/bin/{name}" if name in self.binaries else ""


def test_oberon_editor_preserves_upstream_yaml_and_is_idempotent(tmp_path):
    config = tmp_path / "oberon-config.yaml"
    config.write_text(UPSTREAM_YAML, encoding="utf-8")
    editor = OberonYamlEditor(config)

    first = editor.set_operating_points(500, 2200, 920, 1050)
    once = config.read_text(encoding="utf-8")
    second = editor.set_operating_points(500, 2200, 920, 1050)

    assert first.changed is True
    assert second.changed is False
    assert config.read_text(encoding="utf-8") == once
    assert "metadata: keep-this" in once
    assert editor.state() == {
        "frequency_min": 500,
        "frequency_max": 2200,
        "voltage_min": 920,
        "voltage_max": 1050,
        "safe_voltage": True,
    }


def test_oberon_editor_accepts_documented_plain_mapping(tmp_path):
    config = tmp_path / "oberon-config.yaml"
    config.write_text(
        "frequency:\n  min: 1000\n  max: 1850\n"
        "voltage:\n  min: 920\n  max: 930\n",
        encoding="utf-8",
    )
    OberonYamlEditor(config).set_operating_points(1000, 2000, 920, 960)
    assert OberonYamlEditor(config).state()["frequency_max"] == 2000


def test_oberon_editor_refuses_unsafe_voltage_without_touching_file(tmp_path):
    config = tmp_path / "oberon-config.yaml"
    config.write_text(UPSTREAM_YAML, encoding="utf-8")
    original = config.read_bytes()

    with pytest.raises(OberonYamlError, match="920"):
        OberonYamlEditor(config).set_operating_points(1000, 2000, 810, 960)

    assert config.read_bytes() == original


def test_auto_detection_selects_uniquely_active_oberon(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    repo = FakeRepository(
        states={
            ("systemctl", "is-active", "oberon-governor.service"): (0, "active", ""),
            ("systemctl", "is-enabled", "oberon-governor.service"): (0, "enabled", ""),
        },
        binaries={OBERON_GOVERNOR},
    )
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._package_installed", lambda *_: False)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")
    state = resolve_gpu_governor(repo, "auto")
    assert state["selected"] == OBERON_GOVERNOR
    assert state["detected_backend"] == OBERON_GOVERNOR
    assert state["reason"] == "active"


def test_clean_system_keeps_cyan_as_preparation_target_without_detecting_it(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts._package_installed",
        lambda *_: False,
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts._find_unit",
        lambda _service: "",
    )

    state = resolve_gpu_governor(FakeRepository(), "auto")

    assert state["selected"] == CYAN_GOVERNOR
    assert state["detected_backend"] == ""
    assert state["reason"] == "default"


def test_disabled_supported_governor_can_remain_installed_beside_selected_backend(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    repo = FakeRepository(binaries={CYAN_GOVERNOR, OBERON_GOVERNOR})
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._package_installed", lambda *_: False)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")
    conflicts = detect_incompatible_governors(repo, OBERON_GOVERNOR)
    assert conflicts == []

    state = resolve_gpu_governor(repo, OBERON_GOVERNOR)
    assert [item["identifier"] for item in state["other_installations"]] == [CYAN_GOVERNOR]


def test_selected_oberon_blocks_enabled_cyan_runtime(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: SimpleNamespace(kind="systemd"),
    )
    repo = FakeRepository(
        states={
            ("systemctl", "is-enabled", "cyan-skillfish-governor-smu.service"):
                (0, "enabled", ""),
        },
        binaries={CYAN_GOVERNOR, OBERON_GOVERNOR},
    )
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._package_installed", lambda *_: False)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")
    conflicts = detect_incompatible_governors(repo, OBERON_GOVERNOR)
    assert [item["identifier"] for item in conflicts] == [CYAN_GOVERNOR]

    from bc250cc.infrastructure.governor_conflicts import (
        ensure_no_incompatible_governors,
    )
    with pytest.raises(GovernorConflictError) as caught:
        ensure_no_incompatible_governors(repo, selected=OBERON_GOVERNOR)
    assert caught.value.selected == OBERON_GOVERNOR


def test_oberon_profile_uses_validated_yaml_endpoints_and_never_dbus():
    events = []

    class Repository(GPURepository):
        estado_bc250_cache = None

        def _selected_gpu_governor(self):
            return OBERON_GOVERNOR

        def _editar_governor_toml(self, action, *values):
            events.append((action, *values))
            return "validated"

        def _restart_governor_if_active(self, service):
            events.append(("restart", service))
            return True

        def _require_oberon_idle_transition(self, **_kwargs):
            events.append(("idle-verified",))

        def estado_bc250(self):
            return {"governor_backend": OBERON_GOVERNOR}

        def _ejecutar(self, *_args, **_kwargs):
            raise AssertionError("Oberon profile application must not call busctl")

    result = Repository().aplicar_perfil_gpu(1000, 1850)

    assert events == [
        ("idle-verified",),
        ("set-oberon-operating-points", 1000, 1850, 1000, 1000),
        ("restart", "oberon-governor.service"),
    ]
    assert result["operation_message"].startswith("validated")


def test_oberon_repository_rejects_recovery_and_custom_ranges_before_write():
    events = []

    class Repository(GPURepository):
        estado_bc250_cache = None

        def _selected_gpu_governor(self):
            return OBERON_GOVERNOR

        def _editar_governor_toml(self, *_args):
            events.append("write")

    repository = Repository()
    with pytest.raises(ValueError, match="Unsupported Oberon profile"):
        repository.aplicar_rango_bc250(500, 1000)
    with pytest.raises(ValueError, match="Unsupported Oberon profile"):
        repository.aplicar_rango_bc250(1000, 2200)
    assert events == []


def test_oberon_desktop_benchmark_is_fixed_2000_with_upstream_endpoints():
    events = []

    class Repository(GPURepository):
        estado_bc250_cache = None

        def _selected_gpu_governor(self):
            return OBERON_GOVERNOR

        def _require_oberon_idle_transition(self, **_kwargs):
            events.append(("idle",))

        def _editar_governor_toml(self, action, *values):
            events.append((action, *values))
            return "updated"

        def _restart_governor_if_active(self, service):
            events.append(("restart", service))
            return True

        def estado_bc250(self):
            return {}

    Repository().aplicar_rango_bc250(2000, 2000)

    assert events == [
        ("idle",),
        ("set-oberon-operating-points", 2000, 2000, 1000, 1000),
        ("restart", "oberon-governor.service"),
    ]


def test_oberon_fixed_frequency_path_rejects_non_profile_values_before_idle_or_write():
    events = []

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return OBERON_GOVERNOR

        def _require_oberon_idle_transition(self, **_kwargs):
            events.append("idle")

        def _editar_governor_toml(self, *_args):
            events.append("write")

    with pytest.raises(ValueError, match="Unsupported Oberon profile"):
        Repository().fijar_frecuencia_bc250(1850)

    assert events == []


def test_oberon_idle_gate_requires_three_complete_idle_samples(monkeypatch):
    sleeps = []

    class Repository(GPURepository):
        def _gpu_device_path(self):
            return Path("/sys/fake/card0/device")

        def _leer_entero(self, _path):
            return 2

        def _gpu_hwmon_live_metrics(self, _gpu):
            return 1000, 930

    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.time.sleep", sleeps.append)
    observed = Repository()._require_oberon_idle_transition()

    assert observed == ((2, 1000), (2, 1000), (2, 1000))
    assert sleeps == [0.15, 0.15]


def test_oberon_idle_gate_blocks_load_before_profile_write():
    class Repository(GPURepository):
        def _gpu_device_path(self):
            return Path("/sys/fake/card0/device")

        def _leer_entero(self, _path):
            return 42

        def _gpu_hwmon_live_metrics(self, _gpu):
            return 1850, 960

    with pytest.raises(RuntimeError, match="require an idle GPU"):
        Repository()._require_oberon_idle_transition()


def test_oberon_idle_gate_allows_benchmark_clock_when_gpu_is_idle():
    class Repository(GPURepository):
        def _gpu_device_path(self):
            return Path("/sys/fake/card0/device")

        def _leer_entero(self, _path):
            return 0

        def _gpu_hwmon_live_metrics(self, _gpu):
            return 2000, 993

    assert Repository()._require_oberon_idle_transition(samples=1) == ((0, 2000),)


def test_oberon_idle_gate_uses_fdinfo_when_busy_sysfs_is_unsupported(monkeypatch):
    sleeps = []

    class Repository(GPURepository):
        def __init__(self):
            self.fdinfo_samples = iter((None, 3, 2, 1))

        def _gpu_device_path(self):
            return Path("/sys/fake/card0/device")

        def _leer_entero(self, _path):
            return None

        def _gpu_busy_fdinfo(self):
            return next(self.fdinfo_samples)

        def _gpu_hwmon_live_metrics(self, _gpu):
            return 1000, 993

    monkeypatch.setattr("bc250cc.infrastructure.gpu_repository.time.sleep", sleeps.append)
    observed = Repository()._require_oberon_idle_transition()

    assert observed == ((3, 1000), (2, 1000), (1, 1000))
    assert sleeps == [0.15, 0.15, 0.15]


def test_oberon_idle_gate_stays_fail_closed_without_sysfs_or_fdinfo():
    class Repository(GPURepository):
        def _gpu_device_path(self):
            return Path("/sys/fake/card0/device")

        def _leer_entero(self, _path):
            return None

        def _gpu_busy_fdinfo(self):
            return None

        def _gpu_hwmon_live_metrics(self, _gpu):
            return 1000, 993

    with pytest.raises(RuntimeError, match="telemetry is unavailable"):
        Repository()._require_oberon_idle_transition(interval=0)


def test_oberon_install_pins_source_and_transitive_yaml_dependency(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path
    os_repository = SimpleNamespace(
        info=SimpleNamespace(family="fedora", label="Fedora")
    )
    command = repository._oberon_install_command(os_repository)
    assert "7e13da6c2cb9f1e0519242b1cb084ef767631a5c" in command
    assert "f7320141120f720aecc4c32be25586e7da9eb978" in command
    assert "fetch --depth 1 origin 7e13da6c2cb9f1e0519242b1cb084ef767631a5c" in command
    assert 'rev-parse HEAD)" = 7e13da6c2cb9f1e0519242b1cb084ef767631a5c' in command


def test_cyan_telemetry_repair_is_idempotent_and_preserves_metrics_opt_out(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[gpu-usage]\nfix-metrics = false\nmethod = \"process\"\nflush-every = 10\n"
        "\n[gpu]\nset-method = \"smu\"\n",
        encoding="utf-8",
    )
    editor = GovernorTomlEditor(config)
    first = editor.ensure_gpu_telemetry(fix_frequency=True)
    once = config.read_text(encoding="utf-8")
    second = editor.ensure_gpu_telemetry(fix_frequency=True)

    assert first.changed is True
    assert second.changed is False
    assert config.read_text(encoding="utf-8") == once
    # ``fix-metrics`` is an optional bind overlay and a deliberately disabled
    # value must survive telemetry repair; ``fix-freq`` is the independent
    # 8-core clock-reporting fix that remains mandatory.
    assert "fix-metrics = false" in once
    assert 'method = "process"' in once
    assert "fix-freq = true" in once
    assert "flush-every = 10" in once
