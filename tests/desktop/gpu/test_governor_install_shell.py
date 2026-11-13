import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.dependencias_repository import (
    CYAN_GOVERNOR_REPOSITORY,
    OBERON_REPOSITORY,
    OBERON_REVIEWED_COMMIT,
    OBERON_YAML_CPP_REVIEWED_COMMIT,
    STEAMOS_CYAN_REVIEWED_COMMIT,
    DependenciasRepository,
)
from bc250cc.infrastructure.governor_install_shell import (
    cyan_runtime_verification_command,
    cyan_upstream_runtime_command,
    oberon_install_command,
)


def _os_repository(tmp_path: Path, family: str):
    installer = tmp_path / "scripts/common/install-cyan-upstream-release.sh"
    installer.parent.mkdir(parents=True, exist_ok=True)
    installer.write_text("#!/bin/bash\n", encoding="utf-8")
    return SimpleNamespace(
        info=SimpleNamespace(family=family, label=family.title()),
        scripts_root=tmp_path / "scripts",
    )


def _repository(tmp_path: Path):
    repository = DependenciasRepository.__new__(DependenciasRepository)
    repository._tool_dir = lambda: tmp_path / "tools"
    repository._clone_or_update_commit_command = (
        lambda url, destination, revision: (
            f"CHECKOUT {url} {destination} {revision}"
        )
    )
    return repository


@pytest.mark.parametrize(
    "family",
    (
        "arch", "manjaro", "cachyos", "debian", "ubuntu", "fedora",
        "bazzite", "steamos", "alpine", "gentoo",
    ),
)
def test_oberon_delegate_matches_extracted_builder_and_is_valid_bash(tmp_path, family):
    os_repository = _os_repository(tmp_path, family)
    repository = _repository(tmp_path)
    destination = tmp_path / "tools/oberon-governor"
    checkout = repository._clone_or_update_commit_command(
        OBERON_REPOSITORY, destination, OBERON_REVIEWED_COMMIT
    )
    expected = oberon_install_command(
        os_repository,
        destination=destination,
        checkout_command=checkout,
        yaml_cpp_revision=OBERON_YAML_CPP_REVIEWED_COMMIT,
    )
    actual = repository._oberon_install_command(os_repository)
    assert actual == expected
    syntax = subprocess.run(
        ["bash", "-n"], input=actual, text=True, capture_output=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr


@pytest.mark.parametrize("family", ("ubuntu", "steamos"))
def test_cyan_delegate_matches_extracted_builder(tmp_path, family):
    os_repository = _os_repository(tmp_path, family)
    repository = _repository(tmp_path)
    destination = tmp_path / "tools/cyan-skillfish-governor-smu"
    installer = tmp_path / "scripts/common/install-cyan-upstream-release.sh"
    checkout = repository._clone_or_update_commit_command(
        CYAN_GOVERNOR_REPOSITORY,
        destination,
        STEAMOS_CYAN_REVIEWED_COMMIT,
    )
    expected = cyan_upstream_runtime_command(
        os_repository,
        destination=destination,
        installer=installer,
        checkout_command=checkout,
        reviewed_release="v0.4.15",
    )
    actual = repository._cyan_upstream_runtime_command(os_repository)
    assert actual == expected
    assert "BC250_CYAN_RELEASE_TAG=v0.4.15" in actual


def test_cyan_verification_delegate_is_exact_and_valid_bash():
    actual = DependenciasRepository._cyan_runtime_verification_command()
    assert actual == cyan_runtime_verification_command()
    syntax = subprocess.run(
        ["bash", "-n"], input=actual, text=True, capture_output=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr


def test_unknown_oberon_family_fails_before_command_generation(tmp_path):
    os_repository = _os_repository(tmp_path, "unknown")
    with pytest.raises(RuntimeError, match="no validated Oberon build strategy"):
        oberon_install_command(
            os_repository,
            destination=tmp_path / "oberon",
            checkout_command="CHECKOUT",
            yaml_cpp_revision=OBERON_YAML_CPP_REVIEWED_COMMIT,
        )


def test_steamos_repairs_a_pruned_libdrm_development_payload(tmp_path):
    command = oberon_install_command(
        _os_repository(tmp_path, "steamos"),
        destination=tmp_path / "oberon",
        checkout_command="CHECKOUT",
        yaml_cpp_revision="reviewed-yaml",
    )
    assert "pkg-config --exists libdrm libdrm_amdgpu" in command
    assert "sudo pacman -S --noconfirm libdrm" in command
    assert "exit 54" in command
    assert "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" in command


@pytest.mark.parametrize(
    ("family", "package_command", "development_package"),
    (
        ("arch", "pacman", "libdrm"),
        ("debian", "apt-get", "libdrm-dev"),
        ("ubuntu", "apt-get", "libdrm-dev"),
        ("fedora", "dnf", "libdrm-devel"),
        ("alpine", "apk", "libdrm-dev"),
        ("gentoo", "emerge", "x11-libs/libdrm"),
        ("bazzite", "podman", "libdrm-devel"),
    ),
)
def test_oberon_build_strategy_installs_the_native_libdrm_development_payload(
    tmp_path, family, package_command, development_package
):
    command = oberon_install_command(
        _os_repository(tmp_path, family),
        destination=tmp_path / "oberon",
        checkout_command="CHECKOUT",
        yaml_cpp_revision="reviewed-yaml",
    )
    assert package_command in command
    assert development_package in command


@pytest.mark.parametrize("family", ("arch", "ubuntu", "fedora", "bazzite"))
def test_oberon_applies_and_verifies_gcc_compatibility_patch(tmp_path, family):
    command = oberon_install_command(
        _os_repository(tmp_path, family),
        destination=tmp_path / "oberon",
        checkout_command="CHECKOUT",
        yaml_cpp_revision="reviewed-yaml",
    )

    assert 'sed -i "1i#include <cstdint>" "$yaml_cpp_emitter"' in command
    assert 'grep -Fqx "#include <cstdint>" "$yaml_cpp_emitter"' in command
    assert "yaml-cpp GCC compatibility patch could not be applied" in command
    assert "yaml-cpp\\/null.h" not in command
    assert command.index("yaml_cpp_emitter=") < command.index("cmake --build")

    if family == "bazzite":
        assert "yaml_cpp_emitter=build/_deps/yaml-cpp-src/src/emitterutils.cpp" in command
    else:
        expected = tmp_path / "oberon/build/_deps/yaml-cpp-src/src/emitterutils.cpp"
        assert f"yaml_cpp_emitter={expected}" in command


def test_oberon_gcc_patch_handles_yaml_cpp_quoted_include_and_is_idempotent(tmp_path):
    destination = tmp_path / "oberon"
    emitter = destination / "build/_deps/yaml-cpp-src/src/emitterutils.cpp"
    emitter.parent.mkdir(parents=True)
    emitter.write_text(
        '#include "yaml-cpp/null.h"\n\nuint16_t code_point;\n',
        encoding="utf-8",
    )
    command = oberon_install_command(
        _os_repository(tmp_path, "arch"),
        destination=destination,
        checkout_command="CHECKOUT",
        yaml_cpp_revision="reviewed-yaml",
    )
    patch = "yaml_cpp_emitter=" + command.split("yaml_cpp_emitter=", 1)[1].split(
        "; cmake --build", 1
    )[0]

    for _ in range(2):
        result = subprocess.run(
            ["bash", "-c", f"set -Eeuo pipefail; {patch}"],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    patched_source = emitter.read_text(encoding="utf-8")
    assert patched_source.startswith("#include <cstdint>\n")
    assert patched_source.count("#include <cstdint>") == 1


@pytest.mark.parametrize("openrc", (False, True), ids=("systemd", "openrc"))
@pytest.mark.parametrize(
    "scenario",
    (
        "normal", "disabled", "missing_max", "malformed", "inverted",
        "delayed_ready", "restart_failure", "dbus_never_ready", "service_dies",
        "restore_min_transient", "restore_max_transient", "restore_unreadable",
        "set_range_transient", "set_range_rejected", "restore_mismatch", "inactive",
    ),
)
def test_cyan_verifier_executes_recovery_and_checks_the_actual_range(
    tmp_path, monkeypatch, openrc, scenario
):
    """Run the generated Bash under errexit, not just its string assertions.

    These stand-ins exercise failure paths without writing real GPU registers.
    The full preparation workflow is additionally validated on the BC250 host.
    """
    import json
    import os

    binary = tmp_path / "cyan"
    binary.write_text("GPU frequency fix enabled\n")
    binary.chmod(0o755)
    config = tmp_path / "config.toml"
    config.write_text(
        '[gpu-usage]\nfix-freq = false\nfix-metrics = true\n'
        '[gpu]\nset-method = "smu"\n[dbus]\nenabled = true\n'
    )
    init = tmp_path / "cyan-init"
    init.write_text(f'command="{binary}"\n')
    softlevel = tmp_path / "softlevel"
    if openrc:
        softlevel.touch()
    state = tmp_path / "state.json"
    calls = tmp_path / "calls.jsonl"
    tools = tmp_path / "bin"
    tools.mkdir()
    dispatcher = tools / "dispatch"
    dispatcher.write_text(
        "#!/usr/bin/env python3\n" + r'''
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
state_file = Path(os.environ["CYAN_TEST_STATE"])
calls = Path(os.environ["CYAN_TEST_CALLS"])
scenario = os.environ["CYAN_TEST_SCENARIO"]
s = json.loads(state_file.read_text()) if state_file.exists() else {}
with calls.open("a") as f:
    f.write(json.dumps([name, *args]) + "\n")
def finish(code=0, output=""):
    state_file.write_text(json.dumps(s))
    if output:
        print(output)
    sys.exit(code)
if name == "sudo":
    os.execvp(args[0], args)
if name in ("sleep", "journalctl"):
    finish()
if name in ("systemctl", "rc-service"):
    if args[0] == "show":
        finish(output=os.environ["CYAN_TEST_BINARY"])
    if "restart" in args:
        s["restarted"] = True
        finish(1 if scenario == "restart_failure" else 0)
    if "status" in args or "is-active" in args:
        finish(1 if scenario == "inactive" or
               (scenario == "service_dies" and s.get("restarted")) else 0)
    finish(2)
if name != "busctl":
    finish(2)
assert "--timeout=1s" in args, "every D-Bus call needs its own deadline"
if "call" in args:
    s["set_calls"] = s.get("set_calls", 0) + 1
    assert args[-2:] == ["1000", "1850"], "never invent the previous range"
    if scenario == "set_range_rejected" or (
        scenario == "set_range_transient" and s["set_calls"] < 3
    ):
        finish(1)
    s["restored"] = True
    finish()
prop = args[-1]
if not s.get("restarted"):
    if scenario == "disabled" or (scenario == "missing_max" and prop == "Max"):
        finish(1)
    if scenario == "malformed":
        finish(output="s invalid")
    if scenario == "inverted":
        finish(output="u " + ("1900" if prop == "Min" else "1000"))
    finish(output="u " + ("1000" if prop == "Min" else "1850"))
if scenario == "dbus_never_ready":
    finish(1)
if scenario == "delayed_ready" and not s.get("restored"):
    s["ready_reads"] = s.get("ready_reads", 0) + 1
    if s["ready_reads"] < 4:
        finish(1)
if s.get("restored"):
    if scenario == "restore_unreadable":
        finish(1)
    transient_prop = {"restore_min_transient": "Min", "restore_max_transient": "Max"}.get(scenario)
    if prop == transient_prop and not s.get("transient_consumed"):
        s["transient_consumed"] = True
        finish(1)
    finish(output="u " + ("1000" if prop == "Min" else
                          "1700" if scenario == "restore_mismatch" else "1850"))
finish(output="u " + ("1000" if prop == "Min" else "1700"))
'''
    )
    dispatcher.chmod(0o755)
    for name in ("sudo", "systemctl", "rc-service", "busctl", "journalctl", "sleep"):
        (tools / name).symlink_to(dispatcher)
    monkeypatch.setenv("PATH", f"{tools}:{os.environ['PATH']}")
    monkeypatch.setenv("CYAN_TEST_STATE", str(state))
    monkeypatch.setenv("CYAN_TEST_CALLS", str(calls))
    monkeypatch.setenv("CYAN_TEST_SCENARIO", scenario)
    monkeypatch.setenv("CYAN_TEST_BINARY", str(binary))
    command = cyan_runtime_verification_command()
    for old, new in (
        ("/usr/local/bin/cyan-skillfish-governor-smu", binary),
        ("/etc/cyan-skillfish-governor-smu/config.toml", config),
        ("/etc/init.d/cyan-skillfish-governor-smu", init),
        ("/run/openrc/softlevel", softlevel),
    ):
        command = command.replace(old, str(new))
    result = subprocess.run(
        ["bash", "-Eeuo", "pipefail", "-c", command],
        text=True, capture_output=True, timeout=15,
    )
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    final = json.loads(state.read_text())
    if openrc:
        assert not any(call[0] == "systemctl" for call in recorded)
    failures = {
        "restart_failure": "service restart failed",
        "dbus_never_ready": "D-Bus name is unavailable",
        "service_dies": "D-Bus name is unavailable",
        "restore_unreadable": "previous runtime range could not be restored",
        "set_range_rejected": "previous runtime range could not be restored",
        "restore_mismatch": "previous runtime range could not be restored",
    }
    if scenario in failures:
        assert result.returncode == 61, result.stdout + result.stderr
        assert failures[scenario] in result.stdout
        assert "OK:" not in result.stdout
        if scenario in {"dbus_never_ready", "service_dies"}:
            from bc250cc.shared.error_catalog import for_marker

            assert for_marker(result.stdout).code == "BC250-DBUS-001"
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        if scenario == "inactive":
            assert not final.get("restarted")
            assert not any(call[0] == "busctl" for call in recorded)
        elif scenario in {"disabled", "missing_max", "malformed", "inverted"}:
            assert final["restarted"]
            assert not final.get("set_calls")
            assert "previous runtime range was unknown" in result.stdout
            assert "runtime range was preserved" not in result.stdout
        else:
            assert final["restored"]
            assert "restored Cyan runtime range 1000-1850 MHz" in result.stdout
            if scenario in {"restore_min_transient", "restore_max_transient"}:
                assert final["transient_consumed"]
                assert final["set_calls"] == 2
            elif scenario == "set_range_transient":
                assert final["set_calls"] == 3
    assert final.get("set_calls", 0) <= 25
    assert len([c for c in recorded if c[0] == "busctl"]) < 85


def test_steamos_restores_omitted_kernel_api_headers(tmp_path):
    """R-bb33f44b: linux-api-headers recorded as installed, linux/types.h missing."""
    command = oberon_install_command(
        _os_repository(tmp_path, "steamos"), destination=tmp_path / "oberon",
        checkout_command="CHECKOUT", yaml_cpp_revision="reviewed-yaml",
    )
    assert "#include <linux/types.h>" in command
    assert "sudo pacman -S --noconfirm linux-api-headers" in command
    assert "linux/types.h is still missing" in command


def test_bazzite_builds_in_the_hosts_fedora_release_and_checks_the_binary(tmp_path):
    """R-53376560: built in fedora:latest, the binary needed GLIBCXX_3.4.35."""
    command = oberon_install_command(
        _os_repository(tmp_path, "bazzite"), destination=tmp_path / "oberon",
        checkout_command="CHECKOUT", yaml_cpp_revision="reviewed-yaml",
    )
    assert "fedora:latest" not in command
    assert '"registry.fedoraproject.org/fedora:$bc250_release"' in command
    assert ".bc250-builder" in command
    gate = command.index('grep -q "not found"')
    assert gate < command.index("/usr/local/bin/oberon-governor")
