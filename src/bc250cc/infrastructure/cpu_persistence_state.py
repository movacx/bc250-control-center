"""Pure systemd classification for the persistent CPU OC one-shot service."""


def _normalized(value, default=""):
    return str(value if value is not None else default).strip().lower()


def _service_evidence(enabled, active_state, result, exec_status, status_text, config_exists):
    successful_result = result in {"", "success"}
    successful_exit = exec_status in {"", "0"}
    status_confirms_success = "status=0/success" in status_text.lower() or exec_status == "0"
    oneshot_ok = bool(
        enabled == "enabled"
        and active_state == "inactive"
        and successful_result
        and successful_exit
        and status_confirms_success
    )
    applied = bool(
        active_state == "active"
        or oneshot_ok
        or (
            enabled == "enabled"
            and bool(config_exists)
            and successful_result
            and active_state != "failed"
        )
    )
    return oneshot_ok, applied, successful_result


def _service_presentation(enabled, active_state, result, oneshot_ok, successful_result):
    if active_state == "failed" or not successful_result:
        return "Failed", f"Result {result or active_state}"
    if oneshot_ok:
        return "Applied / enabled", "One-shot finished successfully; it will repeat at boot"
    if active_state == "active":
        return ("Active / enabled" if enabled == "enabled" else "Active"), "Running now"
    if enabled == "enabled":
        return "Ready / enabled", "Enabled for next boot"
    return "Disabled", "Does not start automatically"


def classify_cpu_persistence_service(enabled, active_fallback, properties, status_text, config_exists):
    properties = dict(properties) if isinstance(properties, dict) else {}
    enabled = _normalized(enabled, "unknown")
    active_fallback = _normalized(active_fallback, "unknown")
    status_text = str(status_text or "")
    result = _normalized(properties.get("Result"))
    exec_status = _normalized(properties.get("ExecMainStatus"))
    exec_code = _normalized(properties.get("ExecMainCode"))
    active_state = _normalized(properties.get("ActiveState"), active_fallback) or active_fallback
    sub_state = _normalized(properties.get("SubState"))
    last_start = str(properties.get("ExecMainStartTimestamp") or "")
    last_exit = str(properties.get("ExecMainExitTimestamp") or "")

    oneshot_ok, applied, successful_result = _service_evidence(
        enabled, active_state, result, exec_status, status_text, config_exists
    )
    ui_state, ui_detail = _service_presentation(
        enabled, active_state, result, oneshot_ok, successful_result
    )

    return {
        "active_state": active_state,
        "sub_state": sub_state,
        "result": result,
        "exec_status": exec_status,
        "exec_code": exec_code,
        "oneshot_ok": oneshot_ok,
        "applied": applied,
        "applied_this_boot": bool(applied and (last_start or active_state == "active")),
        "ui_state": ui_state,
        "ui_detail": ui_detail,
        "last_start": last_start,
        "last_exit": last_exit,
    }
