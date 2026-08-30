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
        reviewed_release="v0.4.12",
    )
    actual = repository._cyan_upstream_runtime_command(os_repository)
    assert actual == expected
    assert "BC250_CYAN_RELEASE_TAG=v0.4.12" in actual


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
