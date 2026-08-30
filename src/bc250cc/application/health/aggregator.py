"""Deterministic aggregation of health provider results."""

from __future__ import annotations

from collections.abc import Iterable

from bc250cc.domain.health.models import HealthFinding, HealthSnapshot


def aggregate_findings(findings: Iterable[HealthFinding]) -> HealthSnapshot:
    """Return a stable snapshot without probing or repairing the host."""
    ordered = tuple(sorted(findings, key=lambda item: item.identifier))
    return HealthSnapshot(ordered)
