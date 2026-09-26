from __future__ import annotations

from pathlib import Path

import pytest

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from frontends.desktop.pages import gpu_governor
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _repository_for(
    family: str,
    calls: list[tuple[str, str]],
    *,
    distro_id: str | None = None,
    version_id: str = "",
) -> DependenciasRepository:
    class Repository(DependenciasRepository):
        estado_herramientas_cache = None

        def _os_repository(self):
            info = type(
                "Info", (), {
                    "family": family,
                    "distro_id": distro_id or family,
                    "version_id": version_id,
                    "immutable": family == "bazzite",
                }
            )()
            return type("OSRepository", (), {"family": family, "info": info})()

        def _abrir_terminal(self, command, title=""):
            calls.append((command, title))
            return "terminal"

        def _tool_dir(self):
            return Path("/tmp/bc250-test-tools")

    return Repository()


@pytest.mark.parametrize(
    ("action", "expected", "title"),
    (
        ("kernel", "linux-cachyos-bc250 linux-cachyos-bc250-headers", "kernel"),
        ("mesa", "Installing stable BC-250 patched Mesa", "Mesa"),
        ("full", "Installing stable BC-250 patched Mesa", "kernel y Mesa"),
    ),
)
def test_cachyos_routes_open_only_the_requested_reviewed_transaction(
    action, expected, title
):
    calls: list[tuple[str, str]] = []

    assert _repository_for("cachyos", calls).preparar_cachyos_bc250(action) == "terminal"

    command, terminal_title = calls[0]
    assert expected in command
    assert title in terminal_title


def test_masta_route_is_exposed_to_plain_arch():
    calls: list[tuple[str, str]] = []
    assert _repository_for("arch", calls).preparar_cachyos_bc250("mesa") == "terminal"
    assert "Arch/CachyOS" in calls[0][1]


def test_masta_route_is_not_exposed_to_unqualified_distributions():
    with pytest.raises(RuntimeError, match="plain Arch Linux or CachyOS"):
        _repository_for("ubuntu", []).preparar_cachyos_bc250("mesa")


@pytest.mark.parametrize(
    ("distro_id", "family"),
    (("manjaro", "manjaro"), ("endeavouros", "arch"), ("artix", "arch"), ("fedora", "fedora")),
)
def test_masta_route_rejects_unqualified_arch_derivatives(distro_id, family):
    with pytest.raises(RuntimeError, match="plain Arch Linux or CachyOS"):
        _repository_for(family, [], distro_id=distro_id).preparar_cachyos_bc250("kernel")


def test_bazzite_async_compute_route_uses_only_the_pinned_release(monkeypatch):
    calls: list[tuple[str, str]] = []
    repository = _repository_for("bazzite", calls)
    monkeypatch.setattr(
        repository,
        "_gfx1013_compute_state",
        lambda _os_repository: {"direct_installer_allowed": True},
    )

    assert repository.gestionar_gfx1013_bazzite("install") == "terminal"

    command, title = calls[0]
    assert "bc250-async-compute-0.2.4.tar.zst" in command
    assert "fabece2f0735fd4f096bb253894f53d342e1eb4ec18c761eaca1ac9d20330711" in command
    assert "7.2.0-ogc4.1 or newer" in command
    assert "GFX1013 async compute for Bazzite" == title


def test_bazzite_async_compute_route_never_opens_on_other_distros(monkeypatch):
    repository = _repository_for("fedora", [])
    monkeypatch.setattr(
        repository,
        "_gfx1013_compute_state",
        lambda _os_repository: {"direct_installer_allowed": True},
    )
    with pytest.raises(RuntimeError, match="only on Bazzite"):
        repository.gestionar_gfx1013_bazzite("install")


def test_bazzite_mitigations_route_opens_a_reversible_transaction():
    calls: list[tuple[str, str]] = []
    repository = _repository_for("bazzite", calls)

    assert repository.gestionar_mitigaciones_bazzite("disable") == "terminal"

    command, title = calls[0]
    assert "--append-if-missing=mitigations=off" in command
    assert "No automatic reboot was performed" in command
    assert "mitigaciones de CPU" in title


def test_bazzite_mitigations_route_is_blocked_on_other_distributions():
    with pytest.raises(RuntimeError, match="only on Bazzite"):
        _repository_for("cachyos", []).gestionar_mitigaciones_bazzite("disable")


def test_steamos_graphics_guide_action_opens_documentation_without_running_a_tool(
    monkeypatch,
):
    opened: list[str] = []
    monkeypatch.setattr(
        gpu_governor,
        "open_external_url",
        lambda url: (opened.append(url) or True, ""),
    )

    GpuGovernorPage._open_steamos_graphics_upstream(object(), dialog_parent=None)

    assert opened == ["https://github.com/keyboardspecialist/bc250-steamos"]
