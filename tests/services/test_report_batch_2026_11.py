"""Regressions from the reports of 2 to 5 November 2026, each with its real text."""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from bc250cc.infrastructure import (
    bazzite_async_compute,
    bazzite_memory_tuning,
    privacy,
    system_snapshot,
)
from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.shared import error_catalog

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "privileged/lib"))
import system_setup_kernel_args as kernel  # noqa: E402
from system_setup_common import Host  # noqa: E402

CYAN_SCRIPT = ROOT / "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"
AUR_SCRIPT = ROOT / "packaging/common/os-scripts/common/aur.sh"


def _repair(text: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the script's own repair program on a config file."""
    script = CYAN_SCRIPT.read_text(encoding="utf-8")
    body = re.search(r"complete_missing_switches\(\).*?<<'PY'\n(.*?)\nPY\n", script, re.S)[1]
    source, target = tmp_path / "config.toml", tmp_path / "out.toml"
    source.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, "-c", body, str(source), str(target)],
                          capture_output=True, text=True, check=False)


CONFIG = (
    "[gpu-usage]\nfix-metrics = true\nfix-freq = false\n fix-freq = false\n"
    'method = "busy-flag"\n[gpu]\nset-method = "smu"\n[dbus]\nenabled = true\n'
)


def test_a_repeated_key_in_one_table_is_repaired(tmp_path):
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(CONFIG)
    result = _repair(CONFIG, tmp_path)
    assert result.returncode == 0, result.stderr
    assert tomllib.loads((tmp_path / "out.toml").read_text())["gpu-usage"]["fix-freq"] is False


def test_a_repeated_key_with_another_value_is_never_guessed(tmp_path):
    result = _repair(CONFIG.replace(" fix-freq = false", " fix-freq = true"), tmp_path)
    assert result.returncode != 0
    assert "Conflicting" in result.stderr
    assert not (tmp_path / "out.toml").exists()


def test_a_healthy_config_is_left_alone(tmp_path):
    assert _repair(CONFIG.replace(" fix-freq = false\n", ""), tmp_path).returncode == 3


@pytest.mark.parametrize("action", ["status", "uninstall"])
def test_bazzite_45_can_still_check_and_remove_async_compute(action):
    assert "VERSION_ID" not in bazzite_async_compute.build_bazzite_async_compute_command(action)


def test_installing_async_compute_still_requires_bazzite_44():
    assert 'test "${VERSION_ID:-}" = 44' in bazzite_async_compute.build_bazzite_async_compute_command("install")


STALE = (
    "error: failed retrieving file 'python-filelock-3.31.2-1-any.pkg.tar.zst' from mirror.ps.kz : "
    "The requested URL returned error: 404\nwarning: failed to retrieve some files\n"
    "error: failed to commit transaction (failed to retrieve some files)\nErrors occurred, no packages were upgraded."
)


def test_a_stale_package_database_is_not_blamed_on_the_external_repository():
    entry = error_catalog.for_marker(STALE)
    assert entry.code == "BC250-PKG-005"
    assert "pacman -Syu" in entry.action


def test_a_repository_that_really_moved_keeps_its_diagnosis():
    detail = "error: failed retrieving file 'x.db' from github.com : The requested URL returned error: 404"
    assert error_catalog.for_marker(detail).code == "BC250-UPSTREAM-404"


def test_wine_and_rpm_ostree_timeouts_have_a_diagnosis():
    assert error_catalog.for_marker("wine: could not load kernel32.dll, status c0000135").code == "BC250-WINE-001"
    assert error_catalog.for_marker("error: Updating deployment: Timeout was reached").code == "BC250-TIMEOUT-001"


def test_a_workflow_runs_with_english_tool_messages(tmp_path):
    wrapped = workflow_wrapper('printf "%s" "$LANGUAGE" > ' + shlex.quote(str(tmp_path / "language")),
                               tmp_path / "status", tmp_path / "log", hold=False)
    subprocess.run(["bash", "-c", wrapped], input="", text=True, capture_output=True, timeout=30, check=False)
    assert (tmp_path / "language").read_text() == "en"


def test_mesa_takes_one_architecture_of_the_rpm_answer(monkeypatch):
    answers = {"rpm": "26.2.2-3.fc44\n26.2.2-3.fc44\n"}
    monkeypatch.setattr(system_snapshot, "_run", lambda argv: answers.get(argv[0], ""))
    assert system_snapshot._mesa() == "26.2.2-3.fc44"


def test_a_full_name_equal_to_the_product_does_not_rewrite_the_report(monkeypatch):
    monkeypatch.setattr(privacy, "_slow", lambda: {"users": set(), "real": {"bc250", "Ana Lopez"}, "wifi": set()})
    cleaned = privacy.redact_machine("BC250-CONFIG-001 reported by Ana Lopez")
    assert cleaned.startswith("BC250-CONFIG-001") and "Ana Lopez" not in cleaned


def test_a_failed_aur_clone_stops_before_makepkg(tmp_path):
    script = (
        "set -u; error() { echo \"ERR $*\"; }; ensure_arch_build_toolchain() { :; }; require_user_build() { :; }\n"
        "export_parallel_build_env() { :; }; run() { echo \"RAN $*\"; }\n"
        "clone_or_update() { return 1; }\n"
        f"source {shlex.quote(str(AUR_SCRIPT))}\n"
        f"cd {shlex.quote(str(tmp_path))}\n"
        "install_aur_package_direct umr || echo FAILED\n"
    )
    output = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30,
                            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}, check=False).stdout
    assert "FAILED" in output and "RAN makepkg" not in output


@pytest.mark.parametrize("policy", ["zswap-16", "zswap-32"])
def test_the_bazzite_memory_script_resizes_its_own_swapfile(policy):
    script = bazzite_memory_tuning.build_bazzite_memory_tuning_command(policy, 12)
    assert "different size" not in script
    assert 'sudo swapoff "$swap_path"' in script
    assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True, check=False).returncode == 0


def test_no_space_for_the_swapfile_is_reported_as_storage():
    entry = error_catalog.for_exit_status(73)
    assert entry.code == "BC250-STORAGE-001"


def test_a_grub_package_without_a_menu_is_not_taken_for_the_boot_loader(tmp_path, monkeypatch):
    """R-25b3684d: the grub package on a machine another loader boots."""
    host = Host(tmp_path)
    host.write("/etc/os-release", "ID=arch\n")
    host.write(kernel.GRUB_CONFIG, 'GRUB_CMDLINE_LINUX_DEFAULT="quiet"\n')
    host.write(kernel.CMDLINE, "root=PARTUUID=test rw rootfstype=ext4")
    monkeypatch.setattr(Host, "command", lambda _self, name: name == "grub-mkconfig")
    assert kernel._backend(host) == "unsupported"
    host.write(kernel.GRUB_OUTPUTS[0], "# menu\n")
    assert kernel._backend(host) == "grub"


def _bazzite_removal(tmp_path: Path, status: str) -> subprocess.CompletedProcess:
    """Run the real uninstall script against stand-ins for the system's commands."""
    from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

    calls = []

    class Repository(DependenciasRepository):
        estado_herramientas_cache = None

        def _os_repository(self):
            info = type("Info", (), {"family": "bazzite"})()
            return type("OSRepository", (), {"info": info})()

        def _abrir_terminal(self, command, title=""):
            calls.append(command)
            return "terminal"

    Repository().desinstalar_governor("cyan-skillfish-governor-smu")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "rpm": "exit 0",
        "sudo": 'echo "sudo $*" >> "$CALLS"; exit 0',
        "rpm-ostree": f"printf '%s' {shlex.quote(status)}",
        "cyan-skillfish-governor-smu": "exit 0",
    }
    for name, body in stubs.items():
        path = bin_dir / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)
    return subprocess.run(
        ["/usr/bin/bash", "-c", calls[0]], capture_output=True, text=True, timeout=30, check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALLS": str(tmp_path / "calls"), "HOME": str(tmp_path)},
    )


def test_cyan_inside_the_bazzite_image_is_disabled_not_uninstalled(tmp_path):
    """R-2eb2645b: the 40 CU community image carries the package itself."""
    result = _bazzite_removal(tmp_path, '{"deployments": [{"requested-packages": []}]}')
    assert result.returncode == 0, result.stdout + result.stderr
    assert "part of the system image" in result.stdout
    assert "rpm-ostree uninstall" not in (tmp_path / "calls").read_text()


def test_a_layered_cyan_is_still_uninstalled(tmp_path):
    result = _bazzite_removal(
        tmp_path, '{"deployments": [{"requested-packages": ["cyan-skillfish-governor-smu"]}]}')
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rpm-ostree uninstall cyan-skillfish-governor-smu" in (tmp_path / "calls").read_text()
    assert "PENDING" in result.stdout


def test_a_network_failure_during_download_is_not_called_a_stale_database(tmp_path):
    """pacman ends every failed download with the same line, whatever the cause."""
    detail = (
        "error: failed retrieving file 'a-1-any.pkg.tar.zst' from mirror : Could not resolve host: mirror\n"
        "warning: failed to retrieve some files\n"
        "error: failed to commit transaction (failed to retrieve some files)\n"
        "Errors occurred, no packages were upgraded."
    )
    entry = error_catalog.for_marker(detail)
    assert entry is None or entry.code != "BC250-PKG-005"
    assert "BC250-PKG-005" not in _terminal_output(detail, tmp_path)


def _terminal_output(detail: str, tmp_path: Path, status: int = 1) -> str:
    """What the user reads: the terminal has its own classifier, not ``for_marker``."""
    wrapped = workflow_wrapper(f"printf %s {shlex.quote(detail)}; exit {status}",
                               tmp_path / "status", tmp_path / "log", hold=False)
    return subprocess.run(["bash", "-c", wrapped], input="", text=True, capture_output=True,
                          timeout=30, check=False).stdout


@pytest.mark.parametrize(("report", "detail", "status", "expected"), [
    ("R-53af1e3f", STALE, 1, "BC250-PKG-005"),
    ("R-e1eaa882", "error: failed to init transaction (unable to lock database)", 1, "BC250-PKG-001"),
    ("R-8db5f5cd", "sudo: timed out reading password\nsudo: a password is required", 1, "BC250-AUTH-002"),
    ("R-9825733e", "error: Updating deployment: Timeout was reached", 1, "BC250-TIMEOUT-001"),
    ("R-48e8360b", "wine: could not load kernel32.dll, status c0000135", 1, "BC250-WINE-001"),
    ("R-a7519f9d", "error: Transaction in progress: upgrade", 1, "BC250-BUSY-001"),
    ("R-0bf19beb", "not enough free space on /var: 28 GiB in all", 73, "BC250-STORAGE-001"),
])
def test_the_terminal_gives_each_report_its_diagnosis(report, detail, status, expected, tmp_path):
    assert expected in _terminal_output(detail, tmp_path, status), report


def test_a_repository_that_really_moved_still_reads_as_upstream_in_the_terminal(tmp_path):
    detail = "error: failed retrieving file 'x.db' from github.com : The requested URL returned error: 404"
    assert "BC250-UPSTREAM-404" in _terminal_output(detail, tmp_path)


def test_a_cyan_layered_from_a_local_rpm_is_uninstalled(tmp_path):
    result = _bazzite_removal(tmp_path, '{"deployments": [{"requested-local-packages": '
                                        '["cyan-skillfish-governor-smu-0.4.14-1.fc44.x86_64"]}]}')
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rpm-ostree uninstall" in (tmp_path / "calls").read_text()


def test_an_unreadable_status_does_not_pretend_the_package_is_in_the_image(tmp_path):
    result = _bazzite_removal(tmp_path, "not json")
    assert "part of the system image" not in result.stdout
    assert "rpm-ostree uninstall" in (tmp_path / "calls").read_text()


def _swap_fragment(tmp_path: Path, existing: int, *, active: bool):
    """The real swapfile branch, run against stand-ins for the commands that need root."""
    script = bazzite_memory_tuning.build_bazzite_memory_tuning_command("zswap-16", 12).splitlines()
    start = next(i for i, line in enumerate(script) if line == 'if sudo test -e "$swap_path"; then')
    end = next(i for i, line in enumerate(script) if line.startswith("legacy_swap_unit="))
    bin_dir, calls = tmp_path / "bin", tmp_path / "calls"
    bin_dir.mkdir()
    swap = tmp_path / "bc250-zswap.swap"
    unit = tmp_path / "unit.swap"
    unit.write_text("# Managed by BC250 Control Center\n")
    if existing:
        swap.write_bytes(b"\0" * existing)
    (bin_dir / "sudo").write_text(
        '#!/bin/bash\ncase "$1 $2 $3" in\n'
        '  "stat -c %u") echo 0; exit 0;;\n  "stat -c %a") echo 600; exit 0;;\nesac\n'
        f'case "$1" in\n  swapoff) echo swapoff >> {calls}; exit 0;;\n'
        f'  btrfs) echo create >> {calls}; : > "$6"; exit 0;;\nesac\nexec "$@"\n')
    (bin_dir / "swapon").write_text(f"#!/bin/bash\n{'echo ' + str(swap) if active else ''}\n")
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    head = (f"set -eu\nswap_path={swap}\nswap_unit_path={unit}\nswap_bytes=16\nbc250_var_fs=btrfs\n"
            f"existing_bytes={existing}\n")
    result = subprocess.run(["/usr/bin/bash", "-c", head + "\n".join(script[start:end])],
                            capture_output=True, text=True, timeout=30, check=False,
                            env={"PATH": f"{bin_dir}:/usr/bin:/bin"})
    return result, calls.read_text().split() if calls.exists() else []


def test_a_swapfile_of_the_right_size_is_reused(tmp_path):
    result, calls = _swap_fragment(tmp_path, 16, active=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [] and "Reusing" in result.stdout


def test_a_swapfile_in_use_of_another_size_is_released_then_recreated(tmp_path):
    result, calls = _swap_fragment(tmp_path, 32, active=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == ["swapoff", "create"] and "Resizing" in result.stdout


def test_an_inactive_swapfile_of_another_size_is_recreated_without_swapoff(tmp_path):
    result, calls = _swap_fragment(tmp_path, 32, active=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == ["create"]


def _ostree_update(tmp_path: Path, failures: int) -> tuple[subprocess.CompletedProcess, int]:
    from bc250cc.infrastructure.self_update import _rpm_ostree_install

    bin_dir, count = tmp_path / "bin", tmp_path / "count"
    bin_dir.mkdir()
    (bin_dir / "rpm-ostree").write_text(
        '#!/bin/bash\nif [ "$1" = status ]; then echo \'{"deployments": [{}]}\'; exit 0; fi\n'
        f'n=$(($(cat {count} 2>/dev/null || echo 0) + 1)); echo $n > {count}\n'
        f'if [ $n -le {failures} ]; then echo "error: Transaction in progress: upgrade"; exit 1; fi\n'
        'echo done\n')
    (bin_dir / "sleep").write_text("#!/bin/bash\n")
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    result = subprocess.run(["/usr/bin/bash", "-c", _rpm_ostree_install("/tmp/a.rpm")], capture_output=True,
                            text=True, timeout=30, check=False, env={"PATH": f"{bin_dir}:/usr/bin:/bin"})
    return result, int(count.read_text())


def test_an_update_that_starts_at_the_same_moment_is_waited_for(tmp_path):
    result, attempts = _ostree_update(tmp_path, 1)
    assert result.returncode == 0 and attempts == 2


def test_rpm_ostree_retries_are_bounded_and_keep_the_failure(tmp_path):
    result, attempts = _ostree_update(tmp_path, 9)
    assert result.returncode != 0 and attempts == 3
