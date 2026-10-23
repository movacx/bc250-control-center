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


class FailingSessionController(SessionController):
    """A helper that refuses before sampling, with no friendlier wording."""

    def comando_monitorizar_vram(self, seconds=LIVE_SESSION_SECONDS):
        script = (
            "import sys\n"
            "print('ERROR: bc250_smu package files must belong to the desktop user "
            "and not be writable by group or others.', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        return [sys.executable, "-c", script]


def test_an_unrecognised_helper_failure_is_shown_not_swallowed(qtbot):
    monitor = _monitor(qtbot, FailingSessionController())

    monitor.start_live()
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=8000)

    assert monitor.reading.notice() == (
        "bc250_smu package files must belong to the desktop user "
        "and not be writable by group or others."
    )


PARTIAL = {
    "patch_active": True,
    "chips": [
        {"chip": index, "code": 0x31, "temperature_c": 58.0}
        for index in range(8)
        if index not in (2, 5)
    ],
    "chip_errors": [
        {"chip": 2, "raw": 0xFF, "error": "stage1_timeout"},
        {"chip": 5, "raw": 0xFE, "error": "stage2_timeout"},
    ],
    "average_c": 58.0,
    "hotspot_c": 58.0,
    "hotspot_chip": 0,
}


def test_chips_that_did_not_answer_are_named_under_the_others(qtbot):
    monitor = _monitor(qtbot, SessionController())
    monitor._state.sample = dict(PARTIAL)
    monitor._rebuild()
    reading = monitor.reading

    assert [chip.index for chip in reading.chips] == [0, 1, 3, 4, 6, 7]
    assert reading.unanswered_chips == (2, 5)
    assert reading.notice() == "Chips 2, 5 did not answer this time. The other chips are shown."

    monitor._state.sample = dict(PARTIAL, chip_errors=PARTIAL["chip_errors"][:1])
    monitor._rebuild()
    assert monitor.reading.notice() == "Chip 2 did not answer this time. The other chips are shown."

    monitor._state.sample = dict(SAMPLE)
    monitor._rebuild()
    assert monitor.reading.notice() == ""


class SilentChipsController(SessionController):
    """A session that ends because no chip answered (see the helper)."""

    def comando_monitorizar_vram(self, seconds=LIVE_SESSION_SECONDS):
        script = (
            "import sys\n"
            "print('ERROR: GDDR6_NO_CHIP_ANSWERED: no memory chip answered, so live '"
            "'monitoring stopped.', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        return [sys.executable, "-c", script]


def test_a_session_that_found_no_chip_says_so(qtbot):
    monitor = _monitor(qtbot, SilentChipsController())

    monitor.start_live()
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=8000)

    assert monitor.reading.notice() == (
        "No memory chip answered, so live monitoring stopped. Try again later; if "
        "it keeps happening, power the board off completely."
    )


def test_an_unrecognised_patch_is_explained(qtbot):
    monitor = _monitor(qtbot, SessionController())
    monitor._state.sample = {"patch_active": False, "blocked_reason": "GDDR6_PATCH_UNKNOWN"}
    monitor._rebuild()

    assert "Power the board off completely" in monitor.reading.notice()


def test_an_outdated_checkout_points_at_the_prepare_button(qtbot):
    monitor = _monitor(qtbot, SessionController())
    monitor._state.status = dict(READY, repository_ready=False, repository_outdated=True)
    monitor._rebuild()

    assert monitor.reading.blocker() == (
        "This version uses a newer reviewed release of the memory-temperature tool. "
        "Press Prepare readings to update the checkout."
    )

    monitor._state.status = dict(READY, repository_ready=False)
    monitor._rebuild()
    assert monitor.reading.blocker() == "The reviewed upstream checkout is not prepared yet."
