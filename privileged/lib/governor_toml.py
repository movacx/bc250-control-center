from __future__ import annotations

import os
import re
import sys
import tempfile
import tomllib
from contextlib import suppress
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

_TABLE_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")
_COMMENTED_TABLE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)\[(?P<section>[^\[\]]+)\]\s*(?P<tail>#.*)?$"
)
_ARRAY_TABLE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?\[\[safe-points\]\]\s*(?:#.*)?$"
)
_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?(?P<key>min|max|frequency|voltage)"
    r"(?P<spacing>\s*=\s*)(?P<value>[0-9][0-9_]*)?(?P<tail>\s*(?:#.*)?)$"
)
_GPU_USAGE_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?(?P<key>fix-metrics|fix-freq|fix_freq|method)"
    r"(?P<spacing>\s*=\s*)(?P<value>[^#\r\n]+?)(?P<tail>\s*(?:#.*)?)$"
)
_GPU_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?(?P<key>set-method)"
    r"(?P<spacing>\s*=\s*)(?P<value>[^#\r\n]+?)(?P<tail>\s*(?:#.*)?)$"
)

# Exact safe-point curve reviewed for cyan-skillfish-governor-smu v0.4.12.
# (smu/default-config.toml). Keep this as the single source of truth for the
# UI and the privileged voltage helper.
GOVERNOR_DEFAULT_SAFE_POINTS = (
    (500, 700),
    (1000, 800),
    (1175, 850),
    (1500, 900),
    (1600, 910),
    (1700, 920),
    (1850, 930),
    (2000, 960),
    (2050, 980),
    (2100, 1000),
    (2125, 1020),
    (2150, 1035),
    (2200, 1050),
    (2230, 1085),
    (2300, 1110),
    (2350, 1130),
    (2400, 1150),
)
GOVERNOR_DEFAULT_VOLTAGES = dict(GOVERNOR_DEFAULT_SAFE_POINTS)
SUPPORTED_VOLTAGE_LEVELS = (0, 3, 6)
VOLTAGE_BOOST_START_MHZ = 2000
CUSTOM_VOLTAGE_MIN_MV = 600
CUSTOM_VOLTAGE_MAX_MV = 1210
OBERON_FREQUENCY_MIN_MHZ = 500
OBERON_FREQUENCY_MAX_MHZ = 2400
# The upstream sample is deliberately permissive, but the installation guide
# warns that lower values have caused freezes/black screens on community
# boards. The control center therefore never writes a value below 920 mV.
OBERON_SAFE_VOLTAGE_MIN_MV = 920
OBERON_SAFE_VOLTAGE_MAX_MV = 1210

_YAML_SECTION_RE = re.compile(
    r"^(?P<indent> *)(?:-\s+)?(?P<section>frequency|voltage)\s*:\s*(?P<tail>#.*)?$"
)
_YAML_BOUND_RE = re.compile(
    r"^(?P<indent> *)(?P<dash>-\s+)?(?P<key>min|max)(?P<spacing>\s*:\s*)"
    r"(?P<value>[0-9]+)(?P<tail>\s*(?:#.*)?)$"
)


class GovernorTomlError(RuntimeError):
    pass


class OberonYamlError(RuntimeError):
    pass


@dataclass(frozen=True)
class TomlEditResult:
    changed: bool
    frequencies: tuple[int, ...] = ()


@dataclass(frozen=True)
class _SafePointBlock:
    start: int
    end: int
    frequency: int
    voltage: int
    active: bool


def _uncommented(line: str) -> str:
    match = _ARRAY_TABLE_RE.match(line) or _KEY_RE.match(line)
    if not match or not match.groupdict().get("comment"):
        return line
    start, end = match.span("comment")
    return line[:start] + line[end:]


def _commented(line: str) -> str:
    match = _ARRAY_TABLE_RE.match(line) or _KEY_RE.match(line)
    if not match or match.groupdict().get("comment"):
        return line
    position = len(match.group("indent"))
    return line[:position] + "# " + line[position:]


def _commented_table(line: str) -> str:
    """Comment a normal TOML table header without touching its spelling."""
    if _COMMENTED_TABLE_RE.match(line):
        return line
    match = _TABLE_RE.match(line)
    if not match:
        return line
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}# {line[len(indent) :]}"


def _uncommented_table(line: str) -> str:
    match = _COMMENTED_TABLE_RE.match(line)
    if not match:
        return line
    start, end = match.span("comment")
    return line[:start] + line[end:]


def _parse_int(match: re.Match[str]) -> int | None:
    raw = match.groupdict().get("value")
    if not raw:
        return None
    try:
        return int(raw.replace("_", ""))
    except ValueError:
        return None


def _safe_point_blocks(lines: list[str]):
    index = 0
    while index < len(lines):
        header = _ARRAY_TABLE_RE.match(lines[index].rstrip("\r\n"))
        if not header:
            index += 1
            continue
        end = index + 1
        while end < len(lines):
            body = lines[end].rstrip("\r\n")
            if _ARRAY_TABLE_RE.match(body) or _TABLE_RE.match(body):
                break
            end += 1
        yield index, end, header
        index = end


def _block_frequency(lines: list[str], start: int, end: int) -> tuple[int | None, bool]:
    for candidate in range(start + 1, end):
        match = _KEY_RE.match(lines[candidate].rstrip("\r\n"))
        if match and match.group("key") == "frequency":
            return _parse_int(match), bool(match.group("comment"))
    return None, False


def _block_voltage(lines: list[str], start: int, end: int) -> tuple[int | None, bool]:
    for candidate in range(start + 1, end):
        match = _KEY_RE.match(lines[candidate].rstrip("\r\n"))
        if match and match.group("key") == "voltage":
            return _parse_int(match), bool(match.group("comment"))
    return None, False


def _parsed_safe_point_blocks(lines: list[str]) -> tuple[_SafePointBlock, ...]:
    parsed: list[_SafePointBlock] = []
    for start, end, header in _safe_point_blocks(lines):
        frequency, frequency_commented = _block_frequency(lines, start, end)
        voltage, voltage_commented = _block_voltage(lines, start, end)
        if frequency is None or voltage is None:
            continue
        parsed.append(
            _SafePointBlock(
                start=start,
                end=end,
                frequency=int(frequency),
                voltage=int(voltage),
                active=(
                    not bool(header.group("comment"))
                    and not frequency_commented
                    and not voltage_commented
                ),
            )
        )
    return tuple(parsed)


def _replace_block_voltage(
    lines: list[str],
    start: int,
    end: int,
    voltage: int,
) -> bool:
    for candidate in range(start + 1, end):
        line = lines[candidate]
        body = line.rstrip("\r\n")
        match = _KEY_RE.match(body)
        if not match or match.group("key") != "voltage":
            continue
        ending = line[len(body) :]
        replacement = (
            f"{match.group('indent')}{match.group('comment') or ''}"
            f"voltage{match.group('spacing')}{int(voltage)}{match.group('tail')}"
        )
        lines[candidate] = replacement + ending
        return replacement != body
    return False


def _transform_safe_point_block(
    lines: list[str], start: int, end: int, *, enabled: bool
) -> None:
    for line_index in range(start, end):
        body = lines[line_index].rstrip("\r\n")
        ending = lines[line_index][len(body) :]
        if line_index == start or _KEY_RE.match(body):
            transformed = _uncommented(body) if enabled else _commented(body)
            lines[line_index] = transformed + ending


def voltage_profile(level: int) -> dict[int, int]:
    """Return a complete level curve based on the governor's packaged defaults.

    Level 0 is an exact restoration. Levels 3 and 6 add 30/60 mV to every
    point from 2000 MHz onward; lower-frequency defaults remain untouched.
    """

    try:
        normalized = int(level)
    except (TypeError, ValueError) as error:
        raise GovernorTomlError("Voltage level must be an integer.") from error
    if normalized not in SUPPORTED_VOLTAGE_LEVELS:
        allowed = ", ".join(str(item) for item in SUPPORTED_VOLTAGE_LEVELS)
        raise GovernorTomlError(
            f"Unsupported voltage level {normalized}; use {allowed}."
        )
    addition = normalized * 10
    return {
        frequency: voltage + (addition if frequency >= VOLTAGE_BOOST_START_MHZ else 0)
        for frequency, voltage in GOVERNOR_DEFAULT_SAFE_POINTS
    }


def validate_voltage_curve(values: dict[int, int]) -> None:
    previous_frequency: int | None = None
    previous_voltage: int | None = None
    for frequency, voltage in sorted((int(f), int(v)) for f, v in values.items()):
        if frequency <= 0:
            raise GovernorTomlError(f"Invalid safe-point frequency: {frequency}.")
        if voltage <= 0:
            raise GovernorTomlError(
                f"Invalid voltage at {frequency} MHz: {voltage} mV."
            )
        if previous_voltage is not None and voltage < previous_voltage:
            raise GovernorTomlError(
                f"Voltage decreases from {previous_voltage} mV at "
                f"{previous_frequency} MHz to {voltage} mV at {frequency} MHz."
            )
        previous_frequency = frequency
        previous_voltage = voltage


def _validate_voltage_targets(
    existing: dict[int, int],
    requested: dict[int, int],
    required: set[int],
) -> None:
    missing = sorted(required.difference(existing))
    if missing:
        joined = ", ".join(str(item) for item in missing)
        raise GovernorTomlError(
            "The governor TOML does not contain every required packaged "
            f"safe-point. Missing MHz: {joined}. No voltage was changed."
        )
    unknown = sorted(set(requested).difference(existing))
    if unknown:
        joined = ", ".join(str(item) for item in unknown)
        raise GovernorTomlError(
            f"The requested safe-points are not present in the governor TOML: {joined} MHz."
        )


class GovernorTomlEditor:
    """Transactional, format-preserving edits for the governor TOML.

    The document is parsed before and after every change. Only recognized keys
    in the requested section/block are modified; all unrelated bytes remain
    untouched.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> str:
        try:
            metadata = self.path.lstat()
        except OSError as error:
            raise GovernorTomlError(
                f"Governor configuration is unavailable: {error}"
            ) from error
        if self.path.is_symlink() or not self.path.is_file():
            raise GovernorTomlError(
                "Governor configuration must be a regular, non-symlink file."
            )
        if metadata.st_size > 2 * 1024 * 1024:
            raise GovernorTomlError("Governor configuration is unexpectedly large.")
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise GovernorTomlError(
                f"Governor configuration could not be read: {error}"
            ) from error

    @staticmethod
    def _validate(text: str) -> None:
        try:
            tomllib.loads(text)
        except (tomllib.TOMLDecodeError, ValueError) as error:
            raise GovernorTomlError(
                f"Governor TOML validation failed: {error}"
            ) from error

    def _write(self, original: str, updated: str) -> bool:
        if updated == original:
            return False
        self._validate(updated)
        metadata = self.path.stat(follow_symlinks=False)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, metadata.st_mode & 0o777)
            with suppress(PermissionError):
                os.chown(temporary, metadata.st_uid, metadata.st_gid)
            if self.path.is_symlink():
                raise GovernorTomlError(
                    "Governor configuration changed to a symlink during the edit."
                )
            os.replace(temporary, self.path)
            return True
        except OSError as error:
            raise GovernorTomlError(
                f"Governor configuration could not be updated: {error}"
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _frequency_range_lines(self, lines: list[str]) -> tuple[list[int], list[int]]:
        """Return the section header and its recognized min/max lines.

        Both an active and a deliberately commented ``[frequency-range]``
        header are recognized.  This keeps profile mode deterministic: a
        profile disables the *complete* section, while custom range mode can
        restore exactly that same section without rewriting unrelated TOML.
        """
        section_headers: list[int] = []
        keys: list[int] = []
        inside = False
        for index, line in enumerate(lines):
            body = line.rstrip("\r\n")
            table = _TABLE_RE.match(body)
            commented_table = _COMMENTED_TABLE_RE.match(body)
            if table or commented_table:
                section = (
                    table.group(1) if table else commented_table.group("section")
                ).strip()
                inside = section == "frequency-range"
                if inside:
                    section_headers.append(index)
                continue
            if not inside:
                continue
            key = _KEY_RE.match(body)
            if key and key.group("key") in {"min", "max"}:
                keys.append(index)
        return section_headers, keys

    @staticmethod
    def _gpu_usage_layout(lines: list[str]) -> tuple[dict[str, int], int]:
        """Locate one gpu-usage table and reject duplicate managed keys."""
        headers = 0
        keys: dict[str, int] = {}
        inside = False
        insertion = -1
        for index, line in enumerate(lines):
            body = line.rstrip("\r\n")
            table = _TABLE_RE.match(body)
            if table:
                if inside and insertion < 0:
                    insertion = index
                inside = table.group(1).strip() == "gpu-usage"
                headers += int(inside)
                continue
            match = _GPU_USAGE_KEY_RE.match(body) if inside else None
            if match is None:
                continue
            key = "fix-freq" if match.group("key") == "fix_freq" else match.group("key")
            if key in keys:
                raise GovernorTomlError(
                    f"Duplicate gpu-usage.{key} key in governor TOML."
                )
            keys[key] = index
        if inside and insertion < 0:
            insertion = len(lines)
        if headers != 1:
            raise GovernorTomlError(
                "The governor TOML requires exactly one [gpu-usage] section."
            )
        return keys, insertion

    @staticmethod
    def _replace_gpu_usage_value(line: str, key: str, value: str) -> str:
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = _GPU_USAGE_KEY_RE.match(body)
        if match is None:
            raise GovernorTomlError(f"gpu-usage.{key} changed during telemetry edit.")
        return (
            f"{match.group('indent')}{key}{match.group('spacing')}"
            f"{value}{match.group('tail')}" + ending
        )

    def _edit_gpu_usage_values(self, desired: dict[str, str]) -> TomlEditResult:
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        self._apply_gpu_usage_values(lines, desired, original)
        return TomlEditResult(self._write(original, "".join(lines)))

    def _apply_gpu_usage_values(
        self, lines: list[str], desired: dict[str, str], original: str
    ) -> None:
        keys, insertion = self._gpu_usage_layout(lines)
        additions: list[str] = []
        newline = "\r\n" if "\r\n" in original else "\n"
        for key, value in desired.items():
            index = keys.get(key)
            if index is None:
                additions.append(f"{key} = {value}{newline}")
                continue
            lines[index] = self._replace_gpu_usage_value(lines[index], key, value)
        if additions:
            if insertion > 0 and not lines[insertion - 1].endswith(("\n", "\r")):
                lines[insertion - 1] += newline
            lines[insertion:insertion] = additions

    @staticmethod
    def _gpu_layout(lines: list[str]) -> tuple[dict[str, int], int]:
        headers = 0
        keys: dict[str, int] = {}
        inside = False
        insertion = -1
        for index, line in enumerate(lines):
            body = line.rstrip("\r\n")
            table = _TABLE_RE.match(body)
            if table:
                if inside and insertion < 0:
                    insertion = index
                inside = table.group(1).strip() == "gpu"
                headers += int(inside)
                continue
            match = _GPU_KEY_RE.match(body) if inside else None
            if match is None:
                continue
            key = match.group("key")
            if key in keys:
                raise GovernorTomlError(f"Duplicate gpu.{key} key in governor TOML.")
            keys[key] = index
        if inside and insertion < 0:
            insertion = len(lines)
        if headers != 1:
            raise GovernorTomlError(
                "The governor TOML requires exactly one [gpu] section."
            )
        return keys, insertion

    @staticmethod
    def _replace_gpu_value(line: str, key: str, value: str) -> str:
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = _GPU_KEY_RE.match(body)
        if match is None:
            raise GovernorTomlError(f"gpu.{key} changed during compatibility edit.")
        return (
            f"{match.group('indent')}{key}{match.group('spacing')}"
            f"{value}{match.group('tail')}" + ending
        )

    def _apply_gpu_values(
        self, lines: list[str], desired: dict[str, str], original: str
    ) -> None:
        has_gpu_section = any(
            bool(_TABLE_RE.match(line.rstrip("\r\n")))
            and _TABLE_RE.match(line.rstrip("\r\n")).group(1).strip() == "gpu"
            for line in lines
        )
        if not has_gpu_section:
            newline = "\r\n" if "\r\n" in original else "\n"
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            if lines and lines[-1].strip():
                lines.append(newline)
            lines.append(f"[gpu]{newline}")
        keys, insertion = self._gpu_layout(lines)
        additions: list[str] = []
        newline = "\r\n" if "\r\n" in original else "\n"
        for key, value in desired.items():
            index = keys.get(key)
            if index is None:
                additions.append(f"{key} = {value}{newline}")
                continue
            lines[index] = self._replace_gpu_value(lines[index], key, value)
        if additions:
            if insertion > 0 and not lines[insertion - 1].endswith(("\n", "\r")):
                lines[insertion - 1] += newline
            lines[insertion:insertion] = additions

    def ensure_gpu_telemetry(
        self, *, fix_frequency: bool = False, fix_metrics: bool | None = None
    ) -> TomlEditResult:
        """Validate Cyan telemetry while preserving a known metrics incompatibility.

        ``fix-metrics`` is optional upstream.  An explicitly disabled value is
        retained across dependency preparation; fresh/missing configurations
        retain Cyan's upstream default of ``true``.  ``fix-freq`` remains an
        independent BC-250 compatibility switch and is never forced by this
        helper.
        """
        original = self._read()
        self._validate(original)
        parsed = tomllib.loads(original)
        section = parsed.get("gpu-usage")
        if section is None:
            section = parsed.get("gpu_usage")
        if not isinstance(section, dict):
            section = {}
        method = str(section.get("method") or "").strip().lower()

        desired = {
            "fix-freq": "true" if bool(fix_frequency) else "false",
        }
        # ``method`` selects how Cyan measures GPU load.  It is independent
        # from fix-metrics/fix-freq and must not be silently reset during a
        # telemetry repair.  Only repair a missing/invalid value.
        if method not in {"busy-flag", "process", "kernel"}:
            desired["method"] = '"busy-flag"'
        if fix_metrics is not None:
            desired["fix-metrics"] = "true" if bool(fix_metrics) else "false"
        else:
            keys, _insertion = self._gpu_usage_layout(
                original.splitlines(keepends=True)
            )
            if "fix-metrics" not in keys:
                desired["fix-metrics"] = "true"
        return self._edit_gpu_usage_values(desired)

    def set_gpu_metrics_fix(self, enabled: bool) -> TomlEditResult:
        """Explicitly toggle only Cyan's optional GPU-usage overlay."""
        return self._edit_gpu_usage_values(
            {
                "fix-metrics": "true" if bool(enabled) else "false",
            }
        )

    def set_cyan_compatibility(
        self,
        *,
        set_method: str,
        usage_method: str,
        fix_metrics: bool,
        fix_frequency: bool,
    ) -> TomlEditResult:
        """Atomically set Cyan's independent backend and usage switches."""
        normalized_set_method = str(set_method).strip().lower()
        if normalized_set_method not in {"smu", "kernel"}:
            raise GovernorTomlError("Cyan gpu.set-method must be smu or kernel.")
        normalized_usage_method = str(usage_method).strip().lower()
        if normalized_usage_method not in {"busy-flag", "process", "kernel"}:
            raise GovernorTomlError(
                "Cyan gpu-usage.method must be busy-flag, process or kernel."
            )
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        self._apply_gpu_usage_values(
            lines,
            {
                "fix-metrics": "true" if bool(fix_metrics) else "false",
                "fix-freq": "true" if bool(fix_frequency) else "false",
                "method": f'"{normalized_usage_method}"',
            },
            original,
        )
        self._apply_gpu_values(
            lines, {"set-method": f'"{normalized_set_method}"'}, original
        )
        return TomlEditResult(self._write(original, "".join(lines)))

    def gpu_telemetry_state(self) -> dict[str, object]:
        parsed = tomllib.loads(self._read())
        section = parsed.get("gpu-usage")
        if not isinstance(section, dict):
            raise GovernorTomlError("The [gpu-usage] section is missing or invalid.")
        method = str(section.get("method") or "busy-flag").strip().lower()
        gpu_section = parsed.get("gpu")
        if gpu_section is None:
            gpu_section = {}
        if not isinstance(gpu_section, dict):
            raise GovernorTomlError("The [gpu] section is invalid.")
        set_method = str(gpu_section.get("set-method") or "smu").strip().lower()
        return {
            "fix_metrics": bool(section.get("fix-metrics", True)),
            "fix_frequency": bool(
                section.get("fix-freq", section.get("fix_freq", False))
            ),
            "method": method,
            "set_method": set_method,
            "valid": (
                method in {"busy-flag", "process", "kernel"}
                and set_method in {"smu", "kernel"}
            ),
        }

    @staticmethod
    def _replace_range_value(
        line: str, key_name: str, value: int | None, *, enabled: bool
    ) -> str:
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = _KEY_RE.match(body)
        if not match or match.group("key") != key_name:
            return line
        text_value = "0" if value is None else str(int(value))
        replacement = (
            f"{match.group('indent')}{'' if enabled else '# '}"
            f"{key_name}{match.group('spacing')}{text_value}{match.group('tail')}"
        )
        return replacement + ending

    def clear_frequency_range(self) -> TomlEditResult:
        """Disable the whole optional range section for preset/profile mode."""
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        headers, keys = self._frequency_range_lines(lines)
        for header in headers:
            body = lines[header].rstrip("\r\n")
            ending = lines[header][len(body) :]
            lines[header] = _commented_table(body) + ending
        for index in keys:
            body = lines[index].rstrip("\r\n")
            ending = lines[index][len(body) :]
            lines[index] = _commented(body) + ending
        updated = "".join(lines)
        return TomlEditResult(self._write(original, updated))

    def set_frequency_range(
        self, minimum: int | None, maximum: int | None
    ) -> TomlEditResult:
        """Enable and update the full optional governor range section.

        ``None`` means an explicit unlimited bound (``0`` in upstream TOML).
        The operation is transactional and byte-preserving outside the two
        range keys.  A malformed or missing section is rejected rather than
        inventing configuration beside an unknown upstream layout.
        """
        if minimum is not None and int(minimum) < 0:
            raise GovernorTomlError("Frequency range minimum cannot be negative.")
        if maximum is not None and int(maximum) < 0:
            raise GovernorTomlError("Frequency range maximum cannot be negative.")
        if minimum and maximum and int(minimum) > int(maximum):
            raise GovernorTomlError("Frequency range minimum cannot exceed maximum.")
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        headers, keys = self._frequency_range_lines(lines)
        if not headers:
            raise GovernorTomlError(
                "The governor TOML does not contain a [frequency-range] section."
            )
        if len(headers) != 1:
            raise GovernorTomlError(
                "The governor TOML contains duplicate [frequency-range] sections."
            )
        header = headers[0]
        key_indexes: dict[str, int] = {}
        for index in keys:
            match = _KEY_RE.match(lines[index].rstrip("\r\n"))
            if match:
                if match.group("key") in key_indexes:
                    raise GovernorTomlError(
                        f"The [frequency-range] section contains duplicate {match.group('key')} keys."
                    )
                key_indexes[match.group("key")] = index
        if set(key_indexes) != {"min", "max"}:
            raise GovernorTomlError(
                "The [frequency-range] section must contain both min and max keys."
            )
        body = lines[header].rstrip("\r\n")
        ending = lines[header][len(body) :]
        lines[header] = _uncommented_table(body) + ending
        lines[key_indexes["min"]] = self._replace_range_value(
            lines[key_indexes["min"]], "min", minimum, enabled=True
        )
        lines[key_indexes["max"]] = self._replace_range_value(
            lines[key_indexes["max"]], "max", maximum, enabled=True
        )
        updated = "".join(lines)
        return TomlEditResult(self._write(original, updated))

    def set_frequency_floor(self, minimum: int) -> TomlEditResult:
        """Persist only the minimum floor and leave the maximum bytes untouched.

        In a full custom range, the existing active maximum remains byte-for-byte
        unchanged. In profile mode the table and ``min`` are enabled while the
        already-commented ``max`` stays exactly as it was. This makes the floor
        control literally a minimum-only edit rather than a range rewrite.
        """
        try:
            minimum = int(minimum)
        except (TypeError, ValueError) as error:
            raise GovernorTomlError("Frequency floor must be an integer.") from error
        if minimum < 0:
            raise GovernorTomlError("Frequency floor cannot be negative.")

        state = self.frequency_range_state()
        if not state.get("valid"):
            raise GovernorTomlError(
                str(state.get("error") or "Invalid frequency-range section.")
            )
        if (
            state.get("mode") == "custom"
            and state.get("max") is not None
            and minimum > int(state["max"])
        ):
            raise GovernorTomlError(
                "Frequency floor cannot exceed the active custom maximum."
            )

        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        headers, keys = self._frequency_range_lines(lines)
        if len(headers) != 1:
            raise GovernorTomlError(
                "The governor TOML must contain exactly one [frequency-range] section."
            )

        header = headers[0]
        header_body = lines[header].rstrip("\r\n")
        header_ending = lines[header][len(header_body) :]
        lines[header] = _uncommented_table(header_body) + header_ending

        min_index = None
        for index in keys:
            match = _KEY_RE.match(lines[index].rstrip("\r\n"))
            if match and match.group("key") == "min":
                min_index = index
                break
        if min_index is None:
            raise GovernorTomlError(
                "The [frequency-range] section is missing its min key."
            )
        lines[min_index] = self._replace_range_value(
            lines[min_index], "min", minimum, enabled=True
        )
        return TomlEditResult(self._write(original, "".join(lines)))

    def frequency_range_state(self) -> dict[str, int | bool | None]:
        """Expose the effective optional range section without guessing."""
        text = self._read()
        self._validate(text)
        lines = text.splitlines(keepends=True)
        headers, keys = self._frequency_range_lines(lines)
        if not headers:
            return self._range_error(
                "The [frequency-range] section is missing.",
                present=False,
                mode="missing",
            )
        if len(headers) != 1:
            return self._range_error("Duplicate [frequency-range] sections were found.")
        header = headers[0]
        header_body = lines[header].rstrip("\r\n")
        header_enabled = not bool(_COMMENTED_TABLE_RE.match(header_body))
        values, key_enabled, error = self._range_key_state(lines, keys)
        if error:
            return self._range_error(error, values=values)
        min_enabled = key_enabled["min"]
        max_enabled = key_enabled["max"]
        profile_mode = not header_enabled and not min_enabled and not max_enabled
        custom_mode = header_enabled and min_enabled and max_enabled
        floor_mode = header_enabled and min_enabled and not max_enabled
        if not (profile_mode or custom_mode or floor_mode):
            return self._range_error(
                "The frequency-range header and its keys mix active and commented states.",
                values=values,
            )
        result = {
            "present": True,
            "enabled": header_enabled,
            "valid": True,
            "mode": "custom" if custom_mode else "floor" if floor_mode else "profile",
            "min": values["min"],
            "max": None if floor_mode else values["max"],
            "error": "",
        }
        if floor_mode:
            result["stored_max"] = values["max"]
        return result

    @staticmethod
    def _range_error(message, *, present=True, mode="conflict", values=None):
        values = values or {"min": None, "max": None}
        return {
            "present": bool(present),
            "enabled": False,
            "valid": False,
            "mode": mode,
            "min": values.get("min"),
            "max": values.get("max"),
            "error": str(message),
        }

    @staticmethod
    def _range_key_state(lines, keys):
        values: dict[str, int | None] = {"min": None, "max": None}
        enabled: dict[str, bool] = {}
        for index in keys:
            match = _KEY_RE.match(lines[index].rstrip("\r\n"))
            if match is None:
                continue
            key = match.group("key")
            if key in enabled:
                return (
                    values,
                    enabled,
                    f"Duplicate {key} keys were found in [frequency-range].",
                )
            enabled[key] = not bool(match.group("comment"))
            values[key] = _parse_int(match)
        complete = set(enabled) == {"min", "max"} and all(
            values[key] is not None for key in ("min", "max")
        )
        error = (
            ""
            if complete
            else "The [frequency-range] section requires one min and one max key."
        )
        return values, enabled, error

    def legacy_frequency_range_migration(self) -> dict[str, object]:
        """Describe only legacy states whose original intent is unambiguous.

        Older releases commented min/max but left the table active. The empty
        active table is valid TOML, yet it is not the deterministic profile
        representation used now. Two inverse forms produced by early builds
        are also recognized. Unknown mixed states remain errors rather than
        being guessed or overwritten.
        """
        text = self._read()
        self._validate(text)
        lines = text.splitlines(keepends=True)
        headers, keys = self._frequency_range_lines(lines)
        if len(headers) != 1 or len(keys) != 2:
            return {"needed": False, "target_mode": "", "reason": ""}
        header_body = lines[headers[0]].rstrip("\r\n")
        header_enabled = not bool(_COMMENTED_TABLE_RE.match(header_body))
        enabled: dict[str, bool] = {}
        values: dict[str, int | None] = {}
        for index in keys:
            match = _KEY_RE.match(lines[index].rstrip("\r\n"))
            if not match or match.group("key") in enabled:
                return {"needed": False, "target_mode": "", "reason": ""}
            enabled[match.group("key")] = not bool(match.group("comment"))
            values[match.group("key")] = _parse_int(match)
        if set(enabled) != {"min", "max"} or None in values.values():
            return {"needed": False, "target_mode": "", "reason": ""}
        signature = (header_enabled, enabled["min"], enabled["max"])
        targets = {
            (True, False, False): (
                "profile",
                "Legacy profile mode left an empty active [frequency-range] table.",
            ),
            (False, True, True): (
                "custom",
                "Legacy custom range commented only the section header.",
            ),
            (False, True, False): (
                "floor",
                "Legacy frequency floor commented only the section header.",
            ),
        }
        target = targets.get(signature)
        return {
            "needed": bool(target),
            "target_mode": target[0] if target else "",
            "reason": target[1] if target else "",
            "min": values["min"],
            "max": values["max"],
        }

    def migrate_legacy_frequency_range(self) -> TomlEditResult:
        migration = self.legacy_frequency_range_migration()
        if not migration.get("needed"):
            return TomlEditResult(False)
        target_mode = str(migration["target_mode"])
        if target_mode == "profile":
            return self.clear_frequency_range()

        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        headers, keys = self._frequency_range_lines(lines)
        header = headers[0]
        body = lines[header].rstrip("\r\n")
        ending = lines[header][len(body) :]
        lines[header] = _uncommented_table(body) + ending
        for index in keys:
            match = _KEY_RE.match(lines[index].rstrip("\r\n"))
            if not match:
                continue
            key = match.group("key")
            value = int(migration[key])
            lines[index] = self._replace_range_value(
                lines[index],
                key,
                value,
                enabled=(target_mode == "custom" or key == "min"),
            )
        return TomlEditResult(self._write(original, "".join(lines)))

    def set_high_frequency_points(self, enabled: bool) -> TomlEditResult:
        """Toggle every safe-point block above 2000 MHz transactionally.

        The safe-point blocks are the capability switch.  Persisted startup
        bounds are only adjusted when necessary to keep the TOML bootable:

        * enabling high points from profile mode pins startup to the *existing*
          non-experimental safe-point envelope, never to a hard-coded 500/2000;
        * disabling high points clamps persisted bounds to the highest/lowest
          safe points that remain active.

        Runtime frequency selection stays a D-Bus concern and is not persisted
        here.  This prevents an enable/disable action from silently selecting an
        overclock on the next governor restart.
        """
        original = self._read()
        self._validate(original)
        original_range = self.frequency_range_state()
        lines = original.splitlines(keepends=True)
        original_blocks = _parsed_safe_point_blocks(lines)

        high_blocks = [block for block in original_blocks if block.frequency > 2000]
        if not high_blocks:
            raise GovernorTomlError(
                "The governor TOML does not contain any safe-point above 2000 MHz."
            )
        frequencies = [block.frequency for block in high_blocks]
        if len(frequencies) != len(set(frequencies)):
            raise GovernorTomlError(
                "The governor TOML contains duplicate high-frequency safe-points."
            )
        for block in high_blocks:
            _transform_safe_point_block(
                lines, block.start, block.end, enabled=bool(enabled)
            )

        # Derive safe startup bounds from the actual table rather than assuming
        # upstream's default 500/2000 points are present.  This also supports
        # user-curated curves such as 1000/1500/1850.
        remaining = [
            block.frequency
            for block in _parsed_safe_point_blocks(lines)
            if block.active and block.frequency <= 2000
        ]
        if not remaining:
            raise GovernorTomlError(
                "High-frequency safe-points cannot be changed because the TOML "
                "has no active non-experimental safe-point at or below 2000 MHz."
            )
        safe_min = min(remaining)
        safe_max = max(remaining)

        headers, keys = self._frequency_range_lines(lines)
        if len(headers) == 1:
            indexes: dict[str, int] = {}
            for index in keys:
                match = _KEY_RE.match(lines[index].rstrip("\r\n"))
                if match:
                    indexes[match.group("key")] = index
            if set(indexes) == {"min", "max"}:
                header = headers[0]
                if enabled and original_range.get("mode") == "profile":
                    body = lines[header].rstrip("\r\n")
                    lines[header] = (
                        _uncommented_table(body) + lines[header][len(body) :]
                    )
                    lines[indexes["min"]] = self._replace_range_value(
                        lines[indexes["min"]], "min", safe_min, enabled=True
                    )
                    lines[indexes["max"]] = self._replace_range_value(
                        lines[indexes["max"]], "max", safe_max, enabled=True
                    )
                elif not enabled and original_range.get("enabled"):
                    raw_min = original_range.get("min")
                    raw_max = original_range.get("max")
                    if raw_min is not None and int(raw_min) > safe_max:
                        lines[indexes["min"]] = self._replace_range_value(
                            lines[indexes["min"]], "min", safe_max, enabled=True
                        )
                    elif raw_min is not None and int(raw_min) < safe_min:
                        lines[indexes["min"]] = self._replace_range_value(
                            lines[indexes["min"]], "min", safe_min, enabled=True
                        )
                    if raw_max is not None and int(raw_max) > safe_max:
                        lines[indexes["max"]] = self._replace_range_value(
                            lines[indexes["max"]], "max", safe_max, enabled=True
                        )
                    elif raw_max is not None and int(raw_max) < safe_min:
                        lines[indexes["max"]] = self._replace_range_value(
                            lines[indexes["max"]], "max", safe_min, enabled=True
                        )

        updated = "".join(lines)
        # Validate the active curve before replacing the user's file.  TOML
        # syntax alone is insufficient: enabling an incomplete or duplicate
        # active safe-point table would make Cyan fail later at service start.
        parsed_updated = tomllib.loads(updated)
        active_points = parsed_updated.get("safe-points", [])
        if not isinstance(active_points, list) or not active_points:
            raise GovernorTomlError(
                "The governor TOML has no active safe-point table after the requested edit."
            )
        active_curve: dict[int, int] = {}
        for point in active_points:
            if not isinstance(point, dict):
                raise GovernorTomlError("An active safe-point is not a TOML table.")
            frequency = point.get("frequency")
            voltage = point.get("voltage")
            if not isinstance(frequency, int) or not isinstance(voltage, int):
                raise GovernorTomlError(
                    "Every active safe-point requires integer frequency and voltage values."
                )
            frequency = int(frequency)
            if frequency in active_curve:
                raise GovernorTomlError(
                    f"Duplicate active safe-point frequency: {frequency} MHz."
                )
            active_curve[frequency] = int(voltage)
        validate_voltage_curve(active_curve)

        changed = self._write(original, updated)

        # Read the file back after the atomic replace. A helper exit code is not
        # sufficient evidence that all blocks were actually transformed.
        state = self.high_frequency_state()
        expected = set(frequencies) if enabled else set()
        actual = {int(value) for value in state.get("enabled_frequencies") or ()}
        if actual != expected:
            raise GovernorTomlError(
                "High-frequency safe-point verification failed after writing the TOML: "
                f"expected active {sorted(expected)}, found {sorted(actual)}."
            )
        final_range = self.frequency_range_state()
        if (
            enabled
            and original_range.get("mode") == "profile"
            and not (
                final_range.get("valid")
                and final_range.get("enabled")
                and int(final_range.get("min") or -1) == safe_min
                and int(final_range.get("max") or -1) == safe_max
            )
        ):
            raise GovernorTomlError(
                "High-frequency points were enabled but the safe startup range "
                f"{safe_min}-{safe_max} MHz was not preserved."
            )
        if not enabled and final_range.get("enabled"):
            final_min = final_range.get("min")
            final_max = final_range.get("max")
            if (
                final_min is not None and not safe_min <= int(final_min) <= safe_max
            ) or (final_max is not None and not safe_min <= int(final_max) <= safe_max):
                raise GovernorTomlError(
                    "High-frequency points were disabled but the persisted range "
                    "is outside the remaining active safe-point envelope."
                )
        return TomlEditResult(changed, tuple(sorted(set(frequencies))))

    def _set_voltage_values(
        self,
        values: dict[int, int],
        *,
        include_commented: bool,
        require_frequencies: set[int] | None = None,
        high_points_enabled: bool | None = None,
    ) -> TomlEditResult:
        normalized = {
            int(frequency): int(voltage) for frequency, voltage in values.items()
        }
        validate_voltage_curve(normalized)
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        blocks: list[_SafePointBlock] = []
        existing: dict[int, int] = {}
        for block in _parsed_safe_point_blocks(lines):
            if include_commented or block.active:
                existing[block.frequency] = block.voltage
                blocks.append(block)

        _validate_voltage_targets(
            existing,
            normalized,
            set(require_frequencies or ()),
        )

        resulting = dict(existing)
        resulting.update(normalized)
        validate_voltage_curve(resulting)
        changed_frequencies: list[int] = []
        for block in blocks:
            if block.frequency not in normalized:
                continue
            if _replace_block_voltage(
                lines,
                block.start,
                block.end,
                normalized[block.frequency],
            ):
                changed_frequencies.append(block.frequency)
        if high_points_enabled is not None:
            for block in blocks:
                if block.frequency > 2000:
                    _transform_safe_point_block(
                        lines,
                        block.start,
                        block.end,
                        enabled=high_points_enabled,
                    )
        updated = "".join(lines)
        return TomlEditResult(
            self._write(original, updated),
            tuple(sorted(set(changed_frequencies))),
        )

    def set_voltage_profile(self, level: int) -> TomlEditResult:
        values = voltage_profile(level)
        return self._set_voltage_values(
            values,
            include_commented=True,
            require_frequencies=set(GOVERNOR_DEFAULT_VOLTAGES),
            high_points_enabled=False if int(level) == 0 else None,
        )

    def set_custom_voltages(self, values: dict[int, int]) -> TomlEditResult:
        normalized = {
            int(frequency): int(voltage) for frequency, voltage in values.items()
        }
        if not normalized:
            raise GovernorTomlError("No custom voltage values were provided.")
        for frequency, voltage in normalized.items():
            if not CUSTOM_VOLTAGE_MIN_MV <= voltage <= CUSTOM_VOLTAGE_MAX_MV:
                raise GovernorTomlError(
                    f"Voltage outside the editor range for {frequency} MHz: "
                    f"{voltage} mV ({CUSTOM_VOLTAGE_MIN_MV}..{CUSTOM_VOLTAGE_MAX_MV} mV)."
                )
        return self._set_voltage_values(
            normalized,
            include_commented=False,
        )

    def high_frequency_state(self) -> dict[str, object]:
        text = self._read()
        self._validate(text)
        frequencies: list[int] = []
        enabled: list[int] = []
        lines = text.splitlines()
        for block in _parsed_safe_point_blocks(lines):
            if block.frequency > 2000:
                frequencies.append(block.frequency)
                if block.active:
                    enabled.append(block.frequency)
        return {
            "available": bool(frequencies),
            "frequencies": tuple(sorted(set(frequencies))),
            "enabled_frequencies": tuple(sorted(set(enabled))),
            "enabled": bool(enabled),
        }

    def safe_point_state(self) -> tuple[dict[str, int | bool], ...]:
        text = self._read()
        self._validate(text)
        lines = text.splitlines()
        points: list[dict[str, int | bool]] = []
        for block in _parsed_safe_point_blocks(lines):
            points.append(
                {
                    "frequency": block.frequency,
                    "voltage": block.voltage,
                    "active": block.active,
                }
            )
        return tuple(sorted(points, key=lambda item: int(item["frequency"])))

    def safe_point_diagnostics(self) -> dict[str, object]:
        """Return strict diagnostics for active safe-point blocks."""
        text = self._read()
        self._validate(text)
        points: list[dict[str, int]] = []
        frequencies: list[int] = []
        lines = text.splitlines()
        for start, end, header in _safe_point_blocks(lines):
            if header.group("comment"):
                continue
            frequency, frequency_commented = _block_frequency(lines, start, end)
            if frequency is None or frequency_commented:
                continue
            point = {"frequency": int(frequency)}
            voltage, voltage_commented = _block_voltage(lines, start, end)
            if voltage is not None and not voltage_commented:
                point["voltage"] = int(voltage)
            points.append(point)
            frequencies.append(int(frequency))
        with_voltage = [point for point in points if "voltage" in point]
        missing_voltage = [point for point in points if "voltage" not in point]
        ordered = sorted(with_voltage, key=lambda point: point["frequency"])
        voltage_errors = [
            {
                "previous_frequency": previous["frequency"],
                "previous_voltage": previous["voltage"],
                "frequency": current["frequency"],
                "voltage": current["voltage"],
            }
            for previous, current in pairwise(ordered)
            if current["voltage"] < previous["voltage"]
        ]
        duplicates = sorted(
            {frequency for frequency in frequencies if frequencies.count(frequency) > 1}
        )
        return {
            "points": points,
            "points_with_voltage": with_voltage,
            "max_frequency": max(frequencies, default=None),
            "max_voltage": max(
                (point["voltage"] for point in with_voltage), default=None
            ),
            "missing_voltage": missing_voltage,
            "voltage_order_errors": voltage_errors,
            "duplicate_frequencies": duplicates,
        }


@dataclass(frozen=True)
class _OberonBound:
    section: str
    key: str
    line_index: int
    value: int


class OberonYamlEditor:
    """Transactional, layout-preserving editor for Oberon's small YAML file.

    Upstream uses an ``opps`` sequence while older community instructions show
    plain mappings. Both layouts are accepted, but exactly one numeric min/max
    pair per section is required. Unknown YAML remains byte-for-byte intact.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> str:
        try:
            metadata = self.path.lstat()
        except OSError as error:
            raise OberonYamlError(
                f"Oberon configuration is unavailable: {error}"
            ) from error
        if self.path.is_symlink() or not self.path.is_file():
            raise OberonYamlError(
                "Oberon configuration must be a regular, non-symlink file."
            )
        if metadata.st_size > 1024 * 1024:
            raise OberonYamlError("Oberon configuration is unexpectedly large.")
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise OberonYamlError(
                f"Oberon configuration could not be read: {error}"
            ) from error
        if "\t" in text:
            raise OberonYamlError(
                "Tabs are not accepted in the Oberon YAML configuration."
            )
        return text

    @staticmethod
    def _bounds(text: str) -> dict[tuple[str, str], _OberonBound]:
        bounds: dict[tuple[str, str], _OberonBound] = {}
        current_section = ""
        section_indent = -1
        for index, raw_line in enumerate(text.splitlines()):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            section = _YAML_SECTION_RE.match(raw_line)
            if section:
                current_section = section.group("section")
                section_indent = len(section.group("indent"))
                continue
            indentation = len(raw_line) - len(raw_line.lstrip(" "))
            if current_section and indentation <= section_indent:
                current_section = ""
                section_indent = -1
            if not current_section:
                continue
            match = _YAML_BOUND_RE.match(raw_line)
            if not match or indentation <= section_indent:
                continue
            key = (current_section, match.group("key"))
            if key in bounds:
                raise OberonYamlError(
                    f"Duplicate {current_section}.{match.group('key')} value in Oberon YAML."
                )
            bounds[key] = _OberonBound(
                current_section, match.group("key"), index, int(match.group("value"))
            )
        required = {
            (section, bound)
            for section in ("frequency", "voltage")
            for bound in ("min", "max")
        }
        missing = sorted(required.difference(bounds))
        if missing:
            names = ", ".join(f"{section}.{bound}" for section, bound in missing)
            raise OberonYamlError(
                f"Oberon YAML is missing required numeric values: {names}."
            )
        return bounds

    @staticmethod
    def _validate_values(
        frequency_min: int,
        frequency_max: int,
        voltage_min: int,
        voltage_max: int,
        *,
        enforce_safe_voltage: bool,
    ) -> None:
        frequency_min, frequency_max, voltage_min, voltage_max = (
            int(frequency_min),
            int(frequency_max),
            int(voltage_min),
            int(voltage_max),
        )
        for label, value in (("minimum", frequency_min), ("maximum", frequency_max)):
            if not OBERON_FREQUENCY_MIN_MHZ <= value <= OBERON_FREQUENCY_MAX_MHZ:
                raise OberonYamlError(
                    f"Oberon {label} frequency must be {OBERON_FREQUENCY_MIN_MHZ}-"
                    f"{OBERON_FREQUENCY_MAX_MHZ} MHz."
                )
        if frequency_min > frequency_max:
            raise OberonYamlError("Oberon minimum frequency cannot exceed its maximum.")
        minimum_voltage = OBERON_SAFE_VOLTAGE_MIN_MV if enforce_safe_voltage else 1
        for label, value in (("minimum", voltage_min), ("maximum", voltage_max)):
            if not minimum_voltage <= value <= OBERON_SAFE_VOLTAGE_MAX_MV:
                raise OberonYamlError(
                    f"Oberon {label} voltage must be {minimum_voltage}-"
                    f"{OBERON_SAFE_VOLTAGE_MAX_MV} mV."
                )
        if voltage_min > voltage_max:
            raise OberonYamlError("Oberon minimum voltage cannot exceed its maximum.")

    def state(self) -> dict[str, object]:
        bounds = self._bounds(self._read())
        result: dict[str, object] = {
            "frequency_min": bounds[("frequency", "min")].value,
            "frequency_max": bounds[("frequency", "max")].value,
            "voltage_min": bounds[("voltage", "min")].value,
            "voltage_max": bounds[("voltage", "max")].value,
        }
        self._validate_values(
            int(result["frequency_min"]),
            int(result["frequency_max"]),
            int(result["voltage_min"]),
            int(result["voltage_max"]),
            enforce_safe_voltage=False,
        )
        result["safe_voltage"] = (
            int(result["voltage_min"]) >= OBERON_SAFE_VOLTAGE_MIN_MV
            and int(result["voltage_max"]) >= OBERON_SAFE_VOLTAGE_MIN_MV
        )
        return result

    def _write(self, original: str, updated: str) -> bool:
        if updated == original:
            return False
        self._bounds(updated)
        metadata = self.path.stat(follow_symlinks=False)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, metadata.st_mode & 0o777)
            with suppress(PermissionError):
                os.chown(temporary, metadata.st_uid, metadata.st_gid)
            if self.path.is_symlink():
                raise OberonYamlError(
                    "Oberon configuration changed to a symlink during the edit."
                )
            os.replace(temporary, self.path)
            return True
        except OSError as error:
            raise OberonYamlError(
                f"Oberon configuration could not be updated: {error}"
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def set_operating_points(
        self,
        frequency_min: int,
        frequency_max: int,
        voltage_min: int,
        voltage_max: int,
    ) -> TomlEditResult:
        values = {
            ("frequency", "min"): int(frequency_min),
            ("frequency", "max"): int(frequency_max),
            ("voltage", "min"): int(voltage_min),
            ("voltage", "max"): int(voltage_max),
        }
        self._validate_values(
            values[("frequency", "min")],
            values[("frequency", "max")],
            values[("voltage", "min")],
            values[("voltage", "max")],
            enforce_safe_voltage=True,
        )
        original = self._read()
        bounds = self._bounds(original)
        lines = original.splitlines(keepends=True)
        for key, value in values.items():
            bound = bounds[key]
            line = lines[bound.line_index]
            body = line.rstrip("\r\n")
            ending = line[len(body) :]
            match = _YAML_BOUND_RE.match(body)
            if not match:
                raise OberonYamlError(
                    f"Oberon YAML line for {key[0]}.{key[1]} changed unexpectedly."
                )
            lines[bound.line_index] = (
                f"{match.group('indent')}{match.group('dash') or ''}{match.group('key')}"
                f"{match.group('spacing')}{value}{match.group('tail')}" + ending
            )
        updated = "".join(lines)
        parsed = self._bounds(updated)
        if any(parsed[key].value != value for key, value in values.items()):
            raise OberonYamlError(
                "Oberon YAML verification did not reproduce the requested values."
            )
        return TomlEditResult(self._write(original, updated))


def _parse_custom_pairs(raw_pairs: list[str]) -> dict[int, int]:
    values: dict[int, int] = {}
    for item in raw_pairs:
        if "=" not in item:
            raise GovernorTomlError(f"Invalid voltage pair: {item}.")
        frequency_text, voltage_text = item.split("=", 1)
        try:
            frequency = int(frequency_text)
            voltage = int(voltage_text)
        except ValueError as error:
            raise GovernorTomlError(f"Invalid voltage pair: {item}.") from error
        if frequency in values:
            raise GovernorTomlError(f"Duplicate voltage frequency: {frequency} MHz.")
        values[frequency] = voltage
    return values


def _print_profile(level: int) -> None:
    values = voltage_profile(level)
    addition = int(level) * 10
    print(
        f"Level {level}: packaged defaults +{addition} mV from {VOLTAGE_BOOST_START_MHZ} MHz"
    )
    print("MHz   original   result   added")
    print("----  --------   ------   -----")
    for frequency, original in GOVERNOR_DEFAULT_SAFE_POINTS:
        result = values[frequency]
        print(
            f"{frequency:<4}  {original:<8}   {result:<6}   {result - original:+d} mV"
        )


def _print_status(path: str) -> None:
    points = GovernorTomlEditor(path).safe_point_state()
    print(f"Config: {path}")
    print("MHz   state      current   original   delta")
    print("----  ---------  -------   --------   -----")
    for point in points:
        frequency = int(point["frequency"])
        current = int(point["voltage"])
        original = GOVERNOR_DEFAULT_VOLTAGES.get(frequency)
        delta = "--" if original is None else f"{current - original:+d} mV"
        state = "active" if bool(point["active"]) else "commented"
        original_text = "--" if original is None else str(original)
        print(
            f"{frequency:<4}  {state:<9}  {current:<7}   {original_text:<8}   {delta}"
        )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        raise GovernorTomlError("A governor TOML command is required.")
    command = arguments.pop(0)
    if command == "preview-voltage-level":
        if len(arguments) != 1:
            raise GovernorTomlError("preview-voltage-level expects one level.")
        _print_profile(int(arguments[0]))
        return 0
    if command == "status":
        if len(arguments) != 1:
            raise GovernorTomlError("status expects one TOML path.")
        _print_status(arguments[0])
        return 0
    if len(arguments) < 2:
        raise GovernorTomlError(f"{command} expects a TOML path and values.")
    path = arguments.pop(0)
    editor = GovernorTomlEditor(path)
    if command == "apply-voltage-level":
        if len(arguments) != 1:
            raise GovernorTomlError("apply-voltage-level expects one level.")
        result = editor.set_voltage_profile(int(arguments[0]))
    elif command == "apply-custom-voltage":
        result = editor.set_custom_voltages(_parse_custom_pairs(arguments))
    else:
        raise GovernorTomlError(f"Unsupported governor TOML command: {command}.")
    action = "updated" if result.changed else "already matched"
    frequencies = ", ".join(str(item) for item in result.frequencies) or "none"
    print(f"Governor voltage curve {action}; changed MHz: {frequencies}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GovernorTomlError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None
