"""The installer names the runtime probe that failed, and never loses its exit status doing so.

R-1aad1216: on a Fedora with every package installed the installer said only
"the GUI runtime is still incomplete" and exited 2, which the terminal read as
a helper version mismatch. The real probe function and the real failure block
are extracted from scripts/install-local.sh and run here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install-local.sh"


def _fragments() -> tuple[str, str]:
    source = INSTALLER.read_text(encoding="utf-8")
    function = re.search(r"explain_python_gui_runtime\(\) \{\n.*?\nPY\n\}\n", source, re.S)
    block = re.search(r"    if ! check_python_gui_runtime; then\n(.*?)\n      exit 2\n    fi\n", source, re.S)
    assert function and block
    return function.group(0), block.group(0)


def _run(tmp_path: Path, env: dict) -> subprocess.CompletedProcess:
    function, block = _fragments()
    script = "set -euo pipefail\ncheck_python_gui_runtime() { return 1; }\n" + function + block
    return subprocess.run(["/usr/bin/bash", "-c", script], capture_output=True, text=True, timeout=120,
                          check=False, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), **env})


def test_a_broken_ssl_module_is_named_and_the_installer_still_exits_two(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "ssl.py").write_text("raise ImportError('broken ssl for the test')\n", encoding="utf-8")
    result = _run(tmp_path, {"PYTHONPATH": str(stub)})
    assert result.returncode == 2, result.stderr
    assert "[ERROR] The GUI runtime is still incomplete" in result.stderr
    assert "[ERROR]   ssl: ImportError: broken ssl for the test" in result.stderr
    assert result.stderr.rstrip().endswith("run the installer again.")


def test_an_explainer_that_cannot_run_does_not_hide_the_closing_lines(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    # No python3 on PATH: the explainer fails (127); the block must still finish.
    result = _run(tmp_path, {"PATH": str(empty)})
    assert result.returncode == 2, result.stderr
    assert "[ERROR] The GUI runtime is still incomplete" in result.stderr
    assert "[ERROR] No installed application code was replaced" in result.stderr


def test_every_probe_is_tried_and_only_the_failed_ones_are_printed(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "psutil.py").write_text("raise ImportError('no psutil here')\n", encoding="utf-8")
    result = _run(tmp_path, {"PYTHONPATH": str(stub)})
    lines = [line for line in result.stderr.splitlines() if line.startswith("[ERROR]   ")]
    assert lines == ["[ERROR]   psutil: ImportError: no psutil here"], result.stderr
