"""The process table's rows, without Qt: the desktop and the terminal list the same applications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..i18n import count_label, current_language, tr, tr_format

#: Rows below this, with no CPU, GPU or VRAM use, are not listed unless
#: searched for: tray applets and idle helpers of a few megabytes.
SMALL_ENTRY_BYTES = 8 * 1024 * 1024


def formato_bytes(value: int | float) -> str:
    """Format byte counters locally without importing the retired GUI tree."""
    size = max(0.0, float(value or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024.0
    return "0 B"


@dataclass
class ProcessEntry:
    """One table row: an application (grouped) or a single process."""

    key: str
    name: str
    kind: str
    icon_name: str
    program: str
    processes: list
    grouped: bool = False
    steam_appid: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def memory_exact(self) -> bool:
        """Whether every process gave its PSS. One that did not (another
        user namespace, a game) makes the whole group count RSS, so PSS and
        RSS are never added together."""
        return all(getattr(process, "pss", 0) is not None for process in self.processes)

    @property
    def memory(self) -> int:
        if self.memory_exact:
            return sum(int(getattr(process, "memoria", 0) or 0) for process in self.processes)
        return sum(int(getattr(process, "rss", 0) or getattr(process, "memoria", 0) or 0)
                   for process in self.processes)

    @property
    def cpu(self) -> float | None:
        values = [getattr(process, "cpu_percent", None) for process in self.processes]
        values = [value for value in values if value is not None]
        return sum(values) if values else None

    @property
    def gpu(self) -> float | None:
        values = [getattr(process, "gpu_percent", None) for process in self.processes]
        values = [value for value in values if value is not None]
        return min(100.0, sum(values)) if values else None

    @property
    def vram(self) -> int:
        """GPU memory: VRAM plus GTT. The BC-250 keeps a small VRAM
        carve-out, so most of a game's GPU memory is GTT."""
        return self.vram_only + self.gtt

    @property
    def vram_only(self) -> int:
        return sum(int(getattr(process, "vram", 0) or 0) for process in self.processes)

    @property
    def gtt(self) -> int:
        return sum(int(getattr(process, "gtt", 0) or 0) for process in self.processes)

    def memory_tooltip(self) -> str:
        if self.memory_exact:
            return ""
        return tr("Approximate: some of these processes do not let their shared memory be measured.")

    def gpu_memory_tooltip(self) -> str:
        if not self.vram:
            return ""
        return tr_format("VRAM {v} · GTT {g}", v=formato_bytes(self.vram_only), g=formato_bytes(self.gtt))

    @property
    def threads(self) -> int:
        return sum(int(getattr(process, "threads", 0) or 0) for process in self.processes)

    @property
    def closable(self) -> list:
        return [process for process in self.processes if not bool(getattr(process, "protegido", False))]

    @property
    def protected_count(self) -> int:
        return len(self.processes) - len(self.closable)

    @property
    def fully_protected(self) -> bool:
        return not self.closable

    @property
    def paused(self) -> bool:
        closable = self.closable
        return bool(closable) and all(bool(getattr(process, "paused", False)) for process in closable)

    @property
    def started(self) -> float | None:
        times = [getattr(process, "create_time", None) for process in self.processes]
        times = [value for value in times if value]
        return min(times) if times else None

    @property
    def subtitle(self) -> str:
        if self.grouped or not self.processes:
            return count_label(len(self.processes), "process")
        return f"PID {self.processes[0].pid}"

    def status(self) -> tuple[str, str, str]:
        """(text, tone, tooltip) for the Status column."""
        if self.fully_protected:
            reasons = sorted({str(getattr(process, "razon", "") or "system") for process in self.processes})
            return "Protected", "gray", tr_format("Protected · {reasons}", reasons=", ".join(tr(r) for r in reasons[:2]))
        if self.paused:
            return "Paused", "orange", tr("Paused: it uses no CPU until it is resumed.")
        if self.protected_count:
            return "Partial", "orange", tr_format("Partial · {count} protected", count=self.protected_count)
        return "Running", "green", tr("Safe to close")

    def sort_value(self, key: str):
        if key == "name":
            return self.name.lower()
        if key == "cpu":
            return self.cpu or 0.0
        if key == "gpu":
            return self.gpu or 0.0
        if key == "vram":
            return self.vram
        return self.memory


def localized_name(default: str, names, language: str) -> str:
    """A .desktop file's Name[<locale>] for the page's language (es-419
    tries es_419, then es), or its untranslated Name."""
    if not names or not language:
        return default
    code = language.replace("-", "_")
    return names.get(code) or names.get(code.split("_", 1)[0]) or default


def build_entries(processes: Iterable, *, grouped: bool, view: str, query: str = "") -> list[ProcessEntry]:
    """Rows for the table, for one filter and an optional search."""
    rows: dict[str, ProcessEntry] = {}
    language = current_language()
    for process in processes:
        kind = str(getattr(process, "kind", "app") or "app")
        app_key = str(getattr(process, "app_key", "") or f"pid:{process.pid}")
        key = app_key if grouped else f"pid:{process.pid}"
        entry = rows.get(key)
        if entry is None:
            entry = rows[key] = ProcessEntry(
                key=key,
                name=localized_name(
                    str(getattr(process, "app_name", "") or getattr(process, "nombre", "") or "?"),
                    getattr(process, "app_names", None), language,
                ),
                kind=kind,
                icon_name=str(getattr(process, "icon", "") or ""),
                program=str(getattr(process, "program", "") or getattr(process, "nombre", "")),
                processes=[],
                steam_appid=str(getattr(process, "steam_appid", "") or ""),
            )
        entry.processes.append(process)
        # A group is an application when any of its processes is one.
        rank = {"game": 0, "app": 1, "background": 2, "system": 3}
        if rank.get(kind, 1) < rank.get(entry.kind, 1):
            entry.kind = kind
    output = []
    needle = query.strip().lower()
    for entry in rows.values():
        entry.grouped = grouped and len(entry.processes) > 1
        entry.processes.sort(key=lambda process: int(getattr(process, "memoria", 0) or 0), reverse=True)
        if needle:
            haystack = " ".join(
                f"{entry.name} {getattr(p, 'pid', '')} {getattr(p, 'nombre', '')} {getattr(p, 'comando', '')}"
                for p in entry.processes
            ).lower()
            if needle not in haystack:
                continue
        elif view == "apps" and entry.kind not in {"app", "game"}:
            continue
        elif view in {"background", "system"} and entry.kind != view:
            continue
        if not needle and view != "all" and entry.memory < SMALL_ENTRY_BYTES \
                and not entry.cpu and not entry.vram and entry.kind != "game":
            continue
        output.append(entry)
    return output
