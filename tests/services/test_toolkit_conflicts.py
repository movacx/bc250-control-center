"""Detection of other community toolkits that own the same BC-250 state."""

from __future__ import annotations

from pathlib import Path

from bc250cc.infrastructure.toolkit_conflicts import (
    KNOWN_TOOLKITS,
    SHARED_CONFIGURATION,
)


def _touch(root: Path, path: str) -> None:
    target = root / path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")


def test_every_spec_declares_evidence_and_overlap() -> None:
    for spec in KNOWN_TOOLKITS:
        assert spec.markers, f"{spec.identifier} has no marker to detect it"
        assert spec.overlapping_areas, f"{spec.identifier} declares no overlap"
        assert spec.upstream.startswith("https://")
        # A marker that Control Center also writes would accuse itself.
        assert not set(spec.markers) & set(SHARED_CONFIGURATION)

