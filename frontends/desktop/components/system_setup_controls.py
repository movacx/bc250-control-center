"""Shared option/capability mapping for embedded and legacy preparation UI."""

import os

from bc250cc.infrastructure.memory_runtime import (
    TTM_GIB_PRESETS,
    supported_ttm_gib_presets,
)
from bc250cc.shared.contract import VRAM_SIZE_PRESETS_MB

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
    takeover_available = bool(memory.get("zram_takeover_available"))
    # A ZSWAP option blocked only by a foreign ZRAM stays selectable: picking
    # it is how the user confirms disabling that ZRAM, same as Bazzite
    # already lets every option through.
    selectable = set(policies) | ({"zswap-16", "zswap-32"} if takeover_available else set())
    for i in range(combo.count()):
        item = combo.model().item(i)
        value = combo.itemData(i)
        item.setEnabled(value in selectable)
        item.setToolTip(tr(str(policy_reasons.get(value) or "")))
    combo.setEnabled(enabled)
    owner.ttm_limit_combo.setItemText(1, tr("Restore previous TTM limit"))
    owner.ttm_limit_combo.setEnabled(enabled and bool(memory.get("ttm_available")))
    owner.ttm_limit_combo.model().item(1).setEnabled(bool(memory.get("ttm_restore_available")))
    selected_policy = combo.currentData()
    needs_takeover = takeover_available and selected_policy in {"zswap-16", "zswap-32"} and selected_policy not in policies
    owner.memory_swap_apply_button.setEnabled(enabled and selected_policy in selectable and selected_policy != "preserve")
    if hasattr(owner, "memory_zram_warning_frame"):
        owner.memory_zram_warning.setText(
            tr("Applying this will disable the existing ZRAM to make room for ZSWAP. "
               "Takes effect after the next reboot.")
            if needs_takeover else ""
        )
        owner.memory_zram_warning_frame.setVisible(needs_takeover)
    if hasattr(owner, "memory_swap_usage_bar"):
        used = int(memory.get("swap_used_bytes") or 0)
        gib_suffix = str(memory.get("configured_policy") or "").rsplit("-", 1)
        total_gib = int(gib_suffix[-1]) if len(gib_suffix) == 2 and gib_suffix[-1].isdigit() else 0
        total = total_gib * (1024 ** 3)
        active = bool(memory.get("swap_active")) and total > 0
        owner.memory_swap_usage_bar.setVisible(active)
        owner.memory_swap_usage_label.setVisible(active)
        if active:
            percent = min(100, round(used / total * 100))
            owner.memory_swap_usage_bar.setValue(percent)
            owner.memory_swap_usage_label.setText(
                tr_format("{used} / {total} GiB used", used=round(used / (1024 ** 3), 1), total=total_gib)
            )
    if hasattr(owner, "memory_swap_target_combo"):
        target_combo = owner.memory_swap_target_combo
        targets = memory.get("swap_targets") or {}
        expected = ["", *sorted(target for target in targets if target)]
        existing_targets = [target_combo.itemData(i) for i in range(target_combo.count())]
        if existing_targets != expected:
            previous_target = target_combo.currentData()
            target_combo.blockSignals(True)
            target_combo.clear()
            target_combo.addItem(tr("Default (/var/lib)"), "")
            for target in expected[1:]:
                target_combo.addItem(target, target)
            index = target_combo.findData(previous_target)
            target_combo.setCurrentIndex(index if index >= 0 else 0)
            target_combo.blockSignals(False)
        creates_swapfile = selected_policy in {"swap-16", "swap-32", "zswap-16", "zswap-32"}
        target_combo.setEnabled(enabled and creates_swapfile)
        owner.memory_swap_target_label.setVisible(creates_swapfile)
        target_combo.setVisible(creates_swapfile)
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
        elif enabled and any(memory.get(key) for key in
                              ("restore_pending", "zram_pending", "zram_restore_pending", "zswap_pending")):
            label = "Reboot required"
        owner.memory_scope.setText(label)
        owner.memory_scope.set_tone("gray")
    return True
