import pytest

from bc250cc.infrastructure import bazzite_async_compute as module


@pytest.mark.parametrize(
    ("kernel", "supported"),
    (
        ("7.2.0-ogc4.1.fc44.x86_64", True),
        ("7.2.0-ogc6.1.fc44.x86_64", True),
        ("7.2.1-ogc1.0.fc44.x86_64", True),
        ("7.2.0-ogc3.9.fc44.x86_64", False),
        ("6.19.14-ogc5.1.fc44.x86_64", False),
        ("7.2.0-200.fc44.x86_64", False),
    ),
)
def test_reviewed_kernel_gate(kernel, supported):
    assert module.bazzite_async_kernel_supported(kernel) is supported


@pytest.mark.parametrize("action", ("install", "uninstall", "status"))
def test_bazzite_release_commands_are_closed_and_shell_valid(action, tmp_path):
    command = module.build_bazzite_async_compute_command(action)
    script = tmp_path / f"{action}.sh"
    script.write_text(command, encoding="utf-8")

    assert "test \"${ID:-}\" = bazzite" in command
    assert "VERSION_ID:-}" in command
    assert "tri3gubki-ops/bc250-async-compute-bazzite" in command or action == "status"
    if action != "status":
        assert module.BAZZITE_ASYNC_COMPUTE_ARCHIVE_SHA256 in command
        assert "sha256sum --check --status" in command
    if action == "install":
        assert "7.2.0-ogc4.1 or newer" in command
        assert 'install.sh\" --yes --per-game' in command
        assert "optional per-game RADV driver" in command
        assert str(module.BAZZITE_ASYNC_COMPUTE_ICD) in command
    if action == "uninstall":
        assert "bc250_found=0" not in command
        assert "uninstall.sh" in command
    assert __import__("subprocess").run(
        ["bash", "-n", str(script)], check=False
    ).returncode == 0


def test_invalid_action_is_rejected():
    with pytest.raises(ValueError):
        module.build_bazzite_async_compute_command("kernel-only")


def test_probe_recognizes_reviewed_install(monkeypatch, tmp_path):
    prefix = tmp_path / "bc250-radv"
    share = tmp_path / "share"
    helper = tmp_path / "bin" / "bc250-async-compute"
    env_file = tmp_path / "environment.d" / "95.conf"
    library = prefix / "lib64/libvulkan_radeon.so"
    icd = prefix / "share/vulkan/icd.d/radeon_icd.x86_64.json"
    for path in (library, helper, share / "VERSION", env_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("0.2.4\n" if path.name == "VERSION" else "x", encoding="utf-8")
    icd.parent.mkdir(parents=True, exist_ok=True)
    icd.write_text(
        '{"file_format_version":"1.0.1","ICD":'
        f'{{"library_path":"{library}","library_arch":"64"}}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "BAZZITE_ASYNC_COMPUTE_PREFIX", prefix)
    monkeypatch.setattr(module, "BAZZITE_ASYNC_COMPUTE_SHARE", share)
    monkeypatch.setattr(module, "BAZZITE_ASYNC_COMPUTE_ENV", env_file)
    monkeypatch.setattr(module, "BAZZITE_ASYNC_COMPUTE_ICD", icd)
    # The helper path is intentionally fixed by upstream, so an isolated probe
    # remains invalid until every owned artifact is present at its real path.
    assert module.probe_bazzite_async_compute()["bazzite_async_installed"] is True
