"""Game Mode and the Desktop have to say the same thing about the same knob.

The panel used to declare its own limits. Its CPU slider started at 3500 MHz
against a real floor of 3100, so 3100–3450 MHz was unreachable in Game Mode —
and worse, a profile the user had saved at 3200 on the Desktop was clamped to
3500 and *re-applied* at 3500. The clamp was not a display detail; the clamped
number is the one that went back to the hardware.

It also carried its own copy of the VID coefficients (without the frequency
floor below which the upstream fit is meaningless), its own CU mask ladder, and
its own error classifier that disagreed with ``error_catalog`` on eight of
thirty-two markers.

None of that is testable by reading the panel's own tests, because each side
was tested against its own copy. So what is checked here is that the panel has
no copies left: bounds arrive with the state, and codes come from a generated
catalogue.

``dist/index.js`` is checked too. It is committed, it is what actually runs on
a Steam Deck, and a stale bundle would otherwise ship a panel that disagrees
with the source beside it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bc250cc.shared import contract  # noqa: E402

PLUGIN = ROOT / "integrations" / "decky" / "bc250-quick-access"
PANEL = PLUGIN / "src" / "index.tsx"
BUNDLE = PLUGIN / "dist" / "index.js"
CATALOG = PLUGIN / "src" / "generated" / "error_catalog.json"
BACKEND = PLUGIN / "main.py"


def _source(path: Path) -> str:
    if not path.is_file():  # pragma: no cover - packaging layouts
        pytest.skip(f"{path.name} is not present in this checkout")
    return path.read_text(encoding="utf-8")


def _code_lines(path: Path) -> list[str]:
    """Lines that are not comments. The explanations above mention old values."""
    return [
        line
        for line in _source(path).splitlines()
        if not line.strip().startswith(("//", "*", "/*"))
    ]


# ------------------------------------------------------------------- bounds


def test_no_slider_declares_a_numeric_bound():
    offenders = [
        line.strip()[:90]
        for line in _code_lines(PANEL)
        if re.search(r"\bmin=\{-?\d+\}|\bmax=\{-?\d+\}", line)
    ]
    assert offenders == [], offenders


def test_the_panel_reads_its_bounds_from_the_state():
    source = _source(PANEL)
    assert "state.contract" in source
    assert "result.contract?.cpu" in source


def test_the_cpu_floor_is_the_canonical_one_everywhere():
    low, high = contract.CPU_FREQUENCY_RANGE
    backend = _source(BACKEND)
    assert f"range({low}, {high + 1}, {contract.CPU_FREQUENCY_STEP_MHZ})" in backend
    # Fallbacks used only until the first status arrives — the sliders are
    # disabled before then — but they still have to be canon.
    panel = "\n".join(_code_lines(PANEL))
    assert f"?? {low}" in panel, "the pre-status CPU floor is not the canonical one"
    assert f"?? {high}" in panel


def test_the_vid_estimate_keeps_no_coefficients_of_its_own():
    source = _source(PANEL)
    body = source[source.index("function estimateCpuVid("):]
    body = body[: body.index("\n}")]
    for coefficient in ("1.519", "0.004325", ".004325", "2800", "0.0003", ".0003"):
        assert coefficient not in body, f"{coefficient} is still written into the panel"
    assert "model.floor_mhz" in body, "the floor this copy used to drop"


def test_the_compute_units_ladder_is_not_written_into_the_panel():
    source = _source(PANEL)
    body = source[source.index("function masksFromTarget("):]
    body = body[: body.index("\n}")]
    assert "targets" in body, "the ladder has to come from the state"


# ----------------------------------------------------- one error vocabulary


def test_the_generated_catalogue_is_what_the_panel_classifies_with():
    source = _source(PANEL)
    assert 'from "./generated/error_catalog.json"' in source
    assert "errorCatalog.markers_longest_first" in source


def test_every_catalogue_code_reaches_the_bundle():
    payload = json.loads(_source(CATALOG))
    bundle = _source(BUNDLE)
    missing = [entry["code"] for entry in payload["codes"] if entry["code"] not in bundle]
    assert missing == [], f"the committed bundle is stale: {missing}"


def test_every_marker_reaches_the_bundle():
    payload = json.loads(_source(CATALOG))
    bundle = _source(BUNDLE)
    missing = [marker for marker in payload["markers_longest_first"] if marker not in bundle]
    assert missing == [], f"the committed bundle is stale: {missing}"


def test_the_bundle_was_built_from_the_current_source():
    """A committed bundle that lags its source ships a panel nobody reviewed."""
    bundle = _source(BUNDLE)
    assert "result.contract" in bundle, "dist/index.js predates the shared bounds"
    assert "markers_longest_first" in bundle, "dist/index.js predates the catalogue"


# ----------------------------------------------------------- dead surfaces


def test_the_phantom_gpu_profile_is_gone_from_both_sides():
    """``recovery`` passed the backend allowlist and died in the helper.

    No profile generator ever emitted that key, and the panel carried a filter
    for a value that could not occur.
    """
    assert '"recovery"' not in _source(BACKEND)
    assert '"recovery"' not in "\n".join(_code_lines(PANEL))
