import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/qa/qa-clean-install-containers.sh"


def test_clean_install_runner_is_valid_and_lists_declared_base_families():
    syntax = subprocess.run(["bash", "-n", str(RUNNER)], check=False)
    listed = subprocess.run(
        ["bash", str(RUNNER), "--list"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert syntax.returncode == 0
    assert listed.returncode == 0
    assert [line.split("\t", 1)[0] for line in listed.stdout.splitlines()] == [
        "arch", "debian", "ubuntu", "fedora"
    ]


def test_clean_install_runner_requires_explicit_network_authority():
    completed = subprocess.run(
        ["bash", str(RUNNER), "--image", "arch"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 77
    assert "explicit --allow-network" in completed.stderr


def test_clean_install_runner_never_implicitly_pulls_or_mounts_host_writable():
    source = RUNNER.read_text(encoding="utf-8")

    assert "podman pull" in source
    assert 'if [[ "$allow_pull" -ne 1 ]]' in source
    assert "--pull=never" in source
    assert '$ROOT_DIR:/src:ro' in source
    assert "BC250_SKIP_PRIVILEGED_HELPER=1" in source
    assert "bc250-control-center-cli --version" in source
    assert "qualification template --section compute_units" in source
    assert 'data[\"qualification_evidence_can_self_certify\"] is False' in source
    assert "/opt/bc250/share/bc250-control-center/VERSION" in source
    assert "uninstall-local.sh --yes --keep-privileged" in source
    assert "--keep-privileged" in source
    assert 'command -v pasta' in source
    assert 'command -v slirp4netns' in source
    assert '--network="$network_backend"' in source
