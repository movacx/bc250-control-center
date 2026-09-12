import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QLabel, QPushButton, QScrollArea

from frontends.desktop.i18n import set_language
from frontends.desktop.pages.cpu_smu import CpuSmuPage
from frontends.desktop.pages.dashboard import DashboardPage
from frontends.desktop.pages.fans import FansPage
from frontends.desktop.pages.gpu_governor import GpuGovernorPage
from frontends.desktop.pages.performance import PerformancePage
from frontends.desktop.pages.processes import ProcessesPage
from frontends.desktop.pages.settings import SettingsPage


class _SettingsService:
    def read_local_config(self):
        return {}


class _ActivityService:
    def clear(self):
        return True


def _clipped_copy(page, *, ignored_parent=None):
    def included(widget):
        return ignored_parent is None or not ignored_parent.isAncestorOf(widget)

    buttons = [
        button.text()
        for button in page.findChildren(QPushButton)
        if included(button)
        and button.isVisible()
        and button.text()
        and button.sizeHint().width() > button.width() + 3
    ]
    labels = [
        label.text()
        for label in page.findChildren(QLabel)
        if included(label)
        and label.isVisible()
        and label.text()
        and not label.wordWrap()
        and label.sizeHint().width() > label.width() + 3
    ]
    return buttons, labels


@pytest.mark.parametrize("page_type", (CpuSmuPage, FansPage))
@pytest.mark.parametrize("language", ("en", "es", "de", "pl"))
@pytest.mark.parametrize("width", (360, 480, 1024, 1440))
def test_control_pages_reflow_without_outer_overflow_or_clipped_copy(
    qtbot,
    page_type,
    language,
    width,
):
    try:
        set_language(language)
        page = page_type(object())
        qtbot.addWidget(page)
        page.resize(width, 800)
        page.show()
        qtbot.wait(5)

        assert page.scroll.horizontalScrollBar().maximum() == 0
        assert page.content.width() == page.scroll.viewport().width()
        clipped_buttons, clipped_labels = _clipped_copy(page)
        assert clipped_buttons == []
        assert clipped_labels == []
    finally:
        set_language("en")


@pytest.mark.parametrize("language", ("en", "es", "de", "pl"))
@pytest.mark.parametrize("width", (360, 480, 1024, 1440))
def test_fan_curve_command_deck_reflows_without_hidden_page_height_or_clipping(
    qtbot,
    language,
    width,
):
    try:
        set_language(language)
        page = FansPage(object())
        qtbot.addWidget(page)
        page._set_control_mode("curve")
        page.resize(width, 800)
        page.show()
        qtbot.wait(5)

        assert page.scroll.horizontalScrollBar().maximum() == 0
        # The command deck intentionally follows the current page's preferred
        # height instead of caching the construction-time height.  Qt may give
        # it a few pixels of safe layout slack; correctness is that it never
        # becomes shorter than the visible curve content.
        assert page.control_stack.height() >= page.curve_card.sizeHint().height()
        assert _clipped_copy(page) == ([], [])
    finally:
        set_language("en")


@pytest.mark.parametrize(
    "page_type",
    (DashboardPage, GpuGovernorPage, PerformancePage, ProcessesPage, SettingsPage),
)
@pytest.mark.parametrize("language", ("en", "es", "de", "pl"))
@pytest.mark.parametrize("width", (360, 720, 1024))
def test_remaining_primary_pages_follow_viewport_and_keep_copy_visible(
    qtbot,
    tmp_path,
    page_type,
    language,
    width,
):
    try:
        set_language(language)
        if page_type is SettingsPage:
            settings = QSettings(str(tmp_path / f"{language}-{width}.ini"), QSettings.Format.IniFormat)
            page = page_type(
                object(),
                settings_service=_SettingsService(),
                activity_service=_ActivityService(),
                app_settings=settings,
            )
        elif page_type is ProcessesPage:
            page = page_type(object(), activity_service=_ActivityService())
        else:
            page = page_type(object())
        qtbot.addWidget(page)
        page.resize(width, 800)
        page.show()
        qtbot.wait(5)

        if page_type is GpuGovernorPage:
            scroll = page.overview_scroll
        elif page_type is SettingsPage:
            scroll = next(
                item
                for item in page.findChildren(QScrollArea)
                if item.objectName() == "SettingsSectionScroll" and item.isVisible()
            )
        else:
            scroll = page.scroll
        assert scroll.horizontalScrollBar().maximum() == 0
        assert _clipped_copy(page) == ([], [])
    finally:
        set_language("en")


