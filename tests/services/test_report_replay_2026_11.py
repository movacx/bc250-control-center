"""Replays of the reports of 5 to 10 November 2026, with their real log text.

Each case runs the exact lines a user saw through the terminal wrapper, with
the exit status the failing program really returns, and through the desktop's
``diagnose_error``. Before this, the wrapper read a helper's meaning into the
status of whatever ran last: ``make`` 2 and ``systemctl status`` 3 were "the
interface and protected helper are different versions", ``curl --fail`` 22 was
"Cyan is stopped" and ``curl`` 16 "Linux refused access".
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import system_setup
from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.shared import error_catalog
from frontends.desktop.core.error_diagnostics import diagnose_error


def _terminal(detail: str, tmp_path: Path, status: int = 1) -> str:
    """What the user reads after the workflow: the wrapper's own diagnosis."""
    wrapped = workflow_wrapper(f"printf '%s\\n' {shlex.quote(detail)}; exit {status}",
                               tmp_path / "status", tmp_path / "log", hold=False)
    return subprocess.run(["bash", "-c", wrapped], input="", text=True, capture_output=True,
                          timeout=30, check=False).stdout


def _code(output: str) -> str:
    return output.split("Diagnostic code: ", 1)[1].split()[0]


# R-bb33f44b: Oberon on SteamOS, linux/types.h missing. make exits 2.
OBERON_HEADERS = (
    "/usr/include/bits/sched.h:68:12: fatal error: linux/types.h: No such file or directory\n"
    "   68 | #  include <linux/types.h>\n"
    "      |            ^~~~~~~~~~~~~~~\n"
    "compilation terminated.\n"
    "make[2]: *** [_deps/yaml-cpp-build/CMakeFiles/yaml-cpp.dir/build.make:121: _deps/yaml-cpp-build/CMakeFiles/yaml-cpp.dir/src/convert.cpp.o] Error 1\n"
    "make[1]: *** [CMakeFiles/Makefile2:1094: _deps/yaml-cpp-build/CMakeFiles/yaml-cpp.dir/all] Error 2\n"
    "make: *** [Makefile:136: all] Error 2"
)

# R-79e92b51: the SteamOS audio tools, built for a newer glibc. make exits 2.
AUDIO_GLIBC = (
    "    File \"deps/usr/lib/python3.14/selectors.py\", line 11, in <module>\n"
    "      import math\n"
    "ImportError: /usr/lib/libm.so.6: version `GLIBC_2.44' not found (required by "
    "deps/usr/lib/python3.14/lib-dynload/math.cpython-314-x86_64-linux-gnu.so)\n"
    "make[4]: *** [Makefile:156: tools/bpf/resolve_btfids/libbpf/bpf_helper_defs.h] Error 1\n"
    "make[1]: *** Waiting for unfinished jobs....\n"
    "make: *** [Makefile:248: __sub-make] Error 2"
)

# R-53376560: Oberon built in fedora:latest on an older Bazzite; the unit is in
# auto-restart and the flow ends with ``systemctl status``, which exits 3.
OBERON_AUTO_RESTART = (
    "[sudo] password for user:\n"
    "● oberon-governor.service - Oberon GPU governor\n"
    "     Loaded: loaded (/etc/systemd/system/oberon-governor.service; enabled; preset: disabled)\n"
    "     Active: activating (auto-restart) (Result: exit-code) since Sun 2026-11-08 14:35:43 EST; 10ms ago\n"
    "    Process: 78314 ExecStart=/usr/local/bin/oberon-governor (code=exited, status=1/FAILURE)\n"
    "   Main PID: 78314 (code=exited, status=1/FAILURE)"
)

# R-530bd5f6: GitHub answered 504 three times. curl --fail exits 22.
CURL_504 = (
    "  % Total    % Received % Xferd  Average Speed  Time    Time    Time   Current\n"
    "curl: (22) The requested URL returned error: 504\n"
    "Warning: Problem : HTTP error. Retrying in 2 seconds. 1 retry left.\n"
    "  0      0   0      0   0      0      0      0                              0\n"
    "curl: (22) The requested URL returned error: 504"
)

# R-cc0af5ae: a 118 MB download cut at 91 %. curl exits 16.
CURL_NGHTTP2 = (
    "Downloading bc250-opticlient-1.0.7-bc250.5-linux-x64.tar.gz (118 MB)...\n"
    "#################################################################                 91.6%\n"
    "curl: (16) nghttp2 shuts down connection with error 6: FRAME_SIZE_ERROR"
)

# R-86b82fd2: no DNS while cloning bc250_smu_oc. git exits 128.
GIT_DNS = (
    "Cloning into '/home/u/.local/share/bc250-control-center/ResourceTools/bc250_smu_oc'...\n"
    "fatal: unable to access 'https://github.com/bc250-collective/bc250_smu_oc/': Could not resolve host: github.com"
)

# R-86d44da1: Valve's package server answered 504 for a .sig. pacman exits 1.
PACMAN_504 = (
    ":: Retrieving packages...\n"
    " libxdamage-1.1.7-1-x86_64 is up to date\n"
    "error: failed retrieving file 'libxdamage-1.1.7-1-x86_64.pkg.tar.zst.sig' from steamdeck-packages.steamos.cloud : The requested URL returned error: 504\n"
    "warning: failed to retrieve some files\n"
    "error: failed to commit transaction (failed to retrieve some files)\n"
    "Errors occurred, no packages were upgraded."
)

# R-410912eb: a package list older than the mirrors. pacman exits 1.
PACMAN_MIRROR_404 = (
    "error: failed retrieving file 'python-pip-26.2.1-1-any.pkg.tar.zst' from arch.mirror.constant.com : The requested URL returned error: 404\n"
    "error: failed retrieving file 'python-filelock-3.31.2-1-any.pkg.tar.zst' from in.arch.niranjan.co : The requested URL returned error: 404\n"
    "warning: too many errors from in.arch.niranjan.co, skipping for the remainder of this transaction\n"
    "warning: failed to retrieve some files\n"
    "error: failed to commit transaction (failed to retrieve some files)\n"
    "Errors occurred, no packages were upgraded."
)

# R-fc1cfbe2: SteamOS said the root was writable; pacman could not write.
STEAMOS_READONLY_DB = (
    ":: Processing package changes...\n"
    "error: could not create directory /usr/lib/holo/pacmandb/local/ninja-1.13.2-3/: Read-only file system\n"
    "error: could not commit transaction\n"
    "error: failed to commit transaction (transaction aborted)\n"
    "Errors occurred, no packages were upgraded.\n"
    "warning: could not remove lock file /usr/lib/holo/pacmandb/db.lck\n"
    "Warning: The rootfs is already read-only!\n"
    "         Nothing is performed."
)

# R-a45942d4: Proton's wine inside a Toolbx passes test -x and cannot load.
WINE_TOOLBX = (
    "[helixsr-setup] [#####---------------]   25%  0:11  starting the shader compiler\n"
    "/home/u/.local/share/HelixSR/dxc-wine.sh: line 5: /home/u/.local/share/Steam/steamapps/common/Proton 10.0/files/bin/wine: cannot execute: required file not found\n"
    "[helixsr-setup] error: the setup stopped (exit 1)\n"
    "The network was not built. HelixSR is installed; use Build network files to try again."
)

# R-1aad1216: the installer's own refusal, which exits 2 like make does.
INSTALLER_RUNTIME = (
    "Nothing to do.\n"
    "[ERROR] The GUI runtime is still incomplete after dependency installation. Probes that failed:\n"
    "[ERROR]   Qt SVG plugin: AssertionError: Qt SVG image plugin is missing (qt6-svg / qt6-qtsvg / libqt6svg6)\n"
    "[ERROR] No installed application code was replaced. Repair the native packages named above and run the installer again."
)

# R-00516dc1: the system setup helper's own lock.
SETUP_LOCK = (
    "== BC250 optional system setup (testing) ==\n"
    "[sudo] password for name:\n"
    "ERROR: Another BC250 system setup change is running; try again when it finishes\n"
    "Setup was not confirmed. Existing user swap and original boot entries were not intentionally removed. Review status before retrying."
)

# R-506fdded: rpm-ostree cannot rebuild a layer the repositories no longer carry.
OSTREE_LAYER = (
    "rpm-md repo 'updates-archive' (cached); generated: 2026-11-05T01:24:01Z solvables: 6027\n"
    "error: Packages not found: coolercontrol"
)

# R-64bcb05c: APT warnings about other repositories, then the real cause.
APT_LOCK = (
    "W: An error occurred during the signature verification. The repository is not updated and the previous index files will be used. "
    "GPG error: http://dl.google.com/linux/earth/deb stable InRelease: The following signatures couldn't be verified because the public key is not available: NO_PUBKEY FD533C07C264648F\n"
    "W: Failed to fetch https://apt.packages.shiftkey.dev/ubuntu/dists/any/InRelease  Certificate verification failed: The certificate is NOT trusted.\n"
    "W: Some index files failed to download. They have been ignored, or old ones used instead.\n"
    "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 1602831 (apt-get)\n"
    "N: Be aware that removing the lock file is not a solution and may break your system.\n"
    "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend), is another process using it?"
)

# R-e20dd96d: sudo timed out after a long Bazzite layering step.
SUDO_TIMEOUT = (
    "[INFO] sudo dnf5 -y copr enable filippor/bazzite\n"
    "[sudo] password for name:\n"
    "sudo: timed out reading password\n"
    "sudo: a password is required\n"
    "BC250_RESULT status=error component=governor code=1 message=apply\\ failed\n"
    "[ERROR] Operation failed at line 38 with exit code 1"
)


@pytest.mark.parametrize(("report", "detail", "status", "expected", "never"), [
    ("R-bb33f44b", OBERON_HEADERS, 2, "BC250-BUILD-003", "BC250-PROTOCOL-001"),
    ("R-79e92b51", AUDIO_GLIBC, 2, "BC250-RUNTIME-001", "BC250-PROTOCOL-001"),
    ("R-53376560", OBERON_AUTO_RESTART, 3, "BC250-GENERAL-001", "BC250-PROTOCOL-001"),
    ("R-530bd5f6", CURL_504, 22, "BC250-NET-001", "BC250-DBUS-001"),
    ("R-cc0af5ae", CURL_NGHTTP2, 16, "BC250-NET-001", "BC250-PERM-001"),
    ("R-86b82fd2", GIT_DNS, 128, "BC250-NET-001", "BC250-GENERAL-001"),
    ("R-86d44da1", PACMAN_504, 1, "BC250-NET-001", "BC250-PKG-005"),
    ("R-410912eb", PACMAN_MIRROR_404, 1, "BC250-PKG-005", "BC250-UPSTREAM-404"),
    ("R-fc1cfbe2", STEAMOS_READONLY_DB, 1, "BC250-IMMUTABLE-002", "BC250-IMMUTABLE-001"),
    ("R-a45942d4", WINE_TOOLBX, 1, "BC250-WINE-002", "BC250-GENERAL-001"),
    ("R-1aad1216", INSTALLER_RUNTIME, 2, "BC250-WORKFLOW-001", "BC250-PROTOCOL-001"),
    ("R-00516dc1", SETUP_LOCK, 1, "BC250-BUSY-001", "BC250-WORKFLOW-001"),
    ("R-506fdded", OSTREE_LAYER, 1, "BC250-PKG-004", "BC250-GENERAL-001"),
    ("R-64bcb05c", APT_LOCK, 100, "BC250-PKG-001", "BC250-PKG-002"),
    ("R-e20dd96d", SUDO_TIMEOUT, 1, "BC250-AUTH-002", "BC250-WORKFLOW-001"),
])
def test_the_terminal_gives_each_report_the_right_code(report, detail, status, expected, never, tmp_path):
    output = _terminal(detail, tmp_path, status)
    assert _code(output) == expected, (report, output)
    assert never not in output, report


def test_the_installers_own_lines_are_what_the_user_reads(tmp_path):
    output = _terminal(INSTALLER_RUNTIME, tmp_path, 2)
    assert "What happened: The GUI runtime is still incomplete" in output
    assert "Qt SVG plugin: AssertionError" in output
    assert "different versions" not in output


def test_the_missing_setup_helper_is_a_helper_problem_not_a_service_one(tmp_path):
    """R-2c5122d2: the helper check printed a plain line and exited 69 (SERVICE-003 by number)."""
    command = system_setup.command("acpi-check")
    line = next(part for part in command.splitlines() if "test -x" in part)
    assert "ERROR: " in line and "exit 69" in line
    # The same guard, with the helper path pointed at nothing.
    guard = line.replace(str(system_setup.HELPER), str(tmp_path / "missing-helper"))
    wrapped = workflow_wrapper(guard, tmp_path / "status", tmp_path / "log", hold=False)
    result = subprocess.run(["bash", "-c", wrapped], input="", text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 69
    assert _code(result.stdout) == "BC250-HELPER-001"
    assert "BC250-SERVICE-003" not in result.stdout


def test_sudo_timing_out_no_longer_claims_nothing_changed(tmp_path):
    """R-e20dd96d: UMR had already been layered when sudo timed out."""
    output = _terminal(SUDO_TIMEOUT, tmp_path)
    assert "No hardware change was applied" not in output
    assert "No hardware change was applied" not in error_catalog.BY_CODE["BC250-AUTH-002"].action
    assert "No hardware change was applied" not in diagnose_error("sudo: a password is required").action


@pytest.mark.parametrize(("report", "detail", "context", "expected"), [
    ("R-bb33f44b", OBERON_HEADERS, "GPU governor", "BC250-BUILD-003"),
    ("R-79e92b51", AUDIO_GLIBC, "Prepare BC250 SteamOS compatibility", "BC250-RUNTIME-001"),
    ("R-53376560", "/usr/local/bin/oberon-governor: /lib64/libstdc++.so.6: version `GLIBCXX_3.4.35' not found "
                   "(required by /usr/local/bin/oberon-governor)", "GPU governor", "BC250-RUNTIME-001"),
    ("R-530bd5f6", CURL_504, "GFX1013 async compute", "BC250-NET-001"),
    ("R-cc0af5ae", CURL_NGHTTP2, "FSR4", "BC250-NET-001"),
    ("R-86b82fd2", GIT_DNS, "Prepare BC250 system", "BC250-NET-001"),
    ("R-410912eb", PACMAN_MIRROR_404, "update", "BC250-PKG-005"),
    ("R-fc1cfbe2", STEAMOS_READONLY_DB, "Mesa RADV SteamOS", "BC250-IMMUTABLE-002"),
    ("R-a45942d4", WINE_TOOLBX, "HelixSR", "BC250-WINE-002"),
    # The bridge's refusal reached the user as GPU-900 through the page context.
    ("R-c6ab33f2", "VRChat has anti-cheat (EasyAntiCheat): HelixSR Scaler can get the account banned in online play; "
                   "only with --anticheat-ok yes (offline / single-player use)", "GPU governor", "BC250-UPSCALE-002"),
    # The editor's false positive (fixed in the editor itself) is a configuration fault, not telemetry.
    ("R-2942b02f", "Duplicate gpu-usage.fix-freq key in governor TOML.", "GPU governor", "BC250-CONFIG-001"),
    ("R-2c5122d2", "ERROR: Update/reinstall Control Center to install the protected system setup helper.", "", "BC250-HELPER-001"),
    ("R-00516dc1", SETUP_LOCK, "", "BC250-BUSY-001"),
    ("R-506fdded", OSTREE_LAYER, "update", "BC250-PKG-004"),
    ("R-64bcb05c", APT_LOCK, "TV control", "BC250-PKG-001"),
    ("R-cbc5ba02", "The Cyan governor must be active before changing its voltage curve.", "GPU governor", "BC250-GPU-008"),
])
def test_the_desktop_gives_each_report_the_right_code(report, detail, context, expected):
    assert diagnose_error(detail, context=context).code == expected, report


# ------------------------------------------------------------------ negatives


def test_the_guards_own_restore_line_is_not_a_pending_deployment(tmp_path):
    """Every failed SteamOS flow ends with this INFO line; it used to print IMMUTABLE-001."""
    output = _terminal("make: *** [Makefile:136: all] Error 2\n[INFO] Restoring SteamOS read-only protection.", tmp_path, 2)
    assert _code(output) == "BC250-BUILD-003"
    alone = _terminal("[INFO] Restoring SteamOS read-only protection.", tmp_path)
    assert _code(alone) == "BC250-GENERAL-001"
    assert error_catalog.for_marker("[INFO] Restoring SteamOS read-only protection.") is None
    assert diagnose_error("[INFO] Restoring SteamOS read-only protection.").code != "BC250-IMMUTABLE-001"
    assert error_catalog.for_marker("[ERROR] Failed to restore SteamOS read-only protection.").code == "BC250-IMMUTABLE-001"


def test_a_glibc_mismatch_on_bazzite_is_not_called_steamos_build_tools(tmp_path):
    detail = "oberon-governor: /lib64/libc.so.6: version `GLIBC_2.38' not found (required by oberon-governor)"
    assert _code(_terminal(detail, tmp_path)) == "BC250-RUNTIME-001"
    assert "SteamOS build tools" not in _terminal(detail, tmp_path)
    assert diagnose_error(detail).code == "BC250-RUNTIME-001"


def test_a_mirror_404_and_a_github_404_are_told_apart(tmp_path):
    github = "error: failed retrieving file 'bc250.db' from github.com : The requested URL returned error: 404"
    mirror = "error: failed retrieving file 'bc250.db' from mirror.ps.kz : The requested URL returned error: 404"
    assert _code(_terminal(github, tmp_path)) == "BC250-UPSTREAM-404"
    assert diagnose_error(github).code == "BC250-UPSTREAM-404"
    assert "BC250-UPSTREAM-404" not in _terminal(mirror, tmp_path)
    assert diagnose_error(mirror).code != "BC250-UPSTREAM-404"


def test_a_duplicate_toml_key_is_a_configuration_fault_in_both_surfaces():
    message = "Duplicate gpu-usage.fix-freq key in governor TOML."
    assert diagnose_error(message, context="GPU governor").code == "BC250-CONFIG-001"
    assert diagnose_error("Cannot overwrite a value (at line 3, column 2)", context="GPU governor").code == "BC250-CONFIG-001"


def test_a_recovered_dns_error_does_not_outrank_the_build_that_failed_after_it(tmp_path):
    detail = (
        "fatal: unable to access 'https://github.com/x/y/': Could not resolve host: github.com\n"
        "[INFO] Retrying the clone\n"
        "src/main.cpp:12:10: fatal error: yaml-cpp/yaml.h: No such file or directory\n"
        "compilation terminated.\n"
        "make: *** [Makefile:136: all] Error 2"
    )
    assert _code(_terminal(detail, tmp_path, 2)) == "BC250-BUILD-003"
    assert diagnose_error(detail, context="GPU governor").code == "BC250-BUILD-003"


def test_a_package_list_naming_libnghttp2_is_not_a_network_fault(tmp_path):
    detail = "warning: libnghttp2-1.65.0-1 is up to date -- skipping\nerror: failed to prepare transaction (could not satisfy dependencies)"
    assert "BC250-NET-001" not in _terminal(detail, tmp_path)
    assert diagnose_error(detail).code != "BC250-NET-001"
    assert (error_catalog.for_marker(detail) or error_catalog.GENERAL_FAILURE).code != "BC250-NET-001"


def test_a_game_folder_named_easyanticheat_is_not_an_anti_cheat_refusal(tmp_path):
    detail = "found game folder: /games/VRChat/EasyAntiCheat\nerror: the game is running; close it first"
    assert "BC250-UPSCALE-002" not in _terminal(detail, tmp_path)
    assert diagnose_error(detail, context="HelixSR").code != "BC250-UPSCALE-002"
    assert error_catalog.for_marker(detail) is None


def test_an_available_glibc_version_is_not_a_library_mismatch(tmp_path):
    detail = "GLIBC_2.38 is available\nfoo: command not found"
    assert "BC250-RUNTIME-001" not in _terminal(detail, tmp_path, 127)
    assert error_catalog.for_marker(detail) is None
    assert diagnose_error(detail).code != "BC250-RUNTIME-001"


def test_the_scripts_pci_check_reads_as_missing_hardware_in_the_terminal(tmp_path):
    """R-ffde613d and two more Mint reports: bc250-gfx1013-source.sh's die() line, now paren-free."""
    for script in ("scripts/system/bc250-gfx1013-source.sh", "scripts/system/bc250-async-compute-radv.sh"):
        source = Path(script).read_text(encoding="utf-8")
        assert 'die "AMD BC-250 PCI device 1002:13fe was not found."' in source, script
        assert "(PCI 1002:13fe) was not found" not in source, script
    output = _terminal("[ERROR] AMD BC-250 PCI device 1002:13fe was not found.", tmp_path)
    assert _code(output) == "BC250-HW-001"
    assert "What happened: AMD BC-250 PCI device 1002:13fe was not found." in output


def test_upscale_002_does_not_promise_an_untouched_game_folder():
    for text in (error_catalog.BY_CODE["BC250-UPSCALE-002"].cause,
                 diagnose_error("VRChat has anti-cheat (EasyAntiCheat): refused").cause):
        assert "nothing in the game folder" not in text
        assert "declined to install" in text


def test_gpu_008_names_the_real_governor_controls():
    action = error_catalog.BY_CODE["BC250-GPU-008"].action
    assert "Start governor" in action and "Connected" in action and "Enable" not in action
    assert diagnose_error("The Cyan governor must be active before changing its voltage curve.").action == action


def test_a_curl_write_error_is_not_a_network_fault_in_the_terminal(tmp_path):
    output = _terminal("curl: (23) Failure writing output to destination", tmp_path, 23)
    assert "BC250-NET-001" not in output
    assert "BC250-RANGE-001" not in output  # 23 used to be read as a helper's range status


def test_pacman_404_from_the_steam_server_with_a_signature_failure_keeps_the_signature(tmp_path):
    detail = ('error: libxdamage: signature from "Valve" is invalid\n'
              'error: failed to commit transaction (invalid or corrupted package)')
    assert _code(_terminal(detail, tmp_path)) == "BC250-PKG-002"


def test_apt_warnings_do_not_hide_the_lock_that_stopped_the_flow():
    assert diagnose_error(APT_LOCK).code == "BC250-PKG-001"
    assert error_catalog.for_marker(APT_LOCK).code == "BC250-PKG-001"


def test_the_new_codes_are_registered_and_translatable():
    for code in ("BC250-BUILD-003", "BC250-RUNTIME-001", "BC250-IMMUTABLE-002",
                 "BC250-GPU-008", "BC250-UPSCALE-002", "BC250-WINE-002"):
        entry = error_catalog.BY_CODE[code]
        assert entry.summary and entry.cause and entry.action
        for marker in entry.markers:
            # The terminal reads markers as POSIX ERE and the panel as literals:
            # no metacharacters ("." matches itself too; "]" is literal outside a bracket).
            assert not set(marker) & set("[(){}*+?^$|\\"), (code, marker)
    assert error_catalog.HARDWARE_GATE_MESSAGE in error_catalog.translatable_strings()


def test_declining_the_package_manager_is_a_calm_cancel(tmp_path):
    """R-097a4530: the user answered "n" to pacman; that is not a failure."""
    detail = ("Total Installed Size:  311.64 MiB\n"
              ":: Proceed with installation? [Y/n] n")
    output = _terminal(detail, tmp_path, status=1)
    assert "Diagnostic code" not in output
    assert "Cancelled: you answered no" in output
    assert (tmp_path / "status").read_text().strip() == "130"


def test_a_real_failure_after_a_yes_is_still_diagnosed(tmp_path):
    output = _terminal(":: Proceed with installation? [Y/n] y\nerror: failed to commit transaction", tmp_path)
    assert "Diagnostic code" in output
