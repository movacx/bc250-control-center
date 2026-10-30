"""Five-minute visual privacy must hide live controls without altering the service."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from frontends.desktop.pages import remote_access as remote


def state():
    return {"running": True, "tls": True, "lan": True, "key": "TEST-PAIR", "urls": ["https://192.168.0.2:8250"],
            "devices": [{"id": "device", "address": "192.168.0.3", "control": True}]}


def page_with_clock(qtbot, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(remote, "_privacy_time", lambda: now[0])
    page = remote.RemoteAccessPage()
    page.resize(1000, 800)
    qtbot.addWidget(page)
    page._apply_web(state())
    page.show()
    return page, now


def test_privacy_window_begins_when_opened_and_hides_the_whole_view_at_five_minutes(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    assert page._privacy_timer.interval() == 300000
    assert page._privacy_deadline == 400.0
    now[0] = 399.0
    page._check_privacy()
    assert not page._privacy_hidden
    now[0] = 400.0
    page._check_privacy()
    assert page._privacy_hidden
    assert page._privacy_cover.isVisible()
    assert page._privacy_cover.parentWidget() is page.card
    assert page.card.rect().contains(page._privacy_cover.geometry())
    assert page._scroll.isVisible()
    assert not page.web_pin_box.isVisible()
    assert not page.web_qr_image.isVisible()
    assert not page.device_table.isVisible()
    assert page._privacy_cover.reveal_button.isVisible()
    assert not page.timer.isActive()
    assert not page._privacy_timer.isActive()
    assert not hasattr(page._privacy_cover, "_background")
    assert page._web_state["running"] is True  # Only the view was concealed.


def test_reveal_starts_a_fresh_window_but_refreshes_and_navigation_do_not(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    now[0] = 200.0
    page._apply_web(state())
    assert page._privacy_deadline == 400.0
    page.hide()
    now[0] = 401.0
    page.show()
    assert page._privacy_hidden
    page._apply_web({**state(), "key": "NEXT-PAIR"})
    assert page._privacy_hidden
    assert page.web_pin_box.text() == "TEST-PAIR"
    page._privacy_cover.reveal_button.click()
    assert not page._privacy_hidden
    assert page.web_pin_box.text() == "NEXT-PAIR"
    assert page._scroll.isVisible()
    assert page._privacy_deadline == 701.0
    assert not page._privacy_cover.isVisible()
    now[0] = 701.0
    page._check_privacy()
    assert page._privacy_hidden


def test_cover_blocks_queued_controls_and_does_not_clear_unrelated_clipboard(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    calls = []
    monkeypatch.setattr(page._background, "start", lambda *a, **k: calls.append(a))
    QApplication.clipboard().setText("unrelated clipboard")
    page._conceal_information()
    page._copy("TEST-PAIR")
    page._run("unexpected", lambda: calls.append("work"))
    page.refresh()
    page.set_updates_active(True)
    assert not calls
    assert QApplication.clipboard().text() == "unrelated clipboard"
    assert page._privacy_hidden
    page._privacy_cover.reveal_button.click()
    assert calls and page.timer.isActive()


def test_a_timer_timeout_and_application_activation_check_the_same_deadline(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    now[0] = 401.0
    page._privacy_timer.timeout.emit()
    assert page._privacy_hidden
    page._reveal_information()
    now[0] += remote.PRIVACY_SECONDS + 1
    page._application_state_changed(Qt.ApplicationState.ApplicationActive)
    assert page._privacy_hidden


def test_expired_view_cannot_submit_a_click_before_the_timer_event(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    calls = []
    monkeypatch.setattr(page._background, "start", lambda *a, **k: calls.append(a))
    now[0] = page._privacy_deadline + 1
    page._run("late_click", lambda: calls.append("work"))
    assert page._privacy_hidden
    assert not calls


def test_header_button_locks_again_after_revealing_without_waiting(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    page.privacy_lock_button.click()
    assert page._privacy_hidden
    assert not page.privacy_lock_button.isVisible()
    assert page._web_state["running"] is True
    page._privacy_cover.reveal_button.click()
    assert not page._privacy_hidden
    assert page.privacy_lock_button.isVisible()
    now[0] += 5
    page.privacy_lock_button.click()
    assert page._privacy_hidden
    assert page._privacy_cover.isVisible()
    assert page._privacy_cover.parentWidget() is page.card
    assert page.card.rect().contains(page._privacy_cover.geometry())


def test_cover_stays_inside_card_and_reveal_tracks_the_visible_scrolled_area(qtbot, monkeypatch):
    from PyQt6.QtCore import QPoint, QRect
    page, now = page_with_clock(qtbot, monkeypatch)
    page._set_device_table_height(1800)
    QApplication.processEvents()
    original_height = page.card.height()
    page._conceal_information()
    QApplication.processEvents()
    assert page.card.height() == original_height
    assert page._privacy_cover._sweep.isActive()
    scrollbar = page._scroll.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    page.resize(850, 650)
    QApplication.processEvents()
    page._position_privacy_cover()
    cover = page._privacy_cover
    assert page.card.rect().contains(cover.geometry())
    viewport = page._scroll.viewport()
    visible = QRect(cover.mapFrom(viewport, QPoint(0, 0)), viewport.size()).intersected(cover.rect())
    assert visible.contains(cover._message.geometry().center())
    page.hide()
    assert not cover._sweep.isActive()


def test_soft_animation_changes_pixels_without_capturing_private_content(qtbot, monkeypatch):
    page, now = page_with_clock(qtbot, monkeypatch)
    page._conceal_information()
    cover = page._privacy_cover
    first = cover.grab().toImage()
    for _ in range(12):
        cover._animate()
    second = cover.grab().toImage()
    assert first != second
    assert not hasattr(cover, "_background")
    assert not page.web_qr_image.isVisible()
