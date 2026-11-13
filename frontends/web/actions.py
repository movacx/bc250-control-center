"""The closed list of things the web interface may do.

Each entry validates its own parameters and returns ``(level, work)``: the
confirmation it needs (0 none, 1 explicit confirmation, 2 risk-zone confirmation) and the call to run. ``work`` only calls
the service layer the desktop and the terminal interface use; nothing here
builds a command line from the request.
"""

from __future__ import annotations

import json

from bc250cc.application.fan import board_view
from bc250cc.application.fan.board_actions import (
    FanBoardActions,
    FanBoardError,
    Outcome,
)
from bc250cc.application.fan.system_control import build_system_fan_policy
from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.application.gpu.voltage_lab_state import build_voltage_lab_state
from bc250cc.domain.fan import engine
from bc250cc.domain.fan.channels import LABEL_MAX_LENGTH, MODE_NAME_MAX_LENGTH
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
)
from bc250cc.shared.contract import (
    CPU_FREQUENCY_RANGE,
    CPU_SCALE_RANGE,
    CPU_TEMPERATURE_RANGE,
    CPU_VID_RANGE,
)
from frontends.tui.i18n import tr, tr_format

SAFE_CEILING = 2000  # past the factory TOML's last point the rail turns red
LOW_DUTY = board_view.LOW_DUTY_CONFIRM_PERCENT
ENTRY_MAX_BYTES = 4096  # a channel entry: at most 4 mix curves of 8 points
RANGES = {"frequency": CPU_FREQUENCY_RANGE, "vid": CPU_VID_RANGE, "temperature": CPU_TEMPERATURE_RANGE, "scale": CPU_SCALE_RANGE,
          "gpu": (300, 3000), "pwm": (engine.PWM_MIN, engine.PWM_MAX), "percent": (0, 100), "level": (0, 6)}
SET_METHODS, USAGE_METHODS, TEMP_READS = ("smu", "kernel"), ("busy-flag", "process", "kernel"), ("drm", "sysfs")
GOVERNOR_ACTIONS = ("reiniciar", "activar", "desactivar")
CU_ACTIONS = ("install_service", "remove_service", "factory")


class Invalid(ValueError):
    """The request does not fit the list: nothing runs."""


def number(p: dict, key: str, bounds: str | None = None) -> int:
    low, high = RANGES[bounds or key]
    value = p.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Invalid(key)
    return value


def flag(p: dict, key: str) -> bool:
    if not isinstance(p.get(key), bool):
        raise Invalid(key)
    return p[key]


def choice(p: dict, key: str, options: tuple) -> str:
    if p.get(key) not in options:
        raise Invalid(key)
    return p[key]


def masks(p: dict) -> list[int]:
    value = p.get("masks")
    if not (isinstance(value, list) and len(value) == 4
            and all(isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 31 for item in value)):
        raise Invalid("masks")
    return value


# -- GPU ------------------------------------------------------------------------------------------

def gpu_profile(ctx, p, shell):
    low, high = number(p, "min", "gpu"), number(p, "max", "gpu")
    if low > high:
        raise Invalid("max")
    return (2 if high > SAFE_CEILING else 1), lambda: ctx.service.aplicar_perfil_gpu(low, high)


def gpu_compat(ctx, p, shell):
    args = (choice(p, "set_method", SET_METHODS), choice(p, "usage_method", USAGE_METHODS),
            flag(p, "metrics"), flag(p, "frequencies"), choice(p, "temp_read", TEMP_READS))
    return (2 if args[0] == "kernel" else 1), lambda: ctx.service.configurar_compatibilidad_gpu_cyan(*args)


def gpu_service(ctx, p, shell):
    action = choice(p, "action", GOVERNOR_ACTIONS)
    return (2 if action == "desactivar" else 1), lambda: ctx.service.controlar_governor(action)


def gpu_high_points(ctx, p, shell):
    enable = flag(p, "enable")
    return 2, lambda: ctx.service.alternar_puntos_gpu_altos(enable)


def gpu_voltage(ctx, p, shell):
    level = number(p, "level")
    return 2, lambda: ctx.service.aplicar_laboratorio_voltaje_gpu(level)


def gpu_voltage_custom(ctx, p, shell):
    values = p.get("values")
    if not isinstance(values, dict) or not 1 <= len(values) <= 64:
        raise Invalid("values")
    normalized = {}
    for frequency, voltage in values.items():
        if (not isinstance(frequency, str) or len(frequency) > 4 or not frequency.isascii() or not frequency.isdecimal()
                or str(int(frequency)) != frequency or not 300 <= int(frequency) <= 3000
                or isinstance(voltage, bool) or not isinstance(voltage, int)
                or not CUSTOM_VOLTAGE_MIN_MV <= voltage <= CUSTOM_VOLTAGE_MAX_MV):
            raise Invalid("values")
        normalized[int(frequency)] = voltage

    def apply():
        lab = build_voltage_lab_state(ctx.service.estado_bc250())
        if lab.is_oberon or not set(normalized).issubset(lab.editable_frequencies):
            raise Invalid("active voltage points")
        plan = plan_voltage_apply(level=-1, editable_frequencies=lab.editable_frequencies,
                                  profile_frequencies=lab.profile_frequencies,
                                  current_voltages=dict(lab.current_voltages), custom_values=normalized)
        if not plan.available or plan.violation:
            raise Invalid("voltage curve")
        return ctx.service.aplicar_laboratorio_voltaje_gpu_personalizado(normalized)
    return 2, apply


# -- GDDR6: preparation is explicit; one native helper owns a bounded session.

def gddr6_monitor(ctx, p, shell):
    if p:
        raise Invalid("params")

    def monitor():
        from frontends.web.gddr6 import readiness
        state = readiness(ctx.service)
        if not state["can_monitor"]:
            raise Invalid(state["blocker"] or "GDDR6 monitor unavailable")
        return shell(ctx.service.comando_monitorizar_vram(state["session_seconds"]))
    return 2, monitor


# -- CPU ------------------------------------------------------------------------------------------

def cpu_apply(ctx, p, shell):
    frequency, temperature = number(p, "frequency"), number(p, "temperature")
    manual = flag(p, "manual")
    value = number(p, "scale" if manual else "vid")
    target = {"frequency": frequency, "temperature": temperature,
              "manual_scale" if manual else "vid": value}

    def apply():
        # Both paths run the protected, stress-tested command synchronously.
        # A dependency-installation workflow is not a completed detection run.
        command = (ctx.service.comando_cpu_oc_manual_verificado_embebido(
            frequency, value, temperature, confirm_manual=True) if manual else
            ctx.service.comando_cpu_oc_temporal_embebido(frequency, value, temperature))
        shell(command)  # Failure/cancellation must never bind old config evidence.
        try:
            snapshot = ctx.service.registrar_resultado_deteccion_cpu(target)
            # The detector can lower the requested frequency after throttling.
            ctx.settings.save_local_config({"cpu_oc_last_applied_frequency": int(snapshot["frequency"])})
        except Exception as error:
            # The hardware operation already succeeded. Do not rerun it or
            # report a rollback when only the local evidence failed to save.
            return tr_format("Warning: the completed detection run could not be bound to persistence: {message}",
                             message=str(error))
        return tr_format("Recorded detection run: {frequency} MHz | scale {scale} | {temperature} °C",
                         frequency=snapshot["frequency"], scale=snapshot["scale"], temperature=snapshot["temperature"])

    return 1, apply


def cpu_unlock(ctx, p, shell):
    force = flag(p, "force_mask")
    return 2, lambda: shell(ctx.service.comando_desbloquear_nucleos_cpu(ignore_core_mask=force))


# -- Compute units --------------------------------------------------------------------------------

def cu_apply(ctx, p, shell):
    table = masks(p)
    return 2, lambda: ctx.service.aplicar_tabla_cu(table)


def cu_save(ctx, p, shell):
    table = masks(p)
    return 1, lambda: ctx.service.guardar_tabla_cu(table)


def cu_action(ctx, p, shell):
    name = choice(p, "name", CU_ACTIONS)
    return (2 if name == "factory" else 1), lambda: ctx.service.ejecutar_accion_cu_grafica(name)


# -- Fans -----------------------------------------------------------------------------------------

def _said(outcome: Outcome) -> str:
    """An outcome as the sentence the job log shows."""
    message = tr_format(outcome.message, **outcome.values) if outcome.values else tr(outcome.message)
    return f"{tr(outcome.title)} · {message}"


def _board(ctx) -> FanBoardActions:
    return FanBoardActions(ctx.service, ctx.settings)


def _entry(p: dict) -> dict | None:
    """A channel setting as the engine reads it; the engine itself decides
    whether it is valid, here only its shape and size are checked."""
    entry = p.get("entry")
    if entry is None:
        return None
    if not isinstance(entry, dict) or entry.get("mode") not in engine.MODES:
        raise Invalid("entry")
    try:
        size = len(json.dumps(entry))
    except (TypeError, ValueError) as error:
        raise Invalid("entry") from error
    if size > ENTRY_MAX_BYTES:
        raise Invalid("entry")
    if entry["mode"] == "firmware":
        return None
    try:
        engine.validate_policy({"schema": 2, "channels": {"1": entry}})
    except ValueError as error:
        raise Invalid(f"entry: {error}") from error
    return entry


def _text(p: dict, key: str, limit: int, *, empty: bool = False) -> str:
    value = p.get(key)
    if not isinstance(value, str) or len(value) > limit * 4:
        raise Invalid(key)
    text = " ".join(value.split())[:limit]
    if not text and not empty:
        raise Invalid(key)
    return text


def fan_channel(ctx, p, shell):
    """One channel's setting (Firmware, Fixed, Curve or Mix), as the desktop
    Fans page applies it."""
    pwm, entry = number(p, "pwm"), _entry(p)
    low = bool(entry and entry.get("mode") == "fixed" and int(entry.get("percent", 100)) < LOW_DUTY)
    return (2 if low else 1), lambda: _said(_board(ctx).apply_channel(pwm, entry))


def fan_label(ctx, p, shell):
    pwm, label = number(p, "pwm"), _text(p, "label", LABEL_MAX_LENGTH, empty=True)

    def rename():
        _board(ctx).rename(pwm, label)
        return tr("Saved")
    return 0, rename


def fan_profile(ctx, p, shell):
    """Apply, save or delete a fan profile (the desktop's named modes)."""
    operation = choice(p, "operation", ("apply", "save", "delete"))
    name = _text(p, "name", MODE_NAME_MAX_LENGTH)
    if operation == "apply":
        selected = number(p, "selected", "pwm") if p.get("selected") is not None else None
        return 1, lambda: _said(_board(ctx).apply_profile(name, selected))
    if operation == "delete":
        def delete():
            _board(ctx).delete_profile(name)
            return tr("Saved")
        return 1, delete
    channels = None
    if p.get("draft") is not None:
        # The visible draft of one channel, saved with the others, never applied.
        draft = p["draft"]
        if not isinstance(draft, dict):
            raise Invalid("draft")
        pwm, entry = number(draft, "pwm"), _entry(draft)
        channels = dict(_board(ctx).board().channels)
        if entry is None:
            channels.pop(str(pwm), None)
        else:
            channels[str(pwm)] = entry
    replace = flag(p, "replace") if "replace" in p else False

    def save():
        board = _board(ctx)
        if board.profile_exists(name) and not replace:
            raise FanBoardError("Save as…", "Replace fan profile?", notice=True)
        board.save_profile(name, channels=channels, reserved=[tr(label) for label in ("Quiet", "Balanced", "Performance")])
        return f"{tr('Saved')} · {name}"
    return 1, save


def fan_service(ctx, p, shell):
    operation = choice(p, "operation", ("enable", "disable", "sync"))

    def apply():
        state = ctx.service.estado_control_fan_sistema()
        if not isinstance(state, dict) or state.get("external"):
            raise Invalid("The fan is handed to another program")
        if operation == "disable":
            return ctx.service.desactivar_control_fan_sistema()
        if not state.get("available") and not state.get("enabled"):
            raise Invalid("Fan service unavailable")
        policy = build_system_fan_policy(ctx.settings.read_local_config())
        if policy is None:
            raise Invalid("Choose a curve or a preset first")
        if not board_view.policy_supported(state, policy):
            raise FanBoardError(board_view.NOT_READY_TITLE, "Update fan helper", notice=True)
        if operation == "sync":
            if not state.get("enabled"):
                raise Invalid("Enable the fan service first")
            return ctx.service.sincronizar_control_fan_sistema(policy)
        return ctx.service.activar_control_fan_sistema(policy)
    return 1, apply


ACTIONS = {
    "gddr6.monitor": gddr6_monitor,
    "gddr6.prepare": lambda ctx, p, shell: (1, ctx.service.comando_preparar_gddr6_memory_temp),
    "gpu.profile": gpu_profile, "gpu.compat": gpu_compat, "gpu.service": gpu_service,
    "gpu.high_points": gpu_high_points, "gpu.voltage": gpu_voltage, "gpu.voltage_custom": gpu_voltage_custom,
    "gpu.save_boot": lambda ctx, p, shell: (1, ctx.service.guardar_rango_gpu_arranque),
    "gpu.status": lambda ctx, p, shell: (0, ctx.service.status_governor),
    "cpu.apply": cpu_apply, "cpu.unlock": cpu_unlock,
    "cpu.persist": lambda ctx, p, shell: (1, lambda: shell(ctx.service.comando_cpu_oc_persistente_embebido())),
    "cpu.persist_off": lambda ctx, p, shell: (
        1, lambda: shell(ctx.service.comando_cpu_oc_desactivar_persistente_embebido())),
    "cu.sync": lambda ctx, p, shell: (0, ctx.service.obtener_estado_cu),
    "cu.apply": cu_apply, "cu.save": cu_save, "cu.action": cu_action,
    "fan.channel": fan_channel, "fan.label": fan_label, "fan.profile": fan_profile, "fan.service": fan_service,
}
