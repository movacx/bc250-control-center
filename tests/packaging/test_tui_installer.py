"""scripts/install-tui.sh: the terminal interface alone, installed, run again and removed."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run(tmp_path, *args, extra_env=None):
    env = dict(os.environ, HOME=str(tmp_path / "home"), PREFIX=str(tmp_path / "prefix"),
               BC250_SKIP_PRIVILEGED_HELPER="1", BC250_SKIP_DEPENDENCY_INSTALL="1")
    (tmp_path / "home").mkdir(exist_ok=True)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir(exist_ok=True)
    for tool in ("pacman", "rpm", "dpkg-query", "xbps-query", "apk", "sudo", "doas"):
        if not (fakebin / tool).exists():  # a test may have put its own there
            fake_tool(fakebin, tool, 'exit 1')
    fake_tool(fakebin, "findmnt", 'case "$*" in *' + str(tmp_path) + '*) echo rw ;; *) exit 1 ;; esac')
    env.update(extra_env or {})
    env["PATH"] = str(fakebin) + ":" + os.environ["PATH"]
    env["LANG"] = "C"
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    return subprocess.run(["bash", str(ROOT / "scripts" / "install-tui.sh"), *args], cwd="/tmp", env=env, input="", preexec_fn=lambda: os.umask(0o077),
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


def fake_tool(directory, name, body):
    directory.mkdir(exist_ok=True)
    tool = directory / name
    tool.write_text('#!/bin/sh\n' + body + '\n', encoding='utf-8')
    tool.chmod(0o755)
    return tool


@pytest.mark.parametrize(('tool', 'packages'), [
    ('pacman', 'pacman -S --needed python-psutil'), ('dnf', 'dnf install -y python3-psutil'),
    ('apt-get', 'apt-get install -y python3 python3-psutil'), ('zypper', 'python3-curses'),
    ('transactional-update', 'transactional-update --non-interactive pkg install'),
    ('xbps-install', 'xbps-install -Sy python3 python3-psutil'), ('apk', 'apk add --no-progress bash python3 py3-psutil'),
    ('emerge', 'emerge --ask=n'), ('', 'Nothing is installed with pip')])
def test_each_package_manager_gets_its_own_command_and_nothing_is_written(tmp_path, tool, packages):
    source = (ROOT / 'scripts/install-local.sh').read_text()
    block = source[source.index('if ! command -v python3 >/dev/null 2>&1; then'):source.index('if [[ ${#missing_python_deps_command[@]} -gt 0 && "${BC250_SKIP_DEPENDENCY_INSTALL')]
    fakebin = tmp_path / 'tools'
    fakebin.mkdir()
    fake_tool(fakebin, 'python3', 'exit 1')
    if tool:
        fake_tool(fakebin, tool, 'exit 1')
    result = subprocess.run(['/bin/bash', '-c', 'set -u; INSTALL_PROFILE=tui; missing_python_deps=0; python_gui_deps_missing=0;'
                             'missing_python_deps_reboot_notice=0; missing_python_deps_command=(); APP_DIR=x; BIN_DIR=y\n' .replace('\\n', '\n') + block],
                            env=dict(os.environ, PATH=str(fakebin), BC250_TUI_CHECK='1'), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert packages in result.stderr and 'Runtime: incomplete' in result.stdout
    for desktop in ('pyqt', 'PyQt', 'polkit', 'pkexec'):
        assert desktop not in result.stderr


@pytest.mark.parametrize('tool', ['pacman', 'rpm', 'dpkg-query', 'xbps-query', 'apk'])
def test_files_of_a_system_package_are_left_to_it(tmp_path, tool):
    app = tmp_path / 'prefix/share/bc250-control-center/frontends/tui/app.py'
    app.parent.mkdir(parents=True)
    app.write_text('packaged')
    for name in ('pacman', 'rpm', 'dpkg-query', 'xbps-query', 'apk'):
        fake_tool(tmp_path / 'fakebin', name, 'echo test-package; exit 0' if name == tool else 'exit 1')
    result = run(tmp_path)
    assert result.returncode == 6 and 'test-package' in result.stderr
    assert app.read_text() == 'packaged'


def test_a_missing_runtime_that_cannot_be_installed_replaces_nothing(tmp_path):
    fakebin = tmp_path / 'fakebin'
    fake_tool(fakebin, 'python3', 'case "$*" in *curses*) exit 1 ;; esac\nexec /usr/bin/python3 "$@"')
    fake_tool(fakebin, 'sudo', 'exit 1')
    result = run(tmp_path, extra_env={'BC250_SKIP_DEPENDENCY_INSTALL': '0'})
    assert result.returncode == 2 and 'Administrator access is needed' in result.stderr
    assert not (tmp_path / 'prefix').exists()


def test_without_administrator_access_the_interface_is_installed_and_says_what_is_missing(tmp_path):
    fakebin = tmp_path / 'fakebin'
    fake_tool(fakebin, 'sudo', 'exit 1')
    fake_tool(fakebin, 'findmnt', 'exit 1')
    result = run(tmp_path, extra_env={'BC250_SKIP_PRIVILEGED_HELPER': '0'})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'prefix/bin/bc250-control-center-tui').exists()
    if not Path('/run/ostree-booted').exists():
        assert 'protected helpers were not installed' in result.stderr


def test_help_via_sh_symlink_spaces_and_unrelated_directory(tmp_path):
    link = tmp_path / 'installer with spaces'
    link.symlink_to(ROOT / 'scripts/install-tui.sh')
    result = subprocess.run(['/bin/sh', str(link), '--help'], cwd='/tmp', input='',
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '--dry-run' in result.stdout


def test_the_terminal_profile_still_installs_the_protected_helpers():
    """Without them the interface could read the hardware but never change it."""
    source = (ROOT / 'scripts/install-local.sh').read_text()
    assert '\ninstall_privileged_pwm_components\n' in source
    assert '--keep-privileged' not in (ROOT / 'scripts/install-tui.sh').read_text()


def test_crlf_checkout_reports_how_to_repair_it(tmp_path):
    script = tmp_path / 'install-tui.sh'
    script.write_bytes((ROOT / 'scripts/install-tui.sh').read_bytes().replace(b'\n', b'\r\n'))
    for shell in ('/bin/sh', '/bin/bash'):
        result = subprocess.run([shell, str(script), '--check'], capture_output=True, text=True)
        assert result.returncode == 65
        assert 'Convert shell scripts to LF' in result.stderr


def test_shell_invocation_without_bash_is_clear(tmp_path):
    fake_tool(tmp_path, 'grep', 'exit 1')
    # printf is a shell builtin, so the bootstrap also works on BusyBox sh.
    result = subprocess.run(['/bin/bash', '-c', 'unset BASH_VERSION; . \"$1\"',
                             'sh', str(ROOT / 'scripts/install-tui.sh')],
                            env=dict(os.environ, PATH=str(tmp_path)), capture_output=True, text=True)
    assert result.returncode == 69
    assert 'install bash' in result.stderr


@pytest.mark.parametrize('failure', ['disk', 'launcher', 'signal'])
def test_failed_tui_upgrade_restores_payload_launchers_and_docs(tmp_path, failure):
    assert run(tmp_path).returncode == 0
    prefix = tmp_path / 'prefix'
    payload = prefix / 'share/bc250-control-center/src/old-marker'
    payload.write_text('previous version')
    launcher = prefix / 'bin/bc250-control-center-tui'
    launcher.write_text('#!/bin/sh\necho previous launcher\n')
    readme = prefix / 'share/doc/bc250-control-center/README.md'
    readme.write_text('previous docs')
    fakebin = tmp_path / 'fakebin'
    if failure == 'disk':
        fake_tool(fakebin, 'cp', 'case "$*" in *src*) echo "No space left on device" >&2; exit 1 ;; esac\nexec /bin/cp "$@"')
    else:
        action = 'kill -TERM "$PPID"' if failure == 'signal' else 'echo "injected launcher failure" >&2'
        fake_tool(fakebin, 'install', 'case "$*" in *entrypoints/bc250-control-center-tui*) ' + action + '; exit 1 ;; esac\nexec /usr/bin/install "$@"')
    result = run(tmp_path)
    assert result.returncode != 0, result.stdout
    assert payload.read_text() == 'previous version'
    assert launcher.read_text() == '#!/bin/sh\necho previous launcher\n'
    assert readme.read_text() == 'previous docs'
    assert not list((prefix / 'share').glob('bc250-control-center.update.*'))
    assert not list((prefix / 'share').glob('bc250-control-center.tree.previous.*'))


@pytest.mark.parametrize('version', ['3.10', '3.11', '3.12', '3.13', '3.14'])
def test_python_version_boundary(tmp_path, version):
    source = (ROOT / 'scripts/install-local.sh').read_text()
    function = source.split('require_supported_python() {', 1)[1].split('\n}\n', 1)[0]
    fake_tool(tmp_path, 'python3', 'if [ "$1" = -V ]; then echo Python ' + version + '; exit 0; fi\nexit ' + ('1' if version == '3.10' else '0'))
    result = subprocess.run(['/bin/bash', '-c', 'require_supported_python() {' + function + '\n}\nrequire_supported_python'],
                            env=dict(os.environ, PATH=str(tmp_path)), text=True, capture_output=True)
    assert result.returncode == (2 if version == '3.10' else 0)
    if version == '3.10':
        assert 'Python 3.11 or newer' in result.stderr


def test_check_and_dry_run_leave_no_prefix_and_need_no_tty(tmp_path):
    for argument in ('--check', '--dry-run'):
        result = run(tmp_path, argument)
        assert result.returncode == 0, result.stderr
        assert 'Plan:' in result.stdout and 'Nothing was changed' in result.stdout
        assert not (tmp_path / 'prefix').exists()


def test_tui_over_desktop_keeps_desktop_assets_and_handles_downgrade(tmp_path):
    prefix = tmp_path / 'prefix'
    desktop = prefix / 'share/applications/io.github.movacx.bc250-control-center.desktop'
    desktop.parent.mkdir(parents=True)
    desktop.write_text('[Desktop Entry]\nName=existing desktop\n')
    assert run(tmp_path).returncode == 0
    version = prefix / 'share/bc250-control-center/VERSION'
    version.write_text('999.0\n')
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert desktop.read_text() == '[Desktop Entry]\nName=existing desktop\n'
    assert version.read_text() == (ROOT / 'VERSION').read_text()


def test_the_web_installer_explains_itself_and_refuses_bad_arguments():
    script = str(ROOT / "scripts/install-web.sh")
    shown = subprocess.run(["bash", script, "--help"], capture_output=True, text=True, timeout=30)
    assert shown.returncode == 0 and "web setup" in shown.stdout
    assert subprocess.run(["bash", script, "--nope"], capture_output=True, timeout=30).returncode == 64
    assert subprocess.run(["bash", script, "--no-start", "x"], capture_output=True, timeout=30).returncode == 64
