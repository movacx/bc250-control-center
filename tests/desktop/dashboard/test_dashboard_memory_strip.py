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


def test_the_strip_stays_empty_rather_than_pointing_somewhere_gone(qtbot):
    """It used to say "read it from the CPU module"; that card was removed."""
    page = DashboardPage(PassiveController({}))
    qtbot.addWidget(page)

    page._apply_memory_summary()

    assert not page.memory_summary.detail.text()
    assert all(not cell.code.text() for cell in page.memory_summary.cells)


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
