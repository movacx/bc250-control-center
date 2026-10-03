"""The shipped Decky bundle, run through a JavaScript engine.

dist/index.js is sometimes patched by hand on machines without Node; these
checks catch a broken bundle before Decky does. Skipped without quickjs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

quickjs = pytest.importorskip("quickjs")

BUNDLE = Path(__file__).resolve().parents[2] / "integrations/decky/bc250-quick-access/dist/index.js"


def test_the_bundle_parses():
    body = BUNDLE.read_text(encoding="utf-8").replace("export { index as default };", "")
    quickjs.Context().eval("(function(){\n" + body + "\n});")


def _core_summary():
    source = BUNDLE.read_text(encoding="utf-8")
    start = source.index("function physicalCores(")
    end = source.index("function CoreGrid(", start)
    busiest_start = source.index("    const busiest = (threads) => {", end)
    busiest_end = source.index("    };", busiest_start) + 6
    context = quickjs.Context()
    context.eval(source[start:end] + "\nfunction summarize(cores, slots) {" + source[busiest_start:busiest_end] + """
      const groups = physicalCores(cores, slots);
      return JSON.stringify(groups.map((group) => group.threads.length
        ? (busiest(group.threads).frequency_mhz / 1000).toFixed(2) : "locked"));
    }""")
    # A Qt test earlier in the run may switch the process to a decimal-comma
    # locale, which quickjs's number formatting follows.
    return lambda cores: [value.replace(",", ".") for value in json.loads(context.eval(f"summarize({json.dumps(cores)}, 8)"))]


def _cores(ids, frequency, percent):
    return [
        {"core": index, "core_id": core_id, "frequency_mhz": frequency, "percent": percent}
        for index, core_id in enumerate(ids)
    ]


def test_six_cores_twelve_threads_show_the_two_locked_cores():
    summary = _core_summary()(_cores((0, 0, 1, 1, 2, 2, 4, 4, 5, 5, 6, 6), 3840, 90))
    assert summary == ["3.84", "3.84", "3.84", "locked", "3.84", "3.84", "3.84", "locked"]


def test_eight_unlocked_cores_sixteen_threads_show_eight_cards():
    summary = _core_summary()(_cores(tuple(index // 2 for index in range(16)), 3840, 90))
    assert summary == ["3.84"] * 8


def test_an_idle_core_shows_its_live_clock_not_the_nominal_one():
    cores = [
        {"core": 0, "core_id": 0, "frequency_mhz": 1397, "percent": 0},
        {"core": 1, "core_id": 0, "frequency_mhz": 3194, "percent": 0},
    ]
    assert _core_summary()(cores)[0] == "1.40"
