from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile
import tomllib


_TABLE_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")
_ARRAY_TABLE_RE = re.compile(r"^(?P<indent>\s*)(?P<comment>#\s*)?\[\[safe-points\]\]\s*(?:#.*)?$")
_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?(?P<key>min|max|frequency|voltage)"
    r"(?P<spacing>\s*=\s*)(?P<value>[0-9][0-9_]*)?(?P<tail>\s*(?:#.*)?)$"
)


class GovernorTomlError(RuntimeError):
    pass


@dataclass(frozen=True)
class TomlEditResult:
    changed: bool
    frequencies: tuple[int, ...] = ()


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


def _transform_safe_point_block(lines: list[str], start: int, end: int, *, enabled: bool) -> None:
    for line_index in range(start, end):
        body = lines[line_index].rstrip("\r\n")
        ending = lines[line_index][len(body):]
        if line_index == start or _KEY_RE.match(body):
            transformed = _uncommented(body) if enabled else _commented(body)
            lines[line_index] = transformed + ending


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

    def high_frequency_state(self) -> dict[str, object]:
        text = self._read()
        self._validate(text)
        frequencies: list[int] = []
        enabled: list[int] = []
        lines = text.splitlines()
        for start, end, header in _safe_point_blocks(lines):
            frequency, frequency_commented = _block_frequency(lines, start, end)
            if frequency and frequency > 2000:
                frequencies.append(frequency)
                if not header.group("comment") and not frequency_commented:
                    enabled.append(frequency)
        return {
            "available": bool(frequencies),
            "frequencies": tuple(sorted(set(frequencies))),
            "enabled_frequencies": tuple(sorted(set(enabled))),
            "enabled": bool(enabled),
        }
