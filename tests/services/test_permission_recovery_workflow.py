from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import helper_permissions, terminal_repository
from bc250cc.infrastructure.terminal_repository import (
    TerminalLaunchResult,
    TerminalRepository,
)


@pytest.mark.parametrize("needs_repair", [True, False])
def test_recovery_aborts_on_failure_and_leaves_healthy_workflows_unauthenticated(tmp_path, monkeypatch, needs_repair):
    app = tmp_path / "app"
    maintenance = app / "packaging/common/bc250-package-maintenance"
    maintenance.parent.mkdir(parents=True)
    maintenance.write_text(
        '#!/bin/bash\nBC250_PERMISSION_REPAIR_PROTOCOL=1\nrepair_permissions() {\n'
        f'if [ "${{1:-}}" = check ]; then return {0 if needs_repair else 1}; fi\n'
        'return 77\n}\ncase "${1:-}" in\n*) exit 64;;\nesac\n'
    )
    monkeypatch.setattr(helper_permissions, "__file__", str(app / "src/bc250cc/infrastructure/helper_permissions.py"))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo = fake_bin / "sudo"
    sudo.write_text("#!/bin/sh\nexit 77\n")
    sudo.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(terminal_repository.shutil, "which", lambda name: None)
    requested = tmp_path / "requested"
    executions = []

    def launch(request):
        result = subprocess.run(request.argv, capture_output=True, text=True, timeout=20)
        executions.append(result)
        assert Path(request.status_file).read_text().strip() == ("77" if needs_repair else "0")
        return TerminalLaunchResult("test-console", request.title, None, request.status_file, request.log_file)

    launch.writes_transcript = False
    monkeypatch.setattr(terminal_repository, "_embedded_launcher", launch)
    TerminalRepository()._abrir_terminal(f"touch '{requested}'", "Permission recovery")
    assert executions[0].returncode == (77 if needs_repair else 0)
    assert requested.exists() is not needs_repair


def test_a_mixed_old_repair_program_is_refused_before_launch(tmp_path, monkeypatch):
    app = tmp_path / "app"
    maintenance = app / "packaging/common/bc250-package-maintenance"
    maintenance.parent.mkdir(parents=True)
    maintenance.write_text('repair_permissions() { :; }\ncase "${1:-}" in\n*) exit 64;;\nesac\n')
    monkeypatch.setattr(helper_permissions, "__file__", str(app / "src/bc250cc/infrastructure/helper_permissions.py"))
    with pytest.raises(RuntimeError, match="permission repair is unavailable"):
        helper_permissions.recovery_preflight()
