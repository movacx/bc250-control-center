"""Firmware (BIOS): the board, the catalog and the USB update kit."""

from __future__ import annotations

from bc250cc.application.firmware import firmware_snapshot, prepare_update_usb
from bc250cc.domain.firmware.catalog import FIRMWARE_FAMILIES
from bc250cc.domain.firmware.usb import format_size

from ..content import Choice, Field, Gap, Heading, Note
from ..i18n import tr
from .base import Page, guarded


class FirmwarePage(Page):
    key = "firmware"
    title = "Firmware"
    interval = 6.0

    def load(self, ctx):
        snapshot = firmware_snapshot()
        return {"board": snapshot.board, "installed": snapshot.installed, "drives": list(snapshot.drives)}

    def build(self, ctx, data, tab, ui):
        if not data:
            return [Note(ctx.page_error.get(self.key) or tr("Waiting for data…"), "dim")]
        board, installed, drives = data["board"], data["installed"], data["drives"]
        out = [
            Heading(tr("Firmware")),
            Field(tr("Board"), board.board or "--", "ok" if board.is_bc250 else "warn"),
            Field(tr("Vendor"), board.vendor or "--"),
            Field(tr("Version"), f"{board.version or '--'}  {board.date}".strip()),
        ]
        if installed.variant:
            out.append(Field(tr("Firmware"), installed.variant))
        if installed.evidence:
            out.append(Note(installed.evidence, "dim"))
        out += [Gap(), Heading(tr("USB drives"))]
        if not drives:
            out.append(Note(tr("Not detected"), "dim"))
        for drive in drives:
            blocker = drive.blocker()
            out.append(Field(drive.display_name, f"{format_size(drive.size)}  {tr(blocker) if blocker else tr('Ready')}",
                             "bad" if blocker else "ok"))
        out += [Gap(), Heading(tr("Erase and prepare"))]
        for family in FIRMWARE_FAMILIES:
            def prepare(ui_, family=family):
                self._prepare(ctx, ui_, family, drives)

            out.append(Choice(family.title, prepare, tr("Recommended") if family.recommended else "",
                              tone="ok" if family.recommended else ""))
        return out

    def _prepare(self, ctx, ui, family, drives):
        eligible = [drive for drive in drives if drive.eligible]
        if not eligible:
            ui.notify(tr("Not detected"), "warn")
            return
        image = family.image()
        if family.has_variants:
            key = ui.choose(family.variant_title or tr("Firmware"),
                            [(item.key, item.label) for item in family.images])
            if key is None:
                return
            image = family.image(key)
        drive = ui.choose(tr("USB drives"), [(item, f"{item.display_name}  {format_size(item.size)}") for item in eligible])
        if drive is None:
            return
        note = f"{family.caution}\n\n" if family.caution else ""
        if not ui.confirm(
            f"{note}{tr('Erase this USB drive?')}\n{drive.display_name}\n\n"
            + tr("Everything on it will be erased and replaced by the BIOS update kit. This cannot be undone."),
            danger=True,
        ):
            return
        def work():
            def progress(step, fraction, detail):
                print(f"{step:<8} {fraction * 100:5.1f} %  {detail}", flush=True)

            report, _steps = prepare_update_usb(family, image, drive, progress=progress)
            return f"{tr('Done')}: {report.files} · {format_size(report.bytes_written)}"

        guarded(ui, family.title, work)
