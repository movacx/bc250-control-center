"""The experimental sleep row: only where its author supports it, and never without saying what it changes."""

from __future__ import annotations

from frontends.desktop.components.dashboard_widgets import PreparationSidebar


def _row(qtbot, **info):
    sidebar = PreparationSidebar(standalone=True)
    qtbot.addWidget(sidebar)
    sidebar._render_accessories({"real_sleep": {"s3_supported": True, "mode": "", "reason": "", **info}})
    return sidebar, sidebar.accessory_buttons["real_sleep"]


def test_it_is_hidden_where_it_is_not_supported(qtbot):
    sidebar, _buttons = _row(qtbot, state="unsupported")
    assert sidebar.real_sleep_card.isHidden()


def test_a_reason_turns_the_install_off_and_is_shown(qtbot):
    from bc250cc.infrastructure.accessories.real_sleep import REASON_CORES

    sidebar, buttons = _row(qtbot, state="not-installed", reason=REASON_CORES)
    assert not buttons["install"].isEnabled()
    assert sidebar._accessory_notes["real_sleep"].text() == REASON_CORES


def test_installed_it_offers_the_other_mode_and_remove(qtbot):
    _sidebar, buttons = _row(qtbot, state="installed", mode="s3")
    assert buttons["configure"].request_payload["op"] == "mode-hibernate"
    assert not buttons["remove"].isHidden() and buttons["install"].isHidden()
    # Without BIOS P3.00 there is no S3 to go back to.
    _sidebar, buttons = _row(qtbot, state="installed", mode="hibernate", s3_supported=False)
    assert buttons["configure"].isHidden()
