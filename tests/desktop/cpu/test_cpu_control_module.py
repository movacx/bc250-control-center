"""The unified CPU module: what it offers, and when it refuses to.

One screen holds both the tuning controls and the live readings, so these
cover the runtime half and the profile half of the same view.

The GDDR6 and board-level sensors are deliberately not here. They belong to
the board rather than the processor, and the dashboard strip already drives
them; this page reports what the CPU session is doing.
"""

from frontends.desktop.pages.cpu_control_view import (
    CoreReading,
    CoreUnlockState,
    CpuControlState,
    CpuControlView,
)


def _view(qtbot) -> CpuControlView:
    view = CpuControlView()
    qtbot.addWidget(view)
    return view


def test_hidden_cores_are_shown_as_offline_rather_than_omitted(qtbot):
    """A stock board exposes six of eight slots; the other two must say so."""
    view = _view(qtbot)

    view.apply_state(CpuControlState(
        topology="6 cores / 12 threads",
        cores=tuple(CoreReading(index, 3490, 10, "0, 1", True) for index in range(6)),
    ))

    labels = [cell.frequency.text() for cell in view.core_grid.rows]
    assert len(labels) == 8
    assert labels[0] == "3.49 GHz"
    assert labels[6] == labels[7] != "3.49 GHz"
    # The two the board hides are the whole point of the unlock below them.
    assert not view.core_grid.rows[7].usage.text()
    assert view.core_grid.rows[0].usage.text() == "10 %"


def test_the_unlock_card_and_core_monitor_carry_no_core_count_or_experimental_caption(qtbot):
    """Removed on request: the count sat twice on screen and the caption said
    nothing the red panel does not. Neither may come back."""
    from PyQt6.QtWidgets import QLabel

    view = _view(qtbot)
    view.apply_state(CpuControlState(
        topology="6 cores / 12 threads",
        core_unlock=CoreUnlockState(detected_shape="6 núcleos / 12 hilos"),
    ))
    # Only these two cards: the processor overview still lists the topology.
    for card in (view._risk_panel, view.cores_panel):
        texts = [label.text() for label in card.findChildren(QLabel)]
        assert not any("núcleos / 12 hilos" in text or "cores / 12 threads" in text for text in texts)
        assert not any("restart-required" in text or "requiere reinicio" in text for text in texts)


def test_the_two_unlock_buttons_look_like_the_boot_persistence_ones(qtbot):
    view = _view(qtbot)
    # Same family as Save for boot / Review persistence / Remove from boot:
    # the action in the red tone, the other one neutral, equal width.
    assert view.unlock_button.property("dangerAction") is True
    assert view.firmware_button.property("ghostButton") is True
    assert not view.firmware_button.property("linkButton")


def test_the_runtime_block_mirrors_the_page_instead_of_recomputing_it(qtbot):
    """One source of truth for six readings that decide what can be saved.

    ``_apply_refresh_payload`` already renders boot persistence, the applied
    tuning, the detector reference and the rest onto the legacy runtime card.
    Recomputing them here would give the screen two answers to the same
    question, so the state object reads the widgets the page just filled.
    """
    from frontends.desktop.pages.cpu_control_integration import _control_state

    class FakeStat:
        def __init__(self, value, detail):
            self.value = type("L", (), {"text": staticmethod(lambda v=value: v)})()
            self.detail = type("L", (), {"text": staticmethod(lambda d=detail: d)})()

    class FakeControl:
        def __init__(self, value=0):
            self._value = value

        def value(self):
            return self._value

        def isChecked(self):  # noqa: N802 (mirrors the Qt spelling)
            return False

    page = type("P", (), {
        "core_unlock_button": type("B", (), {"isEnabled": staticmethod(lambda: False)})(),
        "frequency_control": FakeControl(3550),
        "vid_control": FakeControl(1050),
        "temperature_control": FakeControl(90),
        "scale_control": FakeControl(-34),
        "scale_override_check": FakeControl(),
        "current_state": {"service_enabled": True},
        "process": None,
        "persistence_stat": FakeStat("Enabled", "Starts at boot"),
        "last_operation_stat": FakeStat("3850 MHz", "applied"),
        "applied_tuning_stat": FakeStat("3850 MHz", "active scale unconfirmed"),
        "detected_scale_stat": FakeStat("Stale", "no longer matches overclock.conf"),
        "live_scale_stat": FakeStat("Unknown", "no source"),
        "live_telemetry_stat": FakeStat("56 °C | 1397 MHz", "live"),
    })()

    state = _control_state(page, {})

    assert state.tuning.persistence_enabled is True
    assert state.tuning.runtime["persistence"].value == "Enabled"
    assert state.tuning.runtime["applied"].detail == "active scale unconfirmed"
    assert state.tuning.runtime["live"].value == "56 °C | 1397 MHz"


def test_the_runtime_readings_reach_the_cards_the_user_reads(qtbot):
    """The block replaced the six sensor tiles, so it has to render."""
    from frontends.desktop.pages.cpu_control_view import (
        CpuTuningState,
        RuntimeReading,
    )

    view = _view(qtbot)
    view.apply_state(CpuControlState(tuning=CpuTuningState(runtime={
        "persistence": RuntimeReading("Disabled", "Does not start automatically"),
        "live": RuntimeReading("58 °C | 2130 MHz", "live"),
    })))

    assert view.runtime_cards["persistence"].value.text() == "Disabled"
    assert view.runtime_cards["live"].value.text() == "58 °C | 2130 MHz"
    # A reading the backend did not supply says so rather than showing stale text.
    assert view.runtime_cards["applied"].value.text() == "--"


def test_a_turning_ring_replaces_the_pill_while_the_screen_works(qtbot):
    """Applying an overclock, or any other task of the page, shows motion."""
    from frontends.desktop.i18n import tr
    from frontends.desktop.pages.cpu_control_view import CpuTuningState

    view = _view(qtbot)
    view.show()
    pill, badge = view._configuration_status, view._busy_badge

    view.apply_state(CpuControlState(tuning=CpuTuningState(applying=True)))
    assert badge.isVisible() and badge.spinner.running
    assert badge.label.text() == tr("Checking")
    assert not pill.isVisible()

    view.apply_state(CpuControlState(tuning=CpuTuningState(busy=True)))
    assert badge.spinner.running
    assert badge.label.text() == tr("Working")

    view.apply_state(CpuControlState(tuning=CpuTuningState()))
    assert not badge.isVisible() and not badge.spinner.running
    assert pill.isVisible()
    assert pill.text() == tr("Temporary")


def test_the_page_executor_reaches_the_ring():
    """Tasks on the page's executor never went through _set_running."""
    from frontends.desktop.pages import cpu_control_integration as integration

    class Background:
        def __init__(self):
            self.running = False

        def is_running(self):
            return self.running

    class Page:
        _background = Background()

    assert integration._is_busy(Page()) is False
    Page._background.running = True
    assert integration._is_busy(Page()) is True


def test_core_rows_take_their_colours_from_the_theme_not_from_inline_sheets(qtbot):
    """Inline sheets kept the palette they were written with: after a switch to
    the dark theme the rows showed light-theme ink on a dark panel."""
    from frontends.desktop.components.core_monitor import CoreReading

    view = _view(qtbot)
    view.apply_state(CpuControlState(cores=(CoreReading(0, True, 1500, 20, 2),)))
    row = view.core_grid.rows[0]
    for label in (row.name, row.frequency, row.usage):
        assert label.styleSheet() == ""
    assert row.styleSheet() == ""
    assert row.name.property("offline") is False
    # A hidden core is the same labels in their quiet state.
    assert view.core_grid.rows[7].name.property("offline") is True


def test_the_console_opens_at_the_height_the_owner_settled_on(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QPlainTextEdit

    from frontends.desktop.pages.cpu_control_view import CONSOLE_DEFAULT_HEIGHT

    assert CONSOLE_DEFAULT_HEIGHT == 219
    view = CpuControlView(settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(view)
    view.mount_console(QPlainTextEdit("x"))
    assert view.console_height() == 219


def test_the_export_to_decky_button_keeps_its_size_and_font(qtbot):
    """Left column of the CPU screen: asked to stay exactly as it was.

    Measured at c7e91ad, before the unlock card, the console and the runtime
    block were reworked: 148 x 35 px, 12 px bold, about 145 px wide. Pixel-compared then; this
    keeps a later stylesheet change from quietly moving it.
    """
    from PyQt6.QtWidgets import QApplication

    from frontends.desktop.theme import application_stylesheet

    app = QApplication.instance()
    previous = app.styleSheet()
    try:
        for mode in ("light", "dark"):
            app.setStyleSheet(application_stylesheet(mode))
            view = _view(qtbot)
            view.resize(1632, 940)  # a full-size window, laid out
            view.show()
            qtbot.waitExposed(view)
            qtbot.wait(20)
            button = view._export_decky_button
            assert button.height() == 35, mode
            assert 130 <= button.width() <= 160, mode  # compact, never stretched
            assert button.font().pixelSize() == 12, mode
            assert button.font().weight() >= 700, mode
    finally:
        app.setStyleSheet(previous)
