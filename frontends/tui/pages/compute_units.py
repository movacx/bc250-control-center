"""Compute units, laid out as the desktop's: the WGP grid, the target and its actions, then telemetry."""

from __future__ import annotations

from bc250cc.domain.compute_units import WgpMaskTable
from frontends.desktop.core.cu_balance import engine_balance
from frontends.desktop.i18n import count_label

from ..compact import terminal_form
from ..content import (
    Buttons,
    Choice,
    Field,
    Grid,
    Legend,
    Note,
    Pad,
    PadCell,
    PadRow,
    Panel,
)
from ..i18n import tr, tr_format
from .base import Page, guarded

WGPS = 5
FULL_MASK = (1 << WGPS) - 1
ROWS = 4
#: What each cell says: the backend's token, then what it means.
TOKEN_TONES = {"D+": "ok", "S+": "accent", "D!": "bad", "--": "dim"}
LEGEND = (("D+", "Driver + routed"), ("S+", "Live unlock"), ("D!", "Driver blocked"), ("--", "Not routed"))


class ComputeUnitsPage(Page):
    key = "cu"
    title = "Compute Units"
    interval = 4.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in (("routing", "Live routing"),
                ("registers", "Register diagnostics"), ("boot", "Boot persistence"))]

    def load(self, ctx):
        # The cached state keeps this refresh off the privileged path; Unlock / Sync asks the hardware again.
        return {"cu": ctx.service.obtener_estado_cu_cache()}

    @staticmethod
    def _live(data) -> list[int]:
        return [int(row.get("mask", FULL_MASK)) for row in (data or {}).get("rows") or []][:ROWS]

    def _masks(self, ctx, data) -> list[int]:
        pending = ctx.state(self.key).get("masks")
        return list(pending) if pending else self._live(data)

    def build(self, ctx, data, tab, ui):
        state, service = ctx.state(self.key), ctx.service
        data = (data or {}).get("cu") if isinstance(data, dict) else None
        if not isinstance(data, dict) or not data.get("rows"):
            message = (data or {}).get("error") if isinstance(data, dict) else ""
            return [Note(str(message or ctx.page_error.get(self.key) or tr("Waiting for data…")), "dim"),
                    Buttons([Choice(tr("Unlock / Sync"), lambda ui_: self._read_live(ctx, ui_), tone="primary")])]
        masks, live = self._masks(ctx, data), self._live(data)
        rows = data["rows"][:ROWS]
        try:
            active = WgpMaskTable.from_values(masks).active_cus
        except ValueError:
            active = 0
        pending = sum(bin(a ^ b).count("1") for a, b in zip(masks, live))
        ready = bool(data.get("privileged_backend_ready"))

        # -- the grid: move with the arrows or tap a cell; Enter toggles a WGP pair
        def move(dr, dc):
            r, c = state.get("cursor", (0, 0))
            if 0 <= r + dr < ROWS and 0 <= c + dc < WGPS:
                state["cursor"] = (r + dr, c + dc)
                return True
            return False  # at the edge: let the arrows leave the grid

        def toggle(ui_):
            r, c = state.get("cursor", (0, 0))
            current = self._masks(ctx, data)
            current[r] ^= 1 << c
            state["masks"] = current

        pad_rows = []
        for r, mask in enumerate(masks):
            tokens = list(rows[r].get("tokens") or []) if r < len(rows) else []
            cells = []
            for c in range(WGPS):
                on, was = bool(mask & (1 << c)), bool(live[r] & (1 << c)) if r < len(live) else True
                token = tokens[c] if on and was and c < len(tokens) else ("S+" if on else "--")
                tone = "warn" if on != was else TOKEN_TONES.get(token, "ok") if on else "dim"
                cells.append(PadCell(token, tone))
            pad_rows.append(PadRow(str(rows[r].get("name") if r < len(rows) else f"SE{r // 2}.SH{r % 2}"), cells,
                                   f"{bin(mask).count('1') * 2}/10", "warn" if r < len(live) and mask != live[r] else "accent"))
        grid = Panel(tr("Compute Units"), [
            Legend([(token, tr(label), TOKEN_TONES[token]) for token, label in LEGEND]),
            Pad([f"WGP{c}\n{2 * c}-{2 * c + 1}" for c in range(WGPS)], pad_rows,
                tuple(state.get("cursor", (0, 0))), move, toggle, "CU\n/10",
                place=lambda r, c: state.update(cursor=(r, c)), corner="SE/SH")],
            badge=str(data.get("mode") or ""), badge_tone="accent")

        # -- the target and what to do with it
        def apply_live(ui_):
            snapshot = list(masks)
            if ui_.confirm(f"{tr('Apply live table')}: {active} / 40", danger=True):
                if guarded(ui_, tr("Apply now"), lambda: service.aplicar_tabla_cu(snapshot)):
                    state.pop("masks", None)

        def save(ui_):
            snapshot = list(masks)
            if ui_.confirm(tr("Save selection"), danger=True):
                guarded(ui_, tr("Save selection"), lambda: service.guardar_tabla_cu(snapshot))

        def action(name, label, danger=False):
            def handler(ui_):
                if ui_.confirm(tr(label), danger=danger):
                    if guarded(ui_, tr(label), lambda: service.ejecutar_accion_cu_grafica(name)):
                        state.pop("masks", None)
            return handler

        balance = engine_balance(masks)
        detail = (tr("CU write actions are locked until a verified root-owned backend is installed.") if not ready
                  else tr_format("{pairs} differ from the last authorized live table.",
                                 pairs=count_label(pending, "WGP pair")) if pending else tr("No pending WGP changes."))
        spread = tr_format("SE0 {se0} · SE1 {se1} CUs — balanced: every active CU adds performance.",
                           se0=balance.se0, se1=balance.se1) if balance.balanced else tr_format(
            "SE0 {se0} · SE1 {se1} CUs — unbalanced: performs like {effective} CUs; {idle} CUs on the stronger engine "
            "only add heat.", se0=balance.se0, se1=balance.se1, effective=balance.effective, idle=balance.idle)
        target = Panel(tr_format("Target: {count} / 40 CUs", count=active), [
            Note(detail, "warn" if pending else "dim"), Note(spread, "dim" if balance.balanced else "warn"),
            Buttons([Choice(tr("Unlock / Sync"), lambda ui_: self._read_live(ctx, ui_)),
                     Choice(tr("Reset selection"), lambda ui_: state.pop("masks", None), enabled=bool(pending)),
                     Choice(tr("Apply now"), apply_live, tone="primary", enabled=bool(pending) and ready)])])

        shown = state.get("registers", False)
        persistence = Panel(tr("Boot persistence"), [
            Field(tr("Target"), f"{active}/40 CUs"),
            Note(tr("Select the WGP pairs above, then use the buttons below in order — Apply now, Save selection, "
                    "Install service — to make the change survive a reboot."), "dim"),
            Buttons([Choice(tr("Save selection"), save, enabled=ready),
                     Choice(tr("Install service"), action("install_service", "Install service"), enabled=ready),
                     Choice(tr("Remove service"), action("remove_service", "Remove service", True), tone="bad",
                            enabled=bool(data.get("service_installed"))),
                     Choice(tr("Restore factory"), action("factory", "Restore factory", True), enabled=ready),
                     Choice(tr("Raw status"), lambda ui_: ui_.show_text(tr("Raw status"), str(data.get("raw") or "--"))),
                     Choice(tr("Hide registers" if shown else "Show registers"),
                            lambda ui_: state.update(registers=not shown))])])
        left = [target, persistence, Note(tr(
            "Live routing is temporary until the current table is saved and the boot service is installed. One WGP "
            "always represents two CUs; individual CUs cannot be toggled separately."), "dim")]
        if shown or tab == "registers":
            left.append(Panel(tr("Register diagnostics"), [Grid(["SE/SH", "SPI", "CC", "driver", tr("Target")], [
                [str(row.get("name")), str(row.get("spi")), str(row.get("cc")), f"0x{int(row.get('driver_mask', 0)):02x}",
                 f"0x{masks[index]:02x}"] for index, row in enumerate(rows)])]))

        if tab == "boot":
            return terminal_form([persistence, left[2]])
        if tab == "registers":
            return terminal_form([left[-1], Field(tr("Source"), str(data.get("source") or "--")),
                                  Choice(tr("Raw status"), lambda ui_: ui_.show_text(
                                      tr("Raw status"), str(data.get("raw") or "--")))])
        return terminal_form([grid, target, Note("↑↓ ←→ · Space / Enter · Tab", "dim")])

    def _read_live(self, ctx, ui):
        ok, result = ui.run(tr("Unlock / Sync"), ctx.service.obtener_estado_cu)
        if ok and isinstance(result, dict):
            ctx.page_data[self.key] = {**(ctx.page_data.get(self.key) or {}), "cu": result}
        ui.refresh()
