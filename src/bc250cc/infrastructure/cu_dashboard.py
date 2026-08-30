"""Pure parser for BC250 live-manager topology dashboards.

The parser consumes text as untrusted data.  It performs no command execution,
privilege escalation or hardware access and only enriches a caller-provided
fallback state after all four shader rows have been validated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

ROW_PATTERN = re.compile(
    r"\|\s*(SE[01]\.SH[01])\s*\|\s*"
    + r"\s*\|\s*".join([r"(D\+|S\+|D!|--)"] * 5)
    + r"\s*\|\s*(0x[0-9a-fA-F]+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*/\s*10\s*\|",
    re.IGNORECASE,
)

ROW_ERROR = (
    "The 40CU tool returned duplicate rows, inconsistent tokens, or an out-of-range CU count. "
    "Its output format may have changed."
)
TOTAL_ERROR = (
    "The 40CU tool returned a missing, duplicate, inconsistent, or invalid active-CU total. "
    "Its output format may have changed."
)
FORMAT_ERROR = (
    "The 40CU tool output was received, but the expected four topology rows could not be parsed. "
    "Update BC250 Control Center or the live manager before changing CU routing."
)


def clean_dashboard(text: object) -> str:
    ansi = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
    lines = []
    for line in str(text or "").splitlines():
        cleaned = ansi.sub("", line).rstrip()
        if cleaned.strip() not in {"", "== Process finished with exit code 0 =="}:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def _metadata(state: dict[str, object], text: str) -> None:
    patterns = {
        "umr": r"^\s*UMR\s*:\s*(.+?)\s*$",
        "umr_instance": r"^\s*UMR inst\s*:\s*(.+?)\s*$",
        "asic": r"^\s*ASIC\s*:\s*(.+?)\s*$",
        "service": r"^\s*Service\s*:\s*(.+?)\s*$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            state[key] = match.group(1).strip()
    amdgpu = re.search(
        r"^\s*amdgpu\s*:\s*bc250_cc_write_mode=([^,]+),\s*active_cu_number=(.+?)\s*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if amdgpu:
        state["amdgpu_mode"] = amdgpu.group(1).strip()
        state["amdgpu_active_cus"] = amdgpu.group(2).strip()


def _service_and_boot(state: dict[str, object], text: str) -> None:
    service = str(state.get("service") or "").strip()
    lowered_service = service.lower()
    installed = bool(service and lowered_service not in {"not installed", "missing", "unknown"})
    state["service_installed"] = installed
    state["service_enabled"] = lowered_service in {"enabled", "active", "running"}
    if not installed:
        state["service"] = "Not installed"
    lowered = text.lower()
    boot_states = (
        ("pending changes", "Pending changes", "pending"),
        ("current table saved", "Current table saved", "saved"),
        ("saved boot table", "Current table saved", "saved"),
        ("no saved table", "No saved table", "not_saved"),
    )
    for marker, label, key in boot_states:
        if marker in lowered:
            state["boot_sync"], state["boot_sync_key"] = label, key
            break
    else:
        if installed:
            state["boot_sync"], state["boot_sync_key"] = "Unknown", "unknown"


def _rows(text: str) -> tuple[dict[str, dict[str, object]], str]:
    parsed: dict[str, dict[str, object]] = {}
    error = ""
    for match in ROW_PATTERN.finditer(text):
        name, cus = match.group(1).upper(), int(match.group(9))
        if name in parsed or not 0 <= cus <= 10:
            error = ROW_ERROR
            continue
        tokens = [match.group(index).upper() for index in range(2, 7)]
        mask = sum(1 << index for index, token in enumerate(tokens) if token in {"D+", "S+"})
        driver_mask = sum(1 << index for index, token in enumerate(tokens) if token in {"D+", "D!"})
        if cus != mask.bit_count() * 2:
            error = ROW_ERROR
            continue
        parsed[name] = {
            "name": name, "tokens": tokens, "mask": mask,
            "driver_mask": driver_mask, "spi": match.group(7).lower(),
            "cc": match.group(8).strip(), "cus": cus,
        }
    return parsed, error


def _apply_topology(
    state: dict[str, object], parsed: dict[str, dict[str, object]], row_names: Iterable[str]
) -> None:
    names = tuple(row_names)
    if len(parsed) != len(names) or any(name not in parsed for name in names):
        return
    rows = []
    for index, name in enumerate(names):
        row = dict(parsed[name])
        row["index"] = index
        rows.append(row)
    state["rows"] = rows
    state["masks"] = [row["mask"] for row in rows]
    state["driver_masks"] = [row["driver_mask"] for row in rows]
    state["active_cus"] = sum(int(row["cus"]) for row in rows)
    state["routed_wgps"] = int(state["active_cus"]) // 2
    state["driver_topology_available"] = any(row["driver_mask"] for row in rows)
    state["available"] = True


def _validate_total(state: dict[str, object], text: str) -> None:
    matches = re.findall(
        r"CUs\s+active\s*&?\s*routed\s*:\s*(\d+)\s*/\s*40",
        text,
        re.IGNORECASE,
    )
    if not matches:
        return
    if len(matches) != 1:
        state["parse_error"] = TOTAL_ERROR
        state["available"] = False
        return
    total = int(matches[0])
    if not 0 <= total <= 40 or total % 2:
        state["parse_error"] = TOTAL_ERROR
        state["available"] = False
        return
    if state.get("available"):
        if int(state.get("active_cus") or 0) != total:
            state["parse_error"] = TOTAL_ERROR
            state["available"] = False
        return
    state["active_cus"], state["routed_wgps"] = total, total // 2


def _classify_mode(state: dict[str, object]) -> None:
    active = int(state.get("active_cus") or 0)
    masks = list(state.get("masks") or [])
    driver_masks = list(state.get("driver_masks") or [])
    if active >= 40 and masks == [0x1F] * 4:
        state["mode"], state["mode_key"] = "Full 40 CUs", "full"
    elif (
        state.get("driver_topology_available") and masks == driver_masks
    ) or (active == 24 and masks == [0x07] * 4):
        state["mode"], state["mode_key"] = "Factory 24 CUs", "factory"
    else:
        state["mode"], state["mode_key"] = f"Custom {active} CUs", "custom"


def parse_dashboard(
    text: object,
    *,
    base_state: dict[str, object],
    row_names: Iterable[str],
    source: str,
    updated_at: str,
) -> dict[str, object]:
    state = dict(base_state)
    cleaned = clean_dashboard(text)
    state.update(raw=cleaned, source=source, fresh=source == "live", updated_at=updated_at)
    _metadata(state, cleaned)
    _service_and_boot(state, cleaned)
    parsed, row_error = _rows(cleaned)
    state["parse_error"] = row_error
    _apply_topology(state, parsed, row_names)
    _validate_total(state, cleaned)
    if cleaned and not state.get("available") and not state.get("parse_error"):
        state["parse_error"] = FORMAT_ERROR
    _classify_mode(state)
    return state
