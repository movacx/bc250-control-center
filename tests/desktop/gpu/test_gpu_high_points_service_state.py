from bc250cc.infrastructure.gpu_repository import GPURepository


def test_high_point_toggle_is_a_configuration_only_action():
    repository = GPURepository()
    repository._selected_gpu_governor = lambda: "cyan-skillfish-governor-smu"
    commands = []

    def execute(command, timeout=0):
        commands.append((command, timeout))
        return 3, "", ""

    repository._ejecutar = execute
    repository._editar_governor_toml = lambda action: f"validated: {action}"

    result = repository.alternar_puntos_gpu_altos(True)

    assert commands == []
    assert "live GPU range and Cyan service were not changed" in result


def test_high_point_toggle_never_probes_or_restarts_an_already_active_governor():
    repository = GPURepository()
    repository._selected_gpu_governor = lambda: "cyan-skillfish-governor-smu"
    commands = []

    def execute(command, timeout=0):
        commands.append((command, timeout))
        return 0, "", ""

    repository._ejecutar = execute
    repository._leer_rango_governor = lambda kind: (_ for _ in ()).throw(
        AssertionError("enabling high points must not query the live range")
    )
    repository._editar_governor_toml = lambda action: f"validated: {action}"

    result = repository.alternar_puntos_gpu_altos(True)

    assert "live GPU range and Cyan service were not changed" in result
    assert commands == []


def test_disabling_high_points_requires_a_safe_live_range_first():
    repository = GPURepository()
    repository._selected_gpu_governor = lambda: "cyan-skillfish-governor-smu"
    commands = []
    ranges = {"Current": [(1000, 2400)]}

    def execute(command, timeout=0):
        commands.append((command, timeout))
        return 0, "", ""

    repository._ejecutar = execute
    repository._service_is_active = lambda _service: True
    repository._leer_rango_governor = lambda kind: ranges[kind].pop(0)
    edits = []
    repository._editar_governor_toml = edits.append

    try:
        repository.alternar_puntos_gpu_altos(False)
    except RuntimeError as error:
        assert "Apply a range at or below 2000 MHz" in str(error)
    else:
        raise AssertionError("unsafe live range was allowed to lose its point")

    assert edits == []
    assert commands == []


def test_enabling_high_points_does_not_require_live_range_evidence():
    repository = GPURepository()
    repository._selected_gpu_governor = lambda: "cyan-skillfish-governor-smu"
    edited = []

    repository._ejecutar = lambda command, timeout=0: (0, "", "")
    repository._leer_rango_governor = lambda kind: None
    repository._editar_governor_toml = lambda action: edited.append(action)

    repository.alternar_puntos_gpu_altos(True)
    assert edited == ["enable-high-points"]


def test_high_frequency_load_gate_reloads_enabled_toml_point(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[frequency-range]\nmin = 1000\nmax = 2000\n\n"
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n\n"
        "[[safe-points]]\nfrequency = 2000\nvoltage = 960\n\n"
        "[[safe-points]]\nfrequency = 2200\nvoltage = 1050\n",
        encoding="utf-8",
    )
    repository = GPURepository()
    repository._leer_rango_governor = lambda kind: (500, 2000)
    repository._cyan_runtime_config_path = lambda **_kwargs: config
    reloads = []
    repository._reload_cyan_for_high_range = lambda minimum, maximum: reloads.append(
        (minimum, maximum)
    )

    repository._ensure_cyan_frequency_range_loaded(1000, 2200)

    assert reloads == [(1000, 2200)]


def test_fixed_frequency_uses_same_high_point_reload_gate(monkeypatch):
    from bc250cc.infrastructure import gpu_repository as gpu_module

    repository = GPURepository()
    repository._selected_gpu_governor = lambda: "cyan-skillfish-governor-smu"
    repository._require_cyan_runtime_for_live_control = dict
    repository._leer_rango_governor = lambda kind: (
        (1000, 2000) if kind == "Current" else (500, 2000)
    )
    events = []
    repository._ensure_cyan_frequency_range_loaded = lambda minimum, maximum: (
        events.append(("load", minimum, maximum))
    )
    repository._validar_curva_oc_alta = lambda maximum: events.append(
        ("curve", maximum)
    )
    repository.estado_bc250 = dict

    class Result:
        current_min = 1000
        current_max = 2200
        hardware_verification = "confirmed"
        observed_frequency = 2200

        @staticmethod
        def as_dict():
            return {"mode": "fixed-frequency"}

    class Engine:
        def __init__(self, _repository):
            pass

        def apply_fixed(self, frequency):
            events.append(("fixed", frequency))
            return Result()

    monkeypatch.setattr(gpu_module, "CyanGpuEngine", Engine)

    state = repository.fijar_frecuencia_bc250(2200)

    assert events == [("load", 1000, 2200), ("curve", 2200), ("fixed", 2200)]
    assert state["gpu_operation"] == {"mode": "fixed-frequency"}
