#!/usr/bin/env python3
"""Let Flatpak apps use the BC-250 VA-API driver.

A Flatpak app runs in its own sandbox: it cannot open the driver under
/var/lib/bc250-control-center/vaapi, and its own Mesa has only radeonsi, which
the BC-250 cannot start. So GPU Screen Recorder, OBS, Steam and the rest list
"H.264 (not available on your system)" and fall back to software video.

The fix is Flatpak's per-user global override: read-only access to the driver
folder and the two variables libva reads. This script adds or removes exactly
those lines in ~/.local/share/flatpak/overrides/global (a key file), and
leaves every other line, section and override as it found it.

    bc250-vaapi-flatpak.py status  RUNTIME LIBVA_PATH
    bc250-vaapi-flatpak.py enable  RUNTIME LIBVA_PATH
    bc250-vaapi-flatpak.py disable RUNTIME LIBVA_PATH

``status`` prints one line of JSON. Exit status is 0 when the command did what
it was asked (``status`` always).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

DRIVER_NAME = "bc250"


def override_file() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "flatpak" / "overrides" / "global"


def _split_list(value: str) -> list[str]:
    return [item for item in value.split(";") if item]


def _join_list(items: list[str]) -> str:
    return ";".join(items) + ";" if items else ""


def _section_bounds(lines: list[str], name: str) -> tuple[int, int] | None:
    """The line range of ``[name]``: header index, then the index after its last line."""
    start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if start is not None:
                return start, index
            if stripped == f"[{name}]":
                start = index
    return (start, len(lines)) if start is not None else None


def _find_key(lines: list[str], bounds: tuple[int, int], key: str) -> int | None:
    for index in range(bounds[0] + 1, bounds[1]):
        left, separator, _value = lines[index].partition("=")
        if separator and left.strip() == key:
            return index
    return None


def _value(lines: list[str], bounds: tuple[int, int] | None, key: str) -> str | None:
    if bounds is None:
        return None
    index = _find_key(lines, bounds, key)
    return None if index is None else lines[index].partition("=")[2].strip()


def _set(lines: list[str], section: str, key: str, value: str | None) -> list[str]:
    """Set (or, with ``None``, remove) one key; create the section when needed."""
    lines = list(lines)
    bounds = _section_bounds(lines, section)
    if bounds is None:
        if value is None:
            return lines
        if lines and lines[-1].strip():
            lines.append("")
        return [*lines, f"[{section}]", f"{key}={value}"]
    index = _find_key(lines, bounds, key)
    if value is None:
        if index is not None:
            del lines[index]
        # An emptied section the file did not have before goes away with its keys.
        bounds = _section_bounds(lines, section)
        if bounds is not None and not any(line.strip() for line in lines[bounds[0] + 1:bounds[1]]):
            del lines[bounds[0]:bounds[1]]
        return lines
    if index is None:
        lines.insert(bounds[0] + 1, f"{key}={value}")
    else:
        lines[index] = f"{key}={value}"
    return lines


def status(text: str, runtime: str, libva_path: str) -> dict:
    lines = text.splitlines()
    filesystems = _split_list(_value(lines, _section_bounds(lines, "Context"), "filesystems") or "")
    environment = _section_bounds(lines, "Environment")
    return {
        "filesystem": f"{runtime}:ro" in filesystems,
        "driver_name": _value(lines, environment, "LIBVA_DRIVER_NAME") == DRIVER_NAME,
        "driver_path": _value(lines, environment, "LIBVA_DRIVERS_PATH") == libva_path,
    }


def enable(text: str, runtime: str, libva_path: str) -> str:
    lines = text.splitlines()
    filesystems = _split_list(_value(lines, _section_bounds(lines, "Context"), "filesystems") or "")
    # A "!runtime" entry (an earlier --nofilesystem) would deny what is added here.
    filesystems = [item for item in filesystems if item.lstrip("!").rsplit(":", 1)[0] != runtime]
    filesystems.append(f"{runtime}:ro")
    lines = _set(lines, "Context", "filesystems", _join_list(filesystems))
    lines = _set(lines, "Environment", "LIBVA_DRIVER_NAME", DRIVER_NAME)
    lines = _set(lines, "Environment", "LIBVA_DRIVERS_PATH", libva_path)
    return "\n".join(lines) + "\n"


def disable(text: str, runtime: str, libva_path: str) -> str:
    lines = text.splitlines()
    filesystems = _split_list(_value(lines, _section_bounds(lines, "Context"), "filesystems") or "")
    filesystems = [item for item in filesystems if item.lstrip("!").rsplit(":", 1)[0] != runtime]
    lines = _set(lines, "Context", "filesystems", _join_list(filesystems) or None)
    environment = _section_bounds(lines, "Environment")
    # Only what this script wrote: a driver name or path someone else chose stays.
    # The path is ours when it starts with our folder, with or without the 32-bit one after it.
    if _value(lines, environment, "LIBVA_DRIVER_NAME") == DRIVER_NAME:
        lines = _set(lines, "Environment", "LIBVA_DRIVER_NAME", None)
    environment = _section_bounds(lines, "Environment")
    current = _value(lines, environment, "LIBVA_DRIVERS_PATH") or ""
    if current == libva_path or current.split(":")[0] == runtime:
        lines = _set(lines, "Environment", "LIBVA_DRIVERS_PATH", None)
    return "\n".join(lines) + "\n" if any(line.strip() for line in lines) else ""


def _write(path: Path, text: str) -> None:
    if not text:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".global.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in {"status", "enable", "disable"}:
        print(__doc__, file=sys.stderr)
        return 64
    action, runtime, libva_path = argv[1:]
    path = override_file()
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as error:
        print(f"ERROR: {path} could not be read: {error}", file=sys.stderr)
        return 1
    if action == "status":
        print(json.dumps(status(text, runtime, libva_path)))
        return 0
    result = (enable if action == "enable" else disable)(text, runtime, libva_path)
    try:
        _write(path, result)
    except OSError as error:
        print(f"ERROR: {path} could not be written: {error}", file=sys.stderr)
        return 1
    print(f"[OK] Flatpak apps {'can now use' if action == 'enable' else 'no longer use'} the BC-250 video driver.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
