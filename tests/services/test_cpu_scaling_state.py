"""Detection of a board left without CPU frequency scaling.

The BC-250 firmware declares idle states but no performance states, so
without the reviewed ACPI override the kernel registers no cpufreq driver and
every core runs pinned near its base clock. The interface reported nothing.
"""

from __future__ import annotations

from pathlib import Path


def _write(root: Path, relative: str, content: bytes | str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="ascii")

