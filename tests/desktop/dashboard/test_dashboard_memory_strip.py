"""The dashboard's GDDR6 strip mirrors a reading; it never takes one."""

from frontends.desktop.components.dashboard_widgets import (
    GDDR6_CHIP_COUNT,
    DashboardMemorySummary,
)
from frontends.desktop.pages.dashboard import DashboardPage

READY_STATUS = {
    "hardware_detected": True,
    "repository_ready": True,
    "reader_ready": True,
    "helper_ready": True,
    "payload_present": True,
    "firmware_supported": True,
}

SAMPLE = {
    "available": True,
    "patch_active": True,
    "chips": [
        {"chip": index, "code": code, "temperature_c": (code * 2) - 40}
        for index, code in enumerate((0x33, 0x34, 0x35, 0x32, 0x32, 0x35, 0x34, 0x36))
    ],
    "average_c": 63.75,
    "hotspot_c": 68.0,
    "hotspot_chip": 7,
}


class PassiveController:
    """Answers the cached question and fails loudly on the privileged one."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.reads = 0
        self.patch_commands = 0

    def ultima_temperatura_vram(self):
        return dict(self.snapshot)

    def leer_temperatura_vram(self, *, chips=True):  # pragma: no cover - must not run
        self.reads += 1
        raise AssertionError("the dashboard must not trigger a privileged read")

    def comando_aplicar_parche_vram(self):  # pragma: no cover - must not run
        self.patch_commands += 1
        raise AssertionError("live monitoring must not ask for a separate patch")


def test_the_strip_shows_the_monitor_reading_without_asking_for_one(qtbot):
    controller = PassiveController(SAMPLE)
    page = DashboardPage(controller)
    qtbot.addWidget(page)
    page.memory_monitor._state.status = dict(READY_STATUS)
    page.memory_monitor._state.sample = dict(SAMPLE)
    page.memory_monitor._rebuild()

    page._apply_memory_summary()

    cells = page.memory_summary.cells
    assert len(cells) == GDDR6_CHIP_COUNT
    assert cells[0].temperature.text() == "62.0 °C"
    assert cells[7].temperature.text() == "68.0 °C"
    # Flat like the CPU core strip: no cell paints itself differently.
    assert not any(cell.styleSheet() for cell in cells)
    assert not any(cell.temperature.styleSheet() for cell in cells)
    assert controller.reads == 0


def test_the_strip_says_why_it_has_nothing_to_show(qtbot):
    """It used to say "read it from the CPU module"; that card was removed.

    Saying nothing at all was the next mistake: a greyed-out button with an
    empty line beside it reads as a broken feature, which is exactly how it
    was reported. It now states the one blocker that is worth stating.
    """
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)

    page._apply_memory_summary()

    assert page.memory_summary.blocker.text()
    assert "CPU" not in page.memory_summary.blocker.text()
    assert all(not cell.code.text() for cell in page.memory_summary.cells)


def test_the_missing_checkout_is_offered_rather_than_only_reported(qtbot):
    """The one blocker the user can clear from this row swaps the button.

    Cloning the reviewed upstream tool is an ordinary download, and until now
    the only interface that offered it was a page that no longer ships — so
    the live button sat permanently disabled with no way to change that.
    """
    controller = PassiveController({})
    page = DashboardPage(controller)
    qtbot.addWidget(page)
    summary = page.memory_summary

    page._apply_memory_reading(
        page.memory_monitor.reading.__class__(
            hardware_detected=True, reader_ready=True, helper_ready=True
        )
    )
    # isHidden() rather than isVisible(): the page is never shown here, so
    # every descendant answers "not visible" regardless of its own flag.
    assert not summary.prepare_button.isHidden()
    assert summary.live_button.isHidden()

    page._apply_memory_reading(
        page.memory_monitor.reading.__class__(
            hardware_detected=True,
            reader_ready=True,
            helper_ready=True,
            repository_ready=True,
        )
    )
    assert summary.prepare_button.isHidden()
    assert not summary.live_button.isHidden()


def test_a_controller_without_the_gddr6_backend_does_not_break_the_dashboard(qtbot):
    """An older backend simply has no reading to mirror."""
    page = DashboardPage(object())
    qtbot.addWidget(page)

    page._apply_memory_summary()

    assert page.memory_summary.cells


def test_the_strip_updates_cells_instead_of_rebuilding_them(qtbot):
    summary = DashboardMemorySummary()
    qtbot.addWidget(summary)
    chips = [(index, 0x33, 62.0) for index in range(GDDR6_CHIP_COUNT)]
    summary.set_chips(chips)
    identities = [id(cell) for cell in summary.cells]

    for _ in range(3):
        summary.set_chips(chips)

    assert [id(cell) for cell in summary.cells] == identities


def test_the_live_button_asks_for_one_authenticated_session(qtbot):
    """One prompt for the whole window, not one per sample.

    A power cycle clears the volatile SMU patch, so "not patched yet" is the
    normal state every morning. The session helper applies it on the way in,
    which is what makes this a single action and a single authentication.
    """
    controller = PassiveController({})
    page = DashboardPage(controller)
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS)
    monitor._rebuild()
    assert monitor.reading.can_monitor and not monitor.reading.patch_active

    launched = []
    monitor.start_live = lambda: launched.append("session")

    page.memory_summary.live_button.setChecked(True)

    assert launched == ["session"]
    # Never a separate patch prompt: the session covers it.
    assert controller.patch_commands == 0


def test_the_live_button_is_refused_when_no_patch_could_ever_apply(qtbot):
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS, firmware_supported=False)
    monitor._rebuild()

    assert not page.memory_summary.live_button.isEnabled()


def test_a_finished_session_switches_the_button_back_off(qtbot):
    """The helper ends the window itself; the interface must follow it."""
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS)
    monitor._live = True
    monitor._rebuild()
    page.memory_summary.set_live(True)
    assert page.memory_summary.live_button.isChecked()

    monitor._session_finished(0, None)

    assert not monitor.reading.live
    assert not page.memory_summary.live_button.isChecked()


# ------------------------------------------------ BC250-Telemetry's collector
#
# BC250-Telemetry can run its own GDDR6 collector on the same SMU mailbox.
# Two samplers on it hung the SMU on a Bazzite board, so while that collector
# runs the dashboard shows what it publishes and never starts a session.

EXTERNAL_ACTIVE = {
    "state": "active",
    "status": "ok",
    "chips": [
        {"chip": index, "raw": code, "code": code, "temperature_c": float(code * 2 - 40)}
        for index, code in enumerate((38, 37, 42, 38, 38, 41, 41, 39))
    ],
    "average_c": 38.5,
    "hotspot_c": 44.0,
    "hotspot_chip": 2,
}


class SessionRecorder(PassiveController):
    def __init__(self):
        super().__init__({})
        self.session_commands = 0

    def comando_monitorizar_vram(self, seconds=600):  # pragma: no cover - must not run
        self.session_commands += 1
        raise AssertionError("no session may start while the collector owns the SMU")


def _external_page(qtbot, external, controller=None):
    page = DashboardPage(controller or SessionRecorder())
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS, external=dict(external))
    monitor._rebuild()
    return page


def test_the_collectors_readings_are_shown_without_a_session_or_a_prompt(qtbot):
    page = _external_page(qtbot, EXTERNAL_ACTIVE)
    reading = page.memory_monitor.reading
    summary = page.memory_summary

    assert reading.source == "bc250-telemetry"
    assert [cell.temperature.text() for cell in summary.cells][:3] == [
        "36.0 °C",
        "34.0 °C",
        "44.0 °C",
    ]
    assert "BC250-Telemetry" in summary.detail.text()
    # Nothing to start: the readings arrive by themselves.
    assert summary.live_button.isHidden()
    assert summary.prepare_button.isHidden()
    assert not reading.can_monitor
    assert not summary.blocker.text()
    assert page.memory_monitor._backend("comando_monitorizar_vram") is not None


def test_no_session_starts_while_the_collector_owns_the_smu(qtbot):
    controller = SessionRecorder()
    page = _external_page(qtbot, EXTERNAL_ACTIVE, controller)

    page.memory_monitor.start_live()

    assert controller.session_commands == 0
    assert not page.memory_monitor.reading.live


def test_a_collector_without_a_reading_yet_says_so_and_offers_nothing(qtbot):
    page = _external_page(qtbot, {"state": "waiting", "status": "starting", "chips": []})
    summary = page.memory_summary

    assert "BC250-Telemetry" in summary.blocker.text()
    assert summary.live_button.isHidden()
    assert not page.memory_monitor.reading.can_monitor


def test_a_stale_collector_keeps_control_center_off_the_smu(qtbot):
    """Stale can mean it is stuck inside an SMU operation right now."""
    page = _external_page(qtbot, {"state": "stale", "status": "stale", "chips": []})

    assert not page.memory_monitor.reading.can_monitor
    assert "SMU" in page.memory_summary.blocker.text()


def test_a_session_that_found_an_interrupted_collector_says_to_power_off(qtbot):
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS)
    monitor._state.sample = {
        "patch_active": True,
        "error": "ERROR: GDDR6_EXTERNAL_INTERRUPTED: BC250-Telemetry's memory collector stopped",
    }
    monitor._rebuild()

    # Still offered (the next attempt may be after a power cycle), but the
    # reason the last one ended is on screen instead of a silent reset.
    assert monitor.reading.can_monitor
    assert "Power the board off" in page.memory_summary.blocker.text()


def test_a_busy_smu_is_explained_when_a_session_ends_on_it(qtbot):
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS)
    monitor._state.sample = {"patch_active": False, "error": "ERROR: SMU_BUSY: another BC-250 tool"}
    monitor._rebuild()

    assert "Another BC-250 tool" in page.memory_summary.blocker.text()


def test_the_buttons_come_back_when_the_collector_stops(qtbot):
    page = _external_page(qtbot, EXTERNAL_ACTIVE)
    monitor = page.memory_monitor

    monitor._state.status = dict(READY_STATUS, external={"state": "", "chips": []})
    monitor._rebuild()

    assert not page.memory_summary.live_button.isHidden()
    assert monitor.reading.can_monitor
    assert monitor.reading.source == ""


# ------------------------------------------------------------ the governor


def test_a_restarting_governor_pauses_the_readings_and_names_the_likely_cause(qtbot):
    page = DashboardPage(SessionRecorder())
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS, governor_state="restarting")
    monitor._rebuild()

    assert not monitor.reading.can_monitor
    assert not page.memory_summary.live_button.isEnabled()
    assert "Fix metrics" in page.memory_summary.blocker.text()
    monitor.start_live()
    assert not monitor.reading.live


def test_a_deferred_sample_in_a_session_says_the_governor_is_starting(qtbot):
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS)
    monitor._live = True
    monitor._state.sample = {
        "deferred": True,
        "patch_active": False,
        "blocked_reason": "GDDR6_GOVERNOR_UNSETTLED",
        "governor_state": "starting",
        "chips": [],
    }
    monitor._rebuild()

    assert "GPU governor is starting" in page.memory_summary.blocker.text()


def test_an_interrupted_collector_blocks_readings_until_a_power_cycle(qtbot):
    page = _external_page(qtbot, {"state": "interrupted", "status": "stale", "chips": []})

    assert not page.memory_monitor.reading.can_monitor
    assert page.memory_summary.live_button.isHidden()
    assert "Power the board off completely" in page.memory_summary.blocker.text()



# ------------------------------------------------- the manual override (Settings)


class OverrideRecorder(PassiveController):
    def __init__(self):
        super().__init__({})
        self.requests = []

    def comando_monitorizar_vram(self, seconds=600, *, ignore_governor=False):
        self.requests.append(ignore_governor)
        return ["/bin/sh", "-c", "exit 0"]


def test_the_manual_override_lifts_only_the_smu_channel_check(qtbot):
    controller = OverrideRecorder()
    page = DashboardPage(controller)
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(READY_STATUS, governor_state="restarting")
    monitor._rebuild()
    assert not monitor.reading.can_monitor

    monitor.set_manual_override(True)
    assert monitor.reading.can_monitor
    assert page.memory_summary.live_button.isEnabled()
    assert "Manual mode" in page.memory_summary.blocker.text()

    monitor.start_live()
    assert controller.requests == [True]
    qtbot.waitUntil(lambda: not monitor.reading.live, timeout=5000)


def test_the_manual_override_never_lifts_the_hard_guards(qtbot):
    page = DashboardPage(OverrideRecorder())
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor.set_manual_override(True)
    monitor._state.status = dict(READY_STATUS, firmware_supported=False, governor_state="starting")
    monitor._rebuild()
    assert not monitor.reading.can_monitor
    monitor._state.status = dict(
        READY_STATUS, external={"state": "interrupted", "status": "stale", "chips": []}
    )
    monitor._rebuild()
    assert not monitor.reading.can_monitor
    assert page.memory_summary.live_button.isHidden()


def test_an_idle_collector_keeps_the_button_on_the_row_under_the_override(qtbot):
    page = _external_page(qtbot, {"state": "waiting", "status": "waiting", "chips": []}, OverrideRecorder())
    monitor = page.memory_monitor
    assert page.memory_summary.live_button.isHidden()
    monitor.set_manual_override(True)
    assert monitor.reading.can_monitor
    assert not page.memory_summary.live_button.isHidden()
