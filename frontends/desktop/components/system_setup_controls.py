"""Shared option/capability mapping for embedded and legacy preparation UI."""

import os

from bc250cc.infrastructure.memory_runtime import (
    TTM_GIB_PRESETS,
    supported_ttm_gib_presets,
)

from ..i18n import tr, tr_format

MEMORY_OPTIONS = (
    ("Keep current configuration", "preserve"),
    ("Disk swap · 16 GiB", "swap-16"),
    ("Disk swap · 32 GiB", "swap-32"),
    ("ZRAM · up to 4 GiB", "zram"),
    ("Advanced · ZSWAP + 16 GiB swapfile", "zswap-16"),
    ("Advanced heavy loads · ZSWAP + 32 GiB swapfile", "zswap-32"),
    ("Restore BC250 memory changes", "restore"),
)

BAZZITE_MEMORY_OPTIONS = (
    ("Keep Bazzite default (ZRAM)", "current"),
    ("Recommended · ZRAM + 16 GiB emergency swap", "zram-swap-16"),
    ("Advanced · ZSWAP + 16 GiB swapfile", "zswap-16"),
    ("Advanced heavy loads · ZSWAP + 32 GiB swapfile", "zswap-32"),
)

# UMA_SIZE (VRAM) presets, aligned to the 16 MiB CMOS granularity the
# firmware itself enforces (github.com/fanoush/bc250_memcfg). Below 1 GiB the
# label stays in MiB; every other preset here is an exact GiB multiple.
VRAM_SIZE_PRESETS_MB = (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)


def vram_size_label(size_mb: int) -> str:
    if size_mb < 1024:
        return tr_format("{size} MiB", size=size_mb)
    return tr_format("{size} GiB", size=size_mb // 1024)


def is_bazzite_host(tools) -> bool:
    """Recognize Bazzite even when a partial inventory lacks its family key."""
    return any(
        "bazzite" in str(tools.get(key) or "").strip().lower()
        for key in ("os_family", "os_id", "os_label", "os_variant", "image_id")
    )


def bazzite_ui_preview_enabled(environ=None) -> bool:
    """Allow an inert Bazzite card preview on a development workstation."""
    source = os.environ if environ is None else environ
    return str(source.get("BC250_BAZZITE_UI_PREVIEW") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _restore_bazzite_memory_options(owner, tools) -> None:
    combo = owner.memory_policy_combo
    expected = [value for _label, value in BAZZITE_MEMORY_OPTIONS]
    if [combo.itemData(index) for index in range(combo.count())] != expected:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in BAZZITE_MEMORY_OPTIONS:
            combo.addItem(tr(label), value)
        combo.setCurrentIndex(max(0, combo.findData(previous)))
        combo.blockSignals(False)
    ttm_combo = owner.ttm_limit_combo
    state = tools.get("memory_runtime") or {}
    physical = state.get("physical_ram_bytes")
    supported = (
        supported_ttm_gib_presets(physical)
        if type(physical) is int and physical > 0
        else TTM_GIB_PRESETS
    )
    expected_ttm = [0, -1, *supported]
    if [ttm_combo.itemData(index) for index in range(ttm_combo.count())] != expected_ttm:
        previous = ttm_combo.currentData()
        ttm_combo.blockSignals(True)
        ttm_combo.clear()
        ttm_combo.addItem(tr("Keep current TTM limit"), 0)
        ttm_combo.addItem(tr("Kernel default (remove BC250 TTM limit)"), -1)
        for target in supported:
            ttm_combo.addItem(
                tr_format("Limit GPU allocations to {size} GiB", size=target),
                target,
            )
        selected = ttm_combo.findData(previous)
        ttm_combo.setCurrentIndex(selected if selected >= 0 else 0)
        ttm_combo.blockSignals(False)
    else:
        ttm_combo.setItemText(1, tr("Kernel default (remove BC250 TTM limit)"))

    if type(physical) is int and physical > 0:
        visible_gib = physical / (1024 ** 3)
        ttm_combo.setToolTip(
            tr(
                "TTM limits managed GPU pages; it is not a guaranteed VRAM reservation."
            )
            + f"\nMemTotal: {visible_gib:.1f} GiB"
        )


def update_memory_controls(owner, tools):
    """Return False only for the existing independent Bazzite workflow."""
    # The dashboard can display Bazzite from OS_LABEL before a background
    # inventory has filled OS_FAMILY.  Treat that label as authoritative for
    # this Bazzite-only workflow, then restore its choices if an earlier
    # partial refresh had replaced them with the disabled generic list.
    if is_bazzite_host(tools):
        _restore_bazzite_memory_options(owner, tools)
        return False
    setup = tools.get("system_setup") or {}
    memory = setup.get("memory") or {}
    combo = owner.memory_policy_combo
    existing = [combo.itemData(i) for i in range(combo.count())]
    if existing != [value for _, value in MEMORY_OPTIONS]:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in MEMORY_OPTIONS:
            combo.addItem(tr(label), value)
        combo.setCurrentIndex(max(0, combo.findData(previous)))
        combo.blockSignals(False)
    enabled = bool(setup.get("helper_available") and memory.get("supported"))
    policies = memory.get("policies") or []
    policy_reasons = memory.get("policy_reasons") or {}
    for i in range(combo.count()):
        item = combo.model().item(i)
        value = combo.itemData(i)
        item.setEnabled(value in policies)
        item.setToolTip(tr(str(policy_reasons.get(value) or "")))
    combo.setEnabled(enabled)
    owner.ttm_limit_combo.setItemText(1, tr("Restore previous TTM limit"))
    owner.ttm_limit_combo.setEnabled(enabled and bool(memory.get("ttm_available")))
    owner.ttm_limit_combo.model().item(1).setEnabled(bool(memory.get("ttm_restore_available")))
    owner.memory_swap_apply_button.setEnabled(enabled and combo.currentData() in policies and combo.currentData() != "preserve")
    ttm = owner.ttm_limit_combo.currentData()
    owner.memory_ttm_apply_button.setEnabled(enabled and bool(memory.get("ttm_available")) and ttm != 0
                                           and (ttm != -1 or bool(memory.get("ttm_restore_available"))))
    reason = setup.get("reason") or memory.get("reason") or ""
    for widget in (combo, owner.ttm_limit_combo, owner.memory_swap_apply_button, owner.memory_ttm_apply_button):
        widget.setToolTip(tr(reason) if reason else tr("Optional system setup. Review changes before applying."))
    if hasattr(owner, "memory_scope"):
        label = "Testing" if enabled else "Unavailable"
        if enabled and memory.get("phase") == "incomplete":
            label = "Incomplete"
        elif enabled and any(memory.get(key) for key in ("restore_pending", "zram_pending", "zram_restore_pending")):
            label = "Reboot required"
        owner.memory_scope.setText(label)
        owner.memory_scope.set_tone("gray")
    return True
