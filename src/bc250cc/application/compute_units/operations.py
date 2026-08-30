"""Plan CU actions; execution stays in UMR/privileged infrastructure."""

from __future__ import annotations

from collections.abc import Sequence

from bc250cc.domain.compute_units import WgpMaskTable


def validate_cu_masks(masks: object) -> tuple[int, int, int, int]:
    if not isinstance(masks, (list, tuple)):
        raise ValueError("The WGP table must contain exactly four shader rows.")
    return WgpMaskTable.from_values(masks).rows


def plan_cu_mask_operations(
    masks: Sequence[int],
    *,
    save_boot: bool = False,
) -> tuple[tuple[str, ...], ...]:
    validated = validate_cu_masks(masks)
    enabled: list[str] = []
    disabled: list[str] = []
    for row_index, mask in enumerate(validated):
        se, sh = divmod(row_index, 2)
        for wgp in range(5):
            target = f"{se}.{sh}.{wgp}"
            (enabled if mask & (1 << wgp) else disabled).append(target)
    operations: list[tuple[str, ...]] = []
    if disabled:
        operations.append(("--yes", "disable-wgp", *disabled))
    if enabled:
        operations.append(("--yes", "enable-wgp", *enabled))
    if save_boot:
        operations.append(("--yes", "write-service-table"))
    return tuple(operations)
