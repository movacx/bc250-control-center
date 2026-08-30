"""Pure parser for upstream bc250_smu_oc overclock configuration."""

from __future__ import annotations

import configparser
import os
import stat
from pathlib import Path

from bc250cc.domain.cpu import (
    FREQUENCY_RANGE,
    SCALE_RANGE,
    TEMPERATURE_RANGE,
    estimated_vid,
)


def parse_cpu_oc_config(text: str, *, path: str = "") -> dict[str, object]:
    result: dict[str, object] = {
        "path": path,
        "exists": True,
        "readable": True,
        "valid": False,
        "error": "",
        "error_kind": "",
    }
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(text)
        frequency = parser.getint("overclock", "frequency")
        scale = parser.getint("overclock", "scale")
        temperature = parser.getint("overclock", "max_temperature")
    except (configparser.Error, ValueError) as error:
        result.update(
            error=f"Invalid CPU OC configuration: {error}", error_kind="parse"
        )
        return result
    if not FREQUENCY_RANGE[0] <= frequency <= FREQUENCY_RANGE[1]:
        result.update(
            error=f"CPU OC frequency is outside 3500-4200 MHz: {frequency}",
            error_kind="range",
        )
        return result
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        result.update(
            error=f"CPU OC scale is outside -50 to 0: {scale}", error_kind="range"
        )
        return result
    if not TEMPERATURE_RANGE[0] <= temperature <= TEMPERATURE_RANGE[1]:
        result.update(
            error=f"CPU OC temperature is outside 70-90 C: {temperature}",
            error_kind="range",
        )
        return result
    result.update({
        "valid": True,
        "frequency": frequency,
        "scale": scale,
        "max_temperature": temperature,
        "estimated_vid": estimated_vid(frequency, scale),
        "vid_source": "upstream-curve-estimate",
    })
    return result


def _error(path: Path, *, exists: bool, message: str, kind: str) -> dict[str, object]:
    return {
        "path": str(path), "exists": exists, "readable": False,
        "valid": False, "error": message, "error_kind": kind,
    }


def _read_descriptor(descriptor: int, maximum: int) -> bytes:
    chunks = []
    remaining = maximum + 1
    while remaining:
        chunk = os.read(descriptor, min(16 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _preflight(source: Path, maximum: int):
    try:
        metadata = source.lstat()
    except FileNotFoundError:
        return None, _error(source, exists=False, message="", kind="")
    except PermissionError as error:
        return None, _error(
            source, exists=False,
            message=f"CPU OC configuration metadata is protected: {error}",
            kind="permission",
        )
    except OSError as error:
        return None, _error(
            source, exists=False,
            message=f"Could not read CPU OC configuration metadata: {error}", kind="io",
        )
    if not stat.S_ISREG(metadata.st_mode):
        return None, _error(
            source, exists=True,
            message="CPU OC configuration is not a regular file.", kind="type",
        )
    if metadata.st_size > maximum:
        return None, _error(
            source, exists=True,
            message="CPU OC configuration is unexpectedly large.", kind="size",
        )
    return metadata, None


def read_cpu_oc_config(path: str | Path, *, maximum: int = 64 * 1024) -> dict[str, object]:
    """Read one bounded regular file and parse the exact opened descriptor."""
    source = Path(path)
    _metadata, preflight_error = _preflight(source, maximum)
    if preflight_error is not None:
        return preflight_error
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            return _error(
                source, exists=True,
                message="CPU OC configuration is not a regular file.", kind="type",
            )
        content = _read_descriptor(descriptor, maximum)
        if opened.st_size > maximum or len(content) > maximum:
            return _error(
                source, exists=True,
                message="CPU OC configuration is unexpectedly large.", kind="size",
            )
        text = content.decode("utf-8")
    except PermissionError as error:
        return _error(
            source, exists=True,
            message=f"CPU OC configuration is protected from the desktop session: {error}",
            kind="permission",
        )
    except (OSError, UnicodeError) as error:
        return _error(
            source, exists=True,
            message=f"Could not read CPU OC configuration: {error}", kind="io",
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return parse_cpu_oc_config(text, path=str(source))
