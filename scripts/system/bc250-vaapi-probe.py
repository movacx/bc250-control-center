#!/usr/bin/env python3
"""Ask libva what a VA-API driver offers on the BC-250, without any tool.

vainfo is not on every system (SteamOS ships it, a minimal Arch does not),
so this talks to libva itself through ctypes: open the BC-250's render node,
initialise the driver libva picks from the environment (LIBVA_DRIVER_NAME
and LIBVA_DRIVERS_PATH), and list each profile's entry points. One line of
JSON on stdout; exit status 0 only when H.264 and HEVC encode and decode are
all there.

Used before the BC-250 VA-API driver is switched on, against the freshly
built copy, and by the card's Test action against the installed one.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

BC250 = ("0x1002", "0x13fe")
#: va/va.h
PROFILES = {
    6: ("h264", "Main"), 7: ("h264", "High"), 13: ("h264", "Constrained Baseline"),
    17: ("hevc", "Main"), 18: ("hevc", "Main 10"),
}
VLD, ENC_SLICE, VIDEO_PROC = 1, 6, 10


def render_node() -> str:
    for node in sorted(Path("/sys/class/drm").glob("renderD*")):
        try:
            ids = ((node / "device/vendor").read_text().strip(), (node / "device/device").read_text().strip())
        except OSError:
            continue
        if ids == BC250:
            return f"/dev/dri/{node.name}"
    return ""


def probe() -> dict:
    node = render_node()
    if not node:
        return {"ok": False, "error": "The BC-250's render node was not found."}
    try:
        libva = ctypes.CDLL("libva.so.2")
        libva_drm = ctypes.CDLL("libva-drm.so.2")
    except OSError as error:
        return {"ok": False, "error": f"libva is not installed: {error}"}
    libva_drm.vaGetDisplayDRM.restype = ctypes.c_void_p
    libva_drm.vaGetDisplayDRM.argtypes = [ctypes.c_int]
    libva.vaInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    libva.vaQueryVendorString.restype = ctypes.c_char_p
    libva.vaQueryVendorString.argtypes = [ctypes.c_void_p]
    libva.vaMaxNumProfiles.argtypes = [ctypes.c_void_p]
    libva.vaMaxNumEntrypoints.argtypes = [ctypes.c_void_p]
    libva.vaQueryConfigProfiles.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    libva.vaQueryConfigEntrypoints.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ]
    libva.vaTerminate.argtypes = [ctypes.c_void_p]
    try:
        fd = os.open(node, os.O_RDWR)
    except OSError as error:
        return {"ok": False, "error": f"{node} could not be opened: {error}"}
    try:
        display = libva_drm.vaGetDisplayDRM(fd)
        if not display:
            return {"ok": False, "error": "libva could not use the render node."}
        major, minor = ctypes.c_int(), ctypes.c_int()
        status = libva.vaInitialize(display, ctypes.byref(major), ctypes.byref(minor))
        if status != 0:
            return {"ok": False, "error": f"The driver did not start (libva status {status})."}
        try:
            vendor = (libva.vaQueryVendorString(display) or b"").decode("utf-8", "replace")
            count = ctypes.c_int()
            profiles = (ctypes.c_int * max(1, libva.vaMaxNumProfiles(display)))()
            libva.vaQueryConfigProfiles(display, profiles, ctypes.byref(count))
            encode, decode, video_proc = set(), set(), False
            entries = (ctypes.c_int * max(1, libva.vaMaxNumEntrypoints(display)))()
            for profile in list(profiles)[: count.value]:
                found = ctypes.c_int()
                if libva.vaQueryConfigEntrypoints(display, profile, entries, ctypes.byref(found)) != 0:
                    continue
                points = set(list(entries)[: found.value])
                if profile == -1:  # VAProfileNone
                    video_proc = video_proc or VIDEO_PROC in points
                    continue
                codec = PROFILES.get(profile)
                if not codec:
                    continue
                label = f"{codec[0]} {codec[1]}"
                if ENC_SLICE in points:
                    encode.add(label)
                if VLD in points:
                    decode.add(label)
        finally:
            libva.vaTerminate(display)
    finally:
        os.close(fd)
    codecs = {"encode": sorted(encode), "decode": sorted(decode)}
    ok = all(
        any(item.startswith(codec) for item in codecs[direction])
        for codec in ("h264", "hevc") for direction in ("encode", "decode")
    )
    return {"ok": ok, "vendor": vendor, "node": node, "video_proc": video_proc, **codecs}


def main() -> int:
    result = probe()
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
