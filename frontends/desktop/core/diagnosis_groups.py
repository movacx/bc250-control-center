"""Which tab a diagnosis section belongs to; shared by the dialog and the terminal UI."""

from __future__ import annotations

#: (key, label) of the tabs, in order. "all" shows every section.
TABS = (("all", "All"), ("hardware", "Hardware"), ("system", "System"), ("logs", "Logs"))
#: Sections about the board itself, as the report's hardware diagnosis names them.
HARDWARE_TITLES = frozenset({
    "kernel", "previous boot", "black box", "modules", "sensors (hwmon)", "sensors", "gpu", "gpu device",
    "graphics stack", "system setup helper", "steamos", "services",
})


def section_group(title: str) -> str:
    """Which tab a section belongs to: logs, hardware, or the rest of the system."""
    lowered = str(title).lower()
    if "log" in lowered or "journal" in lowered:
        return "logs"
    return "hardware" if lowered in HARDWARE_TITLES else "system"


def size_kb(text: str) -> int:
    return max(1, round(len(text) / 1024))


def as_text(sections: list[tuple[str, str]]) -> str:
    """The whole diagnosis as one plain-text document, the way a report reads."""
    return "\n\n".join(f"== {title} ==\n{body}" for title, body in sections)
