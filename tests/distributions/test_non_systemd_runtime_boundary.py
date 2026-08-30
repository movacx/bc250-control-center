from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import (
    cpu_repository,
    cu_repository,
    gpu_repository,
    health_repository,
    sistema_repository,
)
from bc250cc.infrastructure.cpu_repository import CPURepository
from bc250cc.infrastructure.cu_repository import CURepository
from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.infrastructure.health_repository import HealthRepository
from bc250cc.infrastructure.sistema_repository import SistemaRepository
from bc250cc.platform.init.services import InitManagerState
from bc250cc.platform.packages.strategies.detector import detect_os_info

RUNIT = InitManagerState(
    "runit", True, "runit is active; persistence is detected-only.", False
)


def test_artix_package_family_is_independent_from_its_init_manager():
    os_info = detect_os_info({"ID": "artix", "ID_LIKE": "arch"})
    assert os_info.family == "arch"
    assert RUNIT.kind == "runit"
    assert RUNIT.persistence_supported is False


def test_live_40_cu_state_survives_without_a_persistence_backend(monkeypatch):
    monkeypatch.setattr(cu_repository, "detect_init_manager", lambda: RUNIT)

    class Repository(CURepository):
        def _ejecutar(self, *_args, **_kwargs):
            raise AssertionError("unsupported init must not fall through to systemctl")

    live = {
        "available": True,
        "active_cus": 40,
        "routed_wgps": 20,
        "masks": [0x1F, 0x1F, 0x1F, 0x1F],
        "mode": "Full 40 CUs",
        "service": "enabled",
        "service_installed": True,
        "service_enabled": True,
        "boot_sync": "Current table saved",
        "boot_sync_key": "saved",
    }
    result = Repository()._reconcile_cached_service_state(live)

    assert result["active_cus"] == 40
    assert result["masks"] == [0x1F] * 4
    assert result["boot_sync_key"] == "unsupported"
    assert result["persistence_supported"] is False


def test_cpu_persistence_state_does_not_call_systemctl_on_detected_only_init(monkeypatch):
    monkeypatch.setattr(cpu_repository, "detect_init_manager", lambda: RUNIT)

    class Repository(CPURepository):
        @staticmethod
        def _read_cpu_oc_config(_path):
            return {"exists": True, "valid": True, "frequency": 3900, "scale": -30,
                    "max_temperature": 90}

        def _ejecutar(self, *_args, **_kwargs):
            raise AssertionError("unsupported init must not call systemctl")

    result = Repository().estado_cpu_oc_persistente()

    assert result["persistence_supported"] is False
    assert result["config_valid"] is True
    assert result["enabled"] == "unsupported"


def test_gpu_service_properties_do_not_call_systemctl_on_detected_only_init(monkeypatch):
    monkeypatch.setattr(sistema_repository, "detect_init_manager", lambda: RUNIT)

    class Repository:
        def _ejecutar(self, *_args, **_kwargs):
            raise AssertionError("unsupported init must not call systemctl")

    assert SistemaRepository._service_prop(
        Repository(), "cyan-skillfish-governor-smu.service", "ActiveState"
    ) == ""


def test_health_reports_persistence_as_unsupported_without_systemctl(monkeypatch):
    monkeypatch.setattr(health_repository, "detect_init_manager", lambda: RUNIT)

    class Repository(HealthRepository):
        def _ejecutar(self, *_args, **_kwargs):
            raise AssertionError("health must not call systemctl on runit")

    item = Repository()._service_health(
        "bc250-cu-live-manager.service", optional=True
    )

    assert item["status"] == "healthy"
    assert item["data"]["init_manager"] == "runit"
    assert item["data"]["persistence_supported"] is False


def test_cyan_dbus_runtime_is_read_without_service_persistence(monkeypatch):
    monkeypatch.setattr(gpu_repository, "detect_init_manager", lambda: RUNIT)
    commands = []

    def probe(command):
        commands.append(tuple(command))
        value = "900" if command[-1] == "Min" else "1800"
        return SimpleNamespace(returncode=0, stdout=f"u {value}\n", stderr="")

    monkeypatch.setattr(gpu_repository, "run_daemon_governor_probe", probe)

    class Repository(GPURepository):
        def _gpu_governor_preference(self):
            return "cyan-skillfish-governor-smu"

        def _gpu_device_path(self):
            return None

        @staticmethod
        def _parse_dpm_actual(_value):
            return None

    state = Repository().estado_bc250_daemon()

    assert state["service_active"] == ""
    assert state["dbus_ok"] is True
    assert state["current_min"] == 900
    assert state["current_max"] == 1800
    assert all(command[0] == "busctl" for command in commands)


@pytest.mark.parametrize("action", ("save_boot", "install_service", "apply_saved"))
def test_cu_persistence_actions_fail_closed_but_live_actions_remain_separate(
    monkeypatch, action,
):
    monkeypatch.setattr(cu_repository, "detect_init_manager", lambda: RUNIT)
    with pytest.raises(RuntimeError, match="live CU status and temporary routing remain available"):
        CURepository._require_cu_persistence_backend(action)
