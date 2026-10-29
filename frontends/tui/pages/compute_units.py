"""Compute units: the WGP table, editable live, plus the boot-time actions."""

from __future__ import annotations

from bc250cc.domain.compute_units import WgpMaskTable

from ..content import Choice, Field, Gap, Heading, Note, Raw
from ..i18n import tr
from .base import Page, guarded

WGPS = 5
FULL_MASK = (1 << WGPS) - 1


def _mask_text(mask: int, cursor: int | None) -> str:
    cells = []
    for wgp in range(WGPS):
        mark = "x" if mask & (1 << wgp) else " "
        cells.append(f"[{mark}]" if cursor != wgp else f">{mark}<")
    return " ".join(cells)


class ComputeUnitsPage(Page):
    key = "cu"
    title = "Compute units"
    interval = 4.0

    def load(self, ctx):
        # The cached state keeps this refresh off the privileged path; the
        # explicit refresh action asks the hardware again.
        return ctx.service.obtener_estado_cu_cache()

    def _masks(self, ctx, data) -> list[int]:
        pending = ctx.state(self.key).get("masks")
        if pending:
            return list(pending)
        rows = (data or {}).get("rows") or []
        return [int(row.get("mask", FULL_MASK)) for row in rows][:4]

    def build(self, ctx, data, tab, ui):
        state = ctx.state(self.key)
        if not isinstance(data, dict) or not data.get("rows"):
            message = (data or {}).get("error") if isinstance(data, dict) else ""
            return [Note(str(message or ctx.page_error.get(self.key) or tr("Waiting for data…")), "dim"),
                    Choice(tr("Refresh"), lambda ui_: self._read_live(ctx, ui_))]
        service = ctx.service
        masks = self._masks(ctx, data)
        live = [int(row.get("mask", FULL_MASK)) for row in data["rows"]][:4]
        try:
            active = WgpMaskTable.from_values(masks).active_cus
        except ValueError:
            active = 0
        changed = masks != live
        names = [str(row.get("name") or f"SE{i // 2}.SH{i % 2}") for i, row in enumerate(data["rows"][:4])]
        cursor_row, cursor_col = state.get("cursor", (0, 0))

        out = [
            Heading(tr("Compute units")),
            Field(tr("Active CUs"), f"{active} / 40", "warn" if changed else "ok"),
            Field(tr("Source"), str(data.get("source") or "--")),
            *([Note(tr("Live only until saved"), "warn")] if changed else []),
            Gap(),
            Heading(tr("Current live table")),
        ]
        for index, mask in enumerate(masks):
            def toggle(ui_, index=index):
                col = state.get("cursor", (0, 0))[1] if state.get("cursor", (0, 0))[0] == index else 0
                state["cursor"] = (index, col)
                state["masks"] = [m ^ (1 << col) if i == index else m for i, m in enumerate(self._masks(ctx, data))]

            def move(ui_, delta, index=index):
                col = state.get("cursor", (0, 0))[1] if state.get("cursor", (0, 0))[0] == index else 0
                state["cursor"] = (index, max(0, min(WGPS - 1, col + delta)))

            focus = cursor_col if cursor_row == index else None
            out.append(Choice(names[index], toggle, _mask_text(mask, focus), adjust=move,
                              tone="warn" if mask != live[index] else ""))

        def reset(ui_):
            state.pop("masks", None)

        def apply_live(ui_):
            snapshot = list(masks)
            if ui_.confirm(f"{tr('Apply live table')}: {active} / 40", danger=True):
                guarded(ui_, tr("Apply"), lambda: service.aplicar_tabla_cu(snapshot))
                state.pop("masks", None)

        def save_boot(ui_):
            snapshot = list(masks)
            if ui_.confirm(tr("Save layout for boot"), danger=True):
                guarded(ui_, tr("Save layout for boot"), lambda: service.guardar_tabla_cu(snapshot))

        def action(name, label, danger=False):
            def handler(ui_):
                if ui_.confirm(label, danger=danger):
                    guarded(ui_, label, lambda: service.ejecutar_accion_cu_grafica(name))
                    state.pop("masks", None)
            return handler

        out += [
            Gap(),
            Heading(tr("Actions")),
            Choice(tr("Discard edits"), reset, enabled=changed),
            Choice(tr("Apply live table"), apply_live, enabled=changed, tone="warn"),
            Choice(tr("Save layout for boot"), save_boot),
            Choice(tr("Restore factory routing"), action("factory", tr("Restore factory routing"), True)),
            Choice(tr("Apply saved layout"), action("apply_saved", tr("Apply saved layout"), True)),
            Choice(tr("Install boot restore service"), action("install_service", tr("Install boot restore service"))),
            Choice(tr("Remove boot restore service"), action("remove_service", tr("Remove boot restore service"))),
            Choice(tr("Refresh"), lambda ui_: self._read_live(ctx, ui_)),
        ]
        raw = str(data.get("raw") or "").splitlines()
        if raw:
            out += [Gap(), Heading(tr("Live Dispatch")), Raw(raw, "dim")]
        return out

    def _read_live(self, ctx, ui):
        def read():
            return ctx.service.obtener_estado_cu()

        ok, result = ui.run(tr("Refresh"), read)
        if ok and isinstance(result, dict):
            ctx.page_data[self.key] = result
        ui.refresh()
