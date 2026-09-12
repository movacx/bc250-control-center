"""The CPU frequency bound must mean the same thing in every layer.

It is enforced in four places that cannot import each other: the domain, the
infrastructure validators, the desktop page, and four root-owned privileged
helpers that ship as standalone scripts. A bound changed in one of them and not
the others gives the worst possible result — the interface offers a frequency
the helper then refuses — so this test pins the literals in the helpers to the
domain constant and fails the moment they drift apart.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from bc250cc.domain.cpu import FREQUENCY_RANGE
from bc250cc.infrastructure.quick_access_policy import CPU_QAM_FREQUENCIES

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPERS = (
    "privileged/helpers/bc250-cpu-smu-helper",
    "privileged/helpers/bc250-quick-access-helper",
    "privileged/helpers/bc250-steamos-game-helper",
)
# Any literal comparison of a frequency against a lower and an upper bound.
BOUND_PATTERNS = (
    re.compile(r"\b(\d{4})\s*<=\s*\w*frequency\w*\s*<=\s*(\d{4})\b"),
    re.compile(r"frequency\s*<\s*(\d{4})\s+or\s+\w*frequency\w*\s*>\s*(\d{4})\b"),
)


def _helper_text(name: str) -> str:
    path = REPOSITORY_ROOT / name
    if not path.is_file():  # pragma: no cover - packaging layouts without helpers
        pytest.skip(f"{name} is not present in this checkout")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("helper", HELPERS)
def test_every_helper_bound_matches_the_domain(helper):
    text = _helper_text(helper)
    found = [
        (int(low), int(high))
        for pattern in BOUND_PATTERNS
        for low, high in pattern.findall(text)
    ]
    assert found, f"no frequency bound found in {helper}; did the shape change?"
    for bound in found:
        assert bound == FREQUENCY_RANGE, (helper, bound, FREQUENCY_RANGE)


@pytest.mark.parametrize("helper", HELPERS)
def test_no_cpu_message_quotes_a_stale_bound(helper):
    """The numbers a user reads must be the numbers the code enforces.

    Scoped to CPU wording on purpose: these helpers also quote the GPU range,
    which is a different bound entirely.
    """
    text = _helper_text(helper)
    low, high = FREQUENCY_RANGE
    cpu_lines = [
        line for line in text.splitlines()
        if re.search(r"MHz", line) and re.search(r"cpu|frequency must be", line, re.IGNORECASE)
    ]
    assert cpu_lines, f"no CPU frequency wording found in {helper}"
    for line in cpu_lines:
        for quoted in re.findall(r"(\d{4})\s*[-–]\s*(\d{4})\s*MHz", line):
            assert (int(quoted[0]), int(quoted[1])) == FREQUENCY_RANGE, (helper, line.strip())
        for quoted in re.findall(r"between (\d{4}) and (\d{4}) MHz", line):
            assert (int(quoted[0]), int(quoted[1])) == FREQUENCY_RANGE, (helper, line.strip())
    assert str(low) in text and str(high) in text


def test_the_desktop_page_does_not_keep_its_own_copy():
    from frontends.desktop.pages.cpu_smu import CPU_FREQUENCY_RANGE

    assert CPU_FREQUENCY_RANGE is FREQUENCY_RANGE


def test_the_quick_access_ladder_starts_at_the_domain_floor():
    assert CPU_QAM_FREQUENCIES[0] == FREQUENCY_RANGE[0]
    assert CPU_QAM_FREQUENCIES[-1] == FREQUENCY_RANGE[1]
    assert all(frequency % 50 == 0 for frequency in CPU_QAM_FREQUENCIES)


def test_the_floor_stays_inside_the_voltage_model():
    """``estimated_vid`` returns None below 3000 MHz, so the floor must clear it.

    The ceiling deliberately is *not* checked the same way: the model is
    allowed to predict a VID above the 1.325 V limit at the top of the range,
    and that is how it signals that a frequency needs a deeper undervolt scale
    than the one selected. Only the floor has to be reachable at every scale.
    """
    from bc250cc.domain.cpu.limits import SCALE_RANGE, VID_LIMIT_MV, estimated_vid

    low, _high = FREQUENCY_RANGE
    assert low >= 3000
    for scale in (SCALE_RANGE[0], -23, SCALE_RANGE[1]):
        estimate = estimated_vid(low, scale)
        assert estimate is not None
        assert estimate <= VID_LIMIT_MV, (low, scale, estimate)
