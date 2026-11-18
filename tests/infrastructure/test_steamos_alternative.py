"""Alternative provider selection never silently invokes Real Toolkit."""
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin
from bc250cc.infrastructure.steamos_alternative import (
    ALTERNATIVE_ACTIONS,
    run_alternative,
)


@pytest.mark.parametrize('action', ALTERNATIVE_ACTIONS)
def test_explicit_alternative_action_uses_its_own_lifecycle(action):
    class Repository(SteamosDependenciesMixin):
        def _os_repository(self):
            return SimpleNamespace(info=SimpleNamespace(family='steamos'))

        def preparar_compatibilidad_steamos_alternativo(self):
            return ('kernel', 'install')

        def restaurar_kernel_steamos_alternativo(self):
            return ('kernel', 'rollback')

        def _steamos_compatibility_stage_command(self, *, install):
            assert install is False
            return ('kernel', 'status')

        def _abrir_terminal(self, command, title):
            return command

        def gestionar_graficos_steamos_alternativo(self, operation):
            return ('graphics', operation)

        def gestionar_proton_steamos_alternativo(self, operation):
            return ('proton', operation)

        def gestionar_real_toolkit_steamos(self, action):
            pytest.fail('An alternative action must not invoke Real Toolkit')

    assert run_alternative(Repository(), action) == tuple(action.split('-', 1))


def test_unknown_alternative_action_is_rejected_before_accessing_repository():
    with pytest.raises(ValueError, match='Unknown'):
        run_alternative(None, 'kernel-install;echo nope')


def test_alternative_is_not_available_on_another_distribution():
    repo = SimpleNamespace(_os_repository=lambda: SimpleNamespace(info=SimpleNamespace(family='arch')))
    with pytest.raises(RuntimeError, match='only on SteamOS'):
        run_alternative(repo, 'graphics-status')
