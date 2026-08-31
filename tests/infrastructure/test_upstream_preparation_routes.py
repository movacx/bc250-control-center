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
) -> DependenciasRepository:
    class Repository(DependenciasRepository):
        estado_herramientas_cache = None

        def _os_repository(self):
            info = type(
                "Info", (), {"family": family, "distro_id": distro_id or family}
            )()
            return type("OSRepository", (), {"info": info})()

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


@pytest.mark.parametrize("action", ("install", "uninstall"))
def test_fsr4_route_is_user_scoped_and_limited_to_reviewed_userspace(action):
    calls: list[tuple[str, str]] = []

    assert _repository_for("arch", calls).gestionar_fsr4_bc250(action) == "terminal"

    command, terminal_title = calls[0]
    assert "bc250-fsr4/v3" in command
    assert "github.com/dmorazasanchez/bc250-fsr4" in command
    assert f"{action}-v3.sh" in command
    assert "FSR4 V3" in terminal_title


def test_fsr4_manjaro_route_is_available_but_self_identifies_as_experimental():
    calls: list[tuple[str, str]] = []
    assert _repository_for("manjaro", calls).gestionar_fsr4_bc250("install") == "terminal"
    assert "does not name Manjaro" in calls[0][0]


def test_fsr4_bazzite_route_uses_only_the_official_podman_source_build():
    calls: list[tuple[str, str]] = []

    assert _repository_for("bazzite", calls).gestionar_fsr4_bc250("install") == "terminal"

    command, terminal_title = calls[0]
    assert "official V3 source build for Bazzite" in command
    assert "podman build" in command
    assert "podman run --rm" in command
    assert 'test "${ID:-}" = "bazzite"' in command
    assert "install-v3.sh" not in command
    assert "FSR4 V3" in terminal_title


@pytest.mark.parametrize("family", ("ubuntu", "fedora", "steamos"))
def test_fsr4_precompiled_route_rejects_untested_distribution_abis(family):
    with pytest.raises(RuntimeError, match="Bazzite uses the verified Podman"):
        _repository_for(family, []).gestionar_fsr4_bc250("install")


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
