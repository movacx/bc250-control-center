"""Immutable deployment probes."""

from __future__ import annotations

import os
from pathlib import Path


def is_immutable_root(run_root: Path = Path("/run")) -> bool:
    return (run_root / "ostree-booted").exists() or bool(os.environ.get("OSTREE_DEPLOYMENT"))
