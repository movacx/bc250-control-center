"""HelixSR: a re-published archive installs on GitHub's digest, and Vulkan is
offered only by a setup that knows it (R-84a7093e)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.infrastructure.helixsr import ActionNeeded


def test_a_reviewed_archive_that_differs_is_checked_against_githubs_digest(monkeypatch):
    release = {"tag": "v3.3.0", "version": "3.3.0", **helixsr.HELIXSR_REVIEWED["v3.3.0"],
               "prerelease": False, "reviewed": True, "default": True}
    monkeypatch.setattr(helixsr, "helixsr_release", lambda tag=None: release)
    command = helixsr.build_helixsr_install_command()
    assert "releases/tags/v3.3.0" in command
    assert 'bc250_republished=1' in command
    assert "The author replaced the file under the same version" not in command
    # The reviewed DLL digest only applies to the reviewed archive.
    assert 'if [ "$bc250_republished" = 1 ]; then' in command


@pytest.mark.parametrize("scenario", [
    "reviewed", "republished", "api-down-sums-ok", "metadata-unavailable", "no-digest", "mismatch",
])
def test_archive_verification_distinguishes_metadata_failure_from_bad_bytes(tmp_path, monkeypatch, scenario):
    """R-7c2872af / R-a0a8ed2f did not record the metadata/byte distinction;
    R-e84bcc54 / R-89650f43: GitHub's API turned the lookup away, so the
    release's own SHA256SUMS.txt answers instead."""
    archive = tmp_path / "HelixSR-3.3.0.zip"
    archive.write_bytes(b"a fixture, never extracted or executed")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    release = {"tag": "v3.3.0", "version": "3.3.0", **helixsr.HELIXSR_REVIEWED["v3.3.0"],
               "prerelease": False, "reviewed": True, "default": True}
    release["sha256"] = actual if scenario == "reviewed" else "0" * 64
    listed = actual if scenario in {"republished", "api-down-sums-ok"} else "1" * 64
    metadata = {"assets": [{"name": archive.name, "digest": "sha256:" + listed}]}
    if scenario == "no-digest":
        metadata["assets"][0]["digest"] = ""
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    (tmp_path / "sums.txt").write_text(f"{listed}  {archive.name}\n" if scenario == "api-down-sums-ok" else "")
    monkeypatch.setattr(helixsr, "helixsr_release", lambda: release)
    command = helixsr.build_helixsr_install_command()
    verification = command[command.index("bc250_republished=0"):command.index('echo "Checking the archive layout')]
    api_down = scenario in {"metadata-unavailable", "api-down-sums-ok"}
    stub = ('bc250_fetch() { case "$2" in '
            '*api.github.com*) ' + ('return 22;; ' if api_down else 'cp "$bc250_work/metadata.json" "$1";; ') +
            '*SHA256SUMS.txt) ' + ('cp "$bc250_work/sums.txt" "$1";; ' if scenario == "api-down-sums-ok" else 'return 22;; ') +
            '*) return 22;; esac; }; ')
    result = subprocess.run(["bash", "-Eeuo", "pipefail", "-c", stub + verification],
                            env=os.environ | {"bc250_archive": str(archive), "bc250_work": str(tmp_path),
                                              "bc250_python": sys.executable},
                            capture_output=True, text=True, timeout=10)
    if scenario in {"reviewed", "republished", "api-down-sums-ok"}:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Archive verified." in result.stdout
        if scenario == "api-down-sums-ok":
            assert "SHA256SUMS.txt" in result.stdout
    else:
        assert result.returncode == 30
        assert "Archive verified." not in result.stdout
        assert actual in result.stdout
        if scenario in {"metadata-unavailable", "no-digest"}:
            assert "did not provide a usable SHA-256" in result.stdout
            assert "does not match" not in result.stdout
        else:
            assert "does not match" in result.stdout and listed in result.stdout


def test_the_reviewed_330_is_the_republished_archive():
    """The author replaced 3.3.0 on 2026-11-12; games given the first DLL stay known."""
    release = helixsr.HELIXSR_REVIEWED["v3.3.0"]
    assert release["sha256"].startswith("7d6c0a4adeb5") and release["size"] == 279_492_763
    assert "2feb14f1db4d29eb9e389c955fb9c7d90a565890ab63c789c77f2d1fc0532a46" in helixsr.HELIXSR_DLL_DIGESTS


def _installed(tmp_path, monkeypatch, setup_text: str):
    (tmp_path / helixsr.HELIXSR_SETUP).write_text(setup_text, encoding="utf-8")
    monkeypatch.setattr(helixsr, "helixsr_directory", lambda: tmp_path)
    monkeypatch.setattr(helixsr, "_layout3", lambda: True)
    monkeypatch.setattr(helixsr, "helixsr_release", lambda tag=None: {"tag": "v3.1.0", "version": "3.1.0"})


def test_an_older_setup_is_not_asked_for_vulkan(tmp_path, monkeypatch):
    _installed(tmp_path, monkeypatch, "usage: --dlss PATH --preset-k --rebuild\n")
    with pytest.raises(ActionNeeded, match="does not build Vulkan kernels"):
        helixsr.build_helixsr_network_command(options=("vulkan", "rebuild"))
    assert not helixsr._setup_offers(tmp_path, "--vulkan")


def test_a_setup_that_knows_vulkan_gets_it(tmp_path, monkeypatch):
    _installed(tmp_path, monkeypatch, "usage: --dlss PATH --vulkan --rebuild\n")
    command = helixsr.build_helixsr_network_command(options=("vulkan", "rebuild"))
    assert "--vulkan" in command
