"""The CPU cards' temperature cap and steps survive the export to Decky.

The desktop lets each CPU card carry a 70-90 C cap, but the export used to send
only the name, frequency and VID, so Game Mode ran every card at 90 C. Values
off the 50 MHz / 5 mV steps were accepted on the desktop and then dropped
without a word by Decky. Four places check the same rules: the request, the
root writer, the Quick Access helper's reader and the plugin backend.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from bc250cc.infrastructure.governor_config_request import plan_governor_config_request

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "integrations/decky/bc250-quick-access/main.py"
HELPER = ROOT / "privileged/helpers/bc250-quick-access-helper"
GOVERNOR_TOML = ROOT / "privileged/lib/governor_toml.py"

CARD = {"key": "mid_point", "name": "Cool", "frequency": 3850, "vid": 1150, "temperature": 75}


def _request(*entries):
    (argument,) = plan_governor_config_request("set-decky-cpu-profiles", (list(entries),)).arguments
    return json.loads(argument)


def _governor_toml(monkeypatch):
    spec = importlib.util.spec_from_file_location("bc250_governor_toml_cpu_export_test", GOVERNOR_TOML)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    return module


def _helper():
    loader = SourceFileLoader("bc250_quick_access_helper_cpu_export_test", str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backend(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-settings-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("bc250_quick_access_backend_cpu_export_test", BACKEND)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- the request the desktop sends ------------------------------------------

def test_the_request_keeps_each_cards_temperature_cap():
    assert _request(CARD) == [CARD]


def test_a_request_without_a_cap_means_the_ninety_degrees_decky_always_used():
    older = {key: value for key, value in CARD.items() if key != "temperature"}

    assert _request(older)[0]["temperature"] == 90


@pytest.mark.parametrize("temperature", [69, 91, 0, -5, 750, True, 72.5, "hot", None])
def test_a_cap_outside_seventy_to_ninety_is_refused(temperature):
    with pytest.raises(ValueError, match="temperature|integers"):
        _request({**CARD, "temperature": temperature})


@pytest.mark.parametrize("field, value", [
    ("frequency", 3125), ("frequency", 3101), ("frequency", 4199),
    ("vid", 1052), ("vid", 951), ("vid", 1324),
])
def test_a_value_between_two_steps_is_refused_instead_of_dropped_later(field, value):
    with pytest.raises(ValueError, match="50 MHz and 5 mV steps"):
        _request({**CARD, field: value})


def test_every_step_edge_of_the_ranges_is_still_accepted():
    for frequency, vid in ((3100, 950), (4200, 1325), (3150, 955)):
        for temperature in (70, 90):
            _request({**CARD, "frequency": frequency, "vid": vid, "temperature": temperature})


# -- the root writer ----------------------------------------------------------

def test_the_root_writer_stores_the_cap_and_defaults_an_old_entry(tmp_path, monkeypatch):
    module = _governor_toml(monkeypatch)
    target = tmp_path / "decky-cpu-profiles.json"
    older = {key: value for key, value in CARD.items() if key != "temperature"}

    module.write_decky_cpu_profiles(json.dumps([CARD, {**older, "key": "safe_maximum"}]), target)

    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored["schema"] == 1
    assert [(p["key"], p["temperature"]) for p in stored["profiles"]] == [("mid_point", 75), ("safe_maximum", 90)]


@pytest.mark.parametrize("entry", [
    {**CARD, "temperature": 69}, {**CARD, "temperature": 91}, {**CARD, "temperature": True},
    {**CARD, "temperature": "75"}, {**CARD, "frequency": 3125}, {**CARD, "vid": 1052},
    {**CARD, "frequency": 4250}, {**CARD, "vid": 940},
])
def test_the_root_writer_refuses_what_the_readers_would_drop(tmp_path, monkeypatch, entry):
    module = _governor_toml(monkeypatch)
    target = tmp_path / "decky-cpu-profiles.json"

    with pytest.raises(module.GovernorTomlError, match="Decky CPU profile values"):
        module.write_decky_cpu_profiles(json.dumps([entry]), target)
    assert not target.exists()


# -- the Quick Access helper's reader and the cpu-detect call ---------------

def _published(tmp_path, *entries, mode=0o644):
    path = tmp_path / "decky-cpu-profiles.json"
    path.write_text(json.dumps({"schema": 1, "profiles": list(entries)}), encoding="utf-8")
    path.chmod(mode)
    return path


def test_the_helper_reads_the_cap_and_defaults_a_file_written_before_it(tmp_path, monkeypatch):
    helper = _helper()
    older = {key: value for key, value in CARD.items() if key != "temperature"}
    path = _published(tmp_path, CARD, {**older, "key": "safe_maximum"})
    monkeypatch.setattr(Path, "lstat", lambda self: type("S", (), {"st_mode": 0o100644, "st_uid": 0, "st_size": 400})())

    overrides = helper._load_cpu_profile_overrides(path)

    assert overrides["mid_point"]["temperature"] == 75
    assert overrides["safe_maximum"]["temperature"] == 90


@pytest.mark.parametrize("temperature", [69, 91, True, "75", 75.0, None])
def test_the_helper_drops_an_entry_whose_cap_is_not_a_real_seventy_to_ninety(tmp_path, monkeypatch, temperature):
    helper = _helper()
    path = _published(tmp_path, {**CARD, "temperature": temperature})
    monkeypatch.setattr(Path, "lstat", lambda self: type("S", (), {"st_mode": 0o100644, "st_uid": 0, "st_size": 400})())

    assert helper._load_cpu_profile_overrides(path) == {}


def test_the_detection_runs_at_the_cap_it_was_asked_for(monkeypatch):
    helper = _helper()
    monkeypatch.setattr(helper, "cpu_tuning_context", lambda: {"cpu_tuning_ready": True})

    assert helper.cpu_detection_candidate("3850", "1150", "75") == {
        "frequency": 3850, "vid": 1150, "temperature": 75,
    }
    # The older two-argument call still means the fixed limit.
    assert helper.cpu_detection_candidate("3850", "1150")["temperature"] == 90


@pytest.mark.parametrize("raw", ["69", "91", "7", "075", "-5", "hot", ""])
def test_the_detection_refuses_a_cap_outside_the_range(monkeypatch, raw):
    helper = _helper()
    monkeypatch.setattr(helper, "cpu_tuning_context", lambda: {"cpu_tuning_ready": True})

    with pytest.raises(ValueError, match="thermal limit"):
        helper.cpu_detection_candidate("3850", "1150", raw)


def test_cpu_detect_passes_the_cap_to_the_root_cpu_helper(monkeypatch, capsys):
    helper = _helper()
    calls = []
    detected = {
        "ready": True, "requested_frequency": 3850, "requested_vid": 1150,
        "requested_temperature": 75, "frequency": 3850, "scale": -20, "temperature": 75,
    }
    monkeypatch.setattr(helper, "cpu_tuning_context", lambda: {"cpu_tuning_ready": True})
    monkeypatch.setattr(helper, "cpu_qam_detection_state", lambda: detected)
    monkeypatch.setattr(helper, "cpu_service_state", lambda: {})
    monkeypatch.setattr(
        helper, "run",
        lambda argv, **_kwargs: calls.append(argv) or types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    assert helper.cpu_detect_tuning("3850", "1150", "75") == 0

    assert calls == [[str(helper.CPU_HELPER), "detect-qam", "3850", "1150", "75"]]
    assert json.loads(capsys.readouterr().out)["cpu_applied_profile"]["temperature"] == 75


def test_a_manual_scale_reuses_the_cap_the_detection_ran_with(monkeypatch):
    helper = _helper()
    detected = {"ready": True, "manual_scale_ready": True, "frequency": 3850, "temperature": 75}
    monkeypatch.setattr(helper, "cpu_qam_detection_state", lambda: detected)

    assert helper.cpu_scale_candidate("3850", "-20")["temperature"] == 75


def test_cpu_detect_takes_an_optional_cap_on_the_command_line(monkeypatch):
    helper = _helper()
    seen = []
    monkeypatch.setattr(helper, "require_runtime", lambda: None)
    monkeypatch.setattr(helper, "load_contract", lambda: None)
    monkeypatch.setattr(helper, "cpu_detect_tuning", lambda *args: seen.append(args) or 0)

    assert helper.main(["helper", "cpu-detect", "3850", "1150"]) == 0
    assert helper.main(["helper", "cpu-detect", "3850", "1150", "75"]) == 0
    assert helper.main(["helper", "cpu-detect", "3850", "1150", "75", "1"]) == 2
    assert seen == [("3850", "1150"), ("3850", "1150", "75")]


# -- the plugin backend -------------------------------------------------------

def test_the_backend_shows_the_cap_and_defaults_it_for_an_old_export(monkeypatch):
    module = _backend(monkeypatch)
    older = {key: value for key, value in CARD.items() if key != "temperature"}

    profiles = module._validated_cpu_profiles([CARD, {**older, "key": "safe_maximum"}])

    by_key = {profile["key"]: profile for profile in profiles}
    assert by_key["mid_point"]["temperature"] == 75
    assert by_key["safe_maximum"]["temperature"] == 90
    assert all(profile["temperature"] == 90 for profile in profiles if profile.get("default"))


@pytest.mark.parametrize("temperature", [69, 91, True, "75", 75.0])
def test_the_backend_falls_back_to_the_default_card_for_a_bad_cap(monkeypatch, temperature):
    module = _backend(monkeypatch)

    profiles = module._validated_cpu_profiles([{**CARD, "temperature": temperature}])

    assert profiles[1]["default"] is True


def test_applying_a_card_sends_its_cap_to_the_helper(monkeypatch):
    module = _backend(monkeypatch)
    plugin = module.Plugin()
    calls = []

    async def run(*args, **_kwargs):
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(plugin, "_run_single_operation", run)
    asyncio.run(plugin.apply_cpu_tuning(3850, 1150, 75))
    asyncio.run(plugin.apply_cpu_tuning(3850, 1150))

    assert calls == [
        ("cpu-detect", "3850", "1150", "75"),
        # The default cap keeps the call an older helper understands.
        ("cpu-detect", "3850", "1150"),
    ]


@pytest.mark.parametrize("temperature", [69, 91, "75", 75.5, True, None])
def test_the_backend_refuses_a_cap_outside_seventy_to_ninety(monkeypatch, temperature):
    module = _backend(monkeypatch)
    plugin = module.Plugin()

    async def run(*_args, **_kwargs):
        raise AssertionError("the helper must not be reached")

    monkeypatch.setattr(plugin, "_run_single_operation", run)

    assert asyncio.run(plugin.apply_cpu_tuning(3850, 1150, temperature))["ok"] is False
