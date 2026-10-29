"""Fans: sensors, PWM duty and who owns the fan, like the desktop Fans page."""

from __future__ import annotations

from ..content import Choice, Field, Gap, Heading, Meter, Note, number
from ..i18n import tr
from .base import Page, guarded


class FansPage(Page):
    key = "fans"
    title = "Fans"
    interval = 2.0

    def load(self, ctx):
        service = ctx.service
        fans = service.estado_fans_bc250()
        try:
            system = service.estado_control_fan_sistema()
        except Exception:
            system = {}
        return {"fans": fans, "system": system}

    def build(self, ctx, data, tab, ui):
        data = data or {}
        sensors = (data.get("fans") or {}).get("sensores") or {}
        rows = [row for row in sensors.get("fans") or [] if isinstance(row, dict)]
        system = data.get("system") or {}
        service = ctx.service
        out = [Heading(tr("Fans"))]
        if sensors.get("chip"):
            out.append(Field(tr("NCT chip"), str(sensors["chip"])))
        out.append(Field(
            tr("Service"),
            str(system.get("state") or "--"),
            "ok" if system.get("enabled") else "",
        ))
        if not rows:
            out.append(Note(tr("Not detected"), "warn"))
        for row in rows:
            pwm = row.get("pwm")
            try:
                duty = max(0, min(100, round(int(pwm) * 100 / 255)))
            except (TypeError, ValueError):
                duty = None
            out.append(Meter(str(row.get("label") or f"PWM{row.get('index', '?')}"),
                             None if duty is None else duty / 100.0,
                             f"{number(row.get('rpm'), 'RPM')}  {duty if duty is not None else '--'} %"))
        out += [Gap(), Heading(tr("Actions"))]
        for row in rows:
            index = row.get("index")
            label = str(row.get("label") or f"PWM{index}")

            def set_duty(ui_, index=index, label=label):
                percent_value = ui_.ask_int(f"{label} (%)", 0, 100, 60)
                if percent_value is None:
                    return
                pwm_value = round(percent_value * 255 / 100)
                if ui_.confirm(f"{tr('Apply PWM')}: {label} {percent_value} %", danger=percent_value < 25):
                    guarded(ui_, label, lambda: service.aplicar_pwm_fan(index, pwm_value))

            def automatic(ui_, index=index, label=label):
                if ui_.confirm(f"{label} · {tr('Automatic')}"):
                    guarded(ui_, label, lambda: service.restaurar_pwm_automatico(index))

            out.append(Choice(f"{tr('Apply PWM')} · {label}", set_duty,
                              enabled=bool(row.get("pwm_root_writable") or row.get("pwm_writable"))))
            out.append(Choice(f"{label} · {tr('Automatic')}", automatic))
        return out
