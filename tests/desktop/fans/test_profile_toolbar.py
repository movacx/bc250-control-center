"""Fan profiles: Delete sits right after Apply; Save as… lives in More.

Reported 2026-11-16 (Discord): a saved profile could not be found to delete;
it was only in More › Delete.
"""

from __future__ import annotations

from frontends.desktop.pages.fans import FansPage


class _Controller:
    def aplicar_pwm_fan(self, *args):
        pass

    def restaurar_pwm_automatico(self, *args):
        pass


def _page(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.resize(1440, 900)
    return page


def test_delete_comes_right_after_apply(qtbot):
    page = _page(qtbot)
    rows = [page.toolbar_box.itemAt(i).layout() for i in range(page.toolbar_box.count())]
    row = next(layout for layout in rows if layout is not None and layout.indexOf(page.profile_apply) >= 0)
    assert row.indexOf(page.profile_delete) == row.indexOf(page.profile_apply) + 1
    assert not hasattr(page, "profile_save")


def test_a_built_in_profile_cannot_be_deleted(qtbot):
    page = _page(qtbot)
    page._render_profiles()
    assert page.profile_combo.currentData() in {"Quiet", "Balanced", "Performance"}
    assert not page.profile_delete.isEnabled()


def test_save_as_is_the_first_entry_in_more(qtbot):
    page = _page(qtbot)
    page._fill_more_menu()
    first = next(action for action in page.more_menu.actions() if not action.isSeparator())
    assert first.text() in {"Save profile as…", "Guardar perfil como…"}
