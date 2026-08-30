from pathlib import Path

import pytest

from bc250cc.infrastructure.gpu_repository import GPURepository


def test_gpu_repository_has_no_generic_root_shell_adapter():
    source = Path(GPURepository.__module__.replace(".", "/") + ".py")
    if not source.is_file():
        source = Path(__file__).resolve().parents[3] / "src/bc250cc/infrastructure/gpu_repository.py"
    text = source.read_text(encoding="utf-8")

    assert "_ejecutar_voltage_lab_pkexec" not in text
    assert "['pkexec', bash, '-lc', comando]" not in text


class CyanRepository(GPURepository):
    def __init__(self):
        self.calls = []
        self.estado_bc250_cache = {"stale": True}
        self.estado_herramientas_cache = {"stale": True}

    def _selected_gpu_governor(self):
        return "cyan-skillfish-governor-smu"

    def _usar_steamos_game_helper(self):
        return False

    def _ejecutar(self, command, timeout=2):
        self.calls.append(("exec", command, timeout))
        return 0, "", ""

    def _service_is_active(self, service):
        code, _out, _err = self._ejecutar(
            ["systemctl", "is-active", "--quiet", service], timeout=5
        )
        return code == 0

    def _leer_rango_governor(self, kind):
        assert kind == "Current"
        return 1000, 1850

    def _editar_governor_toml(self, action, *arguments):
        self.calls.append(("edit", action, arguments))
        return "updated"

    def _restart_governor_if_active(self, service):
        self.calls.append(("restart", service))
        return True

    def _restaurar_rango_governor(self, previous):
        self.calls.append(("restore", previous))
        return previous


def test_cyan_voltage_level_uses_protected_helper_boundary_and_restores_range():
    repo = CyanRepository()

    result = repo.aplicar_laboratorio_voltaje_gpu(3)

    assert ("edit", "set-cyan-voltage-level", (3,)) in repo.calls
    assert ("restart", "cyan-skillfish-governor-smu.service") in repo.calls
    assert ("restore", (1000, 1850)) in repo.calls
    assert "1000-1850 MHz" in result


def test_custom_voltage_request_is_sorted_and_does_not_execute_writable_script():
    repo = CyanRepository()

    repo.aplicar_laboratorio_voltaje_gpu_personalizado({1850: 950, 1000: 820})

    assert ("edit", "set-cyan-custom-voltages", ("1000=820", "1850=950")) in repo.calls
    assert all("bash" not in str(call) for call in repo.calls)
    assert all("bc250-gpu-voltage-lab.sh" not in str(call) for call in repo.calls)


def test_inactive_or_unreadable_cyan_range_blocks_edit_before_helper_call():
    repo = CyanRepository()
    repo._ejecutar = lambda *_args, **_kwargs: (3, "", "inactive")

    with pytest.raises(RuntimeError, match="must be active"):
        repo.aplicar_laboratorio_voltaje_gpu(0)
    assert not any(call[0] == "edit" for call in repo.calls)

    repo = CyanRepository()
    repo._leer_rango_governor = lambda _kind: None
    with pytest.raises(RuntimeError, match="could not be read"):
        repo.aplicar_laboratorio_voltaje_gpu(0)
    assert not any(call[0] == "edit" for call in repo.calls)


def test_game_mode_toml_edits_use_the_game_helper_instead_of_raw_pkexec():
    repo = GPURepository.__new__(GPURepository)
    repo.estado_bc250_cache = {"stale": True}
    repo._usar_steamos_game_helper = lambda: True
    calls = []
    repo._ejecutar_steamos_game_helper = lambda *args, **kwargs: calls.append(
        (args, kwargs)
    ) or "updated"

    assert repo._editar_governor_toml("set-frequency-range", 1000, 1850) == "updated"
    assert calls == [
        (("governor-config", "set-frequency-range", "1000", "1850"), {"timeout": 120})
    ]


def test_game_mode_voltage_curve_uses_the_extended_verified_transaction_timeout():
    repo = GPURepository.__new__(GPURepository)
    repo.estado_bc250_cache = {"stale": True}
    repo.estado_herramientas_cache = {"stale": True}
    repo._selected_gpu_governor = lambda: "cyan-skillfish-governor-smu"
    repo._usar_steamos_game_helper = lambda: True
    calls = []
    repo._ejecutar_steamos_game_helper = lambda *args, **kwargs: calls.append(
        (args, kwargs)
    ) or "curve applied"

    assert repo.aplicar_laboratorio_voltaje_gpu(3) == "curve applied"
    assert calls == [
        (("gpu-voltage", "apply", 3), {"timeout": 420})
    ]


def test_oberon_voltage_lab_is_blocked_before_any_yaml_write():
    repo = GPURepository.__new__(GPURepository)
    repo._selected_gpu_governor = lambda: "oberon-governor"

    with pytest.raises(RuntimeError, match="Oberon voltage editing is unavailable"):
        repo.aplicar_laboratorio_voltaje_gpu(3)
    with pytest.raises(RuntimeError, match="Oberon voltage editing is unavailable"):
        repo.aplicar_laboratorio_voltaje_gpu_personalizado({1000: 920, 1850: 930})


def test_cyan_runtime_recovery_message_is_localized_for_every_supported_language():
    from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr

    message = (
        'Cyan D-Bus runtime range is not ready after a governor restart. '
        'Wait for Cyan to recover, then refresh GPU status before applying a new range.'
    )
    for language in SUPPORTED_LANGUAGES:
        assert tr(message, language)
        if language != "en":
            assert tr(message, language) != message
