#!/usr/bin/env python3
"""Game Mode: load the installed Decky plugin (main.py) against the installed
root helpers and drive every call the panel makes. Run as the fake root, after
install-local.sh and install-decky-quick-access.sh. plugin_e2e.py <plugin-dir>
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import sys
import types

plugin_dir = pathlib.Path(sys.argv[1])
unsupported = "--unsupported" in sys.argv
decky = types.ModuleType("decky")
decky.logger = logging.getLogger("decky")
decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp/decky-settings"
decky.DECKY_PLUGIN_DIR = str(plugin_dir)
decky.DECKY_PLUGIN_RUNTIME_DIR = "/tmp/decky-runtime"
decky.DECKY_PLUGIN_LOG_DIR = "/tmp/decky-log"
decky.DECKY_USER_HOME = "/home/deck"
for name in ("DECKY_PLUGIN_SETTINGS_DIR", "DECKY_PLUGIN_RUNTIME_DIR", "DECKY_PLUGIN_LOG_DIR"):
    pathlib.Path(getattr(decky, name)).mkdir(parents=True, exist_ok=True)
sys.modules["decky"] = decky
sys.path.insert(0, str(plugin_dir))
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("bc250_plugin_main", plugin_dir / "main.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(label)


async def main():
    plugin = module.Plugin()
    await plugin._main()
    state = await plugin.ttm_state()
    check("ttm_state answers", state.get("ok") is not False and "ttm" in state, str(state)[:300])
    ttm = state.get("ttm", {})
    if unsupported:
        check("the panel is told why the limit cannot be kept here", ttm.get("supported") is False and bool(ttm.get("reason")), str(state)[:300])
        reply = await plugin.apply_ttm_limit("8")
        check("an apply is refused with the reason", reply.get("ok") is False, str(reply)[:200])
        status = await plugin.status()
        check("the rest of Game Mode still reads (status)", status.get("ok") is not False, str(status)[:200])
        await plugin._unload()
        return
    check("state has every documented field", set(ttm) == set(module.TTM_FIELDS) if hasattr(module, "TTM_FIELDS") else bool(ttm))
    check("limit is supported on this system", ttm.get("supported") is True, str(ttm)[:200])
    for bad in (16, -1, 0, "8; reboot", "default ", True, 8.0, None, [8]):
        reply = await plugin.apply_ttm_limit(bad)
        check(f"apply_ttm_limit({bad!r}) is refused", reply.get("ok") is False)
    reply = await plugin.apply_ttm_limit("10")
    check("apply 10 GiB", reply.get("ok") is not False and reply["ttm"]["configured_pages"] == 2621440 and reply["ttm"]["managed"], str(reply)[:300])
    check("the panel is told a reboot is needed", reply["ttm"]["reboot_required"] is True)
    again = await plugin.ttm_state()
    check("a fresh read agrees with the reply", again["ttm"]["configured_pages"] == 2621440 and again["ttm"]["managed"] is True)
    reply = await plugin.apply_ttm_limit(8)
    check("apply 8 GiB (int accepted)", reply.get("ok") is not False and reply["ttm"]["configured_pages"] == 2097152, str(reply)[:200])
    reply = await plugin.apply_ttm_limit("default")
    check("restore the kernel default", reply.get("ok") is not False and reply["ttm"]["managed"] is False and reply["ttm"]["configured_pages"] is None, str(reply)[:200])
    reply = await plugin.apply_ttm_limit("default")
    check("restoring twice reports nothing to restore", reply.get("ok") is False)
    status = await plugin.status()
    check("status() is healthy and carries VRAM active/pending fields", status.get("ok") is not False and "active_mb" in status.get("vram", {}), str(status)[:300])
    snap = await plugin.monitor_snapshot()
    check("monitor_snapshot() answers", snap.get("ok") is not False, str(snap)[:200])
    await plugin._unload()


asyncio.run(main())
print(("FAILED: " + ", ".join(failures)) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
