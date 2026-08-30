"""Shared option/capability mapping for embedded and legacy preparation UI."""
from ..i18n import tr

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


def is_bazzite_host(tools) -> bool:
    """Recognize Bazzite even when a partial inventory lacks its family key."""
    return any(
        "bazzite" in str(tools.get(key) or "").strip().lower()
        for key in ("os_family", "os_id", "os_label", "os_variant", "image_id")
    )


def _restore_bazzite_memory_options(owner) -> None:
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
    owner.ttm_limit_combo.setItemText(
        1, tr("Kernel default (remove BC250 TTM limit)")
    )


def update_memory_controls(owner, tools):
    """Return False only for the existing independent Bazzite workflow."""
    # The dashboard can display Bazzite from OS_LABEL before a background
    # inventory has filled OS_FAMILY.  Treat that label as authoritative for
    # this Bazzite-only workflow, then restore its choices if an earlier
    # partial refresh had replaced them with the disabled generic list.
    if is_bazzite_host(tools):
        _restore_bazzite_memory_options(owner)
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
