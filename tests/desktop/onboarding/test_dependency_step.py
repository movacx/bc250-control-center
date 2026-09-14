"""Preparing the board from the welcome screen.

The point of doing it here is that it is the first thing anyone needs and the
last thing they would find on their own. The constraints are what make it
awkward: the work runs under sudo, which reads its password from a terminal
and not from a pipe, and the docked console is inside the shell this panel has
switched off. So the panel carries a terminal of its own — the same machinery,
not a copy — and a workflow that outlives the panel is handed over rather than
killed.
"""

import pytest
from PyQt6.QtWidgets import QWidget

from frontends.desktop.onboarding.mini_console import MiniConsole
from frontends.desktop.onboarding.welcome import WelcomeOverlay


@pytest.fixture
def overlay(qtbot):
    window = QWidget()
    window.resize(1300, 900)
    qtbot.addWidget(window)
    panel = WelcomeOverlay(window, system_mode="dark")
    panel.setGeometry(window.rect())
    qtbot.addWidget(panel)
    yield panel
    panel.console.shutdown()


# --------------------------------------------------------------- the step


def test_the_step_sits_before_the_tour(overlay):
    assert overlay.STEP_COUNT == 5
    assert overlay.DEPENDENCY_STEP == 3
    assert overlay.step_rows[overlay.DEPENDENCY_STEP].isChecked() is False


def test_the_step_opens_on_the_choice_not_on_a_black_rectangle(overlay):
    """An empty terminal on a welcome screen reads as a fault, not a terminal."""
    assert overlay.dependency_faces.currentIndex() == 0


def test_pressing_the_button_only_reports_the_intent(overlay):
    """The panel does not know how to install anything; the window does."""
    asked = []
    overlay.prepare_requested.connect(lambda: asked.append(True))

    overlay.prepare_button.click()

    assert asked == [True]


def test_a_running_install_takes_over_the_button(qtbot, overlay):
    before = overlay.prepare_button.text()

    assert overlay.console.run(["/bin/sleep", "300"], title="Preparar")

    assert overlay.dependency_faces.currentIndex() == 1
    assert overlay.prepare_button.isEnabled() is False
    assert overlay.prepare_button.text() != before
    assert overlay.preparing


def test_the_button_comes_back_when_it_finishes(qtbot, overlay):
    with qtbot.waitSignal(overlay.console.workflow_finished, timeout=15000):
        assert overlay.console.run(["/bin/sh", "-c", "exit 0"], title="Preparar")

    assert overlay.prepare_button.isEnabled()
    assert overlay.preparing is False


def test_a_failure_says_so_and_offers_another_go(qtbot, overlay):
    with qtbot.waitSignal(overlay.console.workflow_finished, timeout=15000):
        assert overlay.console.run(["/bin/sh", "-c", "exit 3"], title="Preparar")

    assert overlay.prepare_button.isEnabled()
    assert "3" in overlay.console.state.text()


def test_an_install_that_never_started_is_reported_where_output_would_be(overlay):
    overlay.preparation_failed("no network")

    assert "no network" in overlay.prepare_note.text()
    assert overlay.prepare_button.isEnabled()


# ------------------------------------------------------- the console itself


def test_it_answers_the_contract_a_console_host_asks_for(qtbot):
    """Pointing a host at this is what sends a workflow here instead."""
    from frontends.desktop.console.console_host import ConsoleHost

    console = MiniConsole()
    qtbot.addWidget(console)
    host = ConsoleHost(console)

    from bc250cc.infrastructure.terminal_repository import EmbeddedTerminalRequest

    result = host.launch(EmbeddedTerminalRequest(
        argv=("/bin/sleep", "300"), title="Preparar",
        status_file="", log_file="", launch_file="",
    ))

    assert result is not None
    assert console.busy
    assert isinstance(console.session_pid(), int)
    console.shutdown()


def test_the_output_of_the_workflow_reaches_the_screen(qtbot):
    console = MiniConsole()
    qtbot.addWidget(console)

    with qtbot.waitSignal(console.workflow_finished, timeout=15000):
        assert console.run(["/bin/sh", "-c", "echo listo"], title="Preparar")

    assert "listo" in console.view.screen.full_text()
    console.shutdown()


def test_a_second_workflow_is_declined_rather_than_replacing_the_first(qtbot):
    console = MiniConsole()
    qtbot.addWidget(console)

    assert console.run(["/bin/sleep", "300"], title="primera")
    assert console.run(["/bin/sleep", "300"], title="segunda") is False
    console.shutdown()


# ------------------------------------------------------------- the handover


def test_a_running_install_is_handed_over_rather_than_killed(qtbot):
    """Finishing the setup must not kill a package manager halfway through."""
    from frontends.desktop.console.console_panel import ConsolePanel

    console = MiniConsole()
    qtbot.addWidget(console)
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.resize(900, 300)
    panel.set_auto_hide(False)

    assert console.run(["/bin/sleep", "300"], title="Preparar")
    pid = console.session_pid()

    session = console.release_session()
    assert panel.adopt_session(session, title="Preparar BC250")

    assert console.busy is False, "the terminal it left should be idle"
    assert panel.busy, "the workflow should still be running"
    assert panel.session_pid() == pid, "it should be the same process"
    assert panel.active_tab.title == "Preparar BC250"
    panel.shutdown()
    console.shutdown()


def test_the_adopted_workflow_keeps_printing_into_its_new_home(qtbot):
    from frontends.desktop.console.console_panel import ConsolePanel

    console = MiniConsole()
    qtbot.addWidget(console)
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.resize(900, 300)
    panel.set_auto_hide(False)

    assert console.run(
        ["/bin/sh", "-c", "sleep 0.4; echo despues-del-traspaso"], title="Preparar"
    )
    panel.adopt_session(console.release_session(), title="Preparar BC250")

    qtbot.waitUntil(
        lambda: "despues-del-traspaso" in panel.view.screen.full_text(), timeout=8000
    )
    panel.shutdown()
    console.shutdown()


def test_adopting_nothing_is_not_a_crash(qtbot):
    from frontends.desktop.console.console_panel import ConsolePanel

    panel = ConsolePanel()
    qtbot.addWidget(panel)

    assert panel.adopt_session(None) is False
    panel.shutdown()


def test_what_was_already_printed_travels_with_the_workflow(qtbot):
    """Half an install the user just watched should not vanish on handover."""
    from frontends.desktop.console.console_panel import ConsolePanel

    console = MiniConsole()
    qtbot.addWidget(console)
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.resize(900, 300)
    panel.set_auto_hide(False)

    assert console.run(
        ["/bin/sh", "-c", "echo antes-del-traspaso; sleep 300"], title="Preparar"
    )
    qtbot.waitUntil(
        lambda: "antes-del-traspaso" in console.view.screen.full_text(), timeout=8000
    )

    transcript = console.view.screen.full_text()
    panel.adopt_session(
        console.release_session(), title="Preparar BC250", transcript=transcript
    )

    assert "antes-del-traspaso" in panel.view.screen.full_text()
    panel.shutdown()
    console.shutdown()


# ------------------------------------------------------------- the choosing


def test_all_seven_components_are_offered(overlay):
    """The whole list, not a safe subset chosen on the user's behalf."""
    from frontends.desktop.components.dashboard_widgets import PreparationSidebar

    assert set(overlay.picker.tiles) == {key for key, _l, _d in PreparationSidebar.COMPONENTS}


def test_the_required_one_starts_chosen_and_cannot_be_unchosen(overlay):
    base = overlay.picker.tiles["runtime"]
    assert base.required
    assert base.selected

    base._toggle()

    assert base.selected, "the base runtime is not optional"


def test_choosing_one_puts_it_in_the_selection(overlay):
    tile = overlay.picker.tiles["cpu_oc"]
    assert not tile.selected

    tile._toggle()

    assert "cpu_oc" in overlay.selected_components()


def test_select_all_takes_everything_then_gives_it_back(overlay):
    overlay.picker.select_all.click()
    assert len(overlay.selected_components()) == len(overlay.picker.tiles)

    overlay.picker.select_all.click()
    # The required one stays; it is not the user's to drop.
    assert overlay.selected_components() == {"runtime"}


def test_what_is_already_installed_stops_being_offered(overlay):
    overlay.mark_installed_components({"umr", "cpu_oc"})

    assert overlay.picker.tiles["umr"].installed
    assert overlay.picker.tiles["umr"].actionable is False
    assert "umr" not in overlay.selected_components()
    assert "cpu_oc" not in overlay.selected_components()


def test_an_installed_component_cannot_be_picked_again(overlay):
    overlay.mark_installed_components({"fan_pwm"})
    tile = overlay.picker.tiles["fan_pwm"]

    tile._toggle()

    assert tile.selected is False


def test_the_button_says_how_many_and_refuses_nothing(overlay):
    overlay.mark_installed_components(set())
    for tile in overlay.picker.tiles.values():
        if not tile.required:
            tile.set_selected(False)
    overlay._sync_prepare_button()
    assert overlay.prepare_button.isEnabled()

    overlay.mark_installed_components({"runtime"})
    overlay._sync_prepare_button()

    assert overlay.selected_components() == set()
    assert overlay.prepare_button.isEnabled() is False


def test_the_tiles_do_not_grade_the_components(overlay):
    """No risk badge here.

    The dashboard panel that actually runs these explains what each one does
    to the machine, at the moment it can be acted on. Repeating a one-word
    grade on a first-run screen only labels something the reader has no way
    to judge yet, and colours half the grid as a warning.
    """
    for tile in overlay.picker.tiles.values():
        assert not hasattr(tile, "risk")


def test_the_tiles_arrive_when_the_step_does(qtbot, overlay):
    """Built behind four other steps; the entrance belongs to the arrival."""
    overlay._reach(overlay.DEPENDENCY_STEP)

    tile = next(iter(overlay.picker.tiles.values()))
    assert tile.entrance < 1.0
    qtbot.waitUntil(lambda: tile.entrance == 1.0, timeout=4000)


def test_reaching_the_step_asks_what_is_already_installed(overlay):
    asked = []
    overlay.dependencies_reached.connect(lambda: asked.append(True))

    overlay._reach(overlay.DEPENDENCY_STEP)

    assert asked == [True]


def test_asking_to_install_nothing_does_nothing(overlay):
    """Belt and braces: the button is disabled, but the guard is in the code."""
    overlay.mark_installed_components(set(overlay.picker.tiles))

    assert overlay.selected_components() == set()
