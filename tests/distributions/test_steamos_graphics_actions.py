from pathlib import Path

import pytest

from bc250cc.infrastructure.steamos_graphics_runtime import (
    STEAMOS_GRAPHICS_ACTIONS,
    build_steamos_graphics_command,
)


@pytest.mark.parametrize(
    ("action", "fragment"),
    (
        ("status", "status-json"),
        ("install", " setup"),
        ("install-fsr4", "setup --fsr4"),
        ("uninstall", " uninstall"),
        ("uninstall-fsr4", "uninstall --fsr4"),
    ),
)
def test_steamos_graphics_actions_use_only_the_protected_backend(action, fragment):
    protected = Path(
        "/usr/libexec/bc250-control-center/steamos-amdgpu-backend/bc250-mesh-shader.sh"
    )
    command = build_steamos_graphics_command(
        action,
        checkout_command="echo STAGE_REVIEWED_TREE",
        backend_guard="test -x PROTECTED_BACKEND",
        script=protected,
    )

    assert fragment in command
    assert str(protected) in command
    assert "test -x PROTECTED_BACKEND" in command
    assert "steamos|steamdeck|holo" in command
    assert "/ResourceTools/" not in command
    if action == "status":
        assert "STAGE_REVIEWED_TREE" not in command
        assert command.count("status-json") == 1
    else:
        assert "STAGE_REVIEWED_TREE" in command
        assert command.count("status-json") == 1


def test_steamos_graphics_action_surface_is_finite_and_rejects_empty_guards():
    assert STEAMOS_GRAPHICS_ACTIONS == {
        "status", "install", "install-fsr4", "uninstall", "uninstall-fsr4"
    }
    with pytest.raises(ValueError):
        build_steamos_graphics_command("shell", backend_guard="true")
    with pytest.raises(ValueError):
        build_steamos_graphics_command("install", backend_guard="")
