import ast
from pathlib import Path

from bc250cc.infrastructure.cpu_repository import CPURepository
from bc250cc.infrastructure.sistema_repository import SistemaRepository
from bc250cc.infrastructure.system_service import SistemaService


def _delegated_method_names(path: Path, attribute: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if not isinstance(owner, ast.Attribute):
            continue
        if not isinstance(owner.value, ast.Name) or owner.value.id != 'self':
            continue
        if owner.attr == attribute:
            names.add(node.func.attr)
    return names


def test_service_repository_delegate_contract_is_complete():
    """Every direct SistemaService -> repository delegate must exist.

    This regression test specifically prevents the CPU page failure where the
    service still delegated ``estado_cpu_oc_persistente`` after that repository
    method was accidentally removed during the Scale workflow refactor.
    """
    methods = _delegated_method_names(Path('src/bc250cc/infrastructure/system_service.py'), 'repo')
    missing = sorted(name for name in methods if not hasattr(SistemaRepository, name))
    assert missing == []


def test_cpu_persistence_status_contract_handles_successful_inactive_oneshot(tmp_path):
    config = tmp_path / 'bc250-smu-oc.conf'
    config.write_text(
        '[overclock]\nfrequency = 3850\nscale = -30\nmax_temperature = 90\n',
        encoding='utf-8',
    )

    repository = CPURepository.__new__(CPURepository)
    repository._CPU_OC_SYSTEM_CONFIG = config
    repository._systemctl_valor = lambda args: 'enabled' if args[0] == 'is-enabled' else 'inactive'
    repository._systemctl_show = lambda _service: {
        'ActiveState': 'inactive',
        'SubState': 'dead',
        'Result': 'success',
        'ExecMainStatus': '0',
        'ExecMainCode': 'exited',
        'ExecMainStartTimestamp': 'Sun 2026-08-09 17:00:00 CST',
        'ExecMainExitTimestamp': 'Sun 2026-08-09 17:00:01 CST',
    }
    repository._ejecutar = lambda *_args, **_kwargs: (
        3,
        'Active: inactive (dead)\nstatus=0/SUCCESS\n',
        '',
    )

    state = repository.estado_cpu_oc_persistente()

    assert state['enabled'] == 'enabled'
    assert state['active_state'] == 'inactive'
    assert state['result'] == 'success'
    assert state['oneshot_ok'] is True
    assert state['applied'] is True
    assert state['applied_this_boot'] is True
    assert state['ui_state'] == 'Applied / enabled'
    assert state['config_valid'] is True
    assert state['config']['frequency'] == 3850
    assert state['config']['scale'] == -30
    assert state['config']['max_temperature'] == 90


def test_service_exposes_restored_cpu_persistence_status():
    assert hasattr(SistemaRepository, 'estado_cpu_oc_persistente')
    assert hasattr(SistemaService, 'estado_cpu_oc_persistente')



def test_view_application_api_contract_is_complete():
    missing: dict[str, list[str]] = {}
    for path in Path('frontends/desktop').rglob('*.py'):
        methods = _delegated_method_names(path, 'controller')
        absent = sorted(name for name in methods if not hasattr(SistemaService, name))
        if absent:
            missing[str(path)] = absent
    assert missing == {}


def test_cpu_persistence_does_not_claim_applied_this_boot_without_start_timestamp(tmp_path):
    config = tmp_path / 'bc250-smu-oc.conf'
    config.write_text(
        '[overclock]\nfrequency = 3850\nscale = -30\nmax_temperature = 90\n',
        encoding='utf-8',
    )
    repository = CPURepository.__new__(CPURepository)
    repository._CPU_OC_SYSTEM_CONFIG = config
    repository._systemctl_valor = lambda args: 'enabled' if args[0] == 'is-enabled' else 'inactive'
    repository._systemctl_show = lambda _service: {
        'ActiveState': 'inactive',
        'SubState': 'dead',
        'Result': 'success',
        'ExecMainStatus': '0',
        'ExecMainCode': 'exited',
        'ExecMainStartTimestamp': '',
        'ExecMainExitTimestamp': '',
    }
    repository._ejecutar = lambda *_args, **_kwargs: (3, 'Active: inactive (dead)\n', '')

    state = repository.estado_cpu_oc_persistente()

    assert state['applied_this_boot'] is False
