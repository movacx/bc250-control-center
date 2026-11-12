"""A reviewed HelixSR release re-published with another DLL is shown as
installed, not "Repair required" (Discord, 1.22.7 with HelixSR 3.3.0)."""

from __future__ import annotations

from bc250cc.infrastructure import helixsr


def _install(tmp_path, monkeypatch, dll: bytes, recorded: str):
    directory = tmp_path / "3.3.0"
    (directory / "HelixSR").mkdir(parents=True)
    (directory / "HelixSR" / "helixsr.dll").write_bytes(dll)
    (directory / helixsr.HELIXSR_SETUP).write_text("# setup\n")
    release = {"tag": "v3.3.0", "version": "3.3.0", **helixsr.HELIXSR_REVIEWED["v3.3.0"],
               "prerelease": False, "reviewed": True, "default": True}
    (directory / helixsr.HELIXSR_MARKER).write_text(release["sha256"] + "\n")
    (directory / helixsr.HELIXSR_DLL_MARKER).write_text(recorded + "\n")
    monkeypatch.setattr(helixsr, "helixsr_release", lambda tag=None: release)
    monkeypatch.setattr(helixsr, "helixsr_directory", lambda: directory)
    monkeypatch.setattr(helixsr, "helixsr_root", lambda: tmp_path)
    monkeypatch.setattr(helixsr, "_run_bridge", lambda *a, **k: {"network_ready": True})
    monkeypatch.setattr(helixsr, "refresh_helixsr_scan", lambda: None)
    monkeypatch.setattr(helixsr, "helixsr_games", lambda **k: [])
    monkeypatch.setattr(helixsr, "helixsr_scaler_rows", lambda: [])
    monkeypatch.setattr(helixsr, "_bridge_game_rows", lambda status: [])
    return directory


def test_a_republished_dll_recorded_at_install_counts_as_installed(tmp_path, monkeypatch):
    import hashlib
    dll = b"MZ republished HelixSR"
    _install(tmp_path, monkeypatch, dll, hashlib.sha256(dll).hexdigest())
    assert helixsr.helixsr_state()["state"] == "ready"


def test_a_dll_that_matches_nothing_still_needs_repair(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, b"MZ something else", "0" * 64)
    assert helixsr.helixsr_state()["state"] != "ready"
