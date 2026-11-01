"""scripts/install-tui.sh: the terminal interface alone, installed, run again and removed."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(tmp_path, *args):
    env = dict(os.environ, HOME=str(tmp_path / "home"), PREFIX=str(tmp_path / "prefix"),
               BC250_SKIP_PRIVILEGED_HELPER="1", BC250_SKIP_DEPENDENCY_INSTALL="1")
    (tmp_path / "home").mkdir(exist_ok=True)
    return subprocess.run(["bash", str(ROOT / "scripts" / "install-tui.sh"), *args], cwd=ROOT, env=env,
                          text=True, capture_output=True, timeout=180, check=False)


def test_the_tui_profile_installs_launchers_without_desktop_files_and_uninstalls_cleanly(tmp_path):
    prefix = tmp_path / "prefix"
    for _ in range(2):  # a second run updates the same installation
        completed = run(tmp_path)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (prefix / "bin" / "bc250-control-center-tui").stat().st_mode & 0o111
    assert (prefix / "share" / "bc250-control-center" / "frontends" / "tui" / "app.py").is_file()
    assert (prefix / "share/bc250-control-center/requirements-web.txt").is_file()
    assert not (prefix / "share" / "applications").exists() and not (prefix / "share" / "icons").exists()
    assert "GUI:" not in completed.stdout and "Terminal interface:" in completed.stdout

    completed = run(tmp_path, "--uninstall", "--yes", "--keep-privileged")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not [path for path in prefix.rglob("*") if path.is_file()]


def test_the_tui_profile_asks_only_for_the_terminal_dependencies():
    source = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")
    assert "import curses, psutil" in source
    assert '[[ "$INSTALL_PROFILE" == "desktop" && ${#missing_python_deps_command[@]} -gt 0 ]]' in source


def test_unknown_arguments_are_refused(tmp_path):
    assert run(tmp_path, "--bogus").returncode == 64
