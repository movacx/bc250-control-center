"""The export pages read the Decky inventory alone, for this distribution."""

from __future__ import annotations

from types import SimpleNamespace

from bc250cc.infrastructure import dependencias_repository as module
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


def test_the_decky_state_is_the_inventory_for_the_detected_family(monkeypatch):
    seen = []

    def inventory(*, os_family):
        seen.append(os_family)
        return SimpleNamespace(to_dict=lambda: {"plugin_present": True, "decky_detected": True})

    monkeypatch.setattr(module, "quick_access_inventory", inventory)
    repository = DependenciasRepository.__new__(DependenciasRepository)
    monkeypatch.setattr(repository, "_os_repository", lambda: SimpleNamespace(family="steamos"))

    assert repository.estado_quick_access_decky() == {"plugin_present": True, "decky_detected": True}
    assert seen == ["steamos"]
