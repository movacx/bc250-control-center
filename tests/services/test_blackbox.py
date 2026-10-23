"""The black box keeps the last seconds of the GPU across a freeze."""

from __future__ import annotations

from bc250cc.infrastructure import blackbox


def _write(directory, text):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "current.log").write_text(text, encoding="utf-8")


def test_a_session_cut_by_a_restart_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(blackbox, "boot_id", lambda: "new-boot")
    _write(tmp_path, "# boot=old-boot start=x\n22:19:04.1 2000Mhz busy=99%\n22:19:04.3 2000Mhz busy=100%\n")
    text = blackbox.last_session(tmp_path)
    assert "CUT OFF BY A RESTART" in text
    assert text.endswith("22:19:04.3 2000Mhz busy=100%")


def test_a_stopped_session_is_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(blackbox, "boot_id", lambda: "new-boot")
    _write(tmp_path, "# boot=old-boot start=x\n22:19:04.1 1000Mhz\n# stopped 2026-10-21T22:20\n")
    text = blackbox.last_session(tmp_path)
    assert "stopped normally" in text and "# stopped" not in text


def test_only_the_last_session_and_its_last_lines_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(blackbox, "boot_id", lambda: "b")
    rows = "".join(f"line {n}\n" for n in range(100))
    _write(tmp_path, f"# boot=a start=1\nold\n# boot=b start=2\n{rows}")
    text = blackbox.last_session(tmp_path, lines=5)
    assert "still recording this boot" in text and "old" not in text
    assert text.splitlines()[-5:] == [f"line {n}" for n in range(95, 100)]


def test_without_a_recording_it_says_how_to_get_one(tmp_path):
    assert "was not running" in blackbox.last_session(tmp_path)


def test_recording_rotates_instead_of_growing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(blackbox, "ROTATE_BYTES", 300)

    class FakeSensors:
        device = "/sys/fake"

        def describe(self):
            return "fake"

        def sample(self):
            return "12:00:00.000 1000Mhz busy=1% t_gpu=50"

    monkeypatch.setattr(blackbox, "Sensors", FakeSensors)
    assert blackbox.record(interval=0, samples=40) == 0
    directory = blackbox.log_directory()
    assert (directory / "previous.log").exists()
    assert (directory / "current.log").stat().st_size < 600
