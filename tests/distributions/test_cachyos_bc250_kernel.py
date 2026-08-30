from bc250cc.infrastructure.cachyos_bc250_kernel import (
    CACHYOS_BC250_ACTIONS,
    CACHYOS_BC250_INCLUDE,
    CACHYOS_BC250_REPOSITORY,
    build_cachyos_bc250_kernel_command,
    masta_bc250_stack_state,
    masta_bc250_stack_supported,
)


def test_masta_stack_state_reports_kernel_and_repository_mesa(monkeypatch, tmp_path):
    import bc250cc.infrastructure.cachyos_bc250_kernel as module

    include = tmp_path / "bc250.conf"
    include.write_text("[bc250-cachyos]\n")
    monkeypatch.setattr(module, "CACHYOS_BC250_INCLUDE", str(include))
    monkeypatch.setattr(module.platform, "release", lambda: "7.1.5-cachyos-bc250")

    class Result:
        returncode = 0

        def __init__(self, stdout):
            self.stdout = stdout

    def run(args, **_kwargs):
        if args[1] == "-Qq":
            return Result(args[2] + "\n")
        return Result(
            "bc250-cachyos mesa 26.2.0 [installed]\n"
            "bc250-cachyos vulkan-radeon 26.2.0 [installed]\n"
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    state = masta_bc250_stack_state(distro_id="cachyos", family="cachyos")

    assert state == {
        "supported": True,
        "repository_configured": True,
        "kernel_installed": True,
        "kernel_active": True,
        "mesa_installed": True,
    }


def test_masta_stack_support_is_exact_not_arch_family_wide():
    assert masta_bc250_stack_supported(distro_id="arch", family="arch")
    assert masta_bc250_stack_supported(distro_id="cachyos", family="cachyos")
    assert masta_bc250_stack_supported(distro_id="cachy", family="cachyos")
    assert not masta_bc250_stack_supported(distro_id="manjaro", family="manjaro")
    assert not masta_bc250_stack_supported(distro_id="endeavouros", family="arch")
    assert not masta_bc250_stack_supported(distro_id="artix", family="arch")
    assert not masta_bc250_stack_supported(distro_id="fedora", family="fedora")


def test_cachyos_kernel_workflow_has_a_fixed_reviewable_target():
    command = build_cachyos_bc250_kernel_command()

    assert CACHYOS_BC250_REPOSITORY in command
    assert CACHYOS_BC250_INCLUDE in command
    assert "bc250-cachyos/linux-cachyos-bc250 bc250-cachyos/linux-cachyos-bc250-headers" in command
    assert "Optional TrustAll" in command
    assert "arch) bc250_anchor='core'" in command
    assert "cachyos|cachy) bc250_anchor='cachyos-v3'" in command
    assert "BC250_REBOOT_REQUIRED=1" in command
    assert "rm -f -- \"$bc250_repo_file\"" in command
    assert "$HOME" not in command


def test_cachyos_mesa_and_full_workflows_keep_their_scopes_explicit():
    mesa = build_cachyos_bc250_kernel_command("mesa")
    full = build_cachyos_bc250_kernel_command("full")

    assert CACHYOS_BC250_ACTIONS == {"kernel", "mesa", "full"}
    assert "Installing stable BC-250 patched Mesa" in mesa
    assert "bc250-cachyos/mesa bc250-cachyos/vulkan-radeon" in mesa
    assert 'sudo pacman -Syu "${bc250_scope_guard[@]}" "${bc250_packages[@]}"' in mesa
    assert "--needed" not in mesa
    assert "linux-cachyos-bc250 linux-cachyos-bc250-headers" not in mesa
    assert "bc250-cachyos/lib32-mesa bc250-cachyos/lib32-vulkan-radeon" in mesa
    assert "multilib is unavailable" in mesa
    assert "BC250_REBOOT_REQUIRED=1" not in mesa
    assert "bc250-cachyos/linux-cachyos-bc250-headers" in full
    assert "Installing stable BC-250 patched Mesa" in full
    assert full.count("sudo pacman -Syu") == 1
    assert "--ignore 'mesa*,lib32-mesa*,vulkan-*" in build_cachyos_bc250_kernel_command("kernel")
    assert "--ignore 'linux-cachyos-bc250*" in mesa
    assert "bc250_scope_guard=()" in full
    assert '"${bc250_scope_guard[@]}"' in full


def test_cachyos_configuration_is_checked_and_backed_up_before_replacement():
    command = build_cachyos_bc250_kernel_command("full")
    assert command.index("[$bc250_anchor] was not found") < command.index("sudo install -D")
    assert command.index('sudo cp -a /etc/pacman.conf') < command.index('sudo install -m 0644')
    assert "already configured outside Control Center" in command
    assert "full system upgrade" in command


def test_cachyos_workflows_are_valid_shell_and_unsupported_host_stops_before_privilege(tmp_path):
    import subprocess

    release = tmp_path / "os-release"
    release.write_text("ID=ubuntu\n")
    for action in CACHYOS_BC250_ACTIONS:
        command = build_cachyos_bc250_kernel_command(action)
        assert subprocess.run(["bash", "-n", "-c", command], capture_output=True).returncode == 0
        command = command.replace("/etc/os-release", str(release))
        # Fail loudly if the platform gate ever permits a privileged call.
        command = "sudo() { echo UNEXPECTED_PRIVILEGE; return 99; }\n" + command
        result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
        assert result.returncode == 64
        assert "UNEXPECTED_PRIVILEGE" not in result.stdout


def test_exact_arch_and_cachyos_layouts_reach_privilege_only_after_repo_validation(tmp_path):
    """Simulate both documented layouts without touching pacman or /etc."""
    import subprocess

    for distro_id, anchor in (("arch", "core"), ("cachyos", "cachyos-v3")):
        release = tmp_path / f"{distro_id}-os-release"
        pacman_conf = tmp_path / f"{distro_id}-pacman.conf"
        include = tmp_path / f"{distro_id}-bc250.conf"
        release.write_text(f"ID={distro_id}\n")
        pacman_conf.write_text(f"[options]\nColor\n[{anchor}]\nInclude = /tmp/mirrorlist\n")
        command = build_cachyos_bc250_kernel_command("kernel")
        command = command.replace("/etc/os-release", str(release))
        command = command.replace("/etc/pacman.conf", str(pacman_conf))
        command = command.replace(CACHYOS_BC250_INCLUDE, str(include))
        command = '''
pacman() { return 1; }
pacman-conf() { test "$1" = --repo-list && printf '%s\\n' core extra; }
sudo() { echo PRIVILEGE_BOUNDARY; return 99; }
''' + command
        result = subprocess.run(
            ["bash", "-c", command], capture_output=True, text=True
        )
        assert result.returncode == 99, result.stderr
        assert result.stdout.count("PRIVILEGE_BOUNDARY") == 1
        assert not include.exists()


def test_cachyos_workflow_rejects_unknown_actions():
    import pytest

    with pytest.raises(ValueError, match="Unsupported"):
        build_cachyos_bc250_kernel_command("everything")
