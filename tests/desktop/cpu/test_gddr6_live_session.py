"""Live monitoring is one bounded authenticated session, not a polling timer.

A timer that re-runs a privileged read costs a Polkit check per sample and
leaves the grant cached between them. The session helper is launched once,
streams one JSON sample per line, and ends itself; the interface follows it.
"""

import json
import sys

from frontends.desktop.core.gddr6_monitor import (
    LIVE_SESSION_SECONDS,
    Gddr6Monitor,
)

READY = {
    "hardware_detected": True,
    "repository_ready": True,
    "reader_ready": True,
    "helper_ready": True,
    "payload_present": True,
    "firmware_supported": True,
}

SAMPLE = {
    "patch_active": True,
    "chips": [
        {"chip": index, "code": 0x31, "temperature_c": 58.0} for index in range(8)
    ],
    "average_c": 58.0,
    "hotspot_c": 58.0,
    "hotspot_chip": 0,
}


class SessionController:
    """Stands in for a helper: prints two samples, then ends the session."""

    def __init__(self, *, samples=2):
        self.samples = samples
        self.reads = 0

    def estado_gddr6_memory_temp(self):
        return dict(READY)

    def leer_temperatura_vram(self, *, chips=True):  # pragma: no cover
        self.reads += 1
        raise AssertionError("a live session must not also poll for reads")

    def comando_monitorizar_vram(self, seconds=LIVE_SESSION_SECONDS):
        script = (
            "import json,sys\n"
            f"for _ in range({self.samples}):\n"
            f"    print(json.dumps({SAMPLE!r}), flush=True)\n"
            "print(json.dumps({'session_ended': True}), flush=True)\n"
        )
        return [sys.executable, "-c", script]


def _monitor(qtbot, controller) -> Gddr6Monitor:
    monitor = Gddr6Monitor(controller)
    monitor._state.status = dict(READY)
    monitor._rebuild()
    return monitor


def test_a_session_streams_samples_and_ends_by_itself(qtbot):
    monitor = _monitor(qtbot, SessionController())
    seen = []
    monitor.changed.connect(lambda reading: seen.append(reading))

    monitor.start_live()
    assert monitor.reading.live
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=8000)

    # The readings arrived from the stream, and nothing polled for them.
    live_readings = [reading for reading in seen if reading.chips]
    assert live_readings
    assert live_readings[-1].chips[0].temperature_c == 58.0
    assert monitor.controller.reads == 0


def test_the_readings_are_cleared_when_the_session_ends(qtbot):
    """They were live measurements; once sampling stops they are a photograph.

    Leaving the last numbers on screen presents a minute that has passed as
    the current temperature, which is worse than showing nothing.
    """
    monitor = _monitor(qtbot, SessionController())

    monitor.start_live()
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=8000)

    assert monitor.reading.chips == ()
    assert monitor.reading.average_c is None
    assert monitor.reading.hotspot_c is None
    assert not monitor.reading.sampled_at
    # The patch itself survives until the board loses power, so that is kept.
    assert monitor.reading.patch_active


def test_the_session_end_marker_is_not_shown_as_a_sample(qtbot):
    monitor = _monitor(qtbot, SessionController(samples=1))

    seen = []
    monitor.changed.connect(lambda reading: seen.append(reading))
    monitor.start_live()
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=8000)

    # The end-of-session line never became a reading of its own.
    sampled = [reading for reading in seen if reading.chips]
    assert len(sampled) == 1
    assert sampled[0].sampled_at


def test_stopping_early_terminates_the_privileged_process(qtbot):
    class Endless(SessionController):
        def comando_monitorizar_vram(self, seconds=LIVE_SESSION_SECONDS):
            return [sys.executable, "-c", "import time; time.sleep(300)"]

    monitor = _monitor(qtbot, Endless())
    monitor.start_live()
    assert monitor.reading.live

    monitor.stop_live()

    assert not monitor.reading.live
    assert monitor._session is None


def test_the_requested_window_is_bounded(qtbot):
    """One prompt buys a fixed amount of sampling, not an open-ended grant."""
    assert 0 < LIVE_SESSION_SECONDS <= 1800


def test_a_backend_without_the_session_command_simply_cannot_go_live(qtbot):
    class Old:
        def estado_gddr6_memory_temp(self):
            return dict(READY)

    monitor = _monitor(qtbot, Old())

    monitor.start_live()

    assert not monitor.reading.live


def test_malformed_output_is_ignored_rather_than_crashing_the_view(qtbot):
    class Noisy(SessionController):
        def comando_monitorizar_vram(self, seconds=LIVE_SESSION_SECONDS):
            script = (
                "import json\n"
                "print('not json at all', flush=True)\n"
                f"print(json.dumps({SAMPLE!r}), flush=True)\n"
            )
            return [sys.executable, "-c", script]

    monitor = _monitor(qtbot, Noisy())
    seen = []
    monitor.changed.connect(lambda reading: seen.append(reading))
    monitor.start_live()
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=8000)

    assert [len(reading.chips) for reading in seen if reading.chips] == [8]


def test_the_helper_contract_is_one_json_object_per_line():
    """What the view parses has to be what the helper prints."""
    line = json.dumps(SAMPLE)

    assert json.loads(line)["chips"][0]["temperature_c"] == 58.0
    assert "\n" not in line
