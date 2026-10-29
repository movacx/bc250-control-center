"""Compute units: the live WGP map as a grid you move through and toggle."""

from __future__ import annotations

from bc250cc.domain.compute_units import WgpMaskTable

from ..content import Choice, Field, Gap, Heading, Note, Pad, PadCell, PadRow
from ..i18n import tr
from .base import Page, guarded

WGPS = 5
FULL_MASK = (1 << WGPS) - 1
ROWS = 4
#: What each cell says: the backend's token, then what it means.
TOKEN_TONES = {"D+": "ok", "S+": "accent", "D!": "bad", "--": "dim"}


class ComputeUnitsPage(Page):
    key = "cu"
    title = "Compute units"
    interval = 4.0

    def load(self, ctx):
        # The cached state keeps this refresh off the privileged path; the
        # explicit refresh action asks the hardware again.
        return ctx.service.obtener_estado_cu_cache()

    def _live(self, data) -> list[int]:
        return [int(row.get("mask", FULL_MASK)) for row in (data or {}).get("rows") or []][:ROWS]

    def _masks(self, ctx, data) -> list[int]:
        pending = ctx.state(self.key).get("masks")
        return list(pending) if pending else self._live(data)

    def build(self, ctx, data, tab, ui):
        state = ctx.state(self.key)
        if not isinstance(data, dict) or not data.get("rows"):
            message = (data or {}).get("error") if isinstance(data, dict) else ""
            return [Note(str(message or ctx.page_error.get(self.key) or tr("Waiting for data…")), "dim"),
                    Choice(tr("Refresh"), lambda ui_: self._read_live(ctx, ui_))]
        service = ctx.service
        masks, live = self._masks(ctx, data), self._live(data)
        tokens = [list(row.get("tokens") or []) for row in data["rows"][:ROWS]]
        try:
            active = WgpMaskTable.from_values(masks).active_cus
        except ValueError:
            active = 0
        changed = masks != live
        names = [str(row.get("name") or f"SE{i // 2}.SH{i % 2}") for i, row in enumerate(data["rows"][:ROWS])]
        cursor = tuple(state.get("cursor", (0, 0)))

        def move(dr, dc):
            r, c = state.get("cursor", (0, 0))
            nr, nc = r + dr, c + dc
            if 0 <= nr < ROWS and 0 <= nc < WGPS:
                state["cursor"] = (nr, nc)
                return True
            return False  # at the edge: let the arrows leave the grid

        def toggle(ui_):
            r, c = state.get("cursor", (0, 0))
            current = self._masks(ctx, data)
            current[r] ^= 1 << c
            state["masks"] = current

        pad_rows = []
        for r, mask in enumerate(masks):
            cells = []
            for c in range(WGPS):
                on = bool(mask & (1 << c))
                token = tokens[r][c] if r < len(tokens) and c < len(tokens[r]) else ("D+" if on else "--")
                if not on:
                    cells.append(PadCell("--", tr("Not routed").upper(), "dim"))
                else:
                    cells.append(PadCell(token, tr("ROUTED"), TOKEN_TONES.get(token, "ok")))
            pad_rows.append(PadRow(names[r], cells, f"{bin(mask).count('1') * 2} / 10",
                                   "warn" if mask != live[r] else "accent"))
        headers = [f"WGP{c}" for c in range(WGPS)]
        out = [
            Heading(tr("Compute units")),
            Field(tr("Active CUs"), f"{active} / 40", "warn" if changed else "ok"),
            Field(tr("Source"), str(data.get("source") or "--")),
            Note(tr("Live only until saved") if changed else "D+ " + tr("Driver + routed") + "   S+ "
                 + tr("Live unlock") + "   D! " + tr("Driver blocked") + "   -- " + tr("Not routed"),
                 "warn" if changed else "dim"),
            Gap(),
            Pad(headers, pad_rows, cursor if cursor[0] < ROWS else (0, 0), move, toggle, "CUs"),
        ]

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

        def full(ui_):
            state["masks"] = [FULL_MASK] * ROWS

        out += [
            Gap(), Heading(tr("Actions")),
            Choice(tr("Unlock 40 CUs"), full),
            Choice(tr("Discard edits"), reset, enabled=changed),
            Choice(tr("Apply live table"), apply_live, enabled=changed, tone="warn"),
            Choice(tr("Save layout for boot"), save_boot),
            Choice(tr("Install boot restore service"), action("install_service", tr("Install boot restore service"))),
            Choice(tr("Apply saved layout"), action("apply_saved", tr("Apply saved layout"), True)),
            Choice(tr("Restore factory routing"), action("factory", tr("Restore factory routing"), True), tone="warn"),
            Choice(tr("Remove boot restore service"), action("remove_service", tr("Remove boot restore service"))),
            Choice(tr("Refresh"), lambda ui_: self._read_live(ctx, ui_)),
        ]
        return out

    def _read_live(self, ctx, ui):
        ok, result = ui.run(tr("Refresh"), ctx.service.obtener_estado_cu)
        if ok and isinstance(result, dict):
            ctx.page_data[self.key] = result
        ui.refresh()
