"""The Firmware (BIOS) page, with every piece of hardware replaced.

No test here lists real drives, asks the real UDisks2 or reads this machine's
DMI: the watcher gets a fake drive list, UDisks2 availability and the board
are patched, and the preparation that would erase a stick is a stand-in that
only reports steps. What is exercised is the page: what it selects by itself,
when it lets the user start, what it says while it works and after.
"""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QDialog

import frontends.desktop.pages.firmware as firmware_module
from bc250cc.domain.firmware.boot_logo import check_logo_jpeg
from bc250cc.domain.firmware.catalog import FAMILIES_BY_KEY, FIRMWARE_FAMILIES
from bc250cc.domain.firmware.usb import UsbDrive, UsbPartition
from bc250cc.infrastructure.firmware.board import BoardFirmware
from bc250cc.infrastructure.firmware.preparation import (
    PreparationCancelled,
    PreparationError,
    PreparationReport,
    steps_for,
)
from bc250cc.infrastructure.firmware.store import FirmwareStore
from frontends.desktop.i18n import localize_widget_tree, set_language, tr
from frontends.desktop.pages.firmware import FirmwarePage

GB = 1000 ** 3

KINGSTON = UsbDrive(
    name="sdb", path="/dev/sdb", size=16 * GB, vendor="Kingston", model="DataTraveler 3.0",
    serial="K1", transport="usb", removable=True,
    partitions=(UsbPartition("sdb1", "/dev/sdb1", 16 * GB, label="PHOTOS", fstype="vfat"),),
)
SANDISK = UsbDrive(
    name="sdc", path="/dev/sdc", size=32 * GB, vendor="SanDisk", model="SanDisk Ultra",
    serial="S1", transport="usb", removable=True,
)
LOCKED = UsbDrive(
    name="sdd", path="/dev/sdd", size=8 * GB, vendor="Generic", model="Card Reader",
    serial="L1", transport="usb", read_only=True,
)


class _Dialog:
    """ConfirmDialog stand-in that answers without a window."""

    answer = QDialog.DialogCode.Accepted
    shown: list[tuple] = []

    DialogCode = QDialog.DialogCode

    def __init__(self, title, message, **options):
        _Dialog.shown.append((title, message, options))

    def exec(self):
        return _Dialog.answer


class _Preparation:
    """Reports every step and succeeds, unless told otherwise."""

    behaviour = "succeed"
    plans: list = []

    def __init__(self, store, udisks_client):
        self.store = store
        self.udisks = udisks_client

    def run(self, plan, drive, *, progress, cancelled):
        _Preparation.plans.append((plan, drive))
        if _Preparation.behaviour == "fail-logo":
            progress("download", 1.0, "")
            progress("logo", 0.0, "BC250_3.00_CHIPSETMENU.ROM")
            raise PreparationError(
                "logo", "Custom boot logo: DXE volume: a file has attributes. "
                "This firmware image is not one a logo can be added to."
            )
        if _Preparation.behaviour == "wait-for-cancel":
            progress("download", 0.3, "BOOTX64.EFI")
            for _ in range(500):
                if cancelled():
                    raise PreparationCancelled()
                threading.Event().wait(0.01)
            raise AssertionError("never cancelled")
        for step in steps_for(plan):
            progress(step, 0.0, step)
            if _Preparation.behaviour == "fail-copy" and step == "copy":
                raise PreparationError("copy", "Could not write to the USB: [Errno 5] Input/output error")
            progress(step, 1.0, "")
        return PreparationReport(partition="sdb1", files=len(plan.files), bytes_written=1, ejected=True)


@pytest.fixture
def page(qtbot, monkeypatch, tmp_path):
    _Dialog.answer = QDialog.DialogCode.Accepted
    _Dialog.shown = []
    _Preparation.behaviour = "succeed"
    _Preparation.plans = []
    monkeypatch.setattr(firmware_module, "ConfirmDialog", _Dialog)
    monkeypatch.setattr(firmware_module, "UsbPreparation", _Preparation)
    monkeypatch.setattr(firmware_module.udisks, "available", lambda: True)
    monkeypatch.setattr(firmware_module.udisks, "UDisksClient", lambda: object())
    monkeypatch.setattr(
        firmware_module, "read_board_firmware",
        lambda: BoardFirmware(board="BC-250", vendor="American Megatrends International, LLC.",
                              version="P3.00", date="06/13/2023"),
    )
    widget = FirmwarePage(object())
    widget.store = FirmwareStore(tmp_path / "cache")
    widget.drives = []
    widget.watcher._list_drives = lambda: list(widget.drives)
    qtbot.addWidget(widget)
    widget.resize(1500, 1000)
    yield widget
    widget.set_updates_active(False)


def _plug(qtbot, page, *drives):
    page.drives = list(drives)
    page.set_updates_active(True)
    page.watcher.refresh()
    qtbot.waitUntil(lambda: page.watcher.known and set(page.usb_cards) == {d.name for d in drives})
    qtbot.waitUntil(lambda: page._udisks_ready is not None)


def _fact(facts, key):
    return facts.facts[key].value.text()


def test_every_firmware_is_offered_with_the_recommended_one_chosen(page):
    assert list(page.firmware_cards) == [family.key for family in FIRMWARE_FAMILIES]
    assert page.selected_family().key == "p3-chipset-menu"
    assert page.firmware_cards["p3-chipset-menu"].property("selectedProfile") is True
    assert not page.prepare_button.isEnabled()
    assert _fact(page.plan_facts, "firmware") == "P3.00 Chipset Menu"
    assert _fact(page.plan_facts, "drive") == "Choose a USB drive"


def test_the_list_groups_modded_images_above_stock_ones(page):
    holder = page.firmware_list.widget()
    order = [holder.layout().itemAt(i).widget() for i in range(holder.layout().count())]
    order = [widget for widget in order if widget is not None]
    modded, stock = page.category_headings["modded"], page.category_headings["stock"]
    assert order.index(modded) < order.index(page.firmware_cards["p3-chipset-menu"])
    assert order.index(page.firmware_cards["meimeidxe-v3"]) < order.index(stock)
    assert order.index(stock) < order.index(page.firmware_cards["p5-stock"])
    assert modded.text() == "MODDED BIOS" and stock.text() == "STOCK BIOS (ASROCK)"


def test_no_card_carries_a_pill_any_more(page):
    from frontends.desktop.components.widgets import PillLabel

    assert page.findChildren(PillLabel) == []


@pytest.mark.parametrize(
    "key, vram, cores, logo, after",
    [
        ("p3-chipset-menu", "Yes", "6 of 8", "As shipped", "Clear CMOS"),
        ("meimeidxe-v3", "Yes", "8 of 8", "16 to choose from", "Nothing to do"),
        ("p5-stock", "No", "6 of 8", "As shipped", "Clear CMOS"),
        ("p3-stock", "No", "6 of 8", "As shipped", "Clear CMOS"),
        ("p2-stock", "No", "6 of 8", "As shipped", "Clear CMOS"),
    ],
)
def test_every_card_answers_the_same_four_questions(page, key, vram, cores, logo, after):
    card = page.firmware_cards[key]
    values = {name: label.text() for name, label in card.fact_values.items()}
    assert values == {"vram": vram, "cores": cores, "logo": logo, "after": after}
    assert [label.text() for label in card.fact_labels.values()] == [
        "VRAM IN THE BIOS", "CPU CORES", "BOOT LOGO", "AFTER FLASHING",
    ]
    tone = card.fact_values["after"].property("tone")
    assert tone == ("caution" if after == "Clear CMOS" else None)
    assert card.fact_values["vram"].property("tone") == ("muted" if vram == "No" else None)


def test_every_card_lists_what_its_image_offers(page):
    for family in FIRMWARE_FAMILIES:
        card = page.firmware_cards[family.key]
        assert [row.text.text() for row in card.highlight_rows] == list(family.highlights)
        assert card.highlights.isVisibleTo(card)
    meimei = " / ".join(FAMILIES_BY_KEY["meimeidxe-v3"].highlights)
    for drivers in ("8 CPU cores", "SMU unlock", "ACPI patch", "factory cores", "MeiMeiDXEv3 Menu"):
        assert drivers in meimei


def test_the_highlights_line_up_with_the_facts_and_fold_on_a_narrow_card(qtbot, page):
    card = page.firmware_cards["meimeidxe-v3"]
    page.resize(1920, 900)
    page.show()
    qtbot.waitExposed(page)
    qtbot.waitUntil(lambda: card._highlight_columns == 2)
    second = card.highlight_rows[1]
    third_fact = card.fact_labels["logo"]
    assert second.mapTo(card, second.rect().topLeft()).x() == third_fact.mapTo(card, third_fact.rect().topLeft()).x()
    assert card.highlight_rows[1].y() == card.highlight_rows[0].y()
    # Beside a line that wraps, a short one stays level with it.
    long_line, short_line = card.highlight_rows[2], card.highlight_rows[3]
    long_line.text.setText("A highlight long enough to wrap onto a second line " * 3)
    # It keeps its own height instead of being centred in the taller row.
    qtbot.waitUntil(lambda: long_line.height() > short_line.height())
    assert short_line.y() == long_line.y()
    assert short_line.text.alignment() & firmware_module.Qt.AlignmentFlag.AlignTop
    page.resize(540, 900)
    qtbot.waitUntil(lambda: card.width() < firmware_module.FACTS_ONE_ROW_WIDTH)
    assert card._highlight_columns == 1
    assert card.highlight_rows[1].y() > card.highlight_rows[0].y()


def test_a_caution_shows_only_on_the_chosen_card(page):
    meimei = page.firmware_cards["meimeidxe-v3"]
    assert not meimei.caution.isVisibleTo(meimei)
    meimei.gamepad_activate()
    assert meimei.caution.isVisibleTo(meimei)
    assert "unstable" in meimei.caution.text()
    page.firmware_cards["p3-chipset-menu"].gamepad_activate()
    assert not meimei.caution.isVisibleTo(meimei)


def test_the_installed_bios_is_read_when_the_page_opens(qtbot, page):
    _plug(qtbot, page)
    assert _fact(page.board_facts, "version") == "P3.00"
    assert _fact(page.board_facts, "date") == "06/13/2023"
    assert _fact(page.board_facts, "board") == "BC-250"
    assert not page.board_note.isVisibleTo(page)


def test_a_computer_that_is_not_a_bc250_is_told_so(qtbot, page, monkeypatch):
    monkeypatch.setattr(firmware_module, "read_board_firmware",
                        lambda: BoardFirmware(board="X570 AORUS", version="F37"))
    _plug(qtbot, page)
    assert _fact(page.board_facts, "version") == "F37"
    assert page.board_note.isVisibleTo(page)
    assert "not a BC-250" in page.board_note.text()


def test_a_single_usb_stick_is_chosen_by_itself(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    assert page.selected_drive() == KINGSTON
    assert page.usb_cards["sdb"].property("selectedProfile") is True
    assert page.prepare_button.isEnabled()
    assert _fact(page.plan_facts, "drive") == "Kingston DataTraveler 3.0 · 16 GB"
    assert not page.usb_empty.isVisibleTo(page)


def test_the_drive_card_puts_its_size_in_the_detail_line(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    card = page.usb_cards["sdb"]
    assert card.detail.text() == "/dev/sdb  ·  16 GB  ·  PHOTOS"
    assert card.title.text() == "Kingston DataTraveler 3.0"


def test_two_sticks_wait_for_the_user_to_pick_one(qtbot, page):
    _plug(qtbot, page, KINGSTON, SANDISK)
    assert page.selected_drive() is None
    assert not page.prepare_button.isEnabled()
    page.usb_cards["sdc"].gamepad_activate()
    assert page.selected_drive() == SANDISK
    assert page.prepare_button.isEnabled()


def test_a_drive_that_cannot_be_used_is_shown_disabled_with_the_reason(qtbot, page):
    _plug(qtbot, page, LOCKED)
    card = page.usb_cards["sdd"]
    assert not card.isEnabled()
    assert card.note.text() == "This drive is write-protected."
    assert page.selected_drive() is None
    card.gamepad_activate()
    assert page.selected_drive() is None


def test_pulling_the_chosen_stick_out_clears_the_choice(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    page.drives = []
    page.watcher.refresh()
    qtbot.waitUntil(lambda: not page.usb_cards)
    assert page.selected_drive() is None
    assert not page.prepare_button.isEnabled()
    assert page.usb_empty_label.text() == "Waiting for a USB drive…"


def test_without_udisks_the_page_explains_and_does_not_offer_to_prepare(qtbot, page, monkeypatch):
    monkeypatch.setattr(firmware_module.udisks, "available", lambda: False)
    _plug(qtbot, page, KINGSTON)
    assert page.udisks_note.isVisibleTo(page)
    assert not page.prepare_button.isEnabled()


def test_the_steps_are_left_to_the_tour(page):
    """The page no longer carries a numbered guide; the tour does."""
    from frontends.desktop.onboarding.script import tour_stops

    assert not hasattr(page, "guide_steps")
    flash = [stop for stop in tour_stops() if stop.page == "firmware" and stop.ordered]
    assert len(flash) == 1 and len(flash[0].points) == 6
    assert firmware_module.AFTER_FLASH_WARNING in flash[0].points
    assert page.after_flash_note.text() == firmware_module.AFTER_FLASH_WARNING


def test_variants_name_the_boot_logo_in_the_summary(page):
    page.firmware_cards["meimeidxe-v3"].gamepad_activate()
    combo = page.firmware_cards["meimeidxe-v3"].variant_combo
    assert page.firmware_cards["meimeidxe-v3"].variant_row.isVisibleTo(page)
    combo.setCurrentIndex(combo.findData("cachyos"))
    assert page.selected_image().key == "cachyos"
    assert _fact(page.plan_facts, "firmware") == "P3.00 MeiMeiDXE v3 — CachyOS logo"


def test_a_declined_confirmation_touches_nothing(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    _Dialog.answer = QDialog.DialogCode.Rejected
    page.prepare_button.click()
    assert _Dialog.shown and _Dialog.shown[0][0] == "Erase this USB drive?"
    assert page._job is None
    assert _Preparation.plans == []


def test_the_confirmation_names_the_drive_and_what_is_on_it(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    _Dialog.answer = QDialog.DialogCode.Rejected
    page.prepare_button.click()
    options = _Dialog.shown[0][2]
    summary = dict(options["summary"])
    assert summary["USB drive"] == "Kingston DataTraveler 3.0 · 16 GB"
    assert summary["Device"] == "/dev/sdb"
    assert summary["Contains"] == "PHOTOS"
    assert summary["Firmware"] == "P3.00 Chipset Menu"
    assert summary["Download"].endswith("checked by SHA-256")
    assert options["tone"] == "red"
    assert options["notice"] == firmware_module.AFTER_FLASH_WARNING


def test_an_image_that_resets_its_own_settings_needs_no_cmos_notice(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    page.firmware_cards["meimeidxe-v3"].gamepad_activate()
    _Dialog.answer = QDialog.DialogCode.Rejected
    page.prepare_button.click()
    assert _Dialog.shown[0][2]["notice"] == ""


def test_a_confirmed_preparation_runs_every_step_and_says_what_to_do_next(qtbot, page):
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    plan, drive = _Preparation.plans[0]
    assert drive == KINGSTON
    assert plan.family is FAMILIES_BY_KEY["p3-chipset-menu"]
    assert plan.logo is None
    # Without a custom logo there is no logo step to show.
    assert page.step_rows["logo"].isHidden()
    assert all(row.state == "done" for key, row in page.step_rows.items() if key != "logo")
    assert page.progress.value() == 1000
    assert page.result.property("firmwareResult") == "success"
    assert "ready and ejected" in page.result_text.text()
    assert firmware_module.AFTER_FLASH_WARNING in page.result_text.text()
    assert page.prepare_button.isEnabled()
    assert all(card.isEnabled() for card in page.firmware_cards.values())


def test_a_failure_after_the_erase_says_the_stick_is_not_a_kit(qtbot, page):
    _Preparation.behaviour = "fail-copy"
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    text = page.result_text.text()
    assert page.result.property("firmwareResult") == "danger"
    assert page.step_rows["copy"].state == "failed"
    assert "The USB drive could not be prepared." in text
    assert "erased but is not a working kit" in text
    assert "Input/output error" in text
    assert "BC250-USB-002" in text


def test_cancelling_before_the_erase_leaves_the_stick_untouched(qtbot, page):
    _Preparation.behaviour = "wait-for-cancel"
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page.step_rows["download"].state == "active", timeout=5000)
    assert page.cancel_button.isEnabled()
    assert page.close_blocker() == ""
    page.cancel_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    assert page.result.property("firmwareResult") == "neutral"
    assert page.result_text.text() == "Cancelled. The USB drive was not touched."


class _WritingJob:
    def __init__(self, can_cancel):
        self.can_cancel = can_cancel

    def isRunning(self):  # noqa: N802 - Qt API name
        return True


def test_the_window_cannot_close_while_a_stick_is_being_written(page):
    page._job = _WritingJob(can_cancel=False)
    try:
        assert "Closing now would leave it unusable" in page.close_blocker()
        assert page.busy
        page._select_family("p5-stock")
        assert page.selected_family().key == "p3-chipset-menu"
    finally:
        page._job = None
    assert page.close_blocker() == ""


def test_a_download_that_can_still_be_cancelled_does_not_block_closing(page):
    page._job = _WritingJob(can_cancel=True)
    try:
        assert page.close_blocker() == ""
    finally:
        page._job = None


def test_the_page_speaks_the_chosen_language(qtbot, page):
    _plug(qtbot, page, LOCKED)
    try:
        set_language("es")
        localize_widget_tree(page, "es")
        page.retranslate_dynamic_copy()
        assert page.prepare_button.text() == tr("Prepare USB", "es") == "Preparar USB"
        assert page.usb_cards["sdd"].note.text() == "Esta unidad está protegida contra escritura."
        assert page.step_rows["erase"].title.text() == "Borrar la unidad USB"
        assert page.category_headings["modded"].text() == tr("Modded BIOS", "es").upper()
        assert page.firmware_cards["meimeidxe-v3"].fact_values["after"].text() == tr("Nothing to do", "es")
        assert page.firmware_cards["p5-stock"].summary.text() == tr(
            FAMILIES_BY_KEY["p5-stock"].summary, "es"
        )
        assert page.firmware_cards["meimeidxe-v3"].highlight_rows[0].text.text() == (
            "Los 8 núcleos de CPU, o elige cuáles funcionan"
        )
    finally:
        set_language("en")
        localize_widget_tree(page, "en")
        page.retranslate_dynamic_copy()


@pytest.mark.parametrize("width", [700, 1180, 1920])
def test_the_page_reflows_without_clipping(qtbot, page, width):
    _plug(qtbot, page, KINGSTON, LOCKED)
    page.resize(width, 900)
    page.show()
    qtbot.waitExposed(page)
    content = page.scroll.widget()
    assert content.width() <= page.scroll.viewport().width()
    stacked = width < firmware_module.STACK_WIDTH
    assert not page.safety_panel.isVisible()
    margins = page.content_layout.contentsMargins()
    if stacked:
        assert page.side_panel.y() > page.firmware_panel.y()
        assert page.side_panel.x() == page.firmware_panel.x()
        assert page.firmware_list.height() <= firmware_module.STACKED_LIST_HEIGHT
        assert margins.bottom() == firmware_module.PAGE_BOTTOM
    else:
        # The list runs the full height of the page, beside the side table,
        # and both end clear of the sidebar's Firmware button.
        assert page.side_panel.x() > page.firmware_panel.x()
        assert page.firmware_panel.y() == page.side_panel.y()
        assert page.firmware_panel.geometry().bottom() == page.side_panel.geometry().bottom()
        assert margins.bottom() == firmware_module.FOOT_CLEARANCE
        assert content.height() - page.side_panel.geometry().bottom() > firmware_module.FOOT_CLEARANCE
    for panel in (page.firmware_panel, page.side_panel):
        assert panel.geometry().right() <= content.width()
    holder = page.firmware_list.widget()
    for card in page.firmware_cards.values():
        assert card.geometry().right() <= holder.width()


def test_the_list_scrolls_inside_its_box_and_follows_focus(qtbot, page):
    page.resize(1920, 900)
    page.show()
    qtbot.waitExposed(page)
    bar = page.firmware_list.verticalScrollBar()
    assert bar.maximum() > 0
    last = page.firmware_cards["p2-stock"]
    last.setFocus()
    qtbot.waitUntil(lambda: bar.value() > 0)
    top = last.mapTo(page.firmware_list.viewport(), last.rect().topLeft()).y()
    assert 0 <= top < page.firmware_list.viewport().height()


def test_the_facts_fold_onto_two_lines_on_a_narrow_card(qtbot, page):
    card = page.firmware_cards["p5-stock"]
    page.resize(540, 900)
    page.show()
    qtbot.waitExposed(page)
    qtbot.waitUntil(lambda: card.width() < firmware_module.FACTS_ONE_ROW_WIDTH)
    assert card._fact_columns == 2
    page.resize(1920, 900)
    qtbot.waitUntil(lambda: card._fact_columns == 4)
    for value in card.fact_values.values():
        assert value.geometry().right() <= card.width()


# ------------------------------------------------------- custom boot logo

def _picture(tmp_path, name="mine.png") -> str:
    image = QImage(400, 200, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.fillRect(QRect(100, 50, 200, 100), QColor("#43a047"))
    painter.end()
    path = tmp_path / name
    assert image.save(str(path))
    return str(path)


def _choose(qtbot, page, monkeypatch, path):
    monkeypatch.setattr(
        firmware_module.QFileDialog, "getOpenFileName", staticmethod(lambda *_a, **_k: (path, ""))
    )
    page.logo_choose.click()
    qtbot.waitUntil(lambda: not page._background.is_running("boot-logo"), timeout=5000)


def _cell(page, widget):
    row, column, _rows, _columns = page.workspace.getItemPosition(page.workspace.indexOf(widget))
    return row, column


def test_the_page_is_two_columns_with_the_list_the_full_height(page):
    """Left, the images; right, one table of the logo, the board, the drive
    and the button. Nothing else."""
    page._reflow(1400)
    position = page.workspace.getItemPosition
    assert position(page.workspace.indexOf(page.firmware_panel)) == (0, 0, 1, 1)
    assert _cell(page, page.side_panel) == (0, 1)
    assert page.workspace.count() == 2
    assert not hasattr(page, "sources_panel")
    for section in (page.logo_panel, page.board_facts, page.usb_panel, page.prepare_panel):
        assert page.side_panel.isAncestorOf(section)
    page._reflow(900)
    assert [_cell(page, panel) for panel in (page.firmware_panel, page.side_panel)] == [(0, 0), (1, 0)]


def test_before_you_start_heads_the_right_column_when_shown(page, monkeypatch):
    monkeypatch.setattr(firmware_module, "SAFETY_PANEL_SHOWN", True)
    page._stacked = None
    page._reflow(1400)
    position = page.workspace.getItemPosition
    assert position(page.workspace.indexOf(page.firmware_panel)) == (0, 0, 2, 1)
    assert _cell(page, page.safety_panel) == (0, 1)
    assert _cell(page, page.side_panel) == (1, 1)
    page._reflow(900)
    assert [_cell(page, panel) for panel in (page.firmware_panel, page.safety_panel, page.side_panel)] == [
        (0, 0), (1, 0), (2, 0),
    ]


def test_the_side_table_reads_logo_board_drive_then_button(qtbot, page):
    page.resize(1920, 1100)
    page.show()
    qtbot.waitExposed(page)

    def top(widget):
        return widget.mapTo(page.side_panel, widget.rect().topLeft()).y()

    order = [page.logo_panel, page.board_facts, page.usb_panel, page.prepare_panel]
    assert [top(widget) for widget in order] == sorted(top(widget) for widget in order)
    # The installed BIOS reads across, like a firmware card's facts.
    version, date = page.board_facts.facts["version"], page.board_facts.facts["date"]
    assert version.y() == date.y() and version.x() < date.x()
    # The button ends the column, level with the bottom of the list.
    button = page.prepare_button.mapTo(page, page.prepare_button.rect().bottomLeft()).y()
    list_bottom = page.firmware_panel.mapTo(page, page.firmware_panel.rect().bottomLeft()).y()
    assert 0 <= list_bottom - button <= 40


def test_a_tall_side_table_shares_its_spare_height_instead_of_leaving_a_gap(qtbot, page):
    page.resize(1806, 1300)
    page.show()
    qtbot.waitExposed(page)

    def span(widget):
        top = widget.mapTo(page.side_panel, widget.rect().topLeft()).y()
        return top, top + widget.height()

    board, usb, prepare = span(page.board_facts), span(page.usb_panel), span(page.prepare_panel)
    board_to_usb, usb_to_prepare = usb[0] - board[1], prepare[0] - usb[1]
    assert abs(board_to_usb - usb_to_prepare) <= 2
    assert board_to_usb > firmware_module.SECTION_GAP, "the spare height went into the gaps"
    # Around the line under the logo there is twice the share.
    logo_to_board = board[0] - span(page.logo_panel)[1]
    assert abs(logo_to_board - 2 * board_to_usb) <= 4


def test_before_you_start_is_hidden_but_still_owned_by_the_page(page):
    assert not firmware_module.SAFETY_PANEL_SHOWN
    assert page.workspace.indexOf(page.safety_panel) == -1
    assert not page.safety_panel.isVisibleTo(page)
    assert page.safety_panel.parentWidget() is page.scroll.widget(), "never a window of its own"
    assert page.safety_panel.isAncestorOf(page.after_flash_note)
    assert page.after_flash_note.parentWidget().property("firmwareCallout") == "caution"
    assert [note.text.text() for note in page.safety_notes][1] == (
        "If something goes wrong, the same USB puts your previous BIOS back: type restore."
    )


def test_without_a_picture_the_usb_gets_the_published_image(qtbot, page):
    assert page.logo_facts.facts["file"].value.text() == "--"
    assert not page.logo_preview.showing_logo
    assert page.logo_choose.isEnabled()
    assert not page.logo_remove.isEnabled() and not page.logo_scale.isEnabled()
    assert page.step_rows["logo"].title.text() == "Add your boot logo"
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    plan, _drive = _Preparation.plans[0]
    assert plan.logo is None
    assert "Boot logo" not in dict(_Dialog.shown[0][2]["summary"])


def test_a_chosen_picture_goes_into_the_next_usb(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    assert page.logo_preview.showing_logo
    check_logo_jpeg(page._logo_jpeg)
    assert _fact(page.logo_facts, "file") == "mine.png"
    assert _fact(page.logo_facts, "source") == "400 × 200 px"
    assert _fact(page.logo_facts, "stored").startswith("672 × 378 px · JPEG · ")
    assert _fact(page.plan_facts, "firmware") == "P3.00 Chipset Menu, with your boot logo"
    assert not page.logo_note.isVisibleTo(page)
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    plan, _drive = _Preparation.plans[0]
    assert plan.logo == page._logo_jpeg
    assert plan.files[-1].logo == page._logo_jpeg
    assert plan.rom_path == "BC250/FIRMWARE/LOGO-BC250_3.00_CHIPSETMENU.ROM"
    summary = dict(_Dialog.shown[0][2]["summary"])
    assert summary["Boot logo"] == "mine.png"
    assert summary["Firmware"] == "P3.00 Chipset Menu, with your boot logo"
    assert not page.step_rows["logo"].isHidden()
    assert page.step_rows["logo"].state == "done"


def test_the_size_slider_redraws_the_logo(qtbot, page, monkeypatch, tmp_path):
    opaque = QImage(400, 200, QImage.Format.Format_RGB32)
    opaque.fill(QColor(20, 200, 40))
    assert opaque.save(str(tmp_path / "flat.png"))
    _choose(qtbot, page, monkeypatch, str(tmp_path / "flat.png"))

    def green(x, y):
        colour = page._logo_shown.pixelColor(x, y)
        return colour.green() > 150 and colour.red() < 80

    # At 100 % the 2:1 picture spans the whole width of the logo.
    assert green(20, 189)
    full = page._logo_jpeg
    page.logo_scale.setValue(40)
    assert page.logo_scale_value.text() == "40 %"
    qtbot.waitUntil(lambda: page._logo_jpeg != full, timeout=3000)
    check_logo_jpeg(page._logo_jpeg)
    # At 40 % it keeps clear of the edges and stays in the middle.
    assert not green(20, 189) and green(336, 189)


def test_removing_the_picture_goes_back_to_the_published_image(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    page.logo_scale.setValue(50)
    page.logo_remove.click()
    assert page._logo_jpeg == b"" and not page.logo_preview.showing_logo
    assert page.logo_scale.value() == 100
    assert _fact(page.plan_facts, "firmware") == "P3.00 Chipset Menu"
    assert page._logo_for_plan() is None


def test_a_file_that_is_not_a_picture_says_so_and_changes_nothing(qtbot, page, monkeypatch, tmp_path):
    fake = tmp_path / "logo.png"
    fake.write_bytes(b"not a picture at all")
    _choose(qtbot, page, monkeypatch, str(fake))
    assert page.logo_note.isVisibleTo(page)
    assert page.logo_note.property("firmwareNote") == "danger"
    assert page.logo_note.text() == "logo.png — The file is not a picture this system can read."
    assert page._logo_for_plan() is None
    assert page.logo_choose.isEnabled()


def test_a_new_file_that_fails_keeps_the_picture_already_chosen(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    kept = page._logo_jpeg
    broken = tmp_path / "broken.webp"
    broken.write_bytes(b"RIFF\x00\x00\x00\x00WEBPjunk")
    _choose(qtbot, page, monkeypatch, str(broken))
    assert page.logo_note.text().startswith("broken.webp — ")
    assert page._logo_for_plan() == kept
    assert _fact(page.logo_facts, "file") == "mine.png"
    page.logo_scale.setValue(60)
    qtbot.waitUntil(lambda: page._logo_jpeg != kept, timeout=3000)
    assert not page.logo_note.isVisibleTo(page), "a working redraw clears the old error"


def test_a_cancelled_file_dialog_changes_nothing(qtbot, page, monkeypatch):
    _choose(qtbot, page, monkeypatch, "")
    assert page._logo_picture is None and not page.logo_note.isVisibleTo(page)


def test_without_liblzma_no_logo_is_offered(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    monkeypatch.setattr(firmware_module.lzma1, "available", lambda: "liblzma 5.2.5 is too old")
    page._logo_codec = None
    page._sync_selection()
    assert not page.logo_choose.isEnabled()
    assert page.logo_note.text() == firmware_module.LOGO_CODEC_MISSING
    assert page._logo_for_plan() is None
    assert _fact(page.plan_facts, "firmware") == "P3.00 Chipset Menu"


def test_a_firmware_that_cannot_take_a_logo_gets_the_published_image(qtbot, page, monkeypatch, tmp_path):
    family = FAMILIES_BY_KEY["p5-stock"]
    monkeypatch.setitem(firmware_module.FAMILIES_BY_KEY, "p5-stock", replace(family, logo_replaceable=False))
    page.firmware_cards["p5-stock"].gamepad_activate()
    assert not page.logo_note.isVisibleTo(page), "nothing to say before a picture is chosen"
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    assert page.logo_note.text() == firmware_module.LOGO_NOT_THIS_FIRMWARE
    assert page._logo_for_plan() is None
    page.firmware_cards["p3-chipset-menu"].gamepad_activate()
    assert page._logo_for_plan() == page._logo_jpeg
    assert not page.logo_note.isVisibleTo(page)


def test_the_logo_is_locked_while_a_usb_is_prepared(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    _Preparation.behaviour = "wait-for-cancel"
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page.step_rows["download"].state == "active", timeout=5000)
    assert not page.prepare_button.isEnabled()
    assert not page.logo_choose.isEnabled()
    assert not page.logo_remove.isEnabled()
    assert not page.logo_scale.isEnabled()
    page._remove_logo()
    assert page._logo_jpeg, "the picture of a running preparation stays"
    page.cancel_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    assert page.logo_choose.isEnabled() and page.logo_remove.isEnabled()


def test_a_logo_that_cannot_be_added_says_the_usb_was_not_touched(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    _Preparation.behaviour = "fail-logo"
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    text = page.result_text.text()
    assert page.step_rows["logo"].state == "failed"
    assert "The boot logo could not be added." in text
    assert "BC250-FIRMWARE-002" in text
    assert "erased" not in text


@pytest.mark.parametrize("width", [700, 1366, 1920])
def test_the_logo_section_reflows_without_clipping(qtbot, page, monkeypatch, tmp_path, width):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    page.resize(width, 900)
    page.show()
    qtbot.waitExposed(page)
    preview = page.logo_preview
    facts = page.logo_facts

    def left(widget):
        return widget.mapTo(page.logo_panel, widget.rect().topLeft())

    # The picture beside what it is, and what changes it underneath.
    assert left(preview).y() == left(facts).y()
    assert left(preview).x() + preview.width() < left(facts).x()
    assert left(page.logo_controls).y() >= left(preview).y() + preview.height()
    assert preview.width() <= firmware_module._LogoPreview.MAX_WIDTH
    assert abs(preview.height() - preview.width() * 378 / 672) <= 1
    for widget in (page.logo_picture, page.logo_controls):
        assert widget.geometry().right() <= page.logo_panel.width()
    assert page.side_panel.geometry().right() <= page.scroll.viewport().width()


def test_a_tall_narrow_window_leaves_the_cards_at_their_own_height(qtbot, page):
    page.resize(1000, 3000)
    page.show()
    qtbot.waitExposed(page)
    qtbot.waitUntil(lambda: page.side_panel.y() > page.firmware_panel.y())
    for panel in (page.firmware_panel, page.side_panel):
        assert panel.height() <= panel.sizeHint().height() + 2, panel


def test_the_logo_section_speaks_the_chosen_language(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    try:
        set_language("es")
        localize_widget_tree(page, "es")
        page.retranslate_dynamic_copy()
        assert page.logo_choose.text() == "Elegir imagen…"
        assert page.step_rows["logo"].title.text() == "Añadir tu logo de arranque"
        assert _fact(page.plan_facts, "firmware") == "P3.00 Chipset Menu, con tu logo de arranque"
        assert page.logo_facts.facts["stored"].label.text() == "En el firmware"
        page._logo_error = "The file is not a picture this system can read."
        page._sync_logo()
        assert page.logo_note.text() == "mine.png — El archivo no es una imagen que este sistema pueda leer."
    finally:
        set_language("en")
        localize_widget_tree(page, "en")
        page.retranslate_dynamic_copy()


def test_a_usb_prepared_right_after_moving_the_slider_gets_that_size(qtbot, page, monkeypatch, tmp_path):
    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    page.logo_scale.setValue(35)
    assert page._logo_settle.isActive()
    _plug(qtbot, page, KINGSTON)
    page.prepare_button.click()
    qtbot.waitUntil(lambda: page._job is None, timeout=5000)
    plan, _drive = _Preparation.plans[0]
    expected = firmware_module.encode_logo(firmware_module.render_logo(page._logo_picture, 35))
    assert plan.logo == expected == page._logo_jpeg


@pytest.mark.parametrize("width", [760, 1000, 1280, 1500, 1920])
def test_no_wrapped_text_on_the_page_is_cut_off(qtbot, page, monkeypatch, tmp_path, width):
    """A card that is shorter than its wrapped text hides the end of it."""
    from PyQt6.QtWidgets import QLabel

    _choose(qtbot, page, monkeypatch, _picture(tmp_path))
    page._logo_error_file = "a-picture-with-a-rather-long-file-name.heic"
    page._logo_error = "The file is not a picture this system can read."
    page._sync_logo()
    page.resize(width, 900)
    page.show()
    qtbot.waitExposed(page)
    qtbot.wait(50)
    clipped = [
        (label.text()[:50], label.width(), label.height(), label.heightForWidth(label.width()))
        for label in page.findChildren(QLabel)
        if label.isVisible() and label.wordWrap() and label.width() > 0
        and label.height() < label.heightForWidth(label.width())
    ]
    assert clipped == []
