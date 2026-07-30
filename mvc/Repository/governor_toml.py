from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import tomllib

_TABLE_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")
_ARRAY_TABLE_RE = re.compile(r"^(?P<indent>\s*)(?P<comment>#\s*)?\[\[safe-points\]\]\s*(?:#.*)?$")
_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?(?P<key>min|max|frequency|voltage)"
    r"(?P<spacing>\s*=\s*)(?P<value>[0-9][0-9_]*)?(?P<tail>\s*(?:#.*)?)$"
)

# Exact safe-point curve shipped by cyan-skillfish-governor-smu v0.4.11
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


class GovernorTomlError(RuntimeError):
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
        ending = line[len(body):]
        replacement = (
            f"{match.group('indent')}{match.group('comment') or ''}"
            f"voltage{match.group('spacing')}{int(voltage)}{match.group('tail')}"
        )
        lines[candidate] = replacement + ending
        return replacement != body
    return False


def _transform_safe_point_block(lines: list[str], start: int, end: int, *, enabled: bool) -> None:
    for line_index in range(start, end):
        body = lines[line_index].rstrip("\r\n")
        ending = lines[line_index][len(body):]
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
        raise GovernorTomlError(f"Unsupported voltage level {normalized}; use {allowed}.")
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
            raise GovernorTomlError(f"Invalid voltage at {frequency} MHz: {voltage} mV.")
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
            raise GovernorTomlError(f"Governor configuration is unavailable: {error}") from error
        if self.path.is_symlink() or not self.path.is_file():
            raise GovernorTomlError("Governor configuration must be a regular, non-symlink file.")
        if metadata.st_size > 2 * 1024 * 1024:
            raise GovernorTomlError("Governor configuration is unexpectedly large.")
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise GovernorTomlError(f"Governor configuration could not be read: {error}") from error

    @staticmethod
    def _validate(text: str) -> None:
        try:
            tomllib.loads(text)
        except (tomllib.TOMLDecodeError, ValueError) as error:
            raise GovernorTomlError(f"Governor TOML validation failed: {error}") from error

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
            try:
                os.chown(temporary, metadata.st_uid, metadata.st_gid)
            except PermissionError:
                pass
            if self.path.is_symlink():
                raise GovernorTomlError("Governor configuration changed to a symlink during the edit.")
            os.replace(temporary, self.path)
            return True
        except OSError as error:
            raise GovernorTomlError(f"Governor configuration could not be updated: {error}") from error
        finally:
            temporary.unlink(missing_ok=True)

    def clear_frequency_range(self) -> TomlEditResult:
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        section = ""
        for index, line in enumerate(lines):
            body = line.rstrip("\r\n")
            table = _TABLE_RE.match(body)
            if table:
                section = table.group(1).strip()
                continue
            if section != "frequency-range":
                continue
            key = _KEY_RE.match(body)
            if key and key.group("key") in {"min", "max"} and not key.group("comment"):
                ending = line[len(body):]
                lines[index] = _commented(body) + ending
        updated = "".join(lines)
        return TomlEditResult(self._write(original, updated))

    def set_high_frequency_points(self, enabled: bool) -> TomlEditResult:
        original = self._read()
        self._validate(original)
        lines = original.splitlines(keepends=True)
        blocks: list[tuple[int, int, int]] = []
        for start, end, _header in _safe_point_blocks(lines):
            frequency, _commented_frequency = _block_frequency(lines, start, end)
            if frequency is not None and frequency > 2000:
                blocks.append((start, end, frequency))

        frequencies: list[int] = []
        for start, end, frequency in blocks:
            frequencies.append(frequency)
            _transform_safe_point_block(lines, start, end, enabled=enabled)
        updated = "".join(lines)
        return TomlEditResult(
            self._write(original, updated),
            tuple(sorted(set(frequencies))),
        )

    def _set_voltage_values(
        self,
        values: dict[int, int],
        *,
        include_commented: bool,
        require_frequencies: set[int] | None = None,
        high_points_enabled: bool | None = None,
    ) -> TomlEditResult:
        normalized = {int(frequency): int(voltage) for frequency, voltage in values.items()}
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
        normalized = {int(frequency): int(voltage) for frequency, voltage in values.items()}
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
    print(f"Level {level}: packaged defaults +{addition} mV from {VOLTAGE_BOOST_START_MHZ} MHz")
    print("MHz   original   result   added")
    print("----  --------   ------   -----")
    for frequency, original in GOVERNOR_DEFAULT_SAFE_POINTS:
        result = values[frequency]
        print(f"{frequency:<4}  {original:<8}   {result:<6}   {result - original:+d} mV")


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
            f"{frequency:<4}  {state:<9}  {current:<7}   "
            f"{original_text:<8}   {delta}"
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
        raise SystemExit(1)
