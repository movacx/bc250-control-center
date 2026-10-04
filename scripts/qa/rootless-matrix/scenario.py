#!/usr/bin/env python3
"""One distribution family's kernel-argument scenario, run as the fake root of a
throw-away container (see run-matrix.sh). scenario.py <kind>

It drives the real bc250-system-setup-helper exactly as Control Center and the
Quick Access helper do, and checks the result against the real boot tooling the
image ships (grub-mkconfig, grubby) where there is one.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HELPER = "/src/privileged/helpers/bc250-system-setup-helper"
STATE_DIR = Path("/var/lib/bc250-control-center/system-setup")
OSTREE_STATE = Path("/etc/bc250-control-center/ttm-kargs.original")
PAGES = {8: 2097152, 10: 2621440, 12: 3145728}
kind = sys.argv[1]
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def helper(*args: str, env: dict | None = None) -> tuple[int, str, str]:
    result = subprocess.run(["python3", "-I", HELPER, *args], capture_output=True, text=True,
                            env={**os.environ, **(env or {})})
    return result.returncode, result.stdout, result.stderr


def helper_json(*args: str, env: dict | None = None) -> dict:
    code, out, err = helper(*args, env=env)
    line = next((line for line in out.splitlines() if line.startswith("{")), "")
    if code or not line:
        return {"_error": (err.strip() or out.strip())[-300:], "_code": code}
    return json.loads(line)


def read(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def ttm() -> dict:
    return helper_json("ttm-status")


def grub_config_has(*words: str) -> bool:
    """Regenerate with the image's own grub-mkconfig and look at the linux lines."""
    out = "/boot/grub/grub.cfg"
    cmd = "update-grub" if subprocess.run(["which", "update-grub"], capture_output=True).returncode == 0 else "grub-mkconfig"
    args = [cmd] if cmd == "update-grub" else [cmd, "-o", out]
    result = subprocess.run(args, capture_output=True, text=True)
    text = read(out) or ""
    lines = [line for line in text.splitlines() if line.strip().startswith("linux")]
    check(f"{cmd} ran", result.returncode == 0 and bool(lines), result.stderr[-200:])
    return bool(lines) and all(any(word in line for line in lines) for word in words)


def grub_config_lacks(*words: str) -> bool:
    text = read("/boot/grub/grub.cfg") or ""
    lines = [line for line in text.splitlines() if line.strip().startswith("linux")]
    return bool(lines) and not any(word in line for word in words for line in lines)


print(f"== {kind}")
status = helper_json("status")
check("status answers with a ttm section", "ttm" in status, str(status.get("_error")))

if kind == "steamos":
    state = ttm()
    check("SteamOS is reported as not managed, with the reason", state.get("supported") is False and "SteamOS" in state.get("reason", ""), json.dumps(state)[:200])
    code, _out, err = helper("ttm-apply", "--ttm", "8")
    check("SteamOS refuses ttm-apply and changes nothing", code != 0 and not STATE_DIR.exists() or not list(STATE_DIR.glob("kernel-options.json")), err[-160:])
    kernel = helper_json("kernel-options-set", "--kernel-options", "nosmt")
    check("SteamOS kernel options are refused too", "_error" in kernel, str(kernel)[:160])
    sys.exit(1 if failures else 0)

check("unprivileged-style status has the shared fields", all(k in status["ttm"] for k in ("managed", "external", "reboot_required", "configured_pages")))
state = ttm()
expected_backend = {
    "arch-grub-new": "grub", "arch-grub-old": "grub", "debian-grub": "grub", "ubuntu-grub": "grub", "mint-grub": "grub",
    "cachyos-limine": "limine", "fedora-grubby": "grubby", "nobara-grubby": "grubby", "bazzite": "rpm-ostree",
}[kind]
check(f"backend is {expected_backend}", state.get("backend") == expected_backend and state.get("supported") is True, json.dumps(state)[:240])
check("12 GiB fits 15.5 GB; nothing hidden", state.get("presets_gib") == [8, 10, 12])
check("nothing set yet", state.get("managed") is False and state.get("configured_pages") is None and state.get("reboot_required") is False)

files = {
    "limine": ["/etc/default/limine"], "grub": ["/etc/default/grub"], "grubby": [], "rpm-ostree": [],
}[expected_backend]
before = {path: read(path) for path in files}
ostree_before = (Path("/var/lib/stub-rpm-ostree/kargs").read_text() if kind == "bazzite" and Path("/var/lib/stub-rpm-ostree/kargs").exists() else None)

# --- switches first, then the limit on top
kernel = helper_json("kernel-options-set", "--kernel-options", "mitigations=off,nosmt") if kind != "bazzite" else {"_skip": True}
if kind != "bazzite":
    check("mitigations=off and nosmt set", kernel.get("arguments", {}).get("nosmt", {}).get("managed") is True, str(kernel)[:200])
result = helper_json("ttm-apply", "--ttm", "8")
check("ttm-apply 8 saves the limit for the next boot", result.get("configured_pages") == PAGES[8] and result.get("managed") is True and result.get("reboot_required") is True, str(result)[:300])
check("another reader sees the same state", {k: ttm().get(k) for k in ("managed", "configured_pages", "reboot_required")} == {"managed": True, "configured_pages": PAGES[8], "reboot_required": True})

arg8 = f"ttm.pages_limit={PAGES[8]}"
if expected_backend == "grub":
    reads = "default/grub.d" in (read("/usr/sbin/grub-mkconfig") or read("/usr/bin/grub-mkconfig") or "")
    dropin = Path("/etc/default/grub.d/91-bc250-kernel-options.cfg")
    check(f"{'drop-in' if reads else 'marked block in /etc/default/grub'} is where this GRUB looks", dropin.exists() == reads and (("BEGIN BC250" in (read('/etc/default/grub') or '')) != reads))
    check("the real grub-mkconfig puts the limit and the switches on the linux line", grub_config_has(arg8, "nosmt", "mitigations=off"))
elif expected_backend == "limine":
    check("limine block carries the limit", arg8 in (read("/etc/default/limine") or ""))
elif expected_backend == "rpm-ostree":
    check("rpm-ostree has the argument staged", arg8 in Path("/var/lib/stub-rpm-ostree/kargs").read_text())
    mode = OSTREE_STATE.stat().st_mode & 0o777
    check("journal of the original arguments is 0600 with the shared marker", mode == 0o600 and OSTREE_STATE.read_text().splitlines()[0] == "# Managed by BC250 Control Center", oct(mode))
elif expected_backend == "grubby":
    info = subprocess.run(["grubby", "--info=ALL"], capture_output=True, text=True).stdout
    check("grubby carries the limit and the switches", arg8 in info and "nosmt" in info and "mitigations=off" in info, info[-300:])

# --- change the value: the old one must not linger
result = helper_json("ttm-apply", "--ttm", "10")
check("ttm-apply 10 replaces 8", result.get("configured_pages") == PAGES[10], str(result)[:200])
arg10 = f"ttm.pages_limit={PAGES[10]}"
if expected_backend == "grub":
    check("grub.cfg has 10 and not 8", grub_config_has(arg10, "nosmt") and grub_config_lacks(arg8))
elif expected_backend == "grubby":
    info = subprocess.run(["grubby", "--info=ALL"], capture_output=True, text=True).stdout
    check("grubby has exactly the new value (the old one is gone, the new one kept)", arg10 in info and arg8 not in info and "nosmt" in info, info[-300:])
elif expected_backend == "rpm-ostree":
    args = Path("/var/lib/stub-rpm-ostree/kargs").read_text().split()
    check("rpm-ostree has exactly one ttm.pages_limit, the new one", [a for a in args if a.startswith("ttm.")] == [arg10])
elif expected_backend == "limine":
    text = read("/etc/default/limine") or ""
    check("limine has exactly the new value", arg10 in text and arg8 not in text)

# --- the plugin may only ask for the fixed choices
code, _out, err = helper("ttm-apply", "--ttm", "16")
check("a 16 GiB request is refused by the setup helper", code != 0)
code, _out, _err = helper("ttm-apply", "--ttm", "0")
check("ttm-apply 0 is refused (nothing to do)", code != 0)

# --- removal is blocked while anything of ours is on the boot configuration
code, _out, err = helper("uninstall-check")
check("uninstall-check blocks while the limit is set", code != 0 and "GPU memory limit" in err, err[-200:])

# --- restore
if kind != "bazzite":
    helper_json("kernel-options-set", "--kernel-options", "")
result = helper_json("ttm-apply", "--ttm", "-1")
check("ttm-apply -1 restores the kernel default", result.get("configured_pages") is None and result.get("managed") is False, str(result)[:240])
if expected_backend in ("grub", "limine"):
    after = {path: read(path) for path in files}
    check("boot files are byte-for-byte what they were", after == before, "; ".join(p for p in files if after[p] != before[p]))
    check("no drop-in left behind", not Path("/etc/default/grub.d/91-bc250-kernel-options.cfg").exists())
if expected_backend == "grub":
    check("grub.cfg is clean again", grub_config_has("quiet") and grub_config_lacks("ttm.pages_limit", "nosmt"))
if expected_backend == "grubby":
    info = subprocess.run(["grubby", "--info=ALL"], capture_output=True, text=True).stdout
    check("grubby is clean again", "ttm.pages_limit" not in info and "nosmt" not in info and "mitigations=off" not in info, info[-300:])
if expected_backend == "rpm-ostree":
    check("kargs are exactly the original and the journal is gone", Path("/var/lib/stub-rpm-ostree/kargs").read_text().split() == ostree_before.split() and not OSTREE_STATE.exists())
check("uninstall-check is clean again", helper("uninstall-check")[0] == 0)
check("state files are readable only as intended (no group/world write)", all(not (p.stat().st_mode & 0o022) for p in STATE_DIR.glob("*.json")))

# --- failure paths
if kind == "bazzite":
    Path("/run/rpm-ostree.busy").write_text("")
    code, _out, err = helper("ttm-apply", "--ttm", "8")
    check("a running rpm-ostree transaction is reported, not hidden", code != 0 and "Transaction in progress" in err, err[-200:])
    check("...and leaves no journal behind", not OSTREE_STATE.exists())
    Path("/run/rpm-ostree.busy").unlink()
    # A limit somebody else set is kept in the journal and put back.
    Path("/var/lib/stub-rpm-ostree/kargs").write_text("rhgb quiet ttm.pages_limit=3000000\n")
    state = ttm()
    check("a foreign limit is reported as not ours", state.get("managed") is False and state.get("configured_pages") == 3000000)
    helper_json("ttm-apply", "--ttm", "10")
    check("the foreign limit is journalled", "ttm.pages_limit=3000000" in OSTREE_STATE.read_text())
    helper_json("ttm-apply", "--ttm", "-1")
    check("restore puts the foreign limit back", "ttm.pages_limit=3000000" in Path("/var/lib/stub-rpm-ostree/kargs").read_text() and not OSTREE_STATE.exists())
else:
    # A limit somebody else put in the boot configuration is never replaced.
    foreign = {"limine": "/etc/default/limine", "grub": "/etc/default/grub"}.get(expected_backend)
    if foreign:
        original = read(foreign) or ""
        Path(foreign).write_text(original + '\nGRUB_CMDLINE_LINUX_DEFAULT="${GRUB_CMDLINE_LINUX_DEFAULT} ttm.pages_limit=3000000"\n'
                                 if expected_backend == "grub" else original + 'KERNEL_CMDLINE[default]+=" ttm.pages_limit=3000000"\n')
        state = ttm()
        check("a foreign limit is reported as set elsewhere", state.get("external") is True and state.get("managed") is False, json.dumps(state)[:240])
        code, _out, err = helper("ttm-apply", "--ttm", "8")
        check("and is never replaced", code != 0 and "outside Control Center" in err, err[-200:])
        Path(foreign).write_text(original)

print(("FAILED: " + ", ".join(failures)) if failures else "ALL PASSED")
sys.exit(1 if failures else 0)
