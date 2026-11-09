#!/usr/bin/env python3
"""Generate the copy of the fan-control engine the root service runs.

``src/bc250cc/domain/fan/engine.py`` is canon; the desktop imports it
normally. ``bc250-fan-pwm-helper`` runs as root under ``python3 -I`` and
cannot import ``bc250cc``, so it loads ``privileged/lib/bc250_fan_engine.py``
by absolute path instead. The artefact is committed, for the same reasons as
``generate_contract.py`` gives (rpm-ostree bakes ``/usr``; the package staging
and the local installer already copy ``privileged/lib``). A test re-runs this
generator in memory and byte-compares.

    python3 scripts/development/generate_fan_engine.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "bc250cc" / "domain" / "fan" / "engine.py"
ARTEFACT = ROOT / "privileged" / "lib" / "bc250_fan_engine.py"

HEADER = (
    "# Generated from src/bc250cc/domain/fan/engine.py by\n"
    "# scripts/development/generate_fan_engine.py. Do not edit; a test\n"
    "# byte-compares this file against the generator's output.\n"
)


def artefact() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    forbidden = [
        line for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and line not in {
            "from __future__ import annotations",
            "import math",
            "from dataclasses import dataclass, replace",
        }
    ]
    if forbidden:
        raise SystemExit(
            "engine.py may import only the standard library modules it already "
            f"uses; found: {forbidden}"
        )
    return HEADER + source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the artefact is out of date")
    arguments = parser.parse_args()
    text = artefact()
    current = ARTEFACT.read_text(encoding="utf-8") if ARTEFACT.is_file() else None
    if current == text:
        print("up to date")
        return 0
    if arguments.check:
        print(f"out of date: {ARTEFACT.relative_to(ROOT)}", file=sys.stderr)
        print("run scripts/development/generate_fan_engine.py", file=sys.stderr)
        return 1
    ARTEFACT.write_text(text, encoding="utf-8")
    print(f"wrote {ARTEFACT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
