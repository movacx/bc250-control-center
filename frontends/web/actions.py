"""The closed list of things the web interface may do.

Each entry validates its own parameters and returns ``(level, work)``: the
confirmation it needs (0 none, 1 explicit confirmation, 2 risk-zone confirmation) and the call to run. ``work`` only calls
the service layer the desktop and the terminal interface use; nothing here
builds a command line from the request.
"""

from __future__ import annotations

from bc250cc.application.fan.system_control import build_system_fan_policy
from bc250cc.domain.fan.persistence import (
    CUSTOM_FAN_PRESET,
    normalize_fan_curve,
    validate_fan_curve_points,
)
from bc250cc.shared.contract import (
    CPU_FREQUENCY_RANGE,
    CPU_SCALE_RANGE,
    CPU_TEMPERATURE_RANGE,
    CPU_VID_RANGE,
)

SAFE_CEILING = 2000  # past the factory TOML's last point the rail turns red
LOW_DUTY = 30
RANGES = {"frequency": CPU_FREQUENCY_RANGE, "vid": CPU_VID_RANGE, "temperature": CPU_TEMPERATURE_RANGE, "scale": CPU_SCALE_RANGE,
          "gpu": (300, 3000), "pwm": (1, 8), "percent": (0, 100), "level": (0, 3)}
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


def to_pwm(percent: int) -> int:
    return round(percent * 255 / 100)


def _fan_save(ctx, payload: dict, first=None) -> str:
    """A PWM write, the saved fan settings, then the new policy to the root service when it is on."""
    service = ctx.service
    if first is not None:
        first()
    ctx.settings.save_local_config(payload)
    system = service.estado_control_fan_sistema()
    if isinstance(system, dict) and system.get("enabled"):
        policy = build_system_fan_policy(ctx.settings.read_local_config())
        if policy is not None:
            service.sincronizar_control_fan_sistema(policy)
    return ""


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


# -- CPU ------------------------------------------------------------------------------------------

def cpu_apply(ctx, p, shell):
    frequency, temperature = number(p, "frequency"), number(p, "temperature")
    if flag(p, "manual"):
        scale = number(p, "scale")
        return 1, lambda: shell(ctx.service.comando_cpu_oc_manual_verificado_embebido(
            frequency, scale, temperature, confirm_manual=True))
    vid = number(p, "vid")
    return 1, lambda: ctx.service.ejecutar_cpu_oc_temporal(frequency, vid, temperature)


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

def fan_pwm(ctx, p, shell):
    pwm, percent = number(p, "pwm"), number(p, "percent")
    curve = normalize_fan_curve(ctx.settings.read_local_config().get("fan_curve"))
    payload = {"fan_curve": dict(curve, enabled=False), "fan_preset": {
        "enabled": True, "preset": CUSTOM_FAN_PRESET, "percent": percent, "pwm": pwm}}
    return (2 if percent < LOW_DUTY else 1), lambda: _fan_save(
        ctx, payload, lambda: ctx.service.aplicar_pwm_fan(pwm, to_pwm(percent)))


def fan_auto(ctx, p, shell):
    pwm = number(p, "pwm")
    return 1, lambda: ctx.service.restaurar_pwm_automatico(pwm)


def fan_curve(ctx, p, shell):
    pwm, enabled = number(p, "pwm"), flag(p, "enabled")
    raw = p.get("points")
    if not (isinstance(raw, list) and 2 <= len(raw) <= 8 and all(
            isinstance(item, list) and len(item) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in item)
            and 20 <= item[0] <= 110 and 0 <= item[1] <= 100 for item in raw)):
        raise Invalid("points")
    points = sorted((t, s) for t, s in raw)
    ok, _message = validate_fan_curve_points(points)
    if not ok:
        raise Invalid("points")
    saved = normalize_fan_curve(ctx.settings.read_local_config().get("fan_curve"))
    body = {"enabled": enabled, "edit_enabled": enabled, "pwm": pwm, "point_count": len(points),
            "points": [{"temperature": t, "speed": s} for t, s in points],
            "preset": saved.get("preset", "custom"), "last_pwm_text": saved.get("last_pwm_text", "--")}
    for index, (t, s) in enumerate(points[:3], start=1):  # the legacy daemon's keys
        body[f"t{index}"], body[f"s{index}"] = t, s
    payload = {"fan_curve": body}
    if enabled:
        payload["fan_preset"] = {"enabled": False, "preset": "", "percent": 0, "pwm": pwm}
    return 1, lambda: _fan_save(ctx, payload)


ACTIONS = {
    "gpu.profile": gpu_profile, "gpu.compat": gpu_compat, "gpu.service": gpu_service,
    "gpu.high_points": gpu_high_points, "gpu.voltage": gpu_voltage,
    "gpu.save_boot": lambda ctx, p, shell: (1, ctx.service.guardar_rango_gpu_arranque),
    "gpu.status": lambda ctx, p, shell: (0, ctx.service.status_governor),
    "cpu.apply": cpu_apply, "cpu.unlock": cpu_unlock,
    "cpu.persist": lambda ctx, p, shell: (1, lambda: shell(ctx.service.comando_cpu_oc_persistente_embebido())),
    "cpu.persist_off": lambda ctx, p, shell: (
        1, lambda: shell(ctx.service.comando_cpu_oc_desactivar_persistente_embebido())),
    "cu.sync": lambda ctx, p, shell: (0, ctx.service.obtener_estado_cu),
    "cu.apply": cu_apply, "cu.save": cu_save, "cu.action": cu_action,
    "fan.pwm": fan_pwm, "fan.auto": fan_auto, "fan.curve": fan_curve,
}
