#!/usr/bin/env python3
"""Run the real application workflow and installed helper in a QA container."""

import os
import subprocess
import sys
from pathlib import Path

if os.environ.get("BC250_QA_CONTAINER") != "1" or os.geteuid() != 0 or not Path("/run/.containerenv").is_file():
    raise SystemExit("Container-only application recovery QA; refusing host permission changes")

repo = Path(sys.argv[1]).resolve()
app = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else repo
for name in ("helper_permissions.py", "terminal_repository.py"):
    relative = Path("src/bc250cc/infrastructure") / name
    assert (app / relative).read_bytes() == (repo / relative).read_bytes(), f"Stale installed application: {name}"
sys.path.insert(0, str(app / "src"))
from bc250cc.infrastructure.terminal_repository import (  # noqa: E402
    TerminalLaunchResult,
    TerminalRepository,
    set_embedded_terminal_launcher,
)

helper = "/usr/libexec/bc250-control-center/bc250-system-setup-helper"


def launch(request):
    result = subprocess.run(request.argv, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(request.status_file).read_text().strip() == "0"
    assert '"protocol": 2' in result.stdout, result.stdout
    assert "mode=0777 -> 0755" in result.stdout, result.stdout
    return TerminalLaunchResult("qa-embedded", request.title, None, request.status_file, request.log_file)


launch.writes_transcript = False
set_embedded_terminal_launcher(launch)
os.chmod("/", 0o777)
blocked = subprocess.run([helper, "status"], capture_output=True, text=True)
assert blocked.returncode != 0
assert "uid=0, gid=0, mode=0777" in blocked.stderr, blocked.stderr
TerminalRepository()._abrir_terminal(f"{helper} status", "BC250 installation recovery")
assert Path("/").stat().st_mode & 0o7777 == 0o755

# Recovery must still refuse a genuinely writable installed Python module.
module = Path("/usr/libexec/bc250-control-center/lib/system_setup_common.py")
module.chmod(0o664)
try:
    rejected = subprocess.run([helper, "status"], capture_output=True, text=True)
    assert rejected.returncode != 0
    assert "mode=0664" in rejected.stderr
finally:
    module.chmod(0o644)
print("APPLICATION_PERMISSION_RECOVERY_PASS")
