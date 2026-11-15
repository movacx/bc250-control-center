"""R-e6cfdf24 and R-1d120481: a user's own layered package blocks the update; say which."""

import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.self_update import _rpm_ostree_install

DEPSOLVE = ("error: Could not depsolve transaction; 1 problem detected:\n Problem: conflicting requests\n"
            "  - package logitech-trueforce-0.42.6-1.fc45.noarch from @System requires "
            "(dkms-logitech-trueforce = 0.42.6 if dkms), but none of the providers can be installed")
UNSIGNED = ("error: importing RPMs: package cyan-skillfish-governor-smu-v0.4.15-1.fc44.x86_64 cannot be "
            "verified and repo copr:copr.fedorainfracloud.org:filippor:bazzite is GPG enabled: /var/x.rpm "
            "could not be verified.")


def _run(tmp_path: Path, message: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "rpm-ostree").write_text(
        '#!/bin/bash\nif [ "$1" = status ]; then echo \'{"deployments": [{}]}\'; exit 0; fi\n'
        f"cat <<'EOT'\n{message}\nEOT\nexit 1\n")
    (bin_dir / "sleep").write_text("#!/bin/bash\n")
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    return subprocess.run(["/usr/bin/bash", "-c", _rpm_ostree_install("/tmp/a.rpm")], capture_output=True,
                          text=True, timeout=30, check=False, env={"PATH": f"{bin_dir}:/usr/bin:/bin"})


def test_a_layered_package_that_cannot_resolve_is_named(tmp_path):
    result = _run(tmp_path, DEPSOLVE)
    assert result.returncode != 0
    assert "rpm-ostree uninstall logitech-trueforce-0.42.6-1.fc45.noarch" in result.stdout
    assert "Control Center did not install it" in result.stdout


def test_an_unverifiable_repository_package_is_named(tmp_path):
    result = _run(tmp_path, UNSIGNED)
    assert result.returncode != 0
    assert "cyan-skillfish-governor-smu-v0.4.15-1.fc44.x86_64" in result.stdout
    assert "copr:copr.fedorainfracloud.org:filippor:bazzite" in result.stdout


@pytest.mark.parametrize("message", ["error: something else"])
def test_other_failures_get_no_third_party_hint(tmp_path, message):
    result = _run(tmp_path, message)
    assert "Control Center did not install it" not in result.stdout
