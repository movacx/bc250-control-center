"""HelixSR releases whose archive this installer does not know are not offered."""

from __future__ import annotations

import json

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.shared.errors import ActionNeeded


def test_a_release_with_a_new_layout_is_not_offered(tmp_path, monkeypatch):
    path = tmp_path / "releases.json"
    archive = {"name": "HelixSR-3.0.0.zip", "size": 139914969, "digest": "sha256:" + "a" * 64,
               "browser_download_url": "https://github.com/lonewolf0622/HelixSR/releases/download/v3.0.0/HelixSR-3.0.0.zip"}
    reviewed = [{"tag_name": tag, "prerelease": False, "draft": False, "assets": []} for tag in helixsr.HELIXSR_REVIEWED]
    path.write_text(json.dumps({"releases": [
        {"tag_name": "v3.0.0", "prerelease": True, "draft": False, "assets": [archive]}, *reviewed]}))
    monkeypatch.setattr(helixsr, "_releases_path", lambda: path)
    tags = [row["tag"] for row in helixsr.helixsr_releases()]
    assert "v3.0.0" not in tags


def test_installing_a_release_with_a_new_layout_says_what_to_pick(monkeypatch):
    monkeypatch.setattr(helixsr, "helixsr_release", lambda: {"tag": "v3.0.0", "prerelease": True, "reviewed": False})
    with pytest.raises(ActionNeeded, match="new package layout"):
        helixsr.build_helixsr_install_command()
