"""HelixSR: a re-published archive installs on GitHub's digest, and Vulkan is
offered only by a setup that knows it (R-84a7093e)."""

from __future__ import annotations

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
