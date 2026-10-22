"""Every failure the Game Mode panel shows carries one stable code.

The backend's ``ERROR_CODES`` table maps each code to the locale keys of a
short title and a next step, and to the Desktop's ``BC250-AREA-NNN`` code for
the same fault. These checks keep that table complete against the helper,
consistent with the Desktop catalogue, and actually applied on every path a
failure can take: a helper exit, a timeout, a missing helper, a protocol
mismatch, a busy lock, a rejected argument and a backend exception.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "integrations" / "decky" / "bc250-quick-access"
BACKEND = PLUGIN / "main.py"
HELPER = ROOT / "privileged" / "helpers" / "bc250-quick-access-helper"
PANEL = PLUGIN / "src" / "index.tsx"
BUNDLE = PLUGIN / "dist" / "index.js"
DESKTOP_RULES = ROOT / "frontends" / "desktop" / "core" / "error_diagnostics.py"

sys.path.insert(0, str(ROOT / "src"))
from bc250cc.shared import error_catalog  # noqa: E402


def _backend(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-codes-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("bc250_quick_access_error_codes_test", BACKEND)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ the table


def test_every_code_the_helper_prints_is_in_the_table(monkeypatch):
    module = _backend(monkeypatch)
    printed = set(re.findall(r"\b(QUICK_ACCESS_[A-Z0-9_]+|HARDWARE_CONTEXT)(?=:)", HELPER.read_text(encoding="utf-8")))
    assert printed, "the helper's code prefixes moved"
    assert printed - set(module.ERROR_CODES) == set()


def test_every_title_and_next_step_is_a_locale_string(monkeypatch):
    module = _backend(monkeypatch)
    english = json.loads((PLUGIN / "locales" / "en.json").read_text(encoding="utf-8"))
    missing = [
        (code, key) for code, (title, hint, _desktop) in module.ERROR_CODES.items()
        for key in (title, hint) if key not in english
    ]
    assert missing == []


def test_every_desktop_code_is_one_the_desktop_defines(monkeypatch):
    """No private ids: each is in the shared catalogue or the Desktop's own rules.

    The panel's source may only name catalogue ids (test_error_catalog_contract);
    the backend's table also points at rule-only ids such as INTERNAL-001.
    """
    module = _backend(monkeypatch)
    rules = DESKTOP_RULES.read_text(encoding="utf-8")
    unknown = [
        desktop for _title, _hint, desktop in module.ERROR_CODES.values()
        if desktop not in error_catalog.BY_CODE and f'"{desktop}"' not in rules
    ]
    assert unknown == []


#: Where the Desktop catalogue's marker says something else, on purpose.
#: "QUICK_ACCESS_CPU_SERVICE:" is filed under PROTOCOL-001 there because the
#: helper also prints it for a bad argument, but exits 52-55 are real CPU
#: service failures.
DELIBERATE_DIFFERENCES = {"QUICK_ACCESS_CPU_SERVICE"}


def test_desktop_codes_agree_with_the_catalogue_markers(monkeypatch):
    module = _backend(monkeypatch)
    disagreements = {}
    for code, (_title, _hint, desktop) in module.ERROR_CODES.items():
        entry = error_catalog.for_marker(f"ERR {code}: example")
        if entry is not None and entry.code != desktop and code not in DELIBERATE_DIFFERENCES:
            disagreements[code] = (desktop, entry.code)
    assert disagreements == {}


def test_codes_are_never_renamed(monkeypatch):
    """Players quote these; a rename would point them at nothing."""
    module = _backend(monkeypatch)
    for code in (
        "QUICK_ACCESS_GPU_CONFIG", "QUICK_ACCESS_COMPONENT_MISSING", "QUICK_ACCESS_TIMEOUT",
        "QUICK_ACCESS_OPERATION_FAILED", "QUICK_ACCESS_INTERNAL", "QUICK_ACCESS_FAN_EXTERNAL",
        "QUICK_ACCESS_CU_KERNEL", "HARDWARE_CONTEXT",
    ):
        assert code in module.ERROR_CODES


# ------------------------------------------------------------- classification


def test_the_first_specific_code_wins_over_a_wrapper(monkeypatch):
    module = _backend(monkeypatch)
    text = "ERR QUICK_ACCESS_OPERATION_FAILED: QUICK_ACCESS_COMPONENT_MISSING: the shared BC250 contract is not installed."
    assert module.classify_error(text, 71, "status") == "QUICK_ACCESS_COMPONENT_MISSING"
    assert module.classify_error("ERR QUICK_ACCESS_OPERATION_FAILED: CPU VID must be an integer.", 71, "cpu-detect") \
        == "QUICK_ACCESS_OPERATION_FAILED"
    assert module.classify_error("ERR QUICK_ACCESS_GPU_SERVICE: QUICK_ACCESS_GPU_DBUS: x", 69, "gpu-service") \
        == "QUICK_ACCESS_GPU_SERVICE"


def test_a_helper_lock_is_busy_not_a_generic_failure(monkeypatch):
    module = _backend(monkeypatch)
    text = "ERR QUICK_ACCESS_OPERATION_FAILED: Another fan operation is still in progress."
    assert module.classify_error(text, 71, "fan-system") == "QUICK_ACCESS_BUSY"


def test_uncoded_failures_fall_back_on_exit_status_and_area(monkeypatch):
    module = _backend(monkeypatch)
    assert module.classify_error("ERR Usage: status | ...", 2, "gpu-profile") == "QUICK_ACCESS_PROTOCOL_MISMATCH"
    assert module.classify_error("Failed to set range", 23, "gpu-profile") == "QUICK_ACCESS_GPU_DBUS"
    assert module.classify_error("Job for cyan.service failed", 24, "gpu-voltage-level") == "QUICK_ACCESS_GPU_VERIFY"
    assert module.classify_error("toml: bad key", 22, "gpu-high-points") == "QUICK_ACCESS_GPU_CONFIG"
    assert module.classify_error("umr: cannot open", 31, "cu-save") == "QUICK_ACCESS_CU_BACKEND"
    assert module.classify_error("bc250-detect failed", 81, "cpu-detect") == "QUICK_ACCESS_CPU"
    assert module.classify_error("something odd", 1, "status") == "QUICK_ACCESS_OPERATION_FAILED"
    assert module.classify_error("ERR QUICK_ACCESS_FROM_THE_FUTURE: x", 99, "fan-system") == "QUICK_ACCESS_FAN"


def test_diagnosis_names_title_hint_desktop_code_and_exit_status(monkeypatch):
    module = _backend(monkeypatch)
    diagnosis = module.diagnose({"ok": False, "error": "ERR QUICK_ACCESS_FAN_EXTERNAL: handed over", "exit_code": 58})
    assert diagnosis == {
        "code": "QUICK_ACCESS_FAN_EXTERNAL", "title": "fanExternalFailed", "hint": "fanExternalAction",
        "desktop_code": "BC250-FAN-002", "exit_code": 58,
    }


# --------------------------------------------------------------- the helper run


def _trusted(module, monkeypatch):
    monkeypatch.setattr(module.Plugin, "_trusted_helper", staticmethod(lambda: True))
    monkeypatch.setattr(module.Plugin, "_contract_problem", staticmethod(lambda: ("", "")))


def test_a_missing_helper_is_component_missing(monkeypatch):
    module = _backend(monkeypatch)
    monkeypatch.setattr(module.Plugin, "_trusted_helper", staticmethod(lambda: False))
    result = module.Plugin()._run("status")
    assert result["ok"] is False and result["error_code"] == "QUICK_ACCESS_COMPONENT_MISSING"


def test_a_missing_contract_and_a_different_build_have_their_own_codes(monkeypatch, tmp_path):
    module = _backend(monkeypatch)
    monkeypatch.setattr(module, "CONTRACT_PATH", tmp_path / "absent.py")
    assert module.Plugin._contract_problem()[0] == "QUICK_ACCESS_COMPONENT_MISSING"
    monkeypatch.setattr(module.Plugin, "_trusted_helper", staticmethod(lambda: True))
    monkeypatch.setattr(module.Plugin, "_contract_problem", staticmethod(
        lambda: ("QUICK_ACCESS_PROTOCOL_MISMATCH", "BC250 Quick Access and the installed helper are different versions."),
    ))
    assert module.Plugin()._run("status")["error_code"] == "QUICK_ACCESS_PROTOCOL_MISMATCH"


def test_a_timeout_names_the_action_and_its_limit(monkeypatch):
    module = _backend(monkeypatch)
    _trusted(module, monkeypatch)

    def slow(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("helper", 30)

    monkeypatch.setattr(module.subprocess, "run", slow)
    result = module.Plugin()._run("fan-system", "quiet", timeout=30)
    assert result["error_code"] == "QUICK_ACCESS_TIMEOUT"
    assert "fan-system" in result["error"] and "30 s" in result["error"]


def test_a_helper_that_cannot_start_does_not_raise(monkeypatch):
    module = _backend(monkeypatch)
    _trusted(module, monkeypatch)

    def broken(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(module.subprocess, "run", broken)
    result = module.Plugin()._run("status")
    assert result["error_code"] == "QUICK_ACCESS_COMPONENT_MISSING"
    assert "PermissionError" in result["error"]


def test_a_helper_failure_keeps_its_text_and_exit_status(monkeypatch):
    module = _backend(monkeypatch)
    _trusted(module, monkeypatch)
    monkeypatch.setattr(module.subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess(
        [], 22, "", "ERR QUICK_ACCESS_GPU_CONFIG: Cyan TOML is unreadable.\n",
    ))
    result = module.Plugin()._run("gpu-profile", "gaming")
    assert result == {
        "ok": False, "error": "ERR QUICK_ACCESS_GPU_CONFIG: Cyan TOML is unreadable.",
        "error_code": "QUICK_ACCESS_GPU_CONFIG", "exit_code": 22,
    }


def test_a_protocol_mismatch_has_its_code(monkeypatch):
    module = _backend(monkeypatch)
    plugin = module.Plugin()
    monkeypatch.setattr(plugin, "_run", lambda *_a, **_k: {"ok": True, "protocol": module.HELPER_PROTOCOL - 1})
    assert plugin._verified_status()["error_code"] == "QUICK_ACCESS_PROTOCOL_MISMATCH"


# ------------------------------------------------------------- the RPC boundary


def test_every_public_rpc_is_diagnosed(monkeypatch):
    module = _backend(monkeypatch)
    import inspect

    public = [
        name for name, value in vars(module.Plugin).items()
        if not name.startswith("_") and inspect.iscoroutinefunction(value)
    ]
    assert "status" in public and "apply_gpu_profile" in public
    assert [name for name in public if not hasattr(getattr(module.Plugin, name), "__wrapped__")] == []


def test_a_rejected_argument_reaches_the_panel_diagnosed(monkeypatch):
    module = _backend(monkeypatch)
    result = asyncio.run(module.Plugin().apply_fan_channel(7, 50))
    assert result["error_code"] == "QUICK_ACCESS_INVALID_REQUEST"
    assert result["diagnosis"]["title"] == "requestFailed"
    assert result["diagnosis"]["desktop_code"] == "BC250-RANGE-001"


def test_a_second_press_while_busy_is_coded_busy(monkeypatch):
    module = _backend(monkeypatch)
    plugin = module.Plugin()

    async def exercise():
        await plugin._operation_lock.acquire()
        try:
            return await plugin.apply_gpu_profile("gaming")
        finally:
            plugin._operation_lock.release()

    result = asyncio.run(exercise())
    assert result["error_code"] == "QUICK_ACCESS_BUSY"
    assert result["diagnosis"]["hint"] == "busyAction"


def test_a_backend_exception_becomes_a_diagnosed_result(monkeypatch, tmp_path):
    module = _backend(monkeypatch)
    plugin = module.Plugin()
    plugin._settings_dir = tmp_path

    def explode(*_args, **_kwargs):
        raise KeyError("gpu_range")

    monkeypatch.setattr(plugin, "_verified_status", explode)
    result = asyncio.run(plugin.status())
    assert result["ok"] is False
    assert result["error_code"] == "QUICK_ACCESS_BACKEND"
    assert "KeyError" in result["error"]
    entry = json.loads((tmp_path / module.DIAGNOSTICS_FILENAME).read_text(encoding="utf-8").splitlines()[-1])
    assert entry["module"] == "backend" and entry["target"] == "status"
    assert entry["code"] == "QUICK_ACCESS_BACKEND"


def test_a_success_carries_no_diagnosis(monkeypatch):
    module = _backend(monkeypatch)
    plugin = module.Plugin()
    monkeypatch.setattr(plugin, "_run_gpu_range_write", lambda *_a: asyncio.sleep(0, {"ok": True, "gpu_range": [1000, 1850]}))
    result = asyncio.run(plugin.apply_gpu_profile("gaming"))
    assert "diagnosis" not in result and "error_code" not in result


def test_failed_actions_keep_their_code_in_the_desktop_history(monkeypatch, tmp_path):
    module = _backend(monkeypatch)
    plugin = module.Plugin()
    plugin._settings_dir = tmp_path
    plugin._record_action("fan", "quiet", {"ok": False, "error": "ERR QUICK_ACCESS_FAN: pwm2 is read-only"})
    entry = json.loads((tmp_path / module.DIAGNOSTICS_FILENAME).read_text(encoding="utf-8"))
    assert entry["code"] == "QUICK_ACCESS_FAN"
    assert entry["error"] == "ERR QUICK_ACCESS_FAN: pwm2 is read-only"


def test_a_failed_game_profile_step_keeps_its_code(monkeypatch, tmp_path):
    module = _backend(monkeypatch)
    plugin = module.Plugin()
    plugin._settings_dir = tmp_path
    monkeypatch.setattr(plugin, "_verified_status", lambda: {"ok": True, "protocol": module.HELPER_PROTOCOL})
    monkeypatch.setattr(plugin, "_run", lambda *_a, **_k: module._failure("QUICK_ACCESS_GPU_DBUS", "Cyan is not on the bus."))
    result = plugin._apply_game_profile("440", "Game", {"gpu": "gaming", "fan": None})
    assert result["ok"] is False and result["error_code"] == "QUICK_ACCESS_GPU_DBUS"


def test_status_names_a_silent_governor_and_a_cpu_tuning_problem(monkeypatch):
    module = _backend(monkeypatch)
    status = module.Plugin._decorate_status({
        "ok": True, "gpu_dbus_responsive": False,
        "cpu_tuning_error": "QUICK_ACCESS_CPU: stress is required by bc250-detect",
    })
    assert status["gpu_dbus_diagnosis"]["code"] == "QUICK_ACCESS_GPU_DBUS"
    assert status["cpu_tuning_diagnosis"]["code"] == "QUICK_ACCESS_CPU"
    quiet = module.Plugin._decorate_status({"ok": True, "gpu_dbus_responsive": True})
    assert "gpu_dbus_diagnosis" not in quiet and "cpu_tuning_diagnosis" not in quiet


# ------------------------------------------------------------------ the panel


def test_the_panels_own_code_matches_the_table(monkeypatch):
    module = _backend(monkeypatch)
    source = PANEL.read_text(encoding="utf-8")
    match = re.search(
        r'const NO_RESPONSE: Diagnosis = \{ code: "(\w+)", title: "(\w+)", hint: "(\w+)", desktop_code: "([\w-]+)" \};',
        source,
    )
    assert match, "the panel's NO_RESPONSE diagnosis moved"
    code, title, hint, desktop = match.groups()
    assert module.ERROR_CODES[code] == (title, hint, desktop)


def test_the_panel_renders_every_failure_through_the_diagnosis():
    source = PANEL.read_text(encoding="utf-8")
    assert "localizedErrorSummary" not in source
    assert "function describeFailure(" in source
    # No raw helper text as the visible message: it lives behind Details.
    assert "gddr6_patch_error" not in source
    assert "text.copyDetails" in source and "text.desktopCode" in source


def test_the_bundle_was_rebuilt_with_the_error_codes():
    bundle = BUNDLE.read_text(encoding="utf-8")
    english = json.loads((PLUGIN / "locales" / "en.json").read_text(encoding="utf-8"))
    assert "QUICK_ACCESS_NO_RESPONSE" in bundle
    assert english["noResponseFailed"] in bundle
    assert "RegisterForOnResumeFromSuspend" in bundle
