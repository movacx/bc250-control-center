import pytest
from PyQt6.QtCore import QAbstractAnimation, QPoint, Qt
from PyQt6.QtGui import QImage

import frontends.desktop.pages.dashboard as dashboard_module
from frontends.desktop.components.widgets import ICON_DIR
from frontends.desktop.i18n import localize_widget_tree, set_language, tr
from frontends.desktop.pages.dashboard import CONTACT_URL, SUPPORT_URL, DashboardPage
from frontends.desktop.theme import application_stylesheet


@pytest.mark.parametrize("width", (360, 720, 1440))
@pytest.mark.parametrize("theme", ("light", "dark"))
def test_header_actions_stay_visible_without_covering_scrolled_controls(qtbot, width, theme):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.setStyleSheet(application_stylesheet(theme))
    page.resize(width, 800)
    page.show()
    qtbot.wait(100)
    assert page.width() == width
    assert page.content.isAncestorOf(page.footer)
    assert page.readiness.system_bar.isAncestorOf(page.footer)
    # The links live in the preparation header; no footer strip is reserved.
    assert page.scroll.height() == page.height()
    assert page.scroll.viewportMargins().right() == 0
    scrollbar = page.scroll.verticalScrollBar()
    assert scrollbar.mapTo(page.scroll, QPoint()).x() > page.scroll.viewport().geometry().right()
    bar = page.scroll.verticalScrollBar()
    assert bar.maximum() > 0
    for value in (bar.maximum() // 2, bar.maximum(), 0):
        bar.setValue(value)
        qtbot.wait(10)
        for button in (page.footer.repositories_button, page.contact_button, page.support_button):
            assert button.isVisible()
            origin = button.mapTo(page.readiness.system_bar, QPoint())
            assert page.readiness.system_bar.rect().contains(origin)
            assert page.readiness.system_bar.rect().contains(origin + button.rect().bottomRight())


def test_sticky_buttons_keep_routes_translations_and_keyboard_activation(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr(dashboard_module, "open_external_url", lambda url: (opened.append(url) or True, ""))
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.resize(1000, 800)
    page.show()
    try:
        for language in ("es", "de", "en"):
            set_language(language)
            localize_widget_tree(page, language)
            for button, label in (
                (page.support_button, "Buy me a coffee"),
                (page.contact_button, "Report a problem / Contact"),
                (page.footer.repositories_button, "Official repositories"),
            ):
                assert button.text() == ""
                assert button.accessibleName() == tr(label, language)
                assert button.toolTip() == tr(label, language)
        page.support_button.setFocus()
        qtbot.keyClick(page.support_button, Qt.Key.Key_Space)
        page.contact_button.click()
        assert opened == [SUPPORT_URL, CONTACT_URL]
    finally:
        set_language("en")


def test_footer_hover_animation_is_finite_and_stops_when_hidden(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.show()
    button = page.support_button
    button._animate_lift(True)
    qtbot.waitUntil(lambda: button._lift.state() == QAbstractAnimation.State.Stopped)
    assert button.graphicsEffect().blurRadius() == 16.0
    button._animate_lift(False)
    page.readiness.hide()
    assert button._lift.state() == QAbstractAnimation.State.Stopped
    assert button.graphicsEffect().blurRadius() == 4.0


@pytest.mark.parametrize("scale", (70, 100, 150))
@pytest.mark.parametrize("mode", ("light", "dark"))
def test_header_actions_are_compact_and_scale_without_clipping(qtbot, scale, mode):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    try:
        style = application_stylesheet(mode, scale=scale)
        page.setStyleSheet(style)
        page.resize(360, 800)
        page.show()
        qtbot.wait(100)
        assert page.width() == 360
        assert page.footer.width() < 180
        assert page.footer.height() < 70
        assert page.footer.repositories_button.geometry().right() < page.contact_button.x()
        assert page.contact_button.y() == page.support_button.y()
        assert page.contact_button.geometry().right() < page.support_button.x()
        for button in (page.footer.repositories_button, page.contact_button, page.support_button):
            assert abs(button.width() - button.height()) <= 2
            assert button.iconSize().width() == round(22 * scale / 100)
            assert button.iconSize().width() < button.width()
            assert not button.icon().pixmap(button.iconSize()).isNull()
        if scale == 100:
            assert page.footer.height() <= 48
            assert 34 <= page.support_button.width() <= 38
    finally:
        application_stylesheet("light", scale=100)


def test_official_kofi_artwork_is_available_offline():
    image = QImage(str(ICON_DIR / "kofi_cup.png"))
    assert not image.isNull()
    assert image.hasAlphaChannel()
    assert image.width() > 100
