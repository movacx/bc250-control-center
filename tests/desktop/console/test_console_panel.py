"""The panel's job: appear when needed, say what happened, get out of the way.

The rules encoded here are deliberate. A workflow that succeeded withdraws on
its own; a workflow that failed does not, because its output is the only thing
that explains the failure. And a panel already busy must decline rather than
queue, so the caller can still open a terminal window for the second workflow.
"""

from __future__ import annotations

import pytest

from frontends.desktop.console.console_panel import (
    AUTO_HIDE_DELAY_MS,
    MINIMUM_HEIGHT,
    ConsolePanel,
)


@pytest.fixture
def panel(qtbot):
    """The panel inside a window, because its ceiling is half of one.

    A bare panel is its own window, so "half the window" would be half of the
    panel — the height clamp needs a real container to measure against, and
    that is how the application builds it.
    """
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    host = QWidget()
    host.resize(1100, 900)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    page = QWidget(host)
    page.setMinimumHeight(0)
    layout.addWidget(page, 1)
    widget = ConsolePanel(host)
    layout.addWidget(widget)
    qtbot.addWidget(host)
    host.show()
    yield widget
    widget.shutdown()


def run_and_wait(qtbot, panel, script, *, title="Prueba", timeout=15000):
    with qtbot.waitSignal(panel.workflow_finished, timeout=timeout) as blocker:
        assert panel.run(["/bin/sh", "-c", script], title=title)
    return blocker.args[0]


# ------------------------------------------------------------------ appearing


def test_the_panel_starts_out_of_the_way(panel):
    assert panel.isVisible() is False
    assert panel.busy is False
    assert panel.maximumHeight() == 0


def test_running_a_workflow_reveals_the_panel_and_names_it(qtbot, panel):
    panel.set_auto_hide(False)
    assert panel.run(["/bin/sleep", "5"], title="Instalar Cyan")
    assert panel.isVisible()
    assert panel.title_label.text() == "Instalar Cyan"
    assert panel.busy
    panel.shutdown()


def test_the_panel_slides_rather_than_appearing_at_full_height(qtbot, panel):
    panel.set_auto_hide(False)
    panel.run(["/bin/sleep", "5"])
    assert panel.maximumHeight() < panel.panel_height()
    qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=3000)
    panel.shutdown()


def test_a_workflow_without_a_title_still_has_a_name(qtbot, panel):
    panel.set_auto_hide(False)
    panel.run(["/bin/sleep", "5"])
    assert panel.title_label.text().strip()
    panel.shutdown()


# -------------------------------------------------------------------- output


def test_the_output_of_the_workflow_reaches_the_screen(qtbot, panel):
    panel.set_auto_hide(False)
    run_and_wait(qtbot, panel, "echo governor-ready")
    assert "governor-ready" in panel.view.screen.full_text()


def test_a_progress_redraw_does_not_pile_up_lines(qtbot, panel):
    panel.set_auto_hide(False)
    run_and_wait(qtbot, panel, "printf 'sync  10%%\\rsync 100%%\\n'")
    text = panel.view.screen.full_text()
    assert "sync 100%" in text
    assert "sync  10%" not in text


def test_each_workflow_starts_from_a_clean_screen(qtbot, panel):
    panel.set_auto_hide(False)
    run_and_wait(qtbot, panel, "echo primero")
    run_and_wait(qtbot, panel, "echo segundo")
    text = panel.view.screen.full_text()
    assert "segundo" in text
    assert "primero" not in text


# ------------------------------------------------------------------ finishing


def test_a_successful_workflow_reports_completion(qtbot, panel):
    panel.set_auto_hide(False)
    assert run_and_wait(qtbot, panel, "exit 0") == 0
    assert "·" in panel.state_label.text()
    assert panel.state_label.property("tone") == "ok"


def test_a_successful_workflow_withdraws_on_its_own(qtbot, panel):
    panel.set_auto_hide(True)
    run_and_wait(qtbot, panel, "exit 0")
    qtbot.waitUntil(lambda: panel.maximumHeight() == 0, timeout=AUTO_HIDE_DELAY_MS + 4000)


def test_a_failed_workflow_stays_open_with_its_exit_code(qtbot, panel):
    panel.set_auto_hide(True)
    assert run_and_wait(qtbot, panel, "echo se rompio; exit 23") == 23
    assert "23" in panel.state_label.text()
    assert panel.state_label.property("tone") == "failed"
    # Give the auto-hide the time it would have had on success.
    qtbot.wait(AUTO_HIDE_DELAY_MS + 400)
    assert panel.isVisible()
    assert "se rompio" in panel.view.screen.full_text()


def test_turning_auto_hide_off_keeps_a_successful_workflow_on_screen(qtbot, panel):
    panel.set_auto_hide(False)
    run_and_wait(qtbot, panel, "exit 0")
    qtbot.wait(AUTO_HIDE_DELAY_MS + 400)
    assert panel.isVisible()


def test_the_stop_button_is_only_live_while_something_runs(qtbot, panel):
    panel.set_auto_hide(False)
    run_and_wait(qtbot, panel, "exit 0")
    assert panel.stop_button.isEnabled() is False


def test_stopping_a_workflow_ends_it(qtbot, panel):
    panel.set_auto_hide(False)
    assert panel.run(["/bin/sleep", "300"])
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        panel.stop_button.click()
    assert panel.busy is False


def test_a_command_that_cannot_start_is_reported_not_swallowed(qtbot, panel):
    panel.set_auto_hide(False)
    assert run_and_wait(qtbot, panel, "exit 0") == 0
    panel._on_failed("A pseudo-terminal could not be opened: too many open files")
    assert "too many open files" in panel.view.screen.full_text()
    assert panel.state_label.property("tone") == "failed"


# ----------------------------------------------------------------- one at a time


def test_a_busy_panel_declines_so_the_caller_can_open_a_window(qtbot, panel):
    panel.set_auto_hide(False)
    assert panel.run(["/bin/sleep", "300"], title="primera")
    assert panel.run(["/bin/sleep", "300"], title="segunda") is False
    assert panel.title_label.text() == "primera"
    panel.shutdown()


def test_the_panel_accepts_a_new_workflow_once_the_last_one_ended(qtbot, panel):
    panel.set_auto_hide(False)
    run_and_wait(qtbot, panel, "exit 0", title="primera")
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "exit 0"], title="segunda")
    assert panel.title_label.text() == "segunda"


def test_the_pid_is_available_while_the_workflow_runs(qtbot, panel):
    panel.set_auto_hide(False)
    assert panel.session_pid() is None
    panel.run(["/bin/sleep", "300"])
    assert isinstance(panel.session_pid(), int)
    panel.shutdown()


# --------------------------------------------------------------- the geometry


def test_the_panel_never_shrinks_below_a_usable_height(panel):
    panel.set_panel_height(10)
    assert panel.panel_height() == MINIMUM_HEIGHT


def test_the_stored_height_is_honoured(panel):
    panel.set_panel_height(420)
    assert panel.panel_height() == 420


def test_hiding_the_panel_reports_the_height_to_keep(qtbot, panel):
    seen: list[bool] = []
    panel.visibility_changed.connect(seen.append)
    panel.set_auto_hide(False)
    panel.run(["/bin/sleep", "300"])
    panel.slide_out()
    assert seen == [True, False]
    panel.shutdown()


def test_sliding_out_a_panel_that_was_never_shown_does_nothing(panel):
    panel.slide_out()
    assert panel.isVisible() is False


# ------------------------------------------------------------------ the shell


def test_retranslating_relabels_the_header(panel):
    panel.retranslate()
    for button in (panel.stop_button, panel.copy_button, panel.hide_button):
        assert button.text().strip()


def test_applying_a_theme_does_not_disturb_a_running_workflow(qtbot, panel):
    panel.set_auto_hide(False)
    assert panel.run(["/bin/sleep", "300"])
    panel.apply_theme()
    assert panel.busy
    panel.shutdown()


def test_asking_for_an_external_terminal_passes_the_script_along(qtbot, panel):
    requests: list[str] = []
    panel.external_terminal_requested.connect(requests.append)
    panel.set_auto_hide(False)
    panel.run(["/bin/sleep", "300"], launch_path="/tmp/bc250-launch.sh")
    panel.external_button.click()
    assert requests == ["/tmp/bc250-launch.sh"]
    panel.shutdown()


def test_no_external_terminal_is_requested_without_a_script(qtbot, panel):
    requests: list[str] = []
    panel.external_terminal_requested.connect(requests.append)
    panel.external_button.click()
    assert requests == []


def test_shutdown_stops_a_running_workflow(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"])
    panel.shutdown()
    assert panel.busy is False


def test_shutdown_is_safe_twice(panel):
    panel.shutdown()
    panel.shutdown()


def test_a_finished_session_is_released_before_the_next_one(qtbot, panel):
    """One object per workflow would otherwise pile up for the whole session."""
    from frontends.desktop.console.pty_session import PtySession

    panel.set_auto_hide(False)
    for _ in range(4):
        run_and_wait(qtbot, panel, "exit 0")
    qtbot.wait(120)
    alive = [
        child for child in panel.findChildren(PtySession)
        if not child.signalsBlocked() or True
    ]
    assert len(alive) <= 2, f"{len(alive)} sessions still attached to the panel"


def test_the_resize_connection_is_not_stacked_across_workflows(qtbot, panel):
    panel.set_auto_hide(False)
    for _ in range(3):
        run_and_wait(qtbot, panel, "exit 0")
    # A stacked connection would raise here on the second disconnect.
    panel._release_previous_session()


def test_the_grid_is_sized_for_the_open_panel_not_the_closed_one(qtbot, panel):
    """The workflow starts while the panel is still sliding into place.

    Sizing the terminal from the viewport at that instant gave the process a
    three-row screen, and everything it printed in the first moments scrolled
    away before anyone could see it.
    """
    panel.set_auto_hide(False)
    panel.set_panel_height(320)
    assert panel.run(["/bin/sleep", "5"])
    # Still animating, but the grid already reflects where the panel is going.
    assert panel.maximumHeight() < 320
    assert panel.view.rows > 8
    panel.shutdown()


def test_every_line_of_a_workflow_survives_the_opening_animation(qtbot, panel):
    panel.set_auto_hide(False)
    panel.set_panel_height(320)
    script = "for i in $(seq 1 12); do echo paso $i; done"
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", script], title="Prueba")
    qtbot.waitUntil(lambda: panel.maximumHeight() == 320, timeout=4000)
    text = panel.view.screen.full_text()
    for index in (1, 6, 12):
        assert f"paso {index}" in text
